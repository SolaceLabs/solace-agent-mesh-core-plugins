import unittest
from unittest.mock import patch, MagicMock, ANY
import uuid
import asyncio
import base64

# Adjust import paths as necessary
from src.agents.a2a_client.actions.a2a_client_action import (
    A2AClientAction,
    TaskSendParams,
    TextPart,
    FilePart,
    FileContent,
    Task,
    TaskState,
    SendTaskResponse, # Import SendTaskResponse
)
# Import Message directly from common_a2a.types
from src.common_a2a.types import (
    AgentSkill,
    Message, # Changed from A2AMessage
    TaskStatus,
    Artifact,
    DataPart, # Import necessary types
)
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo
from solace_ai_connector.common.log import log # Import the log object

# Mock the parent component and services
class MockFileService:
    def resolve_url(self, url, session_id=None, return_extra=False): # Add return_extra
        if url == "valid_url":
            mock_file_bytes = b"file_content"
            mock_file_meta = {
                "name": "resolved_file.txt",
                "mime_type": "text/plain",
                "size": len(mock_file_bytes),
                "url": url, # Include original URL for reference
            }
            # Return tuple if return_extra is True
            return (mock_file_bytes, mock_file_bytes, mock_file_meta) if return_extra else mock_file_bytes
        elif url == "invalid_url":
            raise FileNotFoundError(f"Mock File Not Found: {url}")
        elif url == "error_url":
            raise ValueError("Simulated resolution error")
        else:
            raise FileNotFoundError(f"Unknown URL: {url}")

    def upload_from_buffer(self, buffer, file_name, session_id, mime_type=None, data_source=None, **kwargs):
        # Simulate upload and return metadata including a URL
        log.debug("MockFileService: Uploading %s (%d bytes)", file_name, len(buffer))
        return {
            "url": f"fs://mock_files/{file_name}_{uuid.uuid4().hex[:6]}",
            "name": file_name,
            "mime_type": mime_type or "application/octet-stream",
            "size": len(buffer),
            "data_source": data_source or "mock_source",
            **kwargs # Include any extra metadata passed
        }

class MockA2AClientAgentComponent:
    def __init__(self, agent_name="mock_agent", cache_service=None, file_service=None, a2a_client=None):
        self.agent_name = agent_name
        self.get_config = MagicMock(return_value=300) # Mock config for TTL
        self.cache_service = cache_service or MagicMock()
        self.file_service = file_service if file_service is not None else MockFileService()
        self.a2a_client = a2a_client or MagicMock() # Provide a mock client
        self.input_required_ttl = self.get_config('input_required_ttl', 300) # Add TTL attribute

# <inst>
# Write tests for A2AClientAction.invoke
# Please don't mock everything and make the tests very brittle. I want a higher level set of tests
# that test the actual functionality of the invoke method, while still working with reasonable changes to the code.
# </inst>

