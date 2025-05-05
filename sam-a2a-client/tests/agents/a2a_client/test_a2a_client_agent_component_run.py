import unittest
from unittest.mock import patch, MagicMock, call
import threading

# Adjust import paths as necessary
from src.agents.a2a_client.a2a_client_agent_component import A2AClientAgentComponent
from src.agents.a2a_client.a2a_process_manager import A2AProcessManager
from src.agents.a2a_client.a2a_connection_handler import A2AConnectionHandler
from solace_agent_mesh.agents.base_agent_component import BaseAgentComponent
from solace_ai_connector.common.log import log  # Import the log object

# Import helper to create component instance
from .test_helpers import create_test_component


class TestA2AClientAgentComponentRun(unittest.TestCase):

    def setUp(self):
        # Mock cache service needed for component creation
        self.mock_cache = MagicMock()

        # Patch dependencies used within the run method's scope
        self.patcher_pm = patch(
            "src.agents.a2a_client.a2a_client_agent_component.A2AProcessManager",
            spec=A2AProcessManager,
        )
        self.patcher_ch = patch(
            "src.agents.a2a_client.a2a_client_agent_component.A2AConnectionHandler",
            spec=A2AConnectionHandler,
        )
        self.patcher_create_actions = patch.object(
            A2AClientAgentComponent, "_create_actions"
        )
        self.patcher_super_run = patch.object(BaseAgentComponent, "run")
        self.patcher_log_critical = patch.object(log, "critical")
        self.patcher_stop_component = patch.object(
            A2AClientAgentComponent, "stop_component"
        )

        self.MockProcessManager = self.patcher_pm.start()
        self.MockConnectionHandler = self.patcher_ch.start()
        self.mock_create_actions = self.patcher_create_actions.start()
        self.mock_super_run = self.patcher_super_run.start()
        self.mock_log_critical = self.patcher_log_critical.start()
        self.mock_stop_component = self.patcher_stop_component.start()

        # Mock instances returned by constructors
        self.mock_pm_instance = self.MockProcessManager.return_value
        self.mock_ch_instance = self.MockConnectionHandler.return_value

        # Default successful return values for handler methods
        self.mock_ch_instance.wait_for_ready.return_value = True
        self.mock_ch_instance.initialize_client.return_value = (
            None  # Method doesn't return anything
        )

    def tearDown(self):
        self.patcher_pm.stop()
        self.patcher_ch.stop()
        self.patcher_create_actions.stop()
        self.patcher_super_run.stop()
        self.patcher_log_critical.stop()
        self.patcher_stop_component.stop()

    def test_run_success_launch_mode(self):
        """Test successful run sequence in launch mode."""
        config = {
            "a2a_server_command": "run_my_agent.sh",
            "a2a_server_url": "http://launched:1234",
            "a2a_server_startup_timeout": 20,
            "a2a_server_restart_on_crash": True,
            # Explicitly set new configs to None for this test
            "a2a_server_working_dir": None,
            "a2a_server_env_file": None,
        }
        component = create_test_component(config, self.mock_cache)

        # Call run
        component.run()

        # Assertions
        # Updated assertion to include working_dir and env_file
        self.MockProcessManager.assert_called_once_with(
            command=config["a2a_server_command"],
            working_dir=config["a2a_server_working_dir"], # Added
            env_file=config["a2a_server_env_file"],       # Added
            restart_on_crash=config["a2a_server_restart_on_crash"],
            agent_name=component.agent_name,
            stop_event=component.stop_monitor,
        )
        self.mock_pm_instance.launch.assert_called_once()
        self.MockConnectionHandler.assert_called_once_with(
            server_url=config["a2a_server_url"],
            bearer_token=None,  # Assuming default config
            stop_event=component.stop_monitor,
        )
        self.mock_ch_instance.wait_for_ready.assert_called_once_with(
            config["a2a_server_startup_timeout"]
        )
        self.mock_ch_instance.initialize_client.assert_called_once()
        self.mock_create_actions.assert_called_once()
        self.mock_pm_instance.start_monitor.assert_called_once()
        self.assertTrue(component._initialized.is_set())
        self.mock_super_run.assert_called_once()
        self.mock_log_critical.assert_not_called()
        self.mock_stop_component.assert_not_called()  # Should not be called on success

    def test_run_success_connect_mode(self):
        """Test successful run sequence in connect mode (no command)."""
        config = {
            "a2a_server_command": None,  # Explicitly no command
            "a2a_server_url": "http://existing:5678",
            "a2a_server_startup_timeout": 5,  # Shorter timeout for connect check
        }
        component = create_test_component(config, self.mock_cache)

        # Call run
        component.run()

        # Assertions
        self.MockProcessManager.assert_not_called()  # PM not created
        self.mock_pm_instance.launch.assert_not_called()
        self.MockConnectionHandler.assert_called_once_with(
            server_url=config["a2a_server_url"],
            bearer_token=None,
            stop_event=component.stop_monitor,
        )
        self.mock_ch_instance.wait_for_ready.assert_called_once_with(
            config["a2a_server_startup_timeout"]
        )
        self.mock_ch_instance.initialize_client.assert_called_once()
        self.mock_create_actions.assert_called_once()
        self.mock_pm_instance.start_monitor.assert_not_called()  # Monitor not started
        self.assertTrue(component._initialized.is_set())
        self.mock_super_run.assert_called_once()
        self.mock_log_critical.assert_not_called()
        self.mock_stop_component.assert_not_called()

    def test_run_failure_launch_error(self):
        """Test run handles error during process launch."""
        config = {
            "a2a_server_command": "bad_command",
            "a2a_server_working_dir": None,
            "a2a_server_env_file": None,
        }
        component = create_test_component(config, self.mock_cache)
        launch_error = FileNotFoundError("Command not found")
        self.mock_pm_instance.launch.side_effect = launch_error

        # Call run
        component.run()

        # Assertions
        self.MockProcessManager.assert_called_once_with(
            command=config["a2a_server_command"],
            working_dir=config["a2a_server_working_dir"],
            env_file=config["a2a_server_env_file"],
            restart_on_crash=True, # Default
            agent_name=component.agent_name,
            stop_event=component.stop_monitor,
        )
        self.mock_pm_instance.launch.assert_called_once()
        self.MockConnectionHandler.assert_not_called()  # Should fail before CH init
        self.mock_ch_instance.wait_for_ready.assert_not_called()
        self.mock_ch_instance.initialize_client.assert_not_called()
        self.mock_create_actions.assert_not_called()
        self.mock_pm_instance.start_monitor.assert_not_called()
        self.assertFalse(component._initialized.is_set())
        self.mock_super_run.assert_not_called()
        self.mock_log_critical.assert_called_once()
        self.assertIn("Initialization failed", self.mock_log_critical.call_args[0][0])
        # Check the correct argument index for the exception
        self.assertEqual(self.mock_log_critical.call_args[0][2], launch_error)
        self.mock_stop_component.assert_called_once()  # Cleanup should be called

    def test_run_failure_readiness_timeout(self):
        """Test run handles timeout during readiness check."""
        config = {"a2a_server_url": "http://timeout:1234"}
        component = create_test_component(config, self.mock_cache)
        self.mock_ch_instance.wait_for_ready.return_value = False  # Simulate timeout

        # Call run
        component.run()

        # Assertions
        self.MockConnectionHandler.assert_called_once()
        self.mock_ch_instance.wait_for_ready.assert_called_once()
        self.mock_ch_instance.initialize_client.assert_not_called()  # Should fail before client init
        self.mock_create_actions.assert_not_called()
        self.mock_pm_instance.start_monitor.assert_not_called()
        self.assertFalse(component._initialized.is_set())
        self.mock_super_run.assert_not_called()
        self.mock_log_critical.assert_called_once()
        self.assertIn("Initialization failed", self.mock_log_critical.call_args[0][0])
        # Check the correct argument index for the exception
        self.assertIsInstance(self.mock_log_critical.call_args[0][2], TimeoutError)
        self.mock_stop_component.assert_called_once()

    def test_run_failure_client_init_error(self):
        """Test run handles error during A2AClient initialization."""
        config = {"a2a_server_url": "http://client-init-fail:1234"}
        component = create_test_component(config, self.mock_cache)
        init_error = ValueError("Failed to init client")
        self.mock_ch_instance.initialize_client.side_effect = init_error

        # Call run
        component.run()

        # Assertions
        self.MockConnectionHandler.assert_called_once()
        self.mock_ch_instance.wait_for_ready.assert_called_once()
        self.mock_ch_instance.initialize_client.assert_called_once()
        self.mock_create_actions.assert_not_called()  # Should fail before action creation
        self.mock_pm_instance.start_monitor.assert_not_called()
        self.assertFalse(component._initialized.is_set())
        self.mock_super_run.assert_not_called()
        self.mock_log_critical.assert_called_once()
        self.assertIn("Initialization failed", self.mock_log_critical.call_args[0][0])
        # Check the correct argument index for the exception
        self.assertEqual(self.mock_log_critical.call_args[0][2], init_error)
        self.mock_stop_component.assert_called_once()

    def test_run_failure_action_creation_error(self):
        """Test run handles error during action creation."""
        config = {"a2a_server_url": "http://action-fail:1234"}
        component = create_test_component(config, self.mock_cache)
        action_error = Exception("Could not create actions")
        self.mock_create_actions.side_effect = action_error

        # Call run
        component.run()

        # Assertions
        self.MockConnectionHandler.assert_called_once()
        self.mock_ch_instance.wait_for_ready.assert_called_once()
        self.mock_ch_instance.initialize_client.assert_called_once()
        self.mock_create_actions.assert_called_once()
        self.mock_pm_instance.start_monitor.assert_not_called()  # Should fail before monitor start
        self.assertFalse(component._initialized.is_set())  # Should not be set on error
        self.mock_super_run.assert_not_called()
        self.mock_log_critical.assert_called_once()
        self.assertIn(
            "Unexpected error", self.mock_log_critical.call_args[0][0]
        )  # Check generic error log
        # Check the correct argument index for the exception
        self.assertEqual(self.mock_log_critical.call_args[0][2], action_error)
        self.mock_stop_component.assert_called_once()


if __name__ == "__main__":
    unittest.main()
