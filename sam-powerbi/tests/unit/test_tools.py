"""Unit tests for sam_powerbi.tools."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from sam_powerbi.tools import (
    _require,
    _get_auth,
    _format_results_markdown,
    execute_powerbi_query,
    _auth_cache,
)
from sam_powerbi.auth import PowerBIAuthError, PowerBIAuthPending

MINIMAL_CFG = {
    "tenant_id": "tenant-123",
    "client_id": "client-456",
    "workspace_id": "ws-789",
    "dataset_id": "ds-abc",
}


@pytest.fixture(autouse=True)
def clear_auth_cache():
    _auth_cache.clear()
    yield
    _auth_cache.clear()


def _mock_http(status_code, json_data=None, text="", headers=None):
    """Build a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}
    resp.content = b""
    if json_data is not None:
        resp.json.return_value = json_data
        resp.content = str(json_data).encode()
    else:
        resp.json.side_effect = Exception("not JSON")
    return resp


class TestRequire:
    def test_returns_string_value(self):
        assert _require({"k": "val"}, "k") == "val"

    def test_coerces_int_to_str(self):
        assert _require({"k": 42}, "k") == "42"

    def test_raises_when_key_absent(self):
        with pytest.raises(ValueError, match=r"tool_config\['k'\] is required"):
            _require({}, "k")

    def test_raises_when_value_is_none(self):
        with pytest.raises(ValueError):
            _require({"k": None}, "k")

    def test_raises_when_value_is_empty_string(self):
        with pytest.raises(ValueError):
            _require({"k": ""}, "k")


class TestFormatResultsMarkdown:
    def test_empty_payload(self):
        r = _format_results_markdown({})
        assert r["row_count"] == 0
        assert r["truncated"] is False
        assert "empty" in r["markdown"].lower()

    def test_empty_results_list(self):
        r = _format_results_markdown({"results": []})
        assert r["row_count"] == 0

    def test_no_tables(self):
        r = _format_results_markdown({"results": [{"tables": []}]})
        assert r["row_count"] == 0
        assert "no tables" in r["markdown"].lower()

    def test_empty_rows(self):
        r = _format_results_markdown({"results": [{"tables": [{"rows": []}]}]})
        assert r["row_count"] == 0

    def test_single_row(self):
        payload = {"results": [{"tables": [{"rows": [{"Name": "Alice", "Score": 95}]}]}]}
        r = _format_results_markdown(payload)
        assert r["row_count"] == 1
        assert r["columns"] == ["Name", "Score"]
        assert "Alice" in r["markdown"]
        assert "95" in r["markdown"]
        assert r["truncated"] is False

    def test_multiple_rows_returns_correct_count(self):
        rows = [{"A": i, "B": f"v{i}"} for i in range(5)]
        r = _format_results_markdown({"results": [{"tables": [{"rows": rows}]}]})
        assert r["row_count"] == 5
        assert r["truncated"] is False

    def test_truncation_at_max_rows(self):
        rows = [{"X": i} for i in range(150)]
        r = _format_results_markdown({"results": [{"tables": [{"rows": rows}]}]}, max_rows=100)
        assert r["row_count"] == 150
        assert r["truncated"] is True
        assert "100 of 150" in r["markdown"]

    def test_no_truncation_exactly_at_limit(self):
        rows = [{"X": i} for i in range(100)]
        r = _format_results_markdown({"results": [{"tables": [{"rows": rows}]}]}, max_rows=100)
        assert r["truncated"] is False

    def test_null_values_rendered_as_empty_cell(self):
        rows = [{"A": None, "B": "present"}]
        r = _format_results_markdown({"results": [{"tables": [{"rows": rows}]}]})
        assert " | present" in r["markdown"]

    def test_float_uses_4g_format(self):
        rows = [{"Val": 123456.789}]
        r = _format_results_markdown({"results": [{"tables": [{"rows": rows}]}]})
        assert "1.235e+05" in r["markdown"]

    def test_markdown_contains_header_separator(self):
        rows = [{"Col1": "a", "Col2": "b"}]
        r = _format_results_markdown({"results": [{"tables": [{"rows": rows}]}]})
        assert any("---" in line for line in r["markdown"].split("\n"))

    def test_row_count_singular(self):
        rows = [{"X": 1}]
        r = _format_results_markdown({"results": [{"tables": [{"rows": rows}]}]})
        assert "(1 row)" in r["markdown"]

    def test_row_count_plural(self):
        rows = [{"X": 1}, {"X": 2}]
        r = _format_results_markdown({"results": [{"tables": [{"rows": rows}]}]})
        assert "(2 rows)" in r["markdown"]


