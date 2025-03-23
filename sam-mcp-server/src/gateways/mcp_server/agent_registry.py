"""Agent registry for the MCP Server Gateway.

This module provides a registry for storing and managing agent information
for the MCP Server Gateway.
"""

import threading
import time
from typing import Dict, Any, List, Optional


class AgentRegistry:
    """Registry for storing and managing agent information.

    This class provides thread-safe storage and retrieval of agent information,
    including filtering by scopes and handling agent expiration.

    Attributes:
        agents: Dictionary of registered agents.
        lock: Thread lock for thread-safe operations.
        ttl_ms: Time-to-live for agent registrations in milliseconds.
    """

    def __init__(self, ttl_ms: int = 60000):
        """Initialize the agent registry.

        Args:
            ttl_ms: Time-to-live for agent registrations in milliseconds.
        """
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.ttl_ms = ttl_ms

    def register_agent(self, agent_data: Dict[str, Any]) -> None:
        """Register or update an agent in the registry.

        Args:
            agent_data: Agent data to register.

        Raises:
            ValueError: If agent_data does not contain required fields.
        """
        agent_name = agent_data.get("agent_name")
        if not agent_name:
            raise ValueError("Agent data must contain 'agent_name'")

        with self.lock:
            # Add current time for TTL tracking
            agent_data["last_updated"] = int(time.time() * 1000)
            self.agents[agent_name] = agent_data

    def get_agent(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Get agent information by name.

        Args:
            agent_name: Name of the agent to retrieve.

        Returns:
            Agent information or None if not found.
        """
        with self.lock:
            return self.agents.get(agent_name)

    def get_all_agents(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered agents.

        Returns:
            Dictionary of all registered agents.
        """
        with self.lock:
            # Return a copy to prevent modification
            return self.agents.copy()

    def get_filtered_agents(self, scopes: str) -> Dict[str, Dict[str, Any]]:
        """Get agents filtered by scopes.

        Args:
            scopes: Scope pattern to filter agents by.

        Returns:
            Dictionary of agents matching the scope pattern.
        """
        with self.lock:
            # If scope is wildcard, return all agents
            if scopes == "*:*:*":
                return self.agents.copy()

            # Parse scope patterns
            scope_patterns = scopes.split(",")
            filtered_agents = {}

            for agent_name, agent_data in self.agents.items():
                # Check if agent matches any scope pattern
                if self._agent_matches_scopes(agent_data, scope_patterns):
                    filtered_agents[agent_name] = agent_data

            return filtered_agents

    def remove_agent(self, agent_name: str) -> bool:
        """Remove an agent from the registry.

        Args:
            agent_name: Name of the agent to remove.

        Returns:
            True if agent was removed, False if not found.
        """
        with self.lock:
            if agent_name in self.agents:
                del self.agents[agent_name]
                return True
            return False

    def cleanup_expired_agents(self) -> List[str]:
        """Remove expired agents from the registry.

        Returns:
            List of names of agents that were removed.
        """
        current_time = int(time.time() * 1000)
        expired_agents = []

        with self.lock:
            for agent_name, agent_data in list(self.agents.items()):
                last_updated = agent_data.get("last_updated", 0)
                if current_time - last_updated > self.ttl_ms:
                    del self.agents[agent_name]
                    expired_agents.append(agent_name)

        return expired_agents

    def _agent_matches_scopes(self, agent_data: Dict[str, Any], scope_patterns: List[str]) -> bool:
        """Check if an agent matches any of the scope patterns.

        Args:
            agent_data: Agent data to check.
            scope_patterns: List of scope patterns to match against.

        Returns:
            True if agent matches any scope pattern, False otherwise.
        """
        agent_name = agent_data.get("agent_name", "")
        actions = agent_data.get("actions", [])

        for pattern in scope_patterns:
            # Parse pattern parts
            pattern_parts = pattern.split(":")
            if len(pattern_parts) != 3:
                continue

            agent_pattern, action_pattern, permission_pattern = pattern_parts

            # Check agent name match
            if agent_pattern != "*" and agent_pattern != agent_name:
                continue

            # If we're only checking agent level, and it matched, return True
            if action_pattern == "*" and permission_pattern == "*":
                return True

            # Check actions
            for action in actions:
                action_name = action.get("name", "")
                
                # Check action name match
                if action_pattern != "*" and action_pattern != action_name:
                    continue
                
                # If permission is wildcard, we have a match
                if permission_pattern == "*":
                    return True
                
                # Check specific permissions (not implemented yet)
                # This would check action.get("required_scopes") against permission_pattern

        return False
