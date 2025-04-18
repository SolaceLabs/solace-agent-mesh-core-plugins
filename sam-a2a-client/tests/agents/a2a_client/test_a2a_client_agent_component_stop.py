import unittest
from unittest.mock import patch, MagicMock
import threading
import subprocess

# Adjust the import path based on how tests are run (e.g., from root)
from .test_helpers import create_test_component # Import helper

class TestA2AClientAgentComponentStop(unittest.TestCase):

    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.stop_component')
    def test_stop_component_terminates_process(self, mock_super_stop):
        """Test stop_component terminates the process and joins the thread."""
        component = create_test_component()
        # Mock process instance
        mock_process = MagicMock()
        mock_process.pid = 1234
        component.a2a_process = mock_process
        # Mock thread instance
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True # Simulate thread is alive
        component.monitor_thread = mock_thread

        component.stop_component()

        self.assertTrue(component.stop_monitor.is_set())
        # Assert calls on the mock_process instance
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=5)
        mock_process.kill.assert_not_called()
        # Assert calls on the mock_thread instance
        mock_thread.join.assert_called_once_with(timeout=5)
        mock_super_stop.assert_called_once()
        self.assertIsNone(component.a2a_process) # Should be cleared
        self.assertIsNone(component.monitor_thread) # Should be cleared

    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.stop_component')
    def test_stop_component_kills_process(self, mock_super_stop):
        """Test stop_component kills the process if terminate times out."""
        component = create_test_component()
        # Mock process instance
        mock_process = MagicMock()
        mock_process.pid = 1234
        component.a2a_process = mock_process
        # Mock thread instance
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True # Simulate thread is alive
        component.monitor_thread = mock_thread

        # Simulate wait timing out after terminate, then succeeding after kill
        mock_process.wait.side_effect = [subprocess.TimeoutExpired(cmd="cmd", timeout=5), None]

        component.stop_component()

        self.assertTrue(component.stop_monitor.is_set())
        # Assert calls on the mock_process instance
        mock_process.terminate.assert_called_once()
        self.assertEqual(mock_process.wait.call_count, 2) # Called after terminate and after kill
        mock_process.kill.assert_called_once()
        # Assert calls on the mock_thread instance
        mock_thread.join.assert_called_once_with(timeout=5)
        mock_super_stop.assert_called_once()
        self.assertIsNone(component.a2a_process)
        self.assertIsNone(component.monitor_thread)

    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.stop_component')
    @patch('logging.Logger.warning')
    def test_stop_component_joins_thread(self, mock_log_warning, mock_super_stop):
        """Test stop_component attempts to join the monitor thread."""
        component = create_test_component()
        component.a2a_process = None # No process
        # Mock thread instance
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.side_effect = [True, False] # Simulate thread finishing after join is called
        component.monitor_thread = mock_thread

        component.stop_component()

        self.assertTrue(component.stop_monitor.is_set())
        # Assert calls on the mock_thread instance
        mock_thread.join.assert_called_once_with(timeout=5)
        mock_log_warning.assert_not_called() # Thread finished cleanly
        mock_super_stop.assert_called_once()
        self.assertIsNone(component.monitor_thread) # Should be cleared

    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.stop_component')
    @patch('logging.Logger.warning')
    def test_stop_component_thread_join_timeout(self, mock_log_warning, mock_super_stop):
        """Test stop_component logs warning if monitor thread join times out."""
        component = create_test_component()
        component.a2a_process = None # No process
        # Mock thread instance
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True # Simulate thread *not* finishing
        component.monitor_thread = mock_thread

        component.stop_component()

        self.assertTrue(component.stop_monitor.is_set())
        # Assert calls on the mock_thread instance
        mock_thread.join.assert_called_once_with(timeout=5)
        mock_log_warning.assert_called_with("Monitor thread did not exit cleanly.") # Because is_alive is still True
        mock_super_stop.assert_called_once()
        self.assertIsNone(component.monitor_thread) # Should be cleared even if join timed out


    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.stop_component')
    def test_stop_component_no_process_or_thread(self, mock_super_stop):
        """Test stop_component handles no process or thread existing."""
        component = create_test_component()
        component.a2a_process = None
        component.monitor_thread = None

        # Mock Popen.terminate and Thread.join globally to ensure they aren't called
        with patch.object(subprocess.Popen, 'terminate') as mock_terminate, \
             patch.object(threading.Thread, 'join') as mock_join:

            component.stop_component()

            self.assertTrue(component.stop_monitor.is_set())
            # Assert the globally patched methods were NOT called
            mock_terminate.assert_not_called()
            mock_join.assert_not_called()
            mock_super_stop.assert_called_once()

if __name__ == '__main__':
    unittest.main()