class TestGetAuth:
    def test_creates_powerbi_auth_with_correct_args(self):
        with patch("sam_powerbi.tools.PowerBIAuth") as mock_cls:
            mock_cls.return_value = MagicMock()
            _get_auth(MINIMAL_CFG)
            mock_cls.assert_called_once_with(
                tenant_id="tenant-123",
                client_id="client-456",
                token_cache_path="/tmp/samv2/powerbi_msal_cache.json",
            )

    def test_caches_instance_for_same_key(self):
        with patch("sam_powerbi.tools.PowerBIAuth") as mock_cls:
            mock_cls.return_value = MagicMock()
            r1 = _get_auth(MINIMAL_CFG)
            r2 = _get_auth(MINIMAL_CFG)
            assert r1 is r2
            mock_cls.assert_called_once()

    def test_different_tenants_get_different_instances(self):
        with patch("sam_powerbi.tools.PowerBIAuth") as mock_cls:
            auth_a, auth_b = MagicMock(), MagicMock()
            mock_cls.side_effect = [auth_a, auth_b]
            r1 = _get_auth({**MINIMAL_CFG, "tenant_id": "tenant-A"})
            r2 = _get_auth({**MINIMAL_CFG, "tenant_id": "tenant-B"})
            assert r1 is auth_a
            assert r2 is auth_b

    def test_uses_custom_cache_path(self):
        cfg = {**MINIMAL_CFG, "token_cache_path": "/custom/path.json"}
        with patch("sam_powerbi.tools.PowerBIAuth") as mock_cls:
            mock_cls.return_value = MagicMock()
            _get_auth(cfg)
            mock_cls.assert_called_once_with(
                tenant_id="tenant-123",
                client_id="client-456",
                token_cache_path="/custom/path.json",
            )


class TestConfigValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("missing_key", ["tenant_id", "client_id", "workspace_id", "dataset_id"])
    async def test_missing_required_key(self, missing_key):
        cfg = {k: v for k, v in MINIMAL_CFG.items() if k != missing_key}
        r = await execute_powerbi_query("EVALUATE ROW(\"x\", 1)", tool_config=cfg)
        assert r["status"] == "error"
        assert r["error_code"] == "CONFIG_ERROR"
        assert missing_key in r["message"]

    @pytest.mark.asyncio
    async def test_none_tool_config_treated_as_empty(self):
        r = await execute_powerbi_query("EVALUATE ROW(\"x\", 1)", tool_config=None)
        assert r["error_code"] == "CONFIG_ERROR"


# ──────────────────────────────────────────────────────────────────────────────
# execute_powerbi_query — DAX validation
# ──────────────────────────────────────────────────────────────────────────────

class TestDaxValidation:
    @pytest.fixture(autouse=True)
    def mock_auth(self):
        with patch("sam_powerbi.tools._get_auth") as m:
            auth = MagicMock()
            auth.get_token_or_start_device_flow.return_value = "fake-token"
            m.return_value = auth
            yield m

    @pytest.mark.asyncio
    async def test_empty_query_is_rejected(self):
        r = await execute_powerbi_query("", tool_config=MINIMAL_CFG)
        assert r["status"] == "error"
        assert r["error_code"] == "DAX_ERROR"

    @pytest.mark.asyncio
    async def test_whitespace_only_query_is_rejected(self):
        r = await execute_powerbi_query("   \n\t  ", tool_config=MINIMAL_CFG)
        assert r["error_code"] == "DAX_ERROR"

    @pytest.mark.asyncio
    async def test_sql_query_is_rejected(self):
        r = await execute_powerbi_query("SELECT * FROM Table", tool_config=MINIMAL_CFG)
        assert r["error_code"] == "DAX_ERROR"
        assert "EVALUATE" in r["message"]

    @pytest.mark.asyncio
    async def test_evaluate_prefix_is_accepted(self):
        resp = _mock_http(200, json_data={"results": []})
        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.return_value = resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE 'Table'", tool_config=MINIMAL_CFG)
        assert r["status"] == "success"

    @pytest.mark.asyncio
    async def test_define_prefix_is_accepted(self):
        resp = _mock_http(200, json_data={"results": []})
        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.return_value = resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("DEFINE MEASURE t[x] = 1\nEVALUATE {1}", tool_config=MINIMAL_CFG)
        assert r["status"] == "success"

    @pytest.mark.asyncio
    async def test_evaluate_is_case_insensitive(self):
        resp = _mock_http(200, json_data={"results": []})
        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.return_value = resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("evaluate 'Table'", tool_config=MINIMAL_CFG)
        assert r["status"] == "success"


