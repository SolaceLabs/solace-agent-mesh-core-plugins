"""Unit tests for connection string validation."""

import pytest
from sam_sql_database_tool.services.connection_validator import (
    ConnectionStringError,
    validate_connection_string,
)


class TestValidConnectionStrings:
    """Tests for valid connection strings across all supported databases."""

    def test_postgresql_valid(self):
        """PostgreSQL with psycopg2 driver."""
        validate_connection_string("postgresql+psycopg2://user:pass@localhost:5432/mydb")

    def test_postgresql_without_driver(self):
        """PostgreSQL without explicit driver."""
        validate_connection_string("postgresql://user:pass@localhost:5432/mydb")

    def test_mysql_valid(self):
        """MySQL with pymysql driver."""
        validate_connection_string("mysql+pymysql://user:pass@localhost:3306/mydb")

    def test_mysql_without_driver(self):
        """MySQL without explicit driver."""
        validate_connection_string("mysql://user:pass@localhost:3306/mydb")

    def test_mariadb_valid(self):
        """MariaDB with pymysql driver."""
        validate_connection_string("mariadb+pymysql://user:pass@localhost:3306/mydb")

    def test_mariadb_mariadbconnector(self):
        """MariaDB with mariadbconnector driver."""
        validate_connection_string("mariadb+mariadbconnector://user:pass@localhost:3306/mydb")

    def test_mssql_valid(self):
        """MSSQL with pyodbc driver."""
        validate_connection_string("mssql+pyodbc://user:pass@localhost:1433/mydb")

    def test_mssql_pymssql(self):
        """MSSQL with pymssql driver."""
        validate_connection_string("mssql+pymssql://user:pass@localhost:1433/mydb")

    def test_oracle_valid(self):
        """Oracle with oracledb driver."""
        validate_connection_string("oracle+oracledb://user:pass@localhost:1521/mydb")

    def test_oracle_cx_oracle(self):
        """Oracle with cx_oracle driver."""
        validate_connection_string("oracle+cx_oracle://user:pass@localhost:1521/mydb")

    def test_without_port(self):
        """Connection string without explicit port."""
        validate_connection_string("postgresql://user:pass@localhost/mydb")

    def test_with_special_chars_in_password(self):
        """Password with URL-encoded special characters."""
        validate_connection_string("postgresql://user:p%40ss%23word@localhost:5432/mydb")

    def test_with_empty_password(self):
        """Empty password (some DBs allow this)."""
        validate_connection_string("postgresql://user:@localhost:5432/mydb")

    def test_with_ipv4_host(self):
        """IPv4 address as host."""
        validate_connection_string("postgresql://user:pass@192.168.1.100:5432/mydb")


class TestEmptyConnectionStrings:
    """Tests for empty or whitespace connection strings."""

    def test_empty_string(self):
        """Empty string raises error."""
        with pytest.raises(ConnectionStringError) as exc_info:
            validate_connection_string("")
        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_only(self):
        """Whitespace-only string raises error."""
        with pytest.raises(ConnectionStringError) as exc_info:
            validate_connection_string("   ")
        assert "empty" in str(exc_info.value).lower()

    def test_none_raises_error(self):
        """None value raises error."""
        with pytest.raises(ConnectionStringError):
            validate_connection_string(None)


class TestUnresolvedEnvironmentVariables:
    """Tests for unresolved environment variable detection."""

    def test_bash_style_env_var(self):
        """Detects ${VAR} style env vars."""
        with pytest.raises(ConnectionStringError) as exc_info:
            validate_connection_string("postgresql://user:pass@${DB_HOST}:5432/mydb")
        assert "DB_HOST" in str(exc_info.value)
        assert "environment variable" in str(exc_info.value).lower()

    def test_simple_env_var(self):
        """Detects $VAR style env vars."""
        with pytest.raises(ConnectionStringError) as exc_info:
            validate_connection_string("postgresql://user:pass@$DB_HOST:5432/mydb")
        assert "DB_HOST" in str(exc_info.value)

    def test_multiple_env_vars(self):
        """Detects multiple unresolved env vars."""
        with pytest.raises(ConnectionStringError) as exc_info:
            validate_connection_string("postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:5432/mydb")
        error_msg = str(exc_info.value)
        assert "DB_USER" in error_msg
        assert "DB_PASS" in error_msg
        assert "DB_HOST" in error_msg

    def test_entire_string_is_env_var(self):
        """Entire connection string is an unresolved env var."""
        with pytest.raises(ConnectionStringError) as exc_info:
            validate_connection_string("${DATABASE_URL}")
        assert "DATABASE_URL" in str(exc_info.value)

    def test_empty_env_var_braces(self):
        """Empty braces ${} are detected."""
        with pytest.raises(ConnectionStringError) as exc_info:
            validate_connection_string("postgresql://user:pass@${}:5432/mydb")
        assert "environment variable" in str(exc_info.value).lower()


