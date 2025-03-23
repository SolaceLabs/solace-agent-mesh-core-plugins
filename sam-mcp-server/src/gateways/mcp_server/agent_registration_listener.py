"""Agent registration listener for the MCP Server Gateway.

This module provides a component that listens for agent registration messages
and updates the agent registry accordingly.
"""

import threading
import time
from typing import Dict, Any, Optional, Callable

from solace_ai_connector.common.log import log
from .agent_registry import AgentRegistry


class AgentRegistrationListener:
    """Listener for agent registration messages.

    This class listens for agent registration messages and updates the agent registry
    with the information received. It also handles periodic cleanup of expired agents.

    Attributes:
        agent_registry: Registry to store agent information.
        cleanup_interval_ms: Interval in milliseconds for cleaning up expired agents.
        running: Flag indicating whether the listener is running.
        cleanup_thread: Thread for periodic cleanup of expired agents.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        cleanup_interval_ms: int = 60000,
        on_agent_added: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_agent_removed: Optional[Callable[[str], None]] = None,
    ):
        """Initialize the agent registration listener.

        Args:
            agent_registry: Registry to store agent information.
            cleanup_interval_ms: Interval in milliseconds for cleaning up expired agents.
            on_agent_added: Optional callback when an agent is added.
            on_agent_removed: Optional callback when an agent is removed.
        """
        self.agent_registry = agent_registry
        self.cleanup_interval_ms = cleanup_interval_ms
        self.running = False
        self.cleanup_thread = None
        self.on_agent_added = on_agent_added
        self.on_agent_removed = on_agent_removed
        self.log_identifier = "[AgentRegistrationListener] "

    def start(self):
        """Start the agent registration listener.

        This method starts the cleanup thread for periodic cleanup of expired agents.
        """
        if self.running:
            return

        self.running = True
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        log.info(f"{self.log_identifier}Agent registration listener started")

    def stop(self):
        """Stop the agent registration listener.

        This method stops the cleanup thread.
        """
        if not self.running:
            return

        self.running = False
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=1.0)
            self.cleanup_thread = None
        log.info(f"{self.log_identifier}Agent registration listener stopped")

    def process_registration(self, data: Dict[str, Any]) -> bool:
        """Process an agent registration message.

        Args:
            data: Agent registration data.

        Returns:
            True if the agent was registered successfully, False otherwise.
        """
        try:
            agent_name = data.get("agent_name")
            if not agent_name:
                log.warning(
                    f"{self.log_identifier}Received agent registration without name"
                )
                return False

            # Check if this is a new agent
            is_new = self.agent_registry.get_agent(agent_name) is None

            # Register agent in the registry
            self.agent_registry.register_agent(data)

            # Call the callback if this is a new agent
            if is_new and self.on_agent_added:
                self.on_agent_added(agent_name, data)

            log.info(f"{self.log_identifier}Registered agent: {agent_name}")
            return True

        except Exception as e:
            log.error(
                f"{self.log_identifier}Error handling agent registration: {str(e)}"
            )
            return False

    def _cleanup_loop(self):
        """Cleanup loop for periodic cleanup of expired agents."""
        while self.running:
            try:
                # Sleep for the cleanup interval
                time.sleep(self.cleanup_interval_ms / 1000)

                # Clean up expired agents
                expired_agents = self.agent_registry.cleanup_expired_agents()
                if expired_agents:
                    log.info(
                        f"{self.log_identifier}Removed expired agents: {', '.join(expired_agents)}"
                    )

                    # Call the callback for each removed agent
                    if self.on_agent_removed:
                        for agent_name in expired_agents:
                            self.on_agent_removed(agent_name)

            except Exception as e:
                log.error(f"{self.log_identifier}Error in cleanup loop: {str(e)}")
