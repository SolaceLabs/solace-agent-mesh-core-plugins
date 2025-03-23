"""Tests for the AgentRegistry class."""

import time
import unittest
from unittest.mock import patch

from src.gateways.mcp_server.agent_registry import AgentRegistry


class TestAgentRegistry(unittest.TestCase):
    """Test cases for the AgentRegistry class."""

    def setUp(self):
        """Set up test fixtures."""
        self.registry = AgentRegistry(ttl_ms=1000)  # 1 second TTL for testing

    def test_register_agent(self):
        """Test registering an agent."""
        # Register an agent
        agent_data = {
            "agent_name": "test_agent",
            "description": "Test agent",
            "actions": [
                {
                    "name": "test_action",
                    "description": "Test action",
                    "params": []
                }
            ]
        }
        self.registry.register_agent(agent_data)

        # Verify agent was registered
        self.assertIn("test_agent", self.registry.agents)
        self.assertEqual(self.registry.agents["test_agent"]["description"], "Test agent")
        self.assertIn("last_updated", self.registry.agents["test_agent"])

    def test_register_agent_without_name(self):
        """Test registering an agent without a name."""
        # Try to register an agent without a name
        agent_data = {
            "description": "Test agent",
            "actions": []
        }
        with self.assertRaises(ValueError):
            self.registry.register_agent(agent_data)

    def test_get_agent(self):
        """Test getting an agent by name."""
        # Register an agent
        agent_data = {
            "agent_name": "test_agent",
            "description": "Test agent",
            "actions": []
        }
        self.registry.register_agent(agent_data)

        # Get the agent
        agent = self.registry.get_agent("test_agent")
        self.assertIsNotNone(agent)
        self.assertEqual(agent["description"], "Test agent")

        # Try to get a non-existent agent
        agent = self.registry.get_agent("non_existent_agent")
        self.assertIsNone(agent)

    def test_get_all_agents(self):
        """Test getting all registered agents."""
        # Register two agents
        agent1_data = {
            "agent_name": "agent1",
            "description": "Agent 1",
            "actions": []
        }
        agent2_data = {
            "agent_name": "agent2",
            "description": "Agent 2",
            "actions": []
        }
        self.registry.register_agent(agent1_data)
        self.registry.register_agent(agent2_data)

        # Get all agents
        agents = self.registry.get_all_agents()
        self.assertEqual(len(agents), 2)
        self.assertIn("agent1", agents)
        self.assertIn("agent2", agents)

    def test_get_filtered_agents_wildcard(self):
        """Test getting agents filtered by wildcard scope."""
        # Register two agents
        agent1_data = {
            "agent_name": "agent1",
            "description": "Agent 1",
            "actions": []
        }
        agent2_data = {
            "agent_name": "agent2",
            "description": "Agent 2",
            "actions": []
        }
        self.registry.register_agent(agent1_data)
        self.registry.register_agent(agent2_data)

        # Get filtered agents with wildcard
        agents = self.registry.get_filtered_agents("*:*:*")
        self.assertEqual(len(agents), 2)
        self.assertIn("agent1", agents)
        self.assertIn("agent2", agents)

    def test_get_filtered_agents_specific(self):
        """Test getting agents filtered by specific scope."""
        # Register two agents
        agent1_data = {
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
        agent2_data = {
            "agent_name": "agent2",
            "description": "Agent 2",
            "actions": [
                {
                    "name": "action2",
                    "description": "Action 2",
                    "params": []
                }
            ]
        }
        self.registry.register_agent(agent1_data)
        self.registry.register_agent(agent2_data)

        # Get filtered agents with specific agent
        agents = self.registry.get_filtered_agents("agent1:*:*")
        self.assertEqual(len(agents), 1)
        self.assertIn("agent1", agents)
        self.assertNotIn("agent2", agents)

    def test_remove_agent(self):
        """Test removing an agent."""
        # Register an agent
        agent_data = {
            "agent_name": "test_agent",
            "description": "Test agent",
            "actions": []
        }
        self.registry.register_agent(agent_data)

        # Remove the agent
        result = self.registry.remove_agent("test_agent")
        self.assertTrue(result)
        self.assertNotIn("test_agent", self.registry.agents)

        # Try to remove a non-existent agent
        result = self.registry.remove_agent("non_existent_agent")
        self.assertFalse(result)

    def test_cleanup_expired_agents(self):
        """Test cleaning up expired agents."""
        # Register an agent
        agent_data = {
            "agent_name": "test_agent",
            "description": "Test agent",
            "actions": []
        }
        self.registry.register_agent(agent_data)

        # Wait for the agent to expire
        time.sleep(1.1)  # Wait slightly longer than TTL

        # Clean up expired agents
        expired = self.registry.cleanup_expired_agents()
        self.assertEqual(len(expired), 1)
        self.assertIn("test_agent", expired)
        self.assertNotIn("test_agent", self.registry.agents)

    @patch('time.time')
    def test_cleanup_expired_agents_with_mock(self, mock_time):
        """Test cleaning up expired agents with mocked time."""
        # Set initial time
        mock_time.return_value = 1000

        # Register an agent
        agent_data = {
            "agent_name": "test_agent",
            "description": "Test agent",
            "actions": []
        }
        self.registry.register_agent(agent_data)

        # Advance time beyond TTL
        mock_time.return_value = 1002  # 2 seconds later (> 1000ms TTL)

        # Clean up expired agents
        expired = self.registry.cleanup_expired_agents()
        self.assertEqual(len(expired), 1)
        self.assertIn("test_agent", expired)
        self.assertNotIn("test_agent", self.registry.agents)


if __name__ == '__main__':
    unittest.main()
