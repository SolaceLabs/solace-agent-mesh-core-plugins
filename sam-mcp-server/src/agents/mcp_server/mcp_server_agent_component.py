"""Agent component for exposing MCP servers within solace-agent-mesh.

This module provides a component that loads and exposes MCP servers as solace-agent-mesh
agents, converting their capabilities into actions.
"""

import copy
from typing import Dict, Any, Optional

from solace_agent_mesh.agents.base_agent_component import (
    agent_info,
    BaseAgentComponent,
)
import mcp.types as types
from mcp.shared.session import RequestResponder

from solace_ai_connector.common.log import log

from .actions.mcp_server_action import MCPServerAction


# Component configuration
info = copy.deepcopy(agent_info)
info.update(
    {
        "agent_name": None,  # Will be set from configuration
        "class_name": "McpServerAgentComponent",
        "description": None,  # Will be set from configuration
        "config_parameters": [
            {
                "name": "server_name",
                "required": True,
                "description": "Name of the MCP server",
                "type": "string",
            },
            {
                "name": "server_description",
                "required": True,
                "description": "Description of the MCP server",
                "type": "string",
            },
            {
                "name": "mode",
                "required": False,
                "description": "Communication mode: 'sse' or 'stdio'",
                "type": "string",
                "default": "stdio",
            },
            {
                "name": "timeout",
                "required": False,
                "description": "Request timeout in seconds for all modes",
                "type": "integer",
                "default": 90,
            },
            {
                "name": "sse_base_url",
                "required": False,
                "description": "Base URL for HTTP mode",
                "type": "string",
            },
            {
                "name": "sse_timeout",
                "required": False,
                "description": "SSE request timeout in seconds",
                "type": "integer",
                "default": 90,
            },
            {
                "name": "sse_max_retries",
                "required": False,
                "description": "Maximum number of SSE retry attempts",
                "type": "integer",
                "default": 3,
            },
            {
                "name": "sse_retry_delay",
                "required": False,
                "description": "Delay between SSE retries in seconds",
                "type": "integer",
                "default": 30,
            },
            {
                "name": "server_command",
                "required": False,
                "description": "Shell command to start the MCP server (required for stdio mode)",
                "type": "string",
            },
            {
                "name": "server_startup_timeout",
                "required": False,
                "description": "Timeout in seconds to wait for server to start",
                "type": "integer",
                "default": 30,
            },
            # Sampling support is not needed in Solace Agent Mesh context
            # Agents handle their own LLM requests directly
        ],
    }
)


