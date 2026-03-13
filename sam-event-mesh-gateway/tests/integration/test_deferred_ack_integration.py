"""
Integration tests for deferred acknowledgment in the Event Mesh Gateway.

These tests use the real EventMeshGatewayComponent to verify that ACK/NACK
settlement is handled correctly through the full message processing pipeline
for all configuration permutations of acknowledgment_policy.

Test scenarios covered:
- Default (on_receive): no deferred settlement occurs
- on_completion + success (with mocked broker output): ACK after task completes
- on_completion + failure (broker output unavailable): NACK with configurable outcome
- on_completion + failure + action=ack: ACK even on failure
- on_completion + failure + nack_outcome=failed: NACK to dead letter queue
- on_completion + timeout: NACK after timeout expires
- Handler-level override of gateway default
- Pre-submission failure (no matching handler, auth failure): NACK immediately
- Shutdown with pending deferred messages: all NACKed
"""

import asyncio
import pytest
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

from solace_ai_connector.common.message import Message as SolaceMessage
from solace_ai_connector.common.event import Event, EventType

from sam_test_infrastructure.llm_server.server import TestLLMServer
from sam_event_mesh_gateway.component import EventMeshGatewayComponent


# -- Helpers --


class AckTracker:
    """Tracks ACK/NACK calls on a SolaceMessage via callbacks."""

    def __init__(self):
        self.acked = False
        self.nacked = False
        self.nack_outcome = None

    def on_ack(self):
        self.acked = True

    def on_nack(self, outcome=None):
        self.nacked = True
        self.nack_outcome = outcome

    @property
    def settled(self):
        return self.acked or self.nacked


def make_tracked_message(
    topic: str = "test/events/deferred/test",
    payload: Optional[bytes] = None,
    user_properties: Optional[Dict[str, Any]] = None,
) -> tuple:
    """Create a SolaceMessage with ACK/NACK tracking.

    Returns:
        (SolaceMessage, AckTracker)
    """
    if payload is None:
        payload = b'{"message": "deferred ack test"}'
    if user_properties is None:
        user_properties = {"user_id": "deferred_test_user"}

    msg = SolaceMessage(
        payload=payload,
        topic=topic,
        user_properties=user_properties,
    )
    tracker = AckTracker()
    msg.add_acknowledgement(tracker.on_ack)
    msg.add_negative_acknowledgements(tracker.on_nack)
    return msg, tracker


@contextmanager
def deferred_ack_config(
    component: EventMeshGatewayComponent,
    gateway_policy: Optional[Dict[str, Any]] = None,
    handler_policy: Optional[Dict[str, Any]] = None,
    mock_broker_output: bool = False,
):
    """Context manager to temporarily set acknowledgment_policy on the component.

    Saves and restores the original config after the test.

    Args:
        component: The gateway component to patch.
        gateway_policy: Gateway-level acknowledgment_policy.
        handler_policy: Per-handler acknowledgment_policy override for all event handlers.
        mock_broker_output: If True, set data_plane_broker_output to a mock so publish
            succeeds. If False, leave it as None (natural test mode) which triggers
            the "broker unavailable" failure path.
    """
    orig_default_ack_policy = component.default_ack_policy
    orig_any_handler_defers = component.any_handler_defers_ack
    orig_handler_configs = [dict(h) for h in component.event_handlers_config]
    orig_handler_map = dict(component.event_handler_map)
    orig_broker_output = component.data_plane_broker_output

    try:
        # Set gateway-level policy
        component.default_ack_policy = gateway_policy or {}

        # Set handler-level override on all handlers
        if handler_policy is not None:
            for handler in component.event_handlers_config:
                handler["acknowledgment_policy"] = handler_policy

        # Recompute derived flags
        component.any_handler_defers_ack = any(
            component._is_deferred_ack(hc) for hc in component.event_handlers_config
        )
        # Rebuild handler map
        component.event_handler_map = {
            hc.get("name"): hc for hc in component.event_handlers_config
        }

        # Optionally mock broker output
        if mock_broker_output:
            mock_output = MagicMock()
            mock_output.enqueue = MagicMock()
            component.data_plane_broker_output = mock_output

        yield

    finally:
        # Restore original config
        component.default_ack_policy = orig_default_ack_policy
        component.any_handler_defers_ack = orig_any_handler_defers
        for i, handler in enumerate(component.event_handlers_config):
            handler.clear()
            handler.update(orig_handler_configs[i])
        component.event_handler_map = orig_handler_map
        component.data_plane_broker_output = orig_broker_output


