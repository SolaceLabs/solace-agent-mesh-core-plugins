import pytest
from pydantic import ValidationError
from sam_sql_database_tool.tools import DatabaseConfig

class TestDatabaseConfig:
    """Unit tests for the DatabaseConfig model."""

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
                tool_name="postgres_test",
                connection_string="postgresql+psycopg2://user:password@localhost:5432/testdb",
                auto_detect_schema=False
            )

    def test_manual_schema_with_override(self):
        """Test valid config when auto_detect_schema is false with override provided."""
        config = DatabaseConfig(
            tool_name="postgres_test",
            connection_string="postgresql+psycopg2://user:password@localhost:5432/testdb",
            auto_detect_schema=False,
            schema_summary_override="users:\n  columns:\n    id: INTEGER\n    name: VARCHAR"
        )
        assert config.auto_detect_schema is False
        assert config.schema_summary_override is not None

    def test_include_tables(self):
        """Test config accepts include_tables as list of strings."""
        config = DatabaseConfig(
            tool_name="test",
            connection_string="postgresql+psycopg2://user:password@localhost:5432/testdb",
            include_tables=["tms_trx*", "tms_alert*"],
        )
        assert config.include_tables == ["tms_trx*", "tms_alert*"]

    def test_exclude_tables(self):
        """Test config accepts exclude_tables as list of strings."""
        config = DatabaseConfig(
            tool_name="test",
            connection_string="postgresql+psycopg2://user:password@localhost:5432/testdb",
            exclude_tables=["bkp_*", "*_temp"],
        )
        assert config.exclude_tables == ["bkp_*", "*_temp"]

    def test_include_and_exclude_tables_together(self):
        """Test config accepts both include_tables and exclude_tables."""
        config = DatabaseConfig(
            tool_name="test",
            connection_string="postgresql+psycopg2://user:password@localhost:5432/testdb",
            include_tables=["tms_trx*"],
            exclude_tables=["*_temp"],
        )
        assert config.include_tables == ["tms_trx*"]
        assert config.exclude_tables == ["*_temp"]

    def test_table_filters_ignored_when_auto_detect_false(self):
        """Test that a warning is logged when filters are set with auto_detect_schema=false."""
        import logging
        from unittest.mock import patch
        logger = logging.getLogger("sam_sql_database_tool.tools")
        with patch.object(logger, "warning") as mock_warning:
            DatabaseConfig(
                tool_name="test",
                connection_string="postgresql+psycopg2://user:password@localhost:5432/testdb",
                auto_detect_schema=False,
                schema_summary_override="manual schema",
                include_tables=["tms_trx*"],
            )
            mock_warning.assert_called_once()
            assert "include_tables/exclude_tables have no effect" in mock_warning.call_args[0][0]

    def test_table_filters_default_to_none(self):
        """Test that include_tables and exclude_tables default to None."""
        config = DatabaseConfig(
            tool_name="test",
            connection_string="postgresql+psycopg2://user:password@localhost:5432/testdb",
        )
        assert config.include_tables is None
        assert config.exclude_tables is None