class TestMissingComponents:
    """Tests for missing required components in connection strings."""

    def test_missing_host_empty(self):
        """Missing host (empty) raises error."""
        with pytest.raises(ConnectionStringError) as exc_info:
            validate_connection_string("postgresql://user:pass@:5432/mydb")
        assert "host" in str(exc_info.value).lower()

    def test_missing_host_completely(self):
        """Missing host completely raises error."""
        with pytest.raises(ConnectionStringError) as exc_info:
            validate_connection_string("postgresql:///mydb")
        assert "host" in str(exc_info.value).lower()

    def test_empty_credentials_no_host(self):
        """Empty credentials with no host raises error."""
        with pytest.raises(ConnectionStringError) as exc_info:
            validate_connection_string("postgresql://:@")
        assert "host" in str(exc_info.value).lower()

    def test_without_database_is_valid(self):
        """Connection string without database name is valid."""
        validate_connection_string("postgresql://user:pass@localhost:5432/")
        validate_connection_string("postgresql://user:pass@localhost:5432")
        validate_connection_string("postgresql://localhost")

    def test_only_dialect(self):
        """Only dialect provided raises error (missing host)."""
        with pytest.raises(ConnectionStringError) as exc_info:
            validate_connection_string("postgresql://")
        assert "host" in str(exc_info.value).lower()


class TestInvalidFormat:
    """Tests for invalid connection string formats."""

    def test_random_string(self):
        """Random string raises error."""
        with pytest.raises(ConnectionStringError) as exc_info:
            validate_connection_string("not-a-connection-string")
        assert "format" in str(exc_info.value).lower() or "host" in str(exc_info.value).lower()

    def test_http_url_passes_validation(self):
        """HTTP URL passes validation (has valid structure, dialect checked later by SQLAlchemy).

        Note: We only validate URL structure (host present, no unresolved env vars).
        """
        validate_connection_string("http://example.com")

    def test_malformed_url(self):
        """Malformed URL raises error."""
        with pytest.raises(ConnectionStringError):
            validate_connection_string("postgresql:user:pass@localhost/db")


class TestPortValidation:
    """Tests for port validation."""

    def test_valid_port(self):
        """Valid port number passes."""
        validate_connection_string("postgresql://user:pass@localhost:5432/mydb")

    def test_port_1(self):
        """Port 1 is valid."""
        validate_connection_string("postgresql://user:pass@localhost:1/mydb")

    def test_port_65535(self):
        """Port 65535 is valid."""
        validate_connection_string("postgresql://user:pass@localhost:65535/mydb")


class TestDatabaseSpecificFormats:
    """Tests for database-specific connection string formats."""

    def test_postgresql_with_schema(self):
        """PostgreSQL with options."""
        validate_connection_string("postgresql://user:pass@localhost:5432/mydb?options=-csearch_path=myschema")

    def test_mysql_with_charset(self):
        """MySQL with charset option."""
        validate_connection_string("mysql+pymysql://user:pass@localhost:3306/mydb?charset=utf8mb4")

    def test_mssql_with_driver_option(self):
        """MSSQL with driver in query string."""
        validate_connection_string("mssql+pyodbc://user:pass@localhost:1433/mydb?driver=ODBC+Driver+17+for+SQL+Server")

    def test_oracle_with_service_name(self):
        """Oracle connection string format."""
        validate_connection_string("oracle+oracledb://user:pass@localhost:1521/mydb")