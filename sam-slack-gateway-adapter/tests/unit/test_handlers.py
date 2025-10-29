"""Unit tests for Slack event handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sam_slack_gateway_adapter import handlers


@pytest.fixture
def mock_adapter():
    """Create a mock SlackAdapter."""
    adapter = MagicMock()
    adapter.context = MagicMock()
    adapter.context.handle_external_input = AsyncMock()
    adapter.extract_auth_claims = AsyncMock()
    adapter.slack_app = MagicMock()
    adapter.slack_app.client = AsyncMock()
    return adapter


@pytest.fixture
def mock_client():
    """Create a mock Slack client."""
    client = AsyncMock()
    client.chat_postMessage = AsyncMock()
    client.chat_postEphemeral = AsyncMock()
    return client


class TestHandleSlackMessage:
    """Test suite for handle_slack_message handler - tests event filtering behavior."""

    @pytest.mark.asyncio
    async def test_direct_messages_are_processed(self, mock_adapter):
        """Test that direct messages trigger processing."""
        event = {
            "channel_type": "im",
            "channel": "D12345",
            "user": "U12345",
            "text": "Hello bot",
            "ts": "1234567890.123456",
        }
        say = AsyncMock()

        await handlers.handle_slack_message(mock_adapter, event, say)

        # Test actual behavior: context.handle_external_input should be called for DMs
        mock_adapter.context.handle_external_input.assert_called_once()

    @pytest.mark.asyncio
    async def test_bot_messages_ignored(self, mock_adapter):
        """Test that bot messages are filtered out (behavior: no processing)."""
        event = {
            "bot_id": "B12345",
            "channel_type": "im",
            "text": "Bot message",
        }
        say = AsyncMock()

        await handlers.handle_slack_message(mock_adapter, event, say)

        # Test actual behavior: bot messages should not trigger processing
        mock_adapter.context.handle_external_input.assert_not_called()

    @pytest.mark.asyncio
    async def test_channel_messages_without_thread_ignored(self, mock_adapter):
        """Test filtering behavior: channel messages without threads are ignored."""
        event = {
            "channel_type": "channel",
            "channel": "C12345",
            "user": "U12345",
            "text": "Random channel message",
            "ts": "1234567890.123456",
        }
        say = AsyncMock()

        await handlers.handle_slack_message(mock_adapter, event, say)

        # Test actual behavior: non-threaded channel messages are ignored
        mock_adapter.context.handle_external_input.assert_not_called()


class TestProcessSlackEvent:
    """Test suite for command routing behavior."""

    @pytest.mark.asyncio
    async def test_commands_intercepted_before_agent_processing(self, mock_adapter, mock_client):
        """Test that !commands are intercepted and don't reach agents."""
        event = {
            "channel": "C12345",
            "user": "U12345",
            "text": "!help",
            "ts": "1234567890.123456",
        }
        say = AsyncMock()
        mock_adapter.slack_app.client = mock_client

        await handlers._process_slack_event(mock_adapter, event, say)

        # Behavior: commands should NOT be sent to agents
        mock_adapter.context.handle_external_input.assert_not_called()
        # Behavior: help response should be sent
        mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_commands_show_error(self, mock_adapter, mock_client):
        """Test that unknown commands provide helpful error feedback."""
        event = {
            "channel": "C12345",
            "user": "U12345",
            "text": "!nonexistent",
            "ts": "1234567890.123456",
        }
        say = AsyncMock()
        mock_adapter.slack_app.client = mock_client

        await handlers._process_slack_event(mock_adapter, event, say)

        # Behavior: should show error with suggestion to use !help
        mock_client.chat_postEphemeral.assert_called_once()
        call_text = mock_client.chat_postEphemeral.call_args[1]["text"]
        assert "Unknown command" in call_text
        assert "!help" in call_text

    @pytest.mark.asyncio
    async def test_normal_messages_sent_to_agent(self, mock_adapter):
        """Test that non-command messages are sent to agents."""
        event = {
            "channel": "C12345",
            "user": "U12345",
            "text": "What's the weather?",
            "ts": "1234567890.123456",
        }
        say = AsyncMock()

        await handlers._process_slack_event(mock_adapter, event, say)

        # Behavior: normal messages should be processed by agents
        mock_adapter.context.handle_external_input.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_processing_errors_reported_to_user(self, mock_adapter):
        """Test that processing errors result in user-facing error messages."""
        event = {
            "channel": "C12345",
            "user": "U12345",
            "text": "Hello bot",
            "ts": "1234567890.123456",
        }
        say = AsyncMock()

        # Simulate an error during processing
        mock_adapter.context.handle_external_input.side_effect = Exception(
            "Database connection failed"
        )

        await handlers._process_slack_event(mock_adapter, event, say)

        # Behavior: user should see an error message
        say.assert_called_once()
        assert "error" in say.call_args[1]["text"].lower()


