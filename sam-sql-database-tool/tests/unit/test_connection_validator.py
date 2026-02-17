"""Unit tests for connection string validation."""

import pytest
from pydantic import ValidationError
from sam_sql_database_tool.services.connection_validator import validate_connection_string
from sam_sql_database_tool.tools import DatabaseConfig


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
        with pytest.raises(ValueError) as exc_info:
            validate_connection_string("")
        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_only(self):
        """Whitespace-only string raises error."""
        with pytest.raises(ValueError) as exc_info:
            validate_connection_string("   ")
        assert "empty" in str(exc_info.value).lower()

class TestMissingComponents:
    """Tests for missing required components in connection strings."""

    def test_missing_host_empty(self):
        """Missing host (empty) raises error."""
        with pytest.raises(ValueError) as exc_info:
            validate_connection_string("postgresql://user:pass@:5432/mydb")
        assert "host" in str(exc_info.value).lower()

    def test_missing_host_completely(self):
        """Missing host completely raises error."""
        with pytest.raises(ValueError) as exc_info:
            validate_connection_string("postgresql:///mydb")
        assert "host" in str(exc_info.value).lower()

    def test_without_database_is_valid(self):
        """Connection string without database name is valid."""
        validate_connection_string("postgresql://user:pass@localhost:5432/")
        validate_connection_string("postgresql://user:pass@localhost:5432")
        validate_connection_string("postgresql://localhost")

    def test_only_dialect(self):
        """Only dialect provided raises error (missing host)."""
        with pytest.raises(ValueError) as exc_info:
            validate_connection_string("postgresql://")
        assert "host" in str(exc_info.value).lower()


class TestInvalidFormat:
    """Tests for invalid connection string formats."""

    def test_random_string(self):
        """Random string raises error."""
        with pytest.raises(ValueError) as exc_info:
            validate_connection_string("not-a-connection-string")
        assert "format" in str(exc_info.value).lower() or "host" in str(exc_info.value).lower()

    def test_http_url_passes_validation(self):
        """HTTP URL passes validation (has valid structure, dialect checked later by SQLAlchemy).

        Note: We only validate URL structure (host present, no unresolved env vars).
        """
        validate_connection_string("http://example.com")

    def test_malformed_url(self):
        """Malformed URL raises error."""
        with pytest.raises(ValueError):
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

    def test_empty_port_string(self):
        """Empty port string raises error with helpful message."""
        with pytest.raises(ValueError) as exc_info:
            validate_connection_string("postgresql://user:pass@localhost:/mydb")
        assert "invalid port number" in str(exc_info.value).lower()


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


class TestReadmeExamples:
    """Tests for connection string formats documented in README.md.

    These tests validate that the connection string formats shown in the
    README documentation are accepted by the validator.
    """

    def test_postgresql_psycopg2(self):
        """PostgreSQL format: postgresql+psycopg2://user:password@host:port/dbname"""
        validate_connection_string("postgresql+psycopg2://user:password@localhost:5432/dbname")

    def test_mysql_pymysql(self):
        """MySQL format: mysql+pymysql://user:password@host:port/dbname"""
        validate_connection_string("mysql+pymysql://user:password@localhost:3306/dbname")

    def test_mariadb_pymysql(self):
        """MariaDB format: mysql+pymysql://user:password@host:port/dbname"""
        validate_connection_string("mysql+pymysql://user:password@localhost:3306/dbname")

    def test_mssql_freetds(self):
        """MSSQL FreeTDS format with query params."""
        validate_connection_string(
            "mssql+pyodbc://user:password@localhost:1433/dbname?driver=FreeTDS&TrustServerCertificate=yes"
        )

    def test_mssql_microsoft_odbc(self):
        """MSSQL Microsoft ODBC format with query params."""
        validate_connection_string(
            "mssql+pyodbc://user:password@localhost:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
        )

    def test_oracle_oracledb_service_name(self):
        """Oracle format: oracle+oracledb://user:password@host:port/?service_name=NAME"""
        validate_connection_string("oracle+oracledb://user:password@localhost:1521/?service_name=XEPDB1")


class TestPydanticIntegration:
    """Tests for Pydantic model validation of connection strings."""

    def test_valid_config(self):
        """Valid DatabaseConfig with proper connection string."""
        config = DatabaseConfig(
            tool_name="test_tool",
            connection_string="postgresql://user:pass@localhost:5432/mydb"
        )
        assert config.tool_name == "test_tool"

    def test_invalid_connection_string_raises_validation_error(self):
        """Invalid connection string raises Pydantic ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DatabaseConfig(
                tool_name="test_tool",
                connection_string="bad-connection-string"
            )
        assert "connection_string" in str(exc_info.value)

    def test_empty_connection_string_raises_validation_error(self):
        """Empty connection string raises Pydantic ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DatabaseConfig(
                tool_name="test_tool",
                connection_string=""
            )
        assert "connection_string" in str(exc_info.value)

    def test_missing_host_raises_validation_error(self):
        """Connection string missing host raises Pydantic ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DatabaseConfig(
                tool_name="test_tool",
                connection_string="postgresql://"
            )
        assert "connection_string" in str(exc_info.value)