# ──────────────────────────────────────────────────────────────────────────────
# execute_powerbi_query — auth flow
# ──────────────────────────────────────────────────────────────────────────────

class TestAuthFlow:
    @pytest.mark.asyncio
    async def test_auth_pending_returns_auth_required(self):
        pending = PowerBIAuthPending(
            verification_uri="https://aka.ms/devicelogin",
            user_code="ABC123",
            expires_in=900,
            message="Go sign in",
        )
        with patch("sam_powerbi.tools._get_auth") as m:
            auth = MagicMock()
            auth.get_token_or_start_device_flow.side_effect = pending
            m.return_value = auth
            r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        assert r["status"] == "error"
        assert r["error_code"] == "AUTH_REQUIRED"
        assert r["user_code"] == "ABC123"
        assert r["verification_uri"] == "https://aka.ms/devicelogin"
        assert r["expires_in_seconds"] == 900

    @pytest.mark.asyncio
    async def test_auth_error_returns_auth_error(self):
        with patch("sam_powerbi.tools._get_auth") as m:
            auth = MagicMock()
            auth.get_token_or_start_device_flow.side_effect = PowerBIAuthError("token expired")
            m.return_value = auth
            r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        assert r["status"] == "error"
        assert r["error_code"] == "AUTH_ERROR"
        assert "token expired" in r["message"]

    @pytest.mark.asyncio
    async def test_401_triggers_force_reauth_and_retries(self):
        resp_401 = _mock_http(401, text="Unauthorized")
        resp_200 = _mock_http(
            200,
            json_data={"results": [{"tables": [{"rows": [{"A": 1}]}]}]},
        )
        resp_200.content = b"x"

        with patch("sam_powerbi.tools._get_auth") as m:
            auth = MagicMock()
            auth.get_token_or_start_device_flow.return_value = "token"
            m.return_value = auth

            with patch("httpx.AsyncClient") as mock_cls:
                inst = AsyncMock()
                inst.post.side_effect = [resp_401, resp_200]
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        auth.force_reauth.assert_called_once()
        assert r["status"] == "success"

    @pytest.mark.asyncio
    async def test_401_retry_triggers_new_device_flow(self):
        pending = PowerBIAuthPending(
            verification_uri="https://aka.ms/devicelogin",
            user_code="XYZ",
            expires_in=900,
            message="Sign in",
        )
        resp_401 = _mock_http(401)

        with patch("sam_powerbi.tools._get_auth") as m:
            auth = MagicMock()
            # First call returns token, second (after force_reauth) raises pending
            auth.get_token_or_start_device_flow.side_effect = ["token", pending]
            m.return_value = auth

            with patch("httpx.AsyncClient") as mock_cls:
                inst = AsyncMock()
                inst.post.return_value = resp_401
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        assert r["error_code"] == "AUTH_REQUIRED"

    @pytest.mark.asyncio
    async def test_401_retry_triggers_auth_error(self):
        resp_401 = _mock_http(401)

        with patch("sam_powerbi.tools._get_auth") as m:
            auth = MagicMock()
            # First call returns token, second (after force_reauth) raises terminal auth error
            auth.get_token_or_start_device_flow.side_effect = [
                "token",
                PowerBIAuthError("re-auth failed"),
            ]
            m.return_value = auth

            with patch("httpx.AsyncClient") as mock_cls:
                inst = AsyncMock()
                inst.post.return_value = resp_401
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        assert r["error_code"] == "AUTH_ERROR"
        assert "re-auth failed" in r["message"]


# ──────────────────────────────────────────────────────────────────────────────
# execute_powerbi_query — HTTP response handling
# ──────────────────────────────────────────────────────────────────────────────

