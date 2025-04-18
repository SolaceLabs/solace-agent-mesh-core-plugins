import unittest
from unittest.mock import patch, MagicMock, call
import threading

# Adjust the import path based on how tests are run (e.g., from root)
from .test_helpers import create_test_component # Import helper

class TestA2AClientAgentComponentProcessMonitor(unittest.TestCase):

    @patch('src.agents.a2a_client.a2a_client_agent_component.time.sleep', return_value=None) # Avoid actual sleep
    @patch.object(threading.Event, 'wait') # Mock wait on the Event object
    def test_monitor_process_clean_exit(self, mock_event_wait, mock_sleep):
        """Test _monitor_a2a_process exits loop on clean process termination."""
        component = create_test_component()
        mock_process = MagicMock()
        mock_process.pid = 1234
        # Simulate process running then exiting cleanly
        mock_process.poll.side_effect = [None, None, 0]
        component.a2a_process = mock_process
        # Make wait return False so the loop continues until poll() breaks it
        mock_event_wait.side_effect = [False, False]

        component._monitor_a2a_process()

        self.assertEqual(mock_process.poll.call_count, 3)
        # Ensure wait was called twice (for the sleep interval before termination)
        self.assertEqual(mock_event_wait.call_count, 2)
        mock_event_wait.assert_called_with(timeout=5) # Check last wait timeout

    @patch('src.agents.a2a_client.a2a_client_agent_component.time.sleep', return_value=None)
    @patch.object(threading.Event, 'wait')
    @patch('logging.Logger.error')
    def test_monitor_process_crash_no_restart(self, mock_log_error, mock_event_wait, mock_sleep):
        """Test _monitor_a2a_process logs error and exits if restart is disabled."""
        component = create_test_component({"a2a_server_restart_on_crash": False})
        mock_process = MagicMock()
        mock_process.pid = 1234
        # Simulate process running then crashing
        mock_process.poll.side_effect = [None, 1]
        component.a2a_process = mock_process
        # Mock _launch_a2a_process to ensure it's NOT called
        component._launch_a2a_process = MagicMock()
        # Make wait return False
        mock_event_wait.return_value = False

        component._monitor_a2a_process()

        self.assertEqual(mock_process.poll.call_count, 2)
        mock_log_error.assert_called_once_with("Managed A2A process (PID: 1234) terminated with code 1.")
        component._launch_a2a_process.assert_not_called()
        # wait should have been called once before the crash was detected
        mock_event_wait.assert_called_once_with(timeout=5)

    @patch('src.agents.a2a_client.a2a_client_agent_component.time.sleep', return_value=None)
    @patch.object(threading.Event, 'wait')
    @patch('logging.Logger.error')
    @patch('logging.Logger.info')
    def test_monitor_process_crash_with_restart(self, mock_log_info, mock_log_error, mock_event_wait, mock_sleep):
        """Test _monitor_a2a_process attempts restart on crash if enabled."""
        component = create_test_component({"a2a_server_restart_on_crash": True})
        mock_process1 = MagicMock()
        mock_process1.pid = 1111
        # Simulate process 1 running then crashing
        mock_process1.poll.side_effect = [None, 1]
        component.a2a_process = mock_process1

        # Mock _launch_a2a_process to simulate successful restart
        mock_process2 = MagicMock()
        mock_process2.pid = 2222
        # Simulate process 2 running then monitor stopping
        mock_process2.poll.side_effect = [None, None]
        def launch_side_effect():
            component.a2a_process = mock_process2 # Simulate setting the new process
        component._launch_a2a_process = MagicMock(side_effect=launch_side_effect)

        # Simulate stop_monitor being set after process 2 runs for a bit
        mock_event_wait.side_effect = [False, False, False, True] # Wait before crash, wait for restart delay, wait after restart, then stop

        component._monitor_a2a_process()

        self.assertEqual(mock_process1.poll.call_count, 2)
        mock_log_error.assert_called_once_with("Managed A2A process (PID: 1111) terminated with code 1.")
        component._launch_a2a_process.assert_called_once() # Restart called
        self.assertEqual(mock_process2.poll.call_count, 2) # New process polled
        # Check wait calls: initial poll, restart delay, poll new process, stop
        self.assertEqual(mock_event_wait.call_count, 4)
        # Check restart delay wait call (index 1)
        self.assertEqual(mock_event_wait.call_args_list[1], call(2))
        # Check subsequent waits (index 0, 2, 3)
        self.assertEqual(mock_event_wait.call_args_list[0], call(timeout=5))
        self.assertEqual(mock_event_wait.call_args_list[2], call(timeout=5))
        self.assertEqual(mock_event_wait.call_args_list[3], call(timeout=5))


    @patch('src.agents.a2a_client.a2a_client_agent_component.time.sleep', return_value=None)
    @patch.object(threading.Event, 'wait')
    @patch('logging.Logger.error')
    def test_monitor_process_crash_restart_fail(self, mock_log_error, mock_event_wait, mock_sleep):
        """Test _monitor_a2a_process exits if restart attempt fails."""
        component = create_test_component({"a2a_server_restart_on_crash": True})
        mock_process = MagicMock()
        mock_process.pid = 1234
        # Simulate process running then crashing
        mock_process.poll.side_effect = [None, 1]
        component.a2a_process = mock_process

        # Mock _launch_a2a_process to simulate failure
        component._launch_a2a_process = MagicMock(side_effect=Exception("Launch failed"))

        # Simulate wait before crash and wait for restart delay
        mock_event_wait.side_effect = [False, False, True] # Add True to stop loop eventually

        component._monitor_a2a_process()

        self.assertEqual(mock_process.poll.call_count, 2)
        # Check error logs: initial crash, restart failure
        self.assertEqual(mock_log_error.call_count, 2)
        self.assertIn("terminated with code 1", mock_log_error.call_args_list[0][0][0])
        self.assertIn("Exception during A2A process restart", mock_log_error.call_args_list[1][0][0])
        component._launch_a2a_process.assert_called_once() # Restart attempted

    @patch('src.agents.a2a_client.a2a_client_agent_component.time.sleep', return_value=None)
    @patch.object(threading.Event, 'wait', return_value=True) # Simulate stop event being set immediately
    def test_monitor_process_stop_event(self, mock_event_wait, mock_sleep):
        """Test _monitor_a2a_process exits promptly if stop event is set."""
        component = create_test_component()
        mock_process = MagicMock()
        mock_process.pid = 1234
        mock_process.poll.return_value = None # Still running
        component.a2a_process = mock_process

        component._monitor_a2a_process()

        # Poll should not be called because wait returns True immediately
        mock_process.poll.assert_not_called()
        mock_event_wait.assert_called_once_with(timeout=5)

    @patch('logging.Logger.warning')
    def test_monitor_process_no_process(self, mock_log_warning):
        """Test _monitor_a2a_process exits if there's no process initially."""
        component = create_test_component()
        component.a2a_process = None # Explicitly set to None

        component._monitor_a2a_process()

        mock_log_warning.assert_called_with("Monitor thread: No A2A process to monitor. Exiting.")

if __name__ == '__main__':
    unittest.main()
