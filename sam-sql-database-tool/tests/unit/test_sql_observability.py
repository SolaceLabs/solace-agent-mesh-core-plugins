"""Tests for SQL database connector observability instrumentation.

Tests verify that outbound.request.duration metrics are recorded with
correct labels when SQL queries are executed through SqlDatabaseTool.

Philosophy:
- Test behavior, not implementation details
- Minimize mocking — only mock MetricRegistry (the external boundary)
- Let real code execute (monitors, context managers)
- Verify observable outcomes (metrics recorded, labels correct)
"""

import pytest
from unittest.mock import MagicMock, patch

from sam_sql_database_tool.tools import SqlDatabaseTool, DatabaseConfig
from sam_sql_database_tool.observability import SqlRemoteMonitor


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
    """Set up MetricRegistry mock and return a list that captures recorded metrics."""
    recorded = []

    def capture_record(duration, labels):
        recorded.append({"duration": duration, "labels": dict(labels)})

    mock_recorder = MagicMock()
    mock_recorder.record = capture_record

    mock_registry = MagicMock()
    mock_registry.get_recorder.return_value = mock_recorder

    return recorded, mock_registry


def _find_metric(recorded, **expected_labels):
    """Find first metric matching all expected label values."""
    for m in recorded:
        if all(m["labels"].get(k) == v for k, v in expected_labels.items()):
            return m
    return None


@pytest.mark.asyncio
class TestSqlObservability:
    """Test outbound.request.duration metrics for SQL connector."""

    async def test_successful_query_records_metric(self, tool_with_db):
        """Verify metric is recorded with correct labels on successful query."""
        tool, mock_service = tool_with_db
        mock_service.execute_query.return_value = [{"id": 1}]

        recorded, mock_registry = _capture_metrics()
        with patch(
            "solace_ai_connector.common.observability.api.MetricRegistry"
        ) as mock_reg_cls:
            mock_reg_cls.get_instance.return_value = mock_registry

            result = await tool._run_async_impl(args={"query": "SELECT 1"})

        assert "result" in result
        metric = _find_metric(
            recorded,
            **{
                "service.peer.name": "sql_database",
                "operation.name": "execute_query",
            },
        )
        assert metric is not None, f"Expected metric not found in {recorded}"
        assert metric["labels"]["error.type"] == "none"
        assert metric["duration"] >= 0

    async def test_failed_query_records_error_metric(self, tool_with_db):
        """Verify metric captures error.type when query fails."""
        tool, mock_service = tool_with_db

        try:
            from sqlalchemy.exc import SQLAlchemyError

            mock_service.execute_query.side_effect = SQLAlchemyError(
                "connection reset"
            )
        except ImportError:
            pytest.skip("SQLAlchemy not available")

        recorded, mock_registry = _capture_metrics()
        with patch(
            "solace_ai_connector.common.observability.api.MetricRegistry"
        ) as mock_reg_cls:
            mock_reg_cls.get_instance.return_value = mock_registry

            result = await tool._run_async_impl(args={"query": "SELECT 1"})

        assert "error" in result
        metric = _find_metric(
            recorded,
            **{
                "service.peer.name": "sql_database",
                "operation.name": "execute_query",
            },
        )
        assert metric is not None, f"Expected metric not found in {recorded}"
        assert metric["labels"]["error.type"] == "database_error"

    async def test_timeout_error_categorized(self, tool_with_db):
        """Verify TimeoutError is categorized as 'timeout'."""
        tool, mock_service = tool_with_db
        mock_service.execute_query.side_effect = TimeoutError("query timed out")

        recorded, mock_registry = _capture_metrics()
        with patch(
            "solace_ai_connector.common.observability.api.MetricRegistry"
        ) as mock_reg_cls:
            mock_reg_cls.get_instance.return_value = mock_registry

            result = await tool._run_async_impl(args={"query": "SELECT 1"})

        assert "error" in result
        metric = _find_metric(
            recorded,
            **{
                "service.peer.name": "sql_database",
                "operation.name": "execute_query",
            },
        )
        assert metric is not None
        assert metric["labels"]["error.type"] == "timeout"

    async def test_multiple_queries_record_separate_metrics(self, tool_with_db):
        """Verify each query produces its own metric."""
        tool, mock_service = tool_with_db
        mock_service.execute_query.return_value = [{"id": 1}]

        recorded, mock_registry = _capture_metrics()
        with patch(
            "solace_ai_connector.common.observability.api.MetricRegistry"
        ) as mock_reg_cls:
            mock_reg_cls.get_instance.return_value = mock_registry

            await tool._run_async_impl(args={"query": "SELECT 1"})
            await tool._run_async_impl(args={"query": "SELECT 2"})
            await tool._run_async_impl(args={"query": "SELECT 3"})

        sql_metrics = [
            m
            for m in recorded
            if m["labels"].get("service.peer.name") == "sql_database"
        ]
        assert len(sql_metrics) >= 3


class TestSqlRemoteMonitorParseError:
    """Test error categorization for SQL-specific exceptions."""

    def test_sqlalchemy_error(self):
        try:
            from sqlalchemy.exc import SQLAlchemyError

            assert SqlRemoteMonitor.parse_error(SQLAlchemyError("test")) == "database_error"
        except ImportError:
            pytest.skip("SQLAlchemy not available")

    def test_timeout_error(self):
        assert SqlRemoteMonitor.parse_error(TimeoutError("test")) == "timeout"

    def test_connection_error(self):
        assert SqlRemoteMonitor.parse_error(ConnectionError("test")) == "connection_error"

    def test_generic_error(self):
        result = SqlRemoteMonitor.parse_error(ValueError("test"))
        assert result == "ValueError"
