"""Manager for MCP server operations.

This module provides a manager class that handles MCP server operations,
including server initialization, tool registration, and request handling.
"""

import threading
from typing import Dict, Any, Optional, List, Callable

from mcp.types import Tool, Resource, Prompt, PromptArgument, CallToolResult, TextContent

from solace_ai_connector.common.log import log

from .mcp_server_factory import MCPServerFactory
from .agent_registry import AgentRegistry


class MCPServerManager:
    """Manager for MCP server operations.

    This class manages MCP server operations, including server initialization,
    tool registration, and request handling. It uses the agent registry to
    convert agent actions to MCP tools.

    Attributes:
        agent_registry: Registry of available agents.
        server_name: Name of the MCP server.
        host: Host address for the server (for SSE transport).
        port: Port for the server (for SSE transport).
        transport_type: Type of transport to use ('stdio' or 'sse').
        scopes: Scopes to filter agents by.
        server: The MCP server instance.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        server_name: str = "mcp-server",
        host: str = "0.0.0.0",
        port: int = 8080,
        transport_type: str = "stdio",
        scopes: str = "*:*:*",
    ):
        """Initialize the MCP server manager.

        Args:
            agent_registry: Registry of available agents.
            server_name: Name of the MCP server.
            host: Host address for the server (for SSE transport).
            port: Port for the server (for SSE transport).
            transport_type: Type of transport to use ('stdio' or 'sse').
            scopes: Scopes to filter agents by.
        """
        self.agent_registry = agent_registry
        self.server_name = server_name
        self.host = host
        self.port = port
        self.transport_type = transport_type
        self.scopes = scopes
        self.server = None
        self.log_identifier = f"[MCPServerManager:{server_name}] "
        
        # Lock for thread-safe operations
        self.lock = threading.Lock()
        
        # Flag to track initialization
        self.initialized = False
        
    def initialize(self) -> bool:
        """Initialize the MCP server.
        
        Returns:
            True if initialization was successful, False otherwise.
        """
        with self.lock:
            if self.initialized:
                return True
                
            try:
                # Get or create the server
                self.server = MCPServerFactory.get_server(
                    self.server_name,
                    self.host,
                    self.port,
                    self.transport_type
                )
                
                # Register tools from agent registry
                self._register_agent_tools()
                
                # Start the server
                self.server.start()
                
                self.initialized = True
                log.info(f"{self.log_identifier}Initialized MCP server")
                return True
            except Exception as e:
                log.error(
                    f"{self.log_identifier}Failed to initialize MCP server: {str(e)}",
                    exc_info=True
                )
                return False
                
    def shutdown(self) -> None:
        """Shut down the MCP server."""
        with self.lock:
            if not self.initialized:
                return
                
            MCPServerFactory.remove_server(self.server_name)
            self.server = None
            self.initialized = False
            log.info(f"{self.log_identifier}Shut down MCP server")
            
    def _register_agent_tools(self) -> None:
        """Register agent actions as MCP tools."""
        if not self.server:
            return
            
        # Get filtered agents
        agents = self.agent_registry.get_filtered_agents(self.scopes)
        
        for agent_name, agent_data in agents.items():
            actions = agent_data.get("actions", [])
            
            for action in actions:
                if not action:
                    continue
                    
                action_name = action.get("name")
                if not action_name:
                    continue
                    
                # Skip actions without parameters or with invalid parameters
                params = action.get("params", [])
                if not isinstance(params, list):
                    log.warning(
                        f"{self.log_identifier}Skipping action {agent_name}.{action_name} "
                        f"with invalid params: {params}"
                    )
                    continue
                
                # Create tool from action
                tool = self._create_tool_from_action(agent_name, action)
                
                # Create a closure to capture the current agent_name and action_name
                def create_handler(a_name, act_name):
                    return lambda args: self._handle_tool_call(a_name, act_name, args)
                
                # Register tool with server
                handler = create_handler(agent_name, action_name)
                self.server.register_tool(tool, handler)
                
                log.info(
                    f"{self.log_identifier}Registered tool {tool.name} "
                    f"for agent {agent_name}, action {action_name}"
                )
                
    def _create_tool_from_action(self, agent_name: str, action: Dict[str, Any]) -> Tool:
        """Create an MCP tool from an agent action.
        
        Args:
            agent_name: Name of the agent.
            action: Action data.
            
        Returns:
            The MCP tool.
        """
        action_name = action.get("name")
        description = action.get("description", "")
        params = action.get("params", [])
        
        # Create input schema
        properties = {}
        required = []
        
        for param in params:
            param_name = param.get("name")
            if not param_name:
                continue
                
            param_desc = param.get("desc", "")
            param_type = param.get("type", "string")
            param_required = param.get("required", False)
            
            # Map agent mesh parameter types to JSON Schema types
            json_type = "string"  # Default type
            if param_type == "number" or param_type == "integer":
                json_type = param_type
            elif param_type == "boolean":
                json_type = "boolean"
            elif param_type == "array":
                json_type = "array"
                
            properties[param_name] = {
                "type": json_type,
                "description": param_desc
            }
            
            if param_required:
                required.append(param_name)
                
        input_schema = {
            "type": "object",
            "properties": properties,
            "required": required
        }
        
        # Create tool
        return Tool(
            name=f"{agent_name}.{action_name}",
            description=f"{description} (from agent {agent_name})",
            inputSchema=input_schema
        )
        
    def _handle_tool_call(
        self, agent_name: str, action_name: str, args: Dict[str, Any]
    ) -> CallToolResult:
        """Handle a tool call.
        
        Args:
            agent_name: Name of the agent.
            action_name: Name of the action.
            args: Arguments for the action.
            
        Returns:
            The tool call result.
        """
        try:
            # Validate agent exists
            agent = self.agent_registry.get_agent(agent_name)
            if not agent:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Agent '{agent_name}' not found")],
                    isError=True
                )
                
            # Validate action exists
            action = None
            for act in agent.get("actions", []):
                if act and act.get("name") == action_name:
                    action = act
                    break
                    
            if not action:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Action '{action_name}' not found for agent '{agent_name}'")],
                    isError=True
                )
                
            # Validate parameters
            params = action.get("params", [])
            for param in params:
                param_name = param.get("name")
                param_required = param.get("required", False)
                
                if param_required and param_name not in args:
                    return CallToolResult(
                        content=[TextContent(type="text", text=f"Missing required parameter '{param_name}'")],
                        isError=True
                    )
            
            # TODO: Implement actual agent action invocation
            # This is a placeholder that will be implemented in Task 3.1
            result = f"Called {agent_name}.{action_name} with args: {args}"
            
            return CallToolResult(
                content=[TextContent(type="text", text=result)]
            )
        except Exception as e:
            log.error(
                f"{self.log_identifier}Error calling {agent_name}.{action_name}: {str(e)}",
                exc_info=True
            )
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {str(e)}")],
                isError=True
            )
            
    def update_agent_registry(self) -> None:
        """Update the server with the latest agent registry."""
        with self.lock:
            if not self.initialized:
                return
                
            # Re-register tools
            self._register_agent_tools()
