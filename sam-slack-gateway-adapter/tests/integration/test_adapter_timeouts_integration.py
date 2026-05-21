"""
Integration tests for hang-recovery in the Slack adapter.

These complement the structural unit tests in
``tests/unit/test_adapter_timeouts.py`` by exercising the real code paths:

  * A real ``SlackMessageQueue`` with a real background worker coroutine
  * Real ``asyncio.wait_for`` with real timing
  * A Slack HTTP client whose chat methods genuinely hang (await sleep)

The production timeout (``QUEUE_DRAIN_TIMEOUT_SEC = 60.0``) is patched down to
a small value so the test runs in ~1 second instead of ~60. The fix
(DATAGO-137322) is verified by behavior: ``handle_task_complete`` must return
within the bounded window even when the queue worker is stuck on a Slack call
that never returns.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sam_slack_gateway_adapter import adapter as adapter_mod
from sam_slack_gateway_adapter.adapter import SlackAdapter, SlackAdapterConfig
from sam_slack_gateway_adapter.message_queue import SlackMessageQueue
from solace_agent_mesh.gateway.adapter.types import (
    GatewayContext,
    ResponseContext,
)


# Patched value of QUEUE_DRAIN_TIMEOUT_SEC for these tests. Small enough to
# keep CI fast, but large enough to absorb scheduler jitter on shared runners.
TEST_DRAIN_TIMEOUT_SEC = 0.5

# Hard upper bound for the whole test to fail fast on a regression instead of
# stalling the suite. Must exceed TEST_DRAIN_TIMEOUT_SEC by a healthy margin.
TEST_OUTER_DEADLINE_SEC = 5.0


@pytest.fixture
def gateway_context():
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
def hanging_slack_client():
    """A Slack client whose chat methods never return — simulates the real bug."""
    client = MagicMock()

    async def hang_forever(*args, **kwargs):
        await asyncio.sleep(3600)

    # Anything the queue worker might call during a text update path:
    client.chat_postMessage = AsyncMock(side_effect=hang_forever)
    client.chat_update = AsyncMock(side_effect=hang_forever)
    return client


@pytest.fixture
def adapter_with_hung_queue(gateway_context, hanging_slack_client):
    """Adapter wired up with a REAL SlackMessageQueue + real worker.

    The queue is seeded with one text update before ``handle_task_complete``
    is called, so the worker is actively awaiting a hung Slack API call by
    the time the test triggers the timeout-protected drain.
    """
    adapter = SlackAdapter()
    adapter.context = gateway_context
    adapter.slack_app = MagicMock()
    adapter.slack_app.client = hanging_slack_client
    return adapter


@pytest.fixture
def response_ctx():
    return ResponseContext(
        task_id="task-int-stuck",
        session_id="session-int",
        user_id="user-int",
        platform_context={"channel_id": "C-int", "thread_ts": "1.0"},
    )


@pytest.mark.asyncio
async def test_handle_task_complete_recovers_from_hung_slack_call(
    adapter_with_hung_queue, response_ctx, hanging_slack_client, caplog
):
    """End-to-end: real queue + real worker + hung Slack client → adapter must
    recover within the bounded timeout and proceed to ACK.

    This is the regression test for DATAGO-137322. Without the fix, the
    background worker hangs on chat.postMessage forever, queue.join() never
    returns, and handle_task_complete blocks indefinitely.
    """
    task_id = response_ctx.task_id

    # Build a real SlackMessageQueue with the hanging client.
    real_queue = SlackMessageQueue(
        task_id=task_id,
        slack_client=hanging_slack_client,
        channel_id=response_ctx.platform_context["channel_id"],
        thread_ts=response_ctx.platform_context["thread_ts"],
        adapter=adapter_with_hung_queue,
    )
    await real_queue.start()
    adapter_with_hung_queue.message_queues[task_id] = real_queue

    # Seed one text update so the worker is actively stuck on a hung Slack
    # call by the time handle_task_complete runs.
    await real_queue.queue_text_update("Hello from the agent")

    # Give the worker a moment to pull the op and start the hanging call.
    await asyncio.sleep(0.05)

    # Mock the queue's stop() — it has its own 60s wait_for on the processor
    # task in message_queue.py, which is a separate concern from the
    # wait_until_complete hang under test here.
    real_queue.stop = AsyncMock()

    try:
        with patch.object(
            adapter_mod, "QUEUE_DRAIN_TIMEOUT_SEC", TEST_DRAIN_TIMEOUT_SEC
        ), patch.object(
            adapter_with_hung_queue,
            "_resolve_citations_final_pass",
            new=AsyncMock(),
        ), patch(
            "sam_slack_gateway_adapter.adapter.utils.send_slack_message",
            new=AsyncMock(),
        ), patch(
            "sam_slack_gateway_adapter.adapter.utils.update_slack_message",
            new=AsyncMock(),
        ), caplog.at_level(logging.WARNING):
            # Outer deadline: if the fix is removed, this fails fast instead
            # of stalling the suite.
            await asyncio.wait_for(
                adapter_with_hung_queue.handle_task_complete(response_ctx),
                timeout=TEST_OUTER_DEADLINE_SEC,
            )
    finally:
        # Force-cancel the still-stuck worker so the test loop can shut down
        # cleanly. In production this happens via cleanup(); here we do it
        # explicitly because the worker is wedged on asyncio.sleep(3600).
        if real_queue.processor_task and not real_queue.processor_task.done():
            real_queue.processor_task.cancel()
            try:
                await real_queue.processor_task
            except (asyncio.CancelledError, BaseException):
                pass

    # Behavioral assertion: the documented warning was emitted.
    assert any(
        "Timeout waiting for queue to complete" in record.message
        and task_id in record.message
        for record in caplog.records
    ), (
        "handle_task_complete recovered from the hung queue but did not log "
        "the expected timeout warning. Without that log line, operators will "
        "have no signal that a task was abandoned."
    )


@pytest.mark.asyncio
async def test_handle_task_complete_completes_normally_when_queue_drains(
    adapter_with_hung_queue, response_ctx, caplog
):
    """Happy path: a real queue that drains quickly must produce no warning."""
    task_id = response_ctx.task_id

    # Use a client whose chat methods return immediately (no hang).
    fast_client = MagicMock()
    fast_client.chat_postMessage = AsyncMock(
        return_value={"ok": True, "ts": "1.1"}
    )
    fast_client.chat_update = AsyncMock(return_value={"ok": True})

    real_queue = SlackMessageQueue(
        task_id=task_id,
        slack_client=fast_client,
        channel_id=response_ctx.platform_context["channel_id"],
        thread_ts=response_ctx.platform_context["thread_ts"],
        adapter=adapter_with_hung_queue,
    )
    await real_queue.start()
    adapter_with_hung_queue.message_queues[task_id] = real_queue

    try:
        with patch.object(
            adapter_mod, "QUEUE_DRAIN_TIMEOUT_SEC", TEST_DRAIN_TIMEOUT_SEC
        ), patch.object(
            adapter_with_hung_queue,
            "_resolve_citations_final_pass",
            new=AsyncMock(),
        ), patch(
            "sam_slack_gateway_adapter.adapter.utils.send_slack_message",
            new=AsyncMock(),
        ), patch(
            "sam_slack_gateway_adapter.adapter.utils.update_slack_message",
            new=AsyncMock(),
        ), caplog.at_level(logging.WARNING):
            await asyncio.wait_for(
                adapter_with_hung_queue.handle_task_complete(response_ctx),
                timeout=TEST_OUTER_DEADLINE_SEC,
            )
    finally:
        await real_queue.stop()

    assert not any(
        "Timeout waiting for queue to complete" in record.message
        for record in caplog.records
    ), "Happy-path drain must not emit a timeout warning"
