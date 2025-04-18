"""
Main component for the SAM A2A Client Plugin.

This component manages the connection to an external A2A agent,
discovers its capabilities, and exposes them as SAM actions.
"""

import copy
import threading
import logging
import subprocess  # Added import
import shlex
import os
import platform
import time  # Added import
import requests  # Added import
import uuid  # Added import
import json # Added import
from urllib.parse import urljoin  # Added import
from typing import Dict, Any, Optional, List

from solace_agent_mesh.agents.base_agent_component import (
    BaseAgentComponent,
    agent_info as base_agent_info,
)
from solace_agent_mesh.common.action_list import ActionList
from solace_agent_mesh.common.action import Action  # Added import
from solace_agent_mesh.common.action_response import (
    ActionResponse,
    ErrorInfo,
)  # Added import for handler type hint
from solace_agent_mesh.services.file_service import FileService

from ...common_a2a.client import A2AClient, A2ACardResolver
from ...common_a2a.types import (
    AgentCard,
    AgentSkill,
    TaskSendParams,  # Added for handler
    Message as A2AMessage,  # Added for handler
    TextPart,  # Added for handler
    FilePart,  # Added for handler
    FileContent,  # Added for handler
    Task,  # Added for handler
    TaskState,  # Added for handler
)

# Define string constants based on imported enum for robustness in comparisons
A2A_TASK_STATE_COMPLETED = TaskState.COMPLETED
A2A_TASK_STATE_FAILED = TaskState.FAILED
A2A_TASK_STATE_INPUT_REQUIRED = TaskState.INPUT_REQUIRED


# Import the dynamic action class
from .actions.a2a_client_action import A2AClientAction


