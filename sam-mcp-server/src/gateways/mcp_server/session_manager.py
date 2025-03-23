"""Session manager for MCP Server Gateway.

This module provides a session manager that tracks and manages client sessions
for the MCP Server Gateway, including authentication and authorization.
"""

import threading
import time
import uuid
from typing import Dict, Any, Optional, List, Set


class Session:
    """Represents a client session.

    Attributes:
        session_id: Unique identifier for the session.
        client_id: Identifier for the client.
        username: Username used for authentication.
        scopes: Set of scopes the session has access to.
        created_at: Timestamp when the session was created.
        last_active: Timestamp when the session was last active.
        metadata: Additional session metadata.
    """

    def __init__(
        self,
        client_id: str,
        username: Optional[str] = None,
        scopes: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize a new session.

        Args:
            client_id: Identifier for the client.
            username: Username used for authentication.
            scopes: Set of scopes the session has access to.
            metadata: Additional session metadata.
        """
        self.session_id = str(uuid.uuid4())
        self.client_id = client_id
        self.username = username
        self.scopes = scopes or set()
        self.created_at = time.time()
        self.last_active = self.created_at
        self.metadata = metadata or {}

    def update_activity(self):
        """Update the last active timestamp."""
        self.last_active = time.time()

    def has_scope(self, scope: str) -> bool:
        """Check if the session has a specific scope.

        Args:
            scope: The scope to check.

        Returns:
            True if the session has the scope, False otherwise.
        """
        # If the session has the wildcard scope, it has all scopes
        if "*:*:*" in self.scopes:
            return True

        # Check if the exact scope is in the session's scopes
        if scope in self.scopes:
            return True

        # Check for wildcard matches
        parts = scope.split(":")
        if len(parts) != 3:
            return False

        agent, action, permission = parts

        # Check for wildcard patterns
        patterns = [
            f"{agent}:*:*",
            f"*:{action}:*",
            f"*:*:{permission}",
            f"{agent}:{action}:*",
            f"{agent}:*:{permission}",
            f"*:{action}:{permission}",
        ]

        return any(pattern in self.scopes for pattern in patterns)


class SessionManager:
    """Manages client sessions for the MCP Server Gateway.

    This class provides methods for creating, retrieving, and managing
    client sessions, including authentication and authorization.

    Attributes:
        sessions: Dictionary of active sessions keyed by session ID.
        clients: Dictionary mapping client IDs to session IDs.
        lock: Thread lock for thread-safe operations.
        session_ttl_seconds: Time-to-live for sessions in seconds.
    """

    def __init__(self, session_ttl_seconds: int = 3600):
        """Initialize the session manager.

        Args:
            session_ttl_seconds: Time-to-live for sessions in seconds.
        """
        self.sessions: Dict[str, Session] = {}
        self.clients: Dict[str, str] = {}  # Maps client_id to session_id
        self.lock = threading.Lock()
        self.session_ttl_seconds = session_ttl_seconds
        self.log_identifier = "[SessionManager] "

    def create_session(
        self,
        client_id: str,
        username: Optional[str] = None,
        scopes: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Session:
        """Create a new session.

        Args:
            client_id: Identifier for the client.
            username: Username used for authentication.
            scopes: Set of scopes the session has access to.
            metadata: Additional session metadata.

        Returns:
            The newly created session.
        """
        with self.lock:
            # Check if the client already has a session
            if client_id in self.clients:
                # Remove the old session
                old_session_id = self.clients[client_id]
                if old_session_id in self.sessions:
                    del self.sessions[old_session_id]

            # Create a new session
            session = Session(client_id, username, scopes, metadata)
            self.sessions[session.session_id] = session
            self.clients[client_id] = session.session_id
            return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID.

        Args:
            session_id: The session ID to retrieve.

        Returns:
            The session if found, None otherwise.
        """
        with self.lock:
            session = self.sessions.get(session_id)
            if session:
                session.update_activity()
            return session

    def get_session_by_client_id(self, client_id: str) -> Optional[Session]:
        """Get a session by client ID.

        Args:
            client_id: The client ID to retrieve the session for.

        Returns:
            The session if found, None otherwise.
        """
        with self.lock:
            session_id = self.clients.get(client_id)
            if not session_id:
                return None

            # Get the session directly from the sessions dictionary
            # instead of calling get_session to avoid deadlock
            session = self.sessions.get(session_id)
            if session:
                session.update_activity()
            return session

    def remove_session(self, session_id: str) -> bool:
        """Remove a session.

        Args:
            session_id: The session ID to remove.

        Returns:
            True if the session was removed, False otherwise.
        """
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                return False

            # Remove the session
            del self.sessions[session_id]
            if session.client_id in self.clients:
                del self.clients[session.client_id]
            return True

    def cleanup_expired_sessions(self) -> List[str]:
        """Remove expired sessions.

        Returns:
            List of session IDs that were removed.
        """
        current_time = time.time()
        expired_sessions = []

        with self.lock:
            for session_id, session in list(self.sessions.items()):
                if current_time - session.last_active > self.session_ttl_seconds:
                    # Session has expired
                    expired_sessions.append(session_id)
                    del self.sessions[session_id]
                    if session.client_id in self.clients:
                        del self.clients[session.client_id]

        return expired_sessions

    def authenticate(
        self, client_id: str, credentials: Dict[str, Any]
    ) -> Optional[Session]:
        """Authenticate a client and create a session.

        Args:
            client_id: Identifier for the client.
            credentials: Authentication credentials.

        Returns:
            The session if authentication was successful, None otherwise.
        """
        # This is a simple implementation that accepts all authentication
        # In a real implementation, this would validate credentials against
        # a user database or other authentication system
        username = credentials.get("username", "anonymous")

        # Default to all scopes for now
        # In a real implementation, scopes would be determined based on
        # the authenticated user's permissions
        scopes = set(["*:*:*"])

        # Create and return the session
        return self.create_session(client_id, username, scopes)

    def authorize(self, session_id: str, scope: str) -> bool:
        """Check if a session is authorized for a specific scope.

        Args:
            session_id: The session ID to check.
            scope: The scope to check.

        Returns:
            True if the session is authorized, False otherwise.
        """
        session = self.get_session(session_id)
        if not session:
            return False
        return session.has_scope(scope)

    def get_all_sessions(self) -> Dict[str, Session]:
        """Get all active sessions.

        Returns:
            Dictionary of all active sessions keyed by session ID.
        """
        with self.lock:
            return self.sessions.copy()
