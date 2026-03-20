"""
Utility functions for the Slack Gateway adapter.
"""

import asyncio
import json
import logging
import re
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import requests
from slack_sdk.errors import SlackApiError

from .message_queue import retry_with_backoff

if TYPE_CHECKING:
    from .adapter import SlackAdapter

log = logging.getLogger(__name__)

# Maximum length for citation titles before falling back to domain display
MAX_CITATION_TITLE_LENGTH = 40

# Block and Action IDs
SLACK_STATUS_BLOCK_ID = "slack_status_block"
SLACK_CONTENT_BLOCK_ID = "slack_content_block"
SLACK_FEEDBACK_BLOCK_ID = "slack_feedback_block"
SLACK_CANCEL_BUTTON_ACTION_ID = "slack_cancel_request_button"
SLACK_CANCEL_ACTION_BLOCK_ID = "slack_task_cancel_actions"
THUMBS_UP_ACTION_ID = "thumbs_up_action"
THUMBS_DOWN_ACTION_ID = "thumbs_down_action"
SUBMIT_FEEDBACK_ACTION_ID = "submit_feedback_action"
CANCEL_FEEDBACK_ACTION_ID = "cancel_feedback_action"
FEEDBACK_COMMENT_INPUT_ACTION_ID = "feedback_comment_input"
FEEDBACK_COMMENT_BLOCK_ID = "feedback_comment_block"


def create_slack_session_id(channel_id: str, thread_ts: Optional[str]) -> str:
    """
    Creates a safe session ID from a Slack channel and an optional thread timestamp.
    If thread_ts is not provided, the session is scoped to the channel itself.
    """
    if thread_ts:
        safe_thread_ts = thread_ts.replace(".", "_")
        return f"slack-{channel_id}-{safe_thread_ts}"
    return f"slack-{channel_id}"


# --- Citation Patterns ---
# Matches SAM citation markers: [[cite:s0r0]], [[cite:research0]], [[cite:idx0r0]]
# Also handles single-bracket variants: [cite:s0r0]
# Also handles comma-separated multi-citations: [[cite:s0r0, s0r1, s0r2]]
# Uses conditional backreference (?(1)\]) to ensure balanced brackets:
# if a second opening bracket was matched, require a second closing bracket.
CITATION_PATTERN = re.compile(
    r"\[(\[?)cite:((?:s\d+r\d+|idx\d+r\d+|research\d+)"
    r"(?:\s*,\s*(?:cite:)?(?:s\d+r\d+|idx\d+r\d+|research\d+))*)\](?(1)\])"
)
# Pattern to extract individual citation IDs from a comma-separated list
INDIVIDUAL_CITATION_PATTERN = re.compile(
    r"(?:cite:)?(s\d+r\d+|idx\d+r\d+|research\d+)"
)


