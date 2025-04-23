"""
Main SAM Agent Component for interacting with external A2A agents.

This component manages the connection to an A2A agent (either by launching
a process or connecting to an existing URL), discovers its capabilities (skills)
via its AgentCard, dynamically creates corresponding SAM Actions, and handles
the invocation of those actions, including managing the INPUT_REQUIRED state.
"""

import copy
import threading
from typing import Dict, Any, Optional, List

from solace_agent_mesh.agents.base_agent_component import (
    BaseAgentComponent,
    agent_info as base_agent_info,
)
from solace_agent_mesh.common.action_list import ActionList
from solace_agent_mesh.services.file_service import FileService
from solace_agent_mesh.common.action_response import ActionResponse
from solace_ai_connector.common.log import log  # Use solace-ai-connector log

# Import helpers and types
from .a2a_process_manager import A2AProcessManager
from .a2a_connection_handler import A2AConnectionHandler
from .a2a_action_factory import (
    create_actions_from_card,
    create_provide_input_action,
    infer_params_from_skill,  # Import the function directly
)
from .a2a_input_handler import (
    handle_provide_required_input,
)  # Import the handler function
from ...common_a2a.types import AgentCard, AgentSkill
from ...common_a2a.client import A2AClient

# Define component configuration schema by extending the base
info = copy.deepcopy(base_agent_info)
info.update(
    {
        "class_name": "A2AClientAgentComponent",
        "description": "Component to interact with an external A2A agent.",
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
    }
)


