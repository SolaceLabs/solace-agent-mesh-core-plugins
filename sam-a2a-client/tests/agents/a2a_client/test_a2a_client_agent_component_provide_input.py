import unittest
from unittest.mock import patch, MagicMock, ANY, call
import uuid
import asyncio
import base64
import json

# Adjust import paths as necessary
from src.agents.a2a_client.a2a_client_agent_component import A2AClientAgentComponent
from src.common_a2a.types import (
    Task,
    TaskState,
    TaskStatus,
    Message,  # Changed from A2AMessage
    TextPart,
    FilePart,
    FileContent,
    SendTaskResponse,
    JSONRPCError,
)
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo
from solace_ai_connector.common.log import log

# Import helper to create component instance
from .test_helpers import create_test_component


# Helper to create mock A2A responses (similar to test_a2a_client_action_invoke_call.py)
def _create_mock_task_response(
    state, message_parts=None, artifacts=None, task_id="task-123"
):
    """Helper to create a mock SendTaskResponse containing a Task object."""
    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id
    mock_task.status = MagicMock(spec=TaskStatus)
    mock_task.status.state = state
    # Use getattr to safely access parts, default to empty list
    mock_task.status.message = (
        MagicMock(spec=Message, parts=getattr(message_parts, "parts", [])) # Changed spec
        if message_parts
        else None
    )
    mock_task.artifacts = artifacts or []
    # Helper method to mimic Task.get_state()
    mock_task.get_state = MagicMock(return_value=state)

    # Wrap the Task in a mock SendTaskResponse
    mock_response = MagicMock(spec=SendTaskResponse)
    mock_response.result = mock_task
    mock_response.error = None  # No JSON-RPC error
    return mock_response


def _create_mock_part(part_type, **kwargs):
    """Helper to create a mock Part object (TextPart, FilePart, DataPart)."""
    if part_type == "text":
        return TextPart(text=kwargs.get("text", ""))
    elif part_type == "file":
        file_bytes = kwargs.get("bytes", b"")
        encoded_bytes = base64.b64encode(file_bytes).decode("utf-8")
        file_content = FileContent(
            bytes=encoded_bytes,
            name=kwargs.get("name", "file.dat"),
            mimeType=kwargs.get("mimeType", "application/octet-stream"),
        )
        return FilePart(file=file_content)
    elif part_type == "data":
        # Import locally only if needed
        from src.common_a2a.types import DataPart

        return DataPart(data=kwargs.get("data", {}))
    else:
        raise ValueError(f"Unknown part type: {part_type}")


