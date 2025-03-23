"""Output component for the MCP Server Gateway.

This module provides the output component for the MCP Server Gateway, which
handles responses from agents and forwards them to MCP clients.
"""

import logging
from typing import Dict, Any, Optional, List

from solace_ai_connector.common.message import Message
from solace_ai_connector.common.log import log
from solace_agent_mesh.gateway.components.gateway_output import GatewayOutput

# Component configuration
info = {
    "class_name": "MCPServerGatewayOutput",
    "description": "Output component for the MCP Server Gateway",
    "config_parameters": [
        {
            "name": "mcp_server_scopes",
            "required": False,
            "description": "Scopes to filter agents by",
            "type": "string",
            "default": "*:*:*",
        },
    ],
}


class MCPServerGatewayOutput(GatewayOutput):
    """Output component for the MCP Server Gateway.

    This component handles responses from agents and forwards them to MCP clients.

    Attributes:
        scopes: Scopes to filter agents by.
        agent_registry: Registry of available agents.
    """

    def __init__(self, **kwargs):
        """Initialize the MCP Server Gateway output component.

        Args:
            **kwargs: Additional keyword arguments passed to parent.
        """
        super().__init__(**kwargs)
        
        # Get configuration
        self.scopes = self.get_config("mcp_server_scopes", "*:*:*")
        
        # Initialize agent registry
        self.agent_registry = {}
        
        log.info(
            f"{self.log_identifier} Initialized MCP Server Gateway output component "
            f"with scopes={self.scopes}"
        )

    def invoke(self, message: Message, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process responses from agents.

        Args:
            message: The input message.
            data: The input data.

        Returns:
            The processed data.
        """
        try:
            # Get message topic to determine message type
            topic = message.get_topic()
            
            # Handle agent registration
            if "register/agent" in topic:
                self._handle_agent_registration(data)
                self.discard_current_message()
                return None
            
            # Handle agent responses
            if "actionResponse/agent" in topic:
                return self._handle_agent_response(message, data)
            
            # Process other messages using the parent class
            return super().invoke(message, data)
        except Exception as e:
            log.error(f"{self.log_identifier} Error processing agent response: {str(e)}")
            # Return error response
            return {
                "text": f"Error processing agent response: {str(e)}",
                "errors": [str(e)],
            }

    def _handle_agent_registration(self, data: Dict[str, Any]) -> None:
        """Handle agent registration messages.

        Args:
            data: The agent registration data.
        """
        try:
            agent_name = data.get("agent_name")
            if not agent_name:
                log.warning(f"{self.log_identifier} Received agent registration without name")
                return
            
            # Store agent information in registry
            self.agent_registry[agent_name] = {
                "name": agent_name,
                "description": data.get("description", ""),
                "actions": data.get("actions", []),
                "always_open": data.get("always_open", False),
                "last_updated": self._get_current_time(),
            }
            
            log.info(f"{self.log_identifier} Registered agent: {agent_name}")
        except Exception as e:
            log.error(f"{self.log_identifier} Error handling agent registration: {str(e)}")

    def _handle_agent_response(self, message: Message, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent response messages.

        Args:
            message: The input message.
            data: The agent response data.

        Returns:
            The processed response data.
        """
        # Process the message using the parent class
        result = super().invoke(message, data)
        
        # Add MCP server specific properties
        user_properties = message.get_user_properties()
        correlation_id = user_properties.get("mcp_correlation_id")
        if correlation_id:
            result["mcp_correlation_id"] = correlation_id
        
        return result

    def _get_current_time(self) -> int:
        """Get current time in milliseconds.

        Returns:
            Current time in milliseconds.
        """
        import time
        return int(time.time() * 1000)
