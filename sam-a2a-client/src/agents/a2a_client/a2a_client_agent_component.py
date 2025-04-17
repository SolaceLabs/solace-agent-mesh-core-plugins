"""
Main component for the SAM A2A Client Plugin.

This component manages the connection to an external A2A agent,
discovers its capabilities, and exposes them as SAM actions.
"""
import copy
import threading
import logging
import subprocess # Added import
import shlex
import os
import platform
import time # Added import
from typing import Dict, Any, Optional

from solace_agent_mesh.agents.base_agent_component import BaseAgentComponent, agent_info as base_agent_info
from solace_agent_mesh.common.action_list import ActionList
from solace_agent_mesh.services.file_service import FileService
# Import other necessary types later, e.g., ActionResponse, AgentCard, A2AClient etc.

# Define component configuration schema
info = copy.deepcopy(base_agent_info)
info.update(
    {
        "class_name": "A2AClientAgentComponent",
        "description": "Component to interact with an external A2A agent.", # Will be updated dynamically
        "config_parameters": base_agent_info["config_parameters"] + [
            {
                "name": "agent_name",
                "required": True,
                "description": "Unique name for this SAM agent instance wrapping the A2A agent.",
                "type": "string",
            },
            {
                "name": "a2a_server_url",
                "required": True,
                "description": "The base URL of the target A2A agent (e.g., http://localhost:10001).",
                "type": "string",
            },
            {
                "name": "a2a_server_command",
                "required": False,
                "description": "Optional command line to launch the A2A agent process.",
                "type": "string",
            },
            {
                "name": "a2a_server_startup_timeout",
                "required": False,
                "description": "Seconds to wait for a launched A2A agent to become ready.",
                "type": "integer",
                "default": 30,
            },
            {
                "name": "a2a_server_restart_on_crash",
                "required": False,
                "description": "Attempt to restart the managed A2A agent process if it crashes.",
                "type": "boolean",
                "default": True,
            },
            {
                "name": "a2a_bearer_token",
                "required": False,
                "description": "Optional Bearer token for A2A requests.",
                "type": "string",
            },
            {
                "name": "input_required_ttl",
                "required": False,
                "description": "TTL in seconds for storing INPUT_REQUIRED state.",
                "type": "integer",
                "default": 300,
            },
        ],
        # Input schema remains the same as base_agent_info (action_name, action_params)
    }
)

logger = logging.getLogger(__name__)

