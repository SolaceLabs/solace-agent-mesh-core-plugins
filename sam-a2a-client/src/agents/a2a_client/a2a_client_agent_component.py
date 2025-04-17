"""
Main component for the SAM A2A Client Plugin.

This component manages the connection to an external A2A agent,
discovers its capabilities, and exposes them as SAM actions.
"""
import copy
import threading
import logging
import subprocess # Added import
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
        self.a2a_process: Optional[subprocess.Popen] = None # type: ignore # subprocess not yet imported
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


    # Placeholder for stop_component method (Step 1.2.5)
    def stop_component(self):
        pass
