import unittest
from unittest.mock import patch, MagicMock, ANY, call
import uuid
import asyncio
import base64
import json

# Adjust import paths as necessary
from src.agents.a2a_client.actions.a2a_client_action import (
    A2AClientAction,
    AgentSkill,
    TaskSendParams,
    A2AMessage,
    TextPart,
    FilePart,
    FileContent,
    Task,
    TaskState,
    SendTaskResponse,
)
from src.common_a2a.types import TaskStatus, Artifact, DataPart
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo
from solace_ai_connector.common.log import log

# Mock the parent component and services (similar to test_a2a_client_action_invoke_call.py)
class MockFileService:
    def resolve_url(self, url, session_id=None, return_extra=False):
        log.debug("MockFileService.resolve_url called with: %s", url)
        if url == "fs://valid/file1.txt":
            mock_bytes = b"content1"
            mock_meta = {
                "name": "file1.txt",
                "mime_type": "text/plain",
                "size": len(mock_bytes),
                "url": url,
            }
            return (mock_bytes, mock_bytes, mock_meta) if return_extra else mock_bytes
        elif url == "fs://valid/image.png":
            mock_bytes = b"\x89PNG..."
            mock_meta = {
                "name": "image.png",
                "mime_type": "image/png",
                "size": len(mock_bytes),
                "url": url,
            }
            return (mock_bytes, mock_bytes, mock_meta) if return_extra else mock_bytes
        elif url == "fs://invalid/not_found.dat":
            raise FileNotFoundError(f"Mock File Not Found: {url}")
        elif url == "fs://error/resolve_error.log":
            raise ValueError("Simulated resolution error")
        else:
            raise FileNotFoundError(f"Unknown URL: {url}")

    def upload_from_buffer(self, buffer, file_name, session_id, mime_type=None, data_source=None, **kwargs):
        # Only needed for response processing, basic mock is fine here
        return {"url": f"fs://uploaded/{file_name}"}

class MockA2AClientAgentComponent:
    def __init__(self, agent_name="mock_agent", cache_service=None, file_service=None, a2a_client=None):
        self.agent_name = agent_name
        self.get_config = MagicMock(return_value=300)
        self.cache_service = cache_service or MagicMock()
        self.file_service = file_service if file_service is not None else MockFileService()
        self.a2a_client = a2a_client or MagicMock()
        self.input_required_ttl = self.get_config('input_required_ttl', 300)

# <inst>
# Write tests for A2AClientAction invoke mapping
# Please don't mock everything and make the tests very brittle. I want a higher level set of tests
# that test the actual functionality of the invoke method, while still working with reasonable changes to the code.
# </inst>

