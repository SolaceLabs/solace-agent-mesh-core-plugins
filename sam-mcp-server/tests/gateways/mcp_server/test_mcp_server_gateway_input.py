"""Tests for the MCPServerGatewayInput class."""

import unittest
from unittest.mock import patch, MagicMock

from solace_ai_connector.common.message import Message
from src.gateways.mcp_server.mcp_server_gateway_input import MCPServerGatewayInput


class TestMCPServerGatewayInput(unittest.TestCase):
    """Test cases for the MCPServerGatewayInput class."""

    @patch('solace_agent_mesh.gateway.components.gateway_input.GatewayInput.__init__')
    @patch('solace_agent_mesh.gateway.components.gateway_input.GatewayInput.get_config')
    def setUp(self, mock_get_config, mock_init):
        """Set up test fixtures."""
        # Mock parent class initialization
        mock_init.return_value = None
        
        # Mock configuration values
        mock_get_config.side_effect = lambda key, default=None: {
            "mcp_server_scopes": "test:*:*",
            "mcp_server_port": 9090,
            "mcp_server_host": "127.0.0.1",
            "mcp_server_transport": "stdio"
        }.get(key, default)
        
        # Create instance
        self.gateway_input = MCPServerGatewayInput()
        
        # Set required attributes that would normally be set by parent
        self.gateway_input.log_identifier = "[TestGateway]"
        self.gateway_input._initialize_history = MagicMock(return_value=None)
        self.gateway_input._initialize_identity_component = MagicMock(return_value=MagicMock())
        self.gateway_input.use_history = False
        self.gateway_input.gateway_id = "test-gateway"

    @patch('solace_agent_mesh.gateway.components.gateway_input.GatewayInput.invoke')
    def test_invoke_success(self, mock_super_invoke):
        """Test successful invocation."""
        # Mock parent invoke method
        mock_super_invoke.return_value = {"text": "Test response"}
        
        # Create test message and data
        message = Message(payload={"text": "Test request"})
        data = {"text": "Test request"}
        
        # Call invoke method
        result = self.gateway_input.invoke(message, data)
        
        # Verify parent method was called
        mock_super_invoke.assert_called_once_with(message, data)
        
        # Verify result
        self.assertEqual(result, {"text": "Test response"})
        
        # Verify user properties were updated
        self.assertEqual(message.get_user_properties()["mcp_server_scopes"], "test:*:*")

    @patch('solace_agent_mesh.gateway.components.gateway_input.GatewayInput.invoke')
    def test_invoke_error(self, mock_super_invoke):
        """Test invocation with error."""
        # Mock parent invoke method to raise exception
        mock_super_invoke.side_effect = Exception("Test error")
        
        # Create test message and data
        message = Message(payload={"text": "Test request"})
        data = {"text": "Test request"}
        
        # Call invoke method
        result = self.gateway_input.invoke(message, data)
        
        # Verify error response
        self.assertIn("Error processing MCP request", result["text"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("Test error", result["errors"][0])


if __name__ == '__main__':
    unittest.main()
