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
        summary = db_tool_provider.db_service.get_optimized_schema_for_llm()

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
        
    async def test_schema_caching(self, db_tool_provider: SqlDatabaseTool):
        """Test that schema is cached in memory."""
        assert db_tool_provider._schema_context is not None
        assert len(db_tool_provider._schema_context) > 0

        assert "users" in db_tool_provider._schema_context
        assert "products" in db_tool_provider._schema_context

    async def test_cache_hit_performance(self, db_tool_provider: SqlDatabaseTool):
        """Test that cache provides instant schema retrieval."""
        import time

        first_call_start = time.time()
        schema1 = db_tool_provider.db_service.get_optimized_schema_for_llm()
        first_call_time = time.time() - first_call_start

        second_call_start = time.time()
        schema2 = db_tool_provider.db_service.get_optimized_schema_for_llm()
        second_call_time = time.time() - second_call_start

        assert schema1 == schema2
        assert second_call_time < 0.01

    async def test_cache_ttl_configuration(self, db_tool_provider: SqlDatabaseTool):
        """Test that cache TTL is configurable."""
        assert db_tool_provider.db_service._cache_ttl.total_seconds() == 3600

    async def test_parallel_processing(self, db_tool_provider: SqlDatabaseTool):
        """Test that parallel processing detects all tables and columns."""
        schema = db_tool_provider.db_service.get_optimized_schema_for_llm()

        assert "users" in schema
        assert "products" in schema
        assert "id" in schema
        assert "name" in schema
        assert "sku" in schema
        assert "price" in schema

    @pytest.mark.parametrize("query", [
        "INSERT INTO users (id, name) VALUES (10, 'test');",
        "UPDATE users SET name = 'test' WHERE id = 1;",
        "DELETE FROM users WHERE id = 1;",
    ])
    async def test_dml_queries_execute_successfully(self, db_tool_provider: SqlDatabaseTool, query: str):
        """Test that DML queries (INSERT, UPDATE, DELETE) execute and report affected rows."""
        result = await db_tool_provider._run_async_impl(args={"query": query})
        assert "error" not in result
        assert "result" in result
        assert "affected_rows" in result["result"][0]
        assert result["result"][0]["affected_rows"] >= 0

    async def test_manual_schema_override(self, db_tool_provider_manual_schema: SqlDatabaseTool):
        """Test that a manual schema override is correctly applied."""
        description = db_tool_provider_manual_schema.tool_description
        assert "MANUAL_SCHEMA_TEST" in description
        
        # Also ensure it can still run queries
        select_query = "SELECT * FROM users WHERE id = 1;"
        select_result = await db_tool_provider_manual_schema._run_async_impl(args={"query": select_query})
        assert "error" not in select_result
