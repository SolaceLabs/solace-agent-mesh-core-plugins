"""Integration tests for the Slack Gateway Adapter."""

import pytest
from unittest.mock import AsyncMock, patch, Mock

from solace_agent_mesh.gateway.adapter.types import (
    ResponseContext,
    SamTextPart,
    SamFilePart,
)


class TestSlackAdapterIntegration:
    """Integration tests for SlackAdapter end-to-end flows."""

    @pytest.mark.asyncio
    async def test_extract_auth_claims_integration(
        self, slack_adapter, sample_slack_message_event
    ):
        """Test full authentication flow extracts user identity."""
        claims = await slack_adapter.extract_auth_claims(sample_slack_message_event)

        # Verify behavior: user identity is extracted from Slack
        assert claims is not None
        assert claims.id == "test@example.com"
        assert claims.email == "test@example.com"
        assert claims.source == "slack_api"
        assert claims.raw_context["slack_user_id"] == "U12345"

    @pytest.mark.asyncio
    async def test_prepare_task_integration(
        self, slack_adapter, sample_slack_message_event
    ):
        """Test that Slack events are converted into tasks."""
        with patch.object(
            slack_adapter, "_resolve_mentions_in_text", return_value="Hello bot!"
        ):
            task = await slack_adapter.prepare_task(sample_slack_message_event)

        # Verify behavior: event is converted to task with correct structure
        assert task is not None
        assert len(task.parts) == 1
        assert task.parts[0].text == "Hello bot!"
        assert task.session_id.startswith("slack-C12345")
        assert task.target_agent == "OrchestratorAgent"

    @pytest.mark.asyncio
    async def test_prepare_task_with_file(self, slack_adapter, sample_slack_file_event):
        """Test that file attachments are included in tasks."""
        slack_adapter._download_file = AsyncMock(return_value=b"PDF content")

        with patch.object(
            slack_adapter, "_resolve_mentions_in_text", return_value="Here's a document"
        ):
            task = await slack_adapter.prepare_task(sample_slack_file_event)

        # Verify behavior: files are attached to the task
        assert len(task.parts) == 2
        assert isinstance(task.parts[0], SamTextPart)
        assert isinstance(task.parts[1], SamFilePart)
        assert task.parts[1].name == "document.pdf"

    @pytest.mark.asyncio
    async def test_user_email_caching(self, slack_adapter, sample_slack_message_event):
        """Test that user email lookups are cached to reduce API calls."""
        # First call - should hit the API
        claims1 = await slack_adapter.extract_auth_claims(sample_slack_message_event)
        assert claims1.email == "test@example.com"

        # Verify the email was cached
        cached_value = slack_adapter.context.cache_service.get_data(
            "slack_email_cache:U12345"
        )
        assert cached_value == "test@example.com"

        # Second call - should use cache
        slack_adapter.slack_app.client.users_profile_get.reset_mock()
        claims2 = await slack_adapter.extract_auth_claims(sample_slack_message_event)

        # Verify behavior: cache is used, API not called
        assert claims2.email == "test@example.com"
        slack_adapter.slack_app.client.users_profile_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_mention_resolution_integration(self, slack_adapter):
        """Test that @mentions are resolved to user identities."""
        text = "Hello <@U12345> and <@U67890>!"

        resolved = await slack_adapter._resolve_mentions_in_text(text)

        # Verify behavior: mentions are replaced with user info
        assert "@U12345" not in resolved
        assert "test@example.com" in resolved

    @pytest.mark.asyncio
    async def test_file_download_integration(self, slack_adapter):
        """Test downloading files from Slack."""
        file_info = {
            "url_private_download": "https://files.slack.com/test.pdf",
            "name": "test.pdf",
        }

        mock_response = Mock()
        mock_response.content = b"PDF content bytes"
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            content = await slack_adapter._download_file(file_info)

        # Verify behavior: file content is retrieved
        assert content == b"PDF content bytes"
