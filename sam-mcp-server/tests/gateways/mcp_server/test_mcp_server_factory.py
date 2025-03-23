"""Tests for the MCPServerFactory class."""

import unittest
from unittest.mock import patch, MagicMock

# Import directly from our mocked classes
from src.gateways.mcp_server.mcp_server import MCPServer
from src.gateways.mcp_server.mcp_server_factory import MCPServerFactory


class TestMCPServerFactory(unittest.TestCase):
    """Test cases for the MCPServerFactory class."""

    def setUp(self):
        """Set up test fixtures."""
        # Clear instances before each test
        MCPServerFactory._instances = {}

    def test_get_server_new(self):
        """Test getting a new server."""
        # Get a new server
        server = MCPServerFactory.get_server(
            name="test-server",
            host="localhost",
            port=9090,
            transport_type="stdio"
        )
        
        # Verify server was created
        self.assertIsNotNone(server)
        self.assertEqual(server.name, "test-server")
        self.assertEqual(server.host, "localhost")
        self.assertEqual(server.port, 9090)
        self.assertEqual(server.transport_type, "stdio")
        
        # Verify server was added to instances
        self.assertIn("test-server", MCPServerFactory._instances)
        self.assertEqual(MCPServerFactory._instances["test-server"], server)

    def test_get_server_existing(self):
        """Test getting an existing server."""
        # Create a server
        server1 = MCPServerFactory.get_server("test-server")
        
        # Get the same server
        server2 = MCPServerFactory.get_server("test-server")
        
        # Verify both references point to the same server
        self.assertIs(server1, server2)

    def test_get_server_not_create(self):
        """Test getting a server without creating it if missing."""
        # Get a non-existent server without creating it
        server = MCPServerFactory.get_server(
            name="test-server",
            create_if_missing=False
        )
        
        # Verify server is None
        self.assertIsNone(server)
        
        # Verify no server was added to instances
        self.assertNotIn("test-server", MCPServerFactory._instances)

    def test_remove_server_existing(self):
        """Test removing an existing server."""
        # Create a server
        server = MCPServerFactory.get_server("test-server")
        server.stop = MagicMock()
        
        # Remove the server
        result = MCPServerFactory.remove_server("test-server")
        
        # Verify server was removed
        self.assertTrue(result)
        self.assertNotIn("test-server", MCPServerFactory._instances)
        
        # Verify server.stop was called
        server.stop.assert_called_once()

    def test_remove_server_non_existent(self):
        """Test removing a non-existent server."""
        # Remove a non-existent server
        result = MCPServerFactory.remove_server("test-server")
        
        # Verify result is False
        self.assertFalse(result)

    def test_get_all_servers(self):
        """Test getting all servers."""
        # Create two servers
        server1 = MCPServerFactory.get_server("server1")
        server2 = MCPServerFactory.get_server("server2")
        
        # Get all servers
        servers = MCPServerFactory.get_all_servers()
        
        # Verify servers were returned
        self.assertEqual(len(servers), 2)
        self.assertIn("server1", servers)
        self.assertIn("server2", servers)
        self.assertEqual(servers["server1"], server1)
        self.assertEqual(servers["server2"], server2)

    def test_stop_all_servers(self):
        """Test stopping all servers."""
        # Create two servers
        server1 = MCPServerFactory.get_server("server1")
        server2 = MCPServerFactory.get_server("server2")
        server1.stop = MagicMock()
        server2.stop = MagicMock()
        
        # Stop all servers
        MCPServerFactory.stop_all_servers()
        
        # Verify all servers were stopped
        server1.stop.assert_called_once()
        server2.stop.assert_called_once()
        
        # Verify all servers were removed
        self.assertEqual(len(MCPServerFactory._instances), 0)


if __name__ == "__main__":
    unittest.main()