class A2AClientAgentComponent(BaseAgentComponent):
    """
    SAM Agent Component that acts as a client to an external A2A agent.
    """
    info = info # Assign class variable

    def __init__(self, module_info: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initializes the A2AClientAgentComponent.

        Args:
            module_info: Component module information.
            **kwargs: Additional keyword arguments passed from the framework,
                      including 'cache_service'.
        """
        super().__init__(module_info or info, **kwargs)
        logger.info(f"Initializing A2AClientAgentComponent for agent '{self.get_config('agent_name', 'UNKNOWN')}'")

        # Configuration
        self.agent_name: str = self.get_config("agent_name")
        self.a2a_server_url: str = self.get_config("a2a_server_url")
        self.a2a_server_command: Optional[str] = self.get_config("a2a_server_command")
        self.a2a_server_startup_timeout: int = self.get_config("a2a_server_startup_timeout")
        self.a2a_server_restart_on_crash: bool = self.get_config("a2a_server_restart_on_crash")
        self.a2a_bearer_token: Optional[str] = self.get_config("a2a_bearer_token")
        self.input_required_ttl: int = self.get_config("input_required_ttl")

        # State Variables
        self.a2a_process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_monitor = threading.Event()
        self.agent_card = None  # Will be populated with AgentCard type
        self.a2a_client = None  # Will be populated with A2AClient type
        self._initialized = threading.Event() # Signals when connection & actions are ready

        # SAM Services
        self.file_service = FileService()
        self.cache_service = kwargs.get("cache_service")
        if self.cache_service is None:
            logger.warning("Cache service not provided to A2AClientAgentComponent. INPUT_REQUIRED state will not be supported.")

        # Action List (initially empty, populated after connection)
        self.action_list = ActionList([], agent=self, config_fn=self.get_config)

        # Update component info with specific instance name
        # The description will be updated later after fetching the AgentCard
        self.info["agent_name"] = self.agent_name
        logger.info(f"A2AClientAgentComponent '{self.agent_name}' initialized.")

    def _launch_a2a_process(self):
        """Launches the external A2A agent process if configured."""
        if not self.a2a_server_command:
            logger.warning("No 'a2a_server_command' configured, cannot launch process.")
            return

        if self.a2a_process and self.a2a_process.poll() is None:
            logger.warning(f"A2A process (PID: {self.a2a_process.pid}) seems to be already running.")
            return

        logger.info(f"Launching A2A agent process with command: {self.a2a_server_command}")
        try:
            # Use shlex.split for safer command parsing
            args = shlex.split(self.a2a_server_command)

            # Platform specific flags for better process group handling
            popen_kwargs = {}
            if platform.system() == "Windows":
                popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            else: # POSIX
                popen_kwargs['start_new_session'] = True

            # Redirect stdout/stderr to prevent blocking
            with open(os.devnull, 'w') as devnull:
                self.a2a_process = subprocess.Popen(
                    args,
                    stdout=devnull,
                    stderr=devnull,
                    **popen_kwargs
                )
            logger.info(f"Launched A2A agent process with PID: {self.a2a_process.pid}")

        except FileNotFoundError:
            logger.error(f"Command not found: {args[0]}. Please ensure it's in the system PATH or provide the full path.", exc_info=True)
            self.a2a_process = None # Ensure process is None on failure
            raise # Re-raise after logging
        except Exception as e:
            logger.error(f"Failed to launch A2A agent process: {e}", exc_info=True)
            self.a2a_process = None # Ensure process is None on failure
            raise # Re-raise after logging

    def _monitor_a2a_process(self):
        """Monitors the managed A2A process and restarts it if configured."""
        logger.info(f"Starting monitor thread for A2A process '{self.agent_name}'.")
        while not self.stop_monitor.is_set():
            if not self.a2a_process:
                logger.warning("Monitor thread: No A2A process to monitor. Exiting.")
                break

            return_code = self.a2a_process.poll()

            if return_code is not None: # Process terminated
                log_func = logger.info if return_code == 0 else logger.error
                log_func(f"Managed A2A process (PID: {self.a2a_process.pid}) terminated with code {return_code}.")

                if self.a2a_server_restart_on_crash and return_code != 0 and not self.stop_monitor.is_set():
                    logger.info("Attempting to restart the A2A process...")
                    # Wait a moment before restarting
                    self.stop_monitor.wait(2)
                    if self.stop_monitor.is_set(): break # Check again after wait

                    try:
                        self._launch_a2a_process()
                        if not self.a2a_process:
                            logger.error("Failed to restart A2A process. Stopping monitor.")
                            break
                        # If launch succeeded, continue monitoring the new process
                        logger.info("A2A process restarted successfully.")
                        continue # Go back to polling the new process
                    except Exception as e:
                        logger.error(f"Exception during A2A process restart: {e}. Stopping monitor.", exc_info=True)
                        break # Stop monitoring if restart fails critically
                else:
                    # No restart configured, or clean exit, or stopping
                    break # Exit monitor loop

            # Wait for a few seconds before checking again, but check stop_monitor frequently
            wait_interval = 5 # seconds
            if self.stop_monitor.wait(timeout=wait_interval):
                 break # Exit if stop signal is set during wait

        logger.info(f"Stopping monitor thread for A2A process '{self.agent_name}'.")


    def run(self):
        """
        Main execution method called by the SAM framework.
        Initializes the A2A connection and then runs the base component loop.
        """
        # Initialization logic (_initialize_a2a_connection, _create_actions)
        # will be added here in later steps.
        logger.info(f"Starting run loop for A2AClientAgentComponent '{self.agent_name}'")
        super().run()
        logger.info(f"Exiting run loop for A2AClientAgentComponent '{self.agent_name}'")


    def stop_component(self):
        """
        Cleans up resources when the component is stopped.
        """
        logger.info(f"Stopping A2AClientAgentComponent '{self.agent_name}'...")
        self.stop_monitor.set()

        # Terminate the managed process if it exists
        if self.a2a_process:
            logger.info(f"Terminating managed A2A process (PID: {self.a2a_process.pid})...")
            try:
                # Send SIGTERM (terminate) first
                self.a2a_process.terminate()
                try:
                    # Wait for a short period
                    self.a2a_process.wait(timeout=5)
                    logger.info("Managed A2A process terminated gracefully.")
                except subprocess.TimeoutExpired:
                    # If it didn't terminate, send SIGKILL (kill)
                    logger.warning("Managed A2A process did not terminate gracefully after 5s, killing.")
                    self.a2a_process.kill()
                    self.a2a_process.wait() # Wait for kill to complete
                    logger.info("Managed A2A process killed.")
            except Exception as e:
                logger.error(f"Error terminating managed A2A process: {e}", exc_info=True)
            self.a2a_process = None

        # Wait for the monitor thread to finish
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.info("Waiting for monitor thread to exit...")
            self.monitor_thread.join(timeout=5)
            if self.monitor_thread.is_alive():
                logger.warning("Monitor thread did not exit cleanly.")
            else:
                logger.info("Monitor thread exited.")
            self.monitor_thread = None

        # Call base class cleanup
        super().stop_component()
        logger.info(f"A2AClientAgentComponent '{self.agent_name}' stopped.")
