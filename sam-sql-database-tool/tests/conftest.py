import pytest
from pathlib import Path
import testing.postgresql
import psycopg2
import pymysql
import sqlite3
import subprocess
import time

from sam_sql_database_tool.tools import DatabaseConfig, SqlDatabaseTool

def populate_db(conn):
    """Generic function to create tables and insert data."""
    cursor = conn.cursor()
    
    # Drop tables if they exist for a clean slate, especially for mysql_db fixture
    cursor.execute("DROP TABLE IF EXISTS users;")
    cursor.execute("DROP TABLE IF EXISTS products;")

    # Create tables
    cursor.execute("CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(50));")
    cursor.execute("CREATE TABLE products (sku VARCHAR(20) PRIMARY KEY, name VARCHAR(100), price FLOAT);")
    
    users_data = [
        (1, 'Alice'), (2, 'Bob'), (3, 'Charlie'), (4, 'David'), (5, 'Eve')
    ]
    products_data = [
        ('SKU001', 'Laptop', 1200.50),
        ('SKU002', 'Mouse', 25.00),
        ('SKU003', 'Keyboard', 75.99),
        ('SKU004', 'Monitor', 300.00),
        ('SKU005', 'Webcam', 50.25)
    ]
    
    # Determine placeholder style based on the DB driver
    placeholder = "%s" if isinstance(conn, (pymysql.connections.Connection, psycopg2.extensions.connection)) else "?"
    
    user_sql = f"INSERT INTO users (id, name) VALUES ({placeholder}, {placeholder});"
    product_sql = f"INSERT INTO products (sku, name, price) VALUES ({placeholder}, {placeholder}, {placeholder});"

    cursor.executemany(user_sql, users_data)
    cursor.executemany(product_sql, products_data)
    
    conn.commit()
    cursor.close()

# --- PostgreSQL Setup ---
def postgres_init_handler(postgresql):
    """Create tables and insert data for PostgreSQL tests."""
    conn = psycopg2.connect(**postgresql.dsn())
    populate_db(conn)
    conn.close()

PostgresqlFactory = testing.postgresql.PostgresqlFactory(
    cache_initialized_db=True,
    on_initialized=postgres_init_handler
)

@pytest.fixture(scope="function")
def local_postgres_db():
    with PostgresqlFactory() as postgresql:
        yield postgresql

# --- MySQL Setup (Docker-based) ---
@pytest.fixture(scope="session")
def mysql_service(request):
    """Starts and stops the MySQL Docker container using a dynamic port."""
    container_name = "mysql_test_container"
    
    # Ensure the container is stopped and removed before starting
    subprocess.run(["docker", "stop", container_name], check=False, capture_output=True)
    subprocess.run(["docker", "rm", container_name], check=False, capture_output=True)
    
    # Start the container, publishing to a random host port
    run_command = [
        "docker", "run", "--name", container_name, "-d",
        "-e", "MYSQL_DATABASE=test_db",
        "-e", "MYSQL_USER=test_user",
        "-e", "MYSQL_PASSWORD=test_password",
        "-e", "MYSQL_ROOT_PASSWORD=root_password",
        "-P",  # Use -P to publish all exposed ports to random host ports
        "mysql:8.0"
    ]
    subprocess.run(run_command, check=True)

    # Get the dynamically assigned host port
    port_proc = subprocess.run(
        ["docker", "port", container_name, "3306/tcp"],
        check=True, capture_output=True, text=True
    )
    host_port = int(port_proc.stdout.strip().split(":")[-1])
    
    # Wait for the database to be ready
    retries = 15
    while retries > 0:
        try:
            conn = pymysql.connect(
                host="127.0.0.1", port=host_port, user="test_user",
                password="test_password", database="test_db"
            )
            conn.close()
            break
        except pymysql.err.OperationalError:
            retries -= 1
            time.sleep(3)
    
    if retries == 0:
        pytest.fail("Could not connect to MySQL container.")

    def finalizer():
        subprocess.run(["docker", "stop", container_name], check=True, capture_output=True)
        subprocess.run(["docker", "rm", container_name], check=True, capture_output=True)
    
    request.addfinalizer(finalizer)
    return host_port

@pytest.fixture(scope="function")
def mysql_db(mysql_service):
    """Provides a connection to the Dockerized MySQL database and creates tables."""
    host_port = mysql_service
    conn = pymysql.connect(
        host="127.0.0.1",
        port=host_port,
        user="test_user",
        password="test_password",
        database="test_db"
    )
    populate_db(conn)
    yield conn
    conn.close()

# --- Generic Tool Provider ---
@pytest.fixture(
    scope="function",
    params=["postgresql", "mysql", "sqlite"]
)
async def db_tool_provider(request, tmp_path: Path):
    """Yields an initialized SqlDatabaseTool for each database provider."""
    db_type = request.param
    config_dict = None

    if db_type == "postgresql":
        local_postgres_db = request.getfixturevalue("local_postgres_db")
        dsn = local_postgres_db.dsn()
        config_dict = {
            "tool_name": "postgres_test_tool",
            "db_type": "postgresql",
            "db_host": dsn.get("host"),
            "db_port": dsn.get("port"),
            "db_user": dsn.get("user"),
            "db_password": "test",
            "db_name": dsn.get("database", "test")
        }
    elif db_type == "mysql":
        host_port = request.getfixturevalue("mysql_service")
        request.getfixturevalue("mysql_db")
        config_dict = {
            "tool_name": "mysql_test_tool",
            "db_type": "mysql",
            "db_host": "127.0.0.1",
            "db_port": host_port,
            "db_user": "test_user",
            "db_password": "test_password",
            "db_name": "test_db",
        }
    elif db_type == "sqlite":
        sqlite_db_path = tmp_path / "test.db"
        conn = sqlite3.connect(sqlite_db_path)
        populate_db(conn)
        conn.close()
        config_dict = {
            "tool_name": "sqlite_test_tool",
            "db_type": "sqlite",
            "db_name": str(sqlite_db_path),
        }
    
    tool_config = DatabaseConfig(**config_dict)
    tool = SqlDatabaseTool(tool_config)
    await tool.init(component=None, tool_config={})
    
    yield tool
    
    await tool.cleanup(component=None, tool_config={})