class TestA2AClientAgentComponentProvideInput(unittest.TestCase):

    def setUp(self):
        # Mock services
        self.mock_cache_service = MagicMock()
        self.mock_a2a_client = MagicMock()
        self.mock_file_service = MagicMock()
        # Configure file service mock methods if needed for file tests
        self.mock_file_service.resolve_url.return_value = (
            b"resolved_content",
            b"original_bytes",
            {"name": "resolved.txt", "mime_type": "text/plain"},
        )
        self.mock_file_service.upload_from_buffer.return_value = {
            "url": "fs://uploaded/response.txt"
        }

        # Create component using helper
        self.component = create_test_component(
            cache_service_instance=self.mock_cache_service
        )

        # --- Fix: Mock connection_handler and assign mocks to it ---
        self.mock_connection_handler = MagicMock()
        self.mock_connection_handler.a2a_client = self.mock_a2a_client # Assign mock client here
        self.component.connection_handler = self.mock_connection_handler # Assign mock handler to component
        # -----------------------------------------------------------

        # Manually assign mocked file_service after creation
        self.component.file_service = self.mock_file_service

        # Mock an action instance needed for _process_parts
        # Import locally only if needed
        from src.agents.a2a_client.actions.a2a_client_action import A2AClientAction

        mock_skill = MagicMock()
        mock_action = MagicMock(spec=A2AClientAction)
        mock_action._process_parts = MagicMock(
            side_effect=A2AClientAction._process_parts
        )  # Use real method logic
        mock_action.component = self.component  # Link action back to component
        mock_action.name = "mock_processing_action"
        self.component.action_list = MagicMock()
        self.component.action_list.actions = [mock_action]

        # Common inputs
        self.follow_up_id = "sam-follow-up-123"
        self.original_a2a_task_id = "a2a-task-abc"
        self.session_id = "session-xyz"
        self.user_response_text = "My answer is blue"
        self.params = {
            "follow_up_id": self.follow_up_id,
            "user_response": self.user_response_text,
        }
        self.meta = {"session_id": self.session_id}

        # Patch asyncio.run
        self.async_run_patcher = patch(
            "src.agents.a2a_client.a2a_input_handler.asyncio.run"
        )
        self.mock_async_run = self.async_run_patcher.start()

        # Default asyncio.run behavior: execute the coroutine
        async def run_awaitable(awaitable):
            return await awaitable

        self.mock_async_run.side_effect = run_awaitable

        # Default cache behavior: return the original task ID
        self.mock_cache_service.get_data.return_value = self.original_a2a_task_id

    def tearDown(self):
        self.async_run_patcher.stop()

    def test_provide_input_success_completed(self):
        """Test successful follow-up leading to COMPLETED state."""
        # Arrange: Mock A2A client to return COMPLETED task
        response_text = "Task finished!"
        mock_response_part = _create_mock_part(part_type="text", text=response_text)
        mock_a2a_response = _create_mock_task_response(
            state=TaskState.COMPLETED,
            message_parts=[mock_response_part],
            task_id=self.original_a2a_task_id,
        )
        self.mock_a2a_client.send_task.return_value = mock_a2a_response

        # Act
        response = self.component._handle_provide_required_input(self.params, self.meta)

        # Assert
        self.mock_cache_service.get_data.assert_called_once_with(
            f"a2a_follow_up:{self.follow_up_id}"
        )
        self.mock_cache_service.remove_data.assert_called_once_with(
            f"a2a_follow_up:{self.follow_up_id}"
        )
        self.mock_a2a_client.send_task.assert_called_once()
        sent_params_dump = self.mock_a2a_client.send_task.call_args[0][0]
        self.assertEqual(sent_params_dump["id"], self.original_a2a_task_id)
        self.assertEqual(sent_params_dump["sessionId"], self.session_id)
        self.assertEqual(
            sent_params_dump["message"]["parts"][0]["text"], self.user_response_text
        )

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNone(response.error_info)
        self.assertEqual(response.message, response_text)
        self.assertIsNone(response.files)

    def test_provide_input_success_failed(self):
        """Test successful follow-up leading to FAILED state."""
        # Arrange: Mock A2A client to return FAILED task
        error_text = "Follow-up failed validation."
        mock_error_part = _create_mock_part(part_type="text", text=error_text)
        mock_a2a_response = _create_mock_task_response(
            state=TaskState.FAILED,
            message_parts=[mock_error_part],
            task_id=self.original_a2a_task_id,
        )
        self.mock_a2a_client.send_task.return_value = mock_a2a_response

        # Act
        response = self.component._handle_provide_required_input(self.params, self.meta)

        # Assert
        self.mock_cache_service.get_data.assert_called_once()
        self.mock_cache_service.remove_data.assert_called_once()
        self.mock_a2a_client.send_task.assert_called_once()
        sent_params_dump = self.mock_a2a_client.send_task.call_args[0][0]
        self.assertEqual(sent_params_dump["id"], self.original_a2a_task_id)

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info)
        self.assertIn("Failed (after follow-up)", response.message)
        self.assertIn(error_text, response.message)
        self.assertEqual(response.error_info.error_message, error_text)

    def test_provide_input_success_nested_input_required(self):
        """Test successful follow-up leading to another INPUT_REQUIRED state."""
        # Arrange: Mock A2A client to return INPUT_REQUIRED task
        nested_question = "Okay, blue, but which shade?"
        mock_nested_part = _create_mock_part(part_type="text", text=nested_question)
        mock_a2a_response = _create_mock_task_response(
            state=TaskState.INPUT_REQUIRED,
            message_parts=[mock_nested_part],
            task_id=self.original_a2a_task_id,
        )
        self.mock_a2a_client.send_task.return_value = mock_a2a_response

        # Mock uuid for the *new* follow-up ID
        new_generated_uuid = "nested-follow-up-uuid-456"
        with patch("src.agents.a2a_client.a2a_input_handler.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = new_generated_uuid

            # Act
            response = self.component._handle_provide_required_input(
                self.params, self.meta
            )

        # Assert
        self.mock_cache_service.get_data.assert_called_once_with(
            f"a2a_follow_up:{self.follow_up_id}"
        )
        self.mock_cache_service.remove_data.assert_called_once_with(
            f"a2a_follow_up:{self.follow_up_id}"
        )
        self.mock_a2a_client.send_task.assert_called_once()
        sent_params_dump = self.mock_a2a_client.send_task.call_args[0][0]
        self.assertEqual(sent_params_dump["id"], self.original_a2a_task_id)

        # Assert *new* cache entry was added
        self.mock_cache_service.add_data.assert_called_once_with(
            key=f"a2a_follow_up:{new_generated_uuid}",
            value=self.original_a2a_task_id,
            expiry=self.component.input_required_ttl,
        )

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNone(response.error_info)
        self.assertIn(nested_question, response.message)
        self.assertIn("provide_required_input", response.message)
        self.assertIn(f"`{new_generated_uuid}`", response.message)

    def test_provide_input_invalid_follow_up_id(self):
        """Test handling when the follow_up_id is not found in cache."""
        # Arrange: Mock cache to return None
        self.mock_cache_service.get_data.return_value = None

        # Act
        response = self.component._handle_provide_required_input(self.params, self.meta)

        # Assert
        self.mock_cache_service.get_data.assert_called_once_with(
            f"a2a_follow_up:{self.follow_up_id}"
        )
        self.mock_cache_service.remove_data.assert_not_called()
        self.mock_a2a_client.send_task.assert_not_called()

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info)
        self.assertIn("Invalid or expired follow-up ID", response.message)
        self.assertEqual(response.error_info.error_message, "Invalid Follow-up ID")

    def test_provide_input_missing_follow_up_id_param(self):
        """Test handling when 'follow_up_id' is missing from params."""
        # Arrange: Remove follow_up_id from params
        invalid_params = {"user_response": self.user_response_text}

        # Act
        response = self.component._handle_provide_required_input(
            invalid_params, self.meta
        )

        # Assert
        self.mock_cache_service.get_data.assert_not_called()
        self.mock_a2a_client.send_task.assert_not_called()

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info)
        self.assertIn("Missing required parameter: 'follow_up_id'", response.message)
        self.assertEqual(response.error_info.error_message, "Missing Parameter")

    def test_provide_input_missing_user_response_param(self):
        """Test handling when 'user_response' is missing from params."""
        # Arrange: Remove user_response from params
        invalid_params = {"follow_up_id": self.follow_up_id}

        # Act
        response = self.component._handle_provide_required_input(
            invalid_params, self.meta
        )

        # Assert
        self.mock_cache_service.get_data.assert_not_called()
        self.mock_a2a_client.send_task.assert_not_called()

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info)
        self.assertIn("Missing required parameter: 'user_response'", response.message)
        self.assertEqual(response.error_info.error_message, "Missing Parameter")

    def test_provide_input_communication_error(self):
        """Test handling of communication errors during the follow-up A2A call."""
        # Arrange: Mock A2A client to raise an error
        error_message = "Network unreachable"
        self.mock_a2a_client.send_task.side_effect = ConnectionError(error_message)

        # Act
        response = self.component._handle_provide_required_input(self.params, self.meta)

        # Assert
        self.mock_cache_service.get_data.assert_called_once()
        self.mock_cache_service.remove_data.assert_called_once()  # Cache entry removed even on error
        self.mock_a2a_client.send_task.assert_called_once()

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info)
        self.assertIn("Failed to execute follow-up", response.message)
        self.assertIn(
            "A2A Communication/Processing Error", response.error_info.error_message
        )
        self.assertIn(error_message, response.error_info.error_message)

    def test_provide_input_with_file(self):
        """Test successful follow-up including a file parameter."""
        # Arrange: Add a file URL to params
        file_url = "fs://follow_up/doc.pdf"
        params_with_file = self.params.copy()
        params_with_file["files"] = json.dumps([file_url])

        # Mock A2A client to return COMPLETED
        mock_a2a_response = _create_mock_task_response(
            state=TaskState.COMPLETED,
            message_parts=[_create_mock_part(text="File processed.")],
            task_id=self.original_a2a_task_id,
        )
        self.mock_a2a_client.send_task.return_value = mock_a2a_response

        # Act
        response = self.component._handle_provide_required_input(
            params_with_file, self.meta
        )

        # Assert
        self.mock_cache_service.get_data.assert_called_once()
        self.mock_cache_service.remove_data.assert_called_once()
        # Assert file service was called
        self.mock_file_service.resolve_url.assert_called_once_with(
            file_url, session_id=self.session_id, return_extra=True
        )
        # Assert A2A client was called
        self.mock_a2a_client.send_task.assert_called_once()
        sent_params_dump = self.mock_a2a_client.send_task.call_args[0][0]
        self.assertEqual(sent_params_dump["id"], self.original_a2a_task_id)
        # Check that message parts include both text and file
        self.assertEqual(len(sent_params_dump["message"]["parts"]), 2)
        self.assertEqual(sent_params_dump["message"]["parts"][0]["type"], "text")
        self.assertEqual(sent_params_dump["message"]["parts"][1]["type"], "file")
        self.assertEqual(
            sent_params_dump["message"]["parts"][1]["file"]["name"], "resolved.txt"
        ) # Name from mock resolve

        # Assert successful response
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNone(response.error_info)
        self.assertEqual(response.message, "File processed.")

    def test_provide_input_a2a_returns_rpc_error(self):
        """Test handling when A2A server returns a JSON-RPC level error."""
        # Arrange: Mock A2A client to return a response with an error field
        rpc_error = JSONRPCError(code=-32600, message="Invalid Request Structure")
        mock_a2a_response_with_error = MagicMock(spec=SendTaskResponse)
        mock_a2a_response_with_error.result = None
        mock_a2a_response_with_error.error = rpc_error
        self.mock_a2a_client.send_task.return_value = mock_a2a_response_with_error

        # Act
        response = self.component._handle_provide_required_input(self.params, self.meta)

        # Assert
        self.mock_cache_service.get_data.assert_called_once()
        self.mock_cache_service.remove_data.assert_called_once()
        self.mock_a2a_client.send_task.assert_called_once()

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info)
        self.assertIn("A2A agent reported an error during follow-up", response.message)
        self.assertIn(rpc_error.message, response.message)
        self.assertIn(
            f"A2A Error Code {rpc_error.code}", response.error_info.error_message
        )
        self.assertIn(rpc_error.message, response.error_info.error_message)


if __name__ == "__main__":
    unittest.main()
