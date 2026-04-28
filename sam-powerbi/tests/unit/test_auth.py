"""Unit tests for sam_powerbi.auth."""
import time
import pytest
from unittest.mock import MagicMock, patch

from sam_powerbi.auth import PowerBIAuth, PowerBIAuthError, PowerBIAuthPending, POWERBI_SCOPE


def _make_auth(tenant="t-id", client="c-id", cache_path="/tmp/test_cache.json"):
    """Create a PowerBIAuth with a fully mocked MSAL application."""
    mock_app = MagicMock()
    mock_cache = MagicMock()
    mock_cache.has_state_changed = False

    with patch("msal.SerializableTokenCache", return_value=mock_cache), \
         patch("msal.PublicClientApplication", return_value=mock_app), \
         patch("os.path.exists", return_value=False):
        auth = PowerBIAuth(tenant_id=tenant, client_id=client, token_cache_path=cache_path)

    auth._app = mock_app
    auth._cache = mock_cache
    return auth, mock_app, mock_cache


def _fake_device_flow(**overrides):
    base = {
        "user_code": "ABC123",
        "verification_uri": "https://aka.ms/devicelogin",
        "expires_in": 900,
        "expires_at": time.time() + 900,
        "interval": 5,
        "message": "Open the URL and enter the code",
    }
    return {**base, **overrides}


class TestConstructor:
    def test_raises_when_tenant_id_is_empty(self):
        with pytest.raises(ValueError, match="tenant_id"):
            with patch("msal.SerializableTokenCache"), patch("msal.PublicClientApplication"):
                PowerBIAuth(tenant_id="", client_id="client")

    def test_raises_when_client_id_is_empty(self):
        with pytest.raises(ValueError, match="client_id"):
            with patch("msal.SerializableTokenCache"), patch("msal.PublicClientApplication"):
                PowerBIAuth(tenant_id="tenant", client_id="")

    def test_authority_constructed_from_tenant(self):
        auth, _, _ = _make_auth(tenant="my-tenant")
        assert auth._authority == "https://login.microsoftonline.com/my-tenant"

    def test_stores_config_values(self):
        auth, _, _ = _make_auth(tenant="t", client="c", cache_path="/p/cache.json")
        assert auth._tenant_id == "t"
        assert auth._client_id == "c"
        assert auth._token_cache_path == "/p/cache.json"

    def test_loads_existing_cache_file(self, tmp_path):
        cache_content = '{"AccessToken": {}}'
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(cache_content)

        mock_cache = MagicMock()
        mock_cache.has_state_changed = False

        with patch("msal.SerializableTokenCache", return_value=mock_cache), \
             patch("msal.PublicClientApplication"):
            PowerBIAuth(tenant_id="t", client_id="c", token_cache_path=str(cache_file))

        mock_cache.deserialize.assert_called_once_with(cache_content)

    def test_proceeds_when_cache_file_absent(self, tmp_path):
        mock_cache = MagicMock()
        with patch("msal.SerializableTokenCache", return_value=mock_cache), \
             patch("msal.PublicClientApplication"):
            auth = PowerBIAuth(
                tenant_id="t",
                client_id="c",
                token_cache_path=str(tmp_path / "missing.json"),
            )
        mock_cache.deserialize.assert_not_called()
        assert auth._pending_flow is None

    def test_bad_cache_file_logs_warning_but_continues(self, tmp_path):
        cache_file = tmp_path / "bad.json"
        cache_file.write_text("not-valid-cache")

        mock_cache = MagicMock()
        mock_cache.deserialize.side_effect = Exception("corrupt")

        with patch("msal.SerializableTokenCache", return_value=mock_cache), \
             patch("msal.PublicClientApplication"):
            auth = PowerBIAuth(tenant_id="t", client_id="c", token_cache_path=str(cache_file))

        assert auth._pending_flow is None


