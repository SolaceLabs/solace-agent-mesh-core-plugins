"""Unit tests for utility functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import json

from sam_slack_gateway_adapter import utils


class TestCreateSlackSessionId:
    """Test suite for create_slack_session_id function."""

    def test_session_id_with_thread(self):
        """Test creating session ID with thread timestamp."""
        session_id = utils.create_slack_session_id("C12345", "1234567890.123456")
        assert session_id == "slack-C12345-1234567890_123456"

    def test_session_id_without_thread(self):
        """Test creating session ID without thread timestamp."""
        session_id = utils.create_slack_session_id("C12345", None)
        assert session_id == "slack-C12345"

    def test_session_id_replaces_dots(self):
        """Test that dots in timestamp are replaced with underscores."""
        session_id = utils.create_slack_session_id("C12345", "123.456.789")
        assert "." not in session_id
        assert session_id == "slack-C12345-123_456_789"


class TestCorrectSlackMarkdown:
    """Test suite for correct_slack_markdown function."""

    def test_convert_bold(self):
        """Test converting **bold** to *bold*."""
        text = "This is **bold** text"
        result = utils.correct_slack_markdown(text)
        assert result == "This is *bold* text"

    def test_convert_links(self):
        """Test converting [text](url) to <url|text>."""
        text = "Check out [Google](https://google.com)"
        result = utils.correct_slack_markdown(text)
        assert result == "Check out <https://google.com|Google>"

    def test_convert_headings(self):
        """Test converting ### Heading to *Heading*."""
        text = "### My Heading"
        result = utils.correct_slack_markdown(text)
        assert "*My Heading*" in result

    def test_preserve_code_blocks(self):
        """Test that content inside code blocks is preserved."""
        text = "Normal **bold** text\n```python\n**not bold**\n```\nMore **bold**"
        result = utils.correct_slack_markdown(text)
        assert "```\n**not bold**\n```" in result
        # First bold should be converted
        lines = result.split("\n")
        assert "*bold*" in lines[0]

    def test_remove_language_from_code_blocks(self):
        """Test that language specifiers are removed from code blocks."""
        text = "```python\nprint('hello')\n```"
        result = utils.correct_slack_markdown(text)
        assert result == "```\nprint('hello')\n```"

    def test_non_string_input(self):
        """Test handling non-string input."""
        result = utils.correct_slack_markdown(None)
        assert result is None

    def test_multiple_formatting_types(self):
        """Test handling multiple formatting types together."""
        text = "**Bold** and [link](https://example.com)"
        result = utils.correct_slack_markdown(text)
        assert "*Bold*" in result
        assert "<https://example.com|link>" in result


class TestBuildSlackBlocks:
    """Test suite for build_slack_blocks function."""

    def test_build_with_status_only(self):
        """Test building blocks with only status text."""
        blocks = utils.build_slack_blocks(status_text="Processing...")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "context"
        assert blocks[0]["elements"][0]["text"] == "Processing..."

    def test_build_with_content_only(self):
        """Test building blocks with only content text."""
        blocks = utils.build_slack_blocks(content_text="Hello world")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["text"] == "Hello world"

    def test_build_with_empty_content(self):
        """Test building blocks with empty content text."""
        blocks = utils.build_slack_blocks(content_text="")
        assert len(blocks) == 1
        assert blocks[0]["text"]["text"] == " "  # Slack requires non-empty

    def test_build_with_status_and_content(self):
        """Test building blocks with both status and content."""
        blocks = utils.build_slack_blocks(
            status_text="Processing...", content_text="Here's the result"
        )
        assert len(blocks) == 2
        assert blocks[0]["type"] == "context"
        assert blocks[1]["type"] == "section"

    def test_build_with_feedback_elements(self):
        """Test building blocks with feedback elements."""
        feedback_elements = [
            {"type": "button", "text": {"type": "plain_text", "text": "👍"}}
        ]
        blocks = utils.build_slack_blocks(feedback_elements=feedback_elements)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "actions"
        assert blocks[0]["block_id"] == utils.SLACK_FEEDBACK_BLOCK_ID

    def test_build_with_cancel_button(self):
        """Test building blocks with cancel button."""
        cancel_elements = [
            {"type": "button", "text": {"type": "plain_text", "text": "Cancel"}}
        ]
        blocks = utils.build_slack_blocks(cancel_button_action_elements=cancel_elements)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "actions"
        assert blocks[0]["block_id"] == utils.SLACK_CANCEL_ACTION_BLOCK_ID


