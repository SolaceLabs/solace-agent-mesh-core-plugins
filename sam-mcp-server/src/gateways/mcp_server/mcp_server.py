"""MCP Server implementation for the MCP Server Gateway.

This module provides the core MCP server implementation that handles client
connections, processes requests, and manages the server lifecycle.
"""

import asyncio
import logging
import threading
from typing import Dict, Any, Optional, List, Callable, Tuple

# Define mock classes first so they're available regardless of import success
class Tool:
    def __init__(self, name, description, inputSchema):
        self.name = name
        self.description = description
        self.inputSchema = inputSchema

class Resource:
    def __init__(self, uri, name, description=None, mimeType=None, uriTemplate=None):
        self.uri = uri
        self.name = name
        self.description = description
        self.mimeType = mimeType
        self.uriTemplate = uriTemplate

class Prompt:
    def __init__(self, name, description, arguments=None):
        self.name = name
        self.description = description
        self.arguments = arguments or []

class PromptArgument:
    def __init__(self, name, description, required=False):
        self.name = name
        self.description = description
        self.required = required

class TextContent:
    def __init__(self, type, text):
        self.type = type
        self.text = text

class CallToolResult:
    def __init__(self, content=None, isError=False):
        self.content = content or []
        self.isError = isError

class ReadResourceResult:
    def __init__(self, contents=None):
        self.contents = contents or []

class GetPromptResult:
    def __init__(self, messages=None, description=None):
        self.messages = messages or []
        self.description = description

class ServerOptions:
    def __init__(self, capabilities=None):
        self.capabilities = capabilities or {}

class SseServerTransport:
    def __init__(self, server):
        self.server = server

# Now try to import the real MCP classes
try:
    from mcp.server import Server
    from mcp.server.options import ServerOptions
    from mcp.server.stdio import stdio_server
    from mcp.server.sse import SseServerTransport
    from mcp.types import (
        Tool, Resource, Prompt, PromptArgument, 
        CallToolRequest, CallToolResult, 
        ReadResourceRequest, ReadResourceResult,
        GetPromptRequest, GetPromptResult,
        TextContent
    )
    MCP_AVAILABLE = True
except ImportError:
    # Use our mock classes if import fails
    MCP_AVAILABLE = False
    
    class Server:
        def __init__(self, implementation, options=None):
            self.implementation = implementation
            self.options = options
            self.running = False

        def set_request_handler(self, method, handler):
            pass

        async def run(self, stdin, stdout):
            pass

from solace_ai_connector.common.log import log