class McpServerAgentComponent(BaseAgentComponent):
    """Component for exposing MCP servers within solace-agent-mesh.

    This component loads an MCP server module and exposes its capabilities
    (tools, resources, prompts) as solace-agent-mesh actions.

    Attributes:
        info: Component configuration and metadata.
        actions: List of actions exposed by this component.
    """

    info = info
    actions = []  # Will be populated from MCP server capabilities

    def __init__(self, module_info: Optional[Dict[str, Any]] = None, **kwargs) -> None:
        """Initialize the MCP server agent component.

        Args:
            module_info: Optional module configuration dictionary.
            **kwargs: Additional keyword arguments passed to parent.

        Raises:
            ValueError: If server configuration is invalid or server fails to load.
        """
        module_info = module_info or info

        # Call the parent constructor
        super().__init__(module_info, **kwargs)

        self.agent_name = self.get_config("server_name")
        self.agent_description = self.get_config("server_description")
        self.info["agent_name"] = self.agent_name
        self.info["description"] = self.agent_description

        # Initialize these in run()
        self.client_session = None
        self.initialized = False

    def run(self):
        """Run the component and initialize the MCP server."""
        # Initialize the server before starting
        self._initialize_server()
        super().run()

    def __del__(self):
        """Ensure cleanup runs when component is destroyed."""
        if hasattr(self, "server_thread"):
            try:
                self.server_thread.stop()
            except Exception:
                pass  # Ignore cleanup errors during deletion

    def _initialize_server(self):
        """Initialize the MCP server asynchronously."""
        try:
            mode = self.get_config("mode", "stdio")
            timeout = self.get_config("timeout", 90)
            server_command = self.get_config("server_command")

            # Validate configuration
            if mode not in ("sse", "stdio"):
                raise ValueError(f"Invalid mode '{mode}'. Must be 'sse' or 'stdio'")

            if mode == "stdio" and not server_command:
                raise ValueError("server_command is required for stdio mode")

            try:
                # Initialize client
                if mode == "sse":
                    raise NotImplementedError(
                        "SSE mode not yet supported with async thread"
                    )
                else:  # stdio mode
                    from mcp import StdioServerParameters
                    from .async_server import AsyncServerThread

                    parts = server_command.split()
                    server_params = StdioServerParameters(
                        command=parts[0],
                        args=parts[1:],
                        env=None,  # Use default safe environment
                    )

                    # Create and start async server thread
                    self.server_thread = AsyncServerThread(
                        server_params, self.handle_server_request
                    )
                    self.server_thread.start()

            except Exception as e:
                if hasattr(self, "server_thread"):
                    self.server_thread.stop()
                raise e

            # Convert server's capabilities into solace-agent-mesh actions
            self.action_list = self.get_actions_list(agent=self, config_fn=self.get_config)

            # Wait for server initialization to complete with timeout
            if not self.server_thread.initialized.wait(timeout=timeout):
                raise TimeoutError(f"Server initialization timed out after {timeout} seconds")

            # Convert tools to actions
            for tool in self.server_thread.tools:
                self.action_list.add_action(self._convert_tool_to_action(tool))

            # Convert resources to actions
            for resource in self.server_thread.resources:
                self.action_list.add_action(self._convert_resource_to_action(resource))

            # Convert prompts to actions
            for prompt in self.server_thread.prompts:
                self.action_list.add_action(self._convert_prompt_to_action(prompt))

            # Update the description with the list of action names
            self.info["description"] = (
                f"{self.agent_description}\n\nActions available: {', '.join([a.name for a in self.action_list.actions])}"
            )

            # Fix actions (scopes, agent, configs)
            self.action_list.fix_scopes("<agent_name>", self.agent_name)
            self.action_list.set_agent(self)
            self.action_list.set_config_fn(self.get_config)

        except Exception as e:
            raise ValueError(f"Failed to load MCP server: {str(e)}") from e

    def _convert_tool_to_action(self, tool):
        """Convert an MCP tool definition into a solace-agent-mesh action"""

        return MCPServerAction(
            server=self.server_thread,
            operation_type="tool",
            name=tool.name,
            description=tool.description,
            schema=tool.inputSchema,
            agent=self,
            config_fn=self.get_config,
        )

    def _convert_resource_to_action(self, resource):
        """Convert an MCP resource definition into a solace-agent-mesh action"""
        return MCPServerAction(
            server=self.server_thread,
            operation_type="resource",
            name=f"get_{resource.name}",
            description=f"Retrieve the {resource.name} resource: {resource.description}",
            schema={"type": "object", "properties": {}},
            agent=self,
            config_fn=self.get_config,
        )

    def _convert_prompt_to_action(self, prompt):
        """Convert an MCP prompt definition into a solace-agent-mesh action"""
        # Build schema from prompt parameters
        properties = {}
        required = []

        if prompt.arguments:
            for param in prompt.arguments:
                properties[param.name] = {
                    "type": "string",  # Prompts typically use string arguments
                    "description": param.description,
                }
                if param.required:
                    required.append(param.name)

        schema = {"type": "object", "properties": properties, "required": required}

        return MCPServerAction(
            server=self.server_thread,
            operation_type="prompt",
            name=f"use_prompt_{prompt.name}",
            description=f"Use the {prompt.name} prompt template: {prompt.description}",
            schema=schema,
            agent=self,
            config_fn=self.get_config,
        )

    async def handle_server_request(self, responder: RequestResponder):
        """Handle a request from the MCP server.

        Args:
            responder: The request responder object containing the request.

        Returns:
            None: The response is sent through the responder.
        """
        request = responder.request.root
        log.debug("handle_server_request %s", responder.request)
        try:
            # In Solace Agent Mesh context, we explicitly reject all sampling requests
            # Agents handle their own LLM requests directly through the Agent Mesh
            # infrastructure, not through MCP sampling
            err_msg = (
                f"Sampling is not supported in Solace Agent Mesh. "
                f"Method '{request.method}' is not allowed."
            )
            log.warning(err_msg)
            await responder.respond(types.ErrorData(code=400, message=err_msg))
        except Exception as e:
            err_msg = f"Error handling server request: {str(e)}"
            log.error(err_msg)
            await responder.respond(types.ErrorData(code=500, message=err_msg))
