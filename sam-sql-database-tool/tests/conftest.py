import pytest
import psycopg2
import pymysql
import oracledb
import subprocess
import time
import sqlalchemy as sa
from sam_sql_database_tool.tools import DatabaseConfig, SqlDatabaseTool
from .test_data import populate_db

# --- Generic Docker Service Factory ---
@pytest.fixture(scope="session")
def _docker_service_factory(request):
    """A factory for creating Docker-based database services."""
    
    def _factory(container_name, image, env_vars, internal_port, connection_check_fn):
        # Ensure the container is stopped and removed before starting
        subprocess.run(["docker", "stop", container_name], check=False, capture_output=True)
        subprocess.run(["docker", "rm", container_name], check=False, capture_output=True)
        
        run_command = ["docker", "run", "--name", container_name, "-d", "-p", f"0.0.0.0::{internal_port}"]
        for key, value in env_vars.items():
            run_command.extend(["-e", f"{key}={value}"])
        run_command.append(image)
        
        subprocess.run(run_command, check=True)

        # Give the container a moment to start and potentially fail
        time.sleep(5)

        # Verify the container is actually running before proceeding
        container_check = subprocess.run(
            ["docker", "ps", "-f", f"name={container_name}", "-f", "status=running", "--quiet"],
            capture_output=True, text=True, check=True
        )
        if not container_check.stdout.strip():
            logs_proc = subprocess.run(["docker", "logs", container_name], capture_output=True, text=True)
            pytest.fail(
                f"Container '{container_name}' failed to start or exited prematurely.\n"
                f"Docker logs:\n{logs_proc.stderr or logs_proc.stdout}"
            )

        # Get the dynamically assigned host port
        port_proc = subprocess.run(
            ["docker", "port", container_name, f"{internal_port}/tcp"],
            check=True, capture_output=True, text=True
        )
        host_port = int(port_proc.stdout.strip().split(":")[-1])
        
        # Wait for the database to be ready
        retries = 60
        while retries > 0:
            try:
                connection_check_fn(host_port)
                break
            except Exception:
                retries -= 1
                time.sleep(5)
        
        if retries == 0:
            pytest.fail(f"Could not connect to {container_name} container.")

        def finalizer():
            subprocess.run(["docker", "stop", container_name], check=False, capture_output=True)
            subprocess.run(["docker", "rm", container_name], check=False, capture_output=True)
        
        request.addfinalizer(finalizer)
        return host_port

    return _factory


# --- PostgreSQL Setup (Docker-based) ---
@pytest.fixture(scope="session")
def postgres_service(_docker_service_factory):
    """Starts and stops the PostgreSQL Docker container."""
    
    def _connection_check(port):
        conn = psycopg2.connect(
            host="127.0.0.1", port=port, user="test_user",
            password="test_password", dbname="test_db"
        )
        conn.close()

    return _docker_service_factory(
        container_name="postgres_test_container",
        image="postgres:13",
        env_vars={
            "POSTGRES_DB": "test_db",
            "POSTGRES_USER": "test_user",
            "POSTGRES_PASSWORD": "test_password",
        },
        internal_port=5432,
        connection_check_fn=_connection_check
    )

@pytest.fixture(scope="function")
def postgres_engine(postgres_service):
    """Provides a SQLAlchemy engine for the PostgreSQL database and populates it."""
    connection_string = f"postgresql+psycopg2://test_user:test_password@127.0.0.1:{postgres_service}/test_db"
    engine = sa.create_engine(connection_string)
    try:
        populate_db(engine)
        yield engine
    finally:
        engine.dispose()

# --- MySQL Setup (Docker-based) ---
@pytest.fixture(scope="session")
def mysql_service(_docker_service_factory):
    """Starts and stops the MySQL Docker container."""

    def _connection_check(port):
        conn = pymysql.connect(
            host="127.0.0.1", port=port, user="test_user",
            password="test_password", database="test_db"
        )
        conn.close()

    return _docker_service_factory(
        container_name="mysql_test_container",
        image="mysql:8.0",
        env_vars={
            "MYSQL_DATABASE": "test_db",
            "MYSQL_USER": "test_user",
            "MYSQL_PASSWORD": "test_password",
            "MYSQL_ROOT_PASSWORD": "root_password",
        },
        internal_port=3306,
        connection_check_fn=_connection_check
    )

@pytest.fixture(scope="function")
def mysql_engine(mysql_service):
    """Provides a SQLAlchemy engine for the MySQL database and populates it."""
    connection_string = f"mysql+pymysql://test_user:test_password@127.0.0.1:{mysql_service}/test_db"
    engine = sa.create_engine(connection_string)
    try:
        populate_db(engine)
        yield engine
    finally:
        engine.dispose()

# --- MariaDB Setup (Docker-based) ---
@pytest.fixture(scope="session")
def mariadb_service(_docker_service_factory):
    """Starts and stops the MariaDB Docker container."""

    def _connection_check(port):
        conn = pymysql.connect(
            host="127.0.0.1", port=port, user="test_user",
            password="test_password", database="test_db"
        )
        conn.close()

    return _docker_service_factory(
        container_name="mariadb_test_container",
        image="mariadb:latest",
        env_vars={
            "MARIADB_DATABASE": "test_db",
            "MARIADB_USER": "test_user",
            "MARIADB_PASSWORD": "test_password",
            "MARIADB_ROOT_PASSWORD": "root_password",
        },
        internal_port=3306,
        connection_check_fn=_connection_check
    )

@pytest.fixture(scope="function")
def mariadb_engine(mariadb_service):
    """Provides a SQLAlchemy engine for the MariaDB database and populates it."""
    connection_string = f"mysql+pymysql://test_user:test_password@127.0.0.1:{mariadb_service}/test_db"
    engine = sa.create_engine(connection_string)
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
        host_port = request.getfixturevalue("postgres_service")
        request.getfixturevalue("postgres_engine")
        connection_string = f"postgresql+psycopg2://test_user:test_password@127.0.0.1:{host_port}/test_db"
        config_dict = {
            "tool_name": "postgres_test_tool",
            "connection_string": connection_string,
        }
    elif db_type == "mysql":
        host_port = request.getfixturevalue("mysql_service")
        request.getfixturevalue("mysql_engine")
        connection_string = f"mysql+pymysql://test_user:test_password@127.0.0.1:{host_port}/test_db"
        config_dict = {
            "tool_name": "mysql_test_tool",
            "connection_string": connection_string,
        }
    elif db_type == "mariadb":
        host_port = request.getfixturevalue("mariadb_service")
        request.getfixturevalue("mariadb_engine")
        connection_string = f"mysql+pymysql://test_user:test_password@127.0.0.1:{host_port}/test_db"
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
        host_port = request.getfixturevalue("postgres_service")
        request.getfixturevalue("postgres_engine")
        connection_string = f"postgresql+psycopg2://test_user:test_password@127.0.0.1:{host_port}/test_db"
    elif db_type == "mysql":
        host_port = request.getfixturevalue("mysql_service")
        request.getfixturevalue("mysql_engine")
        connection_string = f"mysql+pymysql://test_user:test_password@127.0.0.1:{host_port}/test_db"
    elif db_type == "mariadb":
        host_port = request.getfixturevalue("mariadb_service")
        request.getfixturevalue("mariadb_engine")
        connection_string = f"mysql+pymysql://test_user:test_password@127.0.0.1:{host_port}/test_db"

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
