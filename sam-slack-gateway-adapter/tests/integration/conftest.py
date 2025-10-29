"""Pytest fixtures for integration tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from sam_slack_gateway_adapter.adapter import SlackAdapter, SlackAdapterConfig
from solace_agent_mesh.gateway.adapter.types import SamTextPart, SamFilePart


@pytest.fixture
def mock_slack_client():
    """Create a mock Slack client."""
    client = AsyncMock()
    client.chat_postMessage = AsyncMock(
        return_value={"ok": True, "ts": "1234567890.123456"}
    )
    client.chat_update = AsyncMock(return_value={"ok": True})
    client.chat_delete = AsyncMock(return_value={"ok": True})
    client.users_profile_get = AsyncMock(
        return_value={
            "ok": True,
            "profile": {"email": "test@example.com", "real_name": "Test User"},
        }
    )
    client.users_info = AsyncMock(
        return_value={
            "ok": True,
            "user": {
                "profile": {
                    "email": "test@example.com",
                    "real_name_normalized": "Test User",
                }
            },
        }
    )
    client.files_getUploadURLExternal = AsyncMock(
        return_value={"upload_url": "https://upload.test", "file_id": "F12345"}
    )
    client.files_completeUploadExternal = AsyncMock(return_value={"ok": True})
    return client


@pytest.fixture
def mock_slack_app(mock_slack_client):
    """Create a mock Slack Bolt AsyncApp."""
    app = MagicMock()
    app.client = mock_slack_client
    app.event = MagicMock(return_value=lambda f: f)
    app.command = MagicMock(return_value=lambda f: f)
    app.action = MagicMock(return_value=lambda f: f)
    return app


@pytest.fixture
def mock_artifact_service():
    """Create a mock artifact service."""
    service = MagicMock()
    service.get_artifact = AsyncMock(return_value=b"test artifact content")
    service.save_artifact = AsyncMock(return_value="artifact_id_123")
    service.list_artifacts = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_cache_service():
    """Create a mock cache service."""
    service = MagicMock()
    cache_data = {}

    def get_data(key):
        return cache_data.get(key)

    def add_data(key, value, expiry=None):
        cache_data[key] = value

    service.get_data = MagicMock(side_effect=get_data)
    service.add_data = MagicMock(side_effect=add_data)
    return service


@pytest.fixture
def mock_gateway_context(mock_artifact_service, mock_cache_service):
    """Create a fully mocked GatewayContext."""
    context = MagicMock()
    context.adapter_config = SlackAdapterConfig(
        slack_bot_token="xoxb-test-token",
        slack_app_token="xapp-test-token",
        slack_initial_status_message="Thinking...",
        correct_markdown_formatting=True,
        feedback_enabled=False,
        slack_email_cache_ttl_seconds=3600,
    )
    context.artifact_service = mock_artifact_service
    context.cache_service = mock_cache_service
    context.get_config = MagicMock(return_value="OrchestratorAgent")
    context.handle_external_input = AsyncMock()
    context.submit_feedback = AsyncMock()
    context.cancel_task = AsyncMock()
    context.list_artifacts = AsyncMock(return_value=[])
    context.load_artifact_content = AsyncMock(return_value=b"test content")

    # Mock task state storage
    task_states = {}

    def get_task_state(task_id, key, default=None):
        return task_states.get(f"{task_id}:{key}", default)

    def set_task_state(task_id, key, value):
        task_states[f"{task_id}:{key}"] = value

    context.get_task_state = MagicMock(side_effect=get_task_state)
    context.set_task_state = MagicMock(side_effect=set_task_state)

    # Mock part creation functions (already imported at top)
    context.create_text_part = lambda text: SamTextPart(text=text)
    context.create_file_part_from_bytes = lambda **kwargs: SamFilePart(**kwargs)

    return context


@pytest.fixture
async def slack_adapter(mock_gateway_context, mock_slack_app):
    """Create a SlackAdapter instance for integration testing."""
    adapter = SlackAdapter()
    adapter.context = mock_gateway_context
    adapter.slack_app = mock_slack_app
    adapter.slack_handler = None  # Skip actual socket mode handler
    adapter.message_queues = {}
    return adapter


@pytest.fixture
def sample_slack_message_event():
    """Sample Slack message event payload."""
    return {
        "type": "message",
        "channel": "C12345",
        "channel_type": "im",
        "user": "U12345",
        "team": "T67890",
        "text": "Hello bot!",
        "ts": "1234567890.123456",
    }


@pytest.fixture
def sample_slack_mention_event():
    """Sample Slack app_mention event payload."""
    return {
        "type": "app_mention",
        "channel": "C12345",
        "channel_type": "channel",
        "user": "U12345",
        "team": "T67890",
        "text": "<@B12345> What's the weather?",
        "ts": "1234567890.123456",
    }


@pytest.fixture
def sample_slack_file_event():
    """Sample Slack message event with file attachment."""
    return {
        "type": "message",
        "channel": "C12345",
        "channel_type": "im",
        "user": "U12345",
        "team": "T67890",
        "text": "Here's a document",
        "ts": "1234567890.123456",
        "files": [
            {
                "id": "F12345",
                "name": "document.pdf",
                "mimetype": "application/pdf",
                "url_private_download": "https://files.slack.com/files/document.pdf",
                "size": 1024,
            }
        ],
    }
