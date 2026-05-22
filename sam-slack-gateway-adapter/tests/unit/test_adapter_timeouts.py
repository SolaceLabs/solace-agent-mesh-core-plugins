"""
Unit tests for hang-recovery behavior in the Slack adapter.

A hung Slack API call must not wedge the broker consumer flow. Three
complementary defenses are verified here:

1. The Slack ``AsyncWebClient`` is created with a finite HTTP timeout
   and the ``Bolt-Async/{version}`` user-agent prefix is preserved.
2. ``handle_task_complete`` bounds the per-task queue drain with
   ``asyncio.wait_for`` so a stuck queue worker can't block the broker ACK.
3. The synchronous ``requests.post`` used for Slack file uploads is
   called with an explicit ``timeout=`` so a stalled upload connection
   can't hang the queue worker indefinitely (the slack-sdk's async
   methods have a 30s default, but ``requests`` does not).
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
from sam_slack_gateway_adapter.message_queue import (
    FileUploadOp,
    SlackMessageQueue,
)
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

    @pytest.mark.asyncio
    async def test_init_preserves_bolt_user_agent_prefix(
        self, mock_gateway_context
    ):
        """init() must set ``user_agent_prefix='Bolt-Async/{version}'`` so Slack
        telemetry can continue to identify this adapter as a Bolt client.

        Without this, constructing AsyncWebClient(...) directly drops the
        prefix that slack_bolt's create_async_web_client() would have added
        when AsyncApp(token=...) built its own client.
        """
        adapter = SlackAdapter()

        with patch(
            "sam_slack_gateway_adapter.adapter.AsyncSocketModeHandler"
        ), patch.object(SlackAdapter, "_register_handlers"), patch(
            "sam_slack_gateway_adapter.adapter.asyncio.create_task"
        ):
            await adapter.init(mock_gateway_context)

        client = adapter.slack_app.client
        # AsyncWebClient stores the assembled UA string (prefix + sdk pieces)
        # as `client.headers["User-Agent"]`. The "Bolt-Async/" piece must
        # appear somewhere in that combined string.
        ua = (client.headers or {}).get("User-Agent", "")
        assert "Bolt-Async/" in ua, (
            f"Slack AsyncWebClient must include 'Bolt-Async/' in User-Agent, "
            f"got User-Agent={ua!r}"
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


class TestFileUploadHttpTimeout:
    """Verify Fix 3: the synchronous ``requests.post`` for Slack file uploads
    is invoked with a finite timeout.

    The slack-sdk's async methods default to ``timeout=30`` at the HTTP
    layer, but the file-upload path takes a different route: it grabs an
    upload URL from Slack then uses ``requests.post`` (sync, run via
    ``asyncio.to_thread``) to send the bytes. ``requests`` has NO default
    timeout, so without an explicit one a stalled upload-server connection
    hangs the queue worker forever. This is the most likely culprit for
    the recurring slack-gateway wedges.
    """

    @pytest.mark.asyncio
    async def test_file_upload_passes_explicit_timeout_to_requests_post(self):
        """``_handle_file_upload`` must invoke ``requests.post`` with a
        finite ``timeout=`` kwarg.
        """
        # Real SlackMessageQueue (no Slack network involvement — every
        # outgoing call is mocked).
        mock_client = MagicMock()
        mock_client.files_getUploadURLExternal = AsyncMock(
            return_value={
                "upload_url": "https://files.slack.com/upload/fake",
                "file_id": "F_FAKE_ID",
            }
        )
        mock_client.files_completeUploadExternal = AsyncMock(
            return_value={"ok": True}
        )

        queue = SlackMessageQueue(
            task_id="task-upload-timeout",
            slack_client=mock_client,
            channel_id="C_FAKE",
            thread_ts="1.1",
            adapter=MagicMock(),
        )

        # Mock requests.post to record its call kwargs without actually
        # making a network call. Return a fake response that passes
        # raise_for_status().
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()

        # `requests` is imported inside _handle_file_upload (local import),
        # so it's not an attribute of the message_queue module. Patch the
        # `requests` module's `post` directly — the function will see the
        # patched value when it accesses `requests.post`.
        # Also patch _wait_for_file_visible: it polls files.info repeatedly
        # for up to 30s, which we don't need to exercise here.
        with patch(
            "requests.post", return_value=fake_response
        ) as mock_post, patch.object(
            queue, "_wait_for_file_visible", new=AsyncMock()
        ):
            await queue._handle_file_upload(
                FileUploadOp(
                    filename="report.txt",
                    content_bytes=b"hello world",
                    initial_comment=None,
                )
            )

        # Find the call to the upload URL (the one we care about — the only
        # requests.post call in this code path).
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert "timeout" in kwargs, (
            "requests.post for Slack file upload MUST be called with an "
            "explicit timeout= kwarg; without it the call can hang forever "
            "and wedge the queue worker."
        )
        assert isinstance(kwargs["timeout"], (int, float)), (
            f"timeout must be numeric, got {type(kwargs['timeout']).__name__}"
        )
        assert kwargs["timeout"] > 0, (
            f"timeout must be positive, got {kwargs['timeout']}"
        )
