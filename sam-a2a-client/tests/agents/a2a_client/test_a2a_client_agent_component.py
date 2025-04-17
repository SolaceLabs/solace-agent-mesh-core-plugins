import unittest
from unittest.mock import patch, MagicMock, ANY
import threading

# Adjust the import path based on how tests are run (e.g., from root)
from src.agents.a2a_client.a2a_client_agent_component import A2AClientAgentComponent, info as component_info
from solace_agent_mesh.common.action_list import ActionList


class TestA2AClientAgentComponent(unittest.TestCase):

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
        mock_cache = MagicMock()
        kwargs = {"cache_service": mock_cache}

        # Mock self.get_config to return values from mock_config
        def mock_get_config(key, default=None):
            return mock_config.get(key, default)

        # Need to patch get_config on the instance *during* init
        with patch.object(A2AClientAgentComponent, 'get_config', side_effect=mock_get_config) as patched_get_config:
            component = A2AClientAgentComponent(module_info=component_info, **kwargs)

            # Assert super().__init__ was called
            mock_super_init.assert_called_once_with(component_info, **kwargs)

            # Assert config values are read and stored
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
            mock_file_service.assert_called_once()
            self.assertEqual(component.cache_service, mock_cache)

            # Assert ActionList is initialized
            self.assertIsInstance(component.action_list, ActionList)
            self.assertEqual(len(component.action_list.actions), 0) # Initially empty

            # Assert info is updated
            self.assertEqual(component.info["agent_name"], "test_a2a_agent")

            # Assert no warning about cache service
            mock_log_warning.assert_not_called()

    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.__init__')
    @patch('src.agents.a2a_client.a2a_client_agent_component.FileService')
    @patch('logging.Logger.warning') # Patch logger directly
    def test_init_method_no_cache(self, mock_log_warning, mock_file_service, mock_super_init):
        """Test __init__ logs warning if cache_service is missing."""
        mock_config = {
            "agent_name": "test_a2a_agent_no_cache",
            "a2a_server_url": "http://localhost:10002",
        }
        kwargs = {"cache_service": None} # Explicitly pass None

        def mock_get_config(key, default=None):
            return mock_config.get(key, default)

        with patch.object(A2AClientAgentComponent, 'get_config', side_effect=mock_get_config):
             A2AClientAgentComponent(module_info=component_info, **kwargs)

        # Assert warning was logged
        mock_log_warning.assert_called_once_with(
            "Cache service not provided to A2AClientAgentComponent. INPUT_REQUIRED state will not be supported."
        )


if __name__ == '__main__':
    unittest.main()
