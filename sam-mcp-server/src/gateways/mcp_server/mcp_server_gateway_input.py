"""Input component for the MCP Server Gateway.

This module provides the input component for the MCP Server Gateway, which
handles incoming requests from MCP clients and forwards them to the appropriate
agents.
"""

import logging
from typing import Dict, Any, Optional

from solace_ai_connector.common.message import Message
from solace_ai_connector.common.log import log
from solace_agent_mesh.gateway.components.gateway_input import GatewayInput

# Component configuration
info = {
    "class_name": "MCPServerGatewayInput",
    "description": "Input component for the MCP Server Gateway",
    "config_parameters": [
        {
            "name": "mcp_server_scopes",
            "required": False,
            "description": "Scopes to filter agents by",
            "type": "string",
            "default": "*:*:*",
        },
        {
            "name": "mcp_server_port",
            "required": False,
            "description": "Port for the MCP server",
            "type": "integer",
            "default": 8080,
        },
        {
            "name": "mcp_server_host",
            "required": False,
            "description": "Host for the MCP server",
            "type": "string",
            "default": "0.0.0.0",
        },
        {
            "name": "mcp_server_transport",
            "required": False,
            "description": "Transport for the MCP server (sse or stdio)",
            "type": "string",
            "default": "sse",
        },
    ],
}


class MCPServerGatewayInput(GatewayInput):
    """Input component for the MCP Server Gateway.

    This component handles incoming requests from MCP clients and forwards
    them to the appropriate agents.

    Attributes:
        scopes: Scopes to filter agents by.
        port: Port for the MCP server.
        host: Host for the MCP server.
        transport: Transport for the MCP server.
    """

    def __init__(self, **kwargs):
        """Initialize the MCP Server Gateway input component.

        Args:
            **kwargs: Additional keyword arguments passed to parent.
        """
        super().__init__(**kwargs)
        
        # Get configuration
        self.scopes = self.get_config("mcp_server_scopes", "*:*:*")
        self.port = self.get_config("mcp_server_port", 8080)
        self.host = self.get_config("mcp_server_host", "0.0.0.0")
        self.transport = self.get_config("mcp_server_transport", "sse")
        
        # Only log if log_identifier is available (it may not be during testing)
        if hasattr(self, 'log_identifier'):
            log.info(
                f"{self.log_identifier} Initialized MCP Server Gateway input component "
                f"with scopes={self.scopes}, port={self.port}, host={self.host}, "
                f"transport={self.transport}"
            )

    def invoke(self, message: Message, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming MCP client requests.

        Args:
            message: The input message.
            data: The input data.

        Returns:
            The processed data.
        """
        try:
            # Process the message using the parent class
            result = super().invoke(message, data)
            
            # Add MCP server specific properties
            user_properties = message.get_user_properties()
            user_properties["mcp_server_scopes"] = self.scopes
            message.set_user_properties(user_properties)
            
            return result
        except Exception as e:
            log.error(f"{self.log_identifier} Error processing MCP request: {str(e)}")
            # Return error response
            return {
                "text": f"Error processing MCP request: {str(e)}",
                "errors": [str(e)],
            }
