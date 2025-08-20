import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# This allows us to test the handlers without needing a full Slack connection
with patch("sam_slack.component.SLACK_BOLT_AVAILABLE", True):
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
