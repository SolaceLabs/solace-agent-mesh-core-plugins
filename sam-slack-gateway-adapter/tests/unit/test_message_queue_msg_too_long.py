"""
Red/green tests for the Slack `msg_too_long` failure path observed on task
gdk-task-65dbbce024c744e9a68b3de518e73443 (2026-04-26 10:21 UTC).

Symptom: a streaming text buffer was allowed to grow past Slack's chat.update
text limit (~40K chars).  The resulting `msg_too_long` error from chat.update
(a) crashed the queue processor when it fired during the StopSignal flush,
and (b) aborted file-upload handling before `files_getUploadURLExternal` was
even called -- so the deliverable artifact never reached Slack.

These tests pin the contract:
  * The queue must never send a `chat.update`/`chat.postMessage` with text
    exceeding Slack's per-message limit.
  * A failed text-buffer flush during a file upload must NOT prevent the
    file-upload API calls from running.
  * A failed text-buffer flush during stop must NOT propagate as a fatal
    error from the queue processor.

Run:
    cd sam-slack-gateway-adapter
    uv run pytest tests/unit/test_message_queue_msg_too_long.py -v
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from slack_sdk.errors import SlackApiError

from sam_slack_gateway_adapter.message_queue import SlackMessageQueue


# Slack accepts up to 40_000 chars in chat.{postMessage,update} `text`.
SLACK_MAX_MESSAGE_LENGTH = 40_000


# --- Helpers ---------------------------------------------------------------


def _make_msg_too_long_error() -> SlackApiError:
    """Build a SlackApiError that mimics a real msg_too_long failure."""
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.data = {"ok": False, "error": "msg_too_long"}
    response.get = lambda key, default=None: response.data.get(key, default)
    response.__getitem__ = lambda self_, key: response.data[key]  # type: ignore[assignment]
    return SlackApiError(
        message="The request to the Slack API failed.",
        response=response,
    )


def _make_slack_client(*, fail_chat_update_when_over: int | None = None) -> AsyncMock:
    """
    Build a slack client mock.

    If `fail_chat_update_when_over` is set, chat_update raises msg_too_long
    whenever the `text` argument exceeds that many characters (mirroring
    Slack's real server-side behavior).
    """
    client = AsyncMock()
    client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "111.222"})
    client.chat_delete = AsyncMock(return_value={"ok": True})
    client.files_getUploadURLExternal = AsyncMock(
        return_value={"upload_url": "https://upload.test", "file_id": "F-test"}
    )
    client.files_completeUploadExternal = AsyncMock(return_value={"ok": True})

    # Make files.info return the file as "visible" immediately so the
    # upload handler doesn't sit in its polling loop.
    client.files_info = AsyncMock(
        return_value={
            "ok": True,
            "file": {"shares": {"private": {"C-channel": [{"ts": "1"}]}}},
        }
    )

    if fail_chat_update_when_over is not None:
        threshold = fail_chat_update_when_over

        async def _chat_update(**kwargs: Any) -> dict:
            text = kwargs.get("text", "") or ""
            if len(text) > threshold:
                raise _make_msg_too_long_error()
            return {"ok": True, "ts": kwargs.get("ts", "111.222")}

        client.chat_update = AsyncMock(side_effect=_chat_update)
    else:
        client.chat_update = AsyncMock(return_value={"ok": True, "ts": "111.222"})
    return client


def _make_adapter() -> MagicMock:
    """Adapter mock with `_format_text` as identity (no transformation)."""
    adapter = MagicMock()
    adapter._format_text = MagicMock(side_effect=lambda text, task_id=None: text)
    adapter.context = MagicMock()
    return adapter


def _make_queue(client: AsyncMock, channel: str = "C-channel") -> SlackMessageQueue:
    return SlackMessageQueue(
        task_id="gdk-task-test",
        slack_client=client,
        channel_id=channel,
        thread_ts="111.000",
        adapter=_make_adapter(),
    )


# Avoid the global rate limiter sleeping during tests.
@pytest.fixture(autouse=True)
def _patch_rate_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    from sam_slack_gateway_adapter import message_queue

    async def _no_throttle(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        message_queue.GlobalRateLimiter, "throttle", _no_throttle, raising=True
    )
    # Short-circuit asyncio.sleep so retry/backoff/poll loops don't slow tests.
    real_sleep = asyncio.sleep

    async def _fast_sleep(seconds: float) -> None:
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    # The file-upload path POSTs the binary to a Slack-issued upload URL via
    # the `requests` library; stub it so the test never touches the network.
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock(return_value=None)
    monkeypatch.setattr(requests, "post", MagicMock(return_value=fake_response))


# --- Tests -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_update_never_exceeds_slack_limit() -> None:
    """
    RED before fix: the queue calls `chat.update` with the raw text_buffer,
    which can exceed Slack's 40_000-char text limit.  This test asserts that
    every call into the slack client is at-or-under the limit.

    GREEN after fix: text is truncated to the limit before being sent.
    """
    client = _make_slack_client()
    queue = _make_queue(client)
    await queue.start()

    # Push a single oversized chunk — well above Slack's 40K limit.
    huge_text = "x" * 60_000
    await queue.queue_text_update(huge_text)
    await queue.stop()

    sent_payloads: list[str] = []
    for call in client.chat_postMessage.await_args_list:
        sent_payloads.append(call.kwargs.get("text", ""))
    for call in client.chat_update.await_args_list:
        sent_payloads.append(call.kwargs.get("text", ""))

    assert sent_payloads, "expected at least one Slack send"
    too_long = [len(p) for p in sent_payloads if len(p) > SLACK_MAX_MESSAGE_LENGTH]
    assert not too_long, (
        f"queue sent payloads exceeding Slack's text limit: {too_long}; "
        f"limit={SLACK_MAX_MESSAGE_LENGTH}"
    )


@pytest.mark.asyncio
async def test_file_upload_proceeds_when_text_flush_fails_with_msg_too_long() -> None:
    """
    RED before fix: when a streamed text_buffer is too large, the pre-upload
    chat.update flush in `_handle_file_upload` raises and the file upload
    is abandoned — the user never receives the artifact.

    GREEN after fix: the file upload still calls
    files_getUploadURLExternal + files_completeUploadExternal even if the
    text flush fails.
    """
    # Server only accepts payloads ≤ Slack's text limit.
    client = _make_slack_client(fail_chat_update_when_over=SLACK_MAX_MESSAGE_LENGTH)
    queue = _make_queue(client)
    await queue.start()

    # Seed an established streaming message so the text path uses chat.update.
    queue.current_text_message_ts = "111.222"
    queue.text_buffer = "y" * 60_000  # > 40K -> would trip msg_too_long server-side

    # Now queue a real artifact (the mani report).  The pre-upload flush
    # of the oversized buffer will be attempted; it must not block the
    # file upload.
    await queue.queue_file_upload(
        filename="mani_notable_cases_report.md",
        content_bytes=b"# Notable Support Cases - Mani\n" * 1000,
        initial_comment="Attached file: mani_notable_cases_report.md",
    )
    await queue.stop()

    assert client.files_getUploadURLExternal.await_count >= 1, (
        "files_getUploadURLExternal was never called -- the file upload was "
        "skipped because the pre-flush chat.update failed with msg_too_long"
    )
    assert client.files_completeUploadExternal.await_count >= 1, (
        "files_completeUploadExternal was never called -- file upload incomplete"
    )


@pytest.mark.asyncio
async def test_processor_keeps_running_after_msg_too_long_text_update(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    RED before fix: when chat.update fires msg_too_long during the StopSignal
    final-flush, the exception escapes the per-op try/except and triggers the
    outer "Fatal error in queue processor" path -- killing the queue.  Even
    when the failure is during stop, we should not log "Fatal error", because
    a permanent text-payload error must not be treated as a queue-fatal.

    GREEN after fix: a `msg_too_long` from chat.update is treated as a
    permanent, non-fatal failure (the message couldn't be updated, but the
    processor should not log the outer "Fatal error" path).
    """
    import logging as _logging

    client = _make_slack_client(fail_chat_update_when_over=SLACK_MAX_MESSAGE_LENGTH)
    queue = _make_queue(client)

    caplog.set_level(_logging.ERROR, logger="sam_slack_gateway_adapter.message_queue")

    await queue.start()
    # Stage state that triggers chat.update on stop with an oversized text.
    queue.current_text_message_ts = "111.222"
    queue.text_buffer = "z" * 60_000
    await queue.stop()

    fatal = [
        r for r in caplog.records
        if "Fatal error in queue processor" in r.getMessage()
    ]
    assert not fatal, (
        "queue processor exited via the outer fatal-error path on a "
        "msg_too_long flush -- it should treat that as a non-fatal "
        "permanent error.  Log records:\n"
        + "\n".join(r.getMessage() for r in fatal)
    )
