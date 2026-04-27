"""
Red/green tests for the Slack `msg_too_long` failure path observed on task
gdk-task-65dbbce024c744e9a68b3de518e73443 (2026-04-26 10:21 UTC).

Symptom: a streaming text buffer was allowed to grow past Slack's chat.update
text limit (~40K chars).  The resulting `msg_too_long` error from chat.update
(a) crashed the queue processor when it fired during the StopSignal flush,
and (b) aborted file-upload handling before `files_getUploadURLExternal` was
even called -- so the deliverable artifact never reached Slack.

These tests pin the contract:
  * Slack receives no payload above SLACK_MAX_MESSAGE_LENGTH.
  * A failed text-buffer flush during a file upload does NOT prevent the
    file-upload API calls from running.
  * A failed text-buffer flush during stop does NOT propagate as a fatal
    error from the queue processor.
  * Overflow splits are LOSSLESS: every char of the input ends up in some
    Slack message (no truncation at either end).
  * Reactive overflow recursion is bounded -- a server that keeps replying
    `msg_too_long` cannot trigger an infinite loop.

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

from sam_slack_gateway_adapter.message_queue import (
    SLACK_MAX_MESSAGE_LENGTH,
    SlackMessageQueue,
)


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

    # Real Slack returns a unique `ts` per posted message; we mimic that so
    # tests can correlate later chat_update calls with the message they
    # mutate.
    post_counter = {"n": 0}

    async def _chat_postMessage(**kwargs: Any) -> dict:
        post_counter["n"] += 1
        return {"ok": True, "ts": f"ts-{post_counter['n']}"}

    client.chat_postMessage = AsyncMock(side_effect=_chat_postMessage)
    client.chat_delete = AsyncMock(return_value={"ok": True})
    client.files_getUploadURLExternal = AsyncMock(
        return_value={"upload_url": "https://upload.test", "file_id": "F-test"}
    )
    client.files_completeUploadExternal = AsyncMock(return_value={"ok": True})

    # files.info returns the file as visible immediately so the upload
    # handler doesn't sit in its polling loop.
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
            return {"ok": True, "ts": kwargs.get("ts", "ts-0")}

        client.chat_update = AsyncMock(side_effect=_chat_update)
    else:

        async def _chat_update_ok(**kwargs: Any) -> dict:
            return {"ok": True, "ts": kwargs.get("ts", "ts-0")}

        client.chat_update = AsyncMock(side_effect=_chat_update_ok)
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


def _all_payloads(client: AsyncMock) -> list[str]:
    """Collect every `text` payload sent through chat_postMessage / chat_update."""
    payloads = []
    for call in client.chat_postMessage.await_args_list:
        payloads.append(call.kwargs.get("text", ""))
    for call in client.chat_update.await_args_list:
        payloads.append(call.kwargs.get("text", ""))
    return payloads


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
    """No payload sent to Slack may exceed SLACK_MAX_MESSAGE_LENGTH."""
    client = _make_slack_client()
    queue = _make_queue(client)
    await queue.start()

    huge_text = "x" * 60_000
    await queue.queue_text_update(huge_text)
    await queue.stop()

    payloads = _all_payloads(client)
    assert payloads, "expected at least one Slack send"
    too_long = [len(p) for p in payloads if len(p) > SLACK_MAX_MESSAGE_LENGTH]
    assert not too_long, (
        f"queue sent payloads exceeding SLACK_MAX_MESSAGE_LENGTH "
        f"({SLACK_MAX_MESSAGE_LENGTH}): {too_long}"
    )


@pytest.mark.asyncio
async def test_file_upload_proceeds_when_text_flush_fails_with_msg_too_long() -> None:
    """
    Even if the streamed status text somehow can't be flushed, the file
    upload (the artifact the user actually asked for) must still happen.
    """
    client = _make_slack_client(fail_chat_update_when_over=SLACK_MAX_MESSAGE_LENGTH)
    queue = _make_queue(client)
    await queue.start()

    queue.current_text_message_ts = "111.222"
    queue.text_buffer = "y" * 60_000

    await queue.queue_file_upload(
        filename="mani_notable_cases_report.md",
        content_bytes=b"# Notable Support Cases - Mani\n" * 1000,
        initial_comment="Attached file: mani_notable_cases_report.md",
    )
    await queue.stop()

    assert client.files_getUploadURLExternal.await_count >= 1, (
        "files_getUploadURLExternal was never called -- the file upload was "
        "skipped because the pre-flush chat.update failed"
    )
    assert client.files_completeUploadExternal.await_count >= 1, (
        "files_completeUploadExternal was never called -- file upload incomplete"
    )


@pytest.mark.asyncio
async def test_processor_keeps_running_after_msg_too_long_text_update(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    A msg_too_long during the StopSignal final-flush must not propagate
    to the outer "Fatal error in queue processor" path.
    """
    import logging as _logging

    client = _make_slack_client(fail_chat_update_when_over=SLACK_MAX_MESSAGE_LENGTH)
    queue = _make_queue(client)

    caplog.set_level(_logging.ERROR, logger="sam_slack_gateway_adapter.message_queue")

    await queue.start()
    queue.current_text_message_ts = "111.222"
    queue.text_buffer = "z" * 60_000
    await queue.stop()

    fatal = [
        r for r in caplog.records
        if "Fatal error in queue processor" in r.getMessage()
    ]
    assert not fatal, (
        "queue processor exited via the outer fatal-error path on a "
        "msg_too_long flush.  Log records:\n"
        + "\n".join(r.getMessage() for r in fatal)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "buffer_size",
    [
        # Under the memory-safety cap (text_buffer_max_size = 100K).  Hits
        # only the in-method overflow loop after _format_text.
        100_000,
        # Well above the cap.  Without a lossless cap-drain, the head-slice
        # at the top of _handle_text_update would silently drop ~50K chars
        # from the beginning of the stream.
        250_000,
    ],
    ids=["under_cap_100k", "over_cap_250k"],
)
async def test_overflow_split_is_lossless_no_truncation_at_either_end(
    buffer_size: int,
) -> None:
    """
    A long response that doesn't fit in a single Slack message MUST be
    split across multiple messages so that no characters are dropped --
    not at the head, not at the tail, AND not by the buffer-size memory
    cap that fires when streaming outpaces the queue drain.

    We feed a deterministic buffer and reconstruct the final state of
    every Slack message; the concatenation must equal the original
    byte-for-byte.
    """
    client = _make_slack_client()
    queue = _make_queue(client)
    await queue.start()

    original = "".join(chr(0x21 + (i % 90)) for i in range(buffer_size))
    assert len(original) == buffer_size

    await queue.queue_text_update(original)
    await queue.stop()

    payloads = _all_payloads(client)
    assert payloads, "expected at least one send"
    for p in payloads:
        assert len(p) <= SLACK_MAX_MESSAGE_LENGTH, (
            f"a payload of {len(p)} chars exceeds Slack's limit"
        )

    # Walk every Slack call in real call-order, keyed by the message `ts`
    # the call applies to.  `chat_postMessage` mints a fresh ts (the mock
    # returns "ts-1", "ts-2", ... per call) and `chat_update(ts=...)`
    # mutates the existing message with that ts.  The LAST text per ts is
    # what the user sees.
    next_post_ts = 0
    last_text_per_ts: dict[str, str] = {}
    order: list[str] = []  # ts insertion order
    for call in client.mock_calls:
        name = call[0]
        kwargs = call[2] if len(call) > 2 else {}
        if name == "chat_postMessage":
            next_post_ts += 1
            ts = f"ts-{next_post_ts}"
            order.append(ts)
            last_text_per_ts[ts] = kwargs.get("text", "")
        elif name == "chat_update":
            ts = kwargs.get("ts", "")
            if ts not in last_text_per_ts:
                order.append(ts)
            last_text_per_ts[ts] = kwargs.get("text", "")

    final_messages = [last_text_per_ts[ts] for ts in order]
    reconstructed = "".join(final_messages)
    assert reconstructed == original, (
        f"content was lost across the overflow split.\n"
        f"  original len={len(original)}, reconstructed len={len(reconstructed)}\n"
        f"  messages sent={len(final_messages)} "
        f"sizes={[len(m) for m in final_messages]}"
    )


@pytest.mark.asyncio
async def test_reactive_overflow_recursion_is_bounded() -> None:
    """
    If Slack keeps replying msg_too_long no matter what we send, the
    reactive overflow handler must NOT recurse infinitely.  Bounded
    behavior is proven by completing in finite time and a finite call
    count.
    """
    client = AsyncMock()
    client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "111.222"})
    client.chat_update = AsyncMock(side_effect=_make_msg_too_long_error)
    client.chat_delete = AsyncMock(return_value={"ok": True})
    client.files_info = AsyncMock(
        return_value={
            "ok": True,
            "file": {"shares": {"private": {"C-channel": [{"ts": "1"}]}}},
        }
    )

    queue = _make_queue(client)
    queue._max_overflow_recursions = 3  # tighten for the test

    await queue.start()
    queue.current_text_message_ts = "111.222"
    queue.text_buffer = "q" * 100_000
    # If recursion is unbounded, this either hangs (caught by timeout) or
    # explodes the chat_update call count.
    await asyncio.wait_for(queue.stop(), timeout=5.0)

    assert client.chat_update.await_count <= 50, (
        f"chat_update called {client.chat_update.await_count} times -- "
        "reactive overflow recursion appears unbounded"
    )
