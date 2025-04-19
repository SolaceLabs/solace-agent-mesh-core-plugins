import unittest
from unittest.mock import patch, MagicMock

# Adjust the import path based on how tests are run (e.g., from root)
from .test_helpers import create_test_component # Import helper
from solace_ai_connector.common.log import log # Import the log object

class TestA2AClientAgentComponentRun(unittest.TestCase):

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._initialize_a2a_connection')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._create_actions') # Mock action creation
    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.run') # Mock super().run()
    def test_run_calls_initialize_create_actions_and_super(self, mock_super_run, mock_create_actions, mock_initialize):
        """Test the run method calls initialization, action creation, and super().run()."""
        component = create_test_component()
        component.run()

        mock_initialize.assert_called_once()
        mock_create_actions.assert_called_once() # Verify action creation is called
        mock_super_run.assert_called_once()
        self.assertTrue(component._initialized.is_set()) # Check event is set on success

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._initialize_a2a_connection', side_effect=ValueError("Init failed"))
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._create_actions')
    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.run')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent.stop_component')
    @patch('solace_ai_connector.common.log.log.critical') # Patch the correct log object
    def test_run_handles_initialization_failure(self, mock_log_critical, mock_stop, mock_super_run, mock_create_actions, mock_initialize):
        """Test run handles exceptions during initialization."""
        component = create_test_component()
        component.run()

        mock_initialize.assert_called_once()
        mock_create_actions.assert_not_called() # Should not be called if init fails
        mock_log_critical.assert_called_once() # Check critical error logged
        # Check the first argument of the call contains the expected message
        self.assertIn("Initialization failed", mock_log_critical.call_args[0][0])
        mock_stop.assert_called_once() # Ensure cleanup called
        mock_super_run.assert_not_called() # Base run should not be called
        self.assertFalse(component._initialized.is_set()) # Event should not be set

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._initialize_a2a_connection')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._create_actions', side_effect=Exception("Action creation failed"))
    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.run')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent.stop_component')
    @patch('solace_ai_connector.common.log.log.critical') # Patch the correct log object
    def test_run_handles_action_creation_failure(self, mock_log_critical, mock_stop, mock_super_run, mock_create_actions, mock_initialize):
        """Test run handles exceptions during action creation."""
        component = create_test_component()
        component.run()

        mock_initialize.assert_called_once()
        mock_create_actions.assert_called_once() # Action creation was attempted
        mock_log_critical.assert_called_once() # Check critical error logged
        # Check the first argument of the call contains the expected message
        self.assertIn("Action creation failed", mock_log_critical.call_args[0][0])
        mock_stop.assert_called_once() # Ensure cleanup called
        mock_super_run.assert_not_called() # Base run should not be called
        self.assertFalse(component._initialized.is_set()) # Event should not be set

if __name__ == '__main__':
    unittest.main()
