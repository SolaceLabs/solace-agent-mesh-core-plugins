import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sam_sql_database_tool.tools import SqlDatabaseTool, DatabaseConfig

@pytest.fixture
def basic_config():
    """A fixture for a basic DatabaseConfig."""
    return DatabaseConfig(
        tool_name="test_tool",
        tool_description="A test description.",
        connection_string="postgresql://user:pass@host/db"
    )

@pytest.mark.asyncio
class TestSqlDatabaseToolUnit:
    """Unit tests for the SqlDatabaseTool class."""

    def test_tool_properties(self, basic_config):
        """Test that the tool's properties return correct values."""
        tool = SqlDatabaseTool(basic_config)
        assert tool.tool_name == "test_tool"
        assert tool.tool_description == "A test description."

        # Test description with schema context
        tool._schema_context = "TABLE users(id INT)"
        assert "A test description." in tool.tool_description
        assert "Database Schema:" in tool.tool_description
        assert "TABLE users(id INT)" in tool.tool_description

    async def test_init_db_service_failure(self, basic_config):
        """Test that init raises an error if DatabaseService fails."""
        with patch('sam_sql_database_tool.tools.DatabaseService', side_effect=ValueError("Connection Failed")):
            tool = SqlDatabaseTool(basic_config)
            with pytest.raises(ValueError, match="Invalid connection string or unsupported database dialect."):
                await tool.init(component=None, tool_config={})

    async def test_run_without_initialized_service(self, basic_config):
        """Test that run returns an error if the db_service is not available."""
        tool = SqlDatabaseTool(basic_config)
        # Note: We are NOT calling tool.init() here
        result = await tool._run_async_impl(args={"query": "SELECT 1"})
        assert "error" in result
        assert "is not available" in result["error"]

    async def test_init_schema_detection_failure(self, basic_config):
        """Test that init raises an error if schema detection fails."""
        with patch('sam_sql_database_tool.tools.DatabaseService') as mock_db_service_class:
            mock_service_instance = MagicMock()
            mock_service_instance.get_optimized_schema_for_llm.side_effect = RuntimeError("Schema Read Failed")
            mock_db_service_class.return_value = mock_service_instance
            
            tool = SqlDatabaseTool(basic_config)
            with pytest.raises(RuntimeError, match="Schema Read Failed"):
                await tool.init(component=None, tool_config={})
