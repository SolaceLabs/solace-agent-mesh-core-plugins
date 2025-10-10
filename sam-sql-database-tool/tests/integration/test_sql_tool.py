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
        assert result_data[0]['name'] == 'Alice Smith'

    async def test_schema_detection(self, db_tool_provider: SqlDatabaseTool):
        """Test the automatic schema detection with the new relational schema."""
        summary = db_tool_provider.db_service.get_optimized_schema_for_llm()

        # Check for presence of new tables
        assert "users" in summary
        assert "products" in summary
        assert "categories" in summary
        assert "orders" in summary
        assert "order_items" in summary
        assert "reviews" in summary
        assert "product_categories" in summary

        # Check for a few key columns to ensure detail
        assert "email" in summary
        assert "order_date" in summary
        assert "rating" in summary

    async def test_select_with_aggregation(self, db_tool_provider: SqlDatabaseTool):
        """Test a SELECT query with an aggregation function."""
        query = "SELECT COUNT(*) as user_count FROM users;"
        result = await db_tool_provider._run_async_impl(args={"query": query})
        assert "error" not in result
        # The exact key for the count may vary, so we check the first value.
        assert list(result.get("result")[0].values())[0] == 9

    async def test_select_with_order_by(self, db_tool_provider: SqlDatabaseTool):
        """Test a SELECT query with an ORDER BY clause."""
        query = "SELECT name FROM users ORDER BY name ASC;"
        result = await db_tool_provider._run_async_impl(args={"query": query})
        assert "error" not in result
        names = [row['name'] for row in result.get("result")]
        assert names[0] == 'Alice Smith'
        assert names[-1] == 'User With No Orders'

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
        assert "orders" in schema
        assert "reviews" in schema
        assert "id" in schema
        assert "name" in schema
        assert "price" in schema
        assert "email" in schema
        assert "rating" in schema

    @pytest.mark.parametrize("query", [
        "INSERT INTO users (id, name, email, created_at) VALUES (10, 'test_user', 'test@example.com', '2023-01-01 00:00:00');",
        "UPDATE users SET name = 'test_update' WHERE id = 1;",
        "DELETE FROM users WHERE id = 2;",
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

    async def test_multi_table_join_query(self, db_tool_provider: SqlDatabaseTool):
        """Test a query that joins multiple tables to find product names ordered by a user."""
        query = """
            SELECT p.name
            FROM users u
            JOIN orders o ON u.id = o.user_id
            JOIN order_items oi ON o.id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            WHERE u.name = 'Alice Smith'
            ORDER BY p.name;
        """
        result = await db_tool_provider._run_async_impl(args={"query": query})
        assert "error" not in result, f"Query failed: {result.get('error')}"
        
        product_names = [row['name'] for row in result.get("result", [])]
        assert "Espresso Machine" in product_names
        assert "Laptop Pro 16\"" in product_names
        assert "The Galactic Saga" in product_names
        assert "Wireless ANC Headphones" in product_names

    async def test_aggregation_with_join(self, db_tool_provider: SqlDatabaseTool):
        """Test a query that uses aggregation across joined tables."""
        query = """
            SELECT c.name, AVG(r.rating) as average_rating
            FROM categories c
            JOIN product_categories pc ON c.id = pc.category_id
            JOIN products p ON pc.product_id = p.id
            JOIN reviews r ON p.id = r.product_id
            WHERE c.name = 'Electronics'
            GROUP BY c.name;
        """
        result = await db_tool_provider._run_async_impl(args={"query": query})
        assert "error" not in result, f"Query failed: {result.get('error')}"
        
        result_data = result.get("result")
        assert len(result_data) == 1
        # The average rating for electronics is (5+5+5+4+5)/5 = 4.8
        assert abs(float(result_data[0]['average_rating']) - 4.8) < 0.01
