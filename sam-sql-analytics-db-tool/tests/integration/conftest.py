import pytest
import sqlalchemy as sa
from testcontainers.postgres import PostgresContainer
from testcontainers.mysql import MySqlContainer
from testcontainers.mssql import SqlServerContainer
from testcontainers.oracle import OracleDbContainer
from dataclasses import dataclass
from typing import Type, Callable, Optional
import tempfile
import os
from unittest.mock import Mock

from sam_sql_analytics_db_tool.tools import SqlAnalyticsDbTool
from data_helper import metadata, populate_db

@dataclass
class DatabaseTestConfig:
    """A data class to hold database-specific test configurations."""
    name: str
    container_class: Optional[Type]
    image: Optional[str]
    connection_url_fn: Callable
    dialect: str
    requires_driver: bool = False
    driver_name: Optional[str] = None
    env_vars: dict = None
    is_containerized: bool = True

@pytest.fixture(
    scope="session",
    params=[
        pytest.param(
            DatabaseTestConfig(
                name="postgresql",
                container_class=PostgresContainer,
                image="postgres:14",
                dialect="postgresql",
                connection_url_fn=lambda c: c.get_connection_url().replace("postgresql+psycopg2", "postgresql"),
                env_vars={}
            ),
            id="postgresql",
        ),
        pytest.param(
            DatabaseTestConfig(
                name="mysql",
                container_class=MySqlContainer,
                image="mysql:8.0",
                dialect="mysql",
                connection_url_fn=lambda c: (
                    f"mysql+pymysql://{c.username}:{c.password}@"
                    f"{c.get_container_host_ip()}:{c.get_exposed_port(3306)}/{c.dbname}"
                ),
                env_vars={"MYSQL_ROOT_PASSWORD": "root_password"}
            ),
            id="mysql",
        ),
        # # MSSQL - slow startup (2-3 minutes), enable with: pytest -m slow
        # pytest.param(
        #     DatabaseTestConfig(
        #         name="mssql",
        #         container_class=SqlServerContainer,
        #         image="mcr.microsoft.com/mssql/server:2019-latest",
        #         dialect="mssql",
        #         connection_url_fn=lambda c: (
        #             f"mssql+pyodbc://sa:YourStrong@Passw0rd@"
        #             f"{c.get_container_host_ip()}:{c.get_exposed_port(1433)}/master"
        #             f"?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
        #         ),
        #         env_vars={"ACCEPT_EULA": "Y", "SA_PASSWORD": "YourStrong@Passw0rd"}
        #     ),
        #     id="mssql",
        #     marks=pytest.mark.slow,
        # ),
        # SQLite disabled temporarily - needs special OpenMetadata config structure
        # pytest.param(
        #     DatabaseTestConfig(
        #         name="sqlite",
        #         container_class=None,
        #         image=None,
        #         dialect="sqlite",
        #         connection_url_fn=lambda c: f"sqlite:///{tempfile.gettempdir()}/test_db_{c.name}.db",
        #         env_vars={},
        #         is_containerized=False
        #     ),
        #     id="sqlite",
        # ),
        # Oracle disabled temporarily - container takes 3-5 minutes to start
        # pytest.param(
        #     DatabaseTestConfig(
        #         name="oracle",
        #         container_class=OracleDbContainer,
        #         image="gvenzl/oracle-xe:21-slim",
        #         dialect="oracle",
        #         connection_url_fn=lambda c: (
        #             f"oracle+oracledb://{c.username}:{c.password}@"
        #             f"{c.get_container_host_ip()}:{c.get_exposed_port(1521)}/XE"
        #         ),
        #         env_vars={
        #             "ORACLE_PASSWORD": "test_password",
        #             "APP_USER": "test_user",
        #             "APP_USER_PASSWORD": "test_password"
        #         }
        #     ),
        #     id="oracle",
        # ),
        # pytest.param(
        #     DatabaseTestConfig(
        #         name="mariadb",
        #         container_class=MySqlContainer,
        #         image="mysql:8.0",
        #         dialect="mysql+pymysql",
        #         connection_url_fn=lambda c: (
        #             f"mysql://{c.username}:{c.password}@"
        #             f"{c.get_container_host_ip()}:{c.get_exposed_port(3306)}/{c.dbname}"
        #         ),
        #         env_vars={"MYSQL_ROOT_PASSWORD": "root_password"}
        #     ),
        #     id="mysql",
        # ),
        # pytest.param(
        #     DatabaseTestConfig(
        #         name="mariadb",
        #         container_class=MySqlContainer,
        #         image="mariadb:latest",
        #         dialect="mysql+pymysql",
        #         connection_url_fn=lambda c: (
        #             f"mysql://{c.username}:{c.password}@"
        #             f"{c.get_container_host_ip()}:{c.get_exposed_port(3306)}/{c.dbname}"
        #         ),
        #         env_vars={"MYSQL_ROOT_PASSWORD": "root_password"}
        #     ),
        #     id="mariadb",
        # ),
        # pytest.param(
        #     DatabaseTestConfig(
        #         name="oracle",
        #         container_class=OracleDbContainer,
        #         image="gvenzl/oracle-xe:21-slim",
        #         dialect="oracle+oracledb",
        #         connection_url_fn=lambda c: (
        #             f"oracle://{c.username}:{c.password}@"
        #             f"{c.get_container_host_ip()}:{c.get_exposed_port(1521)}/XE"
        #             f"?mode=SYSDBA"
        #         ),
        #         env_vars={
        #             "ORACLE_PASSWORD": "test_password",
        #             "APP_USER": "test_user",
        #             "APP_USER_PASSWORD": "test_password"
        #         }
        #     ),
        #     id="oracle",
        # ),
        # pytest.param(
        #     DatabaseTestConfig(
        #         name="sqlserver",
        #         container_class=SqlServerContainer,
        #         image="mcr.microsoft.com/mssql/server:2019-latest",
        #         dialect="mssql+pyodbc",
        #         requires_driver=True,
        #         driver_name="ODBC Driver 18 for SQL Server",
        #         connection_url_fn=lambda c: (
        #             f"mssql://{c.username}:{c.password}@"
        #             f"{c.get_container_host_ip()}:{c.get_exposed_port(1433)}/test_db"
        #             f"?driver=ODBC+Driver+18+for+SQL+Server"
        #         ),
        #         env_vars={"ACCEPT_EULA": "Y", "SA_PASSWORD": "test_Password123"}
        #     ),
        #     id="sqlserver",
        # ),
        # pytest.param(
        #     DatabaseTestConfig(
        #         name="snowflake",
        #         container_class=None,
        #         image=None,
        #         dialect="snowflake",
        #         connection_url_fn=lambda c: (
        #             f"snowflake://{os.getenv('SNOWFLAKE_USER')}:{os.getenv('SNOWFLAKE_PASSWORD')}@"
        #             f"{os.getenv('SNOWFLAKE_ACCOUNT')}/{os.getenv('SNOWFLAKE_DATABASE')}/"
        #             f"{os.getenv('SNOWFLAKE_SCHEMA')}?warehouse={os.getenv('SNOWFLAKE_WAREHOUSE')}"
        #         ),
        #         env_vars={},
        #         is_containerized=False
        #     ),
        #     id="snowflake",
        #     marks=pytest.mark.skipif(
        #         not os.getenv("SNOWFLAKE_ACCOUNT"),
        #         reason="Snowflake credentials not configured"
        #     )
        # ),
    ],
)
def db_config(request):
    """Provides database configuration for each backend."""
    return request.param

