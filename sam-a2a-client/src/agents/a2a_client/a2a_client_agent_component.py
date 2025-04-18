import copy
import threading
import logging
from typing import Dict, Any, Optional

from solace_agent_mesh.agents.base_agent_component import (
    BaseAgentComponent,
    agent_info as base_agent_info,
)
from solace_agent_mesh.common.action_list import ActionList
from solace_agent_mesh.services.file_service import FileService

# Import helpers
from .a2a_process_manager import A2AProcessManager
from .a2a_connection_handler import A2AConnectionHandler
from .a2a_action_factory import create_actions_from_card, create_provide_input_action
from .a2a_input_handler import handle_provide_required_input

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

logger = logging.getLogger(__name__)


class A2AClientAgentComponent(BaseAgentComponent):
    """
    SAM Agent Component that acts as a client to an external A2A agent.
    Uses helper classes for process management and connection handling.
    """

    info = info

    def __init__(self, module_info: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(module_info or info, **kwargs)
        logger.info(
            f"Initializing A2AClientAgentComponent for agent '{self.get_config('agent_name', 'UNKNOWN')}'"
        )

        # Configuration
        self.agent_name: str = self.get_config("agent_name")
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
            logger.warning(
                "Cache service not provided to A2AClientAgentComponent. INPUT_REQUIRED state will not be supported."
            )

        # Action List (initially empty)
        self.action_list = ActionList([], agent=self, config_fn=self.get_config)

        # Update component info
        self.info["agent_name"] = self.agent_name
        logger.info(f"A2AClientAgentComponent '{self.agent_name}' initialized.")

    # --- Properties to access underlying client/card ---
    @property
    def a2a_client(self):
        return self.connection_handler.a2a_client if self.connection_handler else None

    @property
    def agent_card(self):
        return self.connection_handler.agent_card if self.connection_handler else None

    # --- Lifecycle Methods ---
    def run(self):
        logger.info(
            f"Starting run loop for A2AClientAgentComponent '{self.agent_name}'"
        )
        try:
            # 1. Initialize Process Manager (if command provided)
            if self.a2a_server_command:
                self.process_manager = A2AProcessManager(
                    command=self.a2a_server_command,
                    restart_on_crash=self.a2a_server_restart_on_crash,
                    agent_name=self.agent_name,
                    stop_event=self.stop_monitor,
                )
                self.process_manager.launch()

            # 2. Initialize Connection Handler
            self.connection_handler = A2AConnectionHandler(
                server_url=self.a2a_server_url,
                startup_timeout=self.a2a_server_startup_timeout,
                bearer_token=self.a2a_bearer_token,
                stop_event=self.stop_monitor,
            )

            # 3. Wait for Readiness and Initialize Client
            if not self.connection_handler.wait_for_ready():
                raise TimeoutError(
                    f"A2A agent at {self.a2a_server_url} did not become ready within {self.a2a_server_startup_timeout}s."
                )
            self.connection_handler.initialize_client()

            # 4. Create Actions
            dynamic_actions = create_actions_from_card(self.agent_card, self)
            static_action = create_provide_input_action(self)
            static_action.set_handler(
                lambda params, meta: handle_provide_required_input(self, params, meta)
            )
            # Add actions individually
            for action in dynamic_actions:
                self.action_list.add_action(action)
            self.action_list.add_action(static_action)


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

            # 5. Start Process Monitor (if applicable)
            if self.process_manager:
                self.process_manager.start_monitor()

            # 6. Signal Initialization Complete and Run Base Loop
            self._initialized.set()
            logger.info(
                f"A2AClientAgentComponent '{self.agent_name}' initialization complete."
            )
            super().run()

        except (TimeoutError, ConnectionError, ValueError, FileNotFoundError) as e:
            logger.critical(
                f"CRITICAL: Initialization failed for A2AClientAgentComponent '{self.agent_name}': {e}. Component will not run.",
                exc_info=True,
            )
            self.stop_component()
            return
        except Exception as e:
            logger.critical(
                f"CRITICAL: Unexpected error in A2AClientAgentComponent '{self.agent_name}' run loop: {e}",
                exc_info=True,
            )
            self.stop_component()
            return

        logger.info(f"Exiting run loop for A2AClientAgentComponent '{self.agent_name}'")

    def stop_component(self):
        logger.info(f"Stopping A2AClientAgentComponent '{self.agent_name}'...")
        self.stop_monitor.set()

        if self.process_manager:
            self.process_manager.stop()
            self.process_manager = None

        # Reset connection handler state
        if self.connection_handler:
            self.connection_handler.agent_card = None
            self.connection_handler.a2a_client = None
            self.connection_handler = None

        super().stop_component()
        logger.info(f"A2AClientAgentComponent '{self.agent_name}' stopped.")

    # --- Helper Methods ---
    # (Keep _infer_params_from_skill here or move to factory if preferred)
    def _infer_params_from_skill(self, skill: Any) -> list[dict[str, Any]]:
        """
        Infers SAM action parameters from an A2A skill.
        Simple initial implementation: always returns a generic 'prompt' and 'files'.
        """
        logger.debug(
            f"Inferring parameters for skill '{getattr(skill, 'id', 'UNKNOWN')}'. Using generic 'prompt' and 'files'."
        )
        return [
            {
                "name": "prompt",
                "desc": "The user request or prompt for the agent.",
                "type": "string",
                "required": True,
            },
            {
                "name": "files",
                "desc": "Optional list of file URLs to include with the prompt.",
                "type": "list",
                "required": False,
            },
        ]

    def _handle_provide_required_input(
        self, params: Dict[str, Any], meta: Dict[str, Any]
    ) -> Any: # Return type should be ActionResponse
        """Wrapper to call the input handler function."""
        return handle_provide_required_input(self, params, meta)
