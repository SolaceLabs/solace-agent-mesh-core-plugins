import pytest
from unittest.mock import MagicMock, patch
from sam_sql_database_tool.services.database_service import DatabaseService

@pytest.fixture
def mock_db_service():
    """Fixture to create a mock DatabaseService."""
    with patch('sqlalchemy.create_engine') as mock_create_engine:
        mock_engine = MagicMock()
        mock_engine.dialect.name = "sqlite"
        mock_create_engine.return_value = mock_engine
        
        service = DatabaseService("sqlite:///:memory:")
        service.engine = mock_engine
        return service

class TestDatabaseService:
    """Unit tests for the DatabaseService."""

    def test_get_detailed_schema_representation(self, mock_db_service):
        """Test the creation of a detailed schema representation."""
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["users"]
        mock_inspector.get_columns.return_value = [
            {"name": "id", "type": "INTEGER", "nullable": False, "default": None},
            {"name": "name", "type": "VARCHAR(50)", "nullable": True, "default": None},
        ]
        mock_inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
        mock_inspector.get_foreign_keys.return_value = []
        mock_inspector.get_indexes.return_value = []
        
        mock_db_service.engine.connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value = [
            {"id": 1}, {"id": 2}
        ]

        with patch('sam_sql_database_tool.services.database_service.inspect', return_value=mock_inspector):
            schema = mock_db_service.get_detailed_schema_representation()

        assert "users" in schema
        assert "id" in schema["users"]["columns"]
        assert schema["users"]["columns"]["id"]["type"] == "INTEGER"
        assert schema["users"]["primary_keys"] == ["id"]

    def test_get_schema_summary_for_llm(self, mock_db_service):
        """Test the creation of a simplified schema summary for the LLM."""
        detailed_schema = {
            "users": {
                "columns": {
                    "id": {"type": "INTEGER"},
                    "name": {"type": "VARCHAR(50)"}
                },
                "primary_keys": ["id"]
            }
        }
        with patch.object(mock_db_service, 'get_detailed_schema_representation', return_value=detailed_schema):
            summary = mock_db_service.get_schema_summary_for_llm()

        assert "users:" in summary
        assert "id: INTEGER" in summary
        assert "primary_keys:" in summary
        assert "- id" in summary

    def test_execute_query_no_engine(self):
        """Test that executing a query without an engine raises an error."""
        with patch('sqlalchemy.create_engine', side_effect=Exception("Connection failed")):
            with pytest.raises(Exception, match="Connection failed"):
                DatabaseService("bad-connection-string")
