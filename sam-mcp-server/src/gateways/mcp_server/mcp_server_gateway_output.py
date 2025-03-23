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
from .agent_registration_listener import AgentRegistrationListener

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

        # Initialize agent registration listener
        cleanup_interval_ms = self.get_config("agent_cleanup_interval_ms", 60000)
        self.registration_listener = AgentRegistrationListener(
            self.agent_registry,
            cleanup_interval_ms,
            on_agent_added=self._on_agent_added,
            on_agent_removed=self._on_agent_removed,
        )
        self.registration_listener.start()
        
        # Cache for server managers
        self.server_managers = {}

        # Only log if log_identifier is available (it may not be during testing)
        if hasattr(self, "log_identifier"):
            log.info(
                f"{self.log_identifier} Initialized MCP Server Gateway output component "
                f"with scopes={self.scopes}"
            )

    def _handle_timeout_response(
        self, message: Message, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle timeout response messages.

        Args:
            message: The input message.
            data: The timeout response data.

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
            
            # Forward the timeout to the MCP server manager if it exists
            server_name = user_properties.get("gateway_id")
            if server_name:
                # Get the server instance
                server_manager = self._get_server_manager(server_name)
                if server_manager:
                    # Forward the timeout to the server manager
                    success = server_manager.handle_action_response(
                        correlation_id, 
                        {
                            "error": "Request timed out",
                            "message": f"The request timed out: {data.get('message', 'No details available')}"
                        }
                    )
                    if success:
                        log.info(
                            f"{self.log_identifier} Successfully forwarded timeout for "
                            f"correlation ID {correlation_id} to MCP server {server_name}"
                        )
                    else:
                        log.warning(
                            f"{self.log_identifier} Failed to forward timeout for "
                            f"correlation ID {correlation_id} to MCP server {server_name}"
                        )

        # Extract agent name from topic
        topic = message.get_topic()
        parts = topic.split("/")
        if len(parts) >= 5:
            agent_name = parts[4]
            result["agent_info"] = {
                "name": agent_name,
                "description": "Request timed out",
            }

        return result

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
                # Check if it's a timeout response
                if "/timeout" in topic:
                    return self._handle_timeout_response(message, data)
                return self._handle_agent_response(message, data)

            # Periodically clean up server managers and their pending requests
            self._cleanup_server_managers()

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
        # Process the registration using the listener
        self.registration_listener.process_registration(data)

    def _get_server_manager(self, server_name: str):
        """Get or create a server manager for the given server name.
        
        Args:
            server_name: Name of the MCP server.
            
        Returns:
            The server manager instance, or None if it couldn't be created.
        """
        if server_name in self.server_managers:
            return self.server_managers[server_name]
            
        try:
            # Import here to avoid circular imports
            from .mcp_server_manager import MCPServerManager
            
            # Create a new server manager
            manager = MCPServerManager(
                agent_registry=self.agent_registry,
                server_name=server_name,
                scopes=self.scopes
            )
            
            # Initialize the manager
            if manager.initialize():
                self.server_managers[server_name] = manager
                return manager
            else:
                log.error(
                    f"{self.log_identifier} Failed to initialize MCP server manager for {server_name}"
                )
                return None
        except Exception as e:
            log.error(
                f"{self.log_identifier} Error creating MCP server manager for {server_name}: {str(e)}",
                exc_info=True
            )
            return None
            
    def _handle_agent_response(
        self, message: Message, data: Dict[str, Any]
    ) -> Dict[str, Any]:
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
            
            # Forward the response to the MCP server manager if it exists
            from .mcp_server_factory import MCPServerFactory
            
            # Extract server name from user properties
            server_name = user_properties.get("gateway_id")
            if server_name:
                # Get the server instance
                server_manager = self._get_server_manager(server_name)
                if server_manager:
                    # Forward the response to the server manager
                    success = server_manager.handle_action_response(correlation_id, data)
                    if success:
                        log.info(
                            f"{self.log_identifier} Successfully forwarded response for "
                            f"correlation ID {correlation_id} to MCP server {server_name}"
                        )
                    else:
                        log.warning(
                            f"{self.log_identifier} Failed to forward response for "
                            f"correlation ID {correlation_id} to MCP server {server_name}"
                        )

        # Add agent information if available
        topic = message.get_topic()
        if "actionResponse/agent" in topic:
            # Extract agent name from topic
            parts = topic.split("/")
            if len(parts) >= 5:
                agent_name = parts[4]
                agent = self.agent_registry.get_agent(agent_name)
                if agent:
                    result["agent_info"] = {
                        "name": agent_name,
                        "description": agent.get("description", ""),
                    }

        return result
        
    def _cleanup_server_managers(self):
        """Clean up server managers and their pending requests.
        
        This method iterates through all server managers and calls
        cleanup_pending_requests on each one to remove timed out requests.
        """
        if hasattr(self, "server_managers"):
            for server_name, manager in list(self.server_managers.items()):
                try:
                    cleaned_up = manager.cleanup_pending_requests()
                    if cleaned_up:
                        log.info(
                            f"{self.log_identifier} Cleaned up {len(cleaned_up)} timed out "
                            f"requests for server {server_name}"
                        )
                except Exception as e:
                    log.error(
                        f"{self.log_identifier} Error cleaning up server manager {server_name}: {str(e)}",
                        exc_info=True
                    )

    def _on_agent_added(self, agent_name: str, agent_data: Dict[str, Any]):
        """Callback when an agent is added to the registry.

        Args:
            agent_name: Name of the agent that was added.
            agent_data: Data for the agent that was added.
        """
        if hasattr(self, "log_identifier"):
            log.info(f"{self.log_identifier} Agent added to registry: {agent_name}")

    def _on_agent_removed(self, agent_name: str):
        """Callback when an agent is removed from the registry.

        Args:
            agent_name: Name of the agent that was removed.
        """
        if hasattr(self, "log_identifier"):
            log.info(f"{self.log_identifier} Agent removed from registry: {agent_name}")

    def get_filtered_agents(self) -> Dict[str, Dict[str, Any]]:
        """Get agents filtered by configured scopes.

        Returns:
            Dictionary of agents matching the scope pattern.
        """
        return self.agent_registry.get_filtered_agents(self.scopes)

    def stop_component(self):
        """Stop the component and clean up resources."""
        if hasattr(self, "registration_listener") and self.registration_listener:
            self.registration_listener.stop()
            
        # Shut down all server managers
        if hasattr(self, "server_managers"):
            for manager in list(self.server_managers.values()):
                manager.shutdown()
            self.server_managers.clear()
            
        super().stop_component()
