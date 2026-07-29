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

Each SAM user gets their own delegated PowerBI token, cached in its own
file derived from ``token_cache_path`` and the caller's ``user_id`` (from
``tool_context.session.user_id``). This isolation is only as
good as the gateway's identity: it requires the gateway to supply a real
per-human user_id (e.g. Slack does this by default; REST/webhook/event-mesh
gateways only do so if authentication is enforced and configured with a
per-user claim — otherwise every caller collapses onto the same generic
identity and shares one cached token). Check your gateway's auth config.
"""

from __future__ import annotations

import hashlib
import logging
import os
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

ANONYMOUS_USER_ID = "anonymous"

# One PowerBIAuth per (tenant, client, per-user cache_path) tuple. Built
# lazily on first tool call so that a SAM install missing PowerBI env vars
# still starts up cleanly and only fails when the tool is actually invoked.
_auth_cache: Dict[tuple, PowerBIAuth] = {}
_auth_lock = threading.Lock()


def _user_cache_path(base_path: str, user_id: str) -> str:
    """Derive a per-user MSAL cache file path from the configured base path."""
    root, ext = os.path.splitext(base_path)
    user_key = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
    return f"{root}.{user_key}{ext}"


def _require(cfg: Dict[str, Any], key: str) -> str:
    val = cfg.get(key)
    if not val:
        raise ValueError(
            f"sam_powerbi.execute_powerbi_query: tool_config['{key}'] is required"
        )
    return str(val)


def _get_auth(cfg: Dict[str, Any], user_id: str) -> PowerBIAuth:
    tenant = _require(cfg, "tenant_id")
    client = _require(cfg, "client_id")
    base_path = cfg.get("token_cache_path") or "/tmp/samv2/powerbi_msal_cache.json"
    cache_path = _user_cache_path(base_path, user_id)
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


def _powerbi_error_info(resp: httpx.Response) -> Optional[str]:
    """Extract PowerBI's own diagnostic header, when present.

    PowerBI's REST API often explains *why* a request failed (expired token,
    missing consent, no workspace access, etc.) in this header even when the
    HTTP status code alone (e.g. a bare 401) doesn't say.
    """
    return resp.headers.get("X-PowerBI-Error-Info") or None


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


async def _send_query_with_reauth(
    auth: PowerBIAuth, endpoint: str, body: Dict[str, Any], token: str, timeout: float
) -> tuple[Optional[httpx.Response], Optional[Dict[str, Any]]]:
    """POST the query; on 401, force reauth and retry once.

    Returns (response, None) on any non-terminal outcome (including a second
    401 that the caller's status dispatch will report), or (None, error_dict)
    if reauth itself failed.
    """

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

    resp = await _post(token)
    if resp.status_code != 401:
        return resp, None

    error_info = _powerbi_error_info(resp)
    logger.info(
        "[sam_powerbi] 401 — forcing re-authentication%s",
        f" (X-PowerBI-Error-Info: {error_info})" if error_info else "",
    )
    auth.force_reauth()
    token, err = _get_token(auth, "Re-auth failed")
    if err:
        if error_info:
            err["message"] = (
                f"PowerBI rejected the previous token (X-PowerBI-Error-Info: "
                f"{error_info}) before this new sign-in was requested — signing in "
                f"again will not help if that reason is a permissions/access issue "
                f"rather than an expired token. {err['message']}"
            )
            err["powerbi_error_info"] = error_info
        return None, err

    resp = await _post(token)
    if resp.status_code == 401:
        error_info = _powerbi_error_info(resp)
        logger.warning(
            "[sam_powerbi] Still 401 after re-authentication%s",
            f" — X-PowerBI-Error-Info: {error_info}" if error_info else "",
        )
        return None, {
            "status": "error",
            "error_code": "AUTH_ERROR",
            "message": (
                "PowerBI rejected the freshly-acquired token (401 persists after "
                "re-authentication). This usually means the AAD app registration is "
                "missing consented PowerBI API permissions, or the signed-in user "
                "lacks access to this workspace/dataset."
                + (f" PowerBI-Error-Info: {error_info}" if error_info else "")
            ),
            "powerbi_error_info": error_info,
        }
    return resp, None


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


def _dispatch_response(resp: httpx.Response) -> Dict[str, Any]:
    """Map a non-retried HTTP response to the tool's result dict, by status code."""
    if resp.status_code == 200:
        return _handle_200_response(resp)
    if resp.status_code == 400:
        return _handle_400_response(resp)
    error_info = _powerbi_error_info(resp)
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After", "unknown")
        return {
            "status": "error",
            "error_code": "RATE_LIMIT",
            "message": (
                f"PowerBI REST API rate limit exceeded (Retry-After: {retry_after}s). Wait before retrying."
                + (f" X-PowerBI-Error-Info: {error_info}" if error_info else "")
            ),
            "retry_after": retry_after,
            "powerbi_error_info": error_info,
        }
    return {
        "status": "error",
        "error_code": "REST_ERROR",
        "message": (
            f"HTTP {resp.status_code}: {resp.text[:500]}"
            + (f" | X-PowerBI-Error-Info: {error_info}" if error_info else "")
        ),
        "http_status": resp.status_code,
        "powerbi_error_info": error_info,
    }


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


def _resolve_user_id(tool_context: Optional[ToolContext]) -> str:
    """Resolve the per-user cache key from tool_context, falling back to a shared anonymous identity."""
    if tool_context is None:
        logger.warning(
            "[sam_powerbi] No tool_context — falling back to shared anonymous cache; per-user isolation is disabled"
        )
        return ANONYMOUS_USER_ID
    return tool_context.session.user_id


def _validate_request_config(cfg: Dict[str, Any]) -> tuple[Optional[tuple[str, str, float]], Optional[Dict[str, Any]]]:
    """Validate tool_config. Returns ((workspace_id, dataset_id, timeout), None) or (None, error_dict)."""
    try:
        _require(cfg, "tenant_id")
        _require(cfg, "client_id")
        workspace_id = _require(cfg, "workspace_id")
        dataset_id = _require(cfg, "dataset_id")
    except ValueError as e:
        logger.error("[sam_powerbi] %s", e)
        return None, {"status": "error", "error_code": "CONFIG_ERROR", "message": str(e)}
    timeout = float(cfg.get("rest_timeout_seconds") or 30)
    return (workspace_id, dataset_id, timeout), None


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

    config, err = _validate_request_config(cfg)
    if err:
        return err
    workspace_id, dataset_id, timeout = config

    dax, err = _validate_dax(dax_query)
    if err:
        return err

    user_id = _resolve_user_id(tool_context)

    auth = _get_auth(cfg, user_id)
    token, err = _get_token(auth, "Failed to acquire PowerBI token")
    if err:
        return err

    endpoint = f"{POWERBI_REST_BASE}/groups/{workspace_id}/datasets/{dataset_id}/executeQueries"
    body = {
        "queries": [{"query": dax}],
        "serializerSettings": {"includeNulls": True},
    }

    try:
        resp, err = await _send_query_with_reauth(auth, endpoint, body, token, timeout)
        if err:
            return err

        return _dispatch_response(resp)

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