def prime_llm_for_success(test_llm_server: TestLLMServer):
    """Prime the LLM server with a simple success response."""
    test_llm_server.prime_responses([
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Deferred ack test response",
                    }
                }
            ]
        }
    ])


async def wait_for_settlement(tracker: AckTracker, max_wait: float = 15.0):
    """Wait for ACK/NACK settlement, polling periodically."""
    start = time.time()
    while not tracker.settled and (time.time() - start) < max_wait:
        await asyncio.sleep(0.25)
    return tracker.settled


# -- Tests --


class TestDefaultOnReceiveMode:
    """Verify default (on_receive) mode: no deferred settlement occurs."""

    @pytest.mark.asyncio
    async def test_default_mode_does_not_defer(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_llm_server: TestLLMServer,
    ):
        """With default config (on_receive), deferred ACK is not enabled.
        The message ACK/NACK is handled by EventForwarderComponent, not by settlement."""
        prime_llm_for_success(test_llm_server)

        with deferred_ack_config(event_mesh_gateway_component, gateway_policy={}):
            assert event_mesh_gateway_component.any_handler_defers_ack is False

            msg, tracker = make_tracked_message()

            result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)

            # In on_receive mode, _handle_incoming_solace_message does NOT call
            # ACK/NACK — that's EventForwarderComponent's job.
            assert tracker.acked is False
            assert tracker.nacked is False


class TestOnCompletionSuccess:
    """Verify on_completion mode with successful task processing."""

    @pytest.mark.asyncio
    async def test_ack_after_successful_task_with_broker_output(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_llm_server: TestLLMServer,
    ):
        """With mode=on_completion and broker output available, message is ACKed
        after successful task completion and response publication."""
        prime_llm_for_success(test_llm_server)

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={"mode": "on_completion"},
            mock_broker_output=True,
        ):
            assert event_mesh_gateway_component.any_handler_defers_ack is True

            msg, tracker = make_tracked_message()

            result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)
            assert result is True

            settled = await wait_for_settlement(tracker)
            assert settled, "Message was not settled within timeout"
            assert tracker.acked is True, (
                f"Expected ACK after success, but acked={tracker.acked}, nacked={tracker.nacked}"
            )
            assert tracker.nacked is False

    @pytest.mark.asyncio
    async def test_ack_when_no_on_success_handler(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_llm_server: TestLLMServer,
    ):
        """With mode=on_completion and no on_success handler, message is still ACKed
        because processing succeeded — just no response to publish."""
        prime_llm_for_success(test_llm_server)

        # Temporarily remove on_success from handler
        handler = event_mesh_gateway_component.event_handlers_config[0]
        orig_on_success = handler.get("on_success")

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={"mode": "on_completion"},
        ):
            handler.pop("on_success", None)
            try:
                msg, tracker = make_tracked_message()

                result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)
                assert result is True

                settled = await wait_for_settlement(tracker)
                assert settled, "Message was not settled within timeout"
                assert tracker.acked is True
                assert tracker.nacked is False
            finally:
                if orig_on_success is not None:
                    handler["on_success"] = orig_on_success


class TestOnCompletionFailure:
    """Verify on_completion mode with various failure configurations.

    In test mode, data_plane_broker_output is None, so _send_final_response_to_external
    hits the "broker unavailable" path and settles as failure. This naturally exercises
    all failure config permutations through the real pipeline.
    """

    @pytest.mark.asyncio
    async def test_nack_with_rejected_outcome_on_failure(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_llm_server: TestLLMServer,
    ):
        """On failure with default config: NACK with 'rejected' outcome (redelivery).

        The broker output is unavailable in test mode, triggering the failure path.
        """
        prime_llm_for_success(test_llm_server)

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={
                "mode": "on_completion",
                "on_failure": {"action": "nack", "nack_outcome": "rejected"},
            },
            # No mock_broker_output → broker unavailable → failure settlement
        ):
            msg, tracker = make_tracked_message()

            result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)
            assert result is True

            settled = await wait_for_settlement(tracker)
            assert settled, "Message was not settled within timeout"
            assert tracker.nacked is True, (
                f"Expected NACK on failure, but acked={tracker.acked}, nacked={tracker.nacked}"
            )
            assert tracker.acked is False
            assert tracker.nack_outcome == "rejected"

    @pytest.mark.asyncio
    async def test_nack_with_failed_outcome_on_failure(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_llm_server: TestLLMServer,
    ):
        """On failure with nack_outcome='failed': NACK to dead letter queue."""
        prime_llm_for_success(test_llm_server)

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={
                "mode": "on_completion",
                "on_failure": {"action": "nack", "nack_outcome": "failed"},
            },
        ):
            msg, tracker = make_tracked_message()

            result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)
            assert result is True

            settled = await wait_for_settlement(tracker)
            assert settled, "Message was not settled within timeout"
            assert tracker.nacked is True
            assert tracker.nack_outcome == "failed"

    @pytest.mark.asyncio
    async def test_ack_on_failure_when_action_is_ack(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_llm_server: TestLLMServer,
    ):
        """On failure with action='ack': ACK even when processing fails."""
        prime_llm_for_success(test_llm_server)

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={
                "mode": "on_completion",
                "on_failure": {"action": "ack"},
            },
        ):
            msg, tracker = make_tracked_message()

            result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)
            assert result is True

            settled = await wait_for_settlement(tracker)
            assert settled, "Message was not settled within timeout"
            assert tracker.acked is True, (
                f"Expected ACK on failure with action='ack', but "
                f"acked={tracker.acked}, nacked={tracker.nacked}"
            )
            assert tracker.nacked is False


