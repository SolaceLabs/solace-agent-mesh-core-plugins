"""
Sequential message queue for Slack to ensure proper ordering of text and file posts.

This module provides a per-task queue that manages all Slack API operations,
ensuring that files are fully visible in the channel before subsequent messages
are posted, preventing race conditions and out-of-order message appearance.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, TypeVar

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

if TYPE_CHECKING:
    from .adapter import SlackAdapter

log = logging.getLogger(__name__)

# Type variable for generic return type
T = TypeVar("T")

# Rate limiting constants for retry logic
DEFAULT_MAX_RETRIES = 5
# Slack always returns Retry-After header, so this is just a fallback
DEFAULT_RETRY_DELAY = 3.0  # seconds - constant delay between retries
DEFAULT_MAX_RETRY_DELAY = 30.0  # seconds - cap for Retry-After header values

# Slack Rate Limit Tiers
# https://api.slack.com/docs/rate-limits
#
# Rate limits are "per API method per workspace/team per app"
#
# Tier 1: 1+ per minute (access infrequently, small burst tolerance)
# Tier 2: 20+ per minute (most methods, occasional bursts allowed)
# Tier 3: 50+ per minute (paginating collections, sporadic bursts welcome)
# Tier 4: 100+ per minute (large request quota, generous burst behavior)
# Special Tier: Varies - unique conditions per method
#
# chat.postMessage is SPECIAL TIER: 1 message per second per CHANNEL,
# plus a workspace-wide limit. Short bursts >1 allowed but not guaranteed.
#
# Slack recommends: Design for 1 request per second, allow temporary bursts.
# When rate limited, Slack returns HTTP 429 with Retry-After header.

from enum import Enum


class SlackApiTier(Enum):
    """Slack API rate limit tiers."""
    TIER_1 = "tier_1"      # 1+ per minute (infrequent access)
    TIER_2 = "tier_2"      # 20+ per minute (most write methods)
    TIER_3 = "tier_3"      # 50+ per minute (read methods, pagination)
    TIER_4 = "tier_4"      # 100+ per minute (high volume)
    SPECIAL = "special"    # Unique rate limiting (e.g., chat.postMessage)


# Minimum intervals between calls for each tier (in seconds)
# Using conservative values based on Slack's recommendation of 1 req/sec
# with allowance for temporary bursts
TIER_INTERVALS = {
    # Tier 1: Very infrequent - be extra conservative
    SlackApiTier.TIER_1: 2.0,
    # Tier 2: 20/min = 1 every 3 seconds, but allow some burst
    SlackApiTier.TIER_2: 1.5,
    # Tier 3: 50/min = 1 every 1.2 seconds
    SlackApiTier.TIER_3: 1.0,
    # Tier 4: 100/min = 1 every 0.6 seconds
    SlackApiTier.TIER_4: 0.5,
    # Special: 1 per second per channel (we track globally, so be conservative)
    SlackApiTier.SPECIAL: 1.0,
}

# Map Slack API methods to their rate limit tiers
# Reference: https://api.slack.com/docs/rate-limits
METHOD_TIERS = {
    # Special Tier - Unique rate limiting per channel
    "chat.postMessage": SlackApiTier.SPECIAL,  # 1/sec per channel + workspace limit
    "chat.postEphemeral": SlackApiTier.SPECIAL,

    # Tier 2 - Most write methods (20+ per minute)
    "chat.update": SlackApiTier.TIER_2,
    "chat.delete": SlackApiTier.TIER_2,
    "reactions.add": SlackApiTier.TIER_2,
    "reactions.remove": SlackApiTier.TIER_2,
    "files.completeUploadExternal": SlackApiTier.TIER_2,

    # Tier 3 - Most read methods and file operations (50+ per minute)
    "files.info": SlackApiTier.TIER_3,
    "files.getUploadURLExternal": SlackApiTier.TIER_3,
    "users.info": SlackApiTier.TIER_3,
    "users.profile.get": SlackApiTier.TIER_3,
    "conversations.info": SlackApiTier.TIER_3,
    "conversations.list": SlackApiTier.TIER_2,  # Tier 2 per docs

    # Tier 4 - High volume (default for unknown methods)
}

# Default tier for methods not in the map - use Tier 3 as safe default
DEFAULT_TIER = SlackApiTier.TIER_3


def get_tier_for_method(method_name: str) -> SlackApiTier:
    """Get the rate limit tier for a Slack API method."""
    return METHOD_TIERS.get(method_name, DEFAULT_TIER)


class GlobalRateLimiter:
    """
    Global rate limiter for Slack API calls with per-tier tracking.

    This class provides a singleton-like rate limiter that all
    message queues share to ensure we don't exceed global rate limits even
    when multiple tasks are running concurrently.

    Each rate limit tier is tracked separately, as Slack enforces limits
    per-method-tier.

    Thread-safe using asyncio.Lock for coordination between concurrent tasks.
    """

    _instance: Optional["GlobalRateLimiter"] = None
    _lock: asyncio.Lock = None  # Will be created on first use

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        # Track last call time for each tier separately
        self._last_call_times: Dict[SlackApiTier, float] = {
            tier: 0.0 for tier in SlackApiTier
        }
        # Lock must be created in async context, so we'll create it lazily
        self._throttle_lock: Optional[asyncio.Lock] = None

    async def _get_lock(self) -> asyncio.Lock:
        """Get or create the throttle lock (must be called from async context)."""
        if self._throttle_lock is None:
            self._throttle_lock = asyncio.Lock()
        return self._throttle_lock

    async def throttle(
        self,
        method_name: Optional[str] = None,
        tier: Optional[SlackApiTier] = None,
        is_message_update: bool = False,  # Kept for backward compatibility
    ) -> None:
        """
        Apply global throttling before making a Slack API call.

        This ensures we don't exceed Slack's rate limits by enforcing
        minimum intervals between API calls across ALL concurrent tasks.

        Args:
            method_name: The Slack API method being called (e.g., "chat.update")
            tier: Explicitly specify the tier (overrides method_name lookup)
            is_message_update: Deprecated - use method_name or tier instead.
                              Kept for backward compatibility (maps to TIER_2)
        """
        # Determine the tier to use
        if tier is not None:
            effective_tier = tier
        elif method_name is not None:
            effective_tier = get_tier_for_method(method_name)
        elif is_message_update:
            # Backward compatibility: is_message_update maps to TIER_2
            effective_tier = SlackApiTier.TIER_2
        else:
            # Default to TIER_3 for general API calls
            effective_tier = SlackApiTier.TIER_3

        min_interval = TIER_INTERVALS[effective_tier]

        lock = await self._get_lock()
        async with lock:
            current_time = time.monotonic()
            last_call_time = self._last_call_times[effective_tier]
            time_since_last_call = current_time - last_call_time
            required_wait = min_interval - time_since_last_call

            if required_wait > 0:
                log.debug(
                    "[GlobalRateLimiter] Throttling %s (tier=%s): waiting %.2fs",
                    method_name or "unknown",
                    effective_tier.value,
                    required_wait,
                )
                await asyncio.sleep(required_wait)

            # Update timestamp for this tier
            self._last_call_times[effective_tier] = time.monotonic()


# Global rate limiter instance - shared across all message queues
_global_rate_limiter: Optional[GlobalRateLimiter] = None


def get_global_rate_limiter() -> GlobalRateLimiter:
    """Get the global rate limiter instance."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = GlobalRateLimiter()
    return _global_rate_limiter


