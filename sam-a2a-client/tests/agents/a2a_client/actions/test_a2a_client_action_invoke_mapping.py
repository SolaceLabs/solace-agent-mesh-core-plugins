import unittest
from unittest.mock import MagicMock, patch, ANY
import uuid

# Adjust import paths as necessary
from src.agents.a2a_client.actions.a2a_client_action import A2AClientAction, AgentSkill
# Mock A2A types needed for assertions
from src.agents.a2a_client.actions.a2a_client_action import TaskSendParams, A2AMessage, TextPart, FilePart, FileContent
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo

# Mock the parent component and services
class MockFileService:
    def resolve_url(self, url, session_id=None):
        if url == "valid_url":
            mock_file = MagicMock()
            mock_file.bytes = b"file_content"
            mock_file.name = "resolved_file.txt"
            mock_file.mime_type = "text/plain"
            return mock_file
        elif url == "invalid_url":
            return None # Simulate resolution failure
        elif url == "error_url":
            raise ValueError("Simulated resolution error")
        else:
            raise FileNotFoundError(f"Unknown URL: {url}")

class MockA2AClientAgentComponent:
    def __init__(self, agent_name="mock_agent", cache_service=None, file_service=None, a2a_client=None):
        self.agent_name = agent_name
        self.get_config = MagicMock()
        self.cache_service = cache_service or MagicMock()
        self.file_service = file_service or MockFileService()
        self.a2a_client = a2a_client or MagicMock() # Provide a mock client

