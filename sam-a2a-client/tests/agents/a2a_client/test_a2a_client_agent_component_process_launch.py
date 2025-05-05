import unittest
from unittest.mock import patch, MagicMock, ANY, call
import subprocess
import platform
import os
import threading # Import threading

# Adjust the import path based on how tests are run (e.g., from root)
from .test_helpers import create_test_component # Import helper
# Import the class we are testing the launch method of
from src.agents.a2a_client.a2a_process_manager import A2AProcessManager
from solace_ai_connector.common.log import log # Import the log object

class TestA2AClientAgentComponentProcessLaunch(unittest.TestCase):

    # Patch where the objects are *used* (in a2a_process_manager)
    @patch('src.agents.a2a_client.a2a_process_manager.subprocess.Popen')
    @patch('src.agents.a2a_client.a2a_process_manager.shlex.split')
    @patch('src.agents.a2a_client.a2a_process_manager.os.devnull', '/mock/dev/null') # Mock devnull path
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('src.agents.a2a_client.a2a_process_manager.dotenv_values') # Mock dotenv
    @patch('src.agents.a2a_client.a2a_process_manager.os.path.exists') # Mock path check
    @patch('src.agents.a2a_client.a2a_process_manager.os.path.isdir') # Mock dir check
    def test_launch_process_success(self, mock_isdir, mock_exists, mock_dotenv, mock_open, mock_shlex_split, mock_popen):
        """Test A2AProcessManager.launch successfully starts a process."""
        command = "my_agent --port 1234"
        agent_name = "test_agent"
        working_dir = "/path/to/work"
        env_file = "/path/to/.env"
        stop_event = threading.Event()
        mock_exists.return_value = True # Assume env file exists
        mock_isdir.return_value = True # Assume working dir exists
        mock_dotenv.return_value = {"AGENT_KEY": "secret"} # Mock loaded env vars

        # Instantiate the Process Manager directly
        process_manager = A2AProcessManager(
            command=command,
            working_dir=working_dir,
            env_file=env_file,
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
        mock_exists.assert_called_once_with(env_file)
        mock_dotenv.assert_called_once_with(env_file)
        mock_isdir.assert_called_once_with(working_dir)

        # Prepare expected environment (merge with current, loaded vars take precedence)
        expected_env = os.environ.copy()
        expected_env.update({"AGENT_KEY": "secret"})

        popen_kwargs = {
            'stdout': ANY,
            'stderr': subprocess.PIPE, # Check stderr is PIPE
            'cwd': working_dir, # Check cwd
            'env': expected_env, # Check env
            'text': True, # Check text mode
            'encoding': 'utf-8', # Check encoding
            'errors': 'replace' # Check error handling
        }
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
    @patch('solace_ai_connector.common.log.log.warning') # Patch the correct log object
    def test_launch_process_no_command(self, mock_log_warning, mock_popen):
        """Test launch does nothing if command is not set."""
        agent_name = "test_agent_no_cmd"
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command=None, # No command
            working_dir=None,
            env_file=None,
            restart_on_crash=True,
            agent_name=agent_name,
            stop_event=stop_event
        )

        process_manager.launch()

        mock_popen.assert_not_called()
        mock_log_warning.assert_called_with("No 'a2a_server_command' configured for '%s', cannot launch process.", agent_name)

    # Patch where the objects are *used*
    @patch('src.agents.a2a_client.a2a_process_manager.subprocess.Popen')
    @patch('solace_ai_connector.common.log.log.warning') # Patch the correct log object
    def test_launch_process_already_running(self, mock_log_warning, mock_popen):
        """Test launch does nothing if process is already running."""
        agent_name = "test_agent_running"
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command="run.sh",
            working_dir=None,
            env_file=None,
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
        mock_log_warning.assert_called_with("A2A process (PID: %d) for '%s' seems to be already running.", 1234, agent_name)

    # Patch where the objects are *used*
    @patch('src.agents.a2a_client.a2a_process_manager.subprocess.Popen', side_effect=FileNotFoundError("Command not found"))
    @patch('src.agents.a2a_client.a2a_process_manager.shlex.split')
    @patch('solace_ai_connector.common.log.log.error') # Patch the correct log object
    @patch('src.agents.a2a_client.a2a_process_manager.os.path.isdir', return_value=True) # Assume WD is valid
    def test_launch_process_command_not_found(self, mock_isdir, mock_log_error, mock_shlex_split, mock_popen):
        """Test launch handles FileNotFoundError for the command."""
        command = "non_existent_command"
        agent_name = "test_agent_fnf"
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command=command,
            working_dir=None,
            env_file=None,
            restart_on_crash=True,
            agent_name=agent_name,
            stop_event=stop_event
        )
        mock_shlex_split.return_value = ["non_existent_command"]

        with self.assertRaises(FileNotFoundError) as cm:
            process_manager.launch()

        self.assertIsNone(process_manager.process)
        mock_log_error.assert_called_once()
        self.assertIn("Command not found for '%s': %s", mock_log_error.call_args[0][0])
        self.assertEqual(mock_log_error.call_args[0][1], agent_name)
        self.assertEqual(mock_log_error.call_args[0][2], "non_existent_command")
        self.assertIn("Command not found", str(cm.exception)) # Check re-raised exception message

    # Patch where the objects are *used*
    @patch('src.agents.a2a_client.a2a_process_manager.subprocess.Popen')
    @patch('src.agents.a2a_client.a2a_process_manager.shlex.split')
    @patch('solace_ai_connector.common.log.log.error') # Patch the correct log object
    @patch('src.agents.a2a_client.a2a_process_manager.os.path.isdir', return_value=False) # WD is invalid
    def test_launch_process_invalid_working_dir(self, mock_isdir, mock_log_error, mock_shlex_split, mock_popen):
        """Test launch handles FileNotFoundError for an invalid working directory."""
        command = "some_command"
        agent_name = "test_agent_bad_wd"
        working_dir = "/invalid/path"
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command=command,
            working_dir=working_dir,
            env_file=None,
            restart_on_crash=True,
            agent_name=agent_name,
            stop_event=stop_event
        )
        mock_shlex_split.return_value = ["some_command"]

        with self.assertRaises(FileNotFoundError) as cm:
            process_manager.launch()

        self.assertIsNone(process_manager.process)
        mock_isdir.assert_called_once_with(working_dir)
        mock_popen.assert_not_called() # Should fail before Popen
        mock_log_error.assert_called_once()
        self.assertIn("Invalid working directory for '%s': %s", mock_log_error.call_args[0][0])
        self.assertEqual(mock_log_error.call_args[0][1], agent_name)
        self.assertEqual(mock_log_error.call_args[0][2], working_dir)
        self.assertIn("Invalid working directory", str(cm.exception)) # Check re-raised exception message

    # Patch where the objects are *used*
    @patch('src.agents.a2a_client.a2a_process_manager.subprocess.Popen', side_effect=Exception("Other Popen error"))
    @patch('src.agents.a2a_client.a2a_process_manager.shlex.split')
    @patch('solace_ai_connector.common.log.log.error') # Patch the correct log object
    @patch('src.agents.a2a_client.a2a_process_manager.os.path.isdir', return_value=True) # Assume WD is valid
    def test_launch_process_other_exception(self, mock_isdir, mock_log_error, mock_shlex_split, mock_popen):
        """Test launch handles other Popen exceptions."""
        command = "some_command"
        agent_name = "test_agent_err"
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command=command,
            working_dir=None,
            env_file=None,
            restart_on_crash=True,
            agent_name=agent_name,
            stop_event=stop_event
        )
        mock_shlex_split.return_value = ["some_command"]

        with self.assertRaises(Exception):
            process_manager.launch()

        self.assertIsNone(process_manager.process)
        mock_log_error.assert_called_once()
        self.assertIn("Failed to launch A2A agent process for '%s': %s", mock_log_error.call_args[0][0])
        self.assertEqual(mock_log_error.call_args[0][1], agent_name)
        self.assertIsInstance(mock_log_error.call_args[0][2], Exception)

    @patch('src.agents.a2a_client.a2a_process_manager.subprocess.Popen')
    @patch('src.agents.a2a_client.a2a_process_manager.shlex.split')
    @patch('src.agents.a2a_client.a2a_process_manager.os.path.exists', return_value=False) # Env file doesn't exist
    @patch('solace_ai_connector.common.log.log.warning') # Patch the correct log object
    @patch('src.agents.a2a_client.a2a_process_manager.os.path.isdir', return_value=True) # Assume WD is valid
    def test_launch_process_env_file_not_found(self, mock_isdir, mock_log_warning, mock_exists, mock_shlex_split, mock_popen):
        """Test launch logs warning if env_file doesn't exist and proceeds."""
        command = "agent_cmd"
        agent_name = "test_agent_no_env"
        env_file = "/missing/.env"
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command=command,
            working_dir=None,
            env_file=env_file,
            restart_on_crash=True,
            agent_name=agent_name,
            stop_event=stop_event
        )
        mock_shlex_split.return_value = ["agent_cmd"]
        mock_process = MagicMock(pid=1111)
        mock_popen.return_value = mock_process

        process_manager.launch()

        mock_exists.assert_called_once_with(env_file)
        mock_log_warning.assert_called_with(
            "Environment file '%s' specified for agent '%s' does not exist. Skipping.",
            env_file, agent_name
        )
        # Check that Popen was called without the 'env' kwarg
        popen_kwargs = mock_popen.call_args[1]
        self.assertNotIn('env', popen_kwargs)
        self.assertEqual(process_manager.process, mock_process)

    @patch('src.agents.a2a_client.a2a_process_manager.subprocess.Popen')
    @patch('src.agents.a2a_client.a2a_process_manager.shlex.split')
    @patch('src.agents.a2a_client.a2a_process_manager.os.path.exists', return_value=True)
    @patch('src.agents.a2a_client.a2a_process_manager.dotenv_values', side_effect=Exception("dotenv error")) # Mock dotenv error
    @patch('solace_ai_connector.common.log.log.error') # Patch the correct log object
    @patch('src.agents.a2a_client.a2a_process_manager.os.path.isdir', return_value=True) # Assume WD is valid
    def test_launch_process_env_file_load_error(self, mock_isdir, mock_log_error, mock_dotenv, mock_exists, mock_shlex_split, mock_popen):
        """Test launch logs error if loading env_file fails and proceeds."""
        command = "agent_cmd"
        agent_name = "test_agent_env_err"
        env_file = "/bad/.env"
        stop_event = threading.Event()
        process_manager = A2AProcessManager(
            command=command,
            working_dir=None,
            env_file=env_file,
            restart_on_crash=True,
            agent_name=agent_name,
            stop_event=stop_event
        )
        mock_shlex_split.return_value = ["agent_cmd"]
        mock_process = MagicMock(pid=2222)
        mock_popen.return_value = mock_process

        process_manager.launch()

        mock_exists.assert_called_once_with(env_file)
        mock_dotenv.assert_called_once_with(env_file)
        mock_log_error.assert_called_once()
        self.assertIn("Failed to load environment variables from '%s'", mock_log_error.call_args[0][0])
        # Check that Popen was called without the 'env' kwarg
        popen_kwargs = mock_popen.call_args[1]
        self.assertNotIn('env', popen_kwargs)
        self.assertEqual(process_manager.process, mock_process)


if __name__ == '__main__':
    unittest.main()
