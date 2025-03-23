"""Tests for the MCPServer class."""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from mcp.types import Tool, Resource, Prompt, CallToolResult, TextContent

from src.gateways.mcp_server.mcp_server import MCPServer


class TestMCPServer(unittest.TestCase):
    """Test cases for the MCPServer class."""

    def setUp(self):
        """Set up test fixtures."""
        self.server = MCPServer(
            name="test-server",
            host="localhost",
            port=9090,
            transport_type="stdio"
        )

    def test_initialization(self):
        """Test server initialization."""
        self.assertEqual(self.server.name, "test-server")
        self.assertEqual(self.server.host, "localhost")
        self.assertEqual(self.server.port, 9090)
        self.assertEqual(self.server.transport_type, "stdio")
        self.assertFalse(self.server.running)
        self.assertIsNone(self.server.server_thread)
        self.assertEqual(len(self.server.tools), 0)
        self.assertEqual(len(self.server.resources), 0)
        self.assertEqual(len(self.server.prompts), 0)

    @patch("threading.Thread")
    def test_start_stdio(self, mock_thread):
        """Test starting the server with stdio transport."""
        # Start the server
        self.server.start()
        
        # Verify thread was started
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        
        # Verify running flag
        self.assertTrue(self.server.running)
        
        # Stop the server
        self.server.stop()
        
        # Verify running flag
        self.assertFalse(self.server.running)

    def test_start_sse(self):
        """Test starting the server with SSE transport."""
        # Set transport type to SSE
        self.server.transport_type = "sse"
        
        # Start the server
        self.server.start()
        
        # Verify server was created
        self.assertIsNotNone(self.server.server)
        
        # Verify running flag
        self.assertTrue(self.server.running)
        
        # Stop the server
        self.server.stop()
        
        # Verify running flag
        self.assertFalse(self.server.running)

    def test_register_tool(self):
        """Test registering a tool."""
        # Create a tool
        tool = Tool(
            name="test-tool",
            description="Test tool",
            inputSchema={"type": "object", "properties": {}}
        )
        
        # Register the tool
        callback = MagicMock()
        self.server.register_tool(tool, callback)
        
        # Verify tool was registered
        self.assertEqual(len(self.server.tools), 1)
        self.assertEqual(self.server.tools[0].name, "test-tool")
        self.assertEqual(self.server.tool_callbacks["test-tool"], callback)

    def test_register_resource(self):
        """Test registering a resource."""
        # Create a resource
        resource = Resource(
            uri="test://resource",
            name="Test Resource",
            description="Test resource"
        )
        
        # Register the resource
        callback = MagicMock()
        self.server.register_resource(resource, callback)
        
        # Verify resource was registered
        self.assertEqual(len(self.server.resources), 1)
        self.assertEqual(self.server.resources[0].uri, "test://resource")
        self.assertEqual(self.server.resource_callbacks["test://resource"], callback)

    def test_register_prompt(self):
        """Test registering a prompt."""
        # Create a prompt
        prompt = Prompt(
            name="test-prompt",
            description="Test prompt",
            arguments=[]
        )
        
        # Register the prompt
        callback = MagicMock()
        self.server.register_prompt(prompt, callback)
        
        # Verify prompt was registered
        self.assertEqual(len(self.server.prompts), 1)
        self.assertEqual(self.server.prompts[0].name, "test-prompt")
        self.assertEqual(self.server.prompt_callbacks["test-prompt"], callback)

    @patch("asyncio.run")
    def test_run_stdio_server(self, mock_run):
        """Test running the stdio server."""
        # Call _run_stdio_server
        self.server._run_stdio_server()
        
        # Verify asyncio.run was called
        mock_run.assert_called_once()

    @patch.object(MCPServer, "_create_server")
    def test_get_sse_transport(self, mock_create_server):
        """Test getting the SSE transport."""
        # Set transport type to SSE
        self.server.transport_type = "sse"
        
        # Mock _create_server
        mock_server = MagicMock()
        mock_create_server.return_value = mock_server
        
        # Get SSE transport
        transport = self.server.get_sse_transport()
        
        # Verify _create_server was called
        mock_create_server.assert_called_once()
        
        # Verify transport was created
        self.assertIsNotNone(transport)

    def test_get_sse_transport_invalid_transport(self):
        """Test getting the SSE transport with invalid transport type."""
        # Set transport type to stdio
        self.server.transport_type = "stdio"
        
        # Verify getting SSE transport raises ValueError
        with self.assertRaises(ValueError):
            self.server.get_sse_transport()


if __name__ == "__main__":
    unittest.main()
