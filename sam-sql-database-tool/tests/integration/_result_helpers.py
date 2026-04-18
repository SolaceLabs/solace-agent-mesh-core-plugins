"""Helpers for asserting against ToolResult shapes in integration tests."""

import csv
import io
from typing import Any, Dict, List

from solace_agent_mesh.agent.tools.tool_result import ToolResult


def is_error(result: Any) -> bool:
    assert isinstance(result, ToolResult), f"Expected ToolResult, got {type(result)!r}"
    return result.status == "error"


def error_message(result: ToolResult) -> str:
    assert isinstance(result, ToolResult)
    return result.message or ""


def row_count(result: ToolResult) -> int:
    """Row count from the inline summary, or 0 for empty / non-row results."""
    assert isinstance(result, ToolResult)
    if result.data and "row_count" in result.data:
        return int(result.data["row_count"])
    return 0


def get_rows(result: ToolResult) -> List[Dict[str, str]]:
    """Return full row set by parsing the CSV DataObject.

    All values are strings (CSV-encoded); callers should cast as needed.
    """
    assert isinstance(result, ToolResult)
    if not result.data_objects:
        # No rows were returned (empty or non-row result)
        if result.data and "preview_rows" in result.data:
            return [dict(r) for r in result.data["preview_rows"]]
        return []
    obj = result.data_objects[0]
    reader = csv.DictReader(io.StringIO(obj.content))
    return [dict(row) for row in reader]


def affected_rows(result: ToolResult) -> int:
    """Affected rows for INSERT/UPDATE/DELETE style queries."""
    assert isinstance(result, ToolResult)
    if result.data and "affected_rows" in result.data:
        return int(result.data["affected_rows"])
    return 0
