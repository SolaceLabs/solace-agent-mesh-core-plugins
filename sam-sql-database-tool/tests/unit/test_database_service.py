import pytest
from unittest.mock import MagicMock, patch
from sam_sql_database_tool.services.database_service import DatabaseService

@pytest.fixture
def mock_db_service():
    """Fixture to create a mock DatabaseService."""
    with patch('sqlalchemy.create_engine') as mock_create_engine:
        mock_engine = MagicMock()
        mock_engine.dialect.name = "postgresql"
        mock_create_engine.return_value = mock_engine

        service = DatabaseService("postgresql://test", cache_ttl_seconds=10)
        service.engine = mock_engine
        return service

class TestDatabaseService:
    """Unit tests for the DatabaseService."""

    def test_get_optimized_schema_for_llm(self, mock_db_service):
        """Test the optimized schema generation for LLM."""
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["users"]
        mock_inspector.get_columns.return_value = [
            {"name": "id", "type": "INTEGER", "nullable": False, "default": None},
            {"name": "name", "type": "VARCHAR(50)", "nullable": True, "default": None},
        ]
        mock_inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
        mock_inspector.get_foreign_keys.return_value = []

        mock_db_service.get_table_sample = MagicMock(return_value=[
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ])

        with patch('sam_sql_database_tool.services.database_service.inspect', return_value=mock_inspector):
            summary = mock_db_service.get_optimized_schema_for_llm()

        assert "users" in summary
        assert "id" in summary
        assert "primary_keys" in summary

    def test_looks_like_enum_column(self, mock_db_service):
        """Test enum column detection heuristic."""
        assert mock_db_service._looks_like_enum_column("status")
        assert mock_db_service._looks_like_enum_column("user_type")
        assert mock_db_service._looks_like_enum_column("category")
        assert not mock_db_service._looks_like_enum_column("email")
        assert not mock_db_service._looks_like_enum_column("description")

    def test_execute_query_no_engine(self):
        """Test that an invalid connection string causes engine creation to fail."""
        with patch('sqlalchemy.create_engine', side_effect=Exception("Connection failed")):
            with pytest.raises(Exception, match="Connection failed"):
                DatabaseService("postgresql://localhost/testdb")

    def test_cache_initialization(self, mock_db_service):
        """Test that cache is properly initialized."""
        assert mock_db_service._schema_cache is None
        assert mock_db_service._cache_timestamp is None
        assert not mock_db_service._refresh_in_progress

    def test_cache_ttl_configuration(self):
        """Test that cache TTL is configurable."""
        with patch('sqlalchemy.create_engine') as mock_create_engine:
            mock_engine = MagicMock()
            mock_engine.dialect.name = "postgresql"
            mock_create_engine.return_value = mock_engine

            service = DatabaseService("postgresql://test", cache_ttl_seconds=3600)
            assert service._cache_ttl.total_seconds() == 3600

            service2 = DatabaseService("postgresql://test", cache_ttl_seconds=7200)
            assert service2._cache_ttl.total_seconds() == 7200

    def test_cache_validity_check(self, mock_db_service):
        """Test cache validity checking."""
        assert not mock_db_service._is_cache_valid()

        mock_db_service._schema_cache = "test_schema"
        assert not mock_db_service._is_cache_valid()

        from datetime import datetime, timedelta, timezone
        mock_db_service._cache_timestamp = datetime.now(timezone.utc)
        assert mock_db_service._is_cache_valid()

        mock_db_service._cache_timestamp = datetime.now(timezone.utc) - timedelta(seconds=11)
        assert not mock_db_service._is_cache_valid()

    def test_clear_cache(self, mock_db_service):
        """Test manual cache clearing."""
        from datetime import datetime, timezone
        mock_db_service._schema_cache = "test_schema"
        mock_db_service._cache_timestamp = datetime.now(timezone.utc)

        mock_db_service.clear_cache()

        assert mock_db_service._schema_cache is None
        assert mock_db_service._cache_timestamp is None

    def test_connection_pool_configuration(self):
        """Test that connection pool is configured correctly."""
        with patch('sqlalchemy.create_engine') as mock_create_engine:
            mock_engine = MagicMock()
            mock_engine.dialect.name = "postgresql"
            mock_create_engine.return_value = mock_engine

            DatabaseService("postgresql://test")

            mock_create_engine.assert_called_once()
            call_kwargs = mock_create_engine.call_args[1]
            assert call_kwargs['pool_size'] == 10
            assert call_kwargs['max_overflow'] == 10
            assert call_kwargs['pool_timeout'] == 30
            assert call_kwargs['pool_recycle'] == 1800
            assert call_kwargs['pool_pre_ping'] is True

    def test_mysql_dialect_detection(self):
        """Test that MySQL dialect is properly detected."""
        with patch('sqlalchemy.create_engine') as mock_create_engine:
            mock_engine = MagicMock()
            mock_engine.dialect.name = "mysql"
            mock_create_engine.return_value = mock_engine

            service = DatabaseService("mysql+pymysql://test")
            assert service.engine.dialect.name == "mysql"


