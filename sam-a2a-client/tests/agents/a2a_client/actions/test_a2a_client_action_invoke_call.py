import unittest
from unittest.mock import MagicMock, patch, ANY
import uuid
from requests.exceptions import ConnectionError

# Adjust import paths as necessary
from src.agents.a2a_client.actions.a2a_client_action import A2AClientAction, AgentSkill

# Mock A2A types needed for assertions - EXPECTING THESE TO BE `Any` in the test env
from src.agents.a2a_client.actions.a2a_client_action import (
    TaskSendParams,
    A2AMessage,
    TextPart,
    FilePart,
    FileContent,
    Task,
    TaskState,  # This will be mocked as Any
)
# Import TaskStatus from the correct location
from src.common_a2a.types import TaskStatus
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo


# Mock the parent component and services
class MockFileService:
    def resolve_url(self, url, session_id=None):
        # Simplified for these tests, assuming text only for now
        raise NotImplementedError


class MockA2AClientAgentComponent:
    def __init__(
        self,
        agent_name="mock_agent",
        cache_service=None,
        file_service=None,
        a2a_client=None,
    ):
        self.agent_name = agent_name
        self.get_config = MagicMock()
        self.cache_service = cache_service or MagicMock()
        self.file_service = file_service or MockFileService()
        self.a2a_client = a2a_client or MagicMock()  # Provide a mock client
        # Add input_required_ttl needed by INPUT_REQUIRED test
        self.input_required_ttl = 300


