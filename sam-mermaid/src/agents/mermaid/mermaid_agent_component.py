"""The agent component for the mermaid"""

import os
import copy
import sys
from typing import Dict, Any

from .actions.mermaid_draw import DrawAction

from solace_agent_mesh.agents.base_agent_component import (
    agent_info,
    BaseAgentComponent,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(SCRIPT_DIR))


info = copy.deepcopy(agent_info)
info.update(
    {
        "agent_name": None,  # Template variable replaced at agent creation
        "class_name": "MermaidAgentComponent",
        "description": "Generates diagrams from Mermaid.js syntax using a mermaid-server.",  # Base description
        "config_parameters": [
            {
                "name": "agent_name",
                "required": True,
                "description": "Name of this Mermaid agent instance (used for topics, queues, etc.)",
                "type": "string",
            },
            {
                "name": "mermaid_server_url",
                "required": True,
                "description": "URL of the mermaid-server instance. Set via {{SNAKE_UPPER_CASE_NAME}}_MERMAID_SERVER_URL env var.",
                "type": "string",
            },
        ],
    }
)


class MermaidAgentComponent(BaseAgentComponent):
    """Component for generating diagrams using Mermaid.js syntax via a mermaid-server."""

    info = info
    actions = [DrawAction]

    def __init__(self, module_info: Dict[str, Any] = None, **kwargs):
        """Initialize the Mermaid agent component."""
        module_info = module_info or info
        super().__init__(module_info, **kwargs)

        # Get core config values
        self.agent_name = self.get_config("agent_name")
        mermaid_server_url = self.get_config("mermaid_server_url")

        # Validate required configuration
        if not mermaid_server_url:
            raise ValueError(
                f"Mermaid server URL is not configured for agent '{self.agent_name}'. "
                f"Please set the {self.agent_name.upper()}_MERMAID_SERVER_URL environment variable."
            )
        # Note: mermaid_server_url is retrieved via get_config but not stored directly on self
        # Actions will retrieve it via self.parent_component.get_config()

        # Update component info with specific instance details
        module_info["agent_name"] = self.agent_name
        module_info["description"] = (  # Update description with instance name
            f"Generates diagrams from Mermaid.js syntax for the '{self.agent_name}' instance."
        )
        self.info = module_info  # Ensure self.info uses the updated module_info

        # Update action scopes
        self.action_list.fix_scopes("<agent_name>", self.agent_name)

    def get_agent_summary(self):
        """Get a summary of the agent's capabilities."""
        summary = {
            "agent_name": self.agent_name,
            "description": self.info.get(
                "description", "Generates diagrams from Mermaid.js syntax."
            ),
            "always_open": self.info.get("always_open", False),
            "actions": self.get_actions_summary(),
        }
        return summary