class TestA2AClientActionInvokeMapping(unittest.TestCase):

    def setUp(self):
        # Mock A2A AgentSkill
        self.mock_skill = MagicMock(spec=AgentSkill)
        self.mock_skill.id = "test_skill_id"
        self.mock_skill.name = "Test Skill Name"
        self.mock_skill.description = "This is a test skill description."

        # Mock the parent component
        self.mock_component = MockA2AClientAgentComponent(agent_name="test_sam_agent")

        # Mock inferred parameters
        self.mock_params_def = [
            {"name": "prompt", "desc": "User prompt", "type": "string", "required": True},
            {"name": "files", "desc": "List of file URLs", "type": "list", "required": False}
        ]

        # Instantiate the action
        with patch('src.agents.a2a_client.actions.a2a_client_action.Action.__init__'):
            self.action = A2AClientAction(
                skill=self.mock_skill,
                component=self.mock_component, # type: ignore
                inferred_params=self.mock_params_def
            )

    def test_invoke_mapping_text_only(self):
        """Test mapping with only text prompt."""
        params = {"prompt": "Hello A2A"}
        meta = {"session_id": "session123"}

        # Call invoke (we only care about the mapping part for now)
        response = self.action.invoke(params, meta)

        # Check the stored task_params (added for testing)
        self.assertTrue(hasattr(self.action, '_last_constructed_task_params'))
        task_params: TaskSendParams = self.action._last_constructed_task_params

        self.assertIsInstance(task_params, TaskSendParams)
        self.assertEqual(task_params.sessionId, "session123")
        self.assertIsInstance(task_params.id, str)
        self.assertIsInstance(task_params.message, A2AMessage)
        self.assertEqual(task_params.message.role, "user")
        self.assertEqual(len(task_params.message.parts), 1)
        self.assertIsInstance(task_params.message.parts[0], TextPart)
        self.assertEqual(task_params.message.parts[0].text, "Hello A2A")
        self.assertEqual(task_params.acceptedOutputModes, ["text", "text/plain", "image/*", "application/json"])

        # Check the temporary response indicates mapping occurred but call is pending
        self.assertFalse(response.success)
        self.assertIn("mapped request", response.message)
        self.assertEqual(response.error_info.code, "Not Implemented")

    def test_invoke_mapping_text_and_valid_file(self):
        """Test mapping with text and a valid file URL."""
        params = {"prompt": "Process this file", "files": ["valid_url"]}
        meta = {"session_id": "session456"}

        response = self.action.invoke(params, meta)
        task_params: TaskSendParams = self.action._last_constructed_task_params

        self.assertEqual(task_params.sessionId, "session456")
        self.assertEqual(len(task_params.message.parts), 2) # Text + File
        self.assertIsInstance(task_params.message.parts[0], TextPart)
        self.assertEqual(task_params.message.parts[0].text, "Process this file")
        self.assertIsInstance(task_params.message.parts[1], FilePart)
        self.assertIsInstance(task_params.message.parts[1].file, FileContent)
        self.assertEqual(task_params.message.parts[1].file.bytes, b"file_content")
        self.assertEqual(task_params.message.parts[1].file.name, "resolved_file.txt")
        self.assertEqual(task_params.message.parts[1].file.mimeType, "text/plain")

        self.assertFalse(response.success) # Still pending call

    def test_invoke_mapping_text_and_multiple_files(self):
        """Test mapping with text and multiple file URLs (valid, invalid, error)."""
        params = {"prompt": "Multiple files", "files": ["valid_url", "invalid_url", "error_url", 123]} # Include non-string
        meta = {"session_id": "session789"}

        with patch('src.agents.a2a_client.actions.a2a_client_action.logger.warning') as mock_log_warn, \
             patch('src.agents.a2a_client.actions.a2a_client_action.logger.error') as mock_log_err:
            response = self.action.invoke(params, meta)

        task_params: TaskSendParams = self.action._last_constructed_task_params

        self.assertEqual(task_params.sessionId, "session789")
        # Should have TextPart and ONE valid FilePart
        self.assertEqual(len(task_params.message.parts), 2)
        self.assertIsInstance(task_params.message.parts[0], TextPart)
        self.assertEqual(task_params.message.parts[0].text, "Multiple files")
        self.assertIsInstance(task_params.message.parts[1], FilePart)
        self.assertEqual(task_params.message.parts[1].file.name, "resolved_file.txt")

        # Check logs for skipped/failed files
        mock_log_warn.assert_any_call("Skipping non-string item in 'files' list: 123")
        mock_log_err.assert_any_call("Failed to resolve file URL 'invalid_url' or resolved object is invalid.")
        mock_log_err.assert_any_call("Error resolving file URL 'error_url' for action 'test_skill_id': Simulated resolution error", exc_info=True)

        self.assertFalse(response.success) # Still pending call

    def test_invoke_mapping_missing_prompt(self):
        """Test mapping fails if required 'prompt' parameter is missing."""
        params = {"files": ["valid_url"]} # No prompt
        meta = {"session_id": "session_no_prompt"}

        response = self.action.invoke(params, meta)

        self.assertFalse(response.success)
        self.assertEqual(response.message, "Missing required 'prompt' parameter.")
        self.assertEqual(response.error_info.code, "Missing Parameter")
        self.assertFalse(hasattr(self.action, '_last_constructed_task_params')) # Should fail before construction

    def test_invoke_mapping_no_session_id(self):
        """Test mapping generates a session ID if none is provided in meta."""
        params = {"prompt": "Generate session"}
        meta = {} # No session_id

        with patch('src.agents.a2a_client.actions.a2a_client_action.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value = uuid.UUID('12345678-1234-5678-1234-567812345678')
            response = self.action.invoke(params, meta)

        task_params: TaskSendParams = self.action._last_constructed_task_params
        self.assertEqual(task_params.sessionId, "12345678-1234-5678-1234-567812345678")
        self.assertFalse(response.success) # Still pending call

    def test_invoke_mapping_no_a2a_client(self):
        """Test mapping fails if a2a_client is not initialized."""
        self.mock_component.a2a_client = None # Simulate client not ready
        params = {"prompt": "Client missing"}
        meta = {"session_id": "session_no_client"}

        response = self.action.invoke(params, meta)

        self.assertFalse(response.success)
        self.assertEqual(response.message, "Internal Error: A2A Client not available.")
        self.assertEqual(response.error_info.code, "A2A Client Missing")

    def test_invoke_mapping_no_file_service(self):
        """Test mapping fails if file_service is not available."""
        self.mock_component.file_service = None # Simulate service missing
        params = {"prompt": "File service missing"}
        meta = {"session_id": "session_no_fs"}

        response = self.action.invoke(params, meta)

        self.assertFalse(response.success)
        self.assertEqual(response.message, "Internal Error: File Service not available.")
        self.assertEqual(response.error_info.code, "File Service Missing")


if __name__ == '__main__':
    unittest.main()