class TestA2AClientActionInvokeCall(unittest.TestCase):

    def setUp(self):
        # Mock A2A AgentSkill
        self.mock_skill = MagicMock(spec=AgentSkill)
        self.mock_skill.id = "test_skill_id"
        self.mock_skill.name = "Test Skill Name"
        self.mock_skill.description = "This is a test skill description."

        # Mock the parent component with a mock A2AClient and CacheService
        self.mock_a2a_client = MagicMock()
        self.mock_cache_service = MagicMock()
        self.mock_component = MockA2AClientAgentComponent(
            agent_name="test_sam_agent",
            a2a_client=self.mock_a2a_client,
            cache_service=self.mock_cache_service,
        )

        # Mock inferred parameters
        self.mock_params_def = [
            {
                "name": "prompt",
                "desc": "User prompt",
                "type": "string",
                "required": True,
            }
        ]

        # Instantiate the action
        # Patch TextPart to avoid import errors during test setup if A2A types are mocked as Any
        with patch(
            "src.agents.a2a_client.actions.a2a_client_action.TextPart", MagicMock()
        ) as self.MockTextPart:
            self.action = A2AClientAction(
                skill=self.mock_skill,
                component=self.mock_component,  # type: ignore
                inferred_params=self.mock_params_def,
            )
            # Ensure the mock TextPart instance can be created for the test setup itself
            self.MockTextPart.return_value = MagicMock()

    def _create_mock_task_response(self, state, message_parts=None, task_id="task-123"):
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
        return mock_task

    def _create_mock_text_part(self, text):
        """Helper to create a mock TextPart."""
        mock_part = MagicMock(spec=TextPart)
        mock_part.text = text
        return mock_part

    @patch(
        "src.agents.a2a_client.actions.a2a_client_action.TextPart"
    )  # Mock TextPart for the invoke call
    @patch("src.agents.a2a_client.actions.a2a_client_action.TaskSendParams")
    @patch("src.agents.a2a_client.actions.a2a_client_action.A2AMessage")
    def test_invoke_call_completed(
        self, MockA2AMessage, MockTaskSendParams, MockTextPart
    ):
        """Test invoke handles COMPLETED state from send_task."""
        params = {"prompt": "Do the thing"}
        meta = {"session_id": "session_complete"}

        # Mock the Task response
        mock_response_task = self._create_mock_task_response(state="completed")
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors used in invoke
        MockTextPart.return_value = MagicMock(text="Do the thing")
        MockA2AMessage.return_value = MagicMock(
            role="user", parts=[MockTextPart.return_value]
        )
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {
            "id": ANY,
            "sessionId": ANY,
            "message": ANY,
            "acceptedOutputModes": ANY,
        }
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertIsNone(response.error_info) # Check for absence of error
        # Response mapping is tested separately, check basic success message for now
        self.assertEqual(response.message, "Task completed.")

    @patch("src.agents.a2a_client.actions.a2a_client_action.TextPart")
    @patch("src.agents.a2a_client.actions.a2a_client_action.TaskSendParams")
    @patch("src.agents.a2a_client.actions.a2a_client_action.A2AMessage")
    def test_invoke_call_failed(self, MockA2AMessage, MockTaskSendParams, MockTextPart):
        """Test invoke handles FAILED state from send_task."""
        params = {"prompt": "This will fail"}
        meta = {"session_id": "session_fail"}

        # Mock the Task response with an error message part
        mock_error_text_part = self._create_mock_text_part("Something went wrong")
        mock_response_task = self._create_mock_task_response(
            state="failed", message_parts=[mock_error_text_part]
        )
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text="This will fail")
        MockA2AMessage.return_value = MagicMock(
            role="user", parts=[MockTextPart.return_value]
        )
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {
            "id": ANY,
            "sessionId": ANY,
            "message": ANY,
            "acceptedOutputModes": ANY,
        }
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertIsNotNone(response.error_info) # Check for presence of error
        self.assertEqual(response.message, "A2A Task Failed: Something went wrong")
        self.assertEqual(response.error_info.error_message, "Something went wrong") # Error details in ErrorInfo

    @patch("src.agents.a2a_client.actions.a2a_client_action.TextPart")
    @patch("src.agents.a2a_client.actions.a2a_client_action.TaskSendParams")
    @patch("src.agents.a2a_client.actions.a2a_client_action.A2AMessage")
    def test_invoke_call_failed_no_details(
        self, MockA2AMessage, MockTaskSendParams, MockTextPart
    ):
        """Test invoke handles FAILED state without details in message."""
        params = {"prompt": "Fail silently"}
        meta = {"session_id": "session_fail_silent"}

        # Mock the Task response with no message parts
        mock_response_task = self._create_mock_task_response(state="failed", message_parts=None)
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text="Fail silently")
        MockA2AMessage.return_value = MagicMock(
            role="user", parts=[MockTextPart.return_value]
        )
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {
            "id": ANY,
            "sessionId": ANY,
            "message": ANY,
            "acceptedOutputModes": ANY,
        }
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertIsNotNone(response.error_info) # Check for presence of error
        self.assertEqual(response.message, "A2A Task Failed")  # No details appended
        self.assertEqual(response.error_info.error_message, "A2A Task Failed") # Default error in ErrorInfo

    @patch("src.agents.a2a_client.actions.a2a_client_action.TextPart")
    @patch("src.agents.a2a_client.actions.a2a_client_action.TaskSendParams")
    @patch("src.agents.a2a_client.actions.a2a_client_action.A2AMessage")
    @patch("src.agents.a2a_client.actions.a2a_client_action.uuid.uuid4") # Mock uuid generation
    def test_invoke_call_input_required(
        self, mock_uuid, MockA2AMessage, MockTaskSendParams, MockTextPart
    ):
        """Test invoke handles INPUT_REQUIRED state from send_task."""
        params = {"prompt": "Need more info"}
        meta = {"session_id": "session_input"}
        mock_follow_up_id = "mock-follow-up-uuid"
        mock_uuid.return_value = mock_follow_up_id
        mock_a2a_task_id = "original-a2a-task-id"

        # Mock the Task response with a question part
        mock_question_part = self._create_mock_text_part("What color?")
        mock_response_task = self._create_mock_task_response(
            state="input-required", message_parts=[mock_question_part], task_id=mock_a2a_task_id
        )
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text="Need more info")
        MockA2AMessage.return_value = MagicMock(
            role="user", parts=[MockTextPart.return_value]
        )
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {
            "id": ANY,
            "sessionId": ANY,
            "message": ANY,
            "acceptedOutputModes": ANY,
        }
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertIsNone(response.error_info) # Not an error state
        # Check message contains question
        self.assertEqual(response.message, "What color?")
        # Check data contains follow-up ID
        self.assertIsNotNone(response.data)
        self.assertEqual(response.data.get('follow_up_id'), mock_follow_up_id)
        # Check cache was called
        self.mock_cache_service.set.assert_called_once_with(
            f"a2a_follow_up:{mock_follow_up_id}",
            mock_a2a_task_id,
            ttl=self.mock_component.input_required_ttl
        )

    @patch("src.agents.a2a_client.actions.a2a_client_action.TextPart")
    @patch("src.agents.a2a_client.actions.a2a_client_action.TaskSendParams")
    @patch("src.agents.a2a_client.actions.a2a_client_action.A2AMessage")
    @patch("src.agents.a2a_client.actions.a2a_client_action.uuid.uuid4")
    @patch("logging.Logger.error")
    def test_invoke_call_input_required_no_cache(
        self, mock_log_error, mock_uuid, MockA2AMessage, MockTaskSendParams, MockTextPart
    ):
        """Test invoke handles INPUT_REQUIRED state when cache service is missing."""
        self.mock_component.cache_service = None # Simulate missing cache
        params = {"prompt": "Need more info, no cache"}
        meta = {"session_id": "session_input_no_cache"}

        # Mock the Task response
        mock_question_part = self._create_mock_text_part("What color?")
        mock_response_task = self._create_mock_task_response(
            state="input-required", message_parts=[mock_question_part]
        )
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text="Need more info, no cache")
        MockA2AMessage.return_value = MagicMock(
            role="user", parts=[MockTextPart.return_value]
        )
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {
            "id": ANY,
            "sessionId": ANY,
            "message": ANY,
            "acceptedOutputModes": ANY,
        }
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertIsNotNone(response.error_info)
        self.assertEqual(response.message, "Internal Error: Cannot handle required input state without CacheService.")
        self.assertEqual(response.error_info.error_message, "Cache Service Missing")
        mock_log_error.assert_called_once() # Check error was logged
        self.assertIn("CacheService not available", mock_log_error.call_args[0][0])
        mock_uuid.assert_not_called() # Should fail before generating follow-up ID

    @patch("src.agents.a2a_client.actions.a2a_client_action.TextPart")
    @patch("src.agents.a2a_client.actions.a2a_client_action.TaskSendParams")
    @patch("src.agents.a2a_client.actions.a2a_client_action.A2AMessage")
    def test_invoke_call_unexpected_state(
        self, MockA2AMessage, MockTaskSendParams, MockTextPart
    ):
        """Test invoke handles unexpected states from send_task."""
        params = {"prompt": "Unexpected"}
        meta = {"session_id": "session_unexpected"}

        # Mock the Task response with an unexpected state
        mock_response_task = self._create_mock_task_response(state="working") # Example unexpected state
        self.mock_a2a_client.send_task.return_value = mock_response_task

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text="Unexpected")
        MockA2AMessage.return_value = MagicMock(
            role="user", parts=[MockTextPart.return_value]
        )
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {
            "id": ANY,
            "sessionId": ANY,
            "message": ANY,
            "acceptedOutputModes": ANY,
        }
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertIsNotNone(response.error_info) # Check for presence of error
        self.assertEqual(
            response.message,
            f"A2A Task is currently in state: {mock_response_task.status.state}",
        )
        self.assertEqual(response.error_info.error_message, f"Unhandled A2A State: {mock_response_task.status.state}")

    @patch("src.agents.a2a_client.actions.a2a_client_action.TextPart")
    @patch("src.agents.a2a_client.actions.a2a_client_action.TaskSendParams")
    @patch("src.agents.a2a_client.actions.a2a_client_action.A2AMessage")
    def test_invoke_call_communication_error(
        self, MockA2AMessage, MockTaskSendParams, MockTextPart
    ):
        """Test invoke handles communication errors during send_task."""
        params = {"prompt": "Comm error"}
        meta = {"session_id": "session_comm_error"}

        # Mock send_task to raise an exception
        error_message = "Network unreachable"
        self.mock_a2a_client.send_task.side_effect = ConnectionError(error_message)

        # Mock A2A type constructors
        MockTextPart.return_value = MagicMock(text="Comm error")
        MockA2AMessage.return_value = MagicMock(
            role="user", parts=[MockTextPart.return_value]
        )
        mock_task_params_instance = MagicMock()
        mock_task_params_instance.model_dump.return_value = {
            "id": ANY,
            "sessionId": ANY,
            "message": ANY,
            "acceptedOutputModes": ANY,
        }
        MockTaskSendParams.return_value = mock_task_params_instance

        response = self.action.invoke(params, meta)

        self.mock_a2a_client.send_task.assert_called_once()
        self.assertIsNotNone(response.error_info) # Check for presence of error
        self.assertEqual(response.message, "Failed to communicate with A2A agent")
        self.assertIn("A2A Communication Error", response.error_info.error_message)
        self.assertIn(error_message, response.error_info.error_message)


if __name__ == "__main__":
    unittest.main()