class MCPServer:
    """MCP Server implementation for the MCP Server Gateway.

    This class implements the Model Context Protocol server that communicates
    with MCP clients, exposing agent capabilities as tools, resources, and prompts.

    Attributes:
        name: Name of the MCP server.
        host: Host address for the server (for SSE transport).
        port: Port for the server (for SSE transport).
        transport_type: Type of transport to use ('stdio' or 'sse').
        server: The MCP server instance.
        running: Flag indicating whether the server is running.
        server_thread: Thread running the server (for stdio transport).
    """

    def __init__(
        self,
        name: str,
        host: str = "0.0.0.0",
        port: int = 8080,
        transport_type: str = "stdio",
    ):
        """Initialize the MCP server.

        Args:
            name: Name of the MCP server.
            host: Host address for the server (for SSE transport).
            port: Port for the server (for SSE transport).
            transport_type: Type of transport to use ('stdio' or 'sse').
        """
        self.name = name
        self.host = host
        self.port = port
        self.transport_type = transport_type
        self.server = None
        self.running = False
        self.server_thread = None
        
        # Callback registries
        self.tool_callbacks: Dict[str, Callable] = {}
        self.resource_callbacks: Dict[str, Callable] = {}
        self.prompt_callbacks: Dict[str, Callable] = {}
        
        # Tool, resource, and prompt registries
        self.tools: List[Tool] = []
        self.resources: List[Resource] = []
        self.prompts: List[Prompt] = []
        
        self.log_identifier = f"[MCPServer:{name}] "
        
    def start(self):
        """Start the MCP server.
        
        This method starts the server in a separate thread for stdio transport,
        or directly for SSE transport.
        """
        if self.running:
            log.warning(f"{self.log_identifier}Server already running")
            return
            
        if self.transport_type == "stdio":
            self.server_thread = threading.Thread(target=self._run_stdio_server)
            self.server_thread.daemon = True
            self.server_thread.start()
            self.running = True
            log.info(f"{self.log_identifier}Started MCP server with stdio transport")
        elif self.transport_type == "sse":
            # SSE transport is not started in a thread - it's expected to be
            # integrated with a web server
            self.server = self._create_server()
            self.running = True
            log.info(
                f"{self.log_identifier}Created MCP server with SSE transport "
                f"on {self.host}:{self.port}"
            )
        else:
            raise ValueError(
                f"{self.log_identifier}Unsupported transport type: {self.transport_type}"
            )
            
    def stop(self):
        """Stop the MCP server."""
        if not self.running:
            return
            
        self.running = False
        if self.server_thread:
            self.server_thread.join(timeout=1.0)
            self.server_thread = None
            
        log.info(f"{self.log_identifier}Stopped MCP server")
        
    def _create_server(self) -> Server:
        """Create the MCP server instance.
        
        Returns:
            The MCP server instance.
        """
        server = Server(
            implementation={"name": self.name, "version": "1.0.0"},
            options=ServerOptions(
                capabilities={
                    "tools": {},
                    "resources": {},
                    "prompts": {},
                }
            ),
        )
        
        # Register handlers for tools, resources, and prompts
        server.set_request_handler(
            "tools/list", 
            lambda request, extra: {"tools": self.tools}
        )
        
        server.set_request_handler(
            "tools/call",
            self._handle_tool_call
        )
        
        server.set_request_handler(
            "resources/list",
            lambda request, extra: {"resources": self.resources}
        )
        
        server.set_request_handler(
            "resources/read",
            self._handle_resource_read
        )
        
        server.set_request_handler(
            "prompts/list",
            lambda request, extra: {"prompts": self.prompts}
        )
        
        server.set_request_handler(
            "prompts/get",
            self._handle_prompt_get
        )
        
        return server
        
    async def _handle_tool_call(self, request: CallToolRequest, extra: Any) -> CallToolResult:
        """Handle a tool call request.
        
        Args:
            request: The tool call request.
            extra: Extra request information.
            
        Returns:
            The tool call result.
        """
        tool_name = request.params.name
        if tool_name not in self.tool_callbacks:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Tool not found: {tool_name}")],
                isError=True
            )
            
        try:
            callback = self.tool_callbacks[tool_name]
            result = callback(request.params.arguments)
            
            # Convert result to CallToolResult if it's not already
            if not isinstance(result, CallToolResult):
                if isinstance(result, str):
                    result = CallToolResult(
                        content=[TextContent(type="text", text=result)]
                    )
                elif isinstance(result, dict):
                    result = CallToolResult(
                        content=[TextContent(type="text", text=str(result))]
                    )
                else:
                    result = CallToolResult(
                        content=[TextContent(type="text", text=str(result))]
                    )
                    
            return result
        except Exception as e:
            log.error(
                f"{self.log_identifier}Error executing tool {tool_name}: {str(e)}",
                exc_info=True
            )
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error executing tool: {str(e)}")],
                isError=True
            )
            
    async def _handle_resource_read(self, request: ReadResourceRequest, extra: Any) -> ReadResourceResult:
        """Handle a resource read request.
        
        Args:
            request: The resource read request.
            extra: Extra request information.
            
        Returns:
            The resource read result.
        """
        resource_uri = request.params.uri
        if resource_uri not in self.resource_callbacks:
            return ReadResourceResult(
                contents=[]
            )
            
        try:
            callback = self.resource_callbacks[resource_uri]
            result = callback()
            
            # Convert result to ReadResourceResult if it's not already
            if not isinstance(result, ReadResourceResult):
                if isinstance(result, str):
                    result = ReadResourceResult(
                        contents=[{
                            "uri": resource_uri,
                            "text": result
                        }]
                    )
                else:
                    result = ReadResourceResult(
                        contents=[{
                            "uri": resource_uri,
                            "text": str(result)
                        }]
                    )
                    
            return result
        except Exception as e:
            log.error(
                f"{self.log_identifier}Error reading resource {resource_uri}: {str(e)}",
                exc_info=True
            )
            return ReadResourceResult(
                contents=[]
            )
            
    async def _handle_prompt_get(self, request: GetPromptRequest, extra: Any) -> GetPromptResult:
        """Handle a prompt get request.
        
        Args:
            request: The prompt get request.
            extra: Extra request information.
            
        Returns:
            The prompt get result.
        """
        prompt_name = request.params.name
        if prompt_name not in self.prompt_callbacks:
            return GetPromptResult(
                messages=[]
            )
            
        try:
            callback = self.prompt_callbacks[prompt_name]
            result = callback(request.params.arguments)
            
            # Convert result to GetPromptResult if it's not already
            if not isinstance(result, GetPromptResult):
                if isinstance(result, str):
                    result = GetPromptResult(
                        messages=[{
                            "role": "user",
                            "content": {
                                "type": "text",
                                "text": result
                            }
                        }]
                    )
                    
            return result
        except Exception as e:
            log.error(
                f"{self.log_identifier}Error getting prompt {prompt_name}: {str(e)}",
                exc_info=True
            )
            return GetPromptResult(
                messages=[]
            )
            
    def _run_stdio_server(self):
        """Run the MCP server with stdio transport."""
        async def run_server():
            server = self._create_server()
            
            async with stdio_server() as (stdin, stdout):
                await server.run(stdin, stdout)
                
        asyncio.run(run_server())
        
    def get_sse_transport(self) -> SseServerTransport:
        """Get the SSE transport for the server.
        
        Returns:
            The SSE transport instance.
        """
        if self.transport_type != "sse":
            raise ValueError(
                f"{self.log_identifier}SSE transport not available for {self.transport_type} transport"
            )
            
        if not self.server:
            self.server = self._create_server()
            
        return SseServerTransport(self.server)
        
    def register_tool(self, tool: Tool, callback: Callable) -> None:
        """Register a tool with the server.
        
        Args:
            tool: The tool to register.
            callback: The callback to execute when the tool is called.
        """
        self.tools.append(tool)
        self.tool_callbacks[tool.name] = callback
        log.info(f"{self.log_identifier}Registered tool: {tool.name}")
        
    def register_resource(self, resource: Resource, callback: Callable) -> None:
        """Register a resource with the server.
        
        Args:
            resource: The resource to register.
            callback: The callback to execute when the resource is read.
        """
        self.resources.append(resource)
        self.resource_callbacks[resource.uri] = callback
        log.info(f"{self.log_identifier}Registered resource: {resource.uri}")
        
    def register_prompt(self, prompt: Prompt, callback: Callable) -> None:
        """Register a prompt with the server.
        
        Args:
            prompt: The prompt to register.
            callback: The callback to execute when the prompt is requested.
        """
        self.prompts.append(prompt)
        self.prompt_callbacks[prompt.name] = callback
        log.info(f"{self.log_identifier}Registered prompt: {prompt.name}")
