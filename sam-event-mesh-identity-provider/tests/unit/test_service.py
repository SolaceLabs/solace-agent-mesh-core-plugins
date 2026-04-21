"""Unit tests for the EventMeshService class."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sam_event_mesh_identity_provider.service import EventMeshService


class TestServiceInitialization:
    """Tests for service initialization and session creation."""

    def test_init_creates_session(self, base_config, mock_component):
        """Initialization calls create_request_response_session."""
        service = EventMeshService(base_config, mock_component)
        mock_component.create_request_response_session.assert_called_once()
        assert service.session_id == "test-session-id"

    def test_init_raises_on_no_config(self, mock_component):
        """ValueError raised when config is None."""
        with pytest.raises(ValueError, match="requires a configuration"):
            EventMeshService(None, mock_component)

    def test_init_raises_on_empty_config(self, mock_component):
        """ValueError raised when config is empty dict."""
        with pytest.raises(ValueError, match="requires a configuration"):
            EventMeshService({}, mock_component)

    def test_init_raises_on_no_component(self, base_config):
        """ValueError raised when component is None."""
        with pytest.raises(ValueError, match="requires a SAM component"):
            EventMeshService(base_config, None)

    def test_init_raises_on_session_failure(self, base_config, mock_component):
        """Error propagates when session creation fails."""
        mock_component.create_request_response_session.side_effect = RuntimeError("Broker down")
        with pytest.raises(RuntimeError, match="Broker down"):
            EventMeshService(base_config, mock_component)

    def test_init_session_config_values(self, base_config, mock_component):
        """Session config contains the correct broker and payload settings."""
        EventMeshService(base_config, mock_component)
        call_kwargs = mock_component.create_request_response_session.call_args
        session_config = call_kwargs.kwargs.get("session_config") or call_kwargs[1].get("session_config")
        assert session_config["broker_config"]["broker_url"] == "tcp://localhost:55555"
        assert session_config["payload_format"] == "json"
        assert session_config["request_expiry_ms"] == 120000

    def test_init_loads_operations(self, base_config, mock_component):
        """Operations dict is loaded from config."""
        service = EventMeshService(base_config, mock_component)
        assert "user_profile" in service.operations
        assert "search_users" in service.operations
        assert service.operations["user_profile"]["response_topic"] == "test/user-profile/response/"


class TestServiceOperationCheck:
    """Tests for is_operation_configured."""

    def test_configured_operation(self, base_config, mock_component):
        """Returns True for configured operations."""
        service = EventMeshService(base_config, mock_component)
        assert service.is_operation_configured("user_profile") is True
        assert service.is_operation_configured("employee_data") is True

    def test_unconfigured_operation(self, base_config, mock_component):
        """Returns False for operations not in config."""
        service = EventMeshService(base_config, mock_component)
        assert service.is_operation_configured("nonexistent") is False

    def test_partial_config(self, partial_config, mock_component):
        """Only configured operations return True."""
        service = EventMeshService(partial_config, mock_component)
        assert service.is_operation_configured("user_profile") is True
        assert service.is_operation_configured("search_users") is False
        assert service.is_operation_configured("employee_data") is False


class TestServiceSendRequest:
    """Tests for the send_request method."""

    @pytest.mark.asyncio
    async def test_send_request_success(self, base_config, mock_component):
        """Successful request returns the response payload."""
        mock_response = MagicMock()
        mock_response.get_payload.return_value = {"name": "Jane", "email": "j@co.com"}
        mock_component.do_broker_request_response_async = AsyncMock(return_value=mock_response)

        service = EventMeshService(base_config, mock_component)
        result = await service.send_request("user_profile", {"email": "j@co.com"})

        assert result == {"name": "Jane", "email": "j@co.com"}
        mock_component.do_broker_request_response_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_request_unconfigured_operation(self, base_config, mock_component):
        """Returns None with warning for an operation not in config."""
        service = EventMeshService(base_config, mock_component)
        result = await service.send_request("nonexistent_op", {"foo": "bar"})
        assert result is None

    @pytest.mark.asyncio
    async def test_send_request_topic_formatting(self, base_config, mock_component):
        """Request ID is interpolated into the topic template."""
        mock_response = MagicMock()
        mock_response.get_payload.return_value = {}
        mock_component.do_broker_request_response_async = AsyncMock(return_value=mock_response)

        service = EventMeshService(base_config, mock_component)
        await service.send_request("user_profile", {"email": "a@b.com"})

        call_args = mock_component.do_broker_request_response_async.call_args
        message = call_args[0][0]
        # Topic should start with "test/user-profile/" followed by a UUID
        assert message.get_topic().startswith("test/user-profile/")
        assert len(message.get_topic().split("/")[-1]) == 36  # UUID length

    @pytest.mark.asyncio
    async def test_send_request_exception_returns_none(self, base_config, mock_component):
        """Returns None when broker request raises an exception."""
        mock_component.do_broker_request_response_async = AsyncMock(
            side_effect=TimeoutError("Request timed out")
        )
        service = EventMeshService(base_config, mock_component)
        result = await service.send_request("user_profile", {"email": "a@b.com"})
        assert result is None

    @pytest.mark.asyncio
    async def test_send_request_passes_payload(self, base_config, mock_component):
        """The request payload is passed correctly in the message."""
        mock_response = MagicMock()
        mock_response.get_payload.return_value = {}
        mock_component.do_broker_request_response_async = AsyncMock(return_value=mock_response)

        service = EventMeshService(base_config, mock_component)
        payload = {"employee_id": "emp123", "extra": "data"}
        await service.send_request("employee_profile", payload)

        call_args = mock_component.do_broker_request_response_async.call_args
        message = call_args[0][0]
        assert message.get_payload() == payload

    @pytest.mark.asyncio
    async def test_send_request_partial_config_only_configured_ops_work(
        self, partial_config, mock_component
    ):
        """Only the configured operation works; unconfigured ones return None."""
        mock_response = MagicMock()
        mock_response.get_payload.return_value = {"id": "1"}
        mock_component.do_broker_request_response_async = AsyncMock(return_value=mock_response)

        service = EventMeshService(partial_config, mock_component)

        # Configured operation works
        result = await service.send_request("user_profile", {"email": "a@b.com"})
        assert result == {"id": "1"}

        # Unconfigured operations return None
        assert await service.send_request("search_users", {"query": "a"}) is None
        assert await service.send_request("employee_data", {}) is None


class TestServiceCleanup:
    """Tests for cleanup behavior."""

    def test_cleanup_destroys_session(self, base_config, mock_component):
        """cleanup() calls destroy_request_response_session."""
        service = EventMeshService(base_config, mock_component)
        service.cleanup()
        mock_component.destroy_request_response_session.assert_called_once_with("test-session-id")
        assert service.session_id is None

    def test_cleanup_safe_when_no_session(self, base_config, mock_component):
        """cleanup() is safe when session_id is already None."""
        service = EventMeshService(base_config, mock_component)
        service.session_id = None
        service.cleanup()  # Should not raise
        mock_component.destroy_request_response_session.assert_not_called()