def _has_valid_url_scheme(url: str) -> bool:
    """Validate that a URL uses http:// or https:// scheme."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https")
    except Exception:
        return False


def _sanitize_for_slack_mrkdwn(text: str) -> str:
    """Escape characters that have special meaning in Slack mrkdwn link syntax.

    Handles structural characters (<, >, |, &) that break the ``<url|label>``
    link syntax, and mrkdwn formatting characters (*, _, ~, `) that Slack
    interprets even inside link labels.  Formatting chars are neutralised by
    inserting a zero-width space (U+200B) after each occurrence so that
    paired delimiters (e.g. ``**bold**``) no longer form valid mrkdwn spans.
    """
    # & must be escaped first to avoid double-escaping
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace("|", "&#124;")
    # Break mrkdwn formatting patterns so titles with e.g. **bold** or
    # _italic_ don't produce unintended formatting inside Slack links.
    text = text.replace("*", "*\u200b")
    text = text.replace("_", "_\u200b")
    text = text.replace("~", "~\u200b")
    text = text.replace("`", "`\u200b")
    return text


def _escape_markdown_chars(text: str) -> str:
    """Escape characters that have special meaning in standard markdown link syntax."""
    # Escape ], [, (, ) which are structural in markdown links
    return text.replace("[", "\\[").replace("]", "\\]").replace("(", "\\(").replace(")", "\\)")


def _get_domain_from_url(url: str) -> str:
    """Extract a clean domain name from a URL for display."""
    try:
        parsed = urlparse(url)
        domain = parsed.hostname or url
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return url


def _transform_citations(
    text: str,
    citation_map: Dict[str, Dict[str, Any]],
    make_link: Callable[[str, str], str],
    make_title_only: Callable[[str], str],
) -> str:
    """
    Shared citation transformation logic.

    Replaces SAM citation markers with formatted links or title-only references
    using the provided formatter callbacks.

    Citation formats handled:
    - Web search: [[cite:s{turn}r{index}]] (e.g., [[cite:s0r0]], [[cite:s1r2]])
    - Document search: [[cite:idx{turn}r{index}]] (e.g., [[cite:idx0r0]])
    - Deep research: [[cite:research{N}]] (e.g., [[cite:research0]])
    - Multi-citations: [[cite:s0r0, s0r1, s0r2]]

    Args:
        text: The text containing citation markers.
        citation_map: Mapping of citation_id -> source info dict.
        make_link: Callable(url, display_text) -> formatted link string.
        make_title_only: Callable(title) -> formatted title-only string.

    Returns:
        Text with citations replaced by formatted links or stripped.
    """

    if not citation_map:
        # No sources available — strip all citation markers to keep output clean.
        # The caller is responsible for preserving raw text (with markers) if a
        # later re-resolution pass is needed (see _resolve_citations_final_pass).
        # Collapse runs of spaces left behind (e.g. "text [[cite:s0r0]] more"
        # becomes "text more", not "text  more").
        stripped = CITATION_PATTERN.sub("", text)
        return re.sub(r" {2,}", " ", stripped)

    def _replace_citation_match(match: re.Match) -> str:
        content = match.group(2)
        citation_ids = INDIVIDUAL_CITATION_PATTERN.findall(content)

        if not citation_ids:
            return ""  # Strip unrecognized citation markers

        links = []
        for cid in citation_ids:
            source = citation_map.get(cid)
            if source:
                url = (
                    source.get("sourceUrl")
                    or source.get("url")
                    or source.get("metadata", {}).get("link")
                )
                title = source.get("title") or source.get("filename")
                if url and _has_valid_url_scheme(url):
                    domain = _get_domain_from_url(url)
                    display = (
                        title
                        if title and len(title) <= MAX_CITATION_TITLE_LENGTH
                        else domain
                    )
                    links.append(make_link(url, display))
                elif title:
                    links.append(make_title_only(title))
                # else: No URL or title — skip this citation silently
            else:
                # Source not found in citation map — show a generic placeholder
                # so the user knows a source was referenced but couldn't be resolved.
                links.append(make_title_only("source"))

        if not links:
            return ""

        # Join multiple citations with commas, wrapped in parentheses
        if len(links) == 1:
            return f" ({links[0]})"
        return " (" + ", ".join(links) + ")"

    result = CITATION_PATTERN.sub(_replace_citation_match, text)
    # Collapse double-spaces left by stripped citations
    # (e.g. "text [[cite:unknown]] more" → "text more")
    return re.sub(r" {2,}", " ", result)


def transform_citations_for_slack(
    text: str,
    citation_map: Optional[Dict[str, Dict[str, Any]]] = None,
    skip_code_blocks: bool = False,
) -> str:
    """
    Transform SAM citation markers into Slack mrkdwn links or clean text.

    Args:
        text: The text containing citation markers.
        citation_map: Optional mapping of citation_id -> source info dict.
            Each source info dict should have at least:
            - "url" or "sourceUrl": The source URL
            - "title" or "filename": The source title
            Example: {"s0r0": {"sourceUrl": "https://...", "title": "..."}}
        skip_code_blocks: If True, preserve citation markers inside fenced
            code blocks (```...```) and only transform citations in
            surrounding text.  ``correct_slack_markdown`` already handles
            this internally; set this flag when calling the function
            directly (e.g. when markdown correction is disabled).

    Returns:
        Text with citations replaced by Slack mrkdwn links or stripped.
    """
    if not isinstance(text, str):
        return text

    citation_map = citation_map or {}

    def _make_slack_link(url: str, display: str) -> str:
        # Strip control characters (newlines, tabs, etc.) that could break
        # Slack's message parsing when placed inside <url|text> links.
        safe_url = re.sub(r"[\x00-\x1f\x7f]", "", url)
        # Sanitize structural Slack mrkdwn characters (<, >, |) but NOT & —
        # Slack auto-parses URLs inside <> angle brackets, and escaping &
        # to &amp; would break query parameters.
        safe_url = safe_url.replace("<", "%3C").replace(">", "%3E").replace("|", "%7C")
        return f"<{safe_url}|{_sanitize_for_slack_mrkdwn(display)}>"

    def _make_slack_title(title: str) -> str:
        return f"_{_sanitize_for_slack_mrkdwn(title)}_"

    try:
        if skip_code_blocks:
            parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
            processed = []
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    # Code block — leave untouched
                    processed.append(part)
                else:
                    processed.append(
                        _transform_citations(
                            part, citation_map, _make_slack_link, _make_slack_title
                        )
                    )
            text = "".join(processed)
        else:
            text = _transform_citations(
                text, citation_map, _make_slack_link, _make_slack_title
            )
    except Exception as e:
        log.warning("[SlackUtil:transform_citations] Error: %s", e)

    return text


def transform_citations_for_markdown(
    text: str, citation_map: Optional[Dict[str, Dict[str, Any]]] = None
) -> str:
    """
    Transform SAM citation markers into standard markdown links.

    Use this for markdown artifact files (e.g., deep research reports) that
    will be uploaded as files. Unlike transform_citations_for_slack() which
    produces Slack mrkdwn format (<URL|text>), this produces standard markdown
    [text](url) which renders correctly in markdown viewers.

    Args:
        text: The text containing citation markers.
        citation_map: Optional mapping of citation_id -> source info dict.

    Returns:
        Text with citations replaced by standard markdown links or stripped.
    """
    if not isinstance(text, str):
        return text

    citation_map = citation_map or {}

    def _make_md_link(url: str, display: str) -> str:
        # Escape characters that would break markdown link syntax [text](<url>)
        # - ) would close the parenthesized URL
        # - > would close the angle-bracket wrapper
        safe_url = url.replace(")", "%29").replace(">", "%3E")
        return f"[{_escape_markdown_chars(display)}](<{safe_url}>)"

    def _make_md_title(title: str) -> str:
        return f"*{_escape_markdown_chars(title)}*"

    try:
        text = _transform_citations(
            text, citation_map, _make_md_link, _make_md_title
        )
    except Exception as e:
        log.warning("[SlackUtil:transform_citations_markdown] Error: %s", e)

    return text


def correct_slack_markdown(
    text: str, citation_map: Optional[Dict[str, Dict[str, Any]]] = None
) -> str:
    """
    Converts common Markdown to Slack's mrkdwn format, avoiding changes inside code blocks.
    Also transforms SAM citation markers into Slack-friendly links.

    Args:
        text: The markdown text to convert.
        citation_map: Optional mapping of citation_id -> source info for link resolution.
    """
    if not isinstance(text, str):
        return text
    try:
        # Split text by code blocks to avoid formatting inside them
        parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
        processed_parts = []

        def heading_replacer(match: re.Match) -> str:
            title = match.group(1).strip()
            return f"\n*{title}*"

        for i, part in enumerate(parts):
            # If it's a code block part (odd index), just clean it up and add it
            if i % 2 == 1:
                # Code blocks: ```lang\ncode``` -> ```\ncode```
                cleaned_code_block = re.sub(r"```[a-zA-Z0-9_-]+\n", "```\n", part)
                processed_parts.append(cleaned_code_block)
            # If it's a non-code block part (even index), apply formatting
            else:
                # Bold and headings run BEFORE link conversion so that
                # the bold regex (**...**) cannot match inside the
                # <url|text> Slack link syntax produced by link conversion.
                # Bold: **Text** -> *Text*
                part = re.sub(r"\*\*(.*?)\*\*", r"*\1*", part)
                # Headings: ### Title -> *Title* with underline
                part = re.sub(
                    r"^\s*#{1,6}\s+(.*)", heading_replacer, part, flags=re.MULTILINE
                )
                # Links: [Text](URL) -> <URL|Text>
                part = re.sub(r"\[(.*?)\]\((http.*?)\)", r"<\2|\1>", part)
                # Citation transformation MUST run LAST — after all markdown
                # regex conversions (bold, headings, links) are complete — so
                # that its output (<url|text> Slack links, _title_ italics)
                # is never fed back through bold/heading/link regexes, which
                # would corrupt the Slack link syntax.  Display text inside
                # citation links is additionally protected by
                # _sanitize_for_slack_mrkdwn which neutralises *, _, ~, `.
                part = transform_citations_for_slack(part, citation_map)
                processed_parts.append(part)

        text = "".join(processed_parts)

    except Exception as e:
        log.warning("[SlackUtil:correct_markdown] Error during formatting: %s", e)
    return text


def build_slack_blocks(
    status_text: Optional[str] = None,
    content_text: Optional[str] = None,
    feedback_elements: Optional[List[Dict]] = None,
    cancel_button_action_elements: Optional[List[Dict]] = None,
) -> List[Dict]:
    """Builds the complete list of Slack blocks based on the current state."""
    blocks = []
    if status_text:
        blocks.append(
            {
                "type": "context",
                "block_id": f"{SLACK_STATUS_BLOCK_ID}_{uuid.uuid4().hex[:8]}",
                "elements": [{"type": "mrkdwn", "text": status_text}],
            }
        )

    # Only add a content block if content_text is provided.
    if content_text is not None:
        # Slack requires non-empty text for markdown blocks
        display_content = content_text if content_text.strip() else " "
        blocks.append(
            {
                "type": "section",
                "block_id": f"{SLACK_CONTENT_BLOCK_ID}_{uuid.uuid4().hex[:8]}",
                "text": {"type": "mrkdwn", "text": display_content},
            }
        )

    if cancel_button_action_elements:
        blocks.append(
            {
                "type": "actions",
                "block_id": SLACK_CANCEL_ACTION_BLOCK_ID,
                "elements": cancel_button_action_elements,
            }
        )

    if feedback_elements:
        blocks.append(
            {
                "type": "actions",
                "block_id": SLACK_FEEDBACK_BLOCK_ID,
                "elements": feedback_elements,
            }
        )
    return blocks


async def send_slack_message(
    adapter: "SlackAdapter",
    channel: str,
    thread_ts: Optional[str],
    text: str,
    blocks: Optional[List[Dict]] = None,
) -> Optional[str]:
    """Wrapper for chat.postMessage with error handling and rate limit retry."""
    try:
        response = await retry_with_backoff(
            adapter.slack_app.client.chat_postMessage,
            channel=channel,
            text=text,
            thread_ts=thread_ts,
            blocks=blocks,
            operation_name=f"send_slack_message to {channel}",
        )
        message_ts = response.get("ts")
        if message_ts:
            log.debug(
                "Successfully sent message to channel %s (Thread: %s, TS: %s)",
                channel,
                thread_ts,
                message_ts,
            )
            return message_ts
        log.error("chat.postMessage response missing 'ts'. Response: %s", response)
        return None
    except Exception as e:
        log.error(
            "Failed to send Slack message to channel %s (Thread: %s): %s",
            channel,
            thread_ts,
            e,
        )
        return None


async def update_slack_message(
    adapter: "SlackAdapter",
    channel: str,
    ts: str,
    text: str,
    blocks: Optional[List[Dict]] = None,
):
    """Wrapper for chat.update with error handling and rate limit retry."""
    try:
        await retry_with_backoff(
            adapter.slack_app.client.chat_update,
            channel=channel,
            ts=ts,
            text=text,
            blocks=blocks,
            operation_name=f"update_slack_message {ts} in {channel}",
        )
        log.debug("Successfully updated message %s in channel %s", ts, channel)
    except Exception as e:
        log.warning(
            "Failed to update Slack message %s in channel %s: %s", ts, channel, e
        )


async def upload_slack_file(
    adapter: "SlackAdapter",
    channel: str,
    thread_ts: Optional[str],
    filename: str,
    content_bytes: bytes,
    initial_comment: Optional[str] = None,
):
    """
    Uploads a file to Slack using the three-step external upload process
    to ensure atomic message/file posting and correct ordering.
    Includes rate limit retry logic for Slack API calls.
    """
    log_id_prefix = "[SlackUpload]"
    try:
        # Step 1: Get an upload URL and file_id from Slack (with retry)
        log.debug("%s Step 1: Getting upload URL for '%s'", log_id_prefix, filename)
        upload_url_response = await retry_with_backoff(
            adapter.slack_app.client.files_getUploadURLExternal,
            filename=filename,
            length=len(content_bytes),
            operation_name=f"files_getUploadURLExternal for {filename}",
        )
        upload_url = upload_url_response.get("upload_url")
        file_id = upload_url_response.get("file_id")

        if not upload_url or not file_id:
            raise SlackApiError(
                "Failed to get upload URL from Slack.", upload_url_response
            )

        # Step 2: Upload the file content to the temporary URL
        log.debug(
            "%s Step 2: Uploading %d bytes to temporary URL.",
            log_id_prefix,
            len(content_bytes),
        )
        # Use to_thread to avoid blocking the async event loop
        upload_response = await asyncio.to_thread(
            requests.post, upload_url, data=content_bytes
        )
        upload_response.raise_for_status()  # Will raise an exception for non-2xx responses

        # Step 3: Complete the upload and post the file to the channel (with retry)
        log.debug(
            "%s Step 3: Completing external upload for file_id %s.",
            log_id_prefix,
            file_id,
        )
        comment = initial_comment or f"Attached file: {filename}"
        await retry_with_backoff(
            adapter.slack_app.client.files_completeUploadExternal,
            files=[{"id": file_id, "title": filename}],
            channel_id=channel,
            thread_ts=thread_ts,
            initial_comment=comment,
            operation_name=f"files_completeUploadExternal for {filename}",
        )

        log.debug(
            "%s Successfully uploaded file '%s' (%d bytes) to channel %s (Thread: %s)",
            log_id_prefix,
            filename,
            len(content_bytes),
            channel,
            thread_ts,
        )

    except Exception as e:
        log.error(
            "%s Failed to upload Slack file '%s' to channel %s (Thread: %s): %s",
            log_id_prefix,
            filename,
            channel,
            thread_ts,
            e,
        )
        try:
            error_text = f":warning: Failed to upload file: {filename}"
            await send_slack_message(adapter, channel, thread_ts, error_text)
        except Exception as notify_err:
            log.error(
                "%s Failed to send file upload error notification: %s",
                log_id_prefix,
                notify_err,
            )


def create_feedback_input_blocks(rating: str, original_payload: Dict) -> List[Dict]:
    """Creates the Slack blocks for text feedback input."""
    submit_payload = {**original_payload, "rating": rating}
    submit_value_string = json.dumps(submit_payload)

    cancel_value_string = json.dumps(original_payload)

    if len(submit_value_string) > 2000 or len(cancel_value_string) > 2000:
        log.error("Feedback payload exceeds 2000 chars. Cannot create input form.")
        return [
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": ":warning: Could not load feedback form (payload too large).",
                    }
                ],
            }
        ]

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "Thanks! Any additional comments?"},
        },
        {
            "type": "input",
            "block_id": FEEDBACK_COMMENT_BLOCK_ID,
            "element": {
                "type": "plain_text_input",
                "action_id": FEEDBACK_COMMENT_INPUT_ACTION_ID,
                "multiline": True,
                "placeholder": {
                    "type": "plain_text",
                    "text": "Let us know what you think...",
                },
            },
            "label": {"type": "plain_text", "text": "Comment"},
        },
        {
            "type": "actions",
            "block_id": f"feedback_actions_{uuid.uuid4().hex[:8]}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Submit"},
                    "style": "primary",
                    "value": submit_value_string,
                    "action_id": SUBMIT_FEEDBACK_ACTION_ID,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Cancel"},
                    "value": cancel_value_string,
                    "action_id": CANCEL_FEEDBACK_ACTION_ID,
                },
            ],
        },
    ]


def create_feedback_blocks(task_id: str, user_id: str, session_id: str) -> List[Dict]:
    """Creates the Slack action blocks for thumbs up/down feedback."""
    try:
        # The value payload for buttons is limited to 2000 characters.
        # We only need the task_id to correlate feedback.
        value_payload = {
            "task_id": task_id,
            "user_id": user_id,
            "session_id": session_id,
        }
        value_string = json.dumps(value_payload)
        if len(value_string) > 2000:
            log.error(
                "Feedback value payload exceeds 2000 chars. Cannot create buttons."
            )
            return []

        return [
            {
                "type": "button",
                "text": {"type": "plain_text", "emoji": True, "text": "👍"},
                "value": value_string,
                "action_id": THUMBS_UP_ACTION_ID,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "emoji": True, "text": "👎"},
                "value": value_string,
                "action_id": THUMBS_DOWN_ACTION_ID,
            },
        ]
    except Exception as e:
        log.error("Failed to create feedback blocks: %s", e)
        return []
