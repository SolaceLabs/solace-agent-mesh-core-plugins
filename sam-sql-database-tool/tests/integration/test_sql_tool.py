import pytest
import sqlalchemy as sa
from sam_sql_database_tool.tools import SqlDatabaseTool
from tests.test_data import users, products, categories, orders, order_items, reviews, product_categories

@pytest.mark.asyncio
class TestSqlDatabaseTool:
    """End-to-end tests for the SqlDatabaseTool across all supported providers."""

    async def test_select_data(self, db_tool_provider: SqlDatabaseTool):
        """Test selecting data from a table."""
        query = sa.select(users).where(users.c.id == 1)
        select_query = str(query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))
        select_result = await db_tool_provider._run_async_impl(args={"query": select_query})
        
        assert "error" not in select_result, f"Failed to select data: {select_result.get('error')}"
        result_data = select_result.get("result")
        assert len(result_data) == 1
        assert result_data[0]['name'] == 'Alice Smith'

    async def test_schema_detection(self, db_tool_provider: SqlDatabaseTool):
        """Test the automatic schema detection with the new relational schema."""
        summary = db_tool_provider.db_service.get_optimized_schema_for_llm()

        if db_tool_provider.tool_config.auto_detect_schema:
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
        else:
            description = db_tool_provider.tool_description
            assert "MANUAL_SCHEMA_TEST" in description
            
            # Also ensure it can still run queries
            query = sa.select(users).where(users.c.id == 1)
            select_query = str(query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))
            select_result = await db_tool_provider._run_async_impl(args={"query": select_query})
            assert "error" not in select_result

    async def test_select_with_aggregation(self, db_tool_provider: SqlDatabaseTool):
        """Test a SELECT query with an aggregation function."""
        query = sa.select(sa.func.count().label("user_count")).select_from(users)
        compiled_query = str(query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))
        result = await db_tool_provider._run_async_impl(args={"query": compiled_query})
        assert "error" not in result
        # The exact key for the count may vary, so we check the first value.
        assert list(result.get("result")[0].values())[0] == 9

    async def test_select_with_order_by(self, db_tool_provider: SqlDatabaseTool):
        """Test a SELECT query with an ORDER BY clause."""
        query = sa.select(users.c.name).order_by(users.c.name.asc())
        compiled_query = str(query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))
        result = await db_tool_provider._run_async_impl(args={"query": compiled_query})
        assert "error" not in result
        names = [row['name'] for row in result.get("result")]
        assert names[0] == 'Alice Smith'
        assert names[-1] == 'User With No Orders'

    async def test_invalid_select_query(self, db_tool_provider: SqlDatabaseTool):
        """Test that an invalid SELECT query returns an error."""
        non_existent_table = sa.Table('non_existent_table', sa.MetaData(), sa.Column('id'))
        query = sa.select(non_existent_table)
        compiled_query = str(query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))
        result = await db_tool_provider._run_async_impl(args={"query": compiled_query})
        assert "error" in result
        
    async def test_schema_caching(self, db_tool_provider: SqlDatabaseTool):
        """Test that schema is cached in memory."""
        assert db_tool_provider._schema_context is not None
        assert len(db_tool_provider._schema_context) > 0

        if db_tool_provider.tool_config.auto_detect_schema:
            assert "users" in db_tool_provider._schema_context
            assert "products" in db_tool_provider._schema_context
        else:
            assert db_tool_provider._schema_context == "MANUAL_SCHEMA_TEST"

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


    async def test_multi_table_join_query(self, db_tool_provider: SqlDatabaseTool):
        """Test a query that joins multiple tables to find product names ordered by a user."""
        query = (
            sa.select(products.c.name)
            .join(order_items, products.c.id == order_items.c.product_id)
            .join(orders, order_items.c.order_id == orders.c.id)
            .join(users, orders.c.user_id == users.c.id)
            .where(users.c.name == 'Alice Smith')
            .order_by(products.c.name)
        )
        compiled_query = str(query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))
        result = await db_tool_provider._run_async_impl(args={"query": compiled_query})
        assert "error" not in result, f"Query failed: {result.get('error')}"
        
        product_names = [row['name'] for row in result.get("result", [])]
        assert "Espresso Machine" in product_names
        assert "Laptop Pro 16\"" in product_names
        assert "The Galactic Saga" in product_names
        assert "Wireless ANC Headphones" in product_names

    async def test_aggregation_with_join(self, db_tool_provider: SqlDatabaseTool):
        """Test a query that uses aggregation across joined tables."""
        query = (
            sa.select(
                categories.c.name,
                sa.func.avg(reviews.c.rating).label("average_rating")
            )
            .join(product_categories, categories.c.id == product_categories.c.category_id)
            .join(products, product_categories.c.product_id == products.c.id)
            .join(reviews, products.c.id == reviews.c.product_id)
            .where(categories.c.name == 'Electronics')
            .group_by(categories.c.name)
        )
        compiled_query = str(query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))
        result = await db_tool_provider._run_async_impl(args={"query": compiled_query})
        assert "error" not in result, f"Query failed: {result.get('error')}"

        result_data = result.get("result")
        assert len(result_data) == 1
        # The average rating for electronics is (5+5+5+4+5)/5 = 4.8
        assert abs(float(result_data[0]['average_rating']) - 4.8) < 0.01

    async def test_insert_and_verify_persistence(self, db_tool_provider: SqlDatabaseTool):
        """Test that INSERT operations properly persist data (DATAGO-116435)."""
        from datetime import datetime

        insert_query = sa.insert(users).values(
            id=999,
            name='Test User',
            email='test.user@example.com',
            created_at=datetime(2024, 1, 1, 12, 0, 0)
        )
        compiled_insert = str(insert_query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))

        insert_result = await db_tool_provider._run_async_impl(args={"query": compiled_insert})
        assert "error" not in insert_result, f"Insert failed: {insert_result.get('error')}"
        assert insert_result.get("result")[0].get("affected_rows") == 1

        verify_query = sa.select(users).where(users.c.id == 999)
        compiled_verify = str(verify_query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))

        verify_result = await db_tool_provider._run_async_impl(args={"query": compiled_verify})
        assert "error" not in verify_result, f"Verify query failed: {verify_result.get('error')}"

        result_data = verify_result.get("result")
        assert len(result_data) == 1, "Inserted row not found - transaction was not committed"
        assert result_data[0]['name'] == 'Test User'
        assert result_data[0]['email'] == 'test.user@example.com'

    async def test_update_and_verify_persistence(self, db_tool_provider: SqlDatabaseTool):
        """Test that UPDATE operations properly persist data (DATAGO-116435)."""
        update_query = sa.update(users).where(users.c.id == 1).values(name='Updated Name')
        compiled_update = str(update_query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))

        update_result = await db_tool_provider._run_async_impl(args={"query": compiled_update})
        assert "error" not in update_result, f"Update failed: {update_result.get('error')}"
        assert update_result.get("result")[0].get("affected_rows") == 1

        verify_query = sa.select(users.c.name).where(users.c.id == 1)
        compiled_verify = str(verify_query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))

        verify_result = await db_tool_provider._run_async_impl(args={"query": compiled_verify})
        assert "error" not in verify_result, f"Verify query failed: {verify_result.get('error')}"

        result_data = verify_result.get("result")
        assert len(result_data) == 1
        assert result_data[0]['name'] == 'Updated Name', "Update was not committed"

    async def test_delete_and_verify_persistence(self, db_tool_provider: SqlDatabaseTool):
        """Test that DELETE operations properly persist data (DATAGO-116435)."""
        count_before_query = sa.select(sa.func.count()).select_from(users).where(users.c.id == 2)
        compiled_count_before = str(count_before_query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))

        count_before_result = await db_tool_provider._run_async_impl(args={"query": compiled_count_before})
        assert list(count_before_result.get("result")[0].values())[0] == 1

        delete_query = sa.delete(users).where(users.c.id == 2)
        compiled_delete = str(delete_query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))

        delete_result = await db_tool_provider._run_async_impl(args={"query": compiled_delete})
        assert "error" not in delete_result, f"Delete failed: {delete_result.get('error')}"
        assert delete_result.get("result")[0].get("affected_rows") == 1

        verify_query = sa.select(sa.func.count()).select_from(users).where(users.c.id == 2)
        compiled_verify = str(verify_query.compile(db_tool_provider.db_service.engine, compile_kwargs={"literal_binds": True}))

        verify_result = await db_tool_provider._run_async_impl(args={"query": compiled_verify})
        assert "error" not in verify_result, f"Verify query failed: {verify_result.get('error')}"

        count_after = list(verify_result.get("result")[0].values())[0]
        assert count_after == 0, "Delete was not committed"
