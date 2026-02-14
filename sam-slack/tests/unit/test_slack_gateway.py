import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sam_slack import component
from solace_agent_mesh.common.data_parts import (
    ArtifactCreationProgressData,
    AgentProgressUpdateData,
)

# This allows us to test the handlers without needing a full Slack connection
with patch.object(component, "SLACK_BOLT_AVAILABLE", True):
    from sam_slack.handlers import (
        handle_slack_message,
        handle_slack_mention,
        _process_slack_event,
    )
    from sam_slack.component import SlackGatewayComponent


@pytest.mark.asyncio
@patch("sam_slack.handlers._process_slack_event", new_callable=AsyncMock)
async def test_handle_slack_message_in_dm(mock_process_event):
    """
    Tests that a direct message ('im') is correctly processed.
    """
    mock_component = MagicMock()
    mock_event = {"channel_type": "im", "text": "Hello"}
    mock_say = AsyncMock()

    await handle_slack_message(mock_component, mock_event, mock_say, None)

    mock_process_event.assert_called_once_with(
        mock_component, mock_event, mock_say, None
    )


@pytest.mark.asyncio
@patch("sam_slack.handlers._process_slack_event", new_callable=AsyncMock)
async def test_handle_slack_message_in_channel_ignored(mock_process_event):
    """
    Tests that a message in a public channel that is not a thread mention is ignored.
    """
    mock_component = MagicMock()
    mock_event = {"channel_type": "channel", "text": "Just a random message"}

    await handle_slack_message(mock_component, mock_event, None, None)

    mock_process_event.assert_not_called()


@pytest.mark.asyncio
@patch("sam_slack.handlers._process_slack_event", new_callable=AsyncMock)
async def test_handle_app_mention(mock_process_event):
    """
    Tests that an app_mention event is always processed.
    """
    mock_component = MagicMock()
    mock_event = {"type": "app_mention", "text": "<@BOTID> what is the status?"}
    mock_say = AsyncMock()

    await handle_slack_mention(mock_component, mock_event, mock_say, None)

    mock_process_event.assert_called_once_with(
        mock_component, mock_event, mock_say, None
    )


@pytest.mark.asyncio
async def test_process_slack_event_auth_failure():
    """
    Tests that an authentication failure is handled correctly.
    """
    mock_component = MagicMock()
    mock_component.authenticate_and_enrich_user = AsyncMock(return_value=None)
    mock_event = {"user": "U123", "channel": "C123", "ts": "123.456"}
    mock_say = AsyncMock()

    await _process_slack_event(mock_component, mock_event, mock_say, None)

    mock_say.assert_called_once_with(
        text="Sorry, I could not authenticate your request. Please try again or contact support.",
        thread_ts="123.456",
    )


@pytest.mark.asyncio
async def test_process_slack_event_translation_error():
    """
    Tests that a ValueError during translation is handled.
    """
    mock_component = MagicMock()
    mock_component.authenticate_and_enrich_user = AsyncMock(return_value={"id": "user"})
    mock_component._translate_external_input = AsyncMock(
        side_effect=ValueError("Cannot determine target agent")
    )
    mock_event = {"user": "U123", "channel": "C123", "ts": "123.456"}
    mock_say = AsyncMock()

    await _process_slack_event(mock_component, mock_event, mock_say, None)

    mock_say.assert_called_once_with(
        text="Sorry, I couldn't determine which agent to send your request to.",
        thread_ts="123.456",
    )


@pytest.mark.asyncio
async def test_process_slack_event_permission_error():
    """
    Tests that a PermissionError during submission is handled.
    """
    mock_component = MagicMock()
    mock_component.authenticate_and_enrich_user = AsyncMock(return_value={"id": "user"})
    mock_component._translate_external_input = AsyncMock(
        return_value=("agent", [], {})
    )
    mock_component.submit_a2a_task = AsyncMock(
        side_effect=PermissionError("You shall not pass!")
    )
    mock_event = {"user": "U123", "channel": "C123", "ts": "123.456"}
    mock_say = AsyncMock()

    await _process_slack_event(mock_component, mock_event, mock_say, None)

    mock_say.assert_called_once_with(
        text="Sorry, your request was denied: You shall not pass!",
        thread_ts="123.456",
    )


# =============================================================================
# DataPart Parsing Tests - Added to prevent field name mismatch bugs
# =============================================================================


