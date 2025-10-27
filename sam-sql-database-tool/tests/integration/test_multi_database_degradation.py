import pytest
import sqlalchemy as sa
from sam_sql_database_tool.tools import SqlDatabaseTool, DatabaseConfig


@pytest.mark.asyncio
class TestMultiDatabaseDegradation:
    """Tests for graceful degradation with multiple database connections."""

    async def test_multiple_healthy_databases(self, database_container, database_engine):
        """Test that multiple healthy databases all initialize successfully."""
        engine, db_config = database_engine
        connection_url = db_config.connection_url_fn(database_container)

        configs = [
            DatabaseConfig(
                tool_name=f"{db_config.name}_db1",
                tool_description=f"First {db_config.name} database",
                connection_string=connection_url,
            ),
            DatabaseConfig(
                tool_name=f"{db_config.name}_db2",
                tool_description=f"Second {db_config.name} database",
                connection_string=connection_url,
            ),
            DatabaseConfig(
                tool_name=f"{db_config.name}_db3",
                tool_description=f"Third {db_config.name} database",
                connection_string=connection_url,
            ),
        ]

        tools = []
        for config in configs:
            tool = SqlDatabaseTool(config)
            await tool.init(component=None, tool_config={})
            tools.append(tool)

        for tool in tools:
            assert tool._connection_healthy is True
            assert tool._connection_error is None
            assert tool.db_service is not None
            assert "✅ Database Connected" in tool.tool_description

            result = await tool._run_async_impl(args={"query": "SELECT 1"})
            assert "result" in result
            assert "error" not in result

        for tool in tools:
            await tool.cleanup(component=None, tool_config={})

    async def test_mixed_health_some_offline(self, database_container, database_engine):
        """Test multiple databases where some are healthy and some are offline."""
        engine, db_config = database_engine
        healthy_connection_url = db_config.connection_url_fn(database_container)

        if db_config.name == "postgresql":
            offline_connection_url = "postgresql+psycopg2://user:pass@nonexistent-host.invalid:5432/db"
        else:
            offline_connection_url = "mysql+pymysql://user:pass@nonexistent-host.invalid:3306/db"

        configs = [
            DatabaseConfig(
                tool_name="healthy_db1",
                tool_description="First healthy database",
                connection_string=healthy_connection_url,
            ),
            DatabaseConfig(
                tool_name="offline_db",
                tool_description="Offline database",
                connection_string=offline_connection_url,
            ),
            DatabaseConfig(
                tool_name="healthy_db2",
                tool_description="Second healthy database",
                connection_string=healthy_connection_url,
            ),
        ]

        tools = []
        for config in configs:
            tool = SqlDatabaseTool(config)
            await tool.init(component=None, tool_config={})
            tools.append(tool)

        assert tools[0]._connection_healthy is True
        assert "✅ Database Connected" in tools[0].tool_description
        result = await tools[0]._run_async_impl(args={"query": "SELECT 1"})
        assert "result" in result

        assert tools[1]._connection_healthy is False
        assert tools[1]._connection_error is not None
        assert "❌ WARNING: This database is currently UNAVAILABLE" in tools[1].tool_description
        result = await tools[1]._run_async_impl(args={"query": "SELECT 1"})
        assert "error" in result
        assert "currently unavailable" in result["error"]

        assert tools[2]._connection_healthy is True
        assert "✅ Database Connected" in tools[2].tool_description
        result = await tools[2]._run_async_impl(args={"query": "SELECT 1"})
        assert "result" in result

        for tool in tools:
            await tool.cleanup(component=None, tool_config={})

    async def test_all_databases_offline(self):
        """Test that all tools degrade gracefully when all databases are offline."""
        configs = [
            DatabaseConfig(
                tool_name="offline_postgres",
                tool_description="Offline PostgreSQL database",
                connection_string="postgresql+psycopg2://user:pass@nonexistent1.invalid:5432/db",
            ),
            DatabaseConfig(
                tool_name="offline_mysql",
                tool_description="Offline MySQL database",
                connection_string="mysql+pymysql://user:pass@nonexistent2.invalid:3306/db",
            ),
        ]

        tools = []
        for config in configs:
            tool = SqlDatabaseTool(config)
            await tool.init(component=None, tool_config={})
            tools.append(tool)

        for tool in tools:
            assert tool._connection_healthy is False
            assert tool._connection_error is not None
            assert "❌ WARNING: This database is currently UNAVAILABLE" in tool.tool_description

            result = await tool._run_async_impl(args={"query": "SELECT 1"})
            assert "error" in result
            assert "currently unavailable" in result["error"]

        for tool in tools:
            await tool.cleanup(component=None, tool_config={})

    async def test_same_server_different_databases(self, database_container, database_engine):
        """Test multiple connections to the same server but different databases."""
        engine, db_config = database_engine
        base_connection_url = db_config.connection_url_fn(database_container)

        if db_config.name == "postgresql":
            db1_url = base_connection_url
            db2_url = base_connection_url.replace("/test_db", "/postgres")
        else:
            db1_url = base_connection_url
            db2_url = base_connection_url.replace("/test_db", "/mysql")

        configs = [
            DatabaseConfig(
                tool_name="db1_connection",
                tool_description="Connection to first database",
                connection_string=db1_url,
            ),
            DatabaseConfig(
                tool_name="db2_connection",
                tool_description="Connection to second database",
                connection_string=db2_url,
            ),
        ]

        tools = []
        for config in configs:
            tool = SqlDatabaseTool(config)
            await tool.init(component=None, tool_config={})
            tools.append(tool)

        assert tools[0]._connection_healthy is True
        assert tools[0].db_service is not None

        result = await tools[0]._run_async_impl(args={"query": "SELECT 1"})
        assert "result" in result

        for tool in tools:
            await tool.cleanup(component=None, tool_config={})

    async def test_degraded_tool_status_messages(self):
        """Test that degraded tools provide clear status messages to the LLM."""
        config = DatabaseConfig(
            tool_name="test_degraded_db",
            tool_description="Test database that will fail",
            connection_string="postgresql+psycopg2://user:pass@nonexistent.invalid:5432/db",
        )

        tool = SqlDatabaseTool(config)
        await tool.init(component=None, tool_config={})

        assert tool._connection_healthy is False

        description = tool.tool_description
        assert "❌ WARNING: This database is currently UNAVAILABLE" in description
        assert "Connection Error:" in description
        assert "Queries to this database will fail until connectivity is restored" in description
        assert "Test database that will fail" in description

        result = await tool._run_async_impl(args={"query": "SELECT * FROM users"})
        assert "error" in result
        assert "test_degraded_db" in result["error"]
        assert "currently unavailable" in result["error"]

        await tool.cleanup(component=None, tool_config={})

    async def test_healthy_tool_status_messages(self, database_container, database_engine):
        """Test that healthy tools show proper status messages to the LLM."""
        engine, db_config = database_engine
        connection_url = db_config.connection_url_fn(database_container)

        config = DatabaseConfig(
            tool_name="test_healthy_db",
            tool_description="Test healthy database",
            connection_string=connection_url,
        )

        tool = SqlDatabaseTool(config)
        await tool.init(component=None, tool_config={})

        assert tool._connection_healthy is True
        assert tool._connection_error is None

        description = tool.tool_description
        assert "✅ Database Connected" in description
        assert "Database Schema:" in description
        assert "Test healthy database" in description
        assert "❌" not in description

        result = await tool._run_async_impl(args={"query": "SELECT 1"})
        assert "result" in result
        assert "error" not in result

        await tool.cleanup(component=None, tool_config={})

    async def test_connection_isolation(self, database_container, database_engine):
        """Test that database connections are properly isolated."""
        engine, db_config = database_engine
        connection_url = db_config.connection_url_fn(database_container)

        tool1_config = DatabaseConfig(
            tool_name="isolated_db1",
            tool_description="First isolated database",
            connection_string=connection_url,
        )

        tool2_config = DatabaseConfig(
            tool_name="isolated_db2",
            tool_description="Second isolated database",
            connection_string=connection_url,
        )

        tool1 = SqlDatabaseTool(tool1_config)
        tool2 = SqlDatabaseTool(tool2_config)

        await tool1.init(component=None, tool_config={})
        await tool2.init(component=None, tool_config={})

        assert tool1.db_service is not tool2.db_service
        assert tool1.db_service.engine is not tool2.db_service.engine

        result1 = await tool1._run_async_impl(args={"query": "SELECT 1 as value"})
        result2 = await tool2._run_async_impl(args={"query": "SELECT 2 as value"})

        assert "result" in result1
        assert "result" in result2
        assert result1 != result2

        await tool1.cleanup(component=None, tool_config={})
        await tool2.cleanup(component=None, tool_config={})

    async def test_recovery_after_init_failure(self):
        """Test that a tool can be identified as degraded and doesn't crash other operations."""
        bad_config = DatabaseConfig(
            tool_name="bad_db",
            tool_description="Database that fails to initialize",
            connection_string="postgresql+psycopg2://user:pass@nonexistent.invalid:5432/db",
        )

        bad_tool = SqlDatabaseTool(bad_config)

        await bad_tool.init(component=None, tool_config={})

        assert bad_tool._connection_healthy is False
        assert bad_tool._connection_error is not None

        result = await bad_tool._run_async_impl(args={"query": "SELECT 1"})
        assert "error" in result
        assert "currently unavailable" in result["error"]

        await bad_tool.cleanup(component=None, tool_config={})

    async def test_mixed_auto_and_manual_schema(self, database_container, database_engine):
        """Test mixed auto-detect and manual schema with some databases offline."""
        engine, db_config = database_engine
        healthy_connection_url = db_config.connection_url_fn(database_container)

        configs = [
            DatabaseConfig(
                tool_name="auto_healthy",
                tool_description="Auto-detect healthy database",
                connection_string=healthy_connection_url,
                auto_detect_schema=True,
            ),
            DatabaseConfig(
                tool_name="manual_offline",
                tool_description="Manual schema offline database",
                connection_string="mysql+pymysql://user:pass@nonexistent.invalid:3306/db",
                auto_detect_schema=False,
                schema_summary_override="Manual schema for offline DB",
            ),
            DatabaseConfig(
                tool_name="auto_offline",
                tool_description="Auto-detect offline database",
                connection_string="postgresql+psycopg2://user:pass@nonexistent.invalid:5432/db",
                auto_detect_schema=True,
            ),
        ]

        tools = []
        for config in configs:
            tool = SqlDatabaseTool(config)
            await tool.init(component=None, tool_config={})
            tools.append(tool)

        assert tools[0]._connection_healthy is True
        assert "Database Schema:" in tools[0].tool_description

        assert tools[1]._connection_healthy is True
        assert "Manual schema for offline DB" in tools[1].tool_description
        result = await tools[1]._run_async_impl(args={"query": "SELECT 1"})
        assert "error" in result

        assert tools[2]._connection_healthy is False
        assert "❌ WARNING" in tools[2].tool_description

        for tool in tools:
            await tool.cleanup(component=None, tool_config={})
