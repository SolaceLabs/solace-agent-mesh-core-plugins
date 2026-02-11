import pytest
import sqlalchemy as sa
from testcontainers.postgres import PostgresContainer
from testcontainers.mysql import MySqlContainer
from testcontainers.mssql import SqlServerContainer
from testcontainers.oracle import OracleDbContainer
from dataclasses import dataclass
from typing import Type, Callable

from sam_sql_database_tool.tools import DatabaseConfig, SqlDatabaseTool
from .test_data import populate_db


@dataclass
class DatabaseTestConfig:
    """A data class to hold database-specific test configurations."""

    name: str
    container_class: Type
    image: str
    connection_url_fn: Callable


@pytest.fixture(
    scope="session",
    params=[
        pytest.param(
            DatabaseTestConfig(
                name="postgresql",
                container_class=PostgresContainer,
                image="postgres:13",
                connection_url_fn=lambda c: c.get_connection_url(),
            ),
            id="postgresql",
        ),
        pytest.param(
            DatabaseTestConfig(
                name="mysql",
                container_class=MySqlContainer,
                image="mysql:8.0",
                connection_url_fn=lambda c: (
                    f"mysql+pymysql://{c.username}:{c.password}@"
                    f"{c.get_container_host_ip()}:{c.get_exposed_port(3306)}/{c.dbname}"
                ),
            ),
            id="mysql",
        ),
        pytest.param(
            DatabaseTestConfig(
                name="mariadb",
                container_class=MySqlContainer,
                image="mariadb:latest",
                connection_url_fn=lambda c: (
                    f"mysql+pymysql://{c.username}:{c.password}@"
                    f"{c.get_container_host_ip()}:{c.get_exposed_port(3306)}/{c.dbname}"
                ),
            ),
            id="mariadb",
        ),
        pytest.param(
            DatabaseTestConfig(
                name="mssql-msodbc18",
                container_class=SqlServerContainer,
                image="mcr.microsoft.com/mssql/server:2022-latest",
                connection_url_fn=lambda c: (
                    f"mssql+pyodbc://sa:{c.password}@"
                    f"{c.get_container_host_ip()}:{c.get_exposed_port(1433)}/master"
                    f"?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
                ),
            ),
            id="mssql-msodbc18",
        ),
        pytest.param(
            DatabaseTestConfig(
                name="mssql-freetds",
                container_class=SqlServerContainer,
                image="mcr.microsoft.com/mssql/server:2022-latest",
                connection_url_fn=lambda c: (
                    f"mssql+pyodbc://sa:{c.password}@"
                    f"{c.get_container_host_ip()}:{c.get_exposed_port(1433)}/master"
                    f"?driver=FreeTDS&TrustServerCertificate=yes"
                ),
            ),
            id="mssql-freetds",
        ),
        pytest.param(
            DatabaseTestConfig(
                name="oracle",
                container_class=OracleDbContainer,
                image="gvenzl/oracle-xe:21-slim",
                connection_url_fn=lambda c: c.get_connection_url().replace(
                    "oracle+cx_oracle://", "oracle+oracledb://"
                ),
            ),
            id="oracle",
        ),
    ],
)
def db_config(request):
    """Provides database configuration for each backend, defined via pytest.param."""
    return request.param


@pytest.fixture(scope="session")
def database_container(db_config: DatabaseTestConfig):
    """Starts and stops a Docker container for the configured database."""
    if db_config.name.startswith("mssql"):
        # MSSQL container has a different constructor signature
        with db_config.container_class(db_config.image) as container:
            container.db_config = db_config
            yield container
    elif db_config.name == "oracle":
        # Oracle container with explicit credentials
        with db_config.container_class(
            db_config.image,
            username="test_user",
            password="test_password",
        ) as container:
            container.db_config = db_config
            yield container
    else:
        with db_config.container_class(
            db_config.image, dbname="test_db", username="test_user", password="test_password"
        ) as container:
            if db_config.name in ["mysql", "mariadb"]:
                container.with_env("MYSQL_ROOT_PASSWORD", "root_password")
            # Attach the config to the container object for easy access in other fixtures
            container.db_config = db_config
            yield container


@pytest.fixture(scope="function")
def database_engine(database_container):
    """Provides a SQLAlchemy engine for the database and populates it."""
    db_config = database_container.db_config
    connection_url = db_config.connection_url_fn(database_container)
    engine = sa.create_engine(connection_url)
    try:
        populate_db(engine)
        yield engine, db_config
    finally:
        engine.dispose()


@pytest.fixture(scope="function", params=[False, True], ids=["auto_schema", "manual_schema"])
async def db_tool_provider(request, database_container, database_engine):
    """Yields an initialized SqlDatabaseTool for each database provider."""
    manual_schema = request.param
    engine, db_config = database_engine

    connection_string = db_config.connection_url_fn(database_container)

    config_dict = {
        "tool_name": f"{db_config.name}_test_tool",
        "connection_string": connection_string,
    }

    if manual_schema:
        config_dict["tool_name"] = f"{db_config.name}_manual_schema_tool"
        config_dict["auto_detect_schema"] = False
        config_dict["schema_summary_override"] = "MANUAL_SCHEMA_TEST"

    tool_config = DatabaseConfig(**config_dict)
    tool = SqlDatabaseTool(tool_config)
    await tool.init(component=None, tool_config={})

    yield tool

    await tool.cleanup(component=None, tool_config={})
