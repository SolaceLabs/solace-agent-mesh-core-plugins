import unittest
from unittest.mock import MagicMock, patch, ANY
import uuid
from requests.exceptions import ConnectionError

# Adjust import paths as necessary
from src.agents.a2a_client.actions.a2a_client_action import A2AClientAction, AgentSkill
# Mock A2A types needed for assertions - EXPECTING THESE TO BE `Any` in the test env
from src.agents.a2a_client.actions.a2a_client_action import TaskSendParams, A2AMessage, TextPart, FilePart, FileContent, Task, TaskState, TaskStatus
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo

# Mock the parent component and services
class MockFileService:
    def resolve_url(self, url, session_id=None):
        # Simplified for these tests, assuming text only for now
        raise NotImplementedError

class MockA2AClientAgentComponent:
    def __init__(self, agent_name="mock_agent", cache_service=None, file_service=None, a2a_client=None):
        self.agent_name = agent_name
        self.get_config = MagicMock()
        self.cache_service = cache_service or MagicMock()
        self.file_service = file_service or MockFileService()
        self.a2a_client = a2a_client or MagicMock() # Provide a mock client

class TestA2AClientActionInvokeCall(unittest.TestCase):

    def setUp(self):
        # Mock A2A AgentSkill
        self.mock_skill = MagicMock(spec=AgentSkill)
        self.mock_skill.id = "test_skill_id"
        self.mock_skill.name = "Test Skill Name"
        self.mock_skill.description = "This is a test skill description."

        # Mock the parent component with a mock A2AClient
        self.mock_a2a_client = MagicMock()
        self.mock_component = MockA2AClientAgentComponent(
            agent_name="test_sam_agent",
            a2a_client=self.mock_a2a_client
        )

        # Mock inferred parameters
        self.mock_params_def = [
            {"name": "prompt", "desc": "User prompt", "type": "string", "required": True}
        ]

        # Instantiate the action
        # Patch TextPart to avoid import errors during test setup if A2A types are mocked as Any
        with patch('src.agents.a2a_client.actions.a2a_client_action.TextPart', MagicMock()) as self.MockTextPart:
            self.action = A2AClientAction(
                skill=self.mock_skill,
                component=self.mock_component, # type: ignore
                inferred_params=self.mock_params_def
            )
            # Ensure the mock TextPart instance can be created for the test setup itself
            self.MockTextPart.return_value = MagicMock()


    @patch('src.agents.a2a_client.actions.a2a_client_action.TextPart') # Mock TextPart for the invoke call
    @patch('src.agents.a2a_client.actions.a2a_client_action.TaskSendParams')
    @patch('src.agents.a2a_client.actions.a2a_client_action.A2AMessage')
    def test_invoke_call_completed(self, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test invoke handles COMPLETED state from send_task."""
        params = {"prompt": "Do the thing"}
        meta = {"session_id": "session_complete"}

        # Mock the Task response
        mock_response_task = MagicMock(spec=Task)
        mock_response_task.status = MagicMock(spec=TaskStatus)
        mock_response_task.status.state = TaskState.COMPLETED
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors used in invoke
        MockTextPart.return_value = MagicMock(text="Do the thing")
        MockA2AMessage.return_value = MagicMock(role="user", parts=[MockTextPart.return_value])
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {"id": ANY, "sessionId": ANY, "message": ANY, "acceptedOutputModes": ANY}
        MockTaskSendParams.return_value = mock_task_params_instance


        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertTrue(response.success)
        self.assertEqual(response.message, "A2A Task Completed (Processing TBD)")
        self.assertIsNone(response.error_info)

    @patch('src.agents.a2a_client.actions.a2a_client_action.TextPart')
    @patch('src.agents.a2a_client.actions.a2a_client_action.TaskSendParams')
    @patch('src.agents.a2a_client.actions.a2a_client_action.A2AMessage')
    def test_invoke_call_failed(self, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test invoke handles FAILED state from send_task."""
        params = {"prompt": "This will fail"}
        meta = {"session_id": "session_fail"}

        # Mock the Task response with an error message part
        mock_error_text_part = MagicMock(spec=TextPart)
        mock_error_text_part.text = "Something went wrong"
        mock_response_task = MagicMock(spec=Task)
        mock_response_task.status = MagicMock(spec=TaskStatus)
        mock_response_task.status.state = TaskState.FAILED
        mock_response_task.status.message = MagicMock(spec=A2AMessage)
        mock_response_task.status.message.parts = [mock_error_text_part]
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text="This will fail")
        MockA2AMessage.return_value = MagicMock(role="user", parts=[MockTextPart.return_value])
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {"id": ANY, "sessionId": ANY, "message": ANY, "acceptedOutputModes": ANY}
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertFalse(response.success)
        self.assertEqual(response.message, "A2A Task Failed: Something went wrong")
        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.error_info.error_message, "A2A Task Failed")

    @patch('src.agents.a2a_client.actions.a2a_client_action.TextPart')
    @patch('src.agents.a2a_client.actions.a2a_client_action.TaskSendParams')
    @patch('src.agents.a2a_client.actions.a2a_client_action.A2AMessage')
    def test_invoke_call_failed_no_details(self, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test invoke handles FAILED state without details in message."""
        params = {"prompt": "Fail silently"}
        meta = {"session_id": "session_fail_silent"}

        # Mock the Task response with no message parts
        mock_response_task = MagicMock(spec=Task)
        mock_response_task.status = MagicMock(spec=TaskStatus)
        mock_response_task.status.state = TaskState.FAILED
        mock_response_task.status.message = None # No message
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text="Fail silently")
        MockA2AMessage.return_value = MagicMock(role="user", parts=[MockTextPart.return_value])
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {"id": ANY, "sessionId": ANY, "message": ANY, "acceptedOutputModes": ANY}
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertFalse(response.success)
        self.assertEqual(response.message, "A2A Task Failed") # No details appended
        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.error_info.error_message, "A2A Task Failed")

    @patch('src.agents.a2a_client.actions.a2a_client_action.TextPart')
    @patch('src.agents.a2a_client.actions.a2a_client_action.TaskSendParams')
    @patch('src.agents.a2a_client.actions.a2a_client_action.A2AMessage')
    def test_invoke_call_input_required(self, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test invoke handles INPUT_REQUIRED state from send_task."""
        params = {"prompt": "Need more info"}
        meta = {"session_id": "session_input"}

        # Mock the Task response with a question part
        mock_question_part = MagicMock(spec=TextPart)
        mock_question_part.text = "What color?"
        mock_response_task = MagicMock(spec=Task)
        mock_response_task.status = MagicMock(spec=TaskStatus)
        mock_response_task.status.state = TaskState.INPUT_REQUIRED
        mock_response_task.status.message = MagicMock(spec=A2AMessage)
        mock_response_task.status.message.parts = [mock_question_part]
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text="Need more info")
        MockA2AMessage.return_value = MagicMock(role="user", parts=[MockTextPart.return_value])
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {"id": ANY, "sessionId": ANY, "message": ANY, "acceptedOutputModes": ANY}
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertFalse(response.success)
        self.assertEqual(response.message, "What color?") # Agent's question
        self.assertEqual(response.status, "INPUT_REQUIRED")
        self.assertIsNone(response.error_info) # Not an error, just pending

    @patch('src.agents.a2a_client.actions.a2a_client_action.TextPart')
    @patch('src.agents.a2a_client.actions.a2a_client_action.TaskSendParams')
    @patch('src.agents.a2a_client.actions.a2a_client_action.A2AMessage')
    def test_invoke_call_unexpected_state(self, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test invoke handles unexpected states from send_task."""
        params = {"prompt": "Unexpected"}
        meta = {"session_id": "session_unexpected"}

        # Mock the Task response with an unexpected state
        mock_response_task = MagicMock(spec=Task)
        mock_response_task.status = MagicMock(spec=TaskStatus)
        # Use a string or a different mock value if TaskState.WORKING isn't available
        mock_response_task.status.state = "WORKING" # Or TaskState.WORKING if available
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text="Unexpected")
        MockA2AMessage.return_value = MagicMock(role="user", parts=[MockTextPart.return_value])
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {"id": ANY, "sessionId": ANY, "message": ANY, "acceptedOutputModes": ANY}
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertFalse(response.success)
        self.assertEqual(response.message, f"A2A Task ended with unexpected state: {mock_response_task.status.state}")
        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.error_info.error_message, "Unexpected A2A State")

    @patch('src.agents.a2a_client.actions.a2a_client_action.TextPart')
    @patch('src.agents.a2a_client.actions.a2a_client_action.TaskSendParams')
    @patch('src.agents.a2a_client.actions.a2a_client_action.A2AMessage')
    def test_invoke_call_communication_error(self, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test invoke handles communication errors during send_task."""
        params = {"prompt": "Comm error"}
        meta = {"session_id": "session_comm_error"}

        # Mock send_task to raise an exception
        error_message = "Network unreachable"
        self.mock_a2a_client.send_task.side_effect = ConnectionError(error_message)

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text="Comm error")
        MockA2AMessage.return_value = MagicMock(role="user", parts=[MockTextPart.return_value])
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {"id": ANY, "sessionId": ANY, "message": ANY, "acceptedOutputModes": ANY}
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertFalse(response.success)
        self.assertEqual(response.message, "Failed to communicate with A2A agent")
        self.assertIsNotNone(response.error_info)
        self.assertIn("A2A Communication Error", response.error_info.error_message)
        self.assertIn(error_message, response.error_info.error_message)


if __name__ == '__main__':
    unittest.main()
