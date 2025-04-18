import unittest
from unittest.mock import patch, MagicMock
import threading

# Adjust the import path based on how tests are run (e.g., from root)
from src.agents.a2a_client.a2a_client_agent_component import A2AClientAgentComponent, info as component_info
from solace_agent_mesh.common.action_list import ActionList
from .test_helpers import create_test_component # Import helper

class TestA2AClientAgentComponentInit(unittest.TestCase):

    def test_info_variable(self):
        """Verify the structure and content of the info class variable."""
        self.assertIsInstance(component_info, dict)
        self.assertEqual(component_info["class_name"], "A2AClientAgentComponent")
        self.assertIn("description", component_info)
        self.assertIsInstance(component_info["config_parameters"], list)

        # Check for presence of specific A2A config parameters
        param_names = [p["name"] for p in component_info["config_parameters"]]
        self.assertIn("agent_name", param_names)
        self.assertIn("a2a_server_url", param_names)
        self.assertIn("a2a_server_command", param_names)
        self.assertIn("a2a_server_startup_timeout", param_names)
        self.assertIn("a2a_server_restart_on_crash", param_names)
        self.assertIn("a2a_bearer_token", param_names)
        self.assertIn("input_required_ttl", param_names)
        # Check inherited param
        self.assertIn("registration_interval", param_names)

    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.__init__')
    @patch('src.agents.a2a_client.a2a_client_agent_component.FileService')
    @patch('logging.Logger.warning') # Patch logger directly if needed
    def test_init_method(self, mock_log_warning, mock_file_service, mock_super_init):
        """Test the __init__ method initializes attributes correctly."""
        mock_config = {
            "agent_name": "test_a2a_agent",
            "a2a_server_url": "http://localhost:10001",
            "a2a_server_command": "run_agent.sh",
            "a2a_server_startup_timeout": 45,
            "a2a_server_restart_on_crash": False,
            "a2a_bearer_token": "test_token_123",
            "input_required_ttl": 600,
            "registration_interval": 60 # Example inherited config
        }
        # Create the mock cache here
        mock_cache = MagicMock()

        # Use the helper, passing the created mock cache instance
        component = create_test_component(
            config_overrides=mock_config,
            cache_service_instance=mock_cache # Pass the instance
        )

        # Assert super().__init__ was called (mocked during create_test_component)
        # We can't directly assert on the mock created inside the helper's context easily,
        # but we trust the helper setup.

        # Assert config values are read and stored (using the instance's mocked get_config)
        self.assertEqual(component.agent_name, "test_a2a_agent")
        self.assertEqual(component.a2a_server_url, "http://localhost:10001")
        self.assertEqual(component.a2a_server_command, "run_agent.sh")
        self.assertEqual(component.a2a_server_startup_timeout, 45)
        self.assertEqual(component.a2a_server_restart_on_crash, False)
        self.assertEqual(component.a2a_bearer_token, "test_token_123")
        self.assertEqual(component.input_required_ttl, 600)

        # Assert state variables are initialized
        self.assertIsNone(component.a2a_process)
        self.assertIsNone(component.monitor_thread)
        self.assertIsInstance(component.stop_monitor, threading.Event)
        self.assertIsNone(component.agent_card)
        self.assertIsNone(component.a2a_client)
        self.assertIsInstance(component._initialized, threading.Event)

        # Assert services are stored/initialized
        # mock_file_service.assert_called_once() # Mocked during create_test_component
        # Now assert that the component's cache service IS the one we created
        self.assertEqual(component.cache_service, mock_cache)

        # Assert ActionList is initialized
        self.assertIsInstance(component.action_list, ActionList)
        self.assertEqual(len(component.action_list.actions), 0) # Initially empty

        # Assert info is updated
        self.assertEqual(component.info["agent_name"], "test_a2a_agent")

        # Assert no warning about cache service
        mock_log_warning.assert_not_called()

    @patch('logging.Logger.warning') # Patch logger directly
    def test_init_method_no_cache(self, mock_log_warning):
        """Test __init__ logs warning if cache_service is missing."""
        mock_config = {
            "agent_name": "test_a2a_agent_no_cache",
            "a2a_server_url": "http://localhost:10002",
        }
        # Use helper, explicitly passing cache_service_instance=None
        create_test_component(
            config_overrides=mock_config,
            cache_service_instance=None # Pass None explicitly
        )

        # Assert warning was logged
        mock_log_warning.assert_called_once_with(
            "Cache service not provided to A2AClientAgentComponent. INPUT_REQUIRED state will not be supported."
        )

if __name__ == '__main__':
    unittest.main()
