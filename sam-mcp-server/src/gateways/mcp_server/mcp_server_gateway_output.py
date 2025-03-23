"""Output component for the MCP Server Gateway.

This module provides the output component for the MCP Server Gateway, which
handles responses from agents and forwards them to MCP clients.
"""

import logging
from typing import Dict, Any, Optional, List

from solace_ai_connector.common.message import Message
from solace_ai_connector.common.log import log
from solace_agent_mesh.gateway.components.gateway_output import GatewayOutput
from .agent_registry import AgentRegistry

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
        {
            "name": "agent_ttl_ms",
            "required": False,
            "description": "Time-to-live for agent registrations in milliseconds",
            "type": "integer",
            "default": 60000,
        },
        {
            "name": "agent_cleanup_interval_ms",
            "required": False,
            "description": "Interval in milliseconds for cleaning up expired agents",
            "type": "integer",
            "default": 60000,
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
        
        # Initialize agent registry with TTL from config
        ttl_ms = self.get_config("agent_ttl_ms", 60000)
        self.agent_registry = AgentRegistry(ttl_ms=ttl_ms)
        
        # Only log if log_identifier is available (it may not be during testing)
        if hasattr(self, 'log_identifier'):
            log.info(
                f"{self.log_identifier} Initialized MCP Server Gateway output component "
                f"with scopes={self.scopes}"
            )
            
        # Set up timer for periodic cleanup of expired agents
        cleanup_interval_ms = self.get_config("agent_cleanup_interval_ms", 60000)
        if hasattr(self, 'add_timer'):
            self.add_timer(cleanup_interval_ms, "agent_registry_cleanup", cleanup_interval_ms)

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
            error_msg = f"Error processing agent response: {str(e)}"
            log.error(f"{self.log_identifier} {error_msg}")
            # Return error response with properly formatted errors list
            return {
                "text": error_msg,
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
            
            # Register agent in the registry
            self.agent_registry.register_agent(data)
            
            log.info(f"{self.log_identifier} Registered agent: {agent_name}")
            
            # Periodically clean up expired agents
            expired_agents = self.agent_registry.cleanup_expired_agents()
            if expired_agents:
                log.info(f"{self.log_identifier} Removed expired agents: {', '.join(expired_agents)}")
                
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
            
        # Add agent information if available
        topic = message.get_topic()
        if "actionResponse/agent" in topic:
            # Extract agent name from topic
            parts = topic.split("/")
            if len(parts) >= 4:
                agent_name = parts[3]
                agent = self.agent_registry.get_agent(agent_name)
                if agent:
                    result["agent_info"] = {
                        "name": agent_name,
                        "description": agent.get("description", "")
                    }
        
        return result

    def handle_timer_event(self, timer_data):
        """Handle timer events for the component.
        
        Args:
            timer_data: Data associated with the timer event.
        """
        if timer_data == "agent_registry_cleanup":
            expired_agents = self.agent_registry.cleanup_expired_agents()
            if expired_agents and hasattr(self, 'log_identifier'):
                log.info(f"{self.log_identifier} Timer cleanup removed expired agents: {', '.join(expired_agents)}")
    def get_filtered_agents(self) -> Dict[str, Dict[str, Any]]:
        """Get agents filtered by configured scopes.
        
        Returns:
            Dictionary of agents matching the scope pattern.
        """
        return self.agent_registry.get_filtered_agents(self.scopes)
