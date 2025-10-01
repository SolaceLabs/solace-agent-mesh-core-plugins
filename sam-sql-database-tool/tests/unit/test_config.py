import pytest
from pydantic import ValidationError
from sam_sql_database_tool.tools import DatabaseConfig

class TestDatabaseConfig:
    """Unit tests for the DatabaseConfig model."""

    def test_valid_sqlite_config(self):
        """Test a valid SQLite configuration."""
        config = {
            "tool_name": "sqlite_test",
            "connection_string": "sqlite:///:memory:",
        }
        assert DatabaseConfig(**config)

    def test_valid_postgresql_config(self):
        """Test a valid PostgreSQL configuration."""
        config = {
            "tool_name": "postgres_test",
            "connection_string": "postgresql+psycopg2://user:password@localhost:5432/testdb",
        }
        assert DatabaseConfig(**config)

    def test_valid_mysql_config(self):
        """Test a valid MySQL configuration."""
        config = {
            "tool_name": "mysql_test",
            "connection_string": "mysql+pymysql://user:password@localhost:3306/testdb",
        }
        assert DatabaseConfig(**config)

    def test_invalid_missing_connection_string(self):
        """Test that config raises error if connection_string is missing."""
        with pytest.raises(ValidationError):
            DatabaseConfig(
                tool_name="test",
            )

    def test_manual_schema_missing_overrides(self):
        """Test error when auto_detect_schema is false but overrides are missing."""
        with pytest.raises(ValidationError):
            DatabaseConfig(
                tool_name="sqlite_test",
                connection_string="sqlite:///:memory:",
                auto_detect_schema=False
                # Missing database_schema_override and schema_summary_override
            )
