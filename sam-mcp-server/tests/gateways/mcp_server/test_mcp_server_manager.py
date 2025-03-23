"""Tests for the MCPServerManager class."""

import unittest
from unittest.mock import patch, MagicMock
from queue import Queue, Empty

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
                ],
                "resources": [
                    {
                        "name": "resource1",
                        "uri": "resource1",
                        "description": "Resource 1",
                        "mime_type": "text/plain"
                    },
                    {
                        "name": "resource2",
                        "uri": "resource2",
                        "description": "Resource 2",
                        "mime_type": "application/json"
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
        
        # Verify register_resource was called twice
        self.assertEqual(mock_server.register_resource.call_count, 2)
        
        # Get the first resource that was registered
        resource1 = mock_server.register_resource.call_args_list[0][0][0]
        
        # Verify resource1 properties
        self.assertEqual(resource1.uri, "agent://agent1/resource1")
        self.assertEqual(resource1.name, "resource1")
        self.assertEqual(resource1.description, "Resource 1 (from agent agent1)")
        self.assertEqual(resource1.mimeType, "text/plain")
        
        # Get the second resource that was registered
        resource2 = mock_server.register_resource.call_args_list[1][0][0]
        
        # Verify resource2 properties
        self.assertEqual(resource2.uri, "agent://agent1/resource2")
        self.assertEqual(resource2.name, "resource2")
        self.assertEqual(resource2.description, "Resource 2 (from agent agent1)")
        self.assertEqual(resource2.mimeType, "application/json")

    @patch('time.time')
    def test_handle_tool_call(self, mock_time):
        """Test handling a tool call."""
        # Set mock time
        mock_time.return_value = 1000
        
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
        
        # Verify pending request was created
        self.assertTrue(hasattr(self.manager, 'pending_requests'))
        self.assertEqual(len(self.manager.pending_requests), 1)
        
        # Get the correlation ID
        correlation_id = list(self.manager.pending_requests.keys())[0]
        
        # Verify request info
        request_info = self.manager.pending_requests[correlation_id]
        self.assertEqual(request_info["agent_name"], "agent1")
        self.assertEqual(request_info["action_name"], "action1")
        self.assertEqual(request_info["timestamp"], 1000)
        
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

    def test_handle_resource_read(self):
        """Test handling a resource read."""
        # Mock agent_registry.get_agent
        self.agent_registry.get_agent.return_value = {
            "agent_name": "agent1",
            "description": "Agent 1",
            "resources": [
                {
                    "name": "resource1",
                    "uri": "resource1",
                    "description": "Resource 1",
                    "mime_type": "text/plain"
                }
            ]
        }
        
        # Call _handle_resource_read with valid parameters
        result = self.manager._handle_resource_read("agent1", "resource1")
        
        # Verify result
        self.assertEqual(len(result.contents), 1)
        
        # Access the TextResourceContents object's attributes directly
        resource_content = result.contents[0]
        # Convert to string for comparison if it's an AnyUrl object
        uri = str(resource_content.uri) if hasattr(resource_content.uri, "__str__") else resource_content.uri
        self.assertEqual(uri, "agent://agent1/resource1")
        self.assertEqual(resource_content.mimeType, "text/plain")
        self.assertTrue("Resource content for agent1/resource1" in resource_content.text)
        
        # Test with non-existent agent
        self.agent_registry.get_agent.return_value = None
        result = self.manager._handle_resource_read("non_existent", "resource1")
        
        # Verify empty result
        self.assertEqual(len(result.contents), 0)
        
        # Test with non-existent resource
        self.agent_registry.get_agent.return_value = {
            "agent_name": "agent1",
            "description": "Agent 1",
            "resources": [
                {
                    "name": "resource1",
                    "uri": "resource1",
                    "description": "Resource 1",
                    "mime_type": "text/plain"
                }
            ]
        }
        result = self.manager._handle_resource_read("agent1", "non_existent")
        
        # Verify empty result
        self.assertEqual(len(result.contents), 0)

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
        
    @patch('time.time')
    def test_handle_action_response(self, mock_time):
        """Test handling an action response."""
        # Set mock time
        mock_time.return_value = 1000
        
        # Create a pending request
        self.manager.pending_requests = {}
        correlation_id = "test-correlation-id"
        
        # Create a mock queue
        mock_queue = MagicMock()
        
        # Add the request to pending requests
        self.manager.pending_requests[correlation_id] = {
            "queue": mock_queue,
            "timestamp": 1000,
            "agent_name": "agent1",
            "action_name": "action1",
        }
        
        # Create response data
        response_data = {"message": "Test response"}
        
        # Handle the response
        result = self.manager.handle_action_response(correlation_id, response_data)
        
        # Verify result
        self.assertTrue(result)
        
        # Verify queue.put was called
        mock_queue.put.assert_called_once_with(response_data)
        
        # Verify request was removed from pending requests
        self.assertNotIn(correlation_id, self.manager.pending_requests)
        
        # Test with unknown correlation ID
        result = self.manager.handle_action_response("unknown-id", response_data)
        
        # Verify result
        self.assertFalse(result)
        
    @patch('time.time')
    def test_cleanup_pending_requests(self, mock_time):
        """Test cleaning up pending requests."""
        # Set mock time
        mock_time.return_value = 1100  # Current time
        
        # Create pending requests
        self.manager.pending_requests = {}
        
        # Create mock queues
        mock_queue1 = MagicMock()
        mock_queue2 = MagicMock()
        
        # Add requests to pending requests
        self.manager.pending_requests["id1"] = {
            "queue": mock_queue1,
            "timestamp": 1000,  # 100 seconds old
            "agent_name": "agent1",
            "action_name": "action1",
        }
        
        self.manager.pending_requests["id2"] = {
            "queue": mock_queue2,
            "timestamp": 1090,  # 10 seconds old
            "agent_name": "agent2",
            "action_name": "action2",
        }
        
        # Clean up requests older than 60 seconds
        cleaned_up = self.manager.cleanup_pending_requests(max_age_seconds=60)
        
        # Verify result
        self.assertEqual(len(cleaned_up), 1)
        self.assertIn("id1", cleaned_up)
        
        # Verify queue.put was called for timed out request
        mock_queue1.put.assert_called_once()
        mock_queue2.put.assert_not_called()
        
        # Verify timed out request was removed
        self.assertNotIn("id1", self.manager.pending_requests)
        self.assertIn("id2", self.manager.pending_requests)


if __name__ == "__main__":
    unittest.main()