class TestHandlerOverride:
    """Verify handler-level acknowledgment_policy override of gateway default."""

    @pytest.mark.asyncio
    async def test_handler_overrides_gateway_to_on_completion(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_llm_server: TestLLMServer,
    ):
        """Handler with on_completion overrides gateway on_receive default.
        Uses mock broker output so the response publish succeeds → ACK."""
        prime_llm_for_success(test_llm_server)

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={"mode": "on_receive"},
            handler_policy={"mode": "on_completion"},
            mock_broker_output=True,
        ):
            assert event_mesh_gateway_component.any_handler_defers_ack is True

            msg, tracker = make_tracked_message()

            result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)
            assert result is True

            settled = await wait_for_settlement(tracker)
            assert settled, "Message was not settled within timeout"
            assert tracker.acked is True

    @pytest.mark.asyncio
    async def test_handler_overrides_gateway_to_on_receive(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_llm_server: TestLLMServer,
    ):
        """Handler with on_receive overrides gateway on_completion default.
        No deferred settlement should occur."""
        prime_llm_for_success(test_llm_server)

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={"mode": "on_completion"},
            handler_policy={"mode": "on_receive"},
        ):
            msg, tracker = make_tracked_message()

            result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)

            # Handler is on_receive, so no deferred settlement
            assert tracker.acked is False
            assert tracker.nacked is False

    @pytest.mark.asyncio
    async def test_handler_overrides_failure_action_to_ack(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_llm_server: TestLLMServer,
    ):
        """Handler overrides failure action from nack to ack.
        Broker unavailable triggers failure path, but handler says action=ack."""
        prime_llm_for_success(test_llm_server)

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={
                "mode": "on_completion",
                "on_failure": {"action": "nack", "nack_outcome": "rejected"},
            },
            handler_policy={
                "on_failure": {"action": "ack"},
            },
        ):
            msg, tracker = make_tracked_message()

            result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)
            assert result is True

            settled = await wait_for_settlement(tracker)
            assert settled, "Message was not settled within timeout"
            # Handler overrides to ack on failure
            assert tracker.acked is True
            assert tracker.nacked is False

    @pytest.mark.asyncio
    async def test_handler_overrides_nack_outcome_to_failed(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_llm_server: TestLLMServer,
    ):
        """Handler overrides nack_outcome from 'rejected' to 'failed'.
        Broker unavailable triggers failure path."""
        prime_llm_for_success(test_llm_server)

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={
                "mode": "on_completion",
                "on_failure": {"action": "nack", "nack_outcome": "rejected"},
            },
            handler_policy={
                "on_failure": {"nack_outcome": "failed"},
            },
        ):
            msg, tracker = make_tracked_message()

            result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)
            assert result is True

            settled = await wait_for_settlement(tracker)
            assert settled, "Message was not settled within timeout"
            assert tracker.nacked is True
            assert tracker.nack_outcome == "failed"


