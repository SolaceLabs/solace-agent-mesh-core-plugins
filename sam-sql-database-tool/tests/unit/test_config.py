import pytest
from pydantic import ValidationError
from sam_sql_database_tool.tools import DatabaseConfig

class TestDatabaseConfig:
    """Unit tests for the DatabaseConfig model."""

    def test_valid_sqlite_config(self):
        """Test a valid SQLite configuration."""
        config = {
            "tool_name": "sqlite_test",
            "db_type": "sqlite",
            "db_name": "/path/to/db.sqlite",
        }
        assert DatabaseConfig(**config)

    def test_valid_postgresql_config(self):
        """Test a valid PostgreSQL configuration."""
        config = {
            "tool_name": "postgres_test",
            "db_type": "postgresql",
            "db_host": "localhost",
            "db_port": 5432,
            "db_user": "user",
            "db_password": "password",
            "db_name": "testdb",
        }
        assert DatabaseConfig(**config)

    def test_valid_mysql_config(self):
        """Test a valid MySQL configuration."""
        config = {
            "tool_name": "mysql_test",
            "db_type": "mysql",
            "db_host": "localhost",
            "db_port": 3306,
            "db_user": "user",
            "db_password": "password",
            "db_name": "testdb",
        }
        assert DatabaseConfig(**config)

    def test_invalid_postgresql_missing_fields(self):
        """Test that PostgreSQL config raises error if fields are missing."""
        with pytest.raises(ValidationError):
            DatabaseConfig(
                tool_name="postgres_test",
                db_type="postgresql",
                db_name="testdb",
                db_host="localhost" # Missing port, user, password
            )

    def test_invalid_mysql_missing_fields(self):
        """Test that MySQL config raises error if fields are missing."""
        with pytest.raises(ValidationError):
            DatabaseConfig(
                tool_name="mysql_test",
                db_type="mysql",
                db_name="testdb",
                db_host="localhost" # Missing port, user
            )

    def test_manual_schema_missing_overrides(self):
        """Test error when auto_detect_schema is false but overrides are missing."""
        with pytest.raises(ValidationError):
            DatabaseConfig(
                tool_name="sqlite_test",
                db_type="sqlite",
                db_name="/path/to/db.sqlite",
                auto_detect_schema=False
                # Missing database_schema_override and schema_summary_override
            )
