"""MCP Server implementation for the MCP Server Gateway.

This module provides the core MCP server implementation that handles client
connections, processes requests, and manages the server lifecycle.
"""

import asyncio
import threading
from typing import Dict, Any, List, Callable

from mcp.server import Server
from mcp.types import (
    Tool,
    Resource,
    Prompt,
    CallToolRequest,
    CallToolResult,
    ReadResourceRequest,
    ReadResourceResult,
    GetPromptRequest,
    GetPromptResult,
    TextContent,
)
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport

# <inst>
# Fix all the log calls to use lazy formatting. I see a log of warnings
# </inst>


# Define ServerOptions class since mcp.server.options doesn't exist
class ServerOptions:
    def __init__(self, capabilities=None):
        self.capabilities = capabilities or {}


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
            log.warning("%sServer already running", self.log_identifier)
            return

        if self.transport_type == "stdio":
            self.server_thread = threading.Thread(target=self._run_stdio_server)
            self.server_thread.daemon = True
            self.server_thread.start()
            self.running = True
            log.info("%sStarted MCP server with stdio transport", self.log_identifier)
        elif self.transport_type == "sse":
            # SSE transport is not started in a thread - it's expected to be
            # integrated with a web server
            self.server = self._create_server()
            self.running = True
            log.info(
                "%sCreated MCP server with SSE transport on %s:%s",
                self.log_identifier,
                self.host,
                self.port
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

        log.info("%sStopped MCP server", self.log_identifier)

    def _create_server(self) -> Server:
        """Create the MCP server instance.

        Returns:
            The MCP server instance.
        """
        server = Server(
            self.name,
            "1.0.0",
            ServerOptions(
                capabilities={
                    "tools": {},
                    "resources": {},
                    "prompts": {},
                }
            ),
        )

        # Register handlers for tools, resources, and prompts

        @server.list_tools()
        async def handle_list_tools():
            return self.tools

        @server.call_tool()
        async def handle_call_tool(name, arguments):
            return await self._handle_tool_call(
                CallToolRequest(
                    params=type(
                        "obj", (object,), {"name": name, "arguments": arguments}
                    )
                ),
                None,
            )

        @server.list_resources()
        async def handle_list_resources():
            return self.resources

        @server.read_resource()
        async def handle_read_resource(uri):
            return await self._handle_resource_read(
                ReadResourceRequest(params=type("obj", (object,), {"uri": uri})), None
            )

        @server.list_prompts()
        async def handle_list_prompts():
            return self.prompts

        @server.get_prompt()
        async def handle_get_prompt(name, arguments):
            return await self._handle_prompt_get(
                GetPromptRequest(
                    params=type(
                        "obj", (object,), {"name": name, "arguments": arguments}
                    )
                ),
                None,
            )

        return server

    async def _handle_tool_call(
        self, request: CallToolRequest, extra: Any
    ) -> CallToolResult:
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
                isError=True,
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
                "%sError executing tool %s: %s",
                self.log_identifier,
                tool_name,
                str(e),
                exc_info=True,
            )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=f"Error executing tool: {str(e)}")
                ],
                isError=True,
            )

    async def _handle_resource_read(
        self, request: ReadResourceRequest, extra: Any
    ) -> ReadResourceResult:
        """Handle a resource read request.

        Args:
            request: The resource read request.
            extra: Extra request information.

        Returns:
            The resource read result.
        """
        resource_uri = request.params.uri
        # Convert AnyUrl to string if needed
        uri_key = (
            str(resource_uri) if hasattr(resource_uri, "__str__") else resource_uri
        )

        if uri_key not in self.resource_callbacks:
            return ReadResourceResult(contents=[])

        try:
            callback = self.resource_callbacks[uri_key]
            result = callback()

            # Convert result to ReadResourceResult if it's not already
            if not isinstance(result, ReadResourceResult):
                if isinstance(result, str):
                    result = ReadResourceResult(
                        contents=[{"uri": resource_uri, "text": result}]
                    )
                else:
                    result = ReadResourceResult(
                        contents=[{"uri": resource_uri, "text": str(result)}]
                    )

            return result
        except Exception as e:
            log.error(
                "%sError reading resource %s: %s",
                self.log_identifier,
                resource_uri,
                str(e),
                exc_info=True,
            )
            return ReadResourceResult(contents=[])

    async def _handle_prompt_get(
        self, request: GetPromptRequest, extra: Any
    ) -> GetPromptResult:
        """Handle a prompt get request.

        Args:
            request: The prompt get request.
            extra: Extra request information.

        Returns:
            The prompt get result.
        """
        prompt_name = request.params.name
        if prompt_name not in self.prompt_callbacks:
            return GetPromptResult(messages=[])

        try:
            callback = self.prompt_callbacks[prompt_name]
            result = callback(request.params.arguments)

            # Convert result to GetPromptResult if it's not already
            if not isinstance(result, GetPromptResult):
                if isinstance(result, str):
                    result = GetPromptResult(
                        messages=[
                            {
                                "role": "user",
                                "content": {"type": "text", "text": result},
                            }
                        ]
                    )

            return result
        except Exception as e:
            log.error(
                "%sError getting prompt %s: %s",
                self.log_identifier,
                prompt_name,
                str(e),
                exc_info=True,
            )
            return GetPromptResult(messages=[])

    def _run_stdio_server(self):
        """Run the MCP server with stdio transport."""

        async def run_server():
            server = self._create_server()

            # Use a try-except block to handle the case where stdio_server is not available
            try:
                # Try to import and use the real stdio_server
                from mcp.server.stdio import stdio_server

                async with stdio_server() as streams:
                    # The API has changed - stdio_server now returns a tuple of streams
                    # that should be passed to server.run
                    await server.run(
                        streams[0],  # read stream
                        streams[1],  # write stream
                        server.create_initialization_options(),
                    )
            except (ImportError, NameError):
                # If that fails, use a mock implementation
                log.warning(
                    "%sUsing mock stdio server implementation",
                    self.log_identifier
                )

                # Create simple stdin/stdout streams for testing
                class MockStream:
                    async def read(self):
                        return None  # Return None to simulate end of stream

                    async def write(self, data):
                        pass  # Do nothing with the data

                    async def drain(self):
                        pass  # No-op

                    async def close(self):
                        pass  # No-op

                stdin = MockStream()
                stdout = MockStream()
                await server.run(stdin, stdout, server.create_initialization_options())

        asyncio.run(run_server())

    def get_sse_transport(self) -> SseServerTransport:
        """Get the SSE transport for the server.

        Returns:
            The SSE transport instance.
        """
        if self.transport_type != "sse":
            raise ValueError(
                "%sSSE transport not available for %s transport",
                self.log_identifier,
                self.transport_type
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
        log.info("%sRegistered tool: %s", self.log_identifier, tool.name)

    def register_resource(self, resource: Resource, callback: Callable) -> None:
        """Register a resource with the server.

        Args:
            resource: The resource to register.
            callback: The callback to execute when the resource is read.
        """
        self.resources.append(resource)
        # Convert AnyUrl to string if needed
        uri_key = (
            str(resource.uri) if hasattr(resource.uri, "__str__") else resource.uri
        )
        self.resource_callbacks[uri_key] = callback
        log.info("%sRegistered resource: %s", self.log_identifier, resource.uri)

    def register_prompt(self, prompt: Prompt, callback: Callable) -> None:
        """Register a prompt with the server.

        Args:
            prompt: The prompt to register.
            callback: The callback to execute when the prompt is requested.
        """
        self.prompts.append(prompt)
        self.prompt_callbacks[prompt.name] = callback
        log.info("%sRegistered prompt: %s", self.log_identifier, prompt.name)
