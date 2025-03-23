"""Factory for creating and managing MCP server instances.

This module provides a factory class for creating and managing MCP server
instances, ensuring that only one instance exists per configuration.
"""

import threading
from typing import Dict, Optional

from .mcp_server import MCPServer


class MCPServerFactory:
    """Factory for creating and managing MCP server instances.

    This class ensures that only one MCP server instance exists per
    configuration, and provides methods for creating, retrieving, and
    managing server instances.

    Attributes:
        _instances: Dictionary of server instances keyed by name.
        _lock: Thread lock for thread-safe operations.
    """

    _instances: Dict[str, MCPServer] = {}
    _lock = threading.Lock()

    @classmethod
    def get_server(
        cls,
        name: str,
        host: str = "0.0.0.0",
        port: int = 8080,
        transport_type: str = "stdio",
        create_if_missing: bool = True,
    ) -> Optional[MCPServer]:
        """Get an MCP server instance.

        Args:
            name: Name of the server.
            host: Host address for the server (for SSE transport).
            port: Port for the server (for SSE transport).
            transport_type: Type of transport to use ('stdio' or 'sse').
            create_if_missing: Whether to create the server if it doesn't exist.

        Returns:
            The MCP server instance, or None if it doesn't exist and
            create_if_missing is False.
        """
        with cls._lock:
            if name in cls._instances:
                return cls._instances[name]

            if not create_if_missing:
                return None

            server = MCPServer(name, host, port, transport_type)
            cls._instances[name] = server
            return server

    @classmethod
    def remove_server(cls, name: str) -> bool:
        """Remove an MCP server instance.

        Args:
            name: Name of the server to remove.

        Returns:
            True if the server was removed, False if it didn't exist.
        """
        with cls._lock:
            if name in cls._instances:
                server = cls._instances[name]
                server.stop()
                del cls._instances[name]
                return True
            return False

    @classmethod
    def get_all_servers(cls) -> Dict[str, MCPServer]:
        """Get all MCP server instances.

        Returns:
            Dictionary of all server instances keyed by name.
        """
        with cls._lock:
            return cls._instances.copy()

    @classmethod
    def stop_all_servers(cls) -> None:
        """Stop all MCP server instances."""
        with cls._lock:
            for server in cls._instances.values():
                server.stop()
            cls._instances.clear()
