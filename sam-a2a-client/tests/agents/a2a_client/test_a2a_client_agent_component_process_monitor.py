import unittest
from unittest.mock import patch, MagicMock, call
import threading

# Adjust the import path based on how tests are run (e.g., from root)
from .test_helpers import create_test_component # Import helper
# Import the class containing the method under test
from src.agents.a2a_client.a2a_process_manager import A2AProcessManager

class TestA2AClientAgentComponentProcessMonitor(unittest.TestCase):

    # Patch time.sleep where it's used (in a2a_process_manager)
    @patch('src.agents.a2a_client.a2a_process_manager.time.sleep', return_value=None) # Avoid actual sleep
    @patch.object(threading.Event, 'wait') # Mock wait on the Event object
    def test_monitor_process_clean_exit(self, mock_event_wait, mock_sleep):
        """Test _monitor_loop exits loop on clean process termination."""
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command="dummy", restart_on_crash=True, agent_name="test", stop_event=stop_event
        )
        mock_process = MagicMock()
        mock_process.pid = 1234
        # Simulate process running then exiting cleanly
        mock_process.poll.side_effect = [None, None, 0]
        process_manager.process = mock_process
        # Make wait return False so the loop continues until poll() breaks it
        mock_event_wait.side_effect = [False, False]

        process_manager._monitor_loop() # Call the method directly

        self.assertEqual(mock_process.poll.call_count, 3)
        # Ensure wait was called twice (for the sleep interval before termination)
        self.assertEqual(mock_event_wait.call_count, 2)
        mock_event_wait.assert_called_with(timeout=5) # Check last wait timeout

    # Patch time.sleep where it's used
    @patch('src.agents.a2a_client.a2a_process_manager.time.sleep', return_value=None)
    @patch.object(threading.Event, 'wait')
    @patch('logging.Logger.error')
    def test_monitor_process_crash_no_restart(self, mock_log_error, mock_event_wait, mock_sleep):
        """Test _monitor_loop logs error and exits if restart is disabled."""
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command="dummy", restart_on_crash=False, agent_name="test_no_restart", stop_event=stop_event
        )
        mock_process = MagicMock()
        mock_process.pid = 1234
        # Simulate process running then crashing
        mock_process.poll.side_effect = [None, 1]
        process_manager.process = mock_process
        # Mock launch on the instance to ensure it's NOT called
        process_manager.launch = MagicMock()
        # Make wait return False
        mock_event_wait.return_value = False

        process_manager._monitor_loop() # Call the method directly

        self.assertEqual(mock_process.poll.call_count, 2)
        mock_log_error.assert_called_once_with("Managed A2A process (PID: 1234) terminated with code 1.")
        process_manager.launch.assert_not_called()
        # wait should have been called once before the crash was detected
        mock_event_wait.assert_called_once_with(timeout=5)

    # Patch time.sleep where it's used
    @patch('src.agents.a2a_client.a2a_process_manager.time.sleep', return_value=None)
    @patch.object(threading.Event, 'wait')
    @patch('logging.Logger.error')
    @patch('logging.Logger.info')
    def test_monitor_process_crash_with_restart(self, mock_log_info, mock_log_error, mock_event_wait, mock_sleep):
        """Test _monitor_loop attempts restart on crash if enabled."""
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command="dummy", restart_on_crash=True, agent_name="test_restart", stop_event=stop_event
        )
        mock_process1 = MagicMock()
        mock_process1.pid = 1111
        # Simulate process 1 running then crashing
        mock_process1.poll.side_effect = [None, 1]
        process_manager.process = mock_process1

        # Mock launch on the instance to simulate successful restart
        mock_process2 = MagicMock()
        mock_process2.pid = 2222
        # Simulate process 2 running then monitor stopping
        mock_process2.poll.side_effect = [None, None]
        def launch_side_effect():
            process_manager.process = mock_process2 # Simulate setting the new process
        process_manager.launch = MagicMock(side_effect=launch_side_effect)

        # Simulate stop_monitor being set after process 2 runs for a bit
        mock_event_wait.side_effect = [False, False, False, True] # Wait before crash, wait for restart delay, wait after restart, then stop

        process_manager._monitor_loop() # Call the method directly

        self.assertEqual(mock_process1.poll.call_count, 2)
        mock_log_error.assert_called_once_with("Managed A2A process (PID: 1111) terminated with code 1.")
        process_manager.launch.assert_called_once() # Restart called
        self.assertEqual(mock_process2.poll.call_count, 2) # New process polled
        # Check wait calls: initial poll, restart delay, poll new process, stop
        self.assertEqual(mock_event_wait.call_count, 4)
        # Check restart delay wait call (index 1)
        self.assertEqual(mock_event_wait.call_args_list[1], call(2))
        # Check subsequent waits (index 0, 2, 3)
        self.assertEqual(mock_event_wait.call_args_list[0], call(timeout=5))
        self.assertEqual(mock_event_wait.call_args_list[2], call(timeout=5))
        self.assertEqual(mock_event_wait.call_args_list[3], call(timeout=5))


    # Patch time.sleep where it's used
    @patch('src.agents.a2a_client.a2a_process_manager.time.sleep', return_value=None)
    @patch.object(threading.Event, 'wait')
    @patch('logging.Logger.error')
    def test_monitor_process_crash_restart_fail(self, mock_log_error, mock_event_wait, mock_sleep):
        """Test _monitor_loop exits if restart attempt fails."""
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command="dummy", restart_on_crash=True, agent_name="test_restart_fail", stop_event=stop_event
        )
        mock_process = MagicMock()
        mock_process.pid = 1234
        # Simulate process running then crashing
        mock_process.poll.side_effect = [None, 1]
        process_manager.process = mock_process

        # Mock launch on the instance to simulate failure
        process_manager.launch = MagicMock(side_effect=Exception("Launch failed"))

        # Simulate wait before crash and wait for restart delay
        mock_event_wait.side_effect = [False, False, True] # Add True to stop loop eventually

        process_manager._monitor_loop() # Call the method directly

        self.assertEqual(mock_process.poll.call_count, 2)
        # Check error logs: initial crash, restart failure
        self.assertEqual(mock_log_error.call_count, 2)
        self.assertIn("terminated with code 1", mock_log_error.call_args_list[0][0][0])
        self.assertIn("Exception during A2A process restart", mock_log_error.call_args_list[1][0][0])
        process_manager.launch.assert_called_once() # Restart attempted

    # Patch time.sleep where it's used
    @patch('src.agents.a2a_client.a2a_process_manager.time.sleep', return_value=None)
    @patch.object(threading.Event, 'wait', return_value=True) # Simulate stop event being set immediately
    def test_monitor_process_stop_event(self, mock_event_wait, mock_sleep):
        """Test _monitor_loop exits promptly if stop event is set."""
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command="dummy", restart_on_crash=True, agent_name="test_stop", stop_event=stop_event
        )
        mock_process = MagicMock()
        mock_process.pid = 1234
        mock_process.poll.return_value = None # Still running
        process_manager.process = mock_process

        process_manager._monitor_loop() # Call the method directly

        # Poll *is* called once before wait() returns True and breaks the loop
        mock_process.poll.assert_called_once()
        mock_event_wait.assert_called_once_with(timeout=5)

    @patch('logging.Logger.warning')
    def test_monitor_process_no_process(self, mock_log_warning):
        """Test _monitor_loop exits if there's no process initially."""
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command="dummy", restart_on_crash=True, agent_name="test_no_proc", stop_event=stop_event
        )
        process_manager.process = None # Explicitly set to None

        process_manager._monitor_loop() # Call the method directly

        mock_log_warning.assert_called_with("Monitor thread: No A2A process to monitor. Exiting.")

if __name__ == '__main__':
    unittest.main()
