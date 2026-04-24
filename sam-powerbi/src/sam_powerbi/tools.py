"""
PowerBI executeQueries tool for Solace Agent Mesh.

Exposes ``execute_powerbi_query`` — an async tool that runs a DAX query
against a PowerBI semantic model via the REST API, using delegated
(on-behalf-of-user) OAuth2 access through MSAL device-code flow.

tool_config (populated from the agent YAML ``tool_config:`` block):
    tenant_id: Azure AD tenant GUID (required)
    client_id: AAD public-client app GUID with device-code enabled (required)
    workspace_id: PowerBI workspace GUID (required)
    dataset_id: PowerBI semantic-model GUID (required)
    rest_timeout_seconds: per-request HTTP timeout (default 30)
    token_cache_path: MSAL serializable cache file path
                      (default /tmp/samv2/powerbi_msal_cache.json)
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

import httpx
from google.adk.tools import ToolContext

from .auth import (
    PowerBIAuth,
    PowerBIAuthError,
    PowerBIAuthPending,
)

logger = logging.getLogger(__name__)

POWERBI_REST_BASE = "https://api.powerbi.com/v1.0/myorg"

# One PowerBIAuth per (tenant, client, cache_path) tuple. Built lazily on
# first tool call so that a SAM install missing PowerBI env vars still
# starts up cleanly and only fails when the tool is actually invoked.
_auth_cache: Dict[tuple, PowerBIAuth] = {}
_auth_lock = threading.Lock()


def _require(cfg: Dict[str, Any], key: str) -> str:
    val = cfg.get(key)
    if not val:
        raise ValueError(
            f"sam_powerbi.execute_powerbi_query: tool_config['{key}'] is required"
        )
    return str(val)


def _get_auth(cfg: Dict[str, Any]) -> PowerBIAuth:
    tenant = _require(cfg, "tenant_id")
    client = _require(cfg, "client_id")
    cache_path = cfg.get("token_cache_path") or "/tmp/samv2/powerbi_msal_cache.json"
    key = (tenant, client, cache_path)
    with _auth_lock:
        auth = _auth_cache.get(key)
        if auth is None:
            auth = PowerBIAuth(
                tenant_id=tenant,
                client_id=client,
                token_cache_path=cache_path,
            )
            _auth_cache[key] = auth
        return auth


def _format_cell_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _format_results_markdown(payload: Dict[str, Any], max_rows: int = 100) -> Dict[str, Any]:
    """Render an executeQueries response as a markdown table + metadata."""
    results = payload.get("results") or []
    if not results:
        return {"markdown": "(empty result)", "row_count": 0, "columns": [], "truncated": False}

    tables = results[0].get("tables") or []
    if not tables:
        return {"markdown": "(no tables in result)", "row_count": 0, "columns": [], "truncated": False}

    rows = tables[0].get("rows") or []
    if not rows:
        return {"markdown": "(0 rows returned)", "row_count": 0, "columns": [], "truncated": False}

    headers = list(rows[0].keys())
    lines = [" | ".join(headers), " | ".join("---" for _ in headers)]
    for row in rows[:max_rows]:
        lines.append(" | ".join(_format_cell_value(row.get(h)) for h in headers))

    truncated = len(rows) > max_rows
    lines.append("")
    if truncated:
        lines.append(f"(Showing {max_rows} of {len(rows)} rows)")
    else:
        lines.append(f"({len(rows)} row{'s' if len(rows) != 1 else ''})")

    return {
        "markdown": "\n".join(lines),
        "row_count": len(rows),
        "columns": headers,
        "truncated": truncated,
    }


def _auth_required_response(pending: PowerBIAuthPending) -> Dict[str, Any]:
    return {
        "status": "error",
        "error_code": "AUTH_REQUIRED",
        "message": (
            f"Sign in to PowerBI required. Open {pending.verification_uri} "
            f"and enter code {pending.user_code}. Then ask your question again."
        ),
        "verification_uri": pending.verification_uri,
        "user_code": pending.user_code,
        "expires_in_seconds": pending.expires_in,
    }


def _get_token(
    auth: PowerBIAuth, error_prefix: str
) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Acquire a token; return (token, None) on success or (None, error_dict) on failure."""
    try:
        return auth.get_token_or_start_device_flow(), None
    except PowerBIAuthPending as pending:
        return None, _auth_required_response(pending)
    except PowerBIAuthError as e:
        return None, {"status": "error", "error_code": "AUTH_ERROR", "message": f"{error_prefix}: {e}"}


