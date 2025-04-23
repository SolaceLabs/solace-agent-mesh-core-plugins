import unittest
from unittest.mock import patch, MagicMock, call
import threading
import time

# Adjust the import path based on how tests are run (e.g., from root)
from src.agents.a2a_client.a2a_process_manager import A2AProcessManager
from solace_ai_connector.common.log import log # Import the log object

class TestA2AClientAgentComponentProcessMonitor(unittest.TestCase):

    def setUp(self):
        self.agent_name = "monitor_test_agent"
        self.stop_event = threading.Event()
        self.mock_process = MagicMock()
        self.mock_process.pid = 12345
        self.mock_process.poll.return_value = None # Default: process running

        # Patch time.sleep to avoid actual sleeping in tests
        self.patcher_sleep = patch('time.sleep', return_value=None)
        self.mock_sleep = self.patcher_sleep.start()

        # Patch the logger where it's used in the module
        self.patcher_log_info = patch('src.agents.a2a_client.a2a_process_manager.log.info')
        self.patcher_log_warning = patch('src.agents.a2a_client.a2a_process_manager.log.warning')
        self.patcher_log_error = patch('src.agents.a2a_client.a2a_process_manager.log.error')
        self.mock_log_info = self.patcher_log_info.start()
        self.mock_log_warning = self.patcher_log_warning.start()
        self.mock_log_error = self.patcher_log_error.start()

        # Patch the launch method within the ProcessManager instance for restart tests
        self.patcher_launch = patch.object(A2AProcessManager, 'launch')
        self.mock_launch = self.patcher_launch.start()

    def tearDown(self):
        self.patcher_sleep.stop()
        self.patcher_log_info.stop()
        self.patcher_log_warning.stop()
        self.patcher_log_error.stop()
        self.patcher_launch.stop()
        self.stop_event.clear() # Reset event for next test

    def test_monitor_loop_process_runs_exits_on_stop(self):
        """Test monitor loop runs while process is alive and exits on stop_event."""
        process_manager = A2AProcessManager("cmd", True, self.agent_name, self.stop_event)
        process_manager.process = self.mock_process

        # Simulate poll returning None twice, then stop_event being set
        poll_count = 0
        def poll_side_effect(*args, **kwargs):
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 3:
                self.stop_event.set() # Signal stop after 2 checks
            return None # Process running

        self.mock_process.poll.side_effect = poll_side_effect

        # Run the loop directly
        process_manager._monitor_loop()

        self.assertEqual(self.mock_process.poll.call_count, 3)
        self.mock_log_info.assert_any_call("Monitor thread running for '%s'.", self.agent_name)
        self.mock_log_info.assert_any_call("Stopping monitor thread for A2A process '%s'.", self.agent_name)
        self.mock_launch.assert_not_called() # No restarts

    def test_monitor_loop_process_crashes_restart_success(self):
        """Test monitor restarts process successfully on crash."""
        process_manager = A2AProcessManager("cmd", True, self.agent_name, self.stop_event)
        process_manager.process = self.mock_process

        # Simulate crash on first poll, then running after restart
        new_mock_process = MagicMock(pid=54321)
        new_mock_process.poll.return_value = None # New process is running

        poll_count = 0
        def poll_side_effect(*args, **kwargs):
            nonlocal poll_count
            poll_count += 1
            if poll_count == 1:
                return 1 # Crash
            elif poll_count == 2:
                # After restart, check the new process
                self.assertEqual(process_manager.process, new_mock_process)
                return None # Running
            else:
                self.stop_event.set() # Stop after successful restart check
                return None

        self.mock_process.poll.side_effect = poll_side_effect

        # Mock launch to simulate successful restart
        def launch_side_effect(*args, **kwargs):
            process_manager.process = new_mock_process # Assign the new mock process

        self.mock_launch.side_effect = launch_side_effect

        # Run the loop
        process_manager._monitor_loop()

        self.assertEqual(self.mock_process.poll.call_count, 1) # Original process polled once
        self.assertEqual(new_mock_process.poll.call_count, 2) # New process polled twice
        self.mock_log_error.assert_any_call(
            "Managed A2A process (PID: %d) for '%s' terminated with code %d.",
            12345, self.agent_name, 1
        )
        self.mock_log_info.assert_any_call(
            "Attempting restart %d/%d for '%s' in %ds...",
            1, 5, self.agent_name, 2 # Check restart attempt log
        )
        self.mock_launch.assert_called_once() # Launch was called
        self.mock_log_info.assert_any_call(
            "A2A process for '%s' restarted successfully (New PID: %d).",
            self.agent_name, 54321 # Check successful restart log
        )
        self.mock_log_info.assert_any_call("Stopping monitor thread for A2A process '%s'.", self.agent_name)

    def test_monitor_loop_process_crashes_restart_fails(self):
        """Test monitor stops if restart attempt fails."""
        process_manager = A2AProcessManager("cmd", True, self.agent_name, self.stop_event)
        process_manager.process = self.mock_process

        # Simulate crash
        self.mock_process.poll.return_value = 1

        # Mock launch to simulate failure (sets process to None)
        def launch_side_effect_fail(*args, **kwargs):
            process_manager.process = None

        self.mock_launch.side_effect = launch_side_effect_fail

        # Run the loop
        process_manager._monitor_loop()

        self.mock_process.poll.assert_called_once()
        self.mock_log_error.assert_any_call(
            "Managed A2A process (PID: %d) for '%s' terminated with code %d.",
            12345, self.agent_name, 1
        )
        self.mock_log_info.assert_any_call(
            "Attempting restart %d/%d for '%s' in %ds...",
            1, 5, self.agent_name, 2
        )
        self.mock_launch.assert_called_once()
        self.mock_log_error.assert_any_call(
            "Failed to restart A2A process for '%s' (launch returned no process). Stopping monitor.",
            self.agent_name
        )
        self.mock_log_info.assert_any_call("Stopping monitor thread for A2A process '%s'.", self.agent_name)

    def test_monitor_loop_process_crashes_restart_disabled(self):
        """Test monitor exits without restarting if restart_on_crash is False."""
        process_manager = A2AProcessManager("cmd", False, self.agent_name, self.stop_event) # Restart disabled
        process_manager.process = self.mock_process

        # Simulate crash
        self.mock_process.poll.return_value = 1

        # Run the loop
        process_manager._monitor_loop()

        self.mock_process.poll.assert_called_once()
        self.mock_log_error.assert_any_call(
            "Managed A2A process (PID: %d) for '%s' terminated with code %d.",
            12345, self.agent_name, 1
        )
        self.mock_launch.assert_not_called() # Restart NOT attempted
        self.mock_log_info.assert_any_call(
            "Monitor loop for '%s' exiting as process terminated and restart is not applicable.",
            self.agent_name
        )
        self.mock_log_info.assert_any_call("Stopping monitor thread for A2A process '%s'.", self.agent_name)

    def test_monitor_loop_process_exits_cleanly(self):
        """Test monitor exits without restarting if process exits with code 0."""
        process_manager = A2AProcessManager("cmd", True, self.agent_name, self.stop_event) # Restart enabled
        process_manager.process = self.mock_process

        # Simulate clean exit
        self.mock_process.poll.return_value = 0

        # Run the loop
        process_manager._monitor_loop()

        self.mock_process.poll.assert_called_once()
        self.mock_log_info.assert_any_call(
            "Managed A2A process (PID: %d) for '%s' terminated with code %d.",
            12345, self.agent_name, 0 # Check code 0 logged as info
        )
        self.mock_launch.assert_not_called() # Restart NOT attempted
        self.mock_log_info.assert_any_call(
            "Monitor loop for '%s' exiting as process terminated and restart is not applicable.",
            self.agent_name
        )
        self.mock_log_info.assert_any_call("Stopping monitor thread for A2A process '%s'.", self.agent_name)

    def test_monitor_loop_max_restarts_exceeded(self):
        """Test monitor stops after exceeding max restart attempts."""
        process_manager = A2AProcessManager("cmd", True, self.agent_name, self.stop_event)
        process_manager.process = self.mock_process
        max_restarts = 5 # Default in implementation

        # Simulate repeated crashes
        self.mock_process.poll.return_value = 1

        # Mock launch to simulate *persistent* failure (process remains None or keeps crashing)
        # For simplicity, let launch do nothing, so self.process stays as the crashed one
        self.mock_launch.side_effect = lambda *args, **kwargs: None

        # Run the loop
        process_manager._monitor_loop()

        # Poll called once initially, then once per restart attempt
        self.assertEqual(self.mock_process.poll.call_count, max_restarts + 1)
        self.assertEqual(self.mock_launch.call_count, max_restarts) # Called 5 times
        self.mock_log_error.assert_any_call(
            "Exceeded maximum restart attempts (%d) for '%s'. Stopping monitor.",
            max_restarts, self.agent_name
        )
        self.mock_log_info.assert_any_call("Stopping monitor thread for A2A process '%s'.", self.agent_name)

    @patch.object(threading.Event, 'wait')
    def test_monitor_loop_stop_during_restart_delay(self, mock_event_wait):
        """Test monitor aborts restart if stop_event is set during delay."""
        process_manager = A2AProcessManager("cmd", True, self.agent_name, self.stop_event)
        process_manager.process = self.mock_process

        # Simulate crash
        self.mock_process.poll.return_value = 1
        # Simulate stop_event.wait returning True (event was set)
        mock_event_wait.return_value = True

        # Run the loop
        process_manager._monitor_loop()

        self.mock_process.poll.assert_called_once()
        self.mock_log_error.assert_any_call(
            "Managed A2A process (PID: %d) for '%s' terminated with code %d.",
            12345, self.agent_name, 1
        )
        self.mock_log_info.assert_any_call(
            "Attempting restart %d/%d for '%s' in %ds...",
            1, 5, self.agent_name, 2
        )
        mock_event_wait.assert_called_once_with(timeout=2) # Check wait was called
        self.mock_log_info.assert_any_call(
            "Stop signal received during restart delay for '%s'. Aborting restart.",
            self.agent_name
        )
        self.mock_launch.assert_not_called() # Restart aborted
        self.mock_log_info.assert_any_call("Stopping monitor thread for A2A process '%s'.", self.agent_name)

    def test_monitor_loop_poll_error(self):
        """Test monitor stops if process.poll() raises an exception."""
        process_manager = A2AProcessManager("cmd", True, self.agent_name, self.stop_event)
        process_manager.process = self.mock_process

        # Simulate poll raising error
        poll_error = OSError("Poll failed")
        self.mock_process.poll.side_effect = poll_error

        # Run the loop
        process_manager._monitor_loop()

        self.mock_process.poll.assert_called_once()
        self.mock_log_error.assert_any_call(
            "Error polling A2A process for '%s': %s. Stopping monitor.",
            self.agent_name, poll_error, exc_info=True
        )
        self.mock_launch.assert_not_called()
        self.mock_log_info.assert_any_call("Stopping monitor thread for A2A process '%s'.", self.agent_name)

if __name__ == '__main__':
    unittest.main()
