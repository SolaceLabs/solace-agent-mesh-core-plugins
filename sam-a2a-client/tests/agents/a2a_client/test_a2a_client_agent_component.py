import unittest
from unittest.mock import patch, MagicMock, ANY, call
import threading
import subprocess
import time
import os
import platform
import requests # Added import

# Adjust the import path based on how tests are run (e.g., from root)
from src.agents.a2a_client.a2a_client_agent_component import A2AClientAgentComponent, info as component_info
from solace_agent_mesh.common.action_list import ActionList

# Mock A2A types if not directly importable
try:
    from common.client import A2AClient, A2ACardResolver
    from common.types import AgentCard, Authentication, AuthenticationScheme
except ImportError:
    A2AClient = MagicMock()
    A2ACardResolver = MagicMock()
    AgentCard = MagicMock()
    Authentication = MagicMock()
    AuthenticationScheme = MagicMock()
    AuthenticationScheme.BEARER = "bearer" # Define mock value


# Helper to create a component instance with mocked dependencies
def create_test_component(config_overrides=None, mock_cache=True):
    base_config = {
        "agent_name": "test_a2a_agent",
        "a2a_server_url": "http://localhost:10001",
        "a2a_server_command": None, # Default to no command
        "a2a_server_startup_timeout": 10, # Use a shorter timeout for tests unless overridden
        "a2a_server_restart_on_crash": True,
        "a2a_bearer_token": None,
        "input_required_ttl": 300,
        "registration_interval": 60
    }
    if config_overrides:
        base_config.update(config_overrides)

    kwargs = {"cache_service": MagicMock() if mock_cache else None}

    # Mock self.get_config to return values from mock_config
    def mock_get_config(key, default=None):
        return base_config.get(key, default)

    with patch.object(A2AClientAgentComponent, 'get_config', side_effect=mock_get_config), \
         patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.__init__'), \
         patch('src.agents.a2a_client.a2a_client_agent_component.FileService'):
        component = A2AClientAgentComponent(module_info=component_info, **kwargs)
    # Restore original get_config after init if necessary, or keep patched if tests need it
    # For simplicity here, assume tests will mock get_config as needed per test method
    component.get_config = MagicMock(side_effect=mock_get_config) # Re-apply mock for test methods
    return component


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

    # --- Tests for Step 2.1.4 ---

    @patch('src.agents.a2a_client.a2a_client_agent_component.subprocess.Popen')
    @patch('src.agents.a2a_client.a2a_client_agent_component.shlex.split')
    @patch('src.agents.a2a_client.a2a_client_agent_component.os.devnull', '/dev/null') # Mock devnull path
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    def test_launch_process_success(self, mock_open, mock_shlex_split, mock_popen):
        """Test _launch_a2a_process successfully starts a process."""
        command = "my_agent --port 1234"
        component = create_test_component({"a2a_server_command": command})
        mock_shlex_split.return_value = ["my_agent", "--port", "1234"]
        # Remove spec=subprocess.Popen
        mock_process = MagicMock()
        mock_process.pid = 9999
        mock_popen.return_value = mock_process

        component._launch_a2a_process()

        mock_shlex_split.assert_called_once_with(command)
        popen_kwargs = {'stdout': ANY, 'stderr': ANY}
        if platform.system() == "Windows":
            popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs['start_new_session'] = True
        mock_popen.assert_called_once_with(["my_agent", "--port", "1234"], **popen_kwargs)
        mock_open.assert_called_once_with('/dev/null', 'w') # Check devnull was opened
        self.assertEqual(component.a2a_process, mock_process)

    @patch('src.agents.a2a_client.a2a_client_agent_component.subprocess.Popen')
    @patch('logging.Logger.warning')
    def test_launch_process_no_command(self, mock_log_warning, mock_popen):
        """Test _launch_a2a_process does nothing if command is not set."""
        component = create_test_component({"a2a_server_command": None})
        component._launch_a2a_process()
        mock_popen.assert_not_called()
        mock_log_warning.assert_called_with("No 'a2a_server_command' configured, cannot launch process.")

    @patch('src.agents.a2a_client.a2a_client_agent_component.subprocess.Popen')
    @patch('logging.Logger.warning')
    def test_launch_process_already_running(self, mock_log_warning, mock_popen):
        """Test _launch_a2a_process does nothing if process is already running."""
        component = create_test_component({"a2a_server_command": "run.sh"})
        # Remove spec=subprocess.Popen
        mock_existing_process = MagicMock()
        mock_existing_process.poll.return_value = None # Indicates running
        mock_existing_process.pid = 1234
        component.a2a_process = mock_existing_process

        component._launch_a2a_process()

        mock_popen.assert_not_called()
        mock_log_warning.assert_called_with("A2A process (PID: 1234) seems to be already running.")

    @patch('src.agents.a2a_client.a2a_client_agent_component.subprocess.Popen', side_effect=FileNotFoundError("Command not found"))
    @patch('src.agents.a2a_client.a2a_client_agent_component.shlex.split')
    @patch('logging.Logger.error')
    def test_launch_process_file_not_found(self, mock_log_error, mock_shlex_split, mock_popen):
        """Test _launch_a2a_process handles FileNotFoundError."""
        command = "non_existent_command"
        component = create_test_component({"a2a_server_command": command})
        mock_shlex_split.return_value = ["non_existent_command"]

        with self.assertRaises(FileNotFoundError):
            component._launch_a2a_process()

        self.assertIsNone(component.a2a_process)
        mock_log_error.assert_called_once()
        self.assertIn("Command not found: non_existent_command", mock_log_error.call_args[0][0])

    @patch('src.agents.a2a_client.a2a_client_agent_component.subprocess.Popen', side_effect=Exception("Other Popen error"))
    @patch('src.agents.a2a_client.a2a_client_agent_component.shlex.split')
    @patch('logging.Logger.error')
    def test_launch_process_other_exception(self, mock_log_error, mock_shlex_split, mock_popen):
        """Test _launch_a2a_process handles other Popen exceptions."""
        command = "some_command"
        component = create_test_component({"a2a_server_command": command})
        mock_shlex_split.return_value = ["some_command"]

        with self.assertRaises(Exception):
            component._launch_a2a_process()

        self.assertIsNone(component.a2a_process)
        mock_log_error.assert_called_once()
        self.assertIn("Failed to launch A2A agent process", mock_log_error.call_args[0][0])

    @patch('src.agents.a2a_client.a2a_client_agent_component.time.sleep', return_value=None) # Avoid actual sleep
    @patch.object(threading.Event, 'wait') # Mock wait on the Event object
    def test_monitor_process_clean_exit(self, mock_event_wait, mock_sleep):
        """Test _monitor_a2a_process exits loop on clean process termination."""
        component = create_test_component()
        # Remove spec=subprocess.Popen
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

    @patch('src.agents.a2a_client.a2a_client_agent_component.time.sleep', return_value=None)
    @patch.object(threading.Event, 'wait')
    @patch('logging.Logger.error')
    def test_monitor_process_crash_no_restart(self, mock_log_error, mock_event_wait, mock_sleep):
        """Test _monitor_a2a_process logs error and exits if restart is disabled."""
        component = create_test_component({"a2a_server_restart_on_crash": False})
        # Remove spec=subprocess.Popen
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
        mock_event_wait.assert_called_once()

    @patch('src.agents.a2a_client.a2a_client_agent_component.time.sleep', return_value=None)
    @patch.object(threading.Event, 'wait')
    @patch('logging.Logger.error')
    @patch('logging.Logger.info')
    def test_monitor_process_crash_with_restart(self, mock_log_info, mock_log_error, mock_event_wait, mock_sleep):
        """Test _monitor_a2a_process attempts restart on crash if enabled."""
        component = create_test_component({"a2a_server_restart_on_crash": True})
        # Remove spec=subprocess.Popen
        mock_process1 = MagicMock()
        mock_process1.pid = 1111
        # Simulate process 1 running then crashing
        mock_process1.poll.side_effect = [None, 1]
        component.a2a_process = mock_process1

        # Mock _launch_a2a_process to simulate successful restart
        # Remove spec=subprocess.Popen
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
        # Check restart delay wait call
        self.assertEqual(mock_event_wait.call_args_list[1], call(2))

    @patch('src.agents.a2a_client.a2a_client_agent_component.time.sleep', return_value=None)
    @patch.object(threading.Event, 'wait')
    @patch('logging.Logger.error')
    def test_monitor_process_crash_restart_fail(self, mock_log_error, mock_event_wait, mock_sleep):
        """Test _monitor_a2a_process exits if restart attempt fails."""
        component = create_test_component({"a2a_server_restart_on_crash": True})
        # Remove spec=subprocess.Popen
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
        # Remove spec=subprocess.Popen
        mock_process = MagicMock()
        mock_process.pid = 1234
        mock_process.poll.return_value = None # Still running
        component.a2a_process = mock_process

        component._monitor_a2a_process()

        # Poll should be called once before wait() causes the loop to break
        mock_process.poll.assert_called_once()
        mock_event_wait.assert_called_once_with(timeout=5)

    @patch('logging.Logger.warning')
    def test_monitor_process_no_process(self, mock_log_warning):
        """Test _monitor_a2a_process exits if there's no process initially."""
        component = create_test_component()
        component.a2a_process = None # Explicitly set to None

        component._monitor_a2a_process()

        mock_log_warning.assert_called_with("Monitor thread: No A2A process to monitor. Exiting.")

    # Remove unnecessary method patches
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
        self.assertEqual(mock_thread.is_alive.call_count, 2) # Check that is_alive was called twice
        mock_thread.join.assert_called_once_with(timeout=5)
        mock_super_stop.assert_called_once()
        self.assertIsNone(component.a2a_process) # Should be cleared
        self.assertIsNone(component.monitor_thread) # Should be cleared

    # Remove unnecessary method patches
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
        self.assertEqual(mock_thread.is_alive.call_count, 2) # Check that is_alive was called twice
        mock_thread.join.assert_called_once_with(timeout=5)
        mock_super_stop.assert_called_once()
        self.assertIsNone(component.a2a_process)
        self.assertIsNone(component.monitor_thread)

    # Remove unnecessary method patches
    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.stop_component')
    @patch('logging.Logger.warning')
    def test_stop_component_joins_thread(self, mock_log_warning, mock_super_stop):
        """Test stop_component attempts to join the monitor thread."""
        component = create_test_component()
        component.a2a_process = None # No process
        # Mock thread instance
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True # Simulate thread not finishing
        component.monitor_thread = mock_thread

        component.stop_component()

        self.assertTrue(component.stop_monitor.is_set())
        # Assert calls on the mock_thread instance
        mock_thread.join.assert_called_once_with(timeout=5)
        mock_log_warning.assert_called_with("Monitor thread did not exit cleanly.") # Because is_alive is True
        mock_super_stop.assert_called_once()
        self.assertIsNone(component.monitor_thread) # Should be cleared even if join timed out

    @patch.object(subprocess.Popen, 'terminate') # Keep this one if needed for other tests, but not strictly for this one
    @patch.object(threading.Thread, 'join') # Keep this one if needed for other tests, but not strictly for this one
    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.stop_component')
    def test_stop_component_no_process_or_thread(self, mock_super_stop, mock_join, mock_terminate):
        """Test stop_component handles no process or thread existing."""
        component = create_test_component()
        component.a2a_process = None
        component.monitor_thread = None

        component.stop_component()

        self.assertTrue(component.stop_monitor.is_set())
        # Assert the globally patched methods were NOT called
        mock_terminate.assert_not_called()
        mock_join.assert_not_called()
        mock_super_stop.assert_called_once()

    # --- Tests for Step 2.2.2 ---

    @patch('src.agents.a2a_client.a2a_client_agent_component.requests.get')
    @patch.object(threading.Event, 'wait', return_value=False) # Simulate wait timeout
    def test_wait_for_agent_ready_success_immediate(self, mock_event_wait, mock_requests_get):
        """Test _wait_for_agent_ready succeeds on the first try."""
        component = create_test_component({"a2a_server_startup_timeout": 5})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests_get.return_value = mock_response

        result = component._wait_for_agent_ready()

        self.assertTrue(result)
        mock_requests_get.assert_called_once_with(
            "http://localhost:10001/.well-known/agent.json",
            timeout=5
        )
        mock_event_wait.assert_not_called() # Should succeed before waiting

    @patch('src.agents.a2a_client.a2a_client_agent_component.requests.get')
    @patch.object(threading.Event, 'wait', return_value=False)
    def test_wait_for_agent_ready_success_retry(self, mock_event_wait, mock_requests_get):
        """Test _wait_for_agent_ready succeeds after a few retries."""
        component = create_test_component({"a2a_server_startup_timeout": 5})
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 503
        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_requests_get.side_effect = [mock_response_fail, mock_response_fail, mock_response_success]

        result = component._wait_for_agent_ready()

        self.assertTrue(result)
        self.assertEqual(mock_requests_get.call_count, 3)
        self.assertEqual(mock_event_wait.call_count, 2) # Wait called twice before success
        mock_event_wait.assert_called_with(timeout=1) # Check last wait timeout

    @patch('src.agents.a2a_client.a2a_client_agent_component.requests.get')
    @patch.object(threading.Event, 'wait', return_value=False)
    @patch('src.agents.a2a_client.a2a_client_agent_component.time.time') # Mock time
    def test_wait_for_agent_ready_timeout(self, mock_time, mock_event_wait, mock_requests_get):
        """Test _wait_for_agent_ready returns False on timeout."""
        timeout = 3 # seconds for test
        component = create_test_component({"a2a_server_startup_timeout": timeout})
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 503
        mock_requests_get.return_value = mock_response_fail

        # Simulate time passing to exceed timeout
        start_time = 1000.0 # Use a fixed start time for easier calculation
        # Time sequence: deadline check, loop1 check, loop2 check, loop3 check (fails), log time
        mock_time.side_effect = [start_time, start_time + 0.1, start_time + 1.2, start_time + 2.3, start_time + 3.4, start_time + 3.5]

        result = component._wait_for_agent_ready()

        self.assertFalse(result)
        # FIX: Loop terminates before 3rd call
        self.assertEqual(mock_requests_get.call_count, 3) # Should try 3 times
        self.assertEqual(mock_event_wait.call_count, 3) # Wait after each failed attempt

    @patch('src.agents.a2a_client.a2a_client_agent_component.requests.get', side_effect=requests.exceptions.ConnectionError("Connection failed"))
    @patch.object(threading.Event, 'wait', return_value=False)
    @patch('src.agents.a2a_client.a2a_client_agent_component.time.time')
    def test_wait_for_agent_ready_connection_error(self, mock_time, mock_event_wait, mock_requests_get):
        """Test _wait_for_agent_ready handles ConnectionError and times out."""
        timeout = 2
        component = create_test_component({"a2a_server_startup_timeout": timeout})
        start_time = 1000.0
        # Time sequence: deadline check, loop1 check, loop2 check (fails), log time
        mock_time.side_effect = [start_time, start_time + 0.1, start_time + 1.2, start_time + 2.3, start_time + 2.4]

        result = component._wait_for_agent_ready()

        self.assertFalse(result)
        # FIX: Loop terminates before 2nd call
        self.assertEqual(mock_requests_get.call_count, 2)
        self.assertEqual(mock_event_wait.call_count, 2) # Wait after each failed attempt

    # Test removed as requested

    @patch('src.agents.a2a_client.a2a_client_agent_component.requests.get')
    @patch.object(threading.Event, 'wait', return_value=True) # Simulate stop event set during wait
    def test_wait_for_agent_ready_stop_event(self, mock_event_wait, mock_requests_get):
        """Test _wait_for_agent_ready returns False immediately if stop event is set."""
        component = create_test_component({"a2a_server_startup_timeout": 10})
        # Simulate request failing once before wait detects stop
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 503
        mock_requests_get.return_value = mock_response_fail

        result = component._wait_for_agent_ready()

        self.assertFalse(result)
        # FIX: Request IS called once before wait detects stop
        mock_requests_get.assert_called_once()
        mock_event_wait.assert_called_once_with(timeout=1) # wait is called after the first failed request

    # --- Tests for Step 2.3.3 ---

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._launch_a2a_process')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClient')
    @patch('src.agents.a2a_client.a2a_client_agent_component.threading.Thread')
    def test_initialize_connection_launch_mode_success(self, mock_thread_cls, mock_a2a_client_cls, mock_resolver_cls, mock_wait_ready, mock_launch):
        """Test successful initialization in launch mode."""
        component = create_test_component({
            "a2a_server_command": "run_agent",
            "a2a_server_restart_on_crash": True
        })
        mock_card = MagicMock(spec=AgentCard)
        mock_card.name = "Launched Agent"
        mock_card.authentication = None # No auth
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.return_value = mock_card
        mock_client_instance = mock_a2a_client_cls.return_value

        component._initialize_a2a_connection()

        mock_launch.assert_called_once()
        mock_wait_ready.assert_called_once()
        mock_resolver_cls.assert_called_once_with(component.a2a_server_url)
        mock_resolver_instance.get_agent_card.assert_called_once()
        mock_a2a_client_cls.assert_called_once_with(agent_card=mock_card, auth_token=None)
        mock_thread_cls.assert_called_once_with(target=component._monitor_a2a_process, daemon=True)
        mock_thread_cls.return_value.start.assert_called_once() # Check monitor thread started

        self.assertEqual(component.agent_card, mock_card)
        self.assertEqual(component.a2a_client, mock_client_instance)
        self.assertIsNotNone(component.monitor_thread)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._launch_a2a_process')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClient')
    @patch('src.agents.a2a_client.a2a_client_agent_component.threading.Thread')
    def test_initialize_connection_connect_mode_success(self, mock_thread_cls, mock_a2a_client_cls, mock_resolver_cls, mock_wait_ready, mock_launch):
        """Test successful initialization in connect mode."""
        component = create_test_component({"a2a_server_command": None}) # No command
        mock_card = MagicMock(spec=AgentCard)
        mock_card.name = "Existing Agent"
        mock_card.authentication = None
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.return_value = mock_card
        mock_client_instance = mock_a2a_client_cls.return_value

        component._initialize_a2a_connection()

        mock_launch.assert_not_called()
        mock_wait_ready.assert_called_once() # Still checks readiness
        mock_resolver_cls.assert_called_once_with(component.a2a_server_url)
        mock_resolver_instance.get_agent_card.assert_called_once()
        mock_a2a_client_cls.assert_called_once_with(agent_card=mock_card, auth_token=None)
        mock_thread_cls.assert_not_called() # No monitor thread in connect mode

        self.assertEqual(component.agent_card, mock_card)
        self.assertEqual(component.a2a_client, mock_client_instance)
        self.assertIsNone(component.monitor_thread)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._launch_a2a_process', side_effect=FileNotFoundError("cmd not found"))
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent.stop_component') # Mock stop to prevent side effects
    def test_initialize_connection_launch_fail(self, mock_stop, mock_launch):
        """Test initialization fails if process launch fails."""
        component = create_test_component({"a2a_server_command": "bad_cmd"})

        with self.assertRaises(FileNotFoundError):
            component._initialize_a2a_connection()

        mock_launch.assert_called_once()
        mock_stop.assert_called_once() # Ensure cleanup is called
        self.assertIsNone(component.agent_card)
        self.assertIsNone(component.a2a_client)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._launch_a2a_process')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=False) # Simulate timeout
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent.stop_component')
    def test_initialize_connection_readiness_timeout(self, mock_stop, mock_wait_ready, mock_launch):
        """Test initialization fails if agent readiness check times out."""
        component = create_test_component({"a2a_server_command": "run_agent"})

        with self.assertRaises(TimeoutError):
            component._initialize_a2a_connection()

        mock_launch.assert_called_once()
        mock_wait_ready.assert_called_once()
        mock_stop.assert_called_once()
        self.assertIsNone(component.agent_card)
        self.assertIsNone(component.a2a_client)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent.stop_component')
    def test_initialize_connection_card_fetch_fail(self, mock_stop, mock_resolver_cls, mock_wait_ready):
        """Test initialization fails if Agent Card fetch fails."""
        component = create_test_component() # Connect mode
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.side_effect = ValueError("Fetch failed")

        with self.assertRaises(ValueError) as cm:
            component._initialize_a2a_connection()

        self.assertIn("Failed to get Agent Card", str(cm.exception))
        mock_wait_ready.assert_called_once()
        mock_resolver_instance.get_agent_card.assert_called_once()
        mock_stop.assert_called_once()
        self.assertIsNone(component.agent_card)
        self.assertIsNone(component.a2a_client)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClient', side_effect=Exception("Client init error")) # Mock A2AClient constructor failure
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent.stop_component')
    def test_initialize_connection_client_init_fail(self, mock_stop, mock_a2a_client_cls, mock_resolver_cls, mock_wait_ready):
        """Test initialization fails if A2AClient initialization fails."""
        component = create_test_component()
        mock_card = MagicMock(spec=AgentCard)
        mock_card.authentication = None
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.return_value = mock_card

        with self.assertRaises(ValueError) as cm:
            component._initialize_a2a_connection()

        self.assertIn("Could not initialize A2AClient", str(cm.exception))
        mock_wait_ready.assert_called_once()
        mock_resolver_instance.get_agent_card.assert_called_once()
        mock_a2a_client_cls.assert_called_once() # Constructor was called
        mock_stop.assert_called_once()
        self.assertEqual(component.agent_card, mock_card) # Card was fetched
        self.assertIsNone(component.a2a_client) # But client init failed

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClient')
    def test_initialize_connection_bearer_auth_success(self, mock_a2a_client_cls, mock_resolver_cls, mock_wait_ready):
        """Test initialization with bearer token required and provided."""
        token = "my-secret-token"
        component = create_test_component({"a2a_bearer_token": token})
        mock_card = MagicMock(spec=AgentCard)
        mock_card.name = "Auth Agent"
        # Simulate AgentCard requiring bearer token
        mock_auth = MagicMock(spec=Authentication)
        mock_auth.schemes = [AuthenticationScheme.BEARER]
        mock_card.authentication = mock_auth
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.return_value = mock_card

        component._initialize_a2a_connection()

        mock_wait_ready.assert_called_once()
        mock_resolver_instance.get_agent_card.assert_called_once()
        # Verify A2AClient was called with the token
        mock_a2a_client_cls.assert_called_once_with(agent_card=mock_card, auth_token=token)
        self.assertIsNotNone(component.a2a_client)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClient')
    @patch('logging.Logger.warning')
    def test_initialize_connection_bearer_auth_missing(self, mock_log_warning, mock_a2a_client_cls, mock_resolver_cls, mock_wait_ready):
        """Test initialization logs warning if bearer token required but not provided."""
        component = create_test_component({"a2a_bearer_token": None}) # No token configured
        mock_card = MagicMock(spec=AgentCard)
        mock_card.name = "Auth Agent Missing Token"
        # Simulate AgentCard requiring bearer token
        mock_auth = MagicMock(spec=Authentication)
        mock_auth.schemes = [AuthenticationScheme.BEARER]
        mock_card.authentication = mock_auth
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.return_value = mock_card

        component._initialize_a2a_connection()

        mock_wait_ready.assert_called_once()
        mock_resolver_instance.get_agent_card.assert_called_once()
        # Verify warning was logged
        mock_log_warning.assert_called_with(
            "A2A Agent Card requires Bearer token, but none configured ('a2a_bearer_token'). Proceeding without authentication."
        )
        # Verify A2AClient was still called, but without the token
        mock_a2a_client_cls.assert_called_once_with(agent_card=mock_card, auth_token=None)
        self.assertIsNotNone(component.a2a_client)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClient')
    @patch('logging.Logger.warning')
    def test_initialize_connection_bearer_auth_not_required(self, mock_log_warning, mock_a2a_client_cls, mock_resolver_cls, mock_wait_ready):
        """Test initialization proceeds normally if bearer token not required."""
        token = "my-secret-token"
        # Token is configured but card doesn't require it
        component = create_test_component({"a2a_bearer_token": token})
        mock_card = MagicMock(spec=AgentCard)
        mock_card.name = "No Auth Agent"
        mock_card.authentication = None # No auth required
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.return_value = mock_card

        component._initialize_a2a_connection()

        mock_wait_ready.assert_called_once()
        mock_resolver_instance.get_agent_card.assert_called_once()
        mock_log_warning.assert_not_called() # No warning about missing token
        # Verify A2AClient was called without the token (as it wasn't required)
        mock_a2a_client_cls.assert_called_once_with(agent_card=mock_card, auth_token=None)
        self.assertIsNotNone(component.a2a_client)

    # --- Test for Step 2.3.2 (Run calls initialize) ---

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._initialize_a2a_connection')
    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.run') # Mock super().run()
    def test_run_calls_initialize_and_super(self, mock_super_run, mock_initialize):
        """Test the run method calls _initialize_a2a_connection and super().run()."""
        component = create_test_component()
        component.run()

        mock_initialize.assert_called_once()
        mock_super_run.assert_called_once()
        self.assertTrue(component._initialized.is_set()) # Check event is set on success

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._initialize_a2a_connection', side_effect=ValueError("Init failed"))
    @patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.run')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent.stop_component')
    @patch('logging.Logger.critical')
    def test_run_handles_initialization_failure(self, mock_log_critical, mock_stop, mock_super_run, mock_initialize):
        """Test run handles exceptions during initialization."""
        component = create_test_component()
        component.run()

        mock_initialize.assert_called_once()
        mock_log_critical.assert_called_once() # Check critical error logged
        self.assertIn("Initialization failed", mock_log_critical.call_args[0][0])
        mock_stop.assert_called_once() # Ensure cleanup called
        mock_super_run.assert_not_called() # Base run should not be called
        self.assertFalse(component._initialized.is_set()) # Event should not be set


if __name__ == '__main__':
    unittest.main()
