import pytest
import sqlalchemy as sa
from testcontainers.postgres import PostgresContainer
from testcontainers.mysql import MySqlContainer

from sam_sql_database_tool.tools import DatabaseConfig, SqlDatabaseTool
from .test_data import populate_db

# --- PostgreSQL Setup ---
@pytest.fixture(scope="session")
def postgres_container():
    """Starts and stops the PostgreSQL Docker container using testcontainers."""
    with PostgresContainer(
        "postgres:13",
        dbname="test_db",
        username="test_user",
        password="test_password"
    ) as container:
        yield container

@pytest.fixture(scope="function")
def postgres_engine(postgres_container):
    """Provides a SQLAlchemy engine for the PostgreSQL database and populates it."""
    engine = sa.create_engine(postgres_container.get_connection_url())
    try:
        populate_db(engine)
        yield engine
    finally:
        engine.dispose()


# --- MySQL Setup ---
@pytest.fixture(scope="session")
def mysql_container():
    """Starts and stops the MySQL Docker container using testcontainers."""
    with MySqlContainer(
        "mysql:8.0",
        dbname="test_db",
        username="test_user",
        password="test_password"
    ) as container:
        container.with_env("MYSQL_ROOT_PASSWORD", "root_password")
        yield container

@pytest.fixture(scope="function")
def mysql_engine(mysql_container):
    """Provides a SQLAlchemy engine for the MySQL database and populates it."""
    connection_url = (
        f"mysql+pymysql://{mysql_container.username}:"
        f"{mysql_container.password}@"
        f"{mysql_container.get_container_host_ip()}:"
        f"{mysql_container.get_exposed_port(3306)}/"
        f"{mysql_container.dbname}"
    )
    engine = sa.create_engine(connection_url)
    try:
        populate_db(engine)
        yield engine
    finally:
        engine.dispose()


# --- MariaDB Setup ---
@pytest.fixture(scope="session")
def mariadb_container():
    """Starts and stops the MariaDB Docker container using testcontainers."""
    with MySqlContainer(
        "mariadb:latest",
        dbname="test_db",
        username="test_user",
        password="test_password"
    ) as container:
        container.with_env("MYSQL_ROOT_PASSWORD", "root_password")
        yield container

@pytest.fixture(scope="function")
def mariadb_engine(mariadb_container):
    """Provides a SQLAlchemy engine for the MariaDB database and populates it."""
    connection_url = (
        f"mysql+pymysql://{mariadb_container.username}:"
        f"{mariadb_container.password}@"
        f"{mariadb_container.get_container_host_ip()}:"
        f"{mariadb_container.get_exposed_port(3306)}/"
        f"{mariadb_container.dbname}"
    )
    engine = sa.create_engine(connection_url)
    try:
        populate_db(engine)
        yield engine
    finally:
        engine.dispose()


# --- Generic Tool Provider ---
@pytest.fixture(
    scope="function",
    params=["postgresql", "mysql", "mariadb"]
)
async def db_tool_provider(request):
    """Yields an initialized SqlDatabaseTool for each database provider."""
    db_type = request.param
    config_dict = None

    if db_type == "postgresql":
        container = request.getfixturevalue("postgres_container")
        request.getfixturevalue("postgres_engine")
        connection_string = container.get_connection_url()
        config_dict = {
            "tool_name": "postgres_test_tool",
            "connection_string": connection_string,
        }
    elif db_type == "mysql":
        container = request.getfixturevalue("mysql_container")
        request.getfixturevalue("mysql_engine")
        connection_string = (
            f"mysql+pymysql://{container.username}:"
            f"{container.password}@"
            f"{container.get_container_host_ip()}:"
            f"{container.get_exposed_port(3306)}/"
            f"{container.dbname}"
        )
        config_dict = {
            "tool_name": "mysql_test_tool",
            "connection_string": connection_string,
        }
    elif db_type == "mariadb":
        container = request.getfixturevalue("mariadb_container")
        request.getfixturevalue("mariadb_engine")
        connection_string = (
            f"mysql+pymysql://{container.username}:"
            f"{container.password}@"
            f"{container.get_container_host_ip()}:"
            f"{container.get_exposed_port(3306)}/"
            f"{container.dbname}"
        )
        config_dict = {
            "tool_name": "mariadb_test_tool",
            "connection_string": connection_string,
        }

    tool_config = DatabaseConfig(**config_dict)
    tool = SqlDatabaseTool(tool_config)
    await tool.init(component=None, tool_config={})

    yield tool

    await tool.cleanup(component=None, tool_config={})


@pytest.fixture(
    scope="function",
    params=["postgresql", "mysql", "mariadb"]
)
async def db_tool_provider_manual_schema(request):
    """Yields a tool configured with a manual schema override for each provider."""
    db_type = request.param
    connection_string = None

    if db_type == "postgresql":
        container = request.getfixturevalue("postgres_container")
        request.getfixturevalue("postgres_engine")
        connection_string = container.get_connection_url()
    elif db_type == "mysql":
        container = request.getfixturevalue("mysql_container")
        request.getfixturevalue("mysql_engine")
        connection_string = (
            f"mysql+pymysql://{container.username}:"
            f"{container.password}@"
            f"{container.get_container_host_ip()}:"
            f"{container.get_exposed_port(3306)}/"
            f"{container.dbname}"
        )
    elif db_type == "mariadb":
        container = request.getfixturevalue("mariadb_container")
        request.getfixturevalue("mariadb_engine")
        connection_string = (
            f"mysql+pymysql://{container.username}:"
            f"{container.password}@"
            f"{container.get_container_host_ip()}:"
            f"{container.get_exposed_port(3306)}/"
            f"{container.dbname}"
        )

    config_dict = {
        "tool_name": f"{db_type}_manual_schema_tool",
        "connection_string": connection_string,
        "auto_detect_schema": False,
        "schema_summary_override": "MANUAL_SCHEMA_TEST"
    }
    
    tool_config = DatabaseConfig(**config_dict)
    tool = SqlDatabaseTool(tool_config)
    await tool.init(component=None, tool_config={})

    yield tool

    await tool.cleanup(component=None, tool_config={})