class TestA2AClientActionInvokeCall(unittest.TestCase):

    def setUp(self):
        # Mock A2A AgentSkill
        self.mock_skill = MagicMock(spec=AgentSkill)
        self.mock_skill.id = "test_skill_id"
        self.mock_skill.name = "Test Skill Name"
        self.mock_skill.description = "This is a test skill description."

        # Mock the parent component with mocked services
        self.mock_a2a_client = MagicMock()
        self.mock_cache_service = MagicMock()
        self.mock_file_service = MagicMock(spec=MockFileService)
        # Configure the mock file service's methods
        self.mock_file_service.resolve_url.side_effect = MockFileService().resolve_url
        self.mock_file_service.upload_from_buffer.side_effect = MockFileService().upload_from_buffer

        self.mock_component = MockA2AClientAgentComponent(
            agent_name="test_sam_agent",
            cache_service=self.mock_cache_service,
            file_service=self.mock_file_service,
            a2a_client=self.mock_a2a_client
        )

        # Define generic parameters used by the action
        self.mock_params_def = [
            {"name": "prompt", "desc": "User prompt", "type": "string", "required": True},
            {"name": "files", "desc": "Optional files", "type": "list", "required": False},
        ]

        # Instantiate the action
        self.action = A2AClientAction(
            skill=self.mock_skill,
            component=self.mock_component, # type: ignore
            inferred_params=self.mock_params_def
        )

        # Common meta dictionary
        self.meta = {"session_id": "session123"}

        # Patch asyncio.run to directly return the result of the awaitable
        self.async_run_patcher = patch('src.agents.a2a_client.actions.a2a_client_action.asyncio.run')
        self.mock_async_run = self.async_run_patcher.start()
        # Make asyncio.run execute the coroutine passed to it
        async def run_awaitable(awaitable):
            return await awaitable
        self.mock_async_run.side_effect = run_awaitable

    def tearDown(self):
        self.async_run_patcher.stop()

    def _create_mock_task_response(self, state, message_parts=None, artifacts=None, task_id="task-123"):
        """Helper to create a mock SendTaskResponse containing a Task object."""
        mock_task = MagicMock(spec=Task)
        mock_task.id = task_id
        mock_task.status = MagicMock(spec=TaskStatus)
        mock_task.status.state = state
        # Use getattr to safely access parts, default to empty list
        mock_task.status.message = MagicMock(spec=Message, parts=getattr(message_parts, 'parts', [])) if message_parts else None # Changed spec
        mock_task.artifacts = artifacts or []
        # Helper method to mimic Task.get_state()
        mock_task.get_state = MagicMock(return_value=state)

        # Wrap the Task in a mock SendTaskResponse
        mock_response = MagicMock(spec=SendTaskResponse)
        mock_response.result = mock_task
        mock_response.error = None # No JSON-RPC error
        return mock_response

    def _create_mock_part(self, part_type, **kwargs):
        """Helper to create a mock Part object (TextPart, FilePart, DataPart)."""
        if part_type == "text":
            return TextPart(text=kwargs.get("text", ""))
        elif part_type == "file":
            import base64
            file_bytes = kwargs.get("bytes", b"")
            encoded_bytes = base64.b64encode(file_bytes).decode("utf-8")
            file_content = FileContent(
                bytes=encoded_bytes,
                name=kwargs.get("name", "file.dat"),
                mimeType=kwargs.get("mimeType", "application/octet-stream")
            )
            return FilePart(file=file_content)
        elif part_type == "data":
            return DataPart(data=kwargs.get("data", {}))
        else:
            raise ValueError(f"Unknown part type: {part_type}")

    # --- Test Cases ---

    async def test_invoke_completed_text_only(self):
        """Test invoke with COMPLETED state and only text response."""
        params = {"prompt": "Hello"}
        response_text = "Hello back!"
        mock_response_part = self._create_mock_part(part_type="text", text=response_text)
        mock_a2a_response = self._create_mock_task_response(
            state=TaskState.COMPLETED,
            message_parts=[mock_response_part]
        )
        self.mock_a2a_client.send_task.return_value = mock_a2a_response

        # Call invoke
        response = self.action.invoke(params, self.meta)

        # Assertions
        self.mock_a2a_client.send_task.assert_called_once()
        sent_params_dump = self.mock_a2a_client.send_task.call_args[0][0]
        self.assertEqual(sent_params_dump['sessionId'], self.meta['session_id'])
        self.assertEqual(sent_params_dump['message']['parts'][0]['text'], params['prompt'])

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNone(response.error_info)
        self.assertEqual(response.message, response_text)
        self.assertIsNone(response.files)
        self.assertNotIn('data', response.to_dict()) # Check data field isn't present

    async def test_invoke_completed_file_only(self):
        """Test invoke with COMPLETED state and only file response."""
        params = {"prompt": "Generate file"}
        file_name = "output.png"
        file_bytes = b"\x89PNG\r\n\x1a\n\x00" # Minimal PNG header
        mock_response_part = self._create_mock_part(part_type="file", bytes=file_bytes, name=file_name, mimeType="image/png")
        mock_a2a_response = self._create_mock_task_response(
            state=TaskState.COMPLETED,
            message_parts=[mock_response_part] # File in message part
        )
        self.mock_a2a_client.send_task.return_value = mock_a2a_response

        # Call invoke
        response = self.action.invoke(params, self.meta)

        # Assertions
        self.mock_a2a_client.send_task.assert_called_once()
        self.mock_file_service.upload_from_buffer.assert_called_once_with(
            buffer=file_bytes,
            file_name=file_name,
            session_id=self.meta['session_id'],
            mime_type="image/png",
            data_source=f"{self.mock_component.agent_name}/{self.action.name}"
        )

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNone(response.error_info)
        self.assertEqual(response.message, "Task completed successfully.") # Default message when no text parts
        self.assertIsInstance(response.files, list)
        self.assertEqual(len(response.files), 1)
        self.assertEqual(response.files[0]['name'], file_name)
        self.assertTrue(response.files[0]['url'].startswith("fs://mock_files/"))

    async def test_invoke_completed_data_only(self):
        """Test invoke with COMPLETED state and only data response."""
        params = {"prompt": "Get data"}
        response_data = {"key": "value", "count": 42}
        mock_response_part = self._create_mock_part(part_type="data", data=response_data)
        mock_a2a_response = self._create_mock_task_response(
            state=TaskState.COMPLETED,
            message_parts=[mock_response_part] # Data in message part
        )
        self.mock_a2a_client.send_task.return_value = mock_a2a_response

        # Call invoke
        response = self.action.invoke(params, self.meta)

        # Assertions
        self.mock_a2a_client.send_task.assert_called_once()
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNone(response.error_info)
        # Check that the data is included in the message string
        self.assertTrue(response.message.startswith("Task completed successfully."))
        self.assertIn("--- Data ---", response.message)
        self.assertIn('"key": "value"', response.message)
        self.assertIn('"count": 42', response.message)
        self.assertIsNone(response.files)

    async def test_invoke_completed_mixed_response(self):
        """Test invoke with COMPLETED state and mixed text, file, data response."""
        params = {"prompt": "Complex request"}
        text_part1 = self._create_mock_part(part_type="text", text="Here is the result.")
        file_part1 = self._create_mock_part(part_type="file", bytes=b"abc", name="file1.txt", mimeType="text/plain")
        data_part1 = self._create_mock_part(part_type="data", data={"status": "ok"})
        text_part2 = self._create_mock_part(part_type="text", text="And some details.")
        file_part2 = self._create_mock_part(part_type="file", bytes=b"def", name="file2.log", mimeType="text/plain")
        data_part2 = self._create_mock_part(part_type="data", data={"code": 200})

        # Distribute parts between message and artifact
        mock_artifact = MagicMock(spec=Artifact)
        mock_artifact.parts = [text_part2, file_part2, data_part2]

        mock_a2a_response = self._create_mock_task_response(
            state=TaskState.COMPLETED,
            message_parts=[text_part1, file_part1, data_part1],
            artifacts=[mock_artifact]
        )
        self.mock_a2a_client.send_task.return_value = mock_a2a_response

        # Call invoke
        response = self.action.invoke(params, self.meta)

        # Assertions
        self.mock_a2a_client.send_task.assert_called_once()
        self.assertEqual(self.mock_file_service.upload_from_buffer.call_count, 2)

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNone(response.error_info)
        # Check message contains text from both sources and data
        self.assertIn("Here is the result.", response.message)
        self.assertIn("--- Artifact ---", response.message)
        self.assertIn("And some details.", response.message)
        self.assertIn("--- Data ---", response.message)
        self.assertIn('"status": "ok"', response.message)
        self.assertIn('"code": 200', response.message)
        # Check files
        self.assertIsInstance(response.files, list)
        self.assertEqual(len(response.files), 2)
        self.assertTrue(any(f['name'] == 'file1.txt' for f in response.files))
        self.assertTrue(any(f['name'] == 'file2.log' for f in response.files))

    async def test_invoke_failed_state(self):
        """Test invoke with FAILED state response."""
        params = {"prompt": "This will fail"}
        error_text = "Invalid operation requested."
        mock_error_part = self._create_mock_part(part_type="text", text=error_text)
        mock_a2a_response = self._create_mock_task_response(
            state=TaskState.FAILED,
            message_parts=[mock_error_part]
        )
        self.mock_a2a_client.send_task.return_value = mock_a2a_response

        # Call invoke
        response = self.action.invoke(params, self.meta)

        # Assertions
        self.mock_a2a_client.send_task.assert_called_once()
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info)
        self.assertIn(f"A2A Task '{self.action.name}' Failed", response.message)
        self.assertIn(error_text, response.message)
        self.assertEqual(response.error_info.error_message, error_text)

    async def test_invoke_input_required_state(self):
        """Test invoke with INPUT_REQUIRED state response."""
        params = {"prompt": "Need more info"}
        question_text = "What color do you want?"
        mock_question_part = self._create_mock_part(part_type="text", text=question_text)
        original_task_id = "task-input-required"
        mock_a2a_response = self._create_mock_task_response(
            state=TaskState.INPUT_REQUIRED,
            message_parts=[mock_question_part],
            task_id=original_task_id
        )
        self.mock_a2a_client.send_task.return_value = mock_a2a_response

        # Mock uuid for predictable follow-up ID
        generated_uuid = "generated-follow-up-uuid"
        with patch('src.agents.a2a_client.actions.a2a_client_action.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value = generated_uuid

            # Call invoke
            response = self.action.invoke(params, self.meta)

        # Assertions
        self.mock_a2a_client.send_task.assert_called_once()
        self.mock_cache_service.add_data.assert_called_once_with(
            key=f"a2a_follow_up:{generated_uuid}",
            value=original_task_id,
            expiry=self.mock_component.input_required_ttl
        )

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNone(response.error_info) # INPUT_REQUIRED is not an error state for the action itself
        self.assertIn(question_text, response.message)
        self.assertIn("provide_required_input", response.message)
        self.assertIn(f"`{generated_uuid}`", response.message)
        # Check data attribute doesn't exist or is None
        self.assertFalse(hasattr(response, 'data') or response.to_dict().get('data') is not None)


    async def test_invoke_input_required_no_cache_service(self):
        """Test invoke fails gracefully for INPUT_REQUIRED if cache service is missing."""
        # Reconfigure component without cache service
        self.mock_component.cache_service = None
        params = {"prompt": "Need more info, no cache"}
        question_text = "What color?"
        mock_question_part = self._create_mock_part(part_type="text", text=question_text)
        mock_a2a_response = self._create_mock_task_response(
            state=TaskState.INPUT_REQUIRED,
            message_parts=[mock_question_part]
        )
        self.mock_a2a_client.send_task.return_value = mock_a2a_response

        # Call invoke
        response = self.action.invoke(params, self.meta)

        # Assertions
        self.mock_a2a_client.send_task.assert_called_once()
        self.mock_cache_service.add_data.assert_not_called() # Cache method not called

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info)
        self.assertIn("Cannot handle required input state without CacheService", response.message)
        self.assertEqual(response.error_info.error_message, "Cache Service Missing")

    async def test_invoke_communication_error(self):
        """Test invoke handles communication errors during send_task."""
        params = {"prompt": "Network error test"}
        error_message = "Connection refused"
        self.mock_a2a_client.send_task.side_effect = ConnectionError(error_message)

        # Call invoke
        response = self.action.invoke(params, self.meta)

        # Assertions
        self.mock_a2a_client.send_task.assert_called_once()
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info)
        self.assertIn("Failed to execute action", response.message)
        self.assertIn("communication or processing error", response.message)
        self.assertIn("A2A Communication/Processing Error", response.error_info.error_message)
        self.assertIn(error_message, response.error_info.error_message)

    async def test_invoke_file_resolution_error(self):
        """Test invoke handles errors during file URL resolution."""
        params = {"prompt": "Process bad file", "files": ["error_url"]}

        # Call invoke - FileService mock will raise ValueError
        response = self.action.invoke(params, self.meta)

        # Assertions
        self.mock_file_service.resolve_url.assert_called_once_with(
            "error_url", session_id=self.meta['session_id'], return_extra=True
        )
        self.mock_a2a_client.send_task.assert_not_called() # Should fail before sending

        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info)
        self.assertIn("Error resolving file URL", response.message) # Check message
        self.assertIn("File Processing Error", response.error_info.error_message)
        self.assertIn("Simulated resolution error", response.error_info.error_message)

    async def test_invoke_file_upload_error(self):
        """Test invoke handles errors during file upload in response processing."""
        params = {"prompt": "Generate file, upload fails"}
        file_name = "output_fails.dat"
        file_bytes = b"data_that_fails_upload"
        mock_response_part = self._create_mock_part(part_type="file", bytes=file_bytes, name=file_name)
        mock_a2a_response = self._create_mock_task_response(
            state=TaskState.COMPLETED,
            message_parts=[mock_response_part]
        )
        self.mock_a2a_client.send_task.return_value = mock_a2a_response

        # Make file service upload fail
        upload_error_msg = "S3 bucket not found"
        self.mock_file_service.upload_from_buffer.side_effect = Exception(upload_error_msg)

        # Call invoke
        response = self.action.invoke(params, self.meta)

        # Assertions
        self.mock_a2a_client.send_task.assert_called_once()
        self.mock_file_service.upload_from_buffer.assert_called_once() # Upload was attempted

        # Even though upload failed, the overall task completed from A2A perspective.
        # The error is logged, but the action returns success with whatever else it processed.
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNone(response.error_info)
        self.assertEqual(response.message, "Task completed successfully.") # Default message
        self.assertIsNone(response.files) # File list is empty because upload failed

if __name__ == '__main__':
    unittest.main()