async def retry_with_backoff(
    func: Callable[..., T],
    *args,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    max_retry_delay: float = DEFAULT_MAX_RETRY_DELAY,
    operation_name: str = "Slack API call",
    **kwargs,
) -> T:
    """
    Execute an async function with constant delay retry for rate limiting.

    This function handles Slack API rate limiting (429 errors) by:
    1. Respecting the Retry-After header when provided (Slack always sends this)
    2. Using a constant delay as fallback when no header is present
    3. Limiting total retries to prevent infinite loops

    Using constant delay instead of exponential backoff to avoid the "burst-wait-burst"
    pattern.

    Args:
        func: The async function to execute
        *args: Positional arguments to pass to the function
        max_retries: Maximum number of retry attempts
        retry_delay: Constant delay between retries (fallback if no Retry-After header)
        max_retry_delay: Maximum delay to wait (caps Retry-After header values)
        operation_name: Name of the operation for logging
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The result of the function call

    Raises:
        SlackApiError: If all retries are exhausted or a non-retryable error occurs
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except SlackApiError as e:
            last_exception = e
            error_code = e.response.get("error", "") if e.response else ""

            # Check if this is a rate limit error
            if error_code == "ratelimited" or (
                hasattr(e.response, "status_code") and e.response.status_code == 429
            ):
                if attempt >= max_retries:
                    log.error(
                        "[RateLimit] %s failed after %d retries due to rate limiting",
                        operation_name,
                        max_retries,
                    )
                    raise

                # Try to get Retry-After header from response
                # Slack always returns this header with 429 errors
                retry_after = None
                if e.response and hasattr(e.response, "headers"):
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            retry_after = float(retry_after)
                        except (ValueError, TypeError):
                            retry_after = None

                # Use Retry-After if available, otherwise use constant delay
                # Cap the wait time to prevent excessively long waits
                wait_time = retry_after if retry_after else retry_delay
                wait_time = min(wait_time, max_retry_delay)

                log.warning(
                    "[RateLimit] %s rate limited (attempt %d/%d). "
                    "Waiting %.2f seconds before retry%s...",
                    operation_name,
                    attempt + 1,
                    max_retries + 1,
                    wait_time,
                    " (from Retry-After header)" if retry_after else " (constant delay)",
                )

                await asyncio.sleep(wait_time)
            else:
                # Non-rate-limit error, don't retry
                raise
        except Exception:
            # For non-Slack errors, don't retry
            raise

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception


# --- Queue Operation Types ---


@dataclass
class QueueOperation:
    """Base class for all queue operations."""

    pass


@dataclass
class TextUpdateOp(QueueOperation):
    """Append text to the current buffered message."""

    text: str


@dataclass
class FileUploadOp(QueueOperation):
    """Upload a file with polling to ensure visibility."""

    filename: str
    content_bytes: bytes
    initial_comment: Optional[str] = None


@dataclass
class MessagePostOp(QueueOperation):
    """Post a new message to the channel."""

    text: str
    blocks: Optional[List[Dict]] = None


@dataclass
class MessageUpdateOp(QueueOperation):
    """Update an existing message."""

    ts: str
    text: str
    blocks: Optional[List[Dict]] = None


@dataclass
class MessageDeleteOp(QueueOperation):
    """Delete an existing message."""

    ts: str


@dataclass
class StopSignal(QueueOperation):
    """Sentinel to stop the queue processor."""

    pass


# --- Main Queue Class ---


class SlackMessageQueue:
    """
    Sequential message queue for a single Slack task.

    Ensures proper ordering of text messages and file uploads by:
    1. Buffering text updates into a single message
    2. Polling files.info after uploads until file is visible
    3. Resetting text state after file uploads (forcing new message)
    4. Processing all operations sequentially in a background task
    """

    def __init__(
        self,
        task_id: str,
        slack_client: AsyncWebClient,
        channel_id: str,
        thread_ts: str,
        adapter: "SlackAdapter",
    ):
        """
        Initialize a message queue for a specific task.

        Args:
            task_id: Unique identifier for this task
            slack_client: Async Slack API client
            channel_id: Target Slack channel ID
            thread_ts: Thread timestamp for replies
            adapter: Reference to SlackAdapter for task state access
        """
        self.task_id = task_id
        self.client = slack_client
        self.channel_id = channel_id
        self.thread_ts = thread_ts
        self.adapter = adapter

        # Queue and processor
        self.queue: asyncio.Queue[QueueOperation] = asyncio.Queue()
        self.processor_task: Optional[asyncio.Task] = None

        # State for text message buffering
        self.current_text_message_ts: Optional[str] = None
        self.text_buffer: str = ""

        # For update coalescing - holds non-text ops found during drain
        self._deferred_operation: Optional[QueueOperation] = None
        
        # Reactive throttling state for text updates
        # Text updates use local throttling as they are high-frequency and benefit from immediate retry detection
        # Non-text operations use the global rate limiter via _throttle()
        # This allows text updates to aggregate during throttle periods
        self._throttled_until: float = 0.0  # Time when we can try again
        self._throttle_retry_count: int = 0  # Track retries for final updates
        self._max_throttle_retries: int = 10  # Maximum retries for final updates

        log.debug("[Queue:%s] Initialized for channel %s", task_id, channel_id)

    async def start(self):
        """Start the background queue processor."""
        if self.processor_task is None or self.processor_task.done():
            self.processor_task = asyncio.create_task(
                self._process_queue(), name=f"slack-queue-{self.task_id}"
            )

    async def stop(self):
        """Stop the queue processor and wait for completion."""
        if self.processor_task and not self.processor_task.done():
            await self.queue.put(StopSignal())
            try:
                await asyncio.wait_for(self.processor_task, timeout=60.0)
            except asyncio.TimeoutError:
                log.error(
                    "[Queue:%s] Timeout waiting for queue to stop, cancelling",
                    self.task_id,
                )
                self.processor_task.cancel()
            log.info("[Queue:%s] Queue processor stopped", self.task_id)

    async def wait_until_complete(self):
        """Wait for all queued operations to be processed."""
        await self.queue.join()
        log.debug("[Queue:%s] All operations complete", self.task_id)

    # --- Queue Operation Methods ---

    async def queue_text_update(self, text: str):
        """Queue a text update to be appended to the current message."""
        await self.queue.put(TextUpdateOp(text=text))
        log.debug("[Queue:%s] Queued text update: %s...", self.task_id, text[:50])

    async def queue_file_upload(
        self, filename: str, content_bytes: bytes, initial_comment: Optional[str] = None
    ):
        """Queue a file upload with automatic polling for visibility."""
        await self.queue.put(
            FileUploadOp(
                filename=filename,
                content_bytes=content_bytes,
                initial_comment=initial_comment,
            )
        )
        log.debug(
            "[Queue:%s] Queued file upload: %s (%d bytes)",
            self.task_id,
            filename,
            len(content_bytes),
        )

    async def queue_message_post(self, text: str, blocks: Optional[List[Dict]] = None):
        """Queue posting a new message."""
        await self.queue.put(MessagePostOp(text=text, blocks=blocks))
        log.debug("[Queue:%s] Queued message post: %s...", self.task_id, text[:50])

    async def queue_message_update(
        self, ts: str, text: str, blocks: Optional[List[Dict]] = None
    ):
        """Queue updating an existing message."""
        await self.queue.put(MessageUpdateOp(ts=ts, text=text, blocks=blocks))
        log.debug("[Queue:%s] Queued message update for ts=%s", self.task_id, ts)

    async def queue_message_delete(self, ts: str):
        """Queue deleting a message."""
        await self.queue.put(MessageDeleteOp(ts=ts))
        log.debug("[Queue:%s] Queued message delete for ts=%s", self.task_id, ts)

    # --- Queue Processor ---

    def _drain_pending_text_updates(self) -> List[TextUpdateOp]:
        """
        Non-blocking drain of all pending TextUpdateOp items from the queue.
        
        This enables update coalescing: instead of sending one Slack API call
        per text update, we batch all pending text updates into a single call.
        This is critical for handling high-frequency artifact progress updates
        without hitting Slack rate limits.
        
        Returns:
            List of TextUpdateOp items that were pending in the queue.
        """
        pending_text_ops = []
        while True:
            try:
                # Non-blocking get - returns immediately if queue is empty
                item = self.queue.get_nowait()
                if isinstance(item, TextUpdateOp):
                    pending_text_ops.append(item)
                    self.queue.task_done()
                else:
                    # Put non-text items back at the front (we'll process them next)
                    self._deferred_operation = item
                    break
            except asyncio.QueueEmpty:
                break
        return pending_text_ops

    async def _process_queue(self):
        """
        Background task that processes queue operations sequentially.
        
        Implements update coalescing for TextUpdateOp: before sending a Slack
        update, drains all pending text updates from the queue and combines them
        into a single API call. This dramatically reduces API calls when receiving
        high-frequency progress updates.
        """
        try:
            while True:
                # Check if we have a deferred operation from a previous drain
                if self._deferred_operation is not None:
                    operation = self._deferred_operation
                    self._deferred_operation = None
                else:
                    operation = await self.queue.get()

                if isinstance(operation, StopSignal):
                    log.debug("[Queue:%s] Received stop signal", self.task_id)
                    # Flush any remaining buffered text as final update
                    if self.text_buffer:
                        log.debug(
                            "[Queue:%s] Flushing remaining buffer (%d chars) on stop",
                            self.task_id, len(self.text_buffer)
                        )
                        await self._handle_text_update(TextUpdateOp(text=""), is_final=True)
                    self.queue.task_done()
                    break

                try:
                    if isinstance(operation, TextUpdateOp):
                        # Check if this is the "final" text update before a non-text op
                        # by peeking at the next item (if any)
                        is_final = False
                        if self._deferred_operation is not None:
                            # There's a deferred non-text op, so this text is final
                            is_final = not isinstance(self._deferred_operation, TextUpdateOp)
                        elif self.queue.empty():
                            # Queue is empty - this might be final (no more updates coming)
                            # But we can't know for sure, so treat as non-final
                            # The stop() method will flush any remaining buffer
                            is_final = False
                        
                        await self._handle_text_update(operation, is_final=is_final)
                    elif isinstance(operation, FileUploadOp):
                        # Flush any pending text buffer before file upload
                        if self.text_buffer:
                            await self._handle_text_update(TextUpdateOp(text=""), is_final=True)
                        await self._handle_file_upload(operation)
                    elif isinstance(operation, MessagePostOp):
                        # Flush any pending text buffer before message post
                        if self.text_buffer:
                            await self._handle_text_update(TextUpdateOp(text=""), is_final=True)
                        await self._handle_message_post(operation)
                    elif isinstance(operation, MessageUpdateOp):
                        # Flush any pending text buffer before message update
                        if self.text_buffer:
                            await self._handle_text_update(TextUpdateOp(text=""), is_final=True)
                        await self._handle_message_update(operation)
                    elif isinstance(operation, MessageDeleteOp):
                        # Flush any pending text buffer before message delete
                        if self.text_buffer:
                            await self._handle_text_update(TextUpdateOp(text=""), is_final=True)
                        await self._handle_message_delete(operation)
                    else:
                        log.warning(
                            "[Queue:%s] Unknown operation type: %s",
                            self.task_id,
                            type(operation),
                        )

                except Exception as e:
                    log.error(
                        "[Queue:%s] Error processing operation %s: %s",
                        self.task_id,
                        operation,
                        e,
                        exc_info=True,
                    )
                    # Continue processing despite error

                finally:
                    self.queue.task_done()

        except Exception as e:
            log.error(
                "[Queue:%s] Fatal error in queue processor: %s",
                self.task_id,
                e,
                exc_info=True,
            )
        finally:
            log.info("[Queue:%s] Queue processor stopped", self.task_id)

    # --- Operation Handlers ---

    async def _handle_text_update(self, op: TextUpdateOp, is_final: bool = False):
        """
        Handle appending text to the current message buffer.
        
        Implements REACTIVE throttling:
        1. Try to send immediately
        2. If throttled (429):
           - For non-final: buffer and return (will retry when next update arrives or delay expires)
           - For final: wait and keep retrying until success (with max retry limit)
        3. If not throttled: send immediately
        
        Note: Text updates use local throttling (_throttled_until) rather than the global
        rate limiter because they are high-frequency and benefit from aggregation during
        throttle periods. Non-text operations continue to use the global rate limiter.
        
        Args:
            op: The text update operation
            is_final: If True, this is the final update and must be sent (will block until success)
        """
        log.debug(
            "[Queue:%s] Processing text update (final=%s): %s...",
            self.task_id, is_final, op.text[:50] if op.text else ""
        )

        # Append text to buffer
        self.text_buffer += op.text
        
        # Check if we're still in throttle period
        current_time = time.monotonic()
        if current_time < self._throttled_until:
            if is_final:
                # Final update - must wait and send
                wait_time = self._throttled_until - current_time
                log.debug(
                    "[Queue:%s] Final update - waiting %.2fs for throttle to expire",
                    self.task_id, wait_time
                )
                await asyncio.sleep(wait_time)
                # Fall through to send
            else:
                # Non-final update - just aggregate and return
                log.debug(
                    "[Queue:%s] Throttled - aggregating text (buffer now %d chars)",
                    self.task_id, len(self.text_buffer)
                )
                return
        
        # Drain any additional pending text updates before sending
        pending_text_ops = self._drain_pending_text_updates()
        if pending_text_ops:
            for pending_op in pending_text_ops:
                self.text_buffer += pending_op.text
            log.debug(
                "[Queue:%s] Coalesced %d additional text updates (%d chars total)",
                self.task_id, len(pending_text_ops), len(self.text_buffer)
            )
        
        # Format the FULL buffer
        formatted_text = self.adapter._format_text(self.text_buffer)
        
        # Reset retry counter for this send attempt
        self._throttle_retry_count = 0
        
        # Try to send
        try:
            if not self.current_text_message_ts:
                # Post a new message
                response = await self._try_slack_call(
                    self.client.chat_postMessage,
                    channel=self.channel_id,
                    thread_ts=self.thread_ts,
                    text=formatted_text,
                )
                if response:
                    self.current_text_message_ts = response.get("ts")
                else:
                    # Throttled - _throttled_until was set by _try_slack_call
                    if is_final:
                        # Final update - must wait and retry with limit
                        self._throttle_retry_count += 1
                        if self._throttle_retry_count > self._max_throttle_retries:
                            log.error(
                                "[Queue:%s] Max throttle retries (%d) exceeded for final update",
                                self.task_id, self._max_throttle_retries
                            )
                            raise RuntimeError(f"Max throttle retries exceeded for final text update")
                        
                        wait_time = self._throttled_until - time.monotonic()
                        if wait_time > 0:
                            log.debug(
                                "[Queue:%s] Final update throttled (retry %d/%d) - waiting %.2fs",
                                self.task_id, self._throttle_retry_count, self._max_throttle_retries, wait_time
                            )
                            await asyncio.sleep(wait_time)
                        response = await retry_with_backoff(
                            self.client.chat_postMessage,
                            channel=self.channel_id,
                            thread_ts=self.thread_ts,
                            text=formatted_text,
                            operation_name=f"[Queue:{self.task_id}] chat_postMessage (final)",
                        )
                        self.current_text_message_ts = response.get("ts")
                    else:
                        # Non-final - buffer is already updated, just return
                        # Next update will try again after throttle expires
                        log.debug(
                            "[Queue:%s] Non-final update throttled - buffered (%d chars)",
                            self.task_id, len(self.text_buffer)
                        )
                        return
            else:
                # Update existing message
                response = await self._try_slack_call(
                    self.client.chat_update,
                    channel=self.channel_id,
                    ts=self.current_text_message_ts,
                    text=formatted_text,
                )
                if not response:
                    # Throttled - _throttled_until was set by _try_slack_call
                    if is_final:
                        # Final update - must wait and retry with limit
                        self._throttle_retry_count += 1
                        if self._throttle_retry_count > self._max_throttle_retries:
                            log.error(
                                "[Queue:%s] Max throttle retries (%d) exceeded for final update",
                                self.task_id, self._max_throttle_retries
                            )
                            raise RuntimeError(f"Max throttle retries exceeded for final text update")
                        
                        wait_time = self._throttled_until - time.monotonic()
                        if wait_time > 0:
                            log.debug(
                                "[Queue:%s] Final update throttled (retry %d/%d) - waiting %.2fs",
                                self.task_id, self._throttle_retry_count, self._max_throttle_retries, wait_time
                            )
                            await asyncio.sleep(wait_time)
                        await retry_with_backoff(
                            self.client.chat_update,
                            channel=self.channel_id,
                            ts=self.current_text_message_ts,
                            text=formatted_text,
                            operation_name=f"[Queue:{self.task_id}] chat_update (final)",
                        )
                    else:
                        # Non-final - buffer is already updated, just return
                        # Next update will try again after throttle expires
                        log.debug(
                            "[Queue:%s] Non-final update throttled - buffered (%d chars)",
                            self.task_id, len(self.text_buffer)
                        )
                        return
        except Exception as e:
            log.error("[Queue:%s] Error sending text update: %s", self.task_id, e)
            # For non-final updates, preserve the buffer so it can be retried
            # The buffer already contains the text, so it will be sent with the next update
            if is_final:
                raise  # Re-raise for final updates - caller needs to know
            # For non-final, log and continue - buffer is preserved for next attempt
            log.warning(
                "[Queue:%s] Non-final text update failed, buffer preserved (%d chars)",
                self.task_id, len(self.text_buffer)
            )
    
    async def _try_slack_call(self, method, **kwargs) -> Optional[Dict]:
        """
        Try to make a Slack API call. Returns response on success, None if throttled.
        
        If throttled (429), sets _throttled_until and returns None.
        Other errors are raised.
        """
        try:
            response = await method(**kwargs)
            return response
        except SlackApiError as e:
            if e.response.status_code == 429:
                # Rate limited - extract retry_after and set throttle time
                retry_after = int(e.response.headers.get("Retry-After", 1))
                self._throttled_until = time.monotonic() + retry_after
                log.warning(
                    "[Queue:%s] Rate limited (429) - will retry after %ds",
                    self.task_id, retry_after
                )
                return None
            raise

    async def _handle_file_upload(self, op: FileUploadOp):
        """
        Handle file upload with polling to ensure visibility.

        This is the critical operation that prevents race conditions.
        """

        # Step 1: Finalize any pending text message (with retry and throttle)
        if self.text_buffer and self.current_text_message_ts:
            await self._throttle(is_message_update=True)
            await retry_with_backoff(
                self.client.chat_update,
                channel=self.channel_id,
                ts=self.current_text_message_ts,
                text=self.text_buffer,
                operation_name=f"[Queue:{self.task_id}] chat_update (finalize text)",
            )

        # Step 2: Reset text state (forces next text to a new message)
        self.text_buffer = ""
        self.current_text_message_ts = None

        # Step 3: Upload file using 3-step process
        try:
            # Step 3a: Get upload URL (with retry and throttle)
            log.debug(
                "[Queue:%s] Step 1: Getting upload URL for %s",
                self.task_id,
                op.filename,
            )
            await self._throttle(is_message_update=False)
            upload_url_response = await retry_with_backoff(
                self.client.files_getUploadURLExternal,
                filename=op.filename,
                length=len(op.content_bytes),
                operation_name=f"[Queue:{self.task_id}] files_getUploadURLExternal",
            )
            upload_url = upload_url_response.get("upload_url")
            file_id = upload_url_response.get("file_id")

            if not upload_url or not file_id:
                raise ValueError("Failed to get upload URL from Slack")

            # Step 3b: Upload content to temporary URL
            log.debug(
                "[Queue:%s] Step 2: Uploading %d bytes",
                self.task_id,
                len(op.content_bytes),
            )
            import requests

            upload_response = await asyncio.to_thread(
                requests.post, upload_url, data=op.content_bytes
            )
            upload_response.raise_for_status()

            # Step 3c: Complete the upload (with retry and throttle)
            log.debug("[Queue:%s] Step 3: Completing external upload", self.task_id)
            comment = op.initial_comment or f"Attached file: {op.filename}"
            await self._throttle(is_message_update=False)
            await retry_with_backoff(
                self.client.files_completeUploadExternal,
                files=[{"id": file_id, "title": op.filename}],
                channel_id=self.channel_id,
                thread_ts=self.thread_ts,
                initial_comment=comment,
                operation_name=f"[Queue:{self.task_id}] files_completeUploadExternal",
            )

            # Step 4: - Poll files.info until file is visible
            await self._wait_for_file_visible(file_id, timeout_seconds=30)

        except Exception as e:
            log.error(
                "[Queue:%s] Failed to upload file %s: %s",
                self.task_id,
                op.filename,
                e,
                exc_info=True,
            )
            # Post error message (with retry and throttle)
            await self._throttle(is_message_update=False)
            await retry_with_backoff(
                self.client.chat_postMessage,
                channel=self.channel_id,
                thread_ts=self.thread_ts,
                text=f"❌ Failed to upload file: {op.filename}",
                operation_name=f"[Queue:{self.task_id}] chat_postMessage (error)",
            )

    async def _handle_message_post(self, op: MessagePostOp):
        """Handle posting a new message."""
        log.debug("[Queue:%s] Posting new message: %s...", self.task_id, op.text[:50])
        await self._throttle(is_message_update=False)
        await retry_with_backoff(
            self.client.chat_postMessage,
            channel=self.channel_id,
            thread_ts=self.thread_ts,
            text=op.text,
            blocks=op.blocks,
            operation_name=f"[Queue:{self.task_id}] chat_postMessage",
        )

    async def _handle_message_update(self, op: MessageUpdateOp):
        """Handle updating an existing message."""
        log.debug("[Queue:%s] Updating message ts=%s", self.task_id, op.ts)
        # Apply stricter throttling for message updates (main source of rate limits)
        await self._throttle(is_message_update=True)
        await retry_with_backoff(
            self.client.chat_update,
            channel=self.channel_id,
            ts=op.ts,
            text=op.text,
            blocks=op.blocks,
            operation_name=f"[Queue:{self.task_id}] chat_update",
        )

    async def _handle_message_delete(self, op: MessageDeleteOp):
        """Handle deleting a message."""
        log.debug("[Queue:%s] Deleting message ts=%s", self.task_id, op.ts)
        await self._throttle(is_message_update=False)
        await retry_with_backoff(
            self.client.chat_delete,
            channel=self.channel_id,
            ts=op.ts,
            operation_name=f"[Queue:{self.task_id}] chat_delete",
        )

    # --- Polling Helper ---

    async def _wait_for_file_visible(self, file_id: str, timeout_seconds: int = 30):
        """
        Poll files.info until the 'shares' object appears, indicating the file
        is fully processed and visible in the channel.

        This is the KEY to ensuring proper ordering - we don't proceed until
        Slack confirms the file is actually posted.

        Args:
            file_id: The Slack file ID to monitor
            timeout_seconds: Maximum time to wait for file visibility

        Raises:
            TimeoutError: If file doesn't become visible within timeout
        """
        start_time = asyncio.get_event_loop().time()
        backoff_delay = 0.5  # Start with 500ms
        max_backoff = 5.0  # Cap at 5 seconds

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout_seconds:
                raise TimeoutError(
                    f"File {file_id} was not shared within {timeout_seconds} seconds"
                )

            try:
                # Query the file info (with retry for rate limiting)
                info_response = await retry_with_backoff(
                    self.client.files_info,
                    file=file_id,
                    operation_name=f"[Queue:{self.task_id}] files_info (polling)",
                )
                file_info = info_response.get("file", {})

                # Check if the 'shares' object exists and is populated
                shares = file_info.get("shares")
                if shares:
                    # Check both public channels and private/DM shares
                    public_shares = shares.get("public", {})
                    private_shares = shares.get("private", {})

                    # Check if file is in our channel (could be in either public or private)
                    if self.channel_id in public_shares:
                        log.debug(
                            "[Queue:%s] File %s confirmed in public channel",
                            self.task_id,
                            file_id,
                        )
                        return
                    elif self.channel_id in private_shares:
                        log.debug(
                            "[Queue:%s] File %s confirmed in private/DM channel",
                            self.task_id,
                            file_id,
                        )
                        return
                    else:
                        log.debug(
                            "[Queue:%s] File %s has shares but not in target channel. "
                            "Public: %s, Private: %s",
                            self.task_id,
                            file_id,
                            list(public_shares.keys()),
                            list(private_shares.keys()),
                        )

                # Not ready yet, wait with exponential backoff
                log.debug(
                    "[Queue:%s] File %s not yet shared. Waiting %.2fs...",
                    self.task_id,
                    file_id,
                    backoff_delay,
                )
                await asyncio.sleep(backoff_delay)
                backoff_delay = min(backoff_delay * 1.5, max_backoff)

            except SlackApiError as e:
                # If it's a rate limit error, the retry_with_backoff already handled it
                # This catch is for other Slack API errors
                log.warning("[Queue:%s] Slack API error checking file info: %s", self.task_id, e)
                await asyncio.sleep(backoff_delay)
                backoff_delay = min(backoff_delay * 1.5, max_backoff)
            except Exception as e:
                log.warning("[Queue:%s] Error checking file info: %s", self.task_id, e)
                await asyncio.sleep(backoff_delay)
                backoff_delay = min(backoff_delay * 1.5, max_backoff)