class A2AClientAgentComponent(BaseAgentComponent):
    """
    SAM Agent Component that acts as a client to an external A2A agent.

    This component initializes and manages the connection to a target A2A agent,
    discovers its skills, creates corresponding SAM actions, and handles the
    invocation flow, including managing the `INPUT_REQUIRED` state using the
    Cache Service. It can optionally manage the lifecycle of the A2A agent process.

    Attributes:
        agent_name (str): Unique name for this SAM agent instance.
        a2a_server_url (str): URL of the target A2A agent.
        a2a_server_command (Optional[str]): Command to launch the A2A agent process.
        a2a_server_startup_timeout (int): Timeout for agent readiness check.
        a2a_server_restart_on_crash (bool): Whether to restart the managed process.
        a2a_bearer_token (Optional[str]): Bearer token for A2A requests.
        input_required_ttl (int): TTL for INPUT_REQUIRED state cache entries.
        stop_monitor (threading.Event): Event to signal termination to helper threads.
        _initialized (threading.Event): Event set when initialization is complete.
        process_manager (Optional[A2AProcessManager]): Helper for managing the A2A process.
        connection_handler (Optional[A2AConnectionHandler]): Helper for managing the connection.
        file_service (FileService): SAM File Service instance.
        cache_service (Optional[Any]): SAM Cache Service instance.
        action_list (ActionList): List of actions exposed by this component.
    """

    actions = []  # Actions will be dynamically created based on the AgentCard

    def __init__(self, module_info: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initializes the A2AClientAgentComponent.

        Args:
            module_info: Component configuration information.
            **kwargs: Additional keyword arguments, including core services like 'cache_service'.
        """
        self.info = copy.deepcopy(info)
        super().__init__(module_info or self.info, **kwargs)
        self.agent_name: str = self.get_config("agent_name")
        if not self.agent_name:
            # This should ideally be caught by SAM core config validation, but added for safety
            raise ValueError("Missing required configuration: 'agent_name'")

        log.debug(
            "Initializing A2AClientAgentComponent for agent '%s'", self.agent_name
        )

        # Configuration
        self.a2a_server_url: str = self.get_config("a2a_server_url")
        self.a2a_server_command: Optional[str] = self.get_config("a2a_server_command")
        self.a2a_server_startup_timeout: int = self.get_config(
            "a2a_server_startup_timeout"
        )
        self.a2a_server_restart_on_crash: bool = self.get_config(
            "a2a_server_restart_on_crash"
        )
        self.a2a_bearer_token: Optional[str] = self.get_config("a2a_bearer_token")
        self.input_required_ttl: int = self.get_config("input_required_ttl")

        # State & Helpers
        self.stop_monitor = threading.Event()  # Used by both manager and handler
        self._initialized = threading.Event()
        self.process_manager: Optional[A2AProcessManager] = None
        self.connection_handler: Optional[A2AConnectionHandler] = None

        # SAM Services
        self.file_service = FileService()
        self.cache_service = kwargs.get("cache_service")
        if self.cache_service is None:
            log.warning(
                "Cache service not provided to A2AClientAgentComponent. INPUT_REQUIRED state will not be supported."
            )

        # Action List (initially empty, populated in run)
        self.action_list = ActionList([], agent=self, config_fn=self.get_config)

        # Update component info (agent_name is crucial for registration)
        self.info["agent_name"] = self.agent_name
        log.info(
            "A2AClientAgentComponent '%s' initialized configuration.", self.agent_name
        )

    # --- Properties to access underlying client/card ---
    @property
    def a2a_client(self) -> Optional[A2AClient]:
        """Provides access to the initialized A2AClient instance."""
        return self.connection_handler.a2a_client if self.connection_handler else None

    @property
    def agent_card(self) -> Optional[AgentCard]:
        """Provides access to the fetched AgentCard."""
        return self.connection_handler.agent_card if self.connection_handler else None

    # --- Lifecycle Methods ---
    def run(self):
        """
        Starts the component's main execution loop.

        Initializes the connection to the A2A agent (launching if necessary),
        discovers skills, creates actions, starts monitoring (if applicable),
        and then enters the base component's run loop for handling messages
        and timers (like registration).
        """
        log.debug("Starting run loop for A2AClientAgentComponent '%s'", self.agent_name)
        try:
            # 1. Initialize Process Manager (if command provided)
            if self.a2a_server_command:
                log.debug("Initializing A2AProcessManager for '%s'.", self.agent_name)
                self.process_manager = A2AProcessManager(
                    command=self.a2a_server_command,
                    restart_on_crash=self.a2a_server_restart_on_crash,
                    agent_name=self.agent_name,
                    stop_event=self.stop_monitor,
                )
                self.process_manager.launch()  # Can raise FileNotFoundError etc.
                log.debug("A2A process launched for '%s'.", self.agent_name)

            # 2. Initialize Connection Handler
            log.debug("Initializing A2AConnectionHandler for '%s'.", self.agent_name)
            self.connection_handler = A2AConnectionHandler(
                server_url=self.a2a_server_url,
                bearer_token=self.a2a_bearer_token,
                stop_event=self.stop_monitor,
            )

            # 3. Wait for Readiness and Initialize Client
            log.debug("Waiting for A2A agent '%s' to become ready...", self.agent_name)
            if not self.connection_handler.wait_for_ready(
                self.a2a_server_startup_timeout
            ):
                # Error logged within wait_for_ready
                raise TimeoutError(
                    f"A2A agent at {self.a2a_server_url} did not become ready within {self.a2a_server_startup_timeout}s."
                )
            self.connection_handler.initialize_client()  # Can raise ValueError

            # 4. Create Actions
            self._create_actions()

            # 5. Start Process Monitor (if applicable)
            if self.process_manager:
                self.process_manager.start_monitor()

            # 6. Signal Initialization Complete and Run Base Loop
            self._initialized.set()
            log.debug(
                "A2AClientAgentComponent '%s' initialization complete. Entering main loop.",
                self.agent_name,
            )
            # Call the base class run method which handles message processing and registration timers
            super().run()

        except (TimeoutError, ConnectionError, ValueError, FileNotFoundError) as e:
            log.critical(
                "CRITICAL: Initialization failed for A2AClientAgentComponent '%s': %s. Component will not run.",
                self.agent_name,
                e,
                exc_info=True,
            )
            self.stop_component()  # Attempt cleanup
            # Do not proceed to super().run()
            return
        except Exception as e:
            # Catch any other unexpected errors during setup
            log.critical(
                "CRITICAL: Unexpected error during A2AClientAgentComponent '%s' setup: %s",
                self.agent_name,
                e,
                exc_info=True,
            )
            self.stop_component()  # Attempt cleanup
            # Do not proceed to super().run()
            return

        log.info("Exiting run loop for A2AClientAgentComponent '%s'", self.agent_name)

    def stop_component(self):
        """
        Stops the component, terminating the managed A2A process (if any)
        and signaling helper threads to exit.
        """
        log.info("Stopping A2AClientAgentComponent '%s'...", self.agent_name)
        self.stop_monitor.set()  # Signal monitor thread and connection handler waits

        if self.process_manager:
            self.process_manager.stop()
            self.process_manager = None

        # Reset connection handler state (client and card)
        if self.connection_handler:
            # No explicit stop needed for handler, but clear refs
            self.connection_handler.agent_card = None
            self.connection_handler.a2a_client = None
            self.connection_handler = None

        # Reset initialization state
        self._initialized.clear()

        super().stop_component()  # Call base class cleanup
        log.info("A2AClientAgentComponent '%s' stopped.", self.agent_name)

    # --- Helper Methods ---

    def _create_actions(self):
        """
        Creates dynamic actions based on the fetched AgentCard and adds the
        static 'provide_required_input' action. Updates the component description.
        """
        log.info("Creating SAM actions for '%s'...", self.agent_name)
        dynamic_actions = create_actions_from_card(self.agent_card, self)
        static_action = create_provide_input_action(self)

        # Set the handler for the static action to the component's method
        # The ProvideInputAction class now handles calling the component method.
        # No explicit set_handler call needed here if using the ProvideInputAction class.

        # Add actions individually to the list
        for action in dynamic_actions:
            self.action_list.add_action(action)
        self.action_list.add_action(static_action)

        # Update component description with discovered actions
        original_description = self.info.get(
            "description", "Component to interact with an external A2A agent."
        )
        action_names = [
            a.name for a in self.action_list.actions if a.name != static_action.name
        ]  # Exclude static action from list
        if action_names:
            self.info["description"] = (
                f"{original_description}\nDiscovered Actions: {', '.join(action_names)}"
            )
        else:
            self.info["description"] = (
                f"{original_description}\nNo dynamic actions discovered."
            )
        log.info(
            "Action creation complete for '%s'. Total actions: %d",
            self.agent_name,
            len(self.action_list.actions),
        )

    def _handle_provide_required_input(
        self, params: Dict[str, Any], meta: Dict[str, Any]
    ) -> ActionResponse:
        """
        Wrapper method to handle the 'provide_required_input' static action.
        Delegates the actual logic to the handler function from a2a_input_handler.

        Args:
            params: Parameters provided to the action (follow_up_id, user_response, files).
            meta: Metadata associated with the action invocation (session_id).

        Returns:
            An ActionResponse containing the result of the follow-up A2A call.
        """
        # This method acts as the entry point registered with the static Action instance.
        # It calls the separate handler function, passing 'self' (the component instance).
        return handle_provide_required_input(self, params, meta)