class TestPreSubmissionFailures:
    """Verify NACK on pre-submission failures when deferred ACK is enabled."""

    @pytest.mark.asyncio
    async def test_nack_on_no_matching_handler(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """NACK when no handler matches and deferred ACK is enabled at gateway level."""
        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={"mode": "on_completion"},
        ):
            # Use a topic that doesn't match any handler
            msg, tracker = make_tracked_message(topic="nonexistent/topic/path")

            result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)
            assert result is False

            assert tracker.nacked is True
            assert tracker.acked is False

    @pytest.mark.asyncio
    async def test_nack_on_auth_failure(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """NACK on authentication failure when deferred ACK is enabled."""
        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={"mode": "on_completion"},
        ):
            # Message with no user_id — should fail authentication
            msg, tracker = make_tracked_message(
                user_properties={},  # No user_id
            )

            result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)
            assert result is False

            assert tracker.nacked is True
            assert tracker.acked is False

    @pytest.mark.asyncio
    async def test_no_nack_on_no_handler_when_on_receive(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """No NACK when on_receive mode and handler doesn't match (already ACKed)."""
        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={},
        ):
            msg, tracker = make_tracked_message(topic="nonexistent/topic/path")

            result = await event_mesh_gateway_component._handle_incoming_solace_message(msg)
            assert result is False

            # No deferred settlement — message was already ACKed by forwarder
            assert tracker.acked is False
            assert tracker.nacked is False


