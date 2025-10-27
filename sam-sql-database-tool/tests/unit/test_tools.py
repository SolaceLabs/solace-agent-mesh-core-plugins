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

        assert "A test description." in tool.tool_description
        assert "❌ WARNING: This database is currently UNAVAILABLE" in tool.tool_description

        tool._connection_healthy = True
        tool._schema_context = "TABLE users(id INT)"
        assert "A test description." in tool.tool_description
        assert "✅ Database Connected" in tool.tool_description
        assert "Database Schema:" in tool.tool_description
        assert "TABLE users(id INT)" in tool.tool_description

    async def test_init_db_service_failure(self, basic_config):
        """Test that init degrades gracefully if DatabaseService fails."""
        with patch('sam_sql_database_tool.tools.DatabaseService', side_effect=ValueError("Connection Failed")):
            tool = SqlDatabaseTool(basic_config)
            await tool.init(component=None, tool_config={})

            assert tool._connection_healthy is False
            assert "Connection Failed" in tool._connection_error
            assert tool.db_service is None

    async def test_run_without_initialized_service(self, basic_config):
        """Test that run returns an error if the db_service is not available."""
        tool = SqlDatabaseTool(basic_config)
        result = await tool._run_async_impl(args={"query": "SELECT 1"})
        assert "error" in result
        assert "not available" in result["error"]
        assert "test_tool" in result["error"]

    async def test_init_schema_detection_failure(self, basic_config):
        """Test that init degrades gracefully if schema detection fails."""
        with patch('sam_sql_database_tool.tools.DatabaseService') as mock_db_service_class:
            mock_service_instance = MagicMock()
            mock_service_instance.get_optimized_schema_for_llm.side_effect = RuntimeError("Schema Read Failed")
            mock_db_service_class.return_value = mock_service_instance

            tool = SqlDatabaseTool(basic_config)
            await tool.init(component=None, tool_config={})

            assert tool._connection_healthy is False
            assert "Schema Read Failed" in tool._connection_error
            assert tool.db_service is not None

    async def test_connection_recovery_after_failure(self, basic_config):
        """Test that the tool recovers when database comes back online."""
        with patch('sam_sql_database_tool.tools.DatabaseService') as mock_db_service_class:
            mock_service = MagicMock()
            mock_db_service_class.return_value = mock_service

            mock_service.get_optimized_schema_for_llm.return_value = "schema"

            tool = SqlDatabaseTool(basic_config)
            await tool.init(component=None, tool_config={})

            assert tool._connection_healthy is True

            mock_service.execute_query.side_effect = Exception("Connection lost")
            result1 = await tool._run_async_impl(args={"query": "SELECT 1"})
            assert "error" in result1
            assert tool._connection_healthy is False
            assert "Connection lost" in tool._connection_error

            mock_service.execute_query.side_effect = None
            mock_service.execute_query.return_value = [{"result": 1}]
            result2 = await tool._run_async_impl(args={"query": "SELECT 1"})
            assert "result" in result2
            assert tool._connection_healthy is True
            assert tool._connection_error is None

    async def test_multiple_failures_stay_degraded(self, basic_config):
        """Test that multiple failures keep the tool degraded until recovery."""
        with patch('sam_sql_database_tool.tools.DatabaseService') as mock_db_service_class:
            mock_service = MagicMock()
            mock_db_service_class.return_value = mock_service
            mock_service.get_optimized_schema_for_llm.return_value = "schema"

            tool = SqlDatabaseTool(basic_config)
            await tool.init(component=None, tool_config={})

            assert tool._connection_healthy is True

            mock_service.execute_query.side_effect = Exception("Connection error")

            result1 = await tool._run_async_impl(args={"query": "SELECT 1"})
            assert "error" in result1
            assert tool._connection_healthy is False

            result2 = await tool._run_async_impl(args={"query": "SELECT 2"})
            assert "error" in result2
            assert tool._connection_healthy is False

            result3 = await tool._run_async_impl(args={"query": "SELECT 3"})
            assert "error" in result3
            assert tool._connection_healthy is False
