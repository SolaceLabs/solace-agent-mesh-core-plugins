"""Tests for the SessionManager class."""

import time
import unittest
from unittest.mock import patch

from src.gateways.mcp_server.session_manager import SessionManager, Session


class TestSessionManager(unittest.TestCase):
    """Test cases for the SessionManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.session_manager = SessionManager(session_ttl_seconds=1)  # Short TTL for testing

    def test_create_session(self):
        """Test creating a session."""
        # Create a session
        session = self.session_manager.create_session(
            client_id="test-client",
            username="test-user",
            scopes=set(["test:*:*"]),
            metadata={"test": "value"}
        )
        
        # Verify session was created
        self.assertIsNotNone(session)
        self.assertEqual(session.client_id, "test-client")
        self.assertEqual(session.username, "test-user")
        self.assertEqual(session.scopes, set(["test:*:*"]))
        self.assertEqual(session.metadata, {"test": "value"})
        
        # Verify session was added to sessions dictionary
        self.assertIn(session.session_id, self.session_manager.sessions)
        
        # Verify client ID was mapped to session ID
        self.assertIn("test-client", self.session_manager.clients)
        self.assertEqual(self.session_manager.clients["test-client"], session.session_id)

    def test_create_session_existing_client(self):
        """Test creating a session for an existing client."""
        # Create a session
        session1 = self.session_manager.create_session(client_id="test-client")
        
        # Create another session for the same client
        session2 = self.session_manager.create_session(client_id="test-client")
        
        # Verify sessions are different
        self.assertNotEqual(session1.session_id, session2.session_id)
        
        # Verify only the new session is in the sessions dictionary
        self.assertNotIn(session1.session_id, self.session_manager.sessions)
        self.assertIn(session2.session_id, self.session_manager.sessions)
        
        # Verify client ID is mapped to the new session ID
        self.assertEqual(self.session_manager.clients["test-client"], session2.session_id)

    def test_get_session(self):
        """Test getting a session by ID."""
        # Create a session
        session = self.session_manager.create_session(client_id="test-client")
        
        # Get the session
        retrieved_session = self.session_manager.get_session(session.session_id)
        
        # Verify session was retrieved
        self.assertIsNotNone(retrieved_session)
        self.assertEqual(retrieved_session.session_id, session.session_id)
        
        # Verify last_active was updated
        self.assertGreaterEqual(retrieved_session.last_active, session.created_at)
        
        # Try to get a non-existent session
        non_existent_session = self.session_manager.get_session("non-existent")
        
        # Verify non-existent session is None
        self.assertIsNone(non_existent_session)

    def test_get_session_by_client_id(self):
        """Test getting a session by client ID."""
        # Create a session
        session = self.session_manager.create_session(client_id="test-client")
        
        # Get the session by client ID
        retrieved_session = self.session_manager.get_session_by_client_id("test-client")
        
        # Verify session was retrieved
        self.assertIsNotNone(retrieved_session)
        self.assertEqual(retrieved_session.session_id, session.session_id)
        
        # Try to get a session for a non-existent client
        non_existent_session = self.session_manager.get_session_by_client_id("non-existent")
        
        # Verify non-existent session is None
        self.assertIsNone(non_existent_session)

    def test_remove_session(self):
        """Test removing a session."""
        # Create a session
        session = self.session_manager.create_session(client_id="test-client")
        
        # Remove the session
        result = self.session_manager.remove_session(session.session_id)
        
        # Verify session was removed
        self.assertTrue(result)
        self.assertNotIn(session.session_id, self.session_manager.sessions)
        self.assertNotIn("test-client", self.session_manager.clients)
        
        # Try to remove a non-existent session
        result = self.session_manager.remove_session("non-existent")
        
        # Verify result is False
        self.assertFalse(result)

    def test_cleanup_expired_sessions(self):
        """Test cleaning up expired sessions."""
        # Create a session
        session = self.session_manager.create_session(client_id="test-client")
        
        # Wait for the session to expire
        time.sleep(1.1)  # Wait slightly longer than TTL
        
        # Clean up expired sessions
        expired_sessions = self.session_manager.cleanup_expired_sessions()
        
        # Verify session was removed
        self.assertEqual(len(expired_sessions), 1)
        self.assertIn(session.session_id, expired_sessions)
        self.assertNotIn(session.session_id, self.session_manager.sessions)
        self.assertNotIn("test-client", self.session_manager.clients)

    def test_authenticate(self):
        """Test authenticating a client."""
        # Authenticate a client
        session = self.session_manager.authenticate(
            client_id="test-client",
            credentials={"username": "test-user"}
        )
        
        # Verify session was created
        self.assertIsNotNone(session)
        self.assertEqual(session.client_id, "test-client")
        self.assertEqual(session.username, "test-user")
        self.assertEqual(session.scopes, set(["*:*:*"]))  # Default scope
        
        # Verify session was added to sessions dictionary
        self.assertIn(session.session_id, self.session_manager.sessions)

    def test_authorize(self):
        """Test authorizing a session."""
        # Create a session with specific scopes
        session = self.session_manager.create_session(
            client_id="test-client",
            scopes=set(["test:read:*", "test:write:data"])
        )
        
        # Test authorization with exact scope
        self.assertTrue(self.session_manager.authorize(session.session_id, "test:read:*"))
        self.assertTrue(self.session_manager.authorize(session.session_id, "test:write:data"))
        
        # Test authorization with non-matching scope
        self.assertFalse(self.session_manager.authorize(session.session_id, "test:delete:*"))
        
        # Test authorization with non-existent session
        self.assertFalse(self.session_manager.authorize("non-existent", "test:read:*"))
        
        # Create a session with wildcard scope
        wildcard_session = self.session_manager.create_session(
            client_id="wildcard-client",
            scopes=set(["*:*:*"])
        )
        
        # Test authorization with wildcard scope
        self.assertTrue(self.session_manager.authorize(wildcard_session.session_id, "any:scope:here"))

    def test_get_all_sessions(self):
        """Test getting all sessions."""
        # Create two sessions
        session1 = self.session_manager.create_session(client_id="client1")
        session2 = self.session_manager.create_session(client_id="client2")
        
        # Get all sessions
        sessions = self.session_manager.get_all_sessions()
        
        # Verify sessions were returned
        self.assertEqual(len(sessions), 2)
        self.assertIn(session1.session_id, sessions)
        self.assertIn(session2.session_id, sessions)


class TestSession(unittest.TestCase):
    """Test cases for the Session class."""

    def test_initialization(self):
        """Test session initialization."""
        # Create a session
        session = Session(
            client_id="test-client",
            username="test-user",
            scopes=set(["test:*:*"]),
            metadata={"test": "value"}
        )
        
        # Verify session attributes
        self.assertIsNotNone(session.session_id)
        self.assertEqual(session.client_id, "test-client")
        self.assertEqual(session.username, "test-user")
        self.assertEqual(session.scopes, set(["test:*:*"]))
        self.assertEqual(session.metadata, {"test": "value"})
        self.assertLessEqual(session.created_at, time.time())
        self.assertEqual(session.last_active, session.created_at)

    def test_update_activity(self):
        """Test updating session activity."""
        # Create a session
        session = Session(client_id="test-client")
        initial_last_active = session.last_active
        
        # Wait a moment
        time.sleep(0.01)
        
        # Update activity
        session.update_activity()
        
        # Verify last_active was updated
        self.assertGreater(session.last_active, initial_last_active)

    def test_has_scope(self):
        """Test checking if a session has a scope."""
        # Create a session with specific scopes
        session = Session(
            client_id="test-client",
            scopes=set(["test:read:*", "test:write:data"])
        )
        
        # Test exact scope matches
        self.assertTrue(session.has_scope("test:read:*"))
        self.assertTrue(session.has_scope("test:write:data"))
        
        # Test wildcard pattern matches
        self.assertTrue(session.has_scope("test:read:specific"))
        
        # Test non-matching scopes
        self.assertFalse(session.has_scope("test:delete:*"))
        self.assertFalse(session.has_scope("other:read:*"))
        
        # Create a session with wildcard scope
        wildcard_session = Session(
            client_id="wildcard-client",
            scopes=set(["*:*:*"])
        )
        
        # Test wildcard scope matches everything
        self.assertTrue(wildcard_session.has_scope("any:scope:here"))
        self.assertTrue(wildcard_session.has_scope("test:read:*"))
        self.assertTrue(wildcard_session.has_scope("other:write:data"))


if __name__ == "__main__":
    unittest.main()
