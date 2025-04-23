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
        # We still need sleep for the restart delay simulation, but not for the main wait
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

        # Patch threading.Event.wait globally for most tests to speed them up,
        # but individual tests can override or remove this patch.
        self.patcher_event_wait = patch.object(threading.Event, 'wait', return_value=False)
        self.mock_event_wait_global = self.patcher_event_wait.start()


    def tearDown(self):
        self.patcher_sleep.stop()
        self.patcher_log_info.stop()
        self.patcher_log_warning.stop()
        self.patcher_log_error.stop()
        self.patcher_launch.stop()
        # Ensure the global patch is stopped if it was running
        try:
            self.patcher_event_wait.stop()
        except RuntimeError: # Catch error if already stopped
            pass
        self.stop_event.clear() # Reset event for next test

    # --- Test that previously ran forever ---
    # Remove the specific patch for threading.Event.wait for this test
    # It relies on the while loop condition checking stop_event.is_set()
    def test_monitor_loop_process_runs_exits_on_stop(self):
        """Test monitor loop runs while process is alive and exits on stop_event."""
        # Stop the global patch for this specific test
        self.patcher_event_wait.stop()

        # Corrected A2AProcessManager instantiation
        process_manager = A2AProcessManager(
            command="cmd",
            working_dir=None,
            env_file=None,
            restart_on_crash=True,
            agent_name=self.agent_name,
            stop_event=self.stop_event
        )
        process_manager.process = self.mock_process

        # Simulate poll returning None twice, then stop_event being set during the third poll call
        poll_count = 0
        def poll_side_effect(*args, **kwargs):
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 3:
                self.stop_event.set() # Signal stop during the 3rd poll check
            return None # Process running

        self.mock_process.poll.side_effect = poll_side_effect

        # Run the loop directly
        process_manager._monitor_loop()

        # The loop condition `while not self.stop_event.is_set()` is checked *before* poll()
        # Iteration 1: is_set()=False, poll() -> None, wait() (not mocked here, will timeout quickly)
        # Iteration 2: is_set()=False, poll() -> None, wait()
        # Iteration 3: is_set()=False, poll() sets event to True, returns None, wait()
        # Iteration 4: is_set()=True -> loop terminates
        self.assertEqual(self.mock_process.poll.call_count, 3)
        self.mock_log_info.assert_any_call("Monitor thread running for '%s'.", self.agent_name)
        # The "Stop signal received..." log might not happen if the loop exits purely on the while condition
        self.mock_log_info.assert_any_call("Stopping monitor thread for A2A process '%s'.", self.agent_name)
        self.mock_launch.assert_not_called() # No restarts

        # Restart the global patch if other tests need it
        self.mock_event_wait_global = self.patcher_event_wait.start()


    # --- Test that was running forever (again) ---
    # Stop the global patch for this specific test to allow real waits
    def test_monitor_loop_process_crashes_restart_success(self):
        """Test monitor restarts process successfully on crash."""
        # Stop the global patch for this specific test
        self.patcher_event_wait.stop()

        # Corrected A2AProcessManager instantiation
        process_manager = A2AProcessManager(
            command="cmd",
            working_dir=None,
            env_file=None,
            restart_on_crash=True,
            agent_name=self.agent_name,
            stop_event=self.stop_event
        )
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
            else: # poll_count >= 3
                self.stop_event.set() # Stop after successful restart check
                return None

        # Determine which process's poll is being called
        def dynamic_poll_side_effect(*args, **kwargs):
            if process_manager.process == self.mock_process:
                # Original process behavior
                return poll_side_effect()
            elif process_manager.process == new_mock_process:
                # New process behavior
                return poll_side_effect()
            else:
                # Should not happen in this test
                return None

        # Assign the dynamic side effect to both mocks initially
        self.mock_process.poll.side_effect = dynamic_poll_side_effect
        new_mock_process.poll.side_effect = dynamic_poll_side_effect


        # Mock launch to simulate successful restart
        def launch_side_effect(*args, **kwargs):
            process_manager.process = new_mock_process # Assign the new mock process

        self.mock_launch.side_effect = launch_side_effect

        # Run the loop
        process_manager._monitor_loop()

        # Expected sequence without wait patch:
        # 1. poll() on mock_process -> 1 (crash)
        # 2. wait(timeout=2) -> False (times out)
        # 3. launch() -> assigns new_mock_process
        # 4. continue
        # 5. poll() on new_mock_process -> None (running)
        # 6. wait(timeout=5) -> False (times out)
        # 7. poll() on new_mock_process -> None (running), sets stop_event
        # 8. wait(timeout=5) -> True (event is set)
        # 9. break

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
        # Check the log message when wait(5) returns True
        self.mock_log_info.assert_any_call(
            "Stop signal received by monitor thread for '%s'.", self.agent_name
        )
        self.mock_log_info.assert_any_call("Stopping monitor thread for A2A process '%s'.", self.agent_name)

        # Restart the global patch if other tests need it
        self.mock_event_wait_global = self.patcher_event_wait.start()


    def test_monitor_loop_process_crashes_restart_fails(self):
        """Test monitor stops if restart attempt fails."""
        # Corrected A2AProcessManager instantiation
        process_manager = A2AProcessManager(
            command="cmd",
            working_dir=None,
            env_file=None,
            restart_on_crash=True,
            agent_name=self.agent_name,
            stop_event=self.stop_event
        )
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
            "Failed to restart A2A process for '%s' (launch resulted in no process). Stopping monitor.",
            self.agent_name
        )
        self.mock_log_info.assert_any_call("Stopping monitor thread for A2A process '%s'.", self.agent_name)

    def test_monitor_loop_process_crashes_restart_disabled(self):
        """Test monitor exits without restarting if restart_on_crash is False."""
        # Corrected A2AProcessManager instantiation
        process_manager = A2AProcessManager(
            command="cmd",
            working_dir=None,
            env_file=None,
            restart_on_crash=False, # Restart disabled
            agent_name=self.agent_name,
            stop_event=self.stop_event
        )
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
        # Corrected A2AProcessManager instantiation
        process_manager = A2AProcessManager(
            command="cmd",
            working_dir=None,
            env_file=None,
            restart_on_crash=True, # Restart enabled
            agent_name=self.agent_name,
            stop_event=self.stop_event
        )
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
        # Corrected A2AProcessManager instantiation
        process_manager = A2AProcessManager(
            command="cmd",
            working_dir=None,
            env_file=None,
            restart_on_crash=True,
            agent_name=self.agent_name,
            stop_event=self.stop_event
        )
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

    # --- Test that was running forever (FIXED) ---
    def test_monitor_loop_stop_during_restart_delay(self):
        """Test monitor aborts restart if stop_event is set during delay."""
        # Stop the global patch for this test
        try:
            self.patcher_event_wait.stop()
        except RuntimeError: pass # Ignore if already stopped

        # Corrected A2AProcessManager instantiation
        process_manager = A2AProcessManager(
            command="cmd",
            working_dir=None,
            env_file=None,
            restart_on_crash=True,
            agent_name=self.agent_name,
            stop_event=self.stop_event
        )
        process_manager.process = self.mock_process

        # Simulate crash
        self.mock_process.poll.return_value = 1

        # Patch the wait method ONLY on the specific event instance used by the manager
        # Make it return True to simulate the event being set during the wait
        with patch.object(process_manager.stop_event, 'wait', return_value=True) as mock_instance_wait:
            # Run the loop
            process_manager._monitor_loop()

            # Assertions
            self.mock_process.poll.assert_called_once() # Poll called once before crash detected
            self.mock_log_error.assert_any_call(
                "Managed A2A process (PID: %d) for '%s' terminated with code %d.",
                12345, self.agent_name, 1
            )
            self.mock_log_info.assert_any_call(
                "Attempting restart %d/%d for '%s' in %ds...",
                1, 5, self.agent_name, 2 # Check restart attempt log
            )
            # Check that the wait method on our specific event instance was called with the restart delay
            mock_instance_wait.assert_called_once_with(timeout=2)
            self.mock_log_info.assert_any_call(
                "Stop signal received during restart delay for '%s'. Aborting restart.",
                self.agent_name # Check log message for aborted restart
            )
            self.mock_launch.assert_not_called() # Restart should NOT have been attempted
            self.mock_log_info.assert_any_call("Stopping monitor thread for A2A process '%s'.", self.agent_name) # Check loop exit log

        # Restart the global patch if needed for other tests
        self.mock_event_wait_global = self.patcher_event_wait.start()


    def test_monitor_loop_poll_error(self):
        """Test monitor stops if process.poll() raises an exception."""
        # Corrected A2AProcessManager instantiation
        process_manager = A2AProcessManager(
            command="cmd",
            working_dir=None,
            env_file=None,
            restart_on_crash=True,
            agent_name=self.agent_name,
            stop_event=self.stop_event
        )
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
