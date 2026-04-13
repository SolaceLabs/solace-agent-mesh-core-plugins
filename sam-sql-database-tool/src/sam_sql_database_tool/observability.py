"""Observability monitors for SQL database connector outbound calls."""

from solace_ai_connector.common.observability.monitors.base import MonitorInstance
from solace_ai_connector.common.observability.monitors.remote import (
    RemoteRequestMonitor,
)


class SqlRemoteMonitor(RemoteRequestMonitor):
    """Monitor for outbound SQL database calls.

    Maps to: outbound.request.duration histogram
    Labels: service.peer.name="sql_database", operation.name, error.type
    """

    @staticmethod
    def parse_error(exc: Exception) -> str:
        """Map SQL-specific exceptions to error categories."""
        try:
            from sqlalchemy.exc import SQLAlchemyError

            if isinstance(exc, SQLAlchemyError):
                return "database_error"
        except ImportError:
            pass
        return RemoteRequestMonitor.parse_error(exc)

    @classmethod
    def execute_query(cls) -> MonitorInstance:
        """Create monitor instance for SQL query execution."""
        return MonitorInstance(
            monitor_type=cls.monitor_type,
            labels={
                "service.peer.name": "sql_database",
                "operation.name": "execute_query",
            },
            error_parser=cls.parse_error,
        )