# Define component configuration schema
info = copy.deepcopy(base_agent_info)
info.update(
    {
        "class_name": "A2AClientAgentComponent",
        "description": "Component to interact with an external A2A agent.",  # Will be updated dynamically
        "config_parameters": base_agent_info["config_parameters"]
        + [
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

    info = info  # Assign class variable

    def __init__(self, module_info: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initializes the A2AClientAgentComponent.

        Args:
            module_info: Component module information.
            **kwargs: Additional keyword arguments passed from the framework,
                      including 'cache_service'.
        """
        super().__init__(module_info or info, **kwargs)
        logger.info(
            f"Initializing A2AClientAgentComponent for agent '{self.get_config('agent_name', 'UNKNOWN')}'"
        )

        # Configuration
        self.agent_name: str = self.get_config("agent_name")
        self.a2a_server_url: str = self.get_config("a2a_server_url").rstrip(
            "/"
        )  # Ensure no trailing slash
        self.a2a_server_command: Optional[str] = self.get_config("a2a_server_command")
        self.a2a_server_startup_timeout: int = self.get_config(
            "a2a_server_startup_timeout"
        )
        self.a2a_server_restart_on_crash: bool = self.get_config(
            "a2a_server_restart_on_crash"
        )
        self.a2a_bearer_token: Optional[str] = self.get_config("a2a_bearer_token")
        self.input_required_ttl: int = self.get_config("input_required_ttl")

        # State Variables
        self.a2a_process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_monitor = threading.Event()
        self.agent_card: Optional[AgentCard] = (
            None  # Will be populated with AgentCard type
        )
        self.a2a_client: Optional[A2AClient] = (
            None  # Will be populated with A2AClient type
        )
        self._initialized = (
            threading.Event()
        )  # Signals when connection & actions are ready

        # SAM Services
        self.file_service = FileService()
        self.cache_service = kwargs.get("cache_service")
        if self.cache_service is None:
            logger.warning(
                "Cache service not provided to A2AClientAgentComponent. INPUT_REQUIRED state will not be supported."
            )

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
            logger.warning(
                f"A2A process (PID: {self.a2a_process.pid}) seems to be already running."
            )
            return

        logger.info(
            f"Launching A2A agent process with command: {self.a2a_server_command}"
        )
        try:
            # Use shlex.split for safer command parsing
            args = shlex.split(self.a2a_server_command)

            # Platform specific flags for better process group handling
            popen_kwargs = {}
            if platform.system() == "Windows":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:  # POSIX
                popen_kwargs["start_new_session"] = True

            # Redirect stdout/stderr to prevent blocking
            with open(os.devnull, "w") as devnull:
                self.a2a_process = subprocess.Popen(
                    args, stdout=devnull, stderr=devnull, **popen_kwargs
                )
            logger.info(f"Launched A2A agent process with PID: {self.a2a_process.pid}")

        except FileNotFoundError:
            logger.error(
                f"Command not found: {args[0]}. Please ensure it's in the system PATH or provide the full path.",
                exc_info=True,
            )
            self.a2a_process = None  # Ensure process is None on failure
            raise  # Re-raise after logging
        except Exception as e:
            logger.error(f"Failed to launch A2A agent process: {e}", exc_info=True)
            self.a2a_process = None  # Ensure process is None on failure
            raise  # Re-raise after logging

    def _monitor_a2a_process(self):
        """Monitors the managed A2A process and restarts it if configured."""
        logger.info(f"Starting monitor thread for A2A process '{self.agent_name}'.")
        while not self.stop_monitor.is_set():
            if not self.a2a_process:
                logger.warning("Monitor thread: No A2A process to monitor. Exiting.")
                break

            return_code = self.a2a_process.poll()

            if return_code is not None:  # Process terminated
                log_func = logger.info if return_code == 0 else logger.error
                log_func(
                    f"Managed A2A process (PID: {self.a2a_process.pid}) terminated with code {return_code}."
                )

                if (
                    self.a2a_server_restart_on_crash
                    and return_code != 0
                    and not self.stop_monitor.is_set()
                ):
                    logger.info("Attempting to restart the A2A process...")
                    # Wait a moment before restarting
                    self.stop_monitor.wait(2)
                    if self.stop_monitor.is_set():
                        break  # Check again after wait

                    try:
                        self._launch_a2a_process()
                        if not self.a2a_process:
                            logger.error(
                                "Failed to restart A2A process. Stopping monitor."
                            )
                            break
                        # If launch succeeded, continue monitoring the new process
                        logger.info("A2A process restarted successfully.")
                        continue  # Go back to polling the new process
                    except Exception as e:
                        logger.error(
                            f"Exception during A2A process restart: {e}. Stopping monitor.",
                            exc_info=True,
                        )
                        break  # Stop monitoring if restart fails critically
                else:
                    # No restart configured, or clean exit, or stopping
                    break  # Exit monitor loop

            # Wait for a few seconds before checking again, but check stop_monitor frequently
            wait_interval = 5  # seconds
            if self.stop_monitor.wait(timeout=wait_interval):
                break  # Exit if stop signal is set during wait

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
        check_interval = 1  # seconds
        request_timeout = 5  # seconds for the HTTP request itself

        logger.info(
            f"Waiting up to {timeout}s for A2A agent at {self.a2a_server_url} to become ready..."
        )

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
                    logger.debug(
                        f"A2A agent not ready yet (Status: {response.status_code}). Retrying in {check_interval}s..."
                    )

            except requests.exceptions.ConnectionError:
                logger.debug(
                    f"A2A agent connection refused at {self.a2a_server_url}. Retrying in {check_interval}s..."
                )
            except requests.exceptions.Timeout:
                logger.warning(
                    f"Request timed out connecting to {agent_card_url}. Retrying..."
                )
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"Error checking A2A agent readiness: {e}. Retrying in {check_interval}s..."
                )

            # Use wait on the stop event for sleeping to allow faster shutdown
            if self.stop_monitor.wait(timeout=check_interval):
                logger.info("Stop signal received while waiting for agent readiness.")
                return False

        logger.error(
            f"A2A agent at {self.a2a_server_url} did not become ready within {timeout} seconds."
        )
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
                    raise TimeoutError(
                        f"Managed A2A agent at {self.a2a_server_url} did not become ready within {self.a2a_server_startup_timeout}s."
                    )
                if self.a2a_server_restart_on_crash and not self.monitor_thread:
                    self.monitor_thread = threading.Thread(
                        target=self._monitor_a2a_process, daemon=True
                    )
                    self.monitor_thread.start()
            else:
                # Check connection to existing agent (use a shorter timeout?)
                # Re-using _wait_for_agent_ready with a shorter effective timeout for a quick check
                quick_check_timeout = 5
                original_timeout = self.a2a_server_startup_timeout
                self.a2a_server_startup_timeout = quick_check_timeout
                ready = self._wait_for_agent_ready()
                self.a2a_server_startup_timeout = (
                    original_timeout  # Restore original timeout
                )
                if not ready:
                    raise ConnectionError(
                        f"Could not connect to existing A2A agent at {self.a2a_server_url} within {quick_check_timeout}s."
                    )

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
                logger.info(
                    f"Successfully fetched Agent Card for '{self.agent_card.name}'"
                )
            except Exception as e:
                logger.error(f"Error fetching/parsing Agent Card: {e}", exc_info=True)
                raise ValueError(
                    f"Failed to get Agent Card from {self.a2a_server_url}: {e}"
                ) from e

            # 3. Initialize A2AClient
            auth_token = None
            bearer_required = False
            if (
                self.agent_card.authentication
                and self.agent_card.authentication.schemes
            ):
                # Check if 'bearer' is in the list of schemes
                # Compare with string literal "bearer" for robustness against mock types
                if any(
                    str(scheme).lower() == "bearer"
                    for scheme in self.agent_card.authentication.schemes
                ):
                    bearer_required = True

            if bearer_required:
                if self.a2a_bearer_token:
                    auth_token = self.a2a_bearer_token
                    logger.info("Using configured Bearer token for A2A client.")
                else:
                    logger.warning(
                        "A2A Agent Card requires Bearer token, but none configured ('a2a_bearer_token'). Proceeding without authentication."
                    )
            # TODO: Add support for other auth schemes (e.g., apiKey) later

            try:
                # Pass agent_card
                self.a2a_client = A2AClient(agent_card=self.agent_card)
                logger.info("A2AClient initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize A2AClient: {e}", exc_info=True)
                raise ValueError(f"Could not initialize A2AClient: {e}") from e

            logger.info(
                f"A2A connection for agent '{self.agent_name}' initialized successfully."
            )

        except (TimeoutError, ConnectionError, ValueError, FileNotFoundError) as e:
            logger.error(
                f"Failed to initialize A2A connection for agent '{self.agent_name}': {e}",
                exc_info=True,
            )
            # Ensure cleanup if initialization fails partially
            self.stop_component()
            raise  # Re-raise the exception to signal failure to the framework

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
        logger.debug(
            f"Inferring parameters for skill '{skill.id}'. Using generic 'prompt'."
        )
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
        logger.info(
            f"Creating actions for agent '{self.agent_name}' based on AgentCard skills..."
        )

        if not self.agent_card or not self.agent_card.skills:
            logger.warning(
                f"No skills found in AgentCard for '{self.agent_name}'. No dynamic actions created."
            )
            # Still add the static action
        else:
            # Create dynamic actions from skills
            for skill in self.agent_card.skills:
                try:
                    inferred_params = self._infer_params_from_skill(skill)
                    action = A2AClientAction(
                        skill=skill, component=self, inferred_params=inferred_params
                    )
                    self.action_list.add_action(action)
                    logger.info(
                        f"Created action '{action.name}' for skill '{skill.id}'"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to create action for skill '{skill.id}': {e}",
                        exc_info=True,
                    )

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
                    "type": "list",  # Assuming list of strings (URLs)
                    "required": False,
                },
            ],
            "required_scopes": [f"{self.agent_name}:provide_required_input:execute"],
        }
        provide_input_action = Action(
            provide_input_action_def, agent=self, config_fn=self.get_config
        )
        # Set the handler method
        provide_input_action.set_handler(self._handle_provide_required_input)
        self.action_list.add_action(provide_input_action)
        logger.info(f"Added static action '{provide_input_action.name}'")

        # Update component description
        original_description = self.info.get(
            "description", "Component to interact with an external A2A agent."
        )
        action_names = [a.name for a in self.action_list.actions]
        if action_names:
            self.info["description"] = (
                f"{original_description}\nDiscovered Actions: {', '.join(action_names)}"
            )
        else:
            self.info["description"] = (
                f"{original_description}\nNo actions discovered or created."
            )
        logger.info(
            f"Action creation complete. Total actions: {len(self.action_list.actions)}"
        )

    def _handle_provide_required_input(
        self, params: Dict[str, Any], meta: Dict[str, Any]
    ) -> ActionResponse:
        """
        Handles the 'provide_required_input' action. Retrieves the original A2A task ID,
        sends the user's response to the A2A agent, and processes the subsequent result.
        """
        logger.info(f"Handling 'provide_required_input' with params: {params}")

        follow_up_id = params.get("follow_up_id")
        user_response_text = params.get("user_response")
        file_urls = params.get("files", [])

        # 1. Validate Input
        if not follow_up_id or not user_response_text:
            return ActionResponse(
                message="Missing required parameters: 'follow_up_id' and 'user_response'.",
                error_info=ErrorInfo("Missing Parameters"),
            )

        # 2. Check Services
        if not self.cache_service:
            logger.error(
                "CacheService not available. Cannot handle 'provide_required_input'."
            )
            return ActionResponse(
                message="Internal Error: Cache Service not available.",
                error_info=ErrorInfo("Cache Service Missing"),
            )
        if not self.a2a_client:
            logger.error(
                "A2AClient not available. Cannot handle 'provide_required_input'."
            )
            return ActionResponse(
                message="Internal Error: A2A Client not available.",
                error_info=ErrorInfo("A2A Client Missing"),
            )
        if not self.file_service:
            logger.error(
                "FileService not available. Cannot handle 'provide_required_input' with files."
            )
            return ActionResponse(
                message="Internal Error: File Service not available.",
                error_info=ErrorInfo("File Service Missing"),
            )

        # 3. Retrieve Original Task ID
        cache_key = f"a2a_follow_up:{follow_up_id}"
        try:
            a2a_taskId = self.cache_service.get(cache_key)
            if a2a_taskId is None:
                logger.warning(
                    f"Follow-up ID '{follow_up_id}' not found in cache or expired."
                )
                return ActionResponse(
                    message="Invalid or expired follow-up ID. Please start the task again.",
                    error_info=ErrorInfo("Invalid Follow-up ID"),
                )
            # Optionally delete the key now that it's used
            self.cache_service.delete(cache_key)
            logger.info(
                f"Retrieved original A2A task ID '{a2a_taskId}' for follow-up ID '{follow_up_id}'."
            )
        except Exception as e:
            logger.error(
                f"Error retrieving task ID from cache for follow-up ID '{follow_up_id}': {e}",
                exc_info=True,
            )
            return ActionResponse(
                message="Internal Error: Failed to retrieve follow-up state.",
                error_info=ErrorInfo(f"Cache Error: {e}"),
            )

        # 4. Map Input to A2A Message Parts
        session_id = meta.get(
            "session_id"
        )  # Get session_id from current invocation meta
        if not session_id:
            session_id = str(
                uuid.uuid4()
            )  # Generate if missing, though less ideal for context
            logger.warning(
                f"No session_id in meta for follow-up. Generated new one: {session_id}"
            )

        parts: List[Any] = []
        try:
            parts.append(TextPart(text=str(user_response_text)))
        except Exception as e:
            logger.error(
                f"Failed to create TextPart for follow-up response: {e}", exc_info=True
            )
            return ActionResponse(
                message="Internal Error: Could not process user response text.",
                error_info=ErrorInfo(f"TextPart Error: {e}"),
            )

        if isinstance(file_urls, str):
            file_urls = [file_urls]
        if file_urls and isinstance(file_urls, list):
            logger.info(f"Processing {len(file_urls)} file URLs for follow-up.")
            for file_url in file_urls:
                if not isinstance(file_url, str):
                    continue
                try:
                    resolved_file = self.file_service.resolve_url(
                        file_url, session_id=session_id
                    )
                    if (
                        resolved_file
                        and hasattr(resolved_file, "bytes")
                        and hasattr(resolved_file, "name")
                        and hasattr(resolved_file, "mime_type")
                    ):
                        import base64

                        encoded_bytes = base64.b64encode(resolved_file.bytes).decode(
                            "utf-8"
                        )
                        file_content = FileContent(
                            bytes=encoded_bytes,
                            name=resolved_file.name,
                            mimeType=resolved_file.mime_type,
                        )
                        parts.append(FilePart(file=file_content))
                    else:
                        logger.error(
                            f"Failed to resolve file URL '{file_url}' for follow-up."
                        )
                except Exception as e:
                    logger.error(
                        f"Error resolving file URL '{file_url}' for follow-up: {e}",
                        exc_info=True,
                    )

        # 5. Create TaskSendParams (using retrieved a2a_taskId)
        try:
            a2a_message = A2AMessage(role="user", parts=parts)
            accepted_modes = [
                "text",
                "text/plain",
                "image/*",
                "application/json",
                "application/*",
            ]
            task_params = TaskSendParams(
                id=a2a_taskId,
                sessionId=session_id,
                message=a2a_message,
                acceptedOutputModes=accepted_modes,
            )
            logger.debug(
                f"Constructed follow-up TaskSendParams for task '{a2a_taskId}': {task_params.model_dump_json(exclude_none=True)}"
            )
        except Exception as e:
            logger.error(
                f"Failed to construct follow-up TaskSendParams for task '{a2a_taskId}': {e}",
                exc_info=True,
            )
            return ActionResponse(
                message="Internal Error: Failed to prepare follow-up A2A request.",
                error_info=ErrorInfo(f"TaskSendParams Error: {e}"),
            )

        # 6. Call A2A Agent and Process Response (Re-use logic from A2AClientAction.invoke)
        # Find the original action instance to reuse its processing logic.
        # This assumes the action list is stable. A more robust way might be needed
        # if actions could be dynamically removed/added after init.
        # For simplicity, we'll call a hypothetical processing method directly.
        # We need to instantiate a dummy action or refactor the processing logic.
        # Let's refactor the response processing into a static/helper method.

        # --- Reusing processing logic ---
        # Find *any* A2AClientAction instance to call its _process_parts helper
        # This is a bit hacky, assumes at least one dynamic action exists.
        # A better approach would be to make _process_parts static or move it.
        action_instance_for_processing = None
        for act in self.action_list.actions:
            if isinstance(act, A2AClientAction):
                action_instance_for_processing = act
                break

        if not action_instance_for_processing:
            logger.error(
                "Cannot process A2A response: No A2AClientAction instance found."
            )
            return ActionResponse(
                message="Internal Error: Cannot process A2A response.",
                error_info=ErrorInfo("Processing Error"),
            )

        try:
            logger.info(f"Sending follow-up input for A2A task '{a2a_taskId}'...")
            response_task: Task = self.a2a_client.send_task(task_params.model_dump())
            task_state = getattr(getattr(response_task, "status", None), "state", None)
            logger.info(
                f"Received follow-up response for task '{a2a_taskId}'. State: {task_state}"
            )

            # Process the response using the same logic as in A2AClientAction.invoke
            if task_state == A2A_TASK_STATE_COMPLETED:
                final_message = ""
                final_files = []
                final_data = {}
                status_message = getattr(response_task.status, "message", None)
                if status_message:
                    msg_parts = getattr(status_message, "parts", [])
                    msg_text, msg_files = action_instance_for_processing._process_parts(
                        msg_parts, session_id, final_data
                    )
                    if msg_text:
                        final_message += msg_text
                    final_files.extend(msg_files)
                artifacts = getattr(response_task, "artifacts", [])
                if artifacts:
                    for artifact in artifacts:
                        artifact_parts = getattr(artifact, "parts", [])
                        art_text, art_files = (
                            action_instance_for_processing._process_parts(
                                artifact_parts, session_id, final_data
                            )
                        )
                        if art_text:
                            if final_message:
                                final_message += "\n\n--- Artifact ---\n"
                            final_message += art_text
                        final_files.extend(art_files)

                # Append final_data to message if it exists
                response_msg = final_message.strip() or "Task completed."
                if final_data:
                    try:
                        data_str = json.dumps(final_data, indent=2)
                        response_msg += f"\n\nData:\n{data_str}"
                    except Exception as json_e:
                        logger.warning(f"Could not serialize final_data to JSON: {json_e}")
                        response_msg += "\n\nData: [Could not serialize]"

                return ActionResponse(
                    message=response_msg,
                    files=final_files or None,
                    # No data parameter
                )

            elif task_state == A2A_TASK_STATE_FAILED:
                error_message = "A2A Task Failed (after follow-up)"
                error_details = ""
                status_message = getattr(response_task.status, "message", None)
                if status_message:
                    msg_parts = getattr(status_message, "parts", [])
                    if msg_parts:
                        try:
                            first_part_text = getattr(msg_parts[0], "text", "")
                            if first_part_text:
                                error_details = first_part_text
                                error_message += f": {error_details}"
                        except Exception:
                            pass
                return ActionResponse(
                    message=error_message,
                    error_info=ErrorInfo(error_details or "A2A Task Failed"),
                )

            elif task_state == A2A_TASK_STATE_INPUT_REQUIRED:
                # Handle nested input required - store new state, return new question/follow-up ID
                agent_question = "A2A Task requires further input (again)."
                status_message = getattr(response_task.status, "message", None)
                if status_message:
                    msg_parts = getattr(status_message, "parts", [])
                    if msg_parts:
                        try:
                            question_details = getattr(msg_parts[0], "text", "")
                            if question_details:
                                agent_question = question_details
                        except Exception:
                            pass

                new_sam_follow_up_id = str(uuid.uuid4())
                new_cache_key = f"a2a_follow_up:{new_sam_follow_up_id}"
                try:
                    self.cache_service.set(
                        new_cache_key, a2a_taskId, ttl=self.input_required_ttl
                    )
                    logger.info(
                        f"Stored *nested* INPUT_REQUIRED state for task '{a2a_taskId}' with follow-up ID '{new_sam_follow_up_id}'."
                    )
                    # Append follow-up ID info to the message
                    response_msg = f"{agent_question}\n\nPlease provide the required input using follow-up ID: `{new_sam_follow_up_id}`"
                    return ActionResponse(
                        message=response_msg,
                        # No data parameter
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to store nested INPUT_REQUIRED state in cache for task '{a2a_taskId}': {e}",
                        exc_info=True,
                    )
                    return ActionResponse(
                        message="Internal Error: Failed to store required input state.",
                        error_info=ErrorInfo(f"Cache Error: {e}"),
                    )
            else:
                logger.warning(
                    f"A2A Task '{a2a_taskId}' returned unhandled state after follow-up: {task_state}."
                )
                return ActionResponse(
                    message=f"A2A Task is currently in state: {task_state}",
                    error_info=ErrorInfo(f"Unhandled A2A State: {task_state}"),
                )

        except Exception as e:
            logger.error(
                f"Failed to communicate with A2A agent during follow-up for task '{a2a_taskId}': {e}",
                exc_info=True,
            )
            return ActionResponse(
                message="Failed to communicate with A2A agent during follow-up",
                error_info=ErrorInfo(f"A2A Communication Error: {e}"),
            )

    def run(self):
        """
        Main execution method called by the SAM framework.
        Initializes the A2A connection, creates actions, and then runs the base component loop.
        """
        logger.info(
            f"Starting run loop for A2AClientAgentComponent '{self.agent_name}'"
        )

        try:
            # Initialize connection and discover actions
            self._initialize_a2a_connection()

            # Create actions based on discovered skills
            self._create_actions()  # Call the action creation method

            # Signal that initialization is complete
            self._initialized.set()
            logger.info(
                f"A2AClientAgentComponent '{self.agent_name}' initialization complete."
            )

            # Call the base class run method to handle message processing etc.
            super().run()

        except (TimeoutError, ConnectionError, ValueError, FileNotFoundError) as e:
            # Initialization failed, log and stop the component thread
            logger.critical(
                f"CRITICAL: Initialization failed for A2AClientAgentComponent '{self.agent_name}': {e}. Component will not run.",
                exc_info=True,
            )
            # Ensure cleanup is called even if run loop doesn't start
            self.stop_component()
            return  # Stop the thread execution

        except Exception as e:
            # Catch any other unexpected errors during initialization or run
            logger.critical(
                f"CRITICAL: Unexpected error in A2AClientAgentComponent '{self.agent_name}' run loop: {e}",
                exc_info=True,
            )
            self.stop_component()
            return  # Stop the thread execution

        logger.info(f"Exiting run loop for A2AClientAgentComponent '{self.agent_name}'")

    def stop_component(self):
        """
        Cleans up resources when the component is stopped.
        """
        logger.info(f"Stopping A2AClientAgentComponent '{self.agent_name}'...")
        self.stop_monitor.set()

        # Terminate the managed process if it exists
        if self.a2a_process:
            logger.info(
                f"Terminating managed A2A process (PID: {self.a2a_process.pid})..."
            )
            try:
                # Send SIGTERM (terminate) first
                self.a2a_process.terminate()
                try:
                    # Wait for a short period
                    self.a2a_process.wait(timeout=5)
                    logger.info("Managed A2A process terminated gracefully.")
                except subprocess.TimeoutExpired:
                    # If it didn't terminate, send SIGKILL (kill)
                    logger.warning(
                        "Managed A2A process did not terminate gracefully after 5s, killing."
                    )
                    self.a2a_process.kill()
                    self.a2a_process.wait()  # Wait for kill to complete
                    logger.info("Managed A2A process killed.")
            except Exception as e:
                logger.error(
                    f"Error terminating managed A2A process: {e}", exc_info=True
                )
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