class TestGetTokenSilent:
    def test_returns_none_when_no_accounts(self):
        auth, mock_app, _ = _make_auth()
        mock_app.get_accounts.return_value = []
        assert auth.get_token_silent() is None

    def test_returns_token_when_silent_refresh_succeeds(self):
        auth, mock_app, mock_cache = _make_auth()
        account = {"username": "user@example.com"}
        mock_app.get_accounts.return_value = [account]
        mock_app.acquire_token_silent.return_value = {"access_token": "silent-token"}
        mock_cache.has_state_changed = False

        result = auth.get_token_silent()

        assert result == "silent-token"
        mock_app.acquire_token_silent.assert_called_once_with(
            [POWERBI_SCOPE], account=account
        )

    def test_returns_none_when_silent_refresh_returns_no_token(self):
        auth, mock_app, _ = _make_auth()
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_app.acquire_token_silent.return_value = {"error": "no_token"}

        assert auth.get_token_silent() is None

    def test_saves_cache_after_successful_refresh(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        auth, mock_app, mock_cache = _make_auth(cache_path=str(cache_file))
        mock_app.get_accounts.return_value = [{"username": "u"}]
        mock_app.acquire_token_silent.return_value = {"access_token": "t"}
        mock_cache.has_state_changed = True
        mock_cache.serialize.return_value = '{"state": "new"}'

        auth.get_token_silent()

        mock_cache.serialize.assert_called()


class TestGetTokenOrStartDeviceFlow:
    def test_returns_token_via_silent_path(self):
        auth, mock_app, _ = _make_auth()
        mock_app.get_accounts.return_value = [{"username": "user"}]
        mock_app.acquire_token_silent.return_value = {"access_token": "cached-token"}

        result = auth.get_token_or_start_device_flow()

        assert result == "cached-token"
        mock_app.initiate_device_flow.assert_not_called()

    def test_starts_device_flow_when_no_cached_token(self):
        auth, mock_app, _ = _make_auth()
        mock_app.get_accounts.return_value = []
        mock_app.initiate_device_flow.return_value = _fake_device_flow()

        with patch("sam_powerbi.auth.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            with pytest.raises(PowerBIAuthPending) as exc_info:
                auth.get_token_or_start_device_flow()

        exc = exc_info.value
        assert exc.user_code == "ABC123"
        assert exc.verification_uri == "https://aka.ms/devicelogin"
        assert exc.expires_in == 900

    def test_raises_pending_with_correct_message_fields(self):
        auth, mock_app, _ = _make_auth()
        mock_app.get_accounts.return_value = []
        mock_app.initiate_device_flow.return_value = _fake_device_flow(
            user_code="XYZ99",
            verification_uri="https://login.example.com/device",
            expires_in=600,
            message="Custom message",
        )

        with patch("sam_powerbi.auth.threading.Thread"):
            with pytest.raises(PowerBIAuthPending) as exc_info:
                auth.get_token_or_start_device_flow()

        exc = exc_info.value
        assert exc.user_code == "XYZ99"
        assert exc.verification_uri == "https://login.example.com/device"
        assert exc.expires_in == 600
        assert exc.message == "Custom message"

    def test_second_call_while_flow_in_flight_re_raises_same_pending(self):
        auth, mock_app, _ = _make_auth()
        mock_app.get_accounts.return_value = []
        mock_app.initiate_device_flow.return_value = _fake_device_flow()

        with patch("sam_powerbi.auth.threading.Thread"):
            try:
                auth.get_token_or_start_device_flow()
            except PowerBIAuthPending:
                pass

            with pytest.raises(PowerBIAuthPending) as exc_info:
                auth.get_token_or_start_device_flow()

        # Device flow must only have been initiated once
        mock_app.initiate_device_flow.assert_called_once()
        assert exc_info.value.user_code == "ABC123"

    def test_failed_device_flow_initiation_raises_auth_error(self):
        auth, mock_app, _ = _make_auth()
        mock_app.get_accounts.return_value = []
        # MSAL returns a dict without 'user_code' when initiation fails
        mock_app.initiate_device_flow.return_value = {"error": "invalid_client"}

        with pytest.raises(PowerBIAuthError):
            auth.get_token_or_start_device_flow()

    def test_background_thread_is_started_as_daemon(self):
        auth, mock_app, _ = _make_auth()
        mock_app.get_accounts.return_value = []
        mock_app.initiate_device_flow.return_value = _fake_device_flow()

        created_threads = []

        def capture_thread(*args, **kwargs):
            t = MagicMock()
            t.daemon = kwargs.get("daemon", False)
            created_threads.append(kwargs)
            return t

        with patch("sam_powerbi.auth.threading.Thread", side_effect=capture_thread):
            try:
                auth.get_token_or_start_device_flow()
            except PowerBIAuthPending:
                pass

        assert len(created_threads) == 1
        assert created_threads[0].get("daemon") is True


class TestPollDeviceFlow:
    def test_clears_pending_flow_on_success(self):
        auth, mock_app, mock_cache = _make_auth()
        mock_cache.has_state_changed = False
        mock_app.acquire_token_by_device_flow.return_value = {"access_token": "new-token"}

        flow = _fake_device_flow()
        auth._pending_flow = {"flow": flow, **flow}

        auth._poll_device_flow(flow)

        assert auth._pending_flow is None

    def test_clears_pending_flow_on_terminal_error(self):
        auth, mock_app, _ = _make_auth()
        mock_app.acquire_token_by_device_flow.return_value = {
            "error": "access_denied",
            "error_description": "User declined",
        }

        flow = _fake_device_flow()
        auth._pending_flow = {"flow": flow, **flow}

        auth._poll_device_flow(flow)

        assert auth._pending_flow is None

    def test_clears_pending_flow_on_expiry(self):
        auth, mock_app, _ = _make_auth()
        # expires_at is in the past — the while loop should not execute at all
        expired_flow = _fake_device_flow(expires_at=time.time() - 1)
        auth._pending_flow = {"flow": expired_flow, **expired_flow}

        auth._poll_device_flow(expired_flow)

        mock_app.acquire_token_by_device_flow.assert_not_called()
        assert auth._pending_flow is None

    def test_saves_cache_on_successful_token_acquisition(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        auth, mock_app, mock_cache = _make_auth(cache_path=str(cache_file))
        mock_cache.has_state_changed = True
        mock_cache.serialize.return_value = '{"state": "saved"}'
        mock_app.acquire_token_by_device_flow.return_value = {"access_token": "tok"}

        flow = _fake_device_flow()
        auth._pending_flow = {"flow": flow, **flow}

        auth._poll_device_flow(flow)

        mock_cache.serialize.assert_called()

    def test_retries_on_authorization_pending(self):
        auth, mock_app, mock_cache = _make_auth()
        mock_cache.has_state_changed = False
        mock_app.acquire_token_by_device_flow.side_effect = [
            {"error": "authorization_pending"},
            {"access_token": "final-token"},
        ]

        flow = _fake_device_flow()
        auth._pending_flow = {"flow": flow, **flow}

        with patch("sam_powerbi.auth.time.sleep"):
            auth._poll_device_flow(flow)

        assert mock_app.acquire_token_by_device_flow.call_count == 2
        assert auth._pending_flow is None

    def test_increases_poll_interval_on_slow_down(self):
        auth, mock_app, mock_cache = _make_auth()
        mock_cache.has_state_changed = False
        mock_app.acquire_token_by_device_flow.side_effect = [
            {"error": "slow_down"},
            {"access_token": "tok"},
        ]

        flow = _fake_device_flow(interval=5)
        auth._pending_flow = {"flow": flow, **flow}

        with patch("sam_powerbi.auth.time.sleep") as mock_sleep:
            auth._poll_device_flow(flow)

        mock_sleep.assert_called_once_with(10)  # 5 (base) + 5 (slow_down increment)
        assert auth._pending_flow is None


class TestForceReauth:
    def test_removes_all_accounts(self):
        auth, mock_app, _ = _make_auth()
        accounts = [{"username": "a@x.com"}, {"username": "b@x.com"}]
        mock_app.get_accounts.return_value = accounts

        auth.force_reauth()

        assert mock_app.remove_account.call_count == 2
        mock_app.remove_account.assert_any_call(accounts[0])
        mock_app.remove_account.assert_any_call(accounts[1])

    def test_handles_remove_account_failure_gracefully(self):
        auth, mock_app, _ = _make_auth()
        mock_app.get_accounts.return_value = [{"username": "u"}]
        mock_app.remove_account.side_effect = Exception("remove failed")

        auth.force_reauth()  # must not raise

    def test_noop_when_no_accounts(self):
        auth, mock_app, _ = _make_auth()
        mock_app.get_accounts.return_value = []

        auth.force_reauth()

        mock_app.remove_account.assert_not_called()
