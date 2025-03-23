"""Tests for the AgentRegistrationListener class."""

import unittest
from unittest.mock import MagicMock, patch

from src.gateways.mcp_server.agent_registry import AgentRegistry
from src.gateways.mcp_server.agent_registration_listener import AgentRegistrationListener


class TestAgentRegistrationListener(unittest.TestCase):
    """Test cases for the AgentRegistrationListener class."""

    def setUp(self):
        """Set up test fixtures."""
        self.agent_registry = MagicMock(spec=AgentRegistry)
        self.on_agent_added = MagicMock()
        self.on_agent_removed = MagicMock()
        
        self.listener = AgentRegistrationListener(
            self.agent_registry,
            cleanup_interval_ms=100,  # Short interval for testing
            on_agent_added=self.on_agent_added,
            on_agent_removed=self.on_agent_removed
        )

    def test_process_registration_success(self):
        """Test successful processing of agent registration."""
        # Mock agent_registry.get_agent to return None (new agent)
        self.agent_registry.get_agent.return_value = None
        
        # Create test agent data
        agent_data = {
            "agent_name": "test_agent",
            "description": "Test agent",
            "actions": []
        }
        
        # Process registration
        result = self.listener.process_registration(agent_data)
        
        # Verify result
        self.assertTrue(result)
        
        # Verify agent_registry.register_agent was called
        self.agent_registry.register_agent.assert_called_once_with(agent_data)
        
        # Verify on_agent_added callback was called
        self.on_agent_added.assert_called_once_with("test_agent", agent_data)

    def test_process_registration_existing_agent(self):
        """Test processing registration for an existing agent."""
        # Mock agent_registry.get_agent to return an existing agent
        self.agent_registry.get_agent.return_value = {
            "agent_name": "test_agent",
            "description": "Existing agent",
            "actions": []
        }
        
        # Create test agent data
        agent_data = {
            "agent_name": "test_agent",
            "description": "Updated agent",
            "actions": []
        }
        
        # Process registration
        result = self.listener.process_registration(agent_data)
        
        # Verify result
        self.assertTrue(result)
        
        # Verify agent_registry.register_agent was called
        self.agent_registry.register_agent.assert_called_once_with(agent_data)
        
        # Verify on_agent_added callback was NOT called (since it's an update)
        self.on_agent_added.assert_not_called()

    def test_process_registration_no_name(self):
        """Test processing registration without agent name."""
        # Create test agent data without name
        agent_data = {
            "description": "Test agent",
            "actions": []
        }
        
        # Process registration
        result = self.listener.process_registration(agent_data)
        
        # Verify result
        self.assertFalse(result)
        
        # Verify agent_registry.register_agent was NOT called
        self.agent_registry.register_agent.assert_not_called()
        
        # Verify on_agent_added callback was NOT called
        self.on_agent_added.assert_not_called()

    def test_process_registration_error(self):
        """Test processing registration with error."""
        #  Mock agent_registry.register_agent to raise an exception
        self.agent_registry.register_agent.side_effect = ValueError("Test error")
        
        # Create test agent data
        agent_data = {
            "agent_name": "test_agent",
            "description": "Test agent",
            "actions": []
        }
        
        # Process registration
        result = self.listener.process_registration(agent_data)
        
        # Verify result
        self.assertFalse(result)
        
        # Verify on_agent_added callback was NOT called
        self.on_agent_added.assert_not_called()

    @patch('threading.Thread')
    def test_start_stop(self, mock_thread):
        """Test starting and stopping the listener."""
        # Start the listener
        self.listener.start()
        
        # Verify thread was started
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        
        # Verify running flag
        self.assertTrue(self.listener.running)
        
        # Stop the listener
        self.listener.stop()
        
        # Verify running flag
        self.assertFalse(self.listener.running)
        
        # Verify thread was joined
        mock_thread.return_value.join.assert_called_once()

    @patch('time.sleep')
    def test_cleanup_loop(self, mock_sleep):
        """Test the cleanup loop."""
        # Mock time.sleep to avoid actual sleeping
        mock_sleep.return_value = None
        
        # Mock agent_registry.cleanup_expired_agents to return expired agents
        self.agent_registry.cleanup_expired_agents.return_value = ["expired_agent"]
        
        # Set running flag to True
        self.listener.running = True
        
        # Call cleanup loop once
        self.listener._cleanup_loop()
        
        # Verify sleep was called
        mock_sleep.assert_called_once_with(0.1)  # 100ms converted to seconds
        
        # Verify agent_registry.cleanup_expired_agents was called
        self.agent_registry.cleanup_expired_agents.assert_called_once()
        
        # Verify on_agent_removed callback was called
        self.on_agent_removed.assert_called_once_with("expired_agent")


if __name__ == '__main__':
    unittest.main()
