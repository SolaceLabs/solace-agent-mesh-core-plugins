"""
Unit tests for hang-recovery behavior in the Slack adapter.

Covers DATAGO-137322: a hung Slack API call must not wedge the broker
consumer flow. Two complementary defenses are verified here:

1. The Slack ``AsyncWebClient`` is created with a finite HTTP timeout so
   stalled requests fail fast instead of awaiting forever.
2. ``handle_task_complete`` bounds the per-task queue drain with
   ``asyncio.wait_for`` so a stuck queue worker can't block the broker ACK.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sam_slack_gateway_adapter.adapter import (
    QUEUE_DRAIN_TIMEOUT_SEC,
    SlackAdapter,
    SlackAdapterConfig,
)
from sam_slack_gateway_adapter.message_queue import SlackMessageQueue
from solace_agent_mesh.gateway.adapter.types import (
    GatewayContext,
    ResponseContext,
)


@pytest.fixture
def mock_gateway_context():
    """Mock GatewayContext with valid SlackAdapterConfig."""
    context = MagicMock(spec=GatewayContext)
    context.adapter_config = SlackAdapterConfig(
        slack_bot_token="xoxb-test-token",
        slack_app_token="xapp-test-token",
        slack_initial_status_message="Thinking...",
        correct_markdown_formatting=True,
        feedback_enabled=False,
        slack_email_cache_ttl_seconds=3600,
    )
    context.cache_service = None
    context.get_config = MagicMock(return_value="OrchestratorAgent")
    context.get_task_state = MagicMock(return_value=None)
    context.set_task_state = MagicMock()
    return context


@pytest.fixture
def slack_adapter(mock_gateway_context):
    """SlackAdapter with mocked Slack client (bypasses init() side effects)."""
    adapter = SlackAdapter()
    adapter.context = mock_gateway_context
    adapter.slack_app = MagicMock()
    adapter.slack_app.client = AsyncMock()
    return adapter


@pytest.fixture
def response_context():
    """A minimal ResponseContext for handle_task_complete invocations."""
    return ResponseContext(
        task_id="task-stuck-123",
        session_id="session-1",
        user_id="user-1",
        platform_context={"channel_id": "C1", "thread_ts": "1.1"},
    )


class TestSlackClientHttpTimeout:
    """Verify Fix 1: the Slack AsyncWebClient is created with an HTTP timeout."""

    @pytest.mark.asyncio
    async def test_init_configures_slack_client_with_http_timeout(
        self, mock_gateway_context
    ):
        """init() must create an AsyncWebClient with timeout=30."""
        adapter = SlackAdapter()

        # Patch out side effects: socket-mode handler start and handler registration.
        with patch(
            "sam_slack_gateway_adapter.adapter.AsyncSocketModeHandler"
        ), patch.object(SlackAdapter, "_register_handlers"), patch(
            "sam_slack_gateway_adapter.adapter.asyncio.create_task"
        ):
            await adapter.init(mock_gateway_context)

        assert adapter.slack_app is not None
        client = adapter.slack_app.client
        # The Slack client used by AsyncApp must have a finite HTTP timeout,
        # otherwise a stalled chat.update can hang forever.
        assert client.timeout == 30, (
            f"Slack AsyncWebClient must have timeout=30, got timeout={client.timeout}"
        )


class TestHandleTaskCompleteTimeout:
    """Verify Fix 2: handle_task_complete bounds the queue wait."""

    @pytest.mark.asyncio
    async def test_does_not_hang_when_queue_stalls(
        self, slack_adapter, response_context, caplog
    ):
        """If the per-task queue's wait_until_complete hangs, handle_task_complete
        must time out (via asyncio.wait_for) and proceed so the broker can ACK.
        """
        task_id = response_context.task_id

        async def hang_forever():
            await asyncio.sleep(3600)  # never returns naturally

        hung_queue = MagicMock(spec=SlackMessageQueue)
        hung_queue.wait_until_complete = lambda: hang_forever()
        hung_queue.stop = AsyncMock()
        slack_adapter.message_queues[task_id] = hung_queue

        # Patching `adapter.asyncio.wait_for` reaches the real asyncio module,
        # so it intercepts EVERY wait_for system-wide while the patch is active.
        # Use a conditional shim: only short-circuit the 60s call inside
        # handle_task_complete; delegate everything else (including this test's
        # own outer wait_for) to the real implementation.
        real_wait_for = asyncio.wait_for

        async def conditional_wait_for(coro, timeout):
            if timeout == QUEUE_DRAIN_TIMEOUT_SEC:
                coro.close()
                raise asyncio.TimeoutError()
            return await real_wait_for(coro, timeout)

        with patch(
            "sam_slack_gateway_adapter.adapter.asyncio.wait_for",
            side_effect=conditional_wait_for,
        ), patch(
            "sam_slack_gateway_adapter.adapter.utils.send_slack_message",
            new=AsyncMock(),
        ), patch(
            "sam_slack_gateway_adapter.adapter.utils.update_slack_message",
            new=AsyncMock(),
        ), patch.object(
            slack_adapter, "_resolve_citations_final_pass", new=AsyncMock()
        ), caplog.at_level(logging.WARNING):
            # Outer wait_for guards against regressions: if the timeout handling
            # is removed, the test fails fast instead of hanging the suite.
            await asyncio.wait_for(
                slack_adapter.handle_task_complete(response_context),
                timeout=5.0,
            )

        assert any(
            "Timeout waiting for queue to complete" in record.message
            and task_id in record.message
            for record in caplog.records
        ), "Expected a TimeoutError warning naming the stuck task to be logged"

    @pytest.mark.asyncio
    async def test_uses_module_level_timeout_constant(
        self, slack_adapter, response_context
    ):
        """The asyncio.wait_for call must use the QUEUE_DRAIN_TIMEOUT_SEC constant."""
        task_id = response_context.task_id

        async def returns_quickly():
            return

        ok_queue = MagicMock(spec=SlackMessageQueue)
        ok_queue.wait_until_complete = lambda: returns_quickly()
        ok_queue.stop = AsyncMock()
        slack_adapter.message_queues[task_id] = ok_queue

        recorded = {}

        async def capture_wait_for(coro, timeout):
            recorded["timeout"] = timeout
            return await coro

        with patch(
            "sam_slack_gateway_adapter.adapter.asyncio.wait_for",
            side_effect=capture_wait_for,
        ), patch(
            "sam_slack_gateway_adapter.adapter.utils.send_slack_message",
            new=AsyncMock(),
        ), patch(
            "sam_slack_gateway_adapter.adapter.utils.update_slack_message",
            new=AsyncMock(),
        ), patch.object(
            slack_adapter, "_resolve_citations_final_pass", new=AsyncMock()
        ):
            await slack_adapter.handle_task_complete(response_context)

        assert recorded.get("timeout") == QUEUE_DRAIN_TIMEOUT_SEC, (
            f"Expected timeout={QUEUE_DRAIN_TIMEOUT_SEC}, "
            f"got {recorded.get('timeout')!r}"
        )

    @pytest.mark.asyncio
    async def test_normal_completion_does_not_log_timeout_warning(
        self, slack_adapter, response_context, caplog
    ):
        """When the queue drains normally, no timeout warning is emitted."""
        task_id = response_context.task_id

        async def returns_quickly():
            return

        ok_queue = MagicMock(spec=SlackMessageQueue)
        ok_queue.wait_until_complete = lambda: returns_quickly()
        ok_queue.stop = AsyncMock()
        slack_adapter.message_queues[task_id] = ok_queue

        with patch(
            "sam_slack_gateway_adapter.adapter.utils.send_slack_message",
            new=AsyncMock(),
        ), patch(
            "sam_slack_gateway_adapter.adapter.utils.update_slack_message",
            new=AsyncMock(),
        ), patch.object(
            slack_adapter, "_resolve_citations_final_pass", new=AsyncMock()
        ), caplog.at_level(logging.WARNING):
            await slack_adapter.handle_task_complete(response_context)

        assert not any(
            "Timeout waiting for queue to complete" in record.message
            for record in caplog.records
        ), "Should not log timeout warning on the happy path"
