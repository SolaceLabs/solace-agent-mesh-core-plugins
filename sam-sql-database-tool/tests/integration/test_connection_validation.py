"""Integration tests for connection string validation."""

import pytest
from pydantic import ValidationError, SecretStr
from sam_sql_database_tool.tools import DatabaseConfig


class TestConnectionValidationIntegration:
    """Integration tests for connection string validation via DatabaseConfig."""

    def test_valid_connection_string_with_secretstr(self, db_tool_provider):
        """Valid SecretStr connection string passes validation in DatabaseConfig."""
        tool_config_dict = db_tool_provider.tool_config.model_dump()
        conn_str = tool_config_dict['connection_string'].get_secret_value()

        config = DatabaseConfig(
            tool_name="test_tool",
            connection_string=SecretStr(conn_str)
        )
        assert config.tool_name == "test_tool"

    def test_invalid_connection_string_rejected(self):
        """Invalid connection string is rejected at config creation."""
        with pytest.raises(ValidationError) as exc_info:
            DatabaseConfig(
                tool_name="test_tool",
                connection_string="not-a-valid-connection-string"
            )
        assert "connection_string" in str(exc_info.value)
