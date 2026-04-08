"""
Slack Gateway Adapter for the Generic Gateway Framework.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, Optional

import requests
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError

from pydantic import BaseModel, Field

# Import from installed solace_agent_mesh package
from solace_agent_mesh.gateway.adapter.base import GatewayAdapter
from solace_agent_mesh.gateway.adapter.types import (
    AuthClaims,
    GatewayContext,
    ResponseContext,
    SamDataPart,
    SamError,
    SamFeedback,
    SamFilePart,
    SamTask,
    SamTextPart,
    SamUpdate,
)
from . import handlers, utils
from .message_queue import SlackMessageQueue

log = logging.getLogger(__name__)

_NO_EMAIL_MARKER = "_NO_EMAIL_"


class SlackAdapterConfig(BaseModel):
    """Configuration model for the SlackAdapter."""

    slack_bot_token: str = Field(..., description="Slack Bot Token (xoxb-...).")
    slack_app_token: str = Field(
        ..., description="Slack App Token (xapp-...) for Socket Mode."
    )
    slack_initial_status_message: str = Field(
        "Got it, thinking...",
        description="Message posted to Slack upon receiving a user request.",
    )
    correct_markdown_formatting: bool = Field(
        True, description="Attempt to convert common Markdown to Slack's format."
    )
    feedback_enabled: bool = Field(
        False, description="Enable thumbs up/down feedback buttons on final messages."
    )
    slack_email_cache_ttl_seconds: int = Field(
        3600, description="TTL for caching Slack user email addresses."
    )


class SlackAdapter(GatewayAdapter):
    """A feature-complete Slack Gateway implementation using the adapter pattern."""

    ConfigModel = SlackAdapterConfig

    def __init__(self):
        self.context: Optional[GatewayContext] = None
        self.slack_app: Optional[AsyncApp] = None
        self.slack_handler: Optional[AsyncSocketModeHandler] = None
        self.message_queues: Dict[str, SlackMessageQueue] = {}

    async def init(self, context: GatewayContext) -> None:
        """Initialize the Slack app, handlers, and start the listener."""
        self.context = context
        log.info("Initializing Slack Adapter...")

        # Config is now a validated Pydantic model
        adapter_config: SlackAdapterConfig = self.context.adapter_config

        self.slack_app = AsyncApp(token=adapter_config.slack_bot_token)

        # --- Register Event and Action Handlers ---
        self._register_handlers()

        # --- Start Socket Mode Handler ---
        self.slack_handler = AsyncSocketModeHandler(
            self.slack_app, adapter_config.slack_app_token
        )
        asyncio.create_task(self.slack_handler.start_async())
        log.info("Slack Adapter initialized and listener started.")

    async def cleanup(self) -> None:
        """Stop the Slack listener and all message queues."""
        # Stop all message queues
        for task_id, queue in list(self.message_queues.items()):
            log.info("Stopping message queue for task %s", task_id)
            try:
                await queue.stop()
            except Exception as e:
                log.error("Error stopping queue for task %s: %s", task_id, e)
        self.message_queues.clear()

        # Stop Slack listener
        if self.slack_handler:
            log.info("Stopping Slack listener...")
            self.slack_handler.close()

    def _register_handlers(self):
        """Registers all Slack event and action handlers."""

        # Event handlers for messages and mentions
        @self.slack_app.event("message")
        async def handle_message_wrapper(event, say, body):
            # Ensure team_id is in the event (extract from body if needed)
            self._ensure_team_id_in_event(event, body)
            await handlers.handle_slack_message(self, event, say)

        @self.slack_app.event("app_mention")
        async def handle_mention_wrapper(event, say, body):
            # Ensure team_id is in the event (extract from body if needed)
            self._ensure_team_id_in_event(event, body)
            await handlers.handle_slack_mention(self, event, say)

        # Slash command handlers that reuse the keyword command logic
        @self.slack_app.command("/artifacts")
        async def handle_artifacts_slash_command(ack, command, client, logger):
            await ack()
            await handlers.handle_artifacts_command(self, command, client, logger)

        @self.slack_app.command("/help")
        async def handle_help_slash_command(ack, command, client, logger):
            await ack()
            await handlers.handle_help_command(self, command, client, logger)

        # Handler for the download button action
        @self.slack_app.action("download_artifact_button")
        async def handle_download_action(ack, body, client, logger):
            await ack()
            action_details = body["actions"][0]
            button_value = json.loads(action_details["value"])
            filename = button_value["filename"]
            version = button_value["version"]
            slack_user_id = body["user"]["id"]

            logger.info(
                f"User {slack_user_id} requested download of {filename} v{version}"
            )

            try:
                # We need the user's primary ID again for the artifact service
                auth_claims = await self.extract_auth_claims(body["user"])
                if not auth_claims or not auth_claims.id:
                    raise ValueError(
                        "Could not determine user identity for artifact download."
                    )

                user_id = auth_claims.id
                session_id = utils.create_slack_session_id(
                    body["container"]["channel_id"],
                    body["container"].get("thread_ts"),
                )

                # Create a response context for the download
                response_context = ResponseContext(
                    task_id=f"slack-dl-{body['trigger_id']}",
                    session_id=session_id,
                    user_id=user_id,
                    platform_context={
                        "channel_id": body["container"]["channel_id"],
                        "thread_ts": body["container"].get("thread_ts"),
                    },
                )

                # Load the artifact content
                content_bytes = await self.context.load_artifact_content(
                    response_context, filename, version
                )

                if content_bytes:
                    # Use the existing file upload utility
                    await utils.upload_slack_file(
                        adapter=self,
                        channel=body["container"]["channel_id"],
                        thread_ts=body["container"].get("thread_ts"),
                        filename=filename,
                        content_bytes=content_bytes,
                        initial_comment=f"Here is your requested file: `{filename}`",
                    )
                else:
                    await client.chat_postMessage(
                        channel=body["container"]["channel_id"],
                        thread_ts=body["container"].get("thread_ts"),
                        text=f"Sorry, I could not retrieve the content for `{filename}`.",
                    )
            except Exception as e:
                logger.error(
                    f"Error downloading artifact {filename}: {e}", exc_info=True
                )
                await client.chat_postMessage(
                    channel=body["container"]["channel_id"],
                    thread_ts=body["container"].get("thread_ts"),
                    text=f"An error occurred while downloading the artifact: {e}",
                )

        # Action handler for the cancel button
        @self.slack_app.action(utils.SLACK_CANCEL_BUTTON_ACTION_ID)
        async def handle_cancel_action(ack, body, logger):
            await ack()
            task_id = body["actions"][0]["value"]
            logger.info(f"Cancel button clicked for task: {task_id}")
            await self.context.cancel_task(task_id)

        # Action handlers for multi-step feedback
        @self.slack_app.action(utils.THUMBS_UP_ACTION_ID)
        async def handle_thumbs_up(ack, body, client, logger):
            await ack()
            payload = json.loads(body["actions"][0]["value"])
            logger.info(
                "Feedback process started (up) for task: %s", payload["task_id"]
            )
            input_blocks = utils.create_feedback_input_blocks("up", payload)
            await client.chat_update(
                channel=body["container"]["channel_id"],
                ts=body["container"]["message_ts"],
                blocks=input_blocks,
                text="Please provide your feedback.",
            )

        @self.slack_app.action(utils.THUMBS_DOWN_ACTION_ID)
        async def handle_thumbs_down(ack, body, client, logger):
            await ack()
            payload = json.loads(body["actions"][0]["value"])
            logger.info(
                "Feedback process started (down) for task: %s", payload["task_id"]
            )
            input_blocks = utils.create_feedback_input_blocks("down", payload)
            await client.chat_update(
                channel=body["container"]["channel_id"],
                ts=body["container"]["message_ts"],
                blocks=input_blocks,
                text="Please provide your feedback.",
            )

        @self.slack_app.action(utils.CANCEL_FEEDBACK_ACTION_ID)
        async def handle_cancel_feedback(ack, body, client, logger):
            await ack()
            payload = json.loads(body["actions"][0]["value"])
            logger.info("Feedback cancelled for task: %s", payload["task_id"])
            original_feedback_elements = utils.create_feedback_blocks(
                payload["task_id"], payload["user_id"], payload["session_id"]
            )
            original_blocks = [
                {
                    "type": "actions",
                    "block_id": utils.SLACK_FEEDBACK_BLOCK_ID,
                    "elements": original_feedback_elements,
                }
            ]
            await client.chat_update(
                channel=body["container"]["channel_id"],
                ts=body["container"]["message_ts"],
                blocks=original_blocks,
                text="How was this response?",
            )

        @self.slack_app.action(utils.SUBMIT_FEEDBACK_ACTION_ID)
        async def handle_submit_feedback(ack, body, client, logger):
            await ack()
            payload = json.loads(body["actions"][0]["value"])
            task_id = payload["task_id"]
            rating = payload["rating"]
            session_id = payload["session_id"]

            comment = ""
            try:
                state_values = body.get("state", {}).get("values", {})
                comment_block = state_values.get(utils.FEEDBACK_COMMENT_BLOCK_ID, {})
                comment = comment_block.get(
                    utils.FEEDBACK_COMMENT_INPUT_ACTION_ID, {}
                ).get("value", "")
            except Exception as e:
                logger.error(
                    "Error extracting feedback comment for task %s: %s", task_id, e
                )

            logger.info(
                "Feedback submitted for task %s: rating=%s, comment='%s...'",
                task_id,
                rating,
                comment[:50],
            )

            feedback = SamFeedback(
                task_id=task_id,
                session_id=session_id,
                rating=rating,
                comment=comment,
                user_id=payload["user_id"],
            )
            await self.context.submit_feedback(feedback)

            thank_you_blocks = [
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "✅ Thank you for your feedback!",
                        }
                    ],
                }
            ]
            await client.chat_update(
                channel=body["container"]["channel_id"],
                ts=body["container"]["message_ts"],
                blocks=thank_you_blocks,
                text="Thank you for your feedback!",
            )

    @staticmethod
    def _is_bot_message(event: Dict) -> bool:
        """Return True if the event should be treated as a bot message and ignored.

        A pure bot message has bot_id but no user (e.g. xoxb- token).
        A user message via an app has both bot_id AND user (e.g. xoxp- token) and
        should be processed normally.
        """
        return (
            (event.get("bot_id") and not event.get("user"))
            or event.get("subtype") == "bot_message"
        )

    async def extract_auth_claims(
        self, external_input: Dict, endpoint_context: Optional[Dict[str, Any]] = None
    ) -> Optional[AuthClaims]:
        """Extract user identity from a Slack event."""
        if self._is_bot_message(external_input):
            log.debug("Skipping auth claims extraction for bot message")
            return None

        # Try multiple possible field names for user ID to handle both
        # message events (which have 'user') and action events (which have 'id')
        slack_user_id = (
            external_input.get("user")
            or external_input.get("user_id")
            or external_input.get("id")
        )

        # Try multiple possible field names for team ID
        # Note: team_id should be present in the event because _ensure_team_id_in_event
        # extracts it from the body before this method is called.
        slack_team_id = (
            external_input.get("team")
            or external_input.get("team_id")
            or external_input.get("team_domain")
        )

        if not slack_user_id or not slack_team_id:
            log.warning(
                "Could not determine Slack user_id or team_id from event. "
                "Event keys: %s, "
                "user fields checked: user=%s, user_id=%s, "
                "team fields checked: team=%s, team_id=%s, team_domain=%s",
                list(external_input.keys()),
                external_input.get("user"),
                external_input.get("user_id"),
                external_input.get("team"),
                external_input.get("team_id"),
                external_input.get("team_domain"),
            )
            return None

        adapter_config: SlackAdapterConfig = self.context.adapter_config
        cache_key = f"slack_email_cache:{slack_user_id}"
        ttl = adapter_config.slack_email_cache_ttl_seconds

        if self.context.cache_service and ttl > 0:
            cached_claim = self.context.cache_service.get_data(cache_key)
            if cached_claim:
                if cached_claim == _NO_EMAIL_MARKER:
                    return AuthClaims(
                        id=f"slack:{slack_team_id}:{slack_user_id}",
                        source="slack_fallback",
                        raw_context={
                            "slack_user_id": slack_user_id,
                            "slack_team_id": slack_team_id,
                        },
                    )
                else:
                    cached_email = cached_claim.lower() if isinstance(cached_claim, str) else cached_claim
                    return AuthClaims(
                        id=cached_email,
                        email=cached_email,
                        source="slack_api",
                        raw_context={
                            "slack_user_id": slack_user_id,
                            "slack_team_id": slack_team_id,
                        },
                    )

        try:
            profile_response = await self.slack_app.client.users_profile_get(
                user=slack_user_id
            )
            user_email = profile_response.get("profile", {}).get("email")
            if user_email:
                user_email = user_email.lower()

            if user_email:
                if self.context.cache_service and ttl > 0:
                    self.context.cache_service.add_data(
                        cache_key, user_email, expiry=ttl
                    )
                return AuthClaims(
                    id=user_email,
                    email=user_email,
                    source="slack_api",
                    raw_context={
                        "slack_user_id": slack_user_id,
                        "slack_team_id": slack_team_id,
                    },
                )
            else:
                raise ValueError("Email not found in profile")
        except Exception as e:
            log.warning(
                "Could not fetch email for Slack user %s: %s. Using fallback ID.",
                slack_user_id,
                e,
            )
            if self.context.cache_service and ttl > 0:
                self.context.cache_service.add_data(
                    cache_key, _NO_EMAIL_MARKER, expiry=ttl
                )
            return AuthClaims(
                id=f"slack:{slack_team_id}:{slack_user_id}",
                source="slack_fallback",
                raw_context={
                    "slack_user_id": slack_user_id,
                    "slack_team_id": slack_team_id,
                },
            )

    async def prepare_task(
        self, external_input: Dict, endpoint_context: Optional[Dict[str, Any]] = None
    ) -> SamTask:
        """Convert a Slack event into a SamTask."""
        if self._is_bot_message(external_input):
            raise ValueError("Ignoring bot message")

        channel_id = external_input.get("channel")
        thread_ts = external_input.get("thread_ts") or external_input.get("ts")
        text = external_input.get("text", "")
        files_info = external_input.get("files", [])

        # Resolve @mentions in the text
        resolved_text = await self._resolve_mentions_in_text(text)

        parts = [self.context.create_text_part(resolved_text)]

        # Handle file uploads
        if files_info:
            for file_info in files_info:
                try:
                    file_bytes = await self._download_file(file_info)
                    parts.append(
                        self.context.create_file_part_from_bytes(
                            name=file_info["name"],
                            content_bytes=file_bytes,
                            mime_type=file_info.get(
                                "mimetype", "application/octet-stream"
                            ),
                        )
                    )
                except Exception as e:
                    log.error(
                        "Failed to download and attach file %s: %s",
                        file_info.get("name"),
                        e,
                    )

        if not any(
            p.text.strip() for p in parts if isinstance(p, SamTextPart)
        ) and not any(isinstance(p, SamFilePart) for p in parts):
            raise ValueError("No content to send to agent")

        return SamTask(
            parts=parts,
            session_id=utils.create_slack_session_id(channel_id, thread_ts),
            target_agent=self.context.get_config("default_agent_name", "default"),
            platform_context={
                "channel_id": channel_id,
                "thread_ts": thread_ts,
            },
        )

    async def handle_update(self, update: SamUpdate, context: ResponseContext) -> None:
        """Handle a streaming update from the agent."""
        task_id = context.task_id
        channel_id = context.platform_context["channel_id"]
        thread_ts = context.platform_context["thread_ts"]

        # Get or create message queue for this task
        queue = await self._get_or_create_queue(task_id, channel_id, thread_ts)

        # Get or create status message timestamp
        status_ts = self.context.get_task_state(task_id, "status_ts")

        adapter_config: SlackAdapterConfig = self.context.adapter_config
        # If this is the first update, post the initial status message
        if not status_ts:
            initial_status_msg = adapter_config.slack_initial_status_message
            if initial_status_msg:
                status_blocks = utils.build_slack_blocks(status_text=initial_status_msg)
                new_status_ts = await utils.send_slack_message(
                    self, channel_id, thread_ts, initial_status_msg, status_blocks
                )
                if new_status_ts:
                    self.context.set_task_state(task_id, "status_ts", new_status_ts)
                    self.context.set_task_state(
                        task_id, "current_status", initial_status_msg
                    )
                    status_ts = new_status_ts

        # Process parts by queuing operations (returns immediately)
        for part in update.parts:
            if isinstance(part, SamTextPart):
                # Queue RAW text update - formatting happens in queue when posting
                await queue.queue_text_update(part.text)

            elif isinstance(part, SamFilePart):
                await self._handle_file_part_queued(part, queue)
            elif isinstance(part, SamDataPart):
                await self._handle_data_part_queued(part, queue, context)

    async def handle_task_complete(self, context: ResponseContext) -> None:
        """Update UI to show task is complete and add feedback buttons."""
        task_id = context.task_id
        channel_id = context.platform_context["channel_id"]
        thread_ts = context.platform_context["thread_ts"]
        status_ts = self.context.get_task_state(task_id, "status_ts")

        adapter_config: SlackAdapterConfig = self.context.adapter_config

        if task_id in self.message_queues:
            queue = self.message_queues[task_id]
            await queue.wait_until_complete()

        # Final citation resolution pass: RAG data signals may have arrived after
        # the text was already formatted and posted. Re-apply citation transformation
        # with the now-populated citation map and update the message in Slack.
        await self._resolve_citations_final_pass(task_id, channel_id)

        # Now update the status message to show completion.
        final_status_text = "✅ Task complete."
        status_blocks = utils.build_slack_blocks(status_text=final_status_text)
        if status_ts:
            await utils.update_slack_message(
                self, channel_id, status_ts, final_status_text, status_blocks
            )
        else:
            # If no status message was ever posted, post a new one.
            await utils.send_slack_message(
                self, channel_id, thread_ts, final_status_text, status_blocks
            )

        # Then, if feedback is enabled, post it as a new message in the thread.
        if adapter_config.feedback_enabled:
            feedback_elements = utils.create_feedback_blocks(
                task_id, context.user_id, context.session_id
            )
            if feedback_elements:
                feedback_blocks = [
                    {
                        "type": "actions",
                        "block_id": utils.SLACK_FEEDBACK_BLOCK_ID,
                        "elements": feedback_elements,
                    }
                ]
                await utils.send_slack_message(
                    self,
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="How was this response?",  # Fallback text for notifications
                    blocks=feedback_blocks,
                )

        # Stop and cleanup the message queue for this task
        if task_id in self.message_queues:
            log.info("Stopping and cleaning up message queue for task %s", task_id)
            await self.message_queues[task_id].stop()
            del self.message_queues[task_id]

    async def handle_error(self, error: SamError, context: ResponseContext) -> None:
        """Display an error message in Slack."""
        task_id = context.task_id
        channel_id = context.platform_context["channel_id"]
        status_ts = self.context.get_task_state(task_id, "status_ts")

        # Wait for any pending operations to complete before showing error
        if task_id in self.message_queues:
            queue = self.message_queues[task_id]
            try:
                await asyncio.wait_for(queue.wait_until_complete(), timeout=10.0)
            except asyncio.TimeoutError:
                log.warning(
                    "Timeout waiting for queue to complete for task %s", task_id
                )

        if status_ts:
            error_text = f"❌ Error: {error.message}"
            if error.category == "CANCELED":
                error_text = "🛑 Task canceled."

            error_blocks = utils.build_slack_blocks(status_text=error_text)
            await utils.update_slack_message(
                self, channel_id, status_ts, error_text, error_blocks
            )

        # Stop and cleanup the message queue for this task
        if task_id in self.message_queues:
            log.info(
                "Stopping and cleaning up message queue after error for task %s",
                task_id,
            )
            try:
                await self.message_queues[task_id].stop()
            except Exception as e:
                log.error("Error stopping queue for task %s: %s", task_id, e)
            del self.message_queues[task_id]

    # --- Private Helper Methods ---

    async def _get_or_create_queue(
        self, task_id: str, channel_id: str, thread_ts: str
    ) -> SlackMessageQueue:
        """
        Get existing message queue for a task or create a new one.

        Args:
            task_id: Unique task identifier
            channel_id: Slack channel ID
            thread_ts: Thread timestamp

        Returns:
            SlackMessageQueue instance for this task
        """
        if task_id not in self.message_queues:
            queue = SlackMessageQueue(
                task_id=task_id,
                slack_client=self.slack_app.client,
                channel_id=channel_id,
                thread_ts=thread_ts,
                adapter=self,
            )
            await queue.start()
            self.message_queues[task_id] = queue
            log.info("Created and started message queue for task %s", task_id)

        return self.message_queues[task_id]

    def _get_icon_for_mime_type(self, mime_type: Optional[str]) -> str:
        """Returns a Slack emoji for a given MIME type."""
        if not mime_type:
            return ":page_facing_up:"
        if "image" in mime_type:
            return ":art:"
        if "audio" in mime_type:
            return ":sound:"
        if "video" in mime_type:
            return ":film_frames:"
        if "pdf" in mime_type:
            return ":page_facing_up:"
        if "zip" in mime_type or "archive" in mime_type:
            return ":compression:"
        if "text" in mime_type or "json" in mime_type or "csv" in mime_type:
            return ":page_with_curl:"
        return ":page_facing_up:"

    def _format_text(self, text: str, task_id: Optional[str] = None) -> str:
        """Applies citation transformation (always) and markdown correction (if enabled).

        Citation transformation is always applied so that [[cite:...]] markers
        are resolved to Slack links regardless of the markdown formatting config.
        The markdown-to-mrkdwn conversion (bold, headings, links) is only applied
        when correct_markdown_formatting is enabled.

        Args:
            text: The raw text to format.
            task_id: Optional task ID to look up the citation map for this task.
        """
        # Get citation map for this task (if available)
        citation_map = None
        if task_id:
            citation_map = self.context.get_task_state(task_id, "citation_map")

        adapter_config: SlackAdapterConfig = self.context.adapter_config
        if adapter_config.correct_markdown_formatting:
            # correct_slack_markdown handles both citations and markdown conversion
            return utils.correct_slack_markdown(text, citation_map)

        # Even without markdown formatting, always transform citations.
        # skip_code_blocks=True ensures citations inside fenced code blocks
        # are preserved (correct_slack_markdown handles this internally).
        return utils.transform_citations_for_slack(
            text, citation_map, skip_code_blocks=True
        )

    def _transform_markdown_content(
        self, content_bytes: bytes, filename: str, task_id: str
    ) -> bytes:
        """Transform citations in markdown file content.

        Decodes the bytes as UTF-8, applies citation transformation for standard
        markdown format, and re-encodes. Returns the original bytes on failure.

        Args:
            content_bytes: The raw file content.
            filename: The filename (for logging).
            task_id: The task ID to look up the citation map.

        Returns:
            Transformed content bytes, or original bytes if transformation fails.
        """
        citation_map = self.context.get_task_state(task_id, "citation_map")
        if not citation_map:
            return content_bytes
        try:
            text_content = content_bytes.decode("utf-8")
            text_content = utils.transform_citations_for_markdown(
                text_content, citation_map
            )
            log.debug(
                "[SlackAdapter] Applied citation transformation to markdown file '%s'",
                filename,
            )
            return text_content.encode("utf-8")
        except UnicodeDecodeError as e:
            log.warning(
                "[SlackAdapter] Cannot decode markdown file '%s' as UTF-8, "
                "skipping citation transformation: %s",
                filename,
                e,
            )
            return content_bytes
        except Exception as e:
            log.error(
                "[SlackAdapter] Unexpected error transforming citations in "
                "markdown file '%s': %s",
                filename,
                e,
                exc_info=True,
            )
            return content_bytes

    async def _handle_file_part_queued(
        self, part: SamFilePart, queue: SlackMessageQueue
    ):
        """Handles queueing a file upload to Slack.

        For markdown files (.md), applies citation transformation to the file
        content before uploading, so that deep research reports with
        [[cite:researchN]] markers get proper Slack links.
        """
        if part.content_bytes:
            content_bytes = part.content_bytes
            # Transform citations in markdown files (e.g., deep research reports)
            if part.name and part.name.lower().endswith(".md"):
                content_bytes = self._transform_markdown_content(
                    content_bytes, part.name, queue.task_id
                )
            await queue.queue_file_upload(part.name, content_bytes)
        elif part.uri:
            uri_text = f":link: Artifact available: {part.name} - {part.uri}"
            await queue.queue_message_post(uri_text)

    def _capture_rag_sources(self, task_id: str, sources: list) -> None:
        """
        Capture RAG source metadata into a citation map stored in task state.

        This builds a mapping of citation_id -> source info that is used by
        _format_text() to transform [[cite:...]] markers into Slack links.

        Args:
            task_id: The task ID to store the citation map under.
            sources: List of source dicts from RAG metadata (camelCase keys).
        """
        if not sources:
            return

        # Get or create the citation map for this task
        citation_map = self.context.get_task_state(task_id, "citation_map") or {}

        for source in sources:
            citation_id = source.get("citationId")
            if not citation_id:
                continue

            # Store the source info keyed by citation ID
            citation_map[citation_id] = {
                "sourceUrl": source.get("sourceUrl"),
                "url": source.get("url"),
                "title": source.get("title"),
                "filename": source.get("filename"),
                "metadata": source.get("metadata", {}),
            }

        self.context.set_task_state(task_id, "citation_map", citation_map)
        log.debug(
            "[SlackAdapter] Updated citation map for task %s: %d citations",
            task_id,
            len(citation_map),
        )

    async def _handle_data_part_queued(
        self, part: SamDataPart, queue: SlackMessageQueue, context: ResponseContext
    ):
        """Handles structured data by queuing appropriate operations."""
        data_type = part.data.get("type")
        task_id = context.task_id
        channel_id = context.platform_context["channel_id"]
        thread_ts = context.platform_context["thread_ts"]

        if data_type == "rag_info_update":
            # Capture RAG source metadata for citation link resolution (deep research)
            sources = part.data.get("sources", [])
            self._capture_rag_sources(task_id, sources)

        elif data_type == "tool_result":
            # Capture RAG source metadata from tool results (web search, index search)
            # Structure: data.result_data.rag_metadata.sources[]
            result_data = part.data.get("result_data")
            if isinstance(result_data, dict):
                rag_metadata = result_data.get("rag_metadata")
                if isinstance(rag_metadata, dict):
                    sources = rag_metadata.get("sources", [])
                    if sources:
                        self._capture_rag_sources(task_id, sources)
                        log.debug(
                            "[SlackAdapter] Captured %d RAG sources from tool_result for task %s",
                            len(sources),
                            task_id,
                        )

        elif data_type == "agent_progress_update":
            status_text = part.data.get("status_text")
            if status_text:
                await self.handle_status_update(status_text, context)

        elif data_type == "artifact_creation_progress":
            status = part.data.get("status")
            filename = part.data.get("filename", "unknown file")
            artifact_msg_ts_key = f"artifact_msg_ts:{filename}"
            artifact_msg_ts = self.context.get_task_state(task_id, artifact_msg_ts_key)

            if status == "in-progress":
                bytes_transferred = part.data.get("bytes_transferred", 0)
                icon = self._get_icon_for_mime_type(None)
                progress_text = f"{icon} Creating `{filename}`..."
                if bytes_transferred > 0:
                    progress_text += f" ({bytes_transferred} bytes)"
                progress_blocks = utils.build_slack_blocks(content_text=progress_text)

                if artifact_msg_ts:
                    # We have a message for this artifact, so queue an update
                    await queue.queue_message_update(
                        ts=artifact_msg_ts,
                        text=progress_text,
                        blocks=progress_blocks,
                    )
                else:
                    # This is the first progress update for this artifact.
                    # Queue a new progress message
                    # Note: The queue will handle finalizing pending text before this posts
                    new_artifact_msg_ts = await utils.send_slack_message(
                        self, channel_id, thread_ts, progress_text, progress_blocks
                    )
                    if new_artifact_msg_ts:
                        self.context.set_task_state(
                            task_id, artifact_msg_ts_key, new_artifact_msg_ts
                        )

            elif status == "completed":
                if artifact_msg_ts:
                    # The placeholder message exists. We will now upload the file with the
                    # final description and then delete the placeholder.
                    description = part.data.get("description", "N/A")
                    mime_type = part.data.get("mime_type")
                    icon = self._get_icon_for_mime_type(mime_type)
                    final_comment = (
                        f"{icon} Artifact Created: `{filename}`\n"
                        f"*Description*: {description}"
                    )

                    try:
                        version = part.data.get("version")
                        content_bytes = await self.context.load_artifact_content(
                            context=context, filename=filename, version=version
                        )

                        if content_bytes:
                            # Transform citations in markdown artifact files
                            if filename.lower().endswith(".md"):
                                content_bytes = self._transform_markdown_content(
                                    content_bytes, filename, task_id
                                )

                            # Queue the file upload (with polling)
                            await queue.queue_file_upload(
                                filename=filename,
                                content_bytes=content_bytes,
                                initial_comment=final_comment,
                            )
                            # Queue deletion of the placeholder message
                            await queue.queue_message_delete(ts=artifact_msg_ts)
                        else:
                            # If content fails to load, queue an error update
                            log.error(
                                "Failed to load content for artifact '%s' (version: %s). Cannot upload to Slack.",
                                filename,
                                version or "latest",
                            )
                            error_text = (
                                f"❌ Failed to load content for artifact `{filename}`."
                            )
                            error_blocks = utils.build_slack_blocks(
                                content_text=error_text
                            )
                            await queue.queue_message_update(
                                ts=artifact_msg_ts,
                                text=error_text,
                                blocks=error_blocks,
                            )

                    except Exception as e:
                        log.exception(
                            "Error fetching or uploading artifact '%s': %s", filename, e
                        )
                        error_text = f"❌ An error occurred while uploading artifact `{filename}`."
                        error_blocks = utils.build_slack_blocks(content_text=error_text)
                        await queue.queue_message_update(
                            ts=artifact_msg_ts,
                            text=error_text,
                            blocks=error_blocks,
                        )
                else:
                    log.warning(
                        "Could not find message TS for completing artifact '%s'",
                        filename,
                    )

            elif status == "failed":
                if artifact_msg_ts:
                    failed_text = f"❌ Failed to create artifact: `{filename}`"
                    failed_blocks = utils.build_slack_blocks(content_text=failed_text)
                    await queue.queue_message_update(
                        ts=artifact_msg_ts,
                        text=failed_text,
                        blocks=failed_blocks,
                    )
                else:
                    # If we never even started a message, queue a new one.
                    failed_text = f"❌ Failed to create artifact: `{filename}`"
                    await queue.queue_message_post(text=failed_text)

    async def handle_status_update(
        self, status_text: str, context: ResponseContext
    ) -> None:
        """Update the status message in Slack."""
        task_id = context.task_id
        channel_id = context.platform_context["channel_id"]
        status_ts = self.context.get_task_state(task_id, "status_ts")
        if status_ts:
            current_status = self.context.get_task_state(task_id, "current_status", "")
            new_status = f"⏳ {status_text}"
            if new_status != current_status:
                status_blocks = utils.build_slack_blocks(status_text=new_status)
                await utils.update_slack_message(
                    self, channel_id, status_ts, new_status, status_blocks
                )
                self.context.set_task_state(task_id, "current_status", new_status)

    async def _resolve_mentions_in_text(self, text: str) -> str:
        """Finds all Slack user mentions (<@U...>) and replaces them with email/name."""
        mention_pattern = re.compile(r"<@([UW][A-Z0-9]+)>")
        user_ids_found = set(mention_pattern.findall(text))
        if not user_ids_found:
            return text

        modified_text = text
        for user_id in user_ids_found:
            try:
                user_info_response = await self.slack_app.client.users_info(
                    user=user_id
                )
                profile = user_info_response.get("user", {}).get("profile", {})
                replacement = profile.get("email") or profile.get(
                    "real_name_normalized"
                )
                if replacement:
                    modified_text = modified_text.replace(f"<@{user_id}>", replacement)
            except SlackApiError as e:
                log.warning(
                    "Slack API error resolving mention for user ID %s: %s", user_id, e
                )
        return modified_text

    def _ensure_team_id_in_event(self, event: Dict, body: Dict) -> None:
        """
        Ensure team_id is present in the event dict.
        
        Some Slack events (particularly those with file uploads) only include
        team_id in the outer body, not in the inner event object. This method
        extracts team_id from the body and adds it to the event if missing.
        
        This is the same approach used by the old sam-slack gateway.
        
        Args:
            event: The Slack event dict (may be modified in place)
            body: The raw Slack webhook body containing team_id
        """
        if "team" not in event and "team_id" not in event:
            if team_id := body.get("team_id"):
                event["team"] = team_id
                log.debug("Extracted team_id from body: %s", team_id)

    async def _resolve_citations_final_pass(
        self, task_id: str, channel_id: str
    ) -> None:
        """
        Final citation resolution pass after all queue operations are complete.

        When web search citations arrive via rag_info_update data signals AFTER
        the text has already been formatted and posted, the citation map was empty
        during _format_text(). The markers were stripped (replaced with empty
        string) because no URL mapping was available.

        This method uses queue.text_buffer (which preserves the original
        [[cite:...]] markers since _format_text() returns a new string without
        modifying text_buffer in-place) to re-format the text with the
        now-populated citation map and update the Slack message.

        Concurrency safety: This method is called AFTER queue.wait_until_complete()
        returns.  At that point the queue processor has finished, no new operations
        will be enqueued (handle_task_response has already returned), and
        text_buffer / current_text_message_ts are effectively immutable — no
        additional synchronization is required.

        No double-conversion risk: text_buffer always holds the *raw* text
        (with [[cite:...]] markers).  _format_text() produces a new formatted
        string without mutating text_buffer, so each call here is a fresh
        formatting pass from the original source text, NOT a re-format of
        already-converted output.

        Note: text_buffer is reset to "" when the queue processes a file upload
        (to start a new message segment). Therefore this method only resolves
        citations in the *last* text segment — i.e., text posted after the
        final file upload. Citations in earlier segments (before a file upload)
        are resolved at format-time with whatever citation map was available
        then.

        Only runs if:
        1. A citation map exists for this task (RAG sources were received)
        2. A text message was posted by the queue (current_text_message_ts exists)
        3. The text buffer contains unresolved citation markers

        Args:
            task_id: The task ID to resolve citations for.
            channel_id: The Slack channel ID where the message was posted.
        """
        citation_map = self.context.get_task_state(task_id, "citation_map")
        if not citation_map:
            return  # No RAG sources received, nothing to resolve

        # Get the message queue to find the last posted text message TS
        # and the text buffer (which preserves [[cite:...]] markers since
        # formatting is applied at read-time via _format_text).
        queue = self.message_queues.get(task_id)
        if not queue or not queue.current_text_message_ts:
            return  # No text message was posted

        raw_text = queue.text_buffer
        if not raw_text:
            return  # No text to resolve

        # Check if the text contains any citation markers
        if not utils.CITATION_PATTERN.search(raw_text):
            return  # No citation markers to resolve

        message_ts = queue.current_text_message_ts

        try:
            # Re-format the raw text with the now-populated citation map
            resolved_text = self._format_text(raw_text, task_id=task_id)

            # Skip if the resolved text is identical to what was last posted
            # (i.e., citations were already resolved during streaming)
            if resolved_text == queue.last_posted_formatted_text:
                return

            # Guard against exceeding Slack's message size limit (~40K chars).
            # Citation expansion replaces short markers like [[cite:s0r0]] with
            # full links like (<https://example.com/...|Title>), so the resolved
            # text can be significantly longer than what was originally posted
            # (where markers were stripped).  If the expanded text exceeds the
            # limit, skip the update — the already-posted text (with markers
            # stripped) is still readable.
            SLACK_MAX_MESSAGE_LENGTH = 40000
            if len(resolved_text) > SLACK_MAX_MESSAGE_LENGTH:
                log.warning(
                    "[SlackAdapter] Final citation pass skipped for task %s: "
                    "resolved text (%d chars) exceeds Slack message limit (%d)",
                    task_id,
                    len(resolved_text),
                    SLACK_MAX_MESSAGE_LENGTH,
                )
                return

            # Update the message with resolved citations.  Pass blocks=[]
            # to explicitly clear any Block Kit blocks, ensuring Slack renders
            # the text field.  (The queue posts text messages without blocks,
            # but this guards against inconsistent rendering if that changes.)
            await utils.update_slack_message(
                self, channel_id, message_ts, resolved_text, blocks=[]
            )
            log.info(
                "[SlackAdapter] Final citation pass resolved citations in message %s "
                "(task %s, %d sources in map)",
                message_ts,
                task_id,
                len(citation_map),
            )
        except Exception as e:
            log.warning(
                "[SlackAdapter] Failed to resolve citations in final pass for task %s: %s",
                task_id,
                e,
            )

    async def _download_file(self, file_info: Dict) -> bytes:
        """Downloads a file from Slack given its private URL."""
        file_url = file_info.get("url_private_download") or file_info.get("url_private")
        if not file_url:
            raise ValueError("File info is missing a download URL.")

        adapter_config: SlackAdapterConfig = self.context.adapter_config
        headers = {"Authorization": f"Bearer {adapter_config.slack_bot_token}"}

        # Use to_thread to avoid blocking the event loop
        response = await asyncio.to_thread(
            requests.get, file_url, headers=headers, timeout=30
        )
        response.raise_for_status()
        return response.content