class TestArtifactCreationProgressDataParsing:
    """
    Tests for ArtifactCreationProgressData parsing to ensure field names
    match between the model and the component code.
    
    This test class was added after a production incident where the component
    used 'bytes_saved' but the model defined 'bytes_transferred', causing
    repeated parsing failures that flooded the message queue.
    """

    def test_artifact_creation_progress_model_fields(self):
        """
        Verify that ArtifactCreationProgressData has the expected field names.
        This test ensures the model schema matches what the component expects.
        """
        # Create a valid artifact creation progress data
        test_data = {
            "type": "artifact_creation_progress",
            "filename": "test_artifact.md",
            "status": "in-progress",
            "bytes_transferred": 1024,
        }
        
        progress_data = ArtifactCreationProgressData.model_validate(test_data)
        
        # Verify the field that was previously buggy (bytes_saved vs bytes_transferred)
        assert hasattr(progress_data, "bytes_transferred"), \
            "ArtifactCreationProgressData must have 'bytes_transferred' field"
        assert progress_data.bytes_transferred == 1024
        
        # Verify it does NOT have the old buggy field name
        assert not hasattr(progress_data, "bytes_saved"), \
            "ArtifactCreationProgressData should NOT have 'bytes_saved' field"

    def test_artifact_creation_progress_status_text_generation(self):
        """
        Test that the status text can be generated correctly using the model fields.
        This mirrors the actual code in component.py line ~1145.
        """
        test_data = {
            "type": "artifact_creation_progress",
            "filename": "my_document.pdf",
            "status": "in-progress",
            "bytes_transferred": 2048,
        }
        
        progress_data = ArtifactCreationProgressData.model_validate(test_data)
        
        # This is the exact pattern used in component.py - must use bytes_transferred
        status_signal_text = f":floppy_disk: Creating artifact `{progress_data.filename}` ({progress_data.bytes_transferred} bytes)..."
        
        assert "my_document.pdf" in status_signal_text
        assert "2048 bytes" in status_signal_text

    def test_artifact_creation_progress_all_statuses(self):
        """
        Test that all valid status values can be parsed.
        """
        valid_statuses = ["in-progress", "completed", "failed", "cancelled"]
        
        for status in valid_statuses:
            test_data = {
                "type": "artifact_creation_progress",
                "filename": "test.txt",
                "status": status,
                "bytes_transferred": 100,
            }
            
            progress_data = ArtifactCreationProgressData.model_validate(test_data)
            assert progress_data.status == status

    def test_artifact_creation_progress_with_optional_fields(self):
        """
        Test parsing with optional fields included.
        """
        test_data = {
            "type": "artifact_creation_progress",
            "filename": "report.md",
            "status": "completed",
            "bytes_transferred": 5000,
            "description": "Monthly sales report",
            "mime_type": "text/markdown",
            "version": 2,
            "function_call_id": "call_abc123",
        }
        
        progress_data = ArtifactCreationProgressData.model_validate(test_data)
        
        assert progress_data.filename == "report.md"
        assert progress_data.bytes_transferred == 5000
        assert progress_data.description == "Monthly sales report"
        assert progress_data.mime_type == "text/markdown"
        assert progress_data.version == 2
        assert progress_data.function_call_id == "call_abc123"


class TestAgentProgressUpdateDataParsing:
    """
    Tests for AgentProgressUpdateData parsing.
    """

    def test_agent_progress_update_model_fields(self):
        """
        Verify that AgentProgressUpdateData has the expected field names.
        """
        test_data = {
            "type": "agent_progress_update",
            "status_text": "Analyzing the document...",
        }
        
        progress_data = AgentProgressUpdateData.model_validate(test_data)
        
        assert hasattr(progress_data, "status_text")
        assert progress_data.status_text == "Analyzing the document..."

    def test_agent_progress_update_status_text_generation(self):
        """
        Test that the status text can be generated correctly.
        This mirrors the actual code in component.py line ~1126.
        """
        test_data = {
            "type": "agent_progress_update",
            "status_text": "Processing your request...",
        }
        
        progress_data = AgentProgressUpdateData.model_validate(test_data)
        
        # This is the exact pattern used in component.py
        status_signal_text = f":thinking_face: {progress_data.status_text}"
        
        assert "Processing your request..." in status_signal_text
