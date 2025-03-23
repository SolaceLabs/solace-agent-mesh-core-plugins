"""Tests for the MCPServerManager class."""

import unittest
from unittest.mock import patch, MagicMock

# Import directly from our mocked classes
from src.gateways.mcp_server.mcp_server import MCPServer, Tool, CallToolResult, TextContent
from src.gateways.mcp_server.mcp_server_factory import MCPServerFactory
from src.gateways.mcp_server.mcp_server_manager import MCPServerManager
from src.gateways.mcp_server.agent_registry import AgentRegistry


class TestMCPServerManager(unittest.TestCase):
    """Test cases for the MCPServerManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.agent_registry = MagicMock(spec=AgentRegistry)
        self.manager = MCPServerManager(
            agent_registry=self.agent_registry,
            server_name="test-server",
            host="localhost",
            port=9090,
            transport_type="stdio",
            scopes="test:*:*"
        )

    def test_initialization(self):
        """Test manager initialization."""
        self.assertEqual(self.manager.server_name, "test-server")
        self.assertEqual(self.manager.host, "localhost")
        self.assertEqual(self.manager.port, 9090)
        self.assertEqual(self.manager.transport_type, "stdio")
        self.assertEqual(self.manager.scopes, "test:*:*")
        self.assertFalse(self.manager.initialized)
        self.assertIsNone(self.manager.server)

    @patch("src.gateways.mcp_server.mcp_server_factory.MCPServerFactory.get_server")
    def test_initialize_success(self, mock_get_server):
        """Test successful initialization."""
        # Mock get_server
        mock_server = MagicMock(spec=MCPServer)
        mock_get_server.return_value = mock_server
        
        # Mock agent registry
        self.agent_registry.get_filtered_agents.return_value = {}
        
        # Initialize manager
        result = self.manager.initialize()
        
        # Verify result
        self.assertTrue(result)
        self.assertTrue(self.manager.initialized)
        self.assertEqual(self.manager.server, mock_server)
        
        # Verify get_server was called
        mock_get_server.assert_called_once_with(
            "test-server",
            "localhost",
            9090,
            "stdio"
        )
        
        # Verify server.start was called
        mock_server.start.assert_called_once()
        
        # Verify agent_registry.get_filtered_agents was called
        self.agent_registry.get_filtered_agents.assert_called_once_with("test:*:*")

    @patch("src.gateways.mcp_server.mcp_server_factory.MCPServerFactory.get_server")
    def test_initialize_error(self, mock_get_server):
        """Test initialization with error."""
        # Mock get_server to raise exception
        mock_get_server.side_effect = Exception("Test error")
        
        # Initialize manager
        result = self.manager.initialize()
        
        # Verify result
        self.assertFalse(result)
        self.assertFalse(self.manager.initialized)
        self.assertIsNone(self.manager.server)

    @patch("src.gateways.mcp_server.mcp_server_factory.MCPServerFactory.remove_server")
    def test_shutdown(self, mock_remove_server):
        """Test shutting down the manager."""
        # Set initialized flag
        self.manager.initialized = True
        self.manager.server = MagicMock()
        
        # Shut down manager
        self.manager.shutdown()
        
        # Verify initialized flag
        self.assertFalse(self.manager.initialized)
        self.assertIsNone(self.manager.server)
        
        # Verify remove_server was called
        mock_remove_server.assert_called_once_with("test-server")

    @patch("src.gateways.mcp_server.mcp_server_factory.MCPServerFactory.get_server")
    def test_register_agent_tools(self, mock_get_server):
        """Test registering agent tools."""
        # Mock get_server
        mock_server = MagicMock(spec=MCPServer)
        mock_get_server.return_value = mock_server
        
        # Mock agent registry
        self.agent_registry.get_filtered_agents.return_value = {
            "agent1": {
                "agent_name": "agent1",
                "description": "Agent 1",
                "actions": [
                    {
                        "name": "action1",
                        "description": "Action 1",
                        "params": [
                            {
                                "name": "param1",
                                "desc": "Parameter 1",
                                "type": "string",
                                "required": True
                            }
                        ]
                    },
                    {
                        "name": "action2",
                        "description": "Action 2",
                        "params": [
                            {
                                "name": "param2",
                                "desc": "Parameter 2",
                                "type": "number",
                                "required": False
                            },
                            {
                                "name": "param3",
                                "desc": "Parameter 3",
                                "type": "boolean",
                                "required": True
                            }
                        ]
                    },
                    # Invalid action without params
                    {
                        "name": "action3",
                        "description": "Action 3"
                    },
                    # Invalid action with non-list params
                    {
                        "name": "action4",
                        "description": "Action 4",
                        "params": "invalid"
                    }
                ]
            }
        }
        
        # Initialize manager
        self.manager.initialize()
        
        # Verify register_tool was called twice (for action1 and action2, not for invalid actions)
        self.assertEqual(mock_server.register_tool.call_count, 2)
        
        # Get the first tool that was registered
        tool1 = mock_server.register_tool.call_args_list[0][0][0]
        
        # Verify tool1 properties
        self.assertEqual(tool1.name, "agent1.action1")
        self.assertEqual(tool1.description, "Action 1 (from agent agent1)")
        self.assertEqual(tool1.inputSchema["type"], "object")
        self.assertEqual(tool1.inputSchema["properties"]["param1"]["type"], "string")
        self.assertEqual(tool1.inputSchema["properties"]["param1"]["description"], "Parameter 1")
        self.assertEqual(tool1.inputSchema["required"], ["param1"])
        
        # Get the second tool that was registered
        tool2 = mock_server.register_tool.call_args_list[1][0][0]
        
        # Verify tool2 properties
        self.assertEqual(tool2.name, "agent1.action2")
        self.assertEqual(tool2.description, "Action 2 (from agent agent1)")
        self.assertEqual(tool2.inputSchema["type"], "object")
        self.assertEqual(tool2.inputSchema["properties"]["param2"]["type"], "number")
        self.assertEqual(tool2.inputSchema["properties"]["param3"]["type"], "boolean")
        self.assertEqual(tool2.inputSchema["required"], ["param3"])

    def test_handle_tool_call(self):
        """Test handling a tool call."""
        # Mock agent_registry.get_agent
        self.agent_registry.get_agent.return_value = {
            "agent_name": "agent1",
            "description": "Agent 1",
            "actions": [
                {
                    "name": "action1",
                    "description": "Action 1",
                    "params": [
                        {
                            "name": "param1",
                            "desc": "Parameter 1",
                            "type": "string",
                            "required": True
                        }
                    ]
                }
            ]
        }
        
        # Call _handle_tool_call with valid parameters
        result = self.manager._handle_tool_call("agent1", "action1", {"param1": "value1"})
        
        # Verify result
        self.assertEqual(result.content[0].type, "text")
        self.assertEqual(
            result.content[0].text,
            "Called agent1.action1 with args: {'param1': 'value1'}"
        )
        self.assertFalse(result.isError)
        
        # Test with missing required parameter
        result = self.manager._handle_tool_call("agent1", "action1", {})
        
        # Verify error result
        self.assertEqual(result.content[0].type, "text")
        self.assertTrue("Missing required parameter" in result.content[0].text)
        self.assertTrue(result.isError)
        
        # Test with non-existent agent
        self.agent_registry.get_agent.return_value = None
        result = self.manager._handle_tool_call("non_existent", "action1", {"param1": "value1"})
        
        # Verify error result
        self.assertEqual(result.content[0].type, "text")
        self.assertTrue("Agent 'non_existent' not found" in result.content[0].text)
        self.assertTrue(result.isError)
        
        # Test with non-existent action
        self.agent_registry.get_agent.return_value = {
            "agent_name": "agent1",
            "description": "Agent 1",
            "actions": [
                {
                    "name": "action1",
                    "description": "Action 1",
                    "params": []
                }
            ]
        }
        result = self.manager._handle_tool_call("agent1", "non_existent", {"param1": "value1"})
        
        # Verify error result
        self.assertEqual(result.content[0].type, "text")
        self.assertTrue("Action 'non_existent' not found" in result.content[0].text)
        self.assertTrue(result.isError)

    def test_update_agent_registry(self):
        """Test updating the agent registry."""
        # Mock _register_agent_tools
        self.manager._register_agent_tools = MagicMock()
        
        # Set initialized flag
        self.manager.initialized = True
        
        # Update agent registry
        self.manager.update_agent_registry()
        
        # Verify _register_agent_tools was called
        self.manager._register_agent_tools.assert_called_once()

    def test_update_agent_registry_not_initialized(self):
        """Test updating the agent registry when not initialized."""
        # Mock _register_agent_tools
        self.manager._register_agent_tools = MagicMock()
        
        # Set initialized flag
        self.manager.initialized = False
        
        # Update agent registry
        self.manager.update_agent_registry()
        
        # Verify _register_agent_tools was not called
        self.manager._register_agent_tools.assert_not_called()


if __name__ == "__main__":
    unittest.main()