class TestA2AClientActionInvokeMapping(unittest.TestCase):

    def setUp(self):
        # Mock A2A AgentSkill
        self.mock_skill = MagicMock(spec=AgentSkill)
        self.mock_skill.id = "mapping_skill"
        self.mock_skill.name = "Mapping Skill"
        self.mock_skill.description = "Tests parameter mapping."

        # Mock the parent component with mocked services
        self.mock_a2a_client = MagicMock()
        self.mock_cache_service = MagicMock()
        # Use a MagicMock for FileService but configure its methods
        self.mock_file_service = MagicMock(spec=MockFileService)
        self.mock_file_service.resolve_url.side_effect = MockFileService().resolve_url
        self.mock_file_service.upload_from_buffer.side_effect = MockFileService().upload_from_buffer

        self.mock_component = MockA2AClientAgentComponent(
            agent_name="mapping_agent",
            cache_service=self.mock_cache_service,
            file_service=self.mock_file_service,
            a2a_client=self.mock_a2a_client
        )

        # Define generic parameters used by the action
        self.mock_params_def = [
            {"name": "prompt", "desc": "User prompt", "type": "string", "required": True},
            {"name": "files", "desc": "Optional files (JSON list of URLs)", "type": "string", "required": False},
        ]

        # Instantiate the action
        self.action = A2AClientAction(
            skill=self.mock_skill,
            component=self.mock_component, # type: ignore
            inferred_params=self.mock_params_def
        )

        # Common meta dictionary
        self.meta = {"session_id": "map_session_123"}

        # Patch asyncio.run
        self.async_run_patcher = patch('src.agents.a2a_client.actions.a2a_client_action.asyncio.run')
        self.mock_async_run = self.async_run_patcher.start()
        async def run_awaitable(awaitable):
            # Simulate a successful A2A response for mapping tests
            mock_response = MagicMock(spec=SendTaskResponse)
            mock_task = MagicMock(spec=Task)
            mock_task.status = MagicMock(spec=TaskStatus, state=TaskState.COMPLETED)
            mock_task.get_state = MagicMock(return_value=TaskState.COMPLETED)
            mock_response.result = mock_task
            mock_response.error = None
            return mock_response
        self.mock_async_run.side_effect = run_awaitable

        # Patch A2A types constructors to verify calls
        self.text_part_patcher = patch('src.agents.a2a_client.actions.a2a_client_action.TextPart', wraps=TextPart)
        self.file_part_patcher = patch('src.agents.a2a_client.actions.a2a_client_action.FilePart', wraps=FilePart)
        self.file_content_patcher = patch('src.agents.a2a_client.actions.a2a_client_action.FileContent', wraps=FileContent)
        self.a2a_message_patcher = patch('src.agents.a2a_client.actions.a2a_client_action.A2AMessage', wraps=A2AMessage)
        self.task_send_params_patcher = patch('src.agents.a2a_client.actions.a2a_client_action.TaskSendParams', wraps=TaskSendParams)

        self.MockTextPart = self.text_part_patcher.start()
        self.MockFilePart = self.file_part_patcher.start()
        self.MockFileContent = self.file_content_patcher.start()
        self.MockA2AMessage = self.a2a_message_patcher.start()
        self.MockTaskSendParams = self.task_send_params_patcher.start()

    def tearDown(self):
        self.async_run_patcher.stop()
        self.text_part_patcher.stop()
        self.file_part_patcher.stop()
        self.file_content_patcher.stop()
        self.a2a_message_patcher.stop()
        self.task_send_params_patcher.stop()

    def test_invoke_mapping_text_only(self):
        """Test mapping only a text prompt."""
        params = {"prompt": "Simple text request"}
        self.action.invoke(params, self.meta)

        # Verify TaskSendParams construction
        self.MockTaskSendParams.assert_called_once()
        call_args, call_kwargs = self.MockTaskSendParams.call_args
        self.assertEqual(call_kwargs['sessionId'], self.meta['session_id'])
        self.assertTrue(call_kwargs['id'].startswith('a2a_task_')) # Check format

        # Verify A2AMessage construction
        self.MockA2AMessage.assert_called_once_with(role='user', parts=ANY)
        message_args, message_kwargs = self.MockA2AMessage.call_args
        sent_parts = message_kwargs['parts']

        # Verify Parts construction
        self.assertEqual(len(sent_parts), 1)
        self.MockTextPart.assert_called_once_with(text=params['prompt'])
        self.assertIsInstance(sent_parts[0], TextPart)
        self.assertEqual(sent_parts[0].text, params['prompt'])
        self.MockFilePart.assert_not_called()

        # Verify FileService was not called
        self.mock_file_service.resolve_url.assert_not_called()

        # Verify A2AClient call
        self.mock_a2a_client.send_task.assert_called_once()
        sent_payload = self.mock_a2a_client.send_task.call_args[0][0]
        self.assertEqual(sent_payload['message']['parts'][0]['text'], params['prompt'])

    def test_invoke_mapping_text_and_one_file(self):
        """Test mapping text and a single valid file URL."""
        file_url = "fs://valid/file1.txt"
        params = {"prompt": "Process this file", "files": json.dumps([file_url])} # JSON list string
        self.action.invoke(params, self.meta)

        # Verify FileService call
        self.mock_file_service.resolve_url.assert_called_once_with(
            file_url, session_id=self.meta['session_id'], return_extra=True
        )

        # Verify Parts construction
        self.MockTextPart.assert_called_once_with(text=params['prompt'])
        self.MockFileContent.assert_called_once()
        file_content_args, file_content_kwargs = self.MockFileContent.call_args
        self.assertEqual(file_content_kwargs['name'], 'file1.txt')
        self.assertEqual(file_content_kwargs['mimeType'], 'text/plain')
        # Check bytes are base64 encoded
        expected_b64 = base64.b64encode(b"content1").decode('utf-8')
        self.assertEqual(file_content_kwargs['bytes'], expected_b64)

        self.MockFilePart.assert_called_once()
        file_part_args, file_part_kwargs = self.MockFilePart.call_args
        self.assertIsInstance(file_part_kwargs['file'], FileContent)

        # Verify A2AMessage parts
        self.MockA2AMessage.assert_called_once()
        message_args, message_kwargs = self.MockA2AMessage.call_args
        sent_parts = message_kwargs['parts']
        self.assertEqual(len(sent_parts), 2)
        self.assertIsInstance(sent_parts[0], TextPart)
        self.assertIsInstance(sent_parts[1], FilePart)
        self.assertEqual(sent_parts[1].file.name, 'file1.txt')

        # Verify A2AClient call payload
        self.mock_a2a_client.send_task.assert_called_once()
        sent_payload = self.mock_a2a_client.send_task.call_args[0][0]
        self.assertEqual(len(sent_payload['message']['parts']), 2)
        self.assertEqual(sent_payload['message']['parts'][1]['type'], 'file')
        self.assertEqual(sent_payload['message']['parts'][1]['file']['name'], 'file1.txt')
        self.assertEqual(sent_payload['message']['parts'][1]['file']['bytes'], expected_b64)

    def test_invoke_mapping_text_and_multiple_files(self):
        """Test mapping text and multiple valid file URLs."""
        file_url1 = "fs://valid/file1.txt"
        file_url2 = "fs://valid/image.png"
        params = {"prompt": "Process these files", "files": json.dumps([file_url1, file_url2])}
        self.action.invoke(params, self.meta)

        # Verify FileService calls
        self.assertEqual(self.mock_file_service.resolve_url.call_count, 2)
        self.mock_file_service.resolve_url.assert_has_calls([
            call(file_url1, session_id=self.meta['session_id'], return_extra=True),
            call(file_url2, session_id=self.meta['session_id'], return_extra=True),
        ], any_order=True) # Order might vary

        # Verify Parts construction
        self.MockTextPart.assert_called_once_with(text=params['prompt'])
        self.assertEqual(self.MockFileContent.call_count, 2)
        self.assertEqual(self.MockFilePart.call_count, 2)

        # Verify A2AMessage parts
        self.MockA2AMessage.assert_called_once()
        message_args, message_kwargs = self.MockA2AMessage.call_args
        sent_parts = message_kwargs['parts']
        self.assertEqual(len(sent_parts), 3) # 1 Text + 2 File
        self.assertIsInstance(sent_parts[0], TextPart)
        self.assertIsInstance(sent_parts[1], FilePart)
        self.assertIsInstance(sent_parts[2], FilePart)
        # Check names to ensure both files were processed
        file_names = {part.file.name for part in sent_parts if isinstance(part, FilePart)}
        self.assertSetEqual(file_names, {'file1.txt', 'image.png'})

        # Verify A2AClient call payload
        self.mock_a2a_client.send_task.assert_called_once()
        sent_payload = self.mock_a2a_client.send_task.call_args[0][0]
        self.assertEqual(len(sent_payload['message']['parts']), 3)

    def test_invoke_mapping_file_resolve_error(self):
        """Test mapping skips file if FileService.resolve_url raises an error."""
        file_url_valid = "fs://valid/file1.txt"
        file_url_error = "fs://error/resolve_error.log"
        params = {"prompt": "Process with error", "files": json.dumps([file_url_valid, file_url_error])}
        self.action.invoke(params, self.meta)

        # Verify FileService calls (both attempted)
        self.assertEqual(self.mock_file_service.resolve_url.call_count, 2)
        self.mock_file_service.resolve_url.assert_has_calls([
            call(file_url_valid, session_id=self.meta['session_id'], return_extra=True),
            call(file_url_error, session_id=self.meta['session_id'], return_extra=True),
        ], any_order=True)

        # Verify Parts construction (only TextPart and one FilePart created)
        self.MockTextPart.assert_called_once_with(text=params['prompt'])
        self.MockFileContent.assert_called_once() # Only for the valid file
        self.MockFilePart.assert_called_once()   # Only for the valid file

        # Verify A2AMessage parts (only Text + 1 File)
        self.MockA2AMessage.assert_called_once()
        message_args, message_kwargs = self.MockA2AMessage.call_args
        sent_parts = message_kwargs['parts']
        self.assertEqual(len(sent_parts), 2)
        self.assertIsInstance(sent_parts[0], TextPart)
        self.assertIsInstance(sent_parts[1], FilePart)
        self.assertEqual(sent_parts[1].file.name, 'file1.txt') # Check it's the valid one

        # Verify A2AClient call (should still proceed with valid parts)
        self.mock_a2a_client.send_task.assert_called_once()
        sent_payload = self.mock_a2a_client.send_task.call_args[0][0]
        self.assertEqual(len(sent_payload['message']['parts']), 2)

    def test_invoke_mapping_file_not_found(self):
        """Test mapping skips file if FileService.resolve_url raises FileNotFoundError."""
        file_url_valid = "fs://valid/file1.txt"
        file_url_not_found = "fs://invalid/not_found.dat"
        params = {"prompt": "Process with missing", "files": json.dumps([file_url_valid, file_url_not_found])}
        self.action.invoke(params, self.meta)

        # Verify FileService calls (both attempted)
        self.assertEqual(self.mock_file_service.resolve_url.call_count, 2)

        # Verify Parts construction (only TextPart and one FilePart created)
        self.MockTextPart.assert_called_once_with(text=params['prompt'])
        self.MockFileContent.assert_called_once() # Only for the valid file
        self.MockFilePart.assert_called_once()   # Only for the valid file

        # Verify A2AMessage parts (only Text + 1 File)
        self.MockA2AMessage.assert_called_once()
        message_args, message_kwargs = self.MockA2AMessage.call_args
        sent_parts = message_kwargs['parts']
        self.assertEqual(len(sent_parts), 2)
        self.assertEqual(sent_parts[1].file.name, 'file1.txt')

        # Verify A2AClient call (should still proceed)
        self.mock_a2a_client.send_task.assert_called_once()
        sent_payload = self.mock_a2a_client.send_task.call_args[0][0]
        self.assertEqual(len(sent_payload['message']['parts']), 2)

    def test_invoke_mapping_invalid_files_param_format(self):
        """Test mapping handles 'files' param not being a valid JSON list string."""
        params = {"prompt": "Invalid files param", "files": "not_a_json_list_or_url"}
        response = self.action.invoke(params, self.meta)

        # Verify FileService was not called
        self.mock_file_service.resolve_url.assert_not_called()

        # Verify A2AClient was not called
        self.mock_a2a_client.send_task.assert_not_called()

        # Verify error response
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "Invalid file URL format.")
        self.assertEqual(response.error_info.error_message, "Invalid File URL")

    def test_invoke_mapping_missing_prompt(self):
        """Test mapping fails if required 'prompt' parameter is missing."""
        params = {"files": json.dumps(["fs://valid/file1.txt"])} # Missing prompt
        response = self.action.invoke(params, self.meta)

        # Verify services not called
        self.mock_file_service.resolve_url.assert_not_called()
        self.mock_a2a_client.send_task.assert_not_called()

        # Verify error response
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "Missing required 'prompt' parameter.")
        self.assertEqual(response.error_info.error_message, "Missing Parameter")

    def test_invoke_mapping_no_session_id(self):
        """Test mapping generates a session ID if none is in meta."""
        params = {"prompt": "No session ID test"}
        meta_no_session = {} # Empty meta
        self.action.invoke(params, meta_no_session)

        # Verify TaskSendParams construction used a generated session ID
        self.MockTaskSendParams.assert_called_once()
        call_args, call_kwargs = self.MockTaskSendParams.call_args
        self.assertIsNotNone(call_kwargs['sessionId'])
        self.assertIsInstance(call_kwargs['sessionId'], str)
        # Check it looks like a UUID hex string (32 chars)
        self.assertEqual(len(call_kwargs['sessionId']), 32)

        # Verify A2AClient call used the generated session ID
        self.mock_a2a_client.send_task.assert_called_once()
        sent_payload = self.mock_a2a_client.send_task.call_args[0][0]
        self.assertEqual(sent_payload['sessionId'], call_kwargs['sessionId'])

if __name__ == '__main__':
    unittest.main()
