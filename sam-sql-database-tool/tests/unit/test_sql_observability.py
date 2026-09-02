"""Tests for SQL database connector observability instrumentation.

Verifies outbound.request.duration metrics are recorded with correct labels
when SQL queries are executed through SqlDatabaseTool.
"""

import pytest
from unittest.mock import MagicMock, patch

from sam_sql_database_tool.tools import SqlDatabaseTool, DatabaseConfig


@pytest.fixture
def basic_config():
    return DatabaseConfig(
        tool_name="test_sql_tool",
        tool_description="Test SQL tool",
        connection_string="postgresql://user:pass@host/db",
    )


@pytest.fixture
def tool_with_db(basic_config):
    """Create a SqlDatabaseTool with a mocked DatabaseService."""
    with patch("sam_sql_database_tool.tools.DatabaseService") as mock_db_cls:
        mock_service = MagicMock()
        mock_service.get_optimized_schema_for_llm.return_value = "schema"
        mock_db_cls.return_value = mock_service

        tool = SqlDatabaseTool(basic_config)
        tool.db_service = mock_service
        tool._connection_healthy = True
        tool._schema_context = "schema"
        yield tool, mock_service


def _capture_metrics():
    recorded = []

    def capture_record(duration, labels):
        recorded.append({"duration": duration, "labels": dict(labels)})

    mock_recorder = MagicMock()
    mock_recorder.record = capture_record
    mock_registry = MagicMock()
    mock_registry.get_recorder.return_value = mock_recorder
    return recorded, mock_registry


def _find_metric(recorded, **expected_labels):
    for m in recorded:
        if all(m["labels"].get(k) == v for k, v in expected_labels.items()):
            return m
    return None


@pytest.mark.asyncio
class TestSqlObservability:

    async def test_successful_query_records_metric(self, tool_with_db):
        tool, mock_service = tool_with_db
        mock_service.execute_query.return_value = [{"id": 1}]

        recorded, mock_registry = _capture_metrics()
        with patch(
            "solace_ai_connector.common.observability.api.MetricRegistry"
        ) as mock_reg_cls:
            mock_reg_cls.get_instance.return_value = mock_registry
            result = await tool._run_async_impl(args={"query": "SELECT 1"})

        assert "result" in result
        metric = _find_metric(recorded, **{"service.peer.name": "sql_database", "operation.name": "execute_query"})
        assert metric is not None, f"Expected metric not found in {recorded}"
        assert metric["labels"]["error.type"] == "none"
        assert metric["duration"] >= 0

    async def test_failed_query_records_error_metric(self, tool_with_db):
        tool, mock_service = tool_with_db
        from sqlalchemy.exc import SQLAlchemyError
        mock_service.execute_query.side_effect = SQLAlchemyError("connection reset")

        recorded, mock_registry = _capture_metrics()
        with patch(
            "solace_ai_connector.common.observability.api.MetricRegistry"
        ) as mock_reg_cls:
            mock_reg_cls.get_instance.return_value = mock_registry
            result = await tool._run_async_impl(args={"query": "SELECT 1"})

        assert "error" in result
        metric = _find_metric(recorded, **{"service.peer.name": "sql_database", "operation.name": "execute_query"})
        assert metric is not None, f"Expected metric not found in {recorded}"
        assert metric["labels"]["error.type"] == "database_error"