class TestTimeout:
    """Verify deferred ACK timeout behavior.

    Instead of relying on a slow LLM response (which would block session teardown),
    we test the timeout handler directly by injecting a context and calling
    _handle_deferred_ack_timeout on the real component instance.
    """

    def test_timeout_handler_nacks_pending_message(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """_handle_deferred_ack_timeout NACKs the original message and removes context."""
        msg, tracker = make_tracked_message()
        task_id = "timeout_test_task_42"

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={"mode": "on_completion"},
        ):
            handler_name = event_mesh_gateway_component.event_handlers_config[0]["name"]

            # Inject context as if a task was submitted
            event_mesh_gateway_component.task_context_manager.store_context(
                task_id,
                {
                    "deferred_ack_enabled": True,
                    "original_data_plane_message": msg,
                    "event_handler_name": handler_name,
                },
            )

            try:
                # Simulate timeout firing
                event_mesh_gateway_component._handle_deferred_ack_timeout(task_id)

                assert tracker.nacked is True
                assert tracker.acked is False

                # Context should have been removed
                ctx = event_mesh_gateway_component.task_context_manager.get_context(task_id)
                assert ctx is None
            finally:
                event_mesh_gateway_component.task_context_manager.remove_context(task_id)

    def test_timeout_handler_with_failed_nack_outcome(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """Timeout respects nack_outcome='failed' config (dead letter queue)."""
        msg, tracker = make_tracked_message()
        task_id = "timeout_test_task_dlq"

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={
                "mode": "on_completion",
                "on_failure": {"nack_outcome": "failed"},
            },
        ):
            handler_name = event_mesh_gateway_component.event_handlers_config[0]["name"]

            event_mesh_gateway_component.task_context_manager.store_context(
                task_id,
                {
                    "deferred_ack_enabled": True,
                    "original_data_plane_message": msg,
                    "event_handler_name": handler_name,
                },
            )

            try:
                event_mesh_gateway_component._handle_deferred_ack_timeout(task_id)

                assert tracker.nacked is True
                assert tracker.nack_outcome == "failed"
            finally:
                event_mesh_gateway_component.task_context_manager.remove_context(task_id)

    def test_timeout_handler_noop_for_already_settled(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """Timeout is a no-op if context was already removed (task completed first)."""
        # Don't store any context — simulates the task completing before timeout fires
        event_mesh_gateway_component._handle_deferred_ack_timeout("nonexistent_task")
        # Should not raise


class TestSettleDeferredAckDirect:
    """Direct tests of _settle_deferred_ack on the real component instance.

    These test the settlement method in isolation with various config permutations,
    complementing the end-to-end tests above.
    """

    def test_settle_ack_on_success(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """ACK is called when settling a successful task."""
        msg, tracker = make_tracked_message()

        context = {
            "deferred_ack_enabled": True,
            "original_data_plane_message": msg,
            "event_handler_name": event_mesh_gateway_component.event_handlers_config[0]["name"],
        }

        event_mesh_gateway_component._settle_deferred_ack(context, success=True)

        assert tracker.acked is True
        assert tracker.nacked is False

    def test_settle_nack_on_failure(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """NACK is called when settling a failed task with default config."""
        msg, tracker = make_tracked_message()

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={"mode": "on_completion"},
        ):
            context = {
                "deferred_ack_enabled": True,
                "original_data_plane_message": msg,
                "event_handler_name": event_mesh_gateway_component.event_handlers_config[0]["name"],
            }

            event_mesh_gateway_component._settle_deferred_ack(context, success=False)

            assert tracker.nacked is True
            assert tracker.nack_outcome == "rejected"

    def test_settle_ack_on_failure_with_ack_action(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """ACK on failure when on_failure.action='ack'."""
        msg, tracker = make_tracked_message()

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={
                "mode": "on_completion",
                "on_failure": {"action": "ack"},
            },
        ):
            context = {
                "deferred_ack_enabled": True,
                "original_data_plane_message": msg,
                "event_handler_name": event_mesh_gateway_component.event_handlers_config[0]["name"],
            }

            event_mesh_gateway_component._settle_deferred_ack(context, success=False)

            assert tracker.acked is True
            assert tracker.nacked is False

    def test_settle_nack_with_failed_outcome(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """NACK with 'failed' outcome sends to dead letter queue."""
        msg, tracker = make_tracked_message()

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={
                "mode": "on_completion",
                "on_failure": {"nack_outcome": "failed"},
            },
        ):
            context = {
                "deferred_ack_enabled": True,
                "original_data_plane_message": msg,
                "event_handler_name": event_mesh_gateway_component.event_handlers_config[0]["name"],
            }

            event_mesh_gateway_component._settle_deferred_ack(context, success=False)

            assert tracker.nacked is True
            assert tracker.nack_outcome == "failed"

    def test_settle_noop_when_not_deferred(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """No-op when deferred_ack_enabled is False."""
        msg, tracker = make_tracked_message()

        context = {
            "deferred_ack_enabled": False,
            "original_data_plane_message": msg,
        }

        event_mesh_gateway_component._settle_deferred_ack(context, success=True)

        assert tracker.acked is False
        assert tracker.nacked is False

    def test_settle_idempotent(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """Calling settle twice is safe — second call is a no-op."""
        msg, tracker = make_tracked_message()

        context = {
            "deferred_ack_enabled": True,
            "original_data_plane_message": msg,
            "event_handler_name": event_mesh_gateway_component.event_handlers_config[0]["name"],
        }

        event_mesh_gateway_component._settle_deferred_ack(context, success=True)
        assert tracker.acked is True

        # Second call should be no-op because original_data_plane_message was popped
        tracker2 = AckTracker()
        msg.add_acknowledgement(tracker2.on_ack)
        event_mesh_gateway_component._settle_deferred_ack(context, success=True)
        assert tracker2.acked is False


class TestNackAllPendingDeferred:
    """Tests for _nack_all_pending_deferred (shutdown cleanup) on real component."""

    def test_shutdown_nacks_all_pending(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """All pending deferred contexts are NACKed during shutdown cleanup."""
        msg1, tracker1 = make_tracked_message()
        msg2, tracker2 = make_tracked_message()

        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={"mode": "on_completion"},
        ):
            handler_name = event_mesh_gateway_component.event_handlers_config[0]["name"]

            # Store contexts as if tasks were submitted
            event_mesh_gateway_component.task_context_manager.store_context(
                "shutdown_test_task_1",
                {
                    "deferred_ack_enabled": True,
                    "original_data_plane_message": msg1,
                    "event_handler_name": handler_name,
                },
            )
            event_mesh_gateway_component.task_context_manager.store_context(
                "shutdown_test_task_2",
                {
                    "deferred_ack_enabled": True,
                    "original_data_plane_message": msg2,
                    "event_handler_name": handler_name,
                },
            )

            try:
                event_mesh_gateway_component._nack_all_pending_deferred("[ShutdownTest]")

                assert tracker1.nacked is True
                assert tracker2.nacked is True
                assert tracker1.acked is False
                assert tracker2.acked is False
            finally:
                # Clean up any remaining contexts
                event_mesh_gateway_component.task_context_manager.remove_context("shutdown_test_task_1")
                event_mesh_gateway_component.task_context_manager.remove_context("shutdown_test_task_2")

    def test_shutdown_skipped_when_no_deferred_handlers(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """Shutdown cleanup is a no-op when no handlers use deferred ACK."""
        with deferred_ack_config(
            event_mesh_gateway_component,
            gateway_policy={},  # on_receive (default)
        ):
            assert event_mesh_gateway_component.any_handler_defers_ack is False

            # Should not raise and should not touch task_context_manager
            event_mesh_gateway_component._nack_all_pending_deferred("[ShutdownTest]")
