import pytest
from unittest.mock import MagicMock, patch
from solace_agent_mesh.agent.tools.tool_result import (
    DataDisposition,
    ToolResult,
)
from sam_sql_database_tool.tools import (
    INLINE_PREVIEW_ROWS,
    DatabaseConfig,
    SqlDatabaseTool,
)

@pytest.fixture
def basic_config():
    """A fixture for a basic DatabaseConfig."""
    return DatabaseConfig(
        tool_name="test_tool",
        tool_description="A test description.",
        connection_string="postgresql://user:pass@host/db"
    )


def _make_initialized_tool(basic_config, mock_db_service_class):
    mock_service = MagicMock()
    mock_db_service_class.return_value = mock_service
    mock_service.get_optimized_schema_for_llm.return_value = "schema"
    tool = SqlDatabaseTool(basic_config)
    return tool, mock_service


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
        assert isinstance(result, ToolResult)
        assert result.status == "error"
        assert "not available" in result.message
        assert "test_tool" in result.message

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
            tool, mock_service = _make_initialized_tool(basic_config, mock_db_service_class)
            await tool.init(component=None, tool_config={})

            assert tool._connection_healthy is True

            mock_service.execute_query.side_effect = Exception("Connection lost")
            result1 = await tool._run_async_impl(args={"query": "SELECT 1"})
            assert isinstance(result1, ToolResult)
            assert result1.status == "error"
            assert tool._connection_healthy is False
            assert "Connection lost" in tool._connection_error

            mock_service.execute_query.side_effect = None
            mock_service.execute_query.return_value = [{"result": 1}]
            result2 = await tool._run_async_impl(args={"query": "SELECT 1"})
            assert isinstance(result2, ToolResult)
            assert result2.status == "success"
            assert tool._connection_healthy is True
            assert tool._connection_error is None

    async def test_multiple_failures_stay_degraded(self, basic_config):
        """Test that multiple failures keep the tool degraded until recovery."""
        with patch('sam_sql_database_tool.tools.DatabaseService') as mock_db_service_class:
            tool, mock_service = _make_initialized_tool(basic_config, mock_db_service_class)
            await tool.init(component=None, tool_config={})

            assert tool._connection_healthy is True

            mock_service.execute_query.side_effect = Exception("Connection error")

            for q in ("SELECT 1", "SELECT 2", "SELECT 3"):
                result = await tool._run_async_impl(args={"query": q})
                assert isinstance(result, ToolResult)
                assert result.status == "error"
                assert tool._connection_healthy is False

    async def test_row_result_produces_csv_artifact_and_summary(self, basic_config):
        """A row-returning query emits a ToolResult with CSV DataObject and summary."""
        with patch('sam_sql_database_tool.tools.DatabaseService') as mock_db_service_class:
            tool, mock_service = _make_initialized_tool(basic_config, mock_db_service_class)
            await tool.init(component=None, tool_config={})

            rows = [{"id": i, "name": f"user{i}"} for i in range(1, 11)]
            mock_service.execute_query.return_value = rows

            result = await tool._run_async_impl(args={"query": "SELECT id, name FROM users"})

            assert isinstance(result, ToolResult)
            assert result.status == "success"
            assert result.data["row_count"] == 10
            assert result.data["columns"] == ["id", "name"]
            assert result.data["preview_rows"] == rows[:INLINE_PREVIEW_ROWS]
            assert len(result.data["preview_rows"]) == INLINE_PREVIEW_ROWS

            assert len(result.data_objects) == 1
            obj = result.data_objects[0]
            assert obj.mime_type == "text/csv"
            assert obj.disposition == DataDisposition.AUTO.value
            assert obj.name == "test_tool_query_result.csv"
            assert obj.content.splitlines()[0] == "id,name"
            assert len(obj.content.splitlines()) == 11  # header + 10 rows

    async def test_empty_result_has_no_artifact(self, basic_config):
        """An empty result set returns an empty summary with no data_objects."""
        with patch('sam_sql_database_tool.tools.DatabaseService') as mock_db_service_class:
            tool, mock_service = _make_initialized_tool(basic_config, mock_db_service_class)
            await tool.init(component=None, tool_config={})

            mock_service.execute_query.return_value = []

            result = await tool._run_async_impl(args={"query": "SELECT * FROM users WHERE 1=0"})

            assert isinstance(result, ToolResult)
            assert result.status == "success"
            assert result.data == {"row_count": 0, "columns": [], "preview_rows": []}
            assert result.data_objects == []

    async def test_non_row_result_returns_status_dict(self, basic_config):
        """INSERT/UPDATE-style results stay inline with no artifact."""
        with patch('sam_sql_database_tool.tools.DatabaseService') as mock_db_service_class:
            tool, mock_service = _make_initialized_tool(basic_config, mock_db_service_class)
            await tool.init(component=None, tool_config={})

            mock_service.execute_query.return_value = [
                {"status": "success", "affected_rows": 3}
            ]

            result = await tool._run_async_impl(args={"query": "UPDATE users SET active=1"})

            assert isinstance(result, ToolResult)
            assert result.status == "success"
            assert result.data == {"status": "success", "affected_rows": 3}
            assert result.data_objects == []
            assert "Affected rows: 3" in result.message
