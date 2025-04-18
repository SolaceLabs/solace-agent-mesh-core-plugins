import unittest
from unittest.mock import patch, MagicMock, ANY
import uuid

# Adjust import paths as necessary
from src.agents.a2a_client.a2a_client_agent_component import A2AClientAgentComponent
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo

# Mock A2A types needed for assertions - EXPECTING THESE TO BE `Any` in the test env
from src.agents.a2a_client.actions.a2a_client_action import (
    TaskSendParams,
    A2AMessage,
    TextPart,
    FilePart,
    FileContent,
    Task,
    TaskState,
    TaskStatus,
    Artifact,
)

# Import helper to create component instance
from .test_helpers import create_test_component

class MockFileService:
    def resolve_url(self, url, session_id=None):
        if url == "follow_up_file_url":
            mock_file = MagicMock()
            mock_file.bytes = b"follow_up_content"
            mock_file.name = "follow_up.txt"
            mock_file.mime_type = "text/plain"
            return mock_file
        else:
            raise FileNotFoundError(f"Mock File Not Found: {url}")

    def upload_from_buffer(self, content, file_name, session_id, mime_type=None, data_source=None):
        # Simulate upload for response processing
        return {
            "url": f"http://fileservice/{file_name}",
            "name": file_name,
            "mime_type": mime_type or "application/octet-stream",
            "size": len(content),
            "data_source": data_source,
        }