class TestSendSlackMessage:
    """Test suite for send_slack_message - tests timestamp extraction behavior."""

    @pytest.mark.asyncio
    async def test_extracts_timestamp_from_response(self):
        """Test that timestamp is correctly extracted from Slack API response."""
        mock_adapter = MagicMock()
        mock_adapter.slack_app.client.chat_postMessage = AsyncMock(
            return_value={"ts": "1234567890.123456", "ok": True}
        )

        ts = await utils.send_slack_message(
            mock_adapter, "C12345", "1234567890.000000", "Hello", None
        )

        # Behavior: function returns the timestamp from the response
        assert ts == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_returns_none_on_api_failure(self):
        """Test that API failures return None instead of raising."""
        mock_adapter = MagicMock()
        mock_adapter.slack_app.client.chat_postMessage = AsyncMock(
            side_effect=Exception("API Error")
        )

        ts = await utils.send_slack_message(
            mock_adapter, "C12345", None, "Hello", None
        )

        # Behavior: errors are handled gracefully
        assert ts is None


class TestUpdateSlackMessage:
    """Test suite for update_slack_message - tests error handling."""

    @pytest.mark.asyncio
    async def test_errors_are_suppressed(self):
        """Test that update errors don't raise exceptions."""
        mock_adapter = MagicMock()
        mock_adapter.slack_app.client.chat_update = AsyncMock(
            side_effect=Exception("API Error")
        )

        # Behavior: should not raise exception even on error
        await utils.update_slack_message(
            mock_adapter, "C12345", "1234567890.123456", "Updated", None
        )


class TestUploadSlackFile:
    """Test suite for upload_slack_file - tests 3-step upload flow."""

    @pytest.mark.asyncio
    async def test_completes_three_step_upload_flow(self):
        """Test that file upload follows Slack's 3-step process correctly."""
        mock_adapter = MagicMock()

        # Step 1: Get upload URL
        mock_adapter.slack_app.client.files_getUploadURLExternal = AsyncMock(
            return_value={
                "upload_url": "https://upload.slack.com/test",
                "file_id": "F12345",
            }
        )

        # Step 3: Complete upload
        mock_adapter.slack_app.client.files_completeUploadExternal = AsyncMock()

        # Step 2: Mock the HTTP POST
        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        with patch("asyncio.to_thread", return_value=mock_response):
            await utils.upload_slack_file(
                mock_adapter,
                "C12345",
                "1234567890.123456",
                "test.txt",
                b"file content",
                "Here's the file",
            )

        # Behavior: verify all 3 steps were executed
        mock_adapter.slack_app.client.files_getUploadURLExternal.assert_called_once()
        mock_adapter.slack_app.client.files_completeUploadExternal.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_errors_dont_crash(self):
        """Test that upload failures are handled gracefully."""
        mock_adapter = MagicMock()
        mock_adapter.slack_app.client.files_getUploadURLExternal = AsyncMock(
            side_effect=Exception("Upload failed")
        )

        with patch.object(utils, "send_slack_message", new_callable=AsyncMock):
            # Behavior: should not raise exception
            await utils.upload_slack_file(
                mock_adapter,
                "C12345",
                None,
                "test.txt",
                b"file content",
            )


class TestCreateFeedbackBlocks:
    """Test suite for create_feedback_blocks function."""

    def test_create_feedback_blocks(self):
        """Test creating feedback blocks."""
        blocks = utils.create_feedback_blocks("task-123", "user-123", "session-123")

        assert len(blocks) == 2
        assert blocks[0]["type"] == "button"
        assert blocks[0]["action_id"] == utils.THUMBS_UP_ACTION_ID
        assert blocks[1]["action_id"] == utils.THUMBS_DOWN_ACTION_ID

        # Verify payload can be parsed
        payload = json.loads(blocks[0]["value"])
        assert payload["task_id"] == "task-123"
        assert payload["user_id"] == "user-123"
        assert payload["session_id"] == "session-123"

    def test_create_feedback_blocks_too_large(self):
        """Test handling when payload is too large."""
        # Create a task_id that will exceed 2000 chars when serialized
        large_task_id = "x" * 2000
        blocks = utils.create_feedback_blocks(large_task_id, "user", "session")

        assert blocks == []


class TestCreateFeedbackInputBlocks:
    """Test suite for create_feedback_input_blocks function."""

    def test_create_feedback_input_blocks(self):
        """Test creating feedback input blocks."""
        original_payload = {
            "task_id": "task-123",
            "user_id": "user-123",
            "session_id": "session-123",
        }

        blocks = utils.create_feedback_input_blocks("up", original_payload)

        # Should have section, input, and actions blocks
        assert len(blocks) == 3
        assert blocks[0]["type"] == "section"
        assert blocks[1]["type"] == "input"
        assert blocks[2]["type"] == "actions"

        # Verify submit button has rating in payload
        submit_button = blocks[2]["elements"][0]
        payload = json.loads(submit_button["value"])
        assert payload["rating"] == "up"
        assert payload["task_id"] == "task-123"

    def test_create_feedback_input_blocks_too_large(self):
        """Test handling when payload is too large."""
        large_payload = {"task_id": "x" * 2000}
        blocks = utils.create_feedback_input_blocks("up", large_payload)

        # Should return error block
        assert len(blocks) == 1
        assert blocks[0]["type"] == "context"
        assert "too large" in blocks[0]["elements"][0]["text"].lower()
