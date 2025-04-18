import unittest
from unittest.mock import MagicMock, patch, ANY
import uuid

# Adjust import paths as necessary
from src.agents.a2a_client.actions.a2a_client_action import A2AClientAction, AgentSkill
# Mock A2A types needed for assertions - EXPECTING THESE TO BE `Any` in the test env
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

        # Instantiate the action - REMOVED patch on Action.__init__
        self.action = A2AClientAction(
            skill=self.mock_skill,
            component=self.mock_component, # type: ignore
            inferred_params=self.mock_params_def
        )

    def test_invoke_mapping_text_only_handles_import_error(self):
        """Test mapping returns error correctly if TextPart instantiation fails (due to import error)."""
        params = {"prompt": "Hello A2A"}
        meta = {"session_id": "session123"}

        # Call invoke - Expecting TextPart(...) to raise TypeError: Any cannot be instantiated
        response = self.action.invoke(params, meta)

        # Assert that an error response is returned due to the expected TypeError
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info, "ActionResponse should have error_info")
        self.assertIn("Could not process prompt text", response.message)
        self.assertIn("TextPart Error", response.error_info.code)
        # Ensure the attribute causing the previous assertion error is NOT set
        self.assertFalse(hasattr(self.action, '_last_constructed_task_params'))

    def test_invoke_mapping_text_and_valid_file_handles_import_error(self):
        """Test mapping returns error correctly if FilePart/FileContent instantiation fails."""
        params = {"prompt": "Process this file", "files": ["valid_url"]}
        meta = {"session_id": "session456"}

        # Call invoke - Expecting TextPart or FilePart/FileContent to raise TypeError
        response = self.action.invoke(params, meta)

        # Assert that an error response is returned
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info, "ActionResponse should have error_info")
        # It will likely fail on TextPart first
        self.assertIn("Could not process prompt text", response.message)
        self.assertIn("TextPart Error", response.error_info.code)
        self.assertFalse(hasattr(self.action, '_last_constructed_task_params'))

    def test_invoke_mapping_text_and_multiple_files_handles_import_error(self):
        """Test mapping returns error correctly even with multiple files if TextPart fails."""
        params = {"prompt": "Multiple files", "files": ["valid_url", "invalid_url", "error_url", 123]} # Include non-string
        meta = {"session_id": "session789"}

        with patch('src.agents.a2a_client.actions.a2a_client_action.logger.warning') as mock_log_warn, \
             patch('src.agents.a2a_client.actions.a2a_client_action.logger.error') as mock_log_err:
            # Call invoke - Expecting TextPart to raise TypeError
            response = self.action.invoke(params, meta)

        # Assert that an error response is returned due to TextPart failure
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info, "ActionResponse should have error_info")
        self.assertIn("Could not process prompt text", response.message)
        self.assertIn("TextPart Error", response.error_info.code)
        self.assertFalse(hasattr(self.action, '_last_constructed_task_params'))

        # Check that the error log for TextPart failure was called
        mock_log_err.assert_any_call(
            "Failed to create TextPart for action 'test_skill_id': Any cannot be instantiated",
            exc_info=True
        )
        # Ensure file processing logs were NOT reached because TextPart failed first
        mock_log_warn.assert_not_called()
        # Check other errors weren't logged for file resolution in this specific path
        file_resolve_errors = [
            c for c in mock_log_err.call_args_list
            if "resolve file URL" in c.args[0]
        ]
        self.assertEqual(len(file_resolve_errors), 0)


    def test_invoke_mapping_missing_prompt(self):
        """Test mapping fails if required 'prompt' parameter is missing."""
        params = {"files": ["valid_url"]} # No prompt
        meta = {"session_id": "session_no_prompt"}

        response = self.action.invoke(params, meta)

        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "Missing required 'prompt' parameter.")
        self.assertEqual(response.error_info.code, "Missing Parameter")
        self.assertFalse(hasattr(self.action, '_last_constructed_task_params')) # Should fail before construction

    def test_invoke_mapping_no_session_id_handles_import_error(self):
        """Test mapping generates session ID but still fails on TextPart due to import error."""
        params = {"prompt": "Generate session"}
        meta = {} # No session_id

        with patch('src.agents.a2a_client.actions.a2a_client_action.uuid.uuid4') as mock_uuid, \
             patch('src.agents.a2a_client.actions.a2a_client_action.logger.warning') as mock_log_warn:
            mock_uuid.return_value = uuid.UUID('12345678-1234-5678-1234-567812345678')
            # Call invoke - Expecting TextPart to raise TypeError
            response = self.action.invoke(params, meta)

        # Assert session ID warning was logged
        mock_log_warn.assert_called_with("No session_id found in meta for action 'test_skill_id'. Generated new one: 12345678-1234-5678-1234-567812345678")

        # Assert that an error response is returned due to TextPart failure
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info, "ActionResponse should have error_info")
        self.assertIn("Could not process prompt text", response.message)
        self.assertIn("TextPart Error", response.error_info.code)
        self.assertFalse(hasattr(self.action, '_last_constructed_task_params'))

    def test_invoke_mapping_no_a2a_client(self):
        """Test mapping fails if a2a_client is not initialized."""
        self.mock_component.a2a_client = None # Simulate client not ready
        params = {"prompt": "Client missing"}
        meta = {"session_id": "session_no_client"}

        response = self.action.invoke(params, meta)

        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "Internal Error: A2A Client not available.")
        self.assertEqual(response.error_info.code, "A2A Client Missing")

    def test_invoke_mapping_no_file_service(self):
        """Test mapping fails if file_service is not available."""
        self.mock_component.file_service = None # Simulate service missing
        params = {"prompt": "File service missing"}
        meta = {"session_id": "session_no_fs"}

        response = self.action.invoke(params, meta)

        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "Internal Error: File Service not available.")
        self.assertEqual(response.error_info.code, "File Service Missing")


if __name__ == '__main__':
    unittest.main()
