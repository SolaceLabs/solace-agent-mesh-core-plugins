"""Tests for the MCPServerGatewayOutput class."""

import unittest
from unittest.mock import patch, MagicMock

from solace_ai_connector.common.message import Message
from src.gateways.mcp_server.mcp_server_gateway_output import MCPServerGatewayOutput
from src.gateways.mcp_server.agent_registry import AgentRegistry


class TestMCPServerGatewayOutput(unittest.TestCase):
    """Test cases for the MCPServerGatewayOutput class."""

    @patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.__init__")
    @patch(
        "solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.get_config"
    )
    def setUp(self, mock_get_config, mock_init):
        """Set up test fixtures."""
        # Mock parent class initialization
        mock_init.return_value = None

        # Mock configuration values
        mock_get_config.side_effect = lambda key, default=None: {
            "mcp_server_scopes": "test:*:*"
        }.get(key, default)

        # Create instance
        self.gateway_output = MCPServerGatewayOutput()

        # Set required attributes that would normally be set by parent
        self.gateway_output.log_identifier = "[TestGateway]"
        self.gateway_output.discard_current_message = MagicMock()
        self.gateway_output.gateway_id = "test-gateway"

    @patch("src.gateways.mcp_server.agent_registry.AgentRegistry.register_agent")
    def test_handle_agent_registration(self, mock_register_agent):
        """Test handling agent registration."""
        # Create test agent data
        agent_data = {
            "agent_name": "test_agent",
            "description": "Test agent",
            "actions": [
                {"name": "test_action", "description": "Test action", "params": []}
            ],
        }

        # Call _handle_agent_registration method
        self.gateway_output._handle_agent_registration(agent_data)

        # Verify agent was registered
        mock_register_agent.assert_called_once_with(agent_data)

    def test_handle_agent_registration_no_name(self):
        """Test handling agent registration without a name."""
        # Create test agent data without name
        agent_data = {"description": "Test agent", "actions": []}

        # Mock the registry's register_agent method
        self.gateway_output.agent_registry.register_agent = MagicMock()

        # Call _handle_agent_registration method
        self.gateway_output._handle_agent_registration(agent_data)

        # Verify register_agent was not called
        self.gateway_output.agent_registry.register_agent.assert_not_called()

    @patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.invoke")
    def test_handle_agent_response(self, mock_super_invoke):
        """Test handling agent response."""
        # Mock parent invoke method
        mock_super_invoke.return_value = {"text": "Test response"}

        # Create test message with correlation ID and agent topic
        message = Message(
            payload={"text": "Test response"},
            user_properties={"mcp_correlation_id": "test-correlation-id"},
            topic="solace-agent-mesh/v1/actionResponse/agent/test_agent/test_action",
        )
        data = {"text": "Test response"}

        # Mock agent registry get_agent method
        self.gateway_output.agent_registry.get_agent = MagicMock(
            return_value={"name": "test_agent", "description": "Test agent description"}
        )

        # Call _handle_agent_response method
        result = self.gateway_output._handle_agent_response(message, data)

        # Verify parent method was called
        mock_super_invoke.assert_called_once_with(message, data)

        # Verify correlation ID was added to result
        self.assertEqual(result["mcp_correlation_id"], "test-correlation-id")

        # Verify agent info was added
        self.assertIn("agent_info", result)
        self.assertEqual(result["agent_info"]["name"], "test_agent")

    @patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.invoke")
    def test_invoke_agent_registration(self, mock_super_invoke):
        """Test invoke with agent registration message."""
        # Create test message with registration topic
        message = Message(
            payload={
                "agent_name": "test_agent",
                "description": "Test agent",
                "actions": [],
            },
            topic="solace-agent-mesh/v1/register/agent/test_agent",
        )
        data = {"agent_name": "test_agent", "description": "Test agent", "actions": []}

        # Mock _handle_agent_registration
        self.gateway_output._handle_agent_registration = MagicMock()

        # Call invoke method
        self.gateway_output.invoke(message, data)

        # Verify _handle_agent_registration was called
        self.gateway_output._handle_agent_registration.assert_called_once_with(data)

        # Verify message was discarded
        self.gateway_output.discard_current_message.assert_called_once()

    @patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.invoke")
    def test_invoke_agent_response(self, mock_super_invoke):
        """Test invoke with agent response message."""
        # Mock parent invoke method
        mock_super_invoke.return_value = {"text": "Test response"}

        # Create test message with response topic
        message = Message(
            payload={"text": "Test response"},
            topic="solace-agent-mesh/v1/actionResponse/agent/test_agent/test_action",
        )
        data = {"text": "Test response"}

        # Mock _handle_agent_response
        self.gateway_output._handle_agent_response = MagicMock(
            return_value={"text": "Processed response"}
        )

        # Call invoke method
        result = self.gateway_output.invoke(message, data)

        # Verify _handle_agent_response was called
        self.gateway_output._handle_agent_response.assert_called_once_with(
            message, data
        )

        # Verify result
        self.assertEqual(result, {"text": "Processed response"})

    @patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.invoke")
    def test_invoke_other_message(self, mock_super_invoke):
        """Test invoke with other message type."""
        # Mock parent invoke method
        mock_super_invoke.return_value = {"text": "Test response"}

        # Create test message with other topic
        message = Message(
            payload={"text": "Test message"}, topic="solace-agent-mesh/v1/other/topic"
        )
        data = {"text": "Test message"}

        # Call invoke method
        result = self.gateway_output.invoke(message, data)

        # Verify parent method was called
        mock_super_invoke.assert_called_once_with(message, data)

        # Verify result
        self.assertEqual(result, {"text": "Test response"})

    @patch("solace_agent_mesh.gateway.components.gateway_output.GatewayOutput.invoke")
    def test_invoke_error(self, mock_super_invoke):
        """Test invoke with error."""
        # Create a specific exception with a clear message
        test_exception = Exception("Test error")
        # Mock parent invoke method to raise the specific exception
        mock_super_invoke.side_effect = test_exception

        # Create test message with a topic that doesn't match any special cases
        message = Message(
            payload={"text": "Test message"}, topic="solace-agent-mesh/v1/other/topic"
        )
        data = {"text": "Test message"}

        # Call invoke method
        result = self.gateway_output.invoke(message, data)

        # Verify error response
        self.assertIn("Error processing agent response", result["text"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0], "Test error")

    def test_get_filtered_agents(self):
        """Test getting filtered agents."""
        # Mock the registry's get_filtered_agents method
        self.gateway_output.agent_registry.get_filtered_agents = MagicMock(
            return_value={"test_agent": {"name": "test_agent"}}
        )

        # Call get_filtered_agents method
        result = self.gateway_output.get_filtered_agents()

        # Verify get_filtered_agents was called with the correct scope
        self.gateway_output.agent_registry.get_filtered_agents.assert_called_once_with(
            "test:*:*"
        )

        # Verify result
        self.assertEqual(result, {"test_agent": {"name": "test_agent"}})

    def test_handle_timer_event(self):
        """Test handling timer events."""
        # Mock the registry's cleanup_expired_agents method
        self.gateway_output.agent_registry.cleanup_expired_agents = MagicMock(
            return_value=["expired_agent"]
        )

        # Call handle_timer_event method
        self.gateway_output.handle_timer_event("agent_registry_cleanup")

        # Verify cleanup_expired_agents was called
        self.gateway_output.agent_registry.cleanup_expired_agents.assert_called_once()


if __name__ == "__main__":
    unittest.main()
