"""Integration tests for the MCP Server Gateway.

This module provides integration tests for the MCP Server Gateway, testing
its interaction with multiple agent types, error handling, and recovery.
"""

import unittest
from unittest.mock import patch, MagicMock, call
import json
import time
import threading
import queue

from solace_ai_connector.common.message import Message
from src.gateways.mcp_server.mcp_server_gateway_output import MCPServerGatewayOutput
from src.gateways.mcp_server.mcp_server_gateway_input import MCPServerGatewayInput
from src.gateways.mcp_server.agent_registry import AgentRegistry
from src.gateways.mcp_server.agent_registration_listener import AgentRegistrationListener
from src.gateways.mcp_server.mcp_server_manager import MCPServerManager
from src.gateways.mcp_server.mcp_server import MCPServer, Tool, CallToolResult, TextContent


class TestMCPServerIntegration(unittest.TestCase):
    """Integration tests for the MCP Server Gateway."""

    def setUp(self):
        """Set up test fixtures."""
        # Create agent registry
        self.agent_registry = AgentRegistry(ttl_ms=1000)  # Short TTL for testing
        
        # Create registration listener
        self.registration_listener = AgentRegistrationListener(
            self.agent_registry,
            cleanup_interval_ms=500,  # Short interval for testing
        )
        
        # Create gateway output component
        self.gateway_output = self._create_gateway_output()
        
        # Create gateway input component
        self.gateway_input = self._create_gateway_input()
        
        # Create server manager
        self.server_manager = MCPServerManager(
            agent_registry=self.agent_registry,
            server_name="test-server",
            host="localhost",
            port=9090,
            transport_type="stdio",
            scopes="*:*:*",
            session_ttl_seconds=10  # Short TTL for testing
        )
        
        # Initialize server manager
        self.server_manager.initialize()
        
        # Register test agents
        self._register_test_agents()
        
    def _create_gateway_output(self):
        """Create a gateway output component for testing."""
        with patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.__init__") as mock_init:
            mock_init.return_value = None
            
            # Create the gateway output instance
            gateway_output = MCPServerGatewayOutput()
            
            # Set required attributes
            gateway_output.log_identifier = "[TestGateway]"
            gateway_output.discard_current_message = MagicMock()
            gateway_output.gateway_id = "test-gateway"
            gateway_output.agent_registry = self.agent_registry
            gateway_output.registration_listener = self.registration_listener
            gateway_output.server_managers = {}
            
            # Set component_config before any get_config calls
            gateway_output.component_config = {}
            
            # Create a mock for get_config that doesn't rely on component_config
            def mock_get_config(key, default=None):
                config_values = {
                    "mcp_server_scopes": "*:*:*",
                    "agent_ttl_ms": 1000,
                    "agent_cleanup_interval_ms": 500
                }
                return config_values.get(key, default)
            
            # Replace the get_config method
            gateway_output.get_config = mock_get_config
            
            return gateway_output
            
    def _create_gateway_input(self):
        """Create a gateway input component for testing."""
        with patch("solace_agent_mesh.gateway.components.gateway_input.GatewayInput.__init__") as mock_init:
            mock_init.return_value = None
            
            gateway_input = MCPServerGatewayInput()
            
            # Set required attributes
            gateway_input.log_identifier = "[TestGateway]"
            gateway_input.scopes = "*:*:*"
            gateway_input.port = 9090
            gateway_input.host = "localhost"
            gateway_input.transport = "stdio"
            
            return gateway_input
            
    def _register_test_agents(self):
        """Register test agents for integration testing."""
        # Register a geo information agent
        geo_agent = {
            "agent_name": "geo_information",
            "description": "Geographic information services",
            "actions": [
                {
                    "name": "city_to_coordinates",
                    "description": "Convert city names to geographic coordinates",
                    "params": [
                        {
                            "name": "city",
                            "desc": "Name of the city",
                            "type": "string",
                            "required": True
                        },
                        {
                            "name": "country",
                            "desc": "Country code (optional)",
                            "type": "string",
                            "required": False
                        }
                    ]
                },
                {
                    "name": "get_weather",
                    "description": "Get weather information for a location",
                    "params": [
                        {
                            "name": "latitude",
                            "desc": "Latitude of the location",
                            "type": "number",
                            "required": True
                        },
                        {
                            "name": "longitude",
                            "desc": "Longitude of the location",
                            "type": "number",
                            "required": True
                        },
                        {
                            "name": "units",
                            "desc": "Units (metric or imperial)",
                            "type": "string",
                            "required": False
                        }
                    ]
                }
            ],
            "resources": [
                {
                    "name": "supported_cities",
                    "uri": "cities",
                    "description": "List of supported cities",
                    "mime_type": "application/json"
                }
            ]
        }
        
        # Register a database agent
        db_agent = {
            "agent_name": "sql_database",
            "description": "SQL database operations",
            "actions": [
                {
                    "name": "search_query",
                    "description": "Execute a search query",
                    "params": [
                        {
                            "name": "query",
                            "desc": "Natural language query",
                            "type": "string",
                            "required": True
                        },
                        {
                            "name": "limit",
                            "desc": "Maximum number of results",
                            "type": "number",
                            "required": False
                        }
                    ]
                }
            ],
            "resources": [
                {
                    "name": "schema",
                    "uri": "schema",
                    "description": "Database schema",
                    "mime_type": "text/plain"
                }
            ],
            "prompts": [
                {
                    "name": "query_builder",
                    "description": "Build a SQL query from natural language",
                    "template": "Convert this question into SQL: {question}",
                    "arguments": [
                        {
                            "name": "question",
                            "description": "Natural language question",
                            "required": True
                        }
                    ]
                }
            ]
        }
        
        # Register agents
        self.agent_registry.register_agent(geo_agent)
        self.agent_registry.register_agent(db_agent)
        
    def test_agent_registration_and_tool_conversion(self):
        """Test agent registration and conversion to MCP tools."""
        # Create a mock MCP server
        mock_server = MagicMock(spec=MCPServer)
        
        # Set the server in the server manager
        self.server_manager.server = mock_server
        
        # Register tools from agent registry
        self.server_manager._register_agent_tools()
        
        # Verify register_tool was called for each action
        self.assertEqual(mock_server.register_tool.call_count, 3)  # 2 geo actions + 1 db action
        
        # Verify register_resource was called for each resource
        self.assertEqual(mock_server.register_resource.call_count, 2)  # 1 geo resource + 1 db resource
        
        # Verify register_prompt was called for each prompt
        self.assertEqual(mock_server.register_prompt.call_count, 1)  # 1 db prompt
        
        # Get the tools that were registered
        tool_calls = mock_server.register_tool.call_args_list
        
        # Verify geo_information.city_to_coordinates tool
        geo_tool = tool_calls[0][0][0]
        self.assertEqual(geo_tool.name, "geo_information.city_to_coordinates")
        self.assertEqual(geo_tool.inputSchema["properties"]["city"]["type"], "string")
        self.assertEqual(geo_tool.inputSchema["required"], ["city"])
        
        # Verify geo_information.get_weather tool
        weather_tool = tool_calls[1][0][0]
        self.assertEqual(weather_tool.name, "geo_information.get_weather")
        self.assertEqual(weather_tool.inputSchema["properties"]["latitude"]["type"], "number")
        self.assertEqual(weather_tool.inputSchema["properties"]["longitude"]["type"], "number")
        self.assertEqual(weather_tool.inputSchema["required"], ["latitude", "longitude"])
        
        # Verify sql_database.search_query tool
        db_tool = tool_calls[2][0][0]
        self.assertEqual(db_tool.name, "sql_database.search_query")
        self.assertEqual(db_tool.inputSchema["properties"]["query"]["type"], "string")
        self.assertEqual(db_tool.inputSchema["required"], ["query"])
        
    def test_tool_call_request_response_flow(self):
        """Test the full tool call request-response flow."""
        # Create a correlation ID
        correlation_id = "test-correlation-id"
        
        # Create a response queue
        response_queue = queue.Queue()
        
        # Add a pending request to the server manager
        with self.server_manager.lock:
            if not hasattr(self.server_manager, 'pending_requests'):
                self.server_manager.pending_requests = {}
            self.server_manager.pending_requests[correlation_id] = {
                "queue": response_queue,
                "timestamp": time.time(),
                "agent_name": "geo_information",
                "action_name": "city_to_coordinates",
            }
        
        # Create a response message
        message = Message(
            payload={
                "message": "Coordinates for New York: 40.7128, -74.0060",
                "files": []
            },
            user_properties={
                "mcp_correlation_id": correlation_id,
                "gateway_id": "test-server"
            },
            topic="solace-agent-mesh/v1/actionResponse/agent/geo_information/city_to_coordinates",
        )
        
        # Process the response
        with patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.invoke") as mock_super_invoke:
            # Mock parent invoke method
            mock_super_invoke.return_value = {
                "text": "Coordinates for New York: 40.7128, -74.0060"
            }
            
            # Handle the response
            self.gateway_output._handle_agent_response(message, message.get_payload())
        
        # Verify the response was put in the queue
        self.assertFalse(response_queue.empty())
        response = response_queue.get(block=False)
        
        # Verify response content
        self.assertIn("content", response)
        self.assertEqual(response["content"][0]["type"], "text")
        self.assertEqual(response["content"][0]["text"], "Coordinates for New York: 40.7128, -74.0060")
        
        # Verify the request was removed from pending requests
        self.assertNotIn(correlation_id, self.server_manager.pending_requests)
        
    def test_timeout_handling(self):
        """Test handling of request timeouts."""
        # Create a correlation ID
        correlation_id = "timeout-correlation-id"
        
        # Create a response queue
        response_queue = queue.Queue()
        
        # Add a pending request to the server manager with an old timestamp
        with self.server_manager.lock:
            if not hasattr(self.server_manager, 'pending_requests'):
                self.server_manager.pending_requests = {}
            self.server_manager.pending_requests[correlation_id] = {
                "queue": response_queue,
                "timestamp": time.time() - 120,  # 2 minutes old (well past timeout)
                "agent_name": "geo_information",
                "action_name": "city_to_coordinates",
            }
        
        # Clean up timed out requests
        cleaned_up = self.server_manager.cleanup_pending_requests(max_age_seconds=60)
        
        # Verify the request was cleaned up
        self.assertIn(correlation_id, cleaned_up)
        self.assertNotIn(correlation_id, self.server_manager.pending_requests)
        
        # Verify an error was put in the queue
        self.assertFalse(response_queue.empty())
        response = response_queue.get(block=False)
        
        # Verify error content
        self.assertIn("error", response)
        self.assertIn("timed out", response["error"])
        
    def test_error_handling(self):
        """Test handling of errors in the request-response flow."""
        # Create a correlation ID
        correlation_id = "error-correlation-id"
        
        # Create a response queue
        response_queue = queue.Queue()
        
        # Add a pending request to the server manager
        with self.server_manager.lock:
            if not hasattr(self.server_manager, 'pending_requests'):
                self.server_manager.pending_requests = {}
            self.server_manager.pending_requests[correlation_id] = {
                "queue": response_queue,
                "timestamp": time.time(),
                "agent_name": "geo_information",
                "action_name": "city_to_coordinates",
            }
        
        # Create an error response message
        message = Message(
            payload={
                "error_info": {
                    "error_message": "City not found in database"
                },
                "message": "Error: City not found in database"
            },
            user_properties={
                "mcp_correlation_id": correlation_id,
                "gateway_id": "test-server"
            },
            topic="solace-agent-mesh/v1/actionResponse/agent/geo_information/city_to_coordinates",
        )
        
        # Process the response
        with patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.invoke") as mock_super_invoke:
            # Mock parent invoke method
            mock_super_invoke.return_value = {
                "text": "Error: City not found in database"
            }
            
            # Handle the response
            self.gateway_output._handle_agent_response(message, message.get_payload())
        
        # Verify the response was put in the queue
        self.assertFalse(response_queue.empty())
        response = response_queue.get(block=False)
        
        # Verify response content
        self.assertIn("content", response)
        self.assertTrue(response.get("isError", False))
        self.assertEqual(response["content"][0]["type"], "text")
        self.assertEqual(response["content"][0]["text"], "City not found in database")
        
    def test_session_management(self):
        """Test session management functionality."""
        # Create a client ID and credentials
        client_id = "test-client"
        credentials = {"username": "test-user"}
        
        # Authenticate the client
        session_id = self.server_manager.authenticate_client(client_id, credentials)
        
        # Verify session was created
        self.assertIsNotNone(session_id)
        
        # Get the session
        session = self.server_manager.get_session(session_id)
        
        # Verify session properties
        self.assertIsNotNone(session)
        self.assertEqual(session.client_id, client_id)
        self.assertEqual(session.username, "test-user")
        
        # Test authorization
        self.assertTrue(self.server_manager.authorize_request(session_id, "geo_information:city_to_coordinates:execute"))
        
        # Create a new session for the same client
        new_session_id = self.server_manager.authenticate_client(client_id, credentials)
        
        # Verify a new session was created
        self.assertIsNotNone(new_session_id)
        self.assertNotEqual(session_id, new_session_id)
        
        # Verify the old session was removed
        old_session = self.server_manager.get_session(session_id)
        self.assertIsNone(old_session)
        
        # Verify the new session exists
        new_session = self.server_manager.get_session(new_session_id)
        self.assertIsNotNone(new_session)
        
    def test_resource_handling(self):
        """Test resource handling functionality."""
        # Create a mock MCP server
        mock_server = MagicMock(spec=MCPServer)
        
        # Set the server in the server manager
        self.server_manager.server = mock_server
        
        # Register tools from agent registry
        self.server_manager._register_agent_tools()
        
        # Get the resources that were registered
        resource_calls = mock_server.register_resource.call_args_list
        
        # Verify geo_information resource
        geo_resource = resource_calls[0][0][0]
        self.assertEqual(geo_resource.uri, "agent://geo_information/cities")
        self.assertEqual(geo_resource.name, "supported_cities")
        self.assertEqual(geo_resource.mimeType, "application/json")
        
        # Verify sql_database resource
        db_resource = resource_calls[1][0][0]
        self.assertEqual(db_resource.uri, "agent://sql_database/schema")
        self.assertEqual(db_resource.name, "schema")
        self.assertEqual(db_resource.mimeType, "text/plain")
        
        # Test resource read handler
        result = self.server_manager._handle_resource_read("geo_information", "cities")
        
        # Verify result
        self.assertEqual(len(result.contents), 1)
        self.assertEqual(result.contents[0].uri, "agent://geo_information/cities")
        self.assertEqual(result.contents[0].mimeType, "application/json")
        self.assertIn("Resource content for geo_information/cities", result.contents[0].text)
        
    def test_prompt_handling(self):
        """Test prompt handling functionality."""
        # Create a mock MCP server
        mock_server = MagicMock(spec=MCPServer)
        
        # Set the server in the server manager
        self.server_manager.server = mock_server
        
        # Register tools from agent registry
        self.server_manager._register_agent_tools()
        
        # Get the prompts that were registered
        prompt_calls = mock_server.register_prompt.call_args_list
        
        # Verify sql_database prompt
        db_prompt = prompt_calls[0][0][0]
        self.assertEqual(db_prompt.name, "sql_database.query_builder")
        self.assertEqual(len(db_prompt.arguments), 1)
        self.assertEqual(db_prompt.arguments[0].name, "question")
        self.assertTrue(db_prompt.arguments[0].required)
        
        # Test prompt get handler
        result = self.server_manager._handle_prompt_get(
            "sql_database", 
            "query_builder", 
            {"question": "How many users are in the database?"}
        )
        
        # Verify result
        self.assertEqual(len(result.messages), 1)
        self.assertEqual(result.messages[0].role, "user")
        self.assertEqual(result.messages[0].content.type, "text")
        self.assertEqual(
            result.messages[0].content.text, 
            "Convert this question into SQL: How many users are in the database?"
        )
        
        # Test missing required argument
        result = self.server_manager._handle_prompt_get(
            "sql_database", 
            "query_builder", 
            {}
        )
        
        # Verify error result
        self.assertEqual(len(result.messages), 0)
        self.assertIn("Missing required argument", result.description)
        
    def test_gateway_input_output_integration(self):
        """Test integration between gateway input and output components."""
        # Create a message for the input component
        input_message = Message(
            payload={"text": "Get weather in New York"},
            user_properties={"identity": "test-user"},
        )
        
        # Process the message through the input component
        with patch("solace_agent_mesh.gateway.components.gateway_input.GatewayInput.invoke") as mock_input_invoke:
            # Mock parent invoke method
            mock_input_invoke.return_value = {
                "text": "Get weather in New York",
                "identity": "test-user",
            }
            
            # Invoke the input component
            input_result = self.gateway_input.invoke(input_message, input_message.get_payload())
        
        # Verify input result
        self.assertEqual(input_result["text"], "Get weather in New York")
        self.assertEqual(input_result["identity"], "test-user")
        
        # Verify MCP server properties were added
        self.assertEqual(input_message.get_user_properties()["mcp_server_scopes"], "*:*:*")
        
        # Create a response message for the output component
        output_message = Message(
            payload={
                "message": "Weather in New York: 72°F, Partly Cloudy",
            },
            user_properties={
                "mcp_correlation_id": "test-correlation-id",
                "gateway_id": "test-server",
                "identity": "test-user",
            },
            topic="solace-agent-mesh/v1/actionResponse/agent/geo_information/get_weather",
        )
        
        # Add a pending request to the server manager
        response_queue = queue.Queue()
        with self.server_manager.lock:
            if not hasattr(self.server_manager, 'pending_requests'):
                self.server_manager.pending_requests = {}
            self.server_manager.pending_requests["test-correlation-id"] = {
                "queue": response_queue,
                "timestamp": time.time(),
                "agent_name": "geo_information",
                "action_name": "get_weather",
            }
            
        # Mock the _get_server_manager method to return our server manager
        with patch("src.gateways.mcp_server.mcp_server_gateway_output.MCPServerGatewayOutput._get_server_manager") as mock_get_manager:
            mock_get_manager.return_value = self.server_manager
            
            # Mock parent invoke method
            with patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.invoke") as mock_output_invoke:
                mock_output_invoke.return_value = {
                    "text": "Weather in New York: 72°F, Partly Cloudy",
                }
                
                # Process the response
                output_result = self.gateway_output._handle_agent_response(
                    output_message, 
                    output_message.get_payload()
                )
        
        # Verify output result
        self.assertEqual(output_result["text"], "Weather in New York: 72°F, Partly Cloudy")
        self.assertEqual(output_result["mcp_correlation_id"], "test-correlation-id")
        self.assertIn("agent_info", output_result)
        
        # Verify the response was put in the queue
        self.assertFalse(response_queue.empty())
        response = response_queue.get(block=False)
        
        # Verify response content
        self.assertIn("content", response)
        self.assertEqual(response["content"][0]["type"], "text")
        self.assertEqual(response["content"][0]["text"], "Weather in New York: 72°F, Partly Cloudy")


if __name__ == "__main__":
    unittest.main()
