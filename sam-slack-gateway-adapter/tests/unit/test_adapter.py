"""Unit tests for the Slack Gateway Adapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock

from sam_slack_gateway_adapter.adapter import (
    SlackAdapter,
    SlackAdapterConfig,
)
from solace_agent_mesh.gateway.adapter.types import (
    GatewayContext,
    ResponseContext,
    SamTask,
    SamTextPart,
    SamFilePart,
    SamError,
)


@pytest.fixture
def mock_gateway_context():
    """Create a mock GatewayContext."""
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
    context.create_text_part = lambda text: SamTextPart(text=text)
    context.create_file_part_from_bytes = lambda **kwargs: SamFilePart(**kwargs)
    context.get_task_state = MagicMock(return_value=None)
    context.set_task_state = MagicMock()
    return context


@pytest.fixture
def slack_adapter(mock_gateway_context):
    """Create a SlackAdapter instance with mocked dependencies."""
    adapter = SlackAdapter()
    adapter.context = mock_gateway_context
    adapter.slack_app = MagicMock()
    adapter.slack_app.client = AsyncMock()
    return adapter


class TestSlackAdapterConfig:
    """Test suite for SlackAdapterConfig validation."""

    def test_config_with_required_fields(self):
        """Test config creation with all required fields."""
        config = SlackAdapterConfig(
            slack_bot_token="xoxb-test",
            slack_app_token="xapp-test",
        )
        assert config.slack_bot_token == "xoxb-test"
        assert config.slack_app_token == "xapp-test"
        assert config.slack_initial_status_message == "Got it, thinking..."
        assert config.correct_markdown_formatting is True
        assert config.feedback_enabled is False
        assert config.slack_email_cache_ttl_seconds == 3600

    def test_config_with_custom_values(self):
        """Test config with custom values."""
        config = SlackAdapterConfig(
            slack_bot_token="xoxb-test",
            slack_app_token="xapp-test",
            slack_initial_status_message="Processing...",
            correct_markdown_formatting=False,
            feedback_enabled=True,
            slack_email_cache_ttl_seconds=7200,
        )
        assert config.slack_initial_status_message == "Processing..."
        assert config.correct_markdown_formatting is False
        assert config.feedback_enabled is True
        assert config.slack_email_cache_ttl_seconds == 7200


class TestExtractAuthClaims:
    """Test suite for extract_auth_claims method."""

    @pytest.mark.asyncio
    async def test_extract_auth_claims_with_email(self, slack_adapter):
        """Test extracting auth claims when email is available."""
        slack_adapter.slack_app.client.users_profile_get = AsyncMock(
            return_value={
                "ok": True,
                "profile": {"email": "user@example.com"},
            }
        )

        external_input = {
            "user": "U12345",
            "team": "T67890",
        }

        claims = await slack_adapter.extract_auth_claims(external_input)

        assert claims is not None
        assert claims.id == "user@example.com"
        assert claims.email == "user@example.com"
        assert claims.source == "slack_api"
        assert claims.raw_context["slack_user_id"] == "U12345"
        assert claims.raw_context["slack_team_id"] == "T67890"

    @pytest.mark.asyncio
    async def test_extract_auth_claims_fallback_no_email(self, slack_adapter):
        """Test extracting auth claims when email is not available."""
        slack_adapter.slack_app.client.users_profile_get = AsyncMock(
            side_effect=Exception("Email not available")
        )

        external_input = {
            "user": "U12345",
            "team": "T67890",
        }

        claims = await slack_adapter.extract_auth_claims(external_input)

        assert claims is not None
        assert claims.id == "slack:T67890:U12345"
        assert claims.email is None
        assert claims.source == "slack_fallback"

    @pytest.mark.asyncio
    async def test_extract_auth_claims_bot_message(self, slack_adapter):
        """Test that bot messages are skipped."""
        external_input = {
            "bot_id": "B12345",
            "user": "U12345",
            "team": "T67890",
        }

        claims = await slack_adapter.extract_auth_claims(external_input)
        assert claims is None

    @pytest.mark.asyncio
    async def test_extract_auth_claims_missing_user_id(self, slack_adapter):
        """Test handling when user_id is missing."""
        external_input = {
            "team": "T67890",
        }

        claims = await slack_adapter.extract_auth_claims(external_input)
        assert claims is None

    @pytest.mark.asyncio
    async def test_extract_auth_claims_with_cache(self, slack_adapter):
        """Test that cached claims are used when available."""
        mock_cache = MagicMock()
        mock_cache.get_data = MagicMock(return_value="cached@example.com")
        slack_adapter.context.cache_service = mock_cache

        external_input = {
            "user": "U12345",
            "team": "T67890",
        }

        claims = await slack_adapter.extract_auth_claims(external_input)

        assert claims is not None
        assert claims.id == "cached@example.com"
        assert claims.email == "cached@example.com"
        # Verify that Slack API was not called
        slack_adapter.slack_app.client.users_profile_get.assert_not_called()


class TestPrepareTask:
    """Test suite for prepare_task method."""

    @pytest.mark.asyncio
    async def test_prepare_task_text_only(self, slack_adapter):
        """Test preparing a task with text only."""
        external_input = {
            "channel": "C12345",
            "ts": "1234567890.123456",
            "text": "Hello, bot!",
        }

        with patch.object(slack_adapter, "_resolve_mentions_in_text", return_value="Hello, bot!"):
            task = await slack_adapter.prepare_task(external_input)

        assert isinstance(task, SamTask)
        assert len(task.parts) == 1
        assert isinstance(task.parts[0], SamTextPart)
        assert task.parts[0].text == "Hello, bot!"
        assert task.session_id == "slack-C12345-1234567890_123456"
        assert task.target_agent == "OrchestratorAgent"

    @pytest.mark.asyncio
    async def test_prepare_task_bot_message_ignored(self, slack_adapter):
        """Test that bot messages raise ValueError."""
        external_input = {
            "bot_id": "B12345",
            "channel": "C12345",
            "text": "Bot message",
        }

        with pytest.raises(ValueError, match="Ignoring bot message"):
            await slack_adapter.prepare_task(external_input)

    @pytest.mark.asyncio
    async def test_prepare_task_with_thread(self, slack_adapter):
        """Test preparing a task with thread timestamp."""
        external_input = {
            "channel": "C12345",
            "ts": "1234567890.999999",
            "thread_ts": "1234567890.123456",
            "text": "Reply in thread",
        }

        with patch.object(slack_adapter, "_resolve_mentions_in_text", return_value="Reply in thread"):
            task = await slack_adapter.prepare_task(external_input)

        assert task.session_id == "slack-C12345-1234567890_123456"

    @pytest.mark.asyncio
    async def test_prepare_task_empty_content(self, slack_adapter):
        """Test that empty content raises ValueError."""
        external_input = {
            "channel": "C12345",
            "ts": "1234567890.123456",
            "text": "   ",
        }

        with patch.object(slack_adapter, "_resolve_mentions_in_text", return_value="   "):
            with pytest.raises(ValueError, match="No content to send to agent"):
                await slack_adapter.prepare_task(external_input)

    @pytest.mark.asyncio
    async def test_prepare_task_with_files(self, slack_adapter):
        """Test preparing a task with file attachments."""
        external_input = {
            "channel": "C12345",
            "ts": "1234567890.123456",
            "text": "Here's a file",
            "files": [
                {
                    "name": "test.txt",
                    "mimetype": "text/plain",
                    "url_private_download": "https://files.slack.com/test.txt",
                }
            ],
        }

        slack_adapter._download_file = AsyncMock(return_value=b"file content")

        with patch.object(slack_adapter, "_resolve_mentions_in_text", return_value="Here's a file"):
            task = await slack_adapter.prepare_task(external_input)

        assert len(task.parts) == 2
        assert isinstance(task.parts[0], SamTextPart)
        assert isinstance(task.parts[1], SamFilePart)
        assert task.parts[1].name == "test.txt"


class TestHandleError:
    """Test suite for handle_error method - tests error message formatting."""

    @pytest.mark.asyncio
    async def test_handle_error_formats_generic_error(self, slack_adapter):
        """Test that generic errors are formatted with error icon and message."""
        context = ResponseContext(
            task_id="task-123",
            session_id="session-123",
            user_id="user-123",
            platform_context={"channel_id": "C12345", "thread_ts": "1234567890.123456"},
        )

        slack_adapter.context.get_task_state = MagicMock(return_value="status-ts-123")
        # Use correct API: code is an integer, category must be from allowed values
        error = SamError(code=1001, message="Something went wrong", category="FAILED")

        with patch("sam_slack_gateway_adapter.utils.update_slack_message") as mock_update:
            await slack_adapter.handle_error(error, context)

        # Test the actual behavior: error message formatting includes icon and message
        args = mock_update.call_args
        assert "❌ Error: Something went wrong" in args[0]

    @pytest.mark.asyncio
    async def test_handle_error_formats_canceled_differently(self, slack_adapter):
        """Test that canceled errors use different formatting than generic errors."""
        context = ResponseContext(
            task_id="task-123",
            session_id="session-123",
            user_id="user-123",
            platform_context={"channel_id": "C12345", "thread_ts": "1234567890.123456"},
        )

        slack_adapter.context.get_task_state = MagicMock(return_value="status-ts-123")
        # Use correct API with CANCELED category and integer code
        error = SamError(code=2001, message="Task was canceled", category="CANCELED")

        with patch("sam_slack_gateway_adapter.utils.update_slack_message") as mock_update:
            await slack_adapter.handle_error(error, context)

        # Test the actual behavior: canceled uses different icon and message
        args = mock_update.call_args
        assert "🛑 Task canceled." in args[0]
        assert "❌" not in args[0]  # Should NOT use error icon


class TestHelperMethods:
    """Test suite for helper methods."""

    def test_get_icon_for_mime_type(self, slack_adapter):
        """Test MIME type to icon conversion."""
        assert slack_adapter._get_icon_for_mime_type("image/png") == ":art:"
        assert slack_adapter._get_icon_for_mime_type("audio/mp3") == ":sound:"
        assert slack_adapter._get_icon_for_mime_type("video/mp4") == ":film_frames:"
        assert slack_adapter._get_icon_for_mime_type("application/pdf") == ":page_facing_up:"
        assert slack_adapter._get_icon_for_mime_type("application/zip") == ":compression:"
        assert slack_adapter._get_icon_for_mime_type("text/plain") == ":page_with_curl:"
        assert slack_adapter._get_icon_for_mime_type(None) == ":page_facing_up:"

    def test_format_text_with_correction(self, slack_adapter):
        """Test text formatting with markdown correction enabled."""
        text = "**bold** text"
        formatted = slack_adapter._format_text(text)
        assert formatted == "*bold* text"

    def test_format_text_without_correction(self, slack_adapter):
        """Test text formatting with markdown correction disabled."""
        slack_adapter.context.adapter_config.correct_markdown_formatting = False
        text = "**bold** text"
        formatted = slack_adapter._format_text(text)
        assert formatted == "**bold** text"

    @pytest.mark.asyncio
    async def test_resolve_mentions_in_text(self, slack_adapter):
        """Test resolving user mentions in text."""
        slack_adapter.slack_app.client.users_info = AsyncMock(
            return_value={
                "ok": True,
                "user": {
                    "profile": {
                        "email": "user@example.com",
                        "real_name_normalized": "John Doe",
                    }
                },
            }
        )

        text = "Hello <@U12345>!"
        resolved = await slack_adapter._resolve_mentions_in_text(text)
        assert resolved == "Hello user@example.com!"

    @pytest.mark.asyncio
    async def test_download_file(self, slack_adapter):
        """Test downloading a file from Slack."""
        file_info = {
            "url_private_download": "https://files.slack.com/test.txt",
        }

        mock_response = Mock()
        mock_response.content = b"file content"
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            content = await slack_adapter._download_file(file_info)

        assert content == b"file content"
