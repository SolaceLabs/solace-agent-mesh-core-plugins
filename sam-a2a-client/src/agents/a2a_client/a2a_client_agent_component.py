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
import requests # Added import
from urllib.parse import urljoin # Added import
from typing import Dict, Any, Optional, List

from solace_agent_mesh.agents.base_agent_component import BaseAgentComponent, agent_info as base_agent_info
from solace_agent_mesh.common.action_list import ActionList
from solace_agent_mesh.common.action import Action # Added import
from solace_agent_mesh.common.action_response import ActionResponse # Added import for handler type hint
from solace_agent_mesh.services.file_service import FileService

# Import A2A types - adjust path as needed based on dependency setup
try:
    from common.client import A2AClient, A2ACardResolver
    from common.types import AgentCard, AuthenticationScheme, AgentSkill
except ImportError:
    # Placeholder if common library isn't directly available
    A2AClient = Any # type: ignore
    A2ACardResolver = Any # type: ignore
    AgentCard = Any # type: ignore
    AuthenticationScheme = Any # type: ignore
    AgentSkill = Any # type: ignore
    logger = logging.getLogger(__name__)
    logger.warning("Could not import A2A common library types. Using placeholders.")

# Import the dynamic action class
from .actions.a2a_client_action import A2AClientAction


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
        self.a2a_server_url: str = self.get_config("a2a_server_url").rstrip('/') # Ensure no trailing slash
        self.a2a_server_command: Optional[str] = self.get_config("a2a_server_command")
        self.a2a_server_startup_timeout: int = self.get_config("a2a_server_startup_timeout")
        self.a2a_server_restart_on_crash: bool = self.get_config("a2a_server_restart_on_crash")
        self.a2a_bearer_token: Optional[str] = self.get_config("a2a_bearer_token")
        self.input_required_ttl: int = self.get_config("input_required_ttl")

        # State Variables
        self.a2a_process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_monitor = threading.Event()
        self.agent_card: Optional[AgentCard] = None  # Will be populated with AgentCard type
        self.a2a_client: Optional[A2AClient] = None  # Will be populated with A2AClient type
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

    def _wait_for_agent_ready(self) -> bool:
        """
        Polls the A2A agent's well-known endpoint until it's ready or timeout occurs.

        Returns:
            True if the agent becomes ready within the timeout, False otherwise.
        """
        agent_card_url = urljoin(self.a2a_server_url, "/.well-known/agent.json")
        timeout = self.a2a_server_startup_timeout
        deadline = time.time() + timeout
        check_interval = 1 # seconds
        request_timeout = 5 # seconds for the HTTP request itself

        logger.info(f"Waiting up to {timeout}s for A2A agent at {self.a2a_server_url} to become ready...")

        while time.time() < deadline:
            if self.stop_monitor.is_set():
                logger.info("Stop signal received while waiting for agent readiness.")
                return False
            try:
                response = requests.get(agent_card_url, timeout=request_timeout)
                if response.status_code == 200:
                    logger.info(f"A2A agent is ready at {self.a2a_server_url}.")
                    return True
                else:
                    logger.debug(f"A2A agent not ready yet (Status: {response.status_code}). Retrying in {check_interval}s...")

            except requests.exceptions.ConnectionError:
                logger.debug(f"A2A agent connection refused at {self.a2a_server_url}. Retrying in {check_interval}s...")
            except requests.exceptions.Timeout:
                logger.warning(f"Request timed out connecting to {agent_card_url}. Retrying...")
            except requests.exceptions.RequestException as e:
                logger.warning(f"Error checking A2A agent readiness: {e}. Retrying in {check_interval}s...")

            # Use wait on the stop event for sleeping to allow faster shutdown
            if self.stop_monitor.wait(timeout=check_interval):
                logger.info("Stop signal received while waiting for agent readiness.")
                return False

        logger.error(f"A2A agent at {self.a2a_server_url} did not become ready within {timeout} seconds.")
        return False

    def _initialize_a2a_connection(self):
        """
        Initializes the connection to the A2A agent.
        Handles process launch (if configured), waits for readiness,
        fetches the AgentCard, and initializes the A2AClient.
        """
        logger.info(f"Initializing A2A connection for agent '{self.agent_name}'...")
        try:
            # 1. Launch process or check connection
            if self.a2a_server_command:
                self._launch_a2a_process()
                if not self._wait_for_agent_ready():
                    raise TimeoutError(f"Managed A2A agent at {self.a2a_server_url} did not become ready within {self.a2a_server_startup_timeout}s.")
                if self.a2a_server_restart_on_crash and not self.monitor_thread:
                    self.monitor_thread = threading.Thread(target=self._monitor_a2a_process, daemon=True)
                    self.monitor_thread.start()
            else:
                # Check connection to existing agent (use a shorter timeout?)
                # Re-using _wait_for_agent_ready with a shorter effective timeout for a quick check
                quick_check_timeout = 5
                original_timeout = self.a2a_server_startup_timeout
                self.a2a_server_startup_timeout = quick_check_timeout
                ready = self._wait_for_agent_ready()
                self.a2a_server_startup_timeout = original_timeout # Restore original timeout
                if not ready:
                    raise ConnectionError(f"Could not connect to existing A2A agent at {self.a2a_server_url} within {quick_check_timeout}s.")

            # 2. Fetch Agent Card
            logger.info(f"Fetching Agent Card from {self.a2a_server_url}")
            # NOTE: Assuming A2ACardResolver.get_agent_card() is synchronous.
            # If it's async, this needs adaptation (e.g., run in executor or use requests directly).
            try:
                resolver = A2ACardResolver(self.a2a_server_url)
                # TODO: Verify if get_agent_card is sync or async. Assuming sync for now.
                self.agent_card = resolver.get_agent_card()
                if not self.agent_card:
                    raise ValueError("Failed to fetch or parse Agent Card.")
                logger.info(f"Successfully fetched Agent Card for '{self.agent_card.name}'")
            except Exception as e:
                logger.error(f"Error fetching/parsing Agent Card: {e}", exc_info=True)
                raise ValueError(f"Failed to get Agent Card from {self.a2a_server_url}: {e}") from e

            # 3. Initialize A2AClient
            auth_token = None
            bearer_required = False
            if self.agent_card.authentication and self.agent_card.authentication.schemes:
                # Check if 'bearer' is in the list of schemes
                # Compare with string literal "bearer" for robustness against mock types
                if any(str(scheme).lower() == "bearer" for scheme in self.agent_card.authentication.schemes):
                     bearer_required = True

            if bearer_required:
                if self.a2a_bearer_token:
                    auth_token = self.a2a_bearer_token
                    logger.info("Using configured Bearer token for A2A client.")
                else:
                    logger.warning("A2A Agent Card requires Bearer token, but none configured ('a2a_bearer_token'). Proceeding without authentication.")
            # TODO: Add support for other auth schemes (e.g., apiKey) later

            try:
                # Pass agent_card and optional auth_token
                self.a2a_client = A2AClient(agent_card=self.agent_card, auth_token=auth_token)
                logger.info("A2AClient initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize A2AClient: {e}", exc_info=True)
                raise ValueError(f"Could not initialize A2AClient: {e}") from e

            logger.info(f"A2A connection for agent '{self.agent_name}' initialized successfully.")

        except (TimeoutError, ConnectionError, ValueError, FileNotFoundError) as e:
            logger.error(f"Failed to initialize A2A connection for agent '{self.agent_name}': {e}", exc_info=True)
            # Ensure cleanup if initialization fails partially
            self.stop_component()
            raise # Re-raise the exception to signal failure to the framework

    def _infer_params_from_skill(self, skill: AgentSkill) -> List[Dict[str, Any]]:
        """
        Infers SAM action parameters from an A2A skill.
        Simple initial implementation: always returns a generic 'prompt'.

        Args:
            skill: The A2A AgentSkill object.

        Returns:
            A list containing a single dictionary defining the 'prompt' parameter.
        """
        # TODO: Implement more sophisticated parsing of skill.description or other fields later.
        logger.debug(f"Inferring parameters for skill '{skill.id}'. Using generic 'prompt'.")
        return [
            {
                "name": "prompt",
                "desc": "The user request or prompt for the agent.",
                "type": "string",
                "required": True,
            }
        ]

    def _create_actions(self):
        """
        Dynamically creates SAM actions based on the skills found in the AgentCard.
        Also adds the static 'provide_required_input' action.
        """
        logger.info(f"Creating actions for agent '{self.agent_name}' based on AgentCard skills...")

        if not self.agent_card or not self.agent_card.skills:
            logger.warning(f"No skills found in AgentCard for '{self.agent_name}'. No dynamic actions created.")
            # Still add the static action
        else:
            # Create dynamic actions from skills
            for skill in self.agent_card.skills:
                try:
                    inferred_params = self._infer_params_from_skill(skill)
                    action = A2AClientAction(
                        skill=skill,
                        component=self,
                        inferred_params=inferred_params
                    )
                    self.action_list.add_action(action)
                    logger.info(f"Created action '{action.name}' for skill '{skill.id}'")
                except Exception as e:
                    logger.error(f"Failed to create action for skill '{skill.id}': {e}", exc_info=True)

        # Define and add the static 'provide_required_input' action
        provide_input_action_def = {
            "name": "provide_required_input",
            "prompt_directive": "Provides the required input to continue a pending A2A task.",
            "params": [
                {
                    "name": "follow_up_id",
                    "desc": "The ID provided by the previous action call that requires input.",
                    "type": "string",
                    "required": True,
                },
                {
                    "name": "user_response",
                    "desc": "The user's response to the agent's request for input.",
                    "type": "string",
                    "required": True,
                },
                {
                    "name": "files",
                    "desc": "Optional list of file URLs to include with the response.",
                    "type": "list", # Assuming list of strings (URLs)
                    "required": False,
                },
            ],
            "required_scopes": [f"{self.agent_name}:provide_required_input:execute"],
        }
        provide_input_action = Action(
            provide_input_action_def,
            agent=self,
            config_fn=self.get_config
        )
        # Set the handler method (to be implemented in Step 4.4)
        provide_input_action.set_handler(self._handle_provide_required_input)
        self.action_list.add_action(provide_input_action)
        logger.info(f"Added static action '{provide_input_action.name}'")

        # Update component description
        original_description = self.info.get("description", "Component to interact with an external A2A agent.")
        action_names = [a.name for a in self.action_list.actions]
        if action_names:
            self.info["description"] = f"{original_description}\nDiscovered Actions: {', '.join(action_names)}"
        else:
             self.info["description"] = f"{original_description}\nNo actions discovered or created."
        logger.info(f"Action creation complete. Total actions: {len(self.action_list.actions)}")

    # Placeholder for the handler method (Step 4.4)
    def _handle_provide_required_input(self, params: Dict[str, Any], meta: Dict[str, Any]) -> ActionResponse:
        """Handles the 'provide_required_input' action."""
        logger.warning("'_handle_provide_required_input' called but not yet implemented.")
        # Implementation from Step 4.4 will go here
        raise NotImplementedError("'_handle_provide_required_input' is not yet implemented.")


    def run(self):
        """
        Main execution method called by the SAM framework.
        Initializes the A2A connection, creates actions, and then runs the base component loop.
        """
        logger.info(f"Starting run loop for A2AClientAgentComponent '{self.agent_name}'")

        try:
            # Initialize connection and discover actions
            self._initialize_a2a_connection()

            # Create actions based on discovered skills
            self._create_actions() # Call the action creation method

            # Signal that initialization is complete
            self._initialized.set()
            logger.info(f"A2AClientAgentComponent '{self.agent_name}' initialization complete.")

            # Call the base class run method to handle message processing etc.
            super().run()

        except (TimeoutError, ConnectionError, ValueError, FileNotFoundError) as e:
            # Initialization failed, log and stop the component thread
            logger.critical(f"CRITICAL: Initialization failed for A2AClientAgentComponent '{self.agent_name}': {e}. Component will not run.", exc_info=True)
            # Ensure cleanup is called even if run loop doesn't start
            self.stop_component()
            return # Stop the thread execution

        except Exception as e:
            # Catch any other unexpected errors during initialization or run
            logger.critical(f"CRITICAL: Unexpected error in A2AClientAgentComponent '{self.agent_name}' run loop: {e}", exc_info=True)
            self.stop_component()
            return # Stop the thread execution

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
