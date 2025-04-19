import unittest
from unittest.mock import MagicMock, patch, ANY
import uuid

# Adjust import paths as necessary
from src.agents.a2a_client.actions.a2a_client_action import A2AClientAction, AgentSkill
# Mock A2A types needed for assertions - EXPECTING THESE TO BE `Any` in the test env
# We will patch these specifically in tests where instantiation failure is expected
# from src.agents.a2a_client.actions.a2a_client_action import TaskSendParams, A2AMessage, TextPart, FilePart, FileContent
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo
from solace_ai_connector.common.log import log # Import the log object

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
        # If file_service is not provided, it defaults to MockFileService instance
        self.file_service = file_service if file_service is not None else MockFileService()
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
        # *** FIX: Explicitly make file_service a MagicMock for call tracking ***
        # We assign a MagicMock that uses the original class for its spec,
        # ensuring methods exist, but allowing call tracking.
        self.mock_component.file_service = MagicMock(spec=MockFileService)
        # If needed for other tests, configure the mock's behavior:
        # self.mock_component.file_service.resolve_url.side_effect = MockFileService().resolve_url

        # Instantiate the action - REMOVED global patch on TextPart
        self.action = A2AClientAction(
            skill=self.mock_skill,
            component=self.mock_component, # type: ignore
            inferred_params=self.mock_params_def
        )

    @patch('src.agents.a2a_client.actions.a2a_client_action.TextPart', side_effect=TypeError("Simulated TextPart instantiation error"))
    def test_invoke_mapping_text_only_handles_import_error(self, mock_text_part_constructor):
        """Test mapping returns error correctly if TextPart instantiation fails."""
        params = {"prompt": "Hello A2A"}
        meta = {"session_id": "session123"}

        # Call invoke - Expecting TextPart(...) to raise TypeError
        response = self.action.invoke(params, meta)

        # Assert that an error response is returned due to the expected TypeError
        mock_text_part_constructor.assert_called_once_with(text="Hello A2A")
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info, "ActionResponse should have error_info")
        self.assertIn("Could not process prompt text", response.message)
        # Check error_message instead of code
        self.assertIn("TextPart Error", response.error_info.error_message)
        self.assertIn("Simulated TextPart instantiation error", response.error_info.error_message)
        # Ensure the A2A client was NOT called
        self.mock_component.a2a_client.send_task.assert_not_called()

    @patch('src.agents.a2a_client.actions.a2a_client_action.TextPart', side_effect=TypeError("Simulated TextPart instantiation error"))
    @patch('src.agents.a2a_client.actions.a2a_client_action.FilePart') # Keep FilePart mocked if TextPart fails first
    @patch('src.agents.a2a_client.actions.a2a_client_action.FileContent')
    def test_invoke_mapping_text_and_valid_file_handles_import_error(self, mock_file_content_cls, mock_file_part_cls, mock_text_part_constructor):
        """Test mapping returns error correctly if TextPart instantiation fails (even with files)."""
        params = {"prompt": "Process this file", "files": ["valid_url"]}
        meta = {"session_id": "session456"}

        # Call invoke - Expecting TextPart to raise TypeError
        response = self.action.invoke(params, meta)

        # Assert that an error response is returned due to TextPart failure
        mock_text_part_constructor.assert_called_once_with(text="Process this file")
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info, "ActionResponse should have error_info")
        self.assertIn("Could not process prompt text", response.message)
        self.assertIn("TextPart Error", response.error_info.error_message)
        self.assertIn("Simulated TextPart instantiation error", response.error_info.error_message)
        # Ensure file processing and A2A client call were not reached
        # *** FIX: Now this assertion works because file_service.resolve_url is a mock ***
        self.mock_component.file_service.resolve_url.assert_not_called()
        mock_file_content_cls.assert_not_called()
        mock_file_part_cls.assert_not_called()
        self.mock_component.a2a_client.send_task.assert_not_called()

    @patch('src.agents.a2a_client.actions.a2a_client_action.TextPart', side_effect=TypeError("Simulated TextPart instantiation error"))
    @patch('src.agents.a2a_client.actions.a2a_client_action.FilePart')
    @patch('src.agents.a2a_client.actions.a2a_client_action.FileContent')
    def test_invoke_mapping_text_and_multiple_files_handles_import_error(self, mock_file_content_cls, mock_file_part_cls, mock_text_part_constructor):
        """Test mapping returns error correctly if TextPart fails, even with multiple files."""
        params = {"prompt": "Multiple files", "files": ["valid_url", "invalid_url", "error_url", 123]} # Include non-string
        meta = {"session_id": "session789"}

        with patch('solace_ai_connector.common.log.log.warning') as mock_log_warn, \
             patch('solace_ai_connector.common.log.log.error') as mock_log_err:
            # Call invoke - Expecting TextPart to raise TypeError
            response = self.action.invoke(params, meta)

        # Assert that an error response is returned due to TextPart failure
        mock_text_part_constructor.assert_called_once_with(text="Multiple files")
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info, "ActionResponse should have error_info")
        self.assertIn("Could not process prompt text", response.message)
        self.assertIn("TextPart Error", response.error_info.error_message)
        self.assertIn("Simulated TextPart instantiation error", response.error_info.error_message)

        # Check that the error log for TextPart failure was called
        mock_log_err.assert_any_call(
            "Failed to create TextPart for action '%s' prompt: %s",
            'test_skill_id', "Simulated TextPart instantiation error",
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
        self.mock_component.a2a_client.send_task.assert_not_called()


    def test_invoke_mapping_missing_prompt(self):
        """Test mapping fails if required 'prompt' parameter is missing."""
        params = {"files": ["valid_url"]} # No prompt
        meta = {"session_id": "session_no_prompt"}

        response = self.action.invoke(params, meta)

        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "Missing required 'prompt' parameter.")
        # Check error_message instead of code
        self.assertEqual(response.error_info.error_message, "Missing Parameter")
        self.mock_component.a2a_client.send_task.assert_not_called() # Should fail before construction

    @patch('src.agents.a2a_client.actions.a2a_client_action.TextPart', side_effect=TypeError("Simulated TextPart instantiation error"))
    def test_invoke_mapping_no_session_id_handles_import_error(self, mock_text_part_constructor):
        """Test mapping generates session ID but still fails on TextPart due to simulated error."""
        params = {"prompt": "Generate session"}
        meta = {} # No session_id
        generated_uuid = '12345678-1234-5678-1234-567812345678'

        with patch('src.agents.a2a_client.actions.a2a_client_action.uuid.uuid4') as mock_uuid, \
             patch('solace_ai_connector.common.log.log.warning') as mock_log_warn:
            mock_uuid.return_value = uuid.UUID(generated_uuid)
            # Call invoke - Expecting TextPart to raise TypeError
            response = self.action.invoke(params, meta)

        # Assert session ID warning was logged
        mock_log_warn.assert_called_with("No session_id found in meta for action '%s'. Generated new one: %s", 'test_skill_id', generated_uuid)

        # Assert that an error response is returned due to TextPart failure
        mock_text_part_constructor.assert_called_once_with(text="Generate session")
        self.assertIsInstance(response, ActionResponse)
        self.assertIsNotNone(response.error_info, "ActionResponse should have error_info")
        self.assertIn("Could not process prompt text", response.message)
        self.assertIn("TextPart Error", response.error_info.error_message)
        self.assertIn("Simulated TextPart instantiation error", response.error_info.error_message)
        self.mock_component.a2a_client.send_task.assert_not_called()

    def test_invoke_mapping_no_a2a_client(self):
        """Test mapping fails if a2a_client is not initialized."""
        self.mock_component.a2a_client = None # Simulate client not ready
        params = {"prompt": "Client missing"}
        meta = {"session_id": "session_no_client"}

        response = self.action.invoke(params, meta)

        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "Internal Error: A2A Client not available.")
        # Check error_message instead of code
        self.assertEqual(response.error_info.error_message, "A2A Client Missing")

    def test_invoke_mapping_no_file_service(self):
        """Test mapping fails if file_service is not available."""
        self.mock_component.file_service = None # Simulate service missing
        params = {"prompt": "File service missing"}
        meta = {"session_id": "session_no_fs"}

        response = self.action.invoke(params, meta)

        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "Internal Error: File Service not available.")
        # Check error_message instead of code
        self.assertEqual(response.error_info.error_message, "File Service Missing")


if __name__ == '__main__':
    unittest.main()