def _handle_200_response(resp: httpx.Response) -> Dict[str, Any]:
    """Parse and format a 200 executeQueries response."""
    try:
        payload = resp.json()
    except Exception as e:
        return {"status": "error", "error_code": "PARSE_ERROR", "message": f"Response was 200 but body was not JSON: {e}"}
    if payload.get("error"):
        err = payload["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        return {"status": "error", "error_code": "DAX_ERROR", "message": msg or "Unknown DAX error in payload"}
    formatted = _format_results_markdown(payload)
    logger.info("[sam_powerbi] Query OK — %d row(s), %d byte(s)", formatted["row_count"], len(resp.content))
    return {
        "status": "success",
        "message": f"Query returned {formatted['row_count']} row(s)" + (" (truncated)" if formatted["truncated"] else ""),
        "results_markdown": formatted["markdown"],
        "row_count": formatted["row_count"],
        "columns": formatted["columns"],
        "truncated": formatted["truncated"],
    }


def _handle_400_response(resp: httpx.Response) -> Dict[str, Any]:
    """Parse a 400 DAX error response."""
    try:
        err_body = resp.json()
        err = err_body.get("error", {})
        code = err.get("code", "BadRequest")
        msg = err.get("message", resp.text[:500])
        details = err.get("details") or []
        detail_msg = ""
        if details:
            detail_msg = " | " + " | ".join(
                f"{d.get('code', '?')}: {d.get('message', '')}" for d in details
            )
        return {
            "status": "error",
            "error_code": "DAX_ERROR",
            "message": f"[{code}] {msg}{detail_msg}. Please correct the DAX query and retry.",
        }
    except Exception:
        return {"status": "error", "error_code": "DAX_ERROR", "message": resp.text[:500]}


def _validate_dax(dax_query: str) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Validate and normalise a DAX query. Returns (dax, None) or (None, error_dict)."""
    if not dax_query or not dax_query.strip():
        return None, {
            "status": "error",
            "error_code": "DAX_ERROR",
            "message": "Empty query. Provide a DAX expression starting with EVALUATE.",
        }
    dax = dax_query.strip()
    if not dax.upper().startswith(("EVALUATE", "DEFINE")):
        return None, {
            "status": "error",
            "error_code": "DAX_ERROR",
            "message": (
                "DAX queries must start with EVALUATE (or DEFINE ... EVALUATE). "
                "Example: EVALUATE ROW(\"Total\", COUNTROWS('Fact GE Losses'))"
            ),
        }
    return dax, None


async def execute_powerbi_query(
    dax_query: str,
    tool_context: Optional[ToolContext] = None,
    tool_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a DAX query against the configured PowerBI semantic model via the
    REST executeQueries endpoint.

    Args:
        dax_query: DAX query string. Must start with EVALUATE (or DEFINE ... EVALUATE).

    Returns:
        On success, a dict with status="success", results_markdown, row_count,
        columns, truncated.

        On failure, a dict with status="error" and an error_code:
            AUTH_REQUIRED — first call; user must sign in via the included
                            verification_uri + user_code.
            AUTH_ERROR    — token acquisition failed terminally.
            DAX_ERROR     — 400 from PowerBI or payload.error set. Read the
                            message and correct the DAX.
            RATE_LIMIT    — 429; retry_after included.
            TIMEOUT       — request exceeded rest_timeout_seconds.
            NETWORK_ERROR — httpx transport error.
            PARSE_ERROR   — 200 but body was not JSON.
            REST_ERROR    — any other non-200 HTTP status.
            CONFIG_ERROR  — tool_config missing required value.
    """
    cfg = tool_config or {}

    try:
        _require(cfg, "tenant_id")
        _require(cfg, "client_id")
        workspace_id = _require(cfg, "workspace_id")
        dataset_id = _require(cfg, "dataset_id")
    except ValueError as e:
        logger.error("[sam_powerbi] %s", e)
        return {"status": "error", "error_code": "CONFIG_ERROR", "message": str(e)}

    timeout = float(cfg.get("rest_timeout_seconds") or 30)

    dax, err = _validate_dax(dax_query)
    if err:
        return err

    auth = _get_auth(cfg)
    token, err = _get_token(auth, "Failed to acquire PowerBI token")
    if err:
        return err

    endpoint = f"{POWERBI_REST_BASE}/groups/{workspace_id}/datasets/{dataset_id}/executeQueries"
    body = {
        "queries": [{"query": dax}],
        "serializerSettings": {"includeNulls": True},
    }

    async def _post(bearer: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=timeout) as client_http:
            return await client_http.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "Content-Type": "application/json",
                },
                json=body,
            )

    try:
        resp = await _post(token)

        if resp.status_code == 401:
            logger.info("[sam_powerbi] 401 — forcing re-authentication")
            auth.force_reauth()
            token, err = _get_token(auth, "Re-auth failed")
            if err:
                return err
            resp = await _post(token)

        if resp.status_code == 200:
            return _handle_200_response(resp)
        if resp.status_code == 400:
            return _handle_400_response(resp)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "unknown")
            return {
                "status": "error",
                "error_code": "RATE_LIMIT",
                "message": f"PowerBI REST API rate limit exceeded (Retry-After: {retry_after}s). Wait before retrying.",
                "retry_after": retry_after,
            }
        return {
            "status": "error",
            "error_code": "REST_ERROR",
            "message": f"HTTP {resp.status_code}: {resp.text[:500]}",
            "http_status": resp.status_code,
        }

    except httpx.TimeoutException:
        return {
            "status": "error",
            "error_code": "TIMEOUT",
            "message": f"PowerBI query exceeded {timeout:.0f}s. Try reducing scope, adding filters, or using TOPN to limit rows.",
        }
    except httpx.RequestError as e:
        logger.error("[sam_powerbi] Request error: %s", e)
        return {"status": "error", "error_code": "NETWORK_ERROR", "message": str(e)}
    except Exception as e:
        logger.exception("[sam_powerbi] Unexpected error")
        return {"status": "error", "error_code": "UNEXPECTED_ERROR", "message": f"{type(e).__name__}: {e}"}
