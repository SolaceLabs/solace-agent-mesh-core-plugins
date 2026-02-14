"""
Tests for deferred acknowledgment in the Event Mesh Gateway.

Tests cover:
- acknowledgment_policy config resolution
- EventForwarderComponent conditional ACK behavior
- _settle_deferred_ack settlement logic
- _nack_if_deferred pre-submission failure handling
- _nack_all_pending_deferred shutdown handling
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from typing import Dict, Any

from sam_event_mesh_gateway.component import EventMeshGatewayComponent


# -- Fixtures --


@pytest.fixture
def mock_component():
    """Create a mock gateway component with real ack policy methods bound."""
    component = MagicMock(spec=EventMeshGatewayComponent)
    component.log_identifier = "[TestGateway]"
    component.gateway_id = "TestGateway"
    component.default_ack_policy = {}
    component.any_handler_defers_ack = False
    component.event_handler_map = {}

    # Bind real methods
    for method_name in [
        "_resolve_ack_policy",
        "_is_deferred_ack",
        "_get_ack_timeout",
        "_get_failure_action",
        "_get_nack_outcome",
        "_settle_deferred_ack",
        "_nack_if_deferred",
        "_nack_all_pending_deferred",
    ]:
        method = getattr(EventMeshGatewayComponent, method_name)
        setattr(component, method_name, method.__get__(component, EventMeshGatewayComponent))

    return component


@pytest.fixture
def mock_solace_message():
    """Create a mock SolaceMessage with ACK/NACK tracking."""
    msg = MagicMock()
    msg.acked = False
    msg.nacked = False
    msg.nack_outcome = None

    def do_ack():
        msg.acked = True

    def do_nack(outcome=None):
        msg.nacked = True
        msg.nack_outcome = outcome

    msg.call_acknowledgements = MagicMock(side_effect=do_ack)
    msg.call_negative_acknowledgements = MagicMock(side_effect=do_nack)
    return msg


# -- Config Resolution Tests --


class TestAckPolicyResolution:
    """Tests for _resolve_ack_policy and helper methods."""

    def test_default_policy_when_no_config(self, mock_component):
        """Default policy returns on_receive mode."""
        policy = mock_component._resolve_ack_policy({})
        assert policy.get("mode", "on_receive") == "on_receive"

    def test_gateway_level_on_completion(self, mock_component):
        """Gateway-level mode=on_completion is respected."""
        mock_component.default_ack_policy = {"mode": "on_completion"}
        assert mock_component._is_deferred_ack({}) is True

    def test_handler_override_mode(self, mock_component):
        """Handler-level mode overrides gateway default."""
        mock_component.default_ack_policy = {"mode": "on_receive"}
        handler = {"acknowledgment_policy": {"mode": "on_completion"}}
        assert mock_component._is_deferred_ack(handler) is True

    def test_handler_override_back_to_on_receive(self, mock_component):
        """Handler can override back to on_receive even when gateway says on_completion."""
        mock_component.default_ack_policy = {"mode": "on_completion"}
        handler = {"acknowledgment_policy": {"mode": "on_receive"}}
        assert mock_component._is_deferred_ack(handler) is False

    def test_default_timeout(self, mock_component):
        """Default timeout is 300 seconds."""
        assert mock_component._get_ack_timeout({}) == 300

    def test_gateway_timeout_override(self, mock_component):
        """Gateway-level timeout is respected."""
        mock_component.default_ack_policy = {"timeout_seconds": 60}
        assert mock_component._get_ack_timeout({}) == 60

    def test_handler_timeout_override(self, mock_component):
        """Handler-level timeout overrides gateway."""
        mock_component.default_ack_policy = {"timeout_seconds": 60}
        handler = {"acknowledgment_policy": {"timeout_seconds": 120}}
        assert mock_component._get_ack_timeout(handler) == 120

    def test_default_failure_action(self, mock_component):
        """Default failure action is 'nack'."""
        assert mock_component._get_failure_action({}) == "nack"

    def test_gateway_failure_action_ack(self, mock_component):
        """Gateway-level on_failure.action='ack' is respected."""
        mock_component.default_ack_policy = {"on_failure": {"action": "ack"}}
        assert mock_component._get_failure_action({}) == "ack"

    def test_handler_failure_action_override(self, mock_component):
        """Handler-level on_failure.action overrides gateway."""
        mock_component.default_ack_policy = {"on_failure": {"action": "nack"}}
        handler = {"acknowledgment_policy": {"on_failure": {"action": "ack"}}}
        assert mock_component._get_failure_action(handler) == "ack"

    def test_default_nack_outcome(self, mock_component):
        """Default NACK outcome is 'rejected'."""
        assert mock_component._get_nack_outcome({}) == "rejected"

    def test_gateway_nack_outcome_failed(self, mock_component):
        """Gateway-level nack_outcome='failed' is respected."""
        mock_component.default_ack_policy = {"on_failure": {"nack_outcome": "failed"}}
        assert mock_component._get_nack_outcome({}) == "failed"

    def test_handler_nack_outcome_override(self, mock_component):
        """Handler-level nack_outcome overrides gateway."""
        mock_component.default_ack_policy = {"on_failure": {"nack_outcome": "rejected"}}
        handler = {"acknowledgment_policy": {"on_failure": {"nack_outcome": "failed"}}}
        assert mock_component._get_nack_outcome(handler) == "failed"

    def test_full_merge(self, mock_component):
        """Full merge: handler overrides some fields, inherits others."""
        mock_component.default_ack_policy = {
            "mode": "on_completion",
            "timeout_seconds": 600,
            "on_failure": {"action": "nack", "nack_outcome": "rejected"},
        }
        handler = {
            "acknowledgment_policy": {
                "timeout_seconds": 120,
                "on_failure": {"nack_outcome": "failed"},
            }
        }
        # mode inherited from gateway
        assert mock_component._is_deferred_ack(handler) is True
        # timeout overridden
        assert mock_component._get_ack_timeout(handler) == 120
        # action inherited from gateway
        assert mock_component._get_failure_action(handler) == "nack"
        # nack_outcome overridden
        assert mock_component._get_nack_outcome(handler) == "failed"


# -- Settlement Tests --


class TestSettleDeferredAck:
    """Tests for _settle_deferred_ack."""

    def test_ack_on_success(self, mock_component, mock_solace_message):
        """ACK is called on success."""
        mock_component.event_handler_map = {"test_handler": {}}
        context = {
            "deferred_ack_enabled": True,
            "original_data_plane_message": mock_solace_message,
            "event_handler_name": "test_handler",
        }
        mock_component._settle_deferred_ack(context, success=True)
        assert mock_solace_message.acked is True
        assert mock_solace_message.nacked is False

    def test_nack_on_failure_default(self, mock_component, mock_solace_message):
        """NACK with 'rejected' outcome on failure by default."""
        mock_component.event_handler_map = {"test_handler": {}}
        context = {
            "deferred_ack_enabled": True,
            "original_data_plane_message": mock_solace_message,
            "event_handler_name": "test_handler",
        }
        mock_component._settle_deferred_ack(context, success=False)
        assert mock_solace_message.nacked is True
        assert mock_solace_message.nack_outcome == "rejected"

    def test_ack_on_failure_when_configured(self, mock_component, mock_solace_message):
        """ACK on failure when on_failure.action='ack'."""
        mock_component.default_ack_policy = {"on_failure": {"action": "ack"}}
        mock_component.event_handler_map = {"test_handler": {}}
        context = {
            "deferred_ack_enabled": True,
            "original_data_plane_message": mock_solace_message,
            "event_handler_name": "test_handler",
        }
        mock_component._settle_deferred_ack(context, success=False)
        assert mock_solace_message.acked is True
        assert mock_solace_message.nacked is False

    def test_nack_with_failed_outcome(self, mock_component, mock_solace_message):
        """NACK with 'failed' outcome sends to dead letter queue."""
        mock_component.default_ack_policy = {
            "on_failure": {"nack_outcome": "failed"}
        }
        mock_component.event_handler_map = {"test_handler": {}}
        context = {
            "deferred_ack_enabled": True,
            "original_data_plane_message": mock_solace_message,
            "event_handler_name": "test_handler",
        }
        mock_component._settle_deferred_ack(context, success=False)
        assert mock_solace_message.nacked is True
        assert mock_solace_message.nack_outcome == "failed"

    def test_noop_when_not_deferred(self, mock_component, mock_solace_message):
        """No-op when deferred_ack_enabled is False."""
        context = {
            "deferred_ack_enabled": False,
            "original_data_plane_message": mock_solace_message,
        }
        mock_component._settle_deferred_ack(context, success=True)
        assert mock_solace_message.acked is False
        assert mock_solace_message.nacked is False

    def test_idempotent_double_settle(self, mock_component, mock_solace_message):
        """Calling settle twice is safe — second call is a no-op."""
        mock_component.event_handler_map = {"test_handler": {}}
        context = {
            "deferred_ack_enabled": True,
            "original_data_plane_message": mock_solace_message,
            "event_handler_name": "test_handler",
        }
        mock_component._settle_deferred_ack(context, success=True)
        assert mock_solace_message.acked is True
        mock_solace_message.call_acknowledgements.reset_mock()

        # Second call — message already popped from context
        mock_component._settle_deferred_ack(context, success=True)
        mock_solace_message.call_acknowledgements.assert_not_called()

    def test_timer_cancelled_on_settle(self, mock_component, mock_solace_message):
        """Timer is cancelled when settling."""
        mock_component.event_handler_map = {"test_handler": {}}
        context = {
            "deferred_ack_enabled": True,
            "original_data_plane_message": mock_solace_message,
            "event_handler_name": "test_handler",
            "a2a_task_id_for_event": "task-123",
        }
        mock_component._settle_deferred_ack(context, success=True)
        mock_component.cancel_timer.assert_called_once_with("deferred_ack_timeout_task-123")


# -- Pre-submission NACK Tests --


class TestNackIfDeferred:
    """Tests for _nack_if_deferred."""

    def test_nack_when_handler_deferred(self, mock_component, mock_solace_message):
        """NACK when handler has deferred ACK enabled."""
        mock_component.default_ack_policy = {"mode": "on_completion"}
        handler = {"acknowledgment_policy": {"mode": "on_completion"}}
        mock_component._nack_if_deferred(mock_solace_message, handler)
        assert mock_solace_message.nacked is True

    def test_noop_when_handler_not_deferred(self, mock_component, mock_solace_message):
        """No-op when handler uses on_receive."""
        handler = {"acknowledgment_policy": {"mode": "on_receive"}}
        mock_component._nack_if_deferred(mock_solace_message, handler)
        assert mock_solace_message.nacked is False

    def test_nack_with_no_handler_uses_default(self, mock_component, mock_solace_message):
        """When handler_config is None, uses gateway default."""
        mock_component.any_handler_defers_ack = True
        mock_component.default_ack_policy = {
            "mode": "on_completion",
            "on_failure": {"nack_outcome": "failed"},
        }
        mock_component._nack_if_deferred(mock_solace_message, None)
        assert mock_solace_message.nacked is True
        assert mock_solace_message.nack_outcome == "failed"

    def test_noop_with_no_handler_and_no_default(self, mock_component, mock_solace_message):
        """No-op when no handler and gateway default is on_receive."""
        mock_component.any_handler_defers_ack = False
        mock_component._nack_if_deferred(mock_solace_message, None)
        assert mock_solace_message.nacked is False


# -- Shutdown Tests --


class TestNackAllPendingDeferred:
    """Tests for _nack_all_pending_deferred."""

    def test_nacks_all_pending_contexts(self, mock_component, mock_solace_message):
        """All pending deferred contexts are NACKed on shutdown."""
        mock_component.any_handler_defers_ack = True
        mock_component.event_handler_map = {"test_handler": {}}
        mock_component.data_plane_message_queue = MagicMock()
        mock_component.data_plane_message_queue.empty.return_value = True

        mock_context = {
            "deferred_ack_enabled": True,
            "original_data_plane_message": mock_solace_message,
            "event_handler_name": "test_handler",
        }
        mock_component.task_context_manager = MagicMock()
        mock_component.task_context_manager.scan_contexts.return_value = [
            ("task-1", mock_context)
        ]

        mock_component._nack_all_pending_deferred("[Test]")
        assert mock_solace_message.nacked is True

    def test_skipped_when_no_deferred_handlers(self, mock_component):
        """Shutdown cleanup is skipped when no handlers use deferred ACK."""
        mock_component.any_handler_defers_ack = False
        mock_component.task_context_manager = MagicMock()

        mock_component._nack_all_pending_deferred("[Test]")
        mock_component.task_context_manager.scan_contexts.assert_not_called()