class TestHTTPResponseHandling:
    @pytest.fixture(autouse=True)
    def mock_auth(self):
        with patch("sam_powerbi.tools._get_auth") as m:
            auth = MagicMock()
            auth.get_token_or_start_device_flow.return_value = "fake-token"
            m.return_value = auth
            yield auth

    @pytest.mark.asyncio
    async def test_200_success_with_rows(self):
        payload = {"results": [{"tables": [{"rows": [{"Name": "Alice"}, {"Name": "Bob"}]}]}]}
        resp = _mock_http(200, json_data=payload)
        resp.content = b"x" * 50

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.return_value = resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        assert r["status"] == "success"
        assert r["row_count"] == 2
        assert r["columns"] == ["Name"]
        assert "Alice" in r["results_markdown"]
        assert r["truncated"] is False

    @pytest.mark.asyncio
    async def test_200_with_error_field_in_payload(self):
        payload = {"error": {"message": "Invalid DAX expression"}}
        resp = _mock_http(200, json_data=payload)

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.return_value = resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE bad", tool_config=MINIMAL_CFG)

        assert r["error_code"] == "DAX_ERROR"
        assert "Invalid DAX expression" in r["message"]

    @pytest.mark.asyncio
    async def test_200_non_json_body(self):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.content = b"not-json"
        resp.json.side_effect = Exception("decode error")

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.return_value = resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        assert r["error_code"] == "PARSE_ERROR"

    @pytest.mark.asyncio
    async def test_400_structured_error_body(self):
        err_body = {
            "error": {
                "code": "SyntaxError",
                "message": "Column not found",
                "details": [{"code": "D1", "message": "Unknown column X"}],
            }
        }
        resp = _mock_http(400, json_data=err_body)

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.return_value = resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE bad", tool_config=MINIMAL_CFG)

        assert r["error_code"] == "DAX_ERROR"
        assert "SyntaxError" in r["message"]
        assert "Column not found" in r["message"]
        assert "D1: Unknown column X" in r["message"]

    @pytest.mark.asyncio
    async def test_400_non_json_body(self):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 400
        resp.text = "Bad Request plain text"
        resp.json.side_effect = Exception("not JSON")

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.return_value = resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE bad", tool_config=MINIMAL_CFG)

        assert r["error_code"] == "DAX_ERROR"

    @pytest.mark.asyncio
    async def test_429_rate_limit(self):
        resp = _mock_http(429, text="Too Many Requests")
        resp.headers = {"Retry-After": "60"}

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.return_value = resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        assert r["error_code"] == "RATE_LIMIT"
        assert r["retry_after"] == "60"

    @pytest.mark.asyncio
    async def test_503_rest_error(self):
        resp = _mock_http(503, text="Service Unavailable")

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.return_value = resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        assert r["error_code"] == "REST_ERROR"
        assert "503" in r["message"]

    @pytest.mark.asyncio
    async def test_timeout_exception(self):
        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.side_effect = httpx.TimeoutException("timed out")
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        assert r["error_code"] == "TIMEOUT"
        assert "30" in r["message"]  # default timeout in message

    @pytest.mark.asyncio
    async def test_custom_timeout_in_error_message(self):
        cfg = {**MINIMAL_CFG, "rest_timeout_seconds": "5"}
        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.side_effect = httpx.TimeoutException("timed out")
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE 'T'", tool_config=cfg)

        assert "5" in r["message"]

    @pytest.mark.asyncio
    async def test_network_error(self):
        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.side_effect = httpx.ConnectError("connection refused")
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        assert r["error_code"] == "NETWORK_ERROR"

    @pytest.mark.asyncio
    async def test_truncated_result_reflected_in_response(self):
        rows = [{"X": i} for i in range(150)]
        payload = {"results": [{"tables": [{"rows": rows}]}]}
        resp = _mock_http(200, json_data=payload)
        resp.content = b"x" * 100

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.return_value = resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        assert r["status"] == "success"
        assert r["truncated"] is True
        assert "(truncated)" in r["message"]

    @pytest.mark.asyncio
    async def test_custom_rest_timeout_passed_to_httpx(self):
        cfg = {**MINIMAL_CFG, "rest_timeout_seconds": "7"}
        resp = _mock_http(200, json_data={"results": []})

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.return_value = resp
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await execute_powerbi_query("EVALUATE 'T'", tool_config=cfg)

        mock_cls.assert_called_with(timeout=7.0)

    @pytest.mark.asyncio
    async def test_unexpected_exception(self):
        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.post.side_effect = RuntimeError("something exploded")
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=inst)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            r = await execute_powerbi_query("EVALUATE 'T'", tool_config=MINIMAL_CFG)

        assert r["error_code"] == "UNEXPECTED_ERROR"
        assert "RuntimeError" in r["message"]
        assert "something exploded" in r["message"]