@pytest.fixture(scope="session")
def database_container(db_config: DatabaseTestConfig):
    """Starts and stops a Docker container for the configured database, or handles file-based DBs."""
    if not hasattr(db_config, 'is_containerized') or db_config.is_containerized:
        # Containerized databases (PostgreSQL, MySQL, Oracle, etc.)
        with db_config.container_class(
            db_config.image, dbname="test_db", username="test_user", password="test_password"
        ) as container:
            # Apply all environment variables from config (database-agnostic)
            for key, value in (db_config.env_vars or {}).items():
                container.with_env(key, value)

            # Attach the config to the container object for easy access in other fixtures
            container.db_config = db_config
            yield container
    else:
        # Non-containerized databases (SQLite, Snowflake with env credentials)
        # Create a mock container object that just holds the config
        class MockContainer:
            def __init__(self, config):
                self.db_config = config
                self.name = config.name  # Add name attribute for connection_url_fn

        yield MockContainer(db_config)

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

@pytest.fixture
def mock_component():
    """Create mock component for async operations."""
    component = Mock()
    async def run_in_executor(func, *args, **kwargs):
        return func(*args, **kwargs)
    component.run_in_executor = run_in_executor
    return component

@pytest.fixture
def analytics_tool_config(database_container, database_engine):
    """Create tool configuration for testing."""
    engine, db_config = database_engine
    return {
        "tool_name": f"{db_config.name}_analytics_tool",
        "tool_description": f"Test analytics tool for {db_config.name}",
        "connection_string": db_config.connection_url_fn(database_container),
        "pool": {
            "pool_size": 1,
            "max_overflow": 1,
            "pool_timeout": 30,
            "pool_recycle": 1800,
            "pool_pre_ping": True
        },
        "timeouts": {
            "connect_timeout": 5,
            "statement_timeout_ms": 10000,
            "query_limit_rows": 1000
        },
        "security": {
            "blocked_operations": ["DROP", "DELETE", "UPDATE", "INSERT", "CREATE"],
            "warning_operations": ["WITH"]
        },
        "profiling": {
            "sample_size": 100,
            "adaptive_sampling": True
        }
    }

@pytest.fixture
async def analytics_tool(database_container, analytics_tool_config, mock_component):
    """Initialize analytics tool with test database."""
    # Create engine and populate test data
    engine = sa.create_engine(analytics_tool_config["connection_string"])
    populate_db(engine)
    
    # Initialize tool
    tool = SqlAnalyticsDbTool(analytics_tool_config)
    await tool.init(mock_component, analytics_tool_config)
    
    yield tool
    
    # Cleanup
    metadata.drop_all(engine)
    await tool.cleanup(mock_component, analytics_tool_config)
