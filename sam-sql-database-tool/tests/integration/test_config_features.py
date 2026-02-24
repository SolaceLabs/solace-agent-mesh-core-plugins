import io
import logging
import threading
import time

import pytest
from sqlalchemy.exc import TimeoutError as SATimeoutError

from sam_sql_database_tool.services.database_service import DatabaseService
from sam_sql_database_tool.tools import SqlDatabaseTool, DatabaseConfig


def get_add_column_sql(dialect, table_name, column_name, column_type="INT"):
    """Get dialect-specific ALTER TABLE ADD COLUMN SQL."""
    if dialect in ('mssql', 'oracle'):
        return f"ALTER TABLE {table_name} ADD {column_name} {column_type}"
    else:
        return f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"


def get_drop_column_sql(dialect, table_name, column_name):
    """Get dialect-specific ALTER TABLE DROP COLUMN SQL."""
    return f"ALTER TABLE {table_name} DROP COLUMN {column_name}"


def get_select_one_sql(dialect):
    """Return a dialect-appropriate query that selects the integer 1."""
    if dialect == "oracle":
        return "SELECT 1 FROM DUAL"
    return "SELECT 1"


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
        dialect = tool.db_service.engine.dialect.name
        add_col_sql = get_add_column_sql(dialect, "users", "temp_col_for_ttl_test")
        drop_col_sql = get_drop_column_sql(dialect, "users", "temp_col_for_ttl_test")

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
        dialect = tool.db_service.engine.dialect.name
        add_col_sql = get_add_column_sql(dialect, "users", "temp_col_for_clear_test")
        drop_col_sql = get_drop_column_sql(dialect, "users", "temp_col_for_clear_test")

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


class TestEngineConfig:
    """Integration tests that verify SQLAlchemy engine/pool config is actually applied.

    Each test creates a fresh DatabaseService directly — bypassing SqlDatabaseTool.init()
    — so it gets its own engine with the specific configuration under test, independent
    of any session-scoped engine reuse.
    """

    def _make_service(self, database_container, **kwargs) -> DatabaseService:
        """Create a fresh DatabaseService with an isolated engine for the given backend."""
        db_config = database_container.db_config
        connection_string = db_config.connection_url_fn(database_container)
        return DatabaseService(connection_string=connection_string, **kwargs)

    def test_pool_size_reflected_on_engine(self, database_container):
        """pool_size=3 is reflected on the QueuePool for every DB backend."""
        service = self._make_service(database_container, pool_size=3)
        try:
            assert service.engine.pool.size() == 3
        finally:
            service.close()

    def test_max_overflow_reflected_on_engine(self, database_container):
        """max_overflow=7 is reflected on the QueuePool for every DB backend."""
        service = self._make_service(database_container, max_overflow=7)
        try:
            assert service.engine.pool._max_overflow == 7
        finally:
            service.close()

    def test_pool_timeout_causes_timeout(self, database_container):
        """pool_timeout=1 causes a TimeoutError when all pool slots are occupied."""
        # pool_size=1, max_overflow=0 → exactly one connection slot; timeout after 1 s
        service = self._make_service(
            database_container, pool_size=1, max_overflow=0, pool_timeout=1
        )
        try:
            ready = threading.Event()
            release = threading.Event()

            def hold_connection():
                with service.engine.connect():
                    ready.set()
                    release.wait(timeout=10)

            holder = threading.Thread(target=hold_connection, daemon=True)
            holder.start()
            ready.wait(timeout=5)

            try:
                with pytest.raises(SATimeoutError):
                    with service.engine.connect():
                        pass
            finally:
                release.set()
                holder.join(timeout=5)
        finally:
            service.close()

    def test_pool_recycle_reflected_on_engine(self, database_container):
        """pool_recycle=600 is stored on the pool for every DB backend."""
        service = self._make_service(database_container, pool_recycle=600)
        try:
            assert service.engine.pool._recycle == 600
        finally:
            service.close()

    def test_pool_pre_ping_disabled_reflected(self, database_container):
        """pool_pre_ping=False is stored on the pool for every DB backend."""
        service = self._make_service(database_container, pool_pre_ping=False)
        try:
            assert service.engine.pool._pre_ping is False
        finally:
            service.close()

    def test_echo_logs_sql(self, database_container):
        """echo=True causes SQL statements to be emitted by the sqlalchemy.engine logger."""
        db_config = database_container.db_config
        service = self._make_service(database_container, echo=True)
        try:
            assert service.echo is True

            stream = io.StringIO()
            handler = logging.StreamHandler(stream)
            logging.getLogger("sqlalchemy.engine").addHandler(handler)
            try:
                service.execute_query(get_select_one_sql(db_config.name))
                output = stream.getvalue()
                assert "SELECT" in output.upper()
            finally:
                logging.getLogger("sqlalchemy.engine").removeHandler(handler)
        finally:
            service.close()

    def test_isolation_level_stored_on_service(self, database_container):
        """isolation_level is stored on DatabaseService and passed to create_engine."""
        db_config = database_container.db_config
        # READ_COMMITTED is supported by all tested backends
        isolation = (
            "READ COMMITTED" if db_config.name.startswith("oracle") else "READ_COMMITTED"
        )
        service = self._make_service(database_container, isolation_level=isolation)
        try:
            assert service.isolation_level == isolation
        finally:
            service.close()

    def test_connect_args_stored_and_engine_functional(self, database_container):
        """connect_args are stored on DatabaseService and the engine executes queries."""
        db_config = database_container.db_config
        # application_name is a valid PostgreSQL connect_arg; use empty dict for other backends
        connect_args = (
            {"application_name": "sam_test"} if db_config.name == "postgresql" else {}
        )
        service = self._make_service(database_container, connect_args=connect_args)
        try:
            assert service.connect_args == connect_args
            results = service.execute_query(get_select_one_sql(db_config.name))
            assert results is not None
        finally:
            service.close()
