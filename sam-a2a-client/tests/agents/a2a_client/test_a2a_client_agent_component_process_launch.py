import unittest
from unittest.mock import patch, MagicMock, ANY
import subprocess
import platform
import os

# Adjust the import path based on how tests are run (e.g., from root)
from .test_helpers import create_test_component # Import helper

class TestA2AClientAgentComponentProcessLaunch(unittest.TestCase):

    @patch('src.agents.a2a_client.a2a_client_agent_component.subprocess.Popen')
    @patch('src.agents.a2a_client.a2a_client_agent_component.shlex.split')
    @patch('src.agents.a2a_client.a2a_client_agent_component.os.devnull', '/dev/null') # Mock devnull path
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    def test_launch_process_success(self, mock_open, mock_shlex_split, mock_popen):
        """Test _launch_a2a_process successfully starts a process."""
        command = "my_agent --port 1234"
        component = create_test_component({"a2a_server_command": command})
        mock_shlex_split.return_value = ["my_agent", "--port", "1234"]
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

if __name__ == '__main__':
    unittest.main()