class TestArtifactsCommand:
    """Test suite for artifacts command handler."""

    @pytest.mark.asyncio
    async def test_artifacts_no_artifacts(self, mock_adapter, mock_client):
        """Test artifacts command when no artifacts exist."""
        event = {
            "channel": "C12345",
            "user": "U12345",
            "ts": "1234567890.123456",
        }

        mock_adapter.extract_auth_claims = AsyncMock(
            return_value=MagicMock(id="user@example.com")
        )
        mock_adapter.context.list_artifacts = AsyncMock(return_value=[])

        logger = MagicMock()

        await handlers.handle_artifacts_command(
            mock_adapter, event, mock_client, logger
        )

        # Should post "no artifacts" message
        mock_client.chat_postMessage.assert_called_once()
        assert "No artifacts" in mock_client.chat_postMessage.call_args[1]["text"]

    @pytest.mark.asyncio
    async def test_artifacts_with_artifacts(self, mock_adapter, mock_client):
        """Test artifacts command with artifacts present."""
        event = {
            "channel": "C12345",
            "user": "U12345",
            "ts": "1234567890.123456",
        }

        mock_artifact = MagicMock()
        mock_artifact.filename = "test.txt"
        mock_artifact.version = 1
        mock_artifact.description = "Test file"
        mock_artifact.last_modified = "2024-01-01T12:00:00Z"

        mock_adapter.extract_auth_claims = AsyncMock(
            return_value=MagicMock(id="user@example.com")
        )
        mock_adapter.context.list_artifacts = AsyncMock(return_value=[mock_artifact])

        logger = MagicMock()

        await handlers.handle_artifacts_command(
            mock_adapter, event, mock_client, logger
        )

        # Should post artifacts list with blocks
        mock_client.chat_postMessage.assert_called_once()
        call_args = mock_client.chat_postMessage.call_args[1]
        assert "blocks" in call_args
        assert len(call_args["blocks"]) > 0

    @pytest.mark.asyncio
    async def test_artifacts_auth_failure(self, mock_adapter, mock_client):
        """Test artifacts command with authentication failure."""
        event = {
            "channel": "C12345",
            "user": "U12345",
            "ts": "1234567890.123456",
        }

        mock_adapter.extract_auth_claims = AsyncMock(return_value=None)
        logger = MagicMock()

        await handlers.handle_artifacts_command(
            mock_adapter, event, mock_client, logger
        )

        # Should post error message
        mock_client.chat_postMessage.assert_called_once()
        assert "error" in mock_client.chat_postMessage.call_args[1]["text"].lower()


class TestHelpCommand:
    """Test suite for help command handler."""

    @pytest.mark.asyncio
    async def test_help_command(self, mock_adapter, mock_client):
        """Test help command posts available commands."""
        event = {
            "channel": "C12345",
            "user": "U12345",
            "ts": "1234567890.123456",
        }

        logger = MagicMock()

        await handlers.handle_help_command(mock_adapter, event, mock_client, logger)

        # Should post help message
        mock_client.chat_postMessage.assert_called_once()
        call_args = mock_client.chat_postMessage.call_args[1]
        assert "Available Commands" in call_args["text"]
        assert "artifacts" in call_args["text"].lower()
        assert "help" in call_args["text"].lower()


class TestCommandRegistry:
    """Test suite for command registration system."""

    def test_register_command_decorator(self):
        """Test that register_command decorator works."""

        @handlers.register_command("test_cmd")
        async def test_handler(adapter, event, client, logger):
            pass

        assert "test_cmd" in handlers.COMMAND_REGISTRY
        assert handlers.COMMAND_REGISTRY["test_cmd"] == test_handler
