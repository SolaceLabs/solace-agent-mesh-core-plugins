import unittest
from unittest.mock import patch, MagicMock
import threading
import subprocess

# Adjust the import path based on how tests are run (e.g., from root)
from .test_helpers import create_test_component # Import helper
from solace_ai_connector.common.log import log # Import the log object
# Import the class to mock its instance methods if needed
from src.agents.a2a_client.a2a_process_manager import A2AProcessManager

class TestA2AClientAgentComponentStop(unittest.TestCase):

    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.stop_component')
    # Removed the patch for A2AProcessManager.stop here
    def test_stop_component_stops_process_manager(self, mock_super_stop):
        """Test stop_component calls stop on the process manager instance if it exists."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache)
        # Mock process manager instance specifically
        mock_pm = MagicMock(spec=A2AProcessManager) # Use spec for better mocking
        component.process_manager = mock_pm
        # Mock connection handler
        component.connection_handler = MagicMock()

        component.stop_component()

        self.assertTrue(component.stop_monitor.is_set())
        # Assert stop was called on the mock INSTANCE
        mock_pm.stop.assert_called_once()
        self.assertIsNone(component.process_manager) # Should be cleared
        self.assertIsNone(component.connection_handler) # Should be cleared
        self.assertFalse(component._initialized.is_set()) # Should be cleared
        mock_super_stop.assert_called_once()

    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.stop_component')
    # Removed the patch for A2AProcessManager.stop here
    def test_stop_component_no_process_manager(self, mock_super_stop):
        """Test stop_component handles no process manager existing."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache)
        component.process_manager = None # No process manager
        # Mock connection handler
        component.connection_handler = MagicMock()

        # Store the original stop method of the class to ensure it's not called
        original_pm_stop = A2AProcessManager.stop

        # Use a spy on the original method if needed, but simpler to just check instance
        # For this test, we just need to ensure no error occurs and super is called.
        # We don't need to assert stop *wasn't* called on a non-existent instance.

        component.stop_component()

        self.assertTrue(component.stop_monitor.is_set())
        # No process manager, so no stop call expected on any instance
        # (We removed the class patch, so no need to assert_not_called on that)
        self.assertIsNone(component.process_manager)
        self.assertIsNone(component.connection_handler) # Still cleared
        self.assertFalse(component._initialized.is_set())
        mock_super_stop.assert_called_once()


    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.stop_component')
    def test_stop_component_clears_connection_handler(self, mock_super_stop):
        """Test stop_component clears connection handler attributes."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache)
        component.process_manager = None # No process manager
        # Mock connection handler with attributes
        mock_ch = MagicMock()
        mock_ch.agent_card = MagicMock()
        mock_ch.a2a_client = MagicMock()
        component.connection_handler = mock_ch

        component.stop_component()

        self.assertTrue(component.stop_monitor.is_set())
        # Check attributes on the original mock are cleared by the component's stop
        self.assertIsNone(mock_ch.agent_card)
        self.assertIsNone(mock_ch.a2a_client)
        self.assertIsNone(component.connection_handler) # Component's reference cleared
        self.assertFalse(component._initialized.is_set())
        mock_super_stop.assert_called_once()

if __name__ == '__main__':
    unittest.main()
