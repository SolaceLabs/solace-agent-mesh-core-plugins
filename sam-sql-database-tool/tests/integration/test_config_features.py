import pytest
import time
from sam_sql_database_tool.tools import SqlDatabaseTool, DatabaseConfig

@pytest.mark.asyncio
class TestConfigFeatures:
    """Tests for specific configuration features of the SqlDatabaseTool."""

    @pytest.mark.parametrize(
        "max_cardinality, should_be_enum",
        [
            (-1, False), # Should not be an enum for negative cardinality
            (0, False),  # Should not be an enum for zero cardinality
            (3, False),  # Should not be an enum when cardinality is below the threshold
            (4, True),   # Should be an enum at the exact boundary
            (5, True),   # Should be an enum when cardinality is above the threshold
            (100, True)  # Should be an enum with a large threshold
        ]
    )
    async def test_max_enum_cardinality(self, db_tool_provider, max_cardinality, should_be_enum):
        """Test that max_enum_cardinality correctly influences schema detection."""
        # Re-initialize the tool with a custom config
        tool_config_dict = db_tool_provider.tool_config.model_dump()
        tool_config_dict['max_enum_cardinality'] = max_cardinality
        
        custom_config = DatabaseConfig(**tool_config_dict)
        tool = SqlDatabaseTool(custom_config)
        await tool.init(component=None, tool_config={})

        schema = tool.db_service.get_optimized_schema_for_llm(
            max_enum_cardinality=tool.tool_config.max_enum_cardinality,
            sample_size=tool.tool_config.schema_sample_size
        )

        # Check if the 'status' column in the 'orders' table is treated as an ENUM
        # The schema is YAML, so we check for the presence of the 'enum:' key under the status column.
        schema_lines = schema.split('\n')
        try:
            orders_index = schema_lines.index('orders:')
            status_index = schema_lines.index('    status:', orders_index)
            enum_line_index = status_index + 2  # Expect 'type' then 'enum'
            
            has_enum = 'enum:' in schema_lines[enum_line_index]
        except ValueError:
            has_enum = False
        
        assert has_enum == should_be_enum
        await tool.cleanup(component=None, tool_config={})

    async def test_cache_ttl_seconds(self, db_tool_provider):
        """Test that the schema cache expires and refreshes after the TTL."""
        # Re-initialize the tool with a short TTL
        tool_config_dict = db_tool_provider.tool_config.model_dump()
        tool_config_dict['cache_ttl_seconds'] = 2

        custom_config = DatabaseConfig(**tool_config_dict)
        tool = SqlDatabaseTool(custom_config)
        await tool.init(component=None, tool_config={})

        # 1. Get the initial schema to populate the cache
        initial_schema = tool.db_service.get_optimized_schema_for_llm()
        assert "temp_col_for_ttl_test" not in initial_schema

        # 2. Directly alter the database schema
        # MSSQL uses different ALTER TABLE syntax (no COLUMN keyword)
        dialect = tool.db_service.engine.dialect.name
        if dialect == 'mssql':
            add_col_sql = "ALTER TABLE users ADD temp_col_for_ttl_test INT"
            drop_col_sql = "ALTER TABLE users DROP COLUMN temp_col_for_ttl_test"
        else:
            add_col_sql = "ALTER TABLE users ADD COLUMN temp_col_for_ttl_test INT"
            drop_col_sql = "ALTER TABLE users DROP COLUMN temp_col_for_ttl_test"

        conn = tool.db_service.engine.connect()
        try:
            conn.execute(pytest.importorskip("sqlalchemy").text(add_col_sql))
            conn.commit()

            # 3. Wait for the cache TTL to expire
            time.sleep(3)

            # 4. Get the schema again. This will return the stale cache and trigger a background refresh.
            stale_schema = tool.db_service.get_optimized_schema_for_llm()
            assert "temp_col_for_ttl_test" not in stale_schema, "Should serve stale schema on first call after expiry"

            # 5. Wait for the background refresh to complete
            time.sleep(1) # Give the background thread a moment to work

            # 6. Get the schema a third time; it should now be refreshed from the background job.
            refreshed_schema = tool.db_service.get_optimized_schema_for_llm()

            # 7. Assert that the new column is now present
            assert "temp_col_for_ttl_test" in refreshed_schema, "Schema should be refreshed with the new column"

        finally:
            # Clean up the added column
            conn.execute(pytest.importorskip("sqlalchemy").text(drop_col_sql))
            conn.commit()
            conn.close()
            await tool.cleanup(component=None, tool_config={})

    async def test_clear_cache(self, db_tool_provider):
        """Test that clear_cache() forces a schema refresh on the next call."""
        tool = db_tool_provider

        # 1. Get the initial schema to populate the cache
        initial_schema = tool.db_service.get_optimized_schema_for_llm()
        assert "temp_col_for_clear_test" not in initial_schema

        # 2. Directly alter the database schema
        # MSSQL uses different ALTER TABLE syntax (no COLUMN keyword)
        dialect = tool.db_service.engine.dialect.name
        if dialect == 'mssql':
            add_col_sql = "ALTER TABLE users ADD temp_col_for_clear_test INT"
            drop_col_sql = "ALTER TABLE users DROP COLUMN temp_col_for_clear_test"
        else:
            add_col_sql = "ALTER TABLE users ADD COLUMN temp_col_for_clear_test INT"
            drop_col_sql = "ALTER TABLE users DROP COLUMN temp_col_for_clear_test"

        conn = tool.db_service.engine.connect()
        try:
            conn.execute(pytest.importorskip("sqlalchemy").text(add_col_sql))
            conn.commit()

            # 3. Manually clear the cache
            tool.db_service.clear_cache()

            # 4. Get the schema again. It should be re-fetched immediately because the cache is gone.
            refreshed_schema = tool.db_service.get_optimized_schema_for_llm()

            # 5. Assert that the new column is now present
            assert "temp_col_for_clear_test" in refreshed_schema

        finally:
            # Clean up the added column
            conn.execute(pytest.importorskip("sqlalchemy").text(drop_col_sql))
            conn.commit()
            conn.close()