class TestFilterTables:
    """Unit tests for table filtering logic."""

    @pytest.fixture
    def service_with_filters(self):
        """Create a DatabaseService with custom include/exclude filters."""
        def _create(include_tables=None, exclude_tables=None):
            with patch('sqlalchemy.create_engine') as mock_create_engine:
                mock_engine = MagicMock()
                mock_engine.dialect.name = "postgresql"
                mock_create_engine.return_value = mock_engine
                return DatabaseService(
                    "postgresql://test",
                    include_tables=include_tables,
                    exclude_tables=exclude_tables,
                )
        return _create

    def test_no_filters_returns_all(self, service_with_filters):
        """No filters should return all tables unchanged."""
        service = service_with_filters()
        tables = ["users", "orders", "products"]
        assert service._filter_tables(tables) == ["users", "orders", "products"]

    def test_include_exact_match(self, service_with_filters):
        """Include with exact names should only return matching tables."""
        service = service_with_filters(include_tables=["users", "orders"])
        tables = ["users", "orders", "products", "logs"]
        assert service._filter_tables(tables) == ["users", "orders"]

    def test_include_wildcard(self, service_with_filters):
        """Include with wildcard patterns should match correctly."""
        service = service_with_filters(include_tables=["tms_trx*", "tms_alert*"])
        tables = ["tms_trx5min", "tms_trx60min", "tms_alert_anomaly", "tms_bank", "bkp_data"]
        assert service._filter_tables(tables) == ["tms_trx5min", "tms_trx60min", "tms_alert_anomaly"]

    def test_exclude_wildcard(self, service_with_filters):
        """Exclude with wildcard patterns should remove matching tables."""
        service = service_with_filters(exclude_tables=["bkp_*", "*_temp", "*_dev"])
        tables = ["tms_trx5min", "bkp_old_data", "tms_data_temp", "tms_aggr_dev", "tms_alert"]
        assert service._filter_tables(tables) == ["tms_trx5min", "tms_alert"]

    def test_include_and_exclude_together(self, service_with_filters):
        """Include and exclude together: include first, then exclude from result."""
        service = service_with_filters(
            include_tables=["tms_trx*"],
            exclude_tables=["*_temp", "*_dev"],
        )
        tables = ["tms_trx5min", "tms_trx_temp", "tms_trx_dev", "tms_trx60min", "tms_bank"]
        assert service._filter_tables(tables) == ["tms_trx5min", "tms_trx60min"]

    def test_question_mark_wildcard(self, service_with_filters):
        """The ? wildcard should match a single character."""
        service = service_with_filters(include_tables=["table_?"])
        tables = ["table_a", "table_b", "table_ab", "other"]
        assert service._filter_tables(tables) == ["table_a", "table_b"]

    def test_case_sensitive(self, service_with_filters):
        """Matching should be case-sensitive."""
        service = service_with_filters(include_tables=["Users"])
        tables = ["Users", "users", "USERS"]
        assert service._filter_tables(tables) == ["Users"]

    def test_empty_include_list_returns_all(self, service_with_filters):
        """An empty include list should be falsy and return all tables."""
        service = service_with_filters(include_tables=[])
        tables = ["users", "orders", "products"]
        assert service._filter_tables(tables) == ["users", "orders", "products"]

    def test_all_tables_filtered_out(self, service_with_filters):
        """When all tables are excluded, result should be empty."""
        service = service_with_filters(include_tables=["nonexistent_*"])
        tables = ["users", "orders", "products"]
        assert service._filter_tables(tables) == []

    def test_compute_schema_uses_filter(self, service_with_filters):
        """_compute_schema should only process tables that pass the filter."""
        service = service_with_filters(include_tables=["users"])

        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["users", "orders", "products"]
        mock_inspector.get_columns.return_value = [
            {"name": "id", "type": "INTEGER", "nullable": False},
        ]
        mock_inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
        mock_inspector.get_foreign_keys.return_value = []
        mock_inspector.get_indexes.return_value = []

        service.get_table_sample = MagicMock(return_value=[{"id": 1}])

        with patch('sam_sql_database_tool.services.database_service.inspect', return_value=mock_inspector):
            schema = service._compute_schema(max_enum_cardinality=100, sample_size=100)

        assert "users" in schema
        assert "orders" not in schema
        assert "products" not in schema
