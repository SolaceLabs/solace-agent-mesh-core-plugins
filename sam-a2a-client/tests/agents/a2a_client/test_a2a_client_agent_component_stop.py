import unittest
from unittest.mock import patch, MagicMock
import threading
import subprocess

# Adjust the import path based on how tests are run (e.g., from root)
from .test_helpers import create_test_component # Import helper
from solace_ai_connector.common.log import log # Import the log object

class TestA2AClientAgentComponentStop(unittest.TestCase):

    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.stop_component')
    @patch('src.agents.a2a_client.a2a_process_manager.A2AProcessManager.stop') # Patch stop in ProcessManager
    def test_stop_component_stops_process_manager(self, mock_pm_stop, mock_super_stop):
        """Test stop_component calls stop on the process manager if it exists."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache)
        # Mock process manager instance
        mock_pm = MagicMock()
        component.process_manager = mock_pm
        # Mock connection handler
        component.connection_handler = MagicMock()

        component.stop_component()

        self.assertTrue(component.stop_monitor.is_set())
        mock_pm_stop.assert_called_once() # Verify process manager stop was called
        self.assertIsNone(component.process_manager) # Should be cleared
        self.assertIsNone(component.connection_handler) # Should be cleared
        self.assertFalse(component._initialized.is_set()) # Should be cleared
        mock_super_stop.assert_called_once()

    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.stop_component')
    @patch('src.agents.a2a_client.a2a_process_manager.A2AProcessManager.stop') # Patch stop in ProcessManager
    def test_stop_component_no_process_manager(self, mock_pm_stop, mock_super_stop):
        """Test stop_component handles no process manager existing."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache)
        component.process_manager = None # No process manager
        # Mock connection handler
        component.connection_handler = MagicMock()

        component.stop_component()

        self.assertTrue(component.stop_monitor.is_set())
        mock_pm_stop.assert_not_called() # Process manager stop NOT called
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