class TestA2AClientAgentComponentProvideInput(unittest.TestCase):

    def setUp(self):
        self.mock_a2a_client = MagicMock()
        self.mock_cache_service = MagicMock()
        self.mock_file_service = MockFileService() # Use our mock

        # Create component instance using helper, passing mocks
        self.component = create_test_component(
            cache_service_instance=self.mock_cache_service,
            # Need to explicitly pass file_service and a2a_client mocks
            # as the helper doesn't handle these by default
        )
        # Manually assign the mocks after creation via helper
        self.component.a2a_client = self.mock_a2a_client
        self.component.file_service = self.mock_file_service

        # Mock the _process_parts method directly on the component instance
        # as finding a specific action instance is tricky in the handler
        self.component._process_parts = MagicMock(side_effect=self._mock_process_parts_side_effect)

    def _mock_process_parts_side_effect(self, parts, session_id, response_data):
        """Simulates the behavior of _process_parts for testing the handler."""
        msg = ""
        files = []
        for part in parts:
            if getattr(part, 'type', None) == "text":
                msg += getattr(part, 'text', '')
            elif getattr(part, 'type', None) == "file":
                # Simulate upload call within _process_parts
                file_content = getattr(part, 'file', None)
                if file_content:
                    file_bytes_b64 = getattr(file_content, 'bytes', '')
                    file_name = getattr(file_content, 'name', 'unknown')
                    mime_type = getattr(file_content, 'mimeType', 'app/octet')
                    try:
                        import base64
                        file_bytes = base64.b64decode(file_bytes_b64)
                        file_meta = self.mock_file_service.upload_from_buffer(
                            file_bytes, file_name, session_id, mime_type, ANY
                        )
                        if file_meta:
                            files.append(file_meta)
                    except Exception:
                        pass # Ignore upload errors in mock
            elif getattr(part, 'type', None) == "data":
                data_content = getattr(part, 'data', None)
                if isinstance(data_content, dict):
                    response_data.update(data_content)
        return msg, files

    def _create_mock_task_response(self, state, message_parts=None, artifacts=None, task_id="task-123"):
        """Helper to create a mock Task object."""
        mock_task = MagicMock(spec=Task)
        mock_task.id = task_id
        mock_task.status = MagicMock(spec=TaskStatus)
        mock_task.status.state = state
        if message_parts:
            mock_task.status.message = MagicMock(spec=A2AMessage)
            mock_task.status.message.parts = message_parts
        else:
            mock_task.status.message = None
        mock_task.artifacts = artifacts or []
        return mock_task

    def _create_mock_part(self, part_type, **kwargs):
        """Helper to create a mock Part object."""
        mock_part = MagicMock()
        mock_part.type = part_type
        if part_type == "text":
            mock_part.text = kwargs.get("text", "")
        elif part_type == "file":
            mock_file = MagicMock(spec=FileContent)
            # Store as base64 string as FileContent expects
            import base64
            mock_file.bytes = base64.b64encode(kwargs.get("bytes", b"")).decode('utf-8')
            mock_file.name = kwargs.get("name", "file.dat")
            mock_file.mimeType = kwargs.get("mimeType", "application/octet-stream")
            mock_part.file = mock_file
        elif part_type == "data":
            mock_part.data = kwargs.get("data", {})
        return mock_part

    @patch("src.agents.a2a_client.a2a_client_agent_component.TextPart")
    @patch("src.agents.a2a_client.a2a_client_agent_component.TaskSendParams")
    @patch("src.agents.a2a_client.a2a_client_agent_component.A2AMessage")
    def test_handle_provide_input_success_completed(self, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test successful follow-up leading to COMPLETED state."""
        follow_up_id = "follow-up-1"
        original_task_id = "original-task-abc"
        user_response_text = "Blue"
        params = {"follow_up_id": follow_up_id, "user_response": user_response_text}
        meta = {"session_id": "session-follow-up"}

        # Mock cache returning the original task ID
        self.mock_cache_service.get.return_value = original_task_id

        # Mock A2A response after follow-up
        mock_final_part = self._create_mock_part(part_type="text", text="Here is the blue image.")
        mock_response_task = self._create_mock_task_response(
            state="completed", message_parts=[mock_final_part], task_id=original_task_id
        )
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors for the follow-up request
        MockTextPart.return_value = MagicMock(text=user_response_text)
        MockA2AMessage.return_value = MagicMock(role="user", parts=[MockTextPart.return_value])
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {"id": original_task_id, "sessionId": ANY, "message": ANY, "acceptedOutputModes": ANY}
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.component._handle_provide_required_input(params, meta)

        self.mock_cache_service.get.assert_called_once_with(f"a2a_follow_up:{follow_up_id}")
        self.mock_cache_service.delete.assert_called_once_with(f"a2a_follow_up:{follow_up_id}")
        self.mock_a2a_client.send_task.assert_called_once()
        # Check that the task ID in the sent params matches the retrieved one
        sent_params_dump = self.mock_a2a_client.send_task.call_args[0][0]
        self.assertEqual(sent_params_dump['id'], original_task_id)

        self.assertIsNone(response.error_info)
        self.assertEqual(response.message, "Here is the blue image.")
        self.assertIsNone(response.files)
        self.assertIsNone(response.data)

    @patch("src.agents.a2a_client.a2a_client_agent_component.TextPart")
    @patch("src.agents.a2a_client.a2a_client_agent_component.FilePart") # Need to mock FilePart too
    @patch("src.agents.a2a_client.a2a_client_agent_component.FileContent") # And FileContent
    @patch("src.agents.a2a_client.a2a_client_agent_component.TaskSendParams")
    @patch("src.agents.a2a_client.a2a_client_agent_component.A2AMessage")
    def test_handle_provide_input_with_file_success(self, MockA2AMessage, MockTaskSendParams, MockFileContent, MockFilePart, MockTextPart):
        """Test successful follow-up including a file."""
        follow_up_id = "follow-up-file"
        original_task_id = "original-task-file"
        user_response_text = "Use this file"
        file_url = "follow_up_file_url"
        params = {"follow_up_id": follow_up_id, "user_response": user_response_text, "files": [file_url]}
        meta = {"session_id": "session-follow-up-file"}

        self.mock_cache_service.get.return_value = original_task_id
        mock_response_task = self._create_mock_task_response(state="completed", task_id=original_task_id)
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors
        mock_text_part_inst = MagicMock(text=user_response_text)
        MockTextPart.return_value = mock_text_part_inst
        mock_file_content_inst = MagicMock(bytes=ANY, name="follow_up.txt", mimeType="text/plain")
        MockFileContent.return_value = mock_file_content_inst
        mock_file_part_inst = MagicMock(file=mock_file_content_inst)
        MockFilePart.return_value = mock_file_part_inst
        MockA2AMessage.return_value = MagicMock(role="user", parts=[mock_text_part_inst, mock_file_part_inst])
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {"id": original_task_id, "sessionId": ANY, "message": ANY, "acceptedOutputModes": ANY}
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.component._handle_provide_required_input(params, meta)

        self.mock_cache_service.get.assert_called_once_with(f"a2a_follow_up:{follow_up_id}")
        self.mock_cache_service.delete.assert_called_once_with(f"a2a_follow_up:{follow_up_id}")
        self.mock_a2a_client.send_task.assert_called_once()
        # Verify FilePart was constructed and included
        MockFilePart.assert_called_once()
        sent_message = MockA2AMessage.call_args[1]['parts']
        self.assertEqual(len(sent_message), 2) # Text + File
        self.assertIn(mock_file_part_inst, sent_message)

        self.assertIsNone(response.error_info)
        self.assertEqual(response.message, "Task completed.") # Default message as mock response had no parts

    @patch("src.agents.a2a_client.a2a_client_agent_component.TextPart")
    @patch("src.agents.a2a_client.a2a_client_agent_component.TaskSendParams")
    @patch("src.agents.a2a_client.a2a_client_agent_component.A2AMessage")
    def test_handle_provide_input_invalid_id(self, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test handling of invalid or expired follow_up_id."""
        follow_up_id = "invalid-id"
        params = {"follow_up_id": follow_up_id, "user_response": "Doesn't matter"}
        meta = {"session_id": "session-invalid"}

        # Mock cache returning None
        self.mock_cache_service.get.return_value = None

        response = self.component._handle_provide_required_input(params, meta)

        self.mock_cache_service.get.assert_called_once_with(f"a2a_follow_up:{follow_up_id}")
        self.mock_a2a_client.send_task.assert_not_called()
        self.mock_cache_service.delete.assert_not_called()

        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "Invalid or expired follow-up ID. Please start the task again.")
        self.assertEqual(response.error_info.error_message, "Invalid Follow-up ID")

    @patch("src.agents.a2a_client.a2a_client_agent_component.TextPart")
    @patch("src.agents.a2a_client.a2a_client_agent_component.TaskSendParams")
    @patch("src.agents.a2a_client.a2a_client_agent_component.A2AMessage")
    def test_handle_provide_input_cache_error(self, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test handling of errors during cache retrieval."""
        follow_up_id = "cache-error-id"
        params = {"follow_up_id": follow_up_id, "user_response": "Cache fail"}
        meta = {"session_id": "session-cache-err"}

        # Mock cache raising an exception
        cache_error_msg = "Redis connection failed"
        self.mock_cache_service.get.side_effect = Exception(cache_error_msg)

        response = self.component._handle_provide_required_input(params, meta)

        self.mock_cache_service.get.assert_called_once_with(f"a2a_follow_up:{follow_up_id}")
        self.mock_a2a_client.send_task.assert_not_called()

        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "Internal Error: Failed to retrieve follow-up state.")
        self.assertIn("Cache Error", response.error_info.error_message)
        self.assertIn(cache_error_msg, response.error_info.error_message)

    @patch("src.agents.a2a_client.a2a_client_agent_component.TextPart")
    @patch("src.agents.a2a_client.a2a_client_agent_component.TaskSendParams")
    @patch("src.agents.a2a_client.a2a_client_agent_component.A2AMessage")
    def test_handle_provide_input_follow_up_fails(self, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test handling when the follow-up A2A call results in FAILED."""
        follow_up_id = "follow-up-fail"
        original_task_id = "original-task-fail"
        user_response_text = "This input causes failure"
        params = {"follow_up_id": follow_up_id, "user_response": user_response_text}
        meta = {"session_id": "session-follow-up-fail"}

        self.mock_cache_service.get.return_value = original_task_id

        # Mock A2A response as FAILED
        mock_error_part = self._create_mock_part(part_type="text", text="Invalid input provided.")
        mock_response_task = self._create_mock_task_response(
            state="failed", message_parts=[mock_error_part], task_id=original_task_id
        )
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text=user_response_text)
        MockA2AMessage.return_value = MagicMock(role="user", parts=[MockTextPart.return_value])
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {"id": original_task_id, "sessionId": ANY, "message": ANY, "acceptedOutputModes": ANY}
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.component._handle_provide_required_input(params, meta)

        self.mock_cache_service.get.assert_called_once()
        self.mock_cache_service.delete.assert_called_once()
        self.mock_a2a_client.send_task.assert_called_once()

        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "A2A Task Failed (after follow-up): Invalid input provided.")
        self.assertEqual(response.error_info.error_message, "Invalid input provided.")

    @patch("src.agents.a2a_client.a2a_client_agent_component.TextPart")
    @patch("src.agents.a2a_client.a2a_client_agent_component.TaskSendParams")
    @patch("src.agents.a2a_client.a2a_client_agent_component.A2AMessage")
    @patch("src.agents.a2a_client.a2a_client_agent_component.uuid.uuid4") # Mock uuid for nested input required
    def test_handle_provide_input_follow_up_input_required_again(self, mock_uuid, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test handling when the follow-up A2A call results in another INPUT_REQUIRED."""
        follow_up_id = "follow-up-nested"
        original_task_id = "original-task-nested"
        user_response_text = "First response"
        params = {"follow_up_id": follow_up_id, "user_response": user_response_text}
        meta = {"session_id": "session-follow-up-nested"}
        new_follow_up_id = "new-follow-up-uuid"
        mock_uuid.return_value = new_follow_up_id

        self.mock_cache_service.get.return_value = original_task_id

        # Mock A2A response as INPUT_REQUIRED again
        mock_nested_question_part = self._create_mock_part(part_type="text", text="Need even more details.")
        mock_response_task = self._create_mock_task_response(
            state="input-required", message_parts=[mock_nested_question_part], task_id=original_task_id
        )
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text=user_response_text)
        MockA2AMessage.return_value = MagicMock(role="user", parts=[MockTextPart.return_value])
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {"id": original_task_id, "sessionId": ANY, "message": ANY, "acceptedOutputModes": ANY}
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.component._handle_provide_required_input(params, meta)

        self.mock_cache_service.get.assert_called_once()
        self.mock_cache_service.delete.assert_called_once() # Original ID deleted
        self.mock_a2a_client.send_task.assert_called_once()

        # Check new state was stored in cache
        self.mock_cache_service.set.assert_called_once_with(
            f"a2a_follow_up:{new_follow_up_id}",
            original_task_id,
            ttl=self.component.input_required_ttl
        )

        self.assertIsNone(response.error_info)
        self.assertEqual(response.message, "Need even more details.")
        self.assertIsNotNone(response.data)
        self.assertEqual(response.data.get('follow_up_id'), new_follow_up_id)

    @patch("src.agents.a2a_client.a2a_client_agent_component.TextPart")
    @patch("src.agents.a2a_client.a2a_client_agent_component.TaskSendParams")
    @patch("src.agents.a2a_client.a2a_client_agent_component.A2AMessage")
    def test_handle_provide_input_communication_error(self, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test handling communication errors during the follow-up call."""
        follow_up_id = "follow-up-comm-err"
        original_task_id = "original-task-comm-err"
        user_response_text = "Comm error follow up"
        params = {"follow_up_id": follow_up_id, "user_response": user_response_text}
        meta = {"session_id": "session-follow-up-comm-err"}

        self.mock_cache_service.get.return_value = original_task_id

        # Mock A2A client to raise error
        error_msg = "Service unavailable"
        self.mock_a2a_client.send_task.side_effect = ConnectionError(error_msg)

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text=user_response_text)
        MockA2AMessage.return_value = MagicMock(role="user", parts=[MockTextPart.return_value])
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {"id": original_task_id, "sessionId": ANY, "message": ANY, "acceptedOutputModes": ANY}
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.component._handle_provide_required_input(params, meta)

        self.mock_cache_service.get.assert_called_once()
        self.mock_cache_service.delete.assert_called_once()
        self.mock_a2a_client.send_task.assert_called_once()

        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "Failed to communicate with A2A agent during follow-up")
        self.assertIn("A2A Communication Error", response.error_info.error_message)
        self.assertIn(error_msg, response.error_info.error_message)


if __name__ == '__main__':
    unittest.main()
