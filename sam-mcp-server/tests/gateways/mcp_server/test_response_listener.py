"""Tests for the response listener functionality in MCPServerGatewayOutput."""

import unittest
from unittest.mock import patch, MagicMock, call

from solace_ai_connector.common.message import Message
from src.gateways.mcp_server.mcp_server_gateway_output import MCPServerGatewayOutput
from src.gateways.mcp_server.agent_registry import AgentRegistry
from src.gateways.mcp_server.mcp_server_manager import MCPServerManager


class TestResponseListener(unittest.TestCase):
    """Test cases for the response listener functionality in MCPServerGatewayOutput."""

    @patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.__init__")
    @patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.get_config")
    @patch("src.gateways.mcp_server.agent_registration_listener.AgentRegistrationListener")
    def setUp(self, mock_listener_class, mock_get_config, mock_init):
        """Set up test fixtures."""
        # Mock parent class initialization
        mock_init.return_value = None

        # Mock configuration values
        mock_get_config.side_effect = lambda key, default=None: {
            "mcp_server_scopes": "test:*:*",
            "agent_ttl_ms": 60000,
            "agent_cleanup_interval_ms": 60000
        }.get(key, default)
        
        # Mock the AgentRegistrationListener
        self.mock_listener = MagicMock()
        mock_listener_class.return_value = self.mock_listener

        # Create instance
        self.gateway_output = MCPServerGatewayOutput()

        # Set required attributes that would normally be set by parent
        self.gateway_output.log_identifier = "[TestGateway]"
        self.gateway_output.discard_current_message = MagicMock()
        
        # Mock the agent registry
        self.gateway_output.agent_registry = MagicMock(spec=AgentRegistry)
        
        # Initialize server_managers dictionary
        self.gateway_output.server_managers = {}

    @patch("src.gateways.mcp_server.mcp_server_gateway_output.MCPServerGatewayOutput._get_server_manager")
    @patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.invoke")
    def test_handle_agent_response(self, mock_super_invoke, mock_get_server_manager):
        """Test handling agent response."""
        # Mock parent invoke method
        mock_super_invoke.return_value = {"text": "Test response"}

        # Mock server manager
        mock_server_manager = MagicMock(spec=MCPServerManager)
        mock_server_manager.handle_action_response.return_value = True
        mock_get_server_manager.return_value = mock_server_manager

        # Create test message with correlation ID and agent topic
        message = Message(
            payload={"text": "Test response"},
            user_properties={
                "mcp_correlation_id": "test-correlation-id",
                "gateway_id": "test-server"
            },
            topic="solace-agent-mesh/v1/actionResponse/agent/test_agent/test_action",
        )
        data = {"text": "Test response"}

        # Mock agent registry get_agent method
        self.gateway_output.agent_registry.get_agent.return_value = {
            "agent_name": "test_agent", 
            "description": "Test agent description"
        }

        # Call _handle_agent_response method
        result = self.gateway_output._handle_agent_response(message, data)

        # Verify parent method was called
        mock_super_invoke.assert_called_once_with(message, data)

        # Verify _get_server_manager was called
        mock_get_server_manager.assert_called_once_with("test-server")

        # Verify handle_action_response was called
        mock_server_manager.handle_action_response.assert_called_once_with(
            "test-correlation-id", data
        )

        # Verify correlation ID was added to result
        self.assertEqual(result["mcp_correlation_id"], "test-correlation-id")

        # Verify agent info was added
        self.assertIn("agent_info", result)
        self.assertEqual(result["agent_info"]["name"], "test_agent")

    @patch("src.gateways.mcp_server.mcp_server_gateway_output.MCPServerGatewayOutput._get_server_manager")
    @patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.invoke")
    def test_handle_timeout_response(self, mock_super_invoke, mock_get_server_manager):
        """Test handling timeout response."""
        # Mock parent invoke method
        mock_super_invoke.return_value = {"text": "Timeout response"}

        # Mock server manager
        mock_server_manager = MagicMock(spec=MCPServerManager)
        mock_server_manager.handle_action_response.return_value = True
        mock_get_server_manager.return_value = mock_server_manager

        # Create test message with correlation ID and timeout topic
        message = Message(
            payload={"message": "Request timed out"},
            user_properties={
                "mcp_correlation_id": "test-correlation-id",
                "gateway_id": "test-server"
            },
            topic="solace-agent-mesh/v1/actionResponse/agent/test_agent/test_action/timeout",
        )
        data = {"message": "Request timed out"}

        # Call _handle_timeout_response method
        result = self.gateway_output._handle_timeout_response(message, data)

        # Verify parent method was called
        mock_super_invoke.assert_called_once_with(message, data)

        # Verify _get_server_manager was called
        mock_get_server_manager.assert_called_once_with("test-server")

        # Verify handle_action_response was called with error data
        mock_server_manager.handle_action_response.assert_called_once()
        call_args = mock_server_manager.handle_action_response.call_args[0]
        self.assertEqual(call_args[0], "test-correlation-id")
        self.assertEqual(call_args[1]["error"], "Request timed out")

        # Verify correlation ID was added to result
        self.assertEqual(result["mcp_correlation_id"], "test-correlation-id")

        # Verify agent info was added
        self.assertIn("agent_info", result)
        self.assertEqual(result["agent_info"]["name"], "test_agent")

    @patch("src.gateways.mcp_server.mcp_server_manager.MCPServerManager")
    def test_get_server_manager_new(self, mock_server_manager_class):
        """Test getting a new server manager."""
        # Mock MCPServerManager
        mock_server_manager = MagicMock(spec=MCPServerManager)
        mock_server_manager.initialize.return_value = True
        mock_server_manager_class.return_value = mock_server_manager

        # Call _get_server_manager method
        result = self.gateway_output._get_server_manager("test-server")

        # Verify MCPServerManager was created
        mock_server_manager_class.assert_called_once_with(
            agent_registry=self.gateway_output.agent_registry,
            server_name="test-server",
            scopes="test:*:*"
        )

        # Verify initialize was called
        mock_server_manager.initialize.assert_called_once()

        # Verify result
        self.assertEqual(result, mock_server_manager)
        self.assertIn("test-server", self.gateway_output.server_managers)
        self.assertEqual(self.gateway_output.server_managers["test-server"], mock_server_manager)

    def test_get_server_manager_existing(self):
        """Test getting an existing server manager."""
        # Create a mock server manager
        mock_server_manager = MagicMock(spec=MCPServerManager)
        
        # Add it to the server_managers dictionary
        self.gateway_output.server_managers = {"test-server": mock_server_manager}

        # Call _get_server_manager method
        result = self.gateway_output._get_server_manager("test-server")

        # Verify result
        self.assertEqual(result, mock_server_manager)

    @patch("src.gateways.mcp_server.mcp_server_manager.MCPServerManager")
    def test_get_server_manager_failure(self, mock_server_manager_class):
        """Test getting a server manager that fails to initialize."""
        # Mock MCPServerManager
        mock_server_manager = MagicMock(spec=MCPServerManager)
        mock_server_manager.initialize.return_value = False
        mock_server_manager_class.return_value = mock_server_manager

        # Call _get_server_manager method
        result = self.gateway_output._get_server_manager("test-server")

        # Verify MCPServerManager was created
        mock_server_manager_class.assert_called_once()

        # Verify initialize was called
        mock_server_manager.initialize.assert_called_once()

        # Verify result
        self.assertIsNone(result)
        self.assertNotIn("test-server", self.gateway_output.server_managers)

    def test_cleanup_server_managers(self):
        """Test cleaning up server managers."""
        # Create mock server managers
        mock_server_manager1 = MagicMock(spec=MCPServerManager)
        mock_server_manager1.cleanup_pending_requests.return_value = ["request1", "request2"]
        
        mock_server_manager2 = MagicMock(spec=MCPServerManager)
        mock_server_manager2.cleanup_pending_requests.return_value = []
        
        # Add them to the server_managers dictionary
        self.gateway_output.server_managers = {
            "server1": mock_server_manager1,
            "server2": mock_server_manager2
        }

        # Call _cleanup_server_managers method
        self.gateway_output._cleanup_server_managers()

        # Verify cleanup_pending_requests was called on both managers
        mock_server_manager1.cleanup_pending_requests.assert_called_once()
        mock_server_manager2.cleanup_pending_requests.assert_called_once()

    def test_stop_component(self):
        """Test stopping the component."""
        # Create mock server managers
        mock_server_manager1 = MagicMock(spec=MCPServerManager)
        mock_server_manager2 = MagicMock(spec=MCPServerManager)
        
        # Add them to the server_managers dictionary
        self.gateway_output.server_managers = {
            "server1": mock_server_manager1,
            "server2": mock_server_manager2
        }

        # Mock parent stop_component method
        with patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.stop_component") as mock_super_stop:
            # Call stop_component method
            self.gateway_output.stop_component()
            
            # Verify shutdown was called on both managers
            mock_server_manager1.shutdown.assert_called_once()
            mock_server_manager2.shutdown.assert_called_once()
            
            # Verify server_managers was cleared
            self.assertEqual(len(self.gateway_output.server_managers), 0)
            
            # Verify registration_listener was stopped
            self.gateway_output.registration_listener.stop.assert_called_once()
            
            # Verify parent method was called
            mock_super_stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
