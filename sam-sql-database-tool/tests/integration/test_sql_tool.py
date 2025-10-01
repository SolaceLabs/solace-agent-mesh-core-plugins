import pytest
from sam_sql_database_tool.tools import SqlDatabaseTool

@pytest.mark.asyncio
class TestSqlDatabaseTool:
    """End-to-end tests for the SqlDatabaseTool across all supported providers."""

    async def test_select_data(self, db_tool_provider: SqlDatabaseTool):
        """Test selecting data from a table."""
        select_query = "SELECT * FROM users WHERE id = 1;"
        select_result = await db_tool_provider._run_async_impl(args={"query": select_query})
        
        assert "error" not in select_result, f"Failed to select data: {select_result.get('error')}"
        result_data = select_result.get("result")
        assert len(result_data) == 1
        assert result_data[0]['name'] == 'Alice'

    async def test_schema_detection(self, db_tool_provider: SqlDatabaseTool):
        """Test the automatic schema detection."""
        summary = db_tool_provider.db_service.get_schema_summary_for_llm()
        
        assert "products" in summary
        assert "sku" in summary
        assert "price" in summary

    async def test_select_with_aggregation(self, db_tool_provider: SqlDatabaseTool):
        """Test a SELECT query with an aggregation function."""
        query = "SELECT COUNT(*) as user_count FROM users;"
        result = await db_tool_provider._run_async_impl(args={"query": query})
        assert "error" not in result
        # The exact key for the count may vary, so we check the first value.
        assert list(result.get("result")[0].values())[0] == 5

    async def test_select_with_order_by(self, db_tool_provider: SqlDatabaseTool):
        """Test a SELECT query with an ORDER BY clause."""
        query = "SELECT name FROM users ORDER BY name DESC;"
        result = await db_tool_provider._run_async_impl(args={"query": query})
        assert "error" not in result
        names = [row['name'] for row in result.get("result")]
        assert names == ['Eve', 'David', 'Charlie', 'Bob', 'Alice']

    async def test_invalid_select_query(self, db_tool_provider: SqlDatabaseTool):
        """Test that an invalid SELECT query returns an error."""
        invalid_query = "SELECT * FROM non_existent_table;"
        result = await db_tool_provider._run_async_impl(args={"query": invalid_query})
        assert "error" in result
        
    async def test_detailed_schema_representation(self, db_tool_provider: SqlDatabaseTool):
        """Test the detailed schema representation (read-only)."""
        schema = db_tool_provider.db_service.get_detailed_schema_representation()
        
        assert "users" in schema
        assert "products" in schema
        
        assert "id" in schema["users"]["columns"]
        assert "name" in schema["users"]["columns"]
        assert schema["users"]["primary_keys"] == ["id"]
        
        assert "sku" in schema["products"]["columns"]
        assert "price" in schema["products"]["columns"]
        assert schema["products"]["primary_keys"] == ["sku"]
