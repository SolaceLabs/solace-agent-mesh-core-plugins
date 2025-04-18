import unittest
from unittest.mock import patch, MagicMock, ANY
import subprocess
import platform
import os
import threading # Import threading

# Adjust the import path based on how tests are run (e.g., from root)
from .test_helpers import create_test_component # Import helper
# Import the class we are testing the launch method of
from src.agents.a2a_client.a2a_process_manager import A2AProcessManager

class TestA2AClientAgentComponentProcessLaunch(unittest.TestCase):

    # Patch where the objects are *used* (in a2a_process_manager)
    @patch('src.agents.a2a_client.a2a_process_manager.subprocess.Popen')
    @patch('src.agents.a2a_client.a2a_process_manager.shlex.split')
    @patch('src.agents.a2a_client.a2a_process_manager.os.devnull', '/mock/dev/null') # Mock devnull path
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    def test_launch_process_success(self, mock_open, mock_shlex_split, mock_popen):
        """Test A2AProcessManager.launch successfully starts a process."""
        command = "my_agent --port 1234"
        agent_name = "test_agent"
        stop_event = threading.Event()
        # Instantiate the Process Manager directly
        process_manager = A2AProcessManager(
            command=command,
            restart_on_crash=True,
            agent_name=agent_name,
            stop_event=stop_event
        )

        mock_shlex_split.return_value = ["my_agent", "--port", "1234"]
        mock_process = MagicMock()
        mock_process.pid = 9999
        mock_popen.return_value = mock_process

        # Call the launch method on the process manager instance
        process_manager.launch()

        mock_shlex_split.assert_called_once_with(command)
        popen_kwargs = {'stdout': ANY, 'stderr': ANY}
        if platform.system() == "Windows":
            popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs['start_new_session'] = True
        mock_popen.assert_called_once_with(["my_agent", "--port", "1234"], **popen_kwargs)
        # Check devnull was opened with the mocked path
        mock_open.assert_called_once_with('/mock/dev/null', 'w', encoding='utf-8')
        self.assertEqual(process_manager.process, mock_process)

    # Patch where the objects are *used*
    @patch('src.agents.a2a_client.a2a_process_manager.subprocess.Popen')
    @patch('logging.Logger.warning')
    def test_launch_process_no_command(self, mock_log_warning, mock_popen):
        """Test launch does nothing if command is not set."""
        agent_name = "test_agent_no_cmd"
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command=None, # No command
            restart_on_crash=True,
            agent_name=agent_name,
            stop_event=stop_event
        )

        process_manager.launch()

        mock_popen.assert_not_called()
        mock_log_warning.assert_called_with("No 'a2a_server_command' configured, cannot launch process.")

    # Patch where the objects are *used*
    @patch('src.agents.a2a_client.a2a_process_manager.subprocess.Popen')
    @patch('logging.Logger.warning')
    def test_launch_process_already_running(self, mock_log_warning, mock_popen):
        """Test launch does nothing if process is already running."""
        agent_name = "test_agent_running"
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command="run.sh",
            restart_on_crash=True,
            agent_name=agent_name,
            stop_event=stop_event
        )
        mock_existing_process = MagicMock()
        mock_existing_process.poll.return_value = None # Indicates running
        mock_existing_process.pid = 1234
        process_manager.process = mock_existing_process # Pre-set the process

        process_manager.launch()

        mock_popen.assert_not_called()
        mock_log_warning.assert_called_with("A2A process (PID: 1234) seems to be already running.")

    # Patch where the objects are *used*
    @patch('src.agents.a2a_client.a2a_process_manager.subprocess.Popen', side_effect=FileNotFoundError("Command not found"))
    @patch('src.agents.a2a_client.a2a_process_manager.shlex.split')
    @patch('logging.Logger.error')
    def test_launch_process_file_not_found(self, mock_log_error, mock_shlex_split, mock_popen):
        """Test launch handles FileNotFoundError."""
        command = "non_existent_command"
        agent_name = "test_agent_fnf"
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command=command,
            restart_on_crash=True,
            agent_name=agent_name,
            stop_event=stop_event
        )
        mock_shlex_split.return_value = ["non_existent_command"]

        with self.assertRaises(FileNotFoundError):
            process_manager.launch()

        self.assertIsNone(process_manager.process)
        mock_log_error.assert_called_once()
        self.assertIn("Command not found: non_existent_command", mock_log_error.call_args[0][0])

    # Patch where the objects are *used*
    @patch('src.agents.a2a_client.a2a_process_manager.subprocess.Popen', side_effect=Exception("Other Popen error"))
    @patch('src.agents.a2a_client.a2a_process_manager.shlex.split')
    @patch('logging.Logger.error')
    def test_launch_process_other_exception(self, mock_log_error, mock_shlex_split, mock_popen):
        """Test launch handles other Popen exceptions."""
        command = "some_command"
        agent_name = "test_agent_err"
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command=command,
            restart_on_crash=True,
            agent_name=agent_name,
            stop_event=stop_event
        )
        mock_shlex_split.return_value = ["some_command"]

        with self.assertRaises(Exception):
            process_manager.launch()

        self.assertIsNone(process_manager.process)
        mock_log_error.assert_called_once()
        self.assertIn("Failed to launch A2A agent process", mock_log_error.call_args[0][0])

if __name__ == '__main__':
    unittest.main()
