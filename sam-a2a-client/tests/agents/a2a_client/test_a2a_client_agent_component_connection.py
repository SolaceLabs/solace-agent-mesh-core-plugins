import unittest
from unittest.mock import patch, MagicMock, ANY
import threading

# Adjust import paths as necessary
from src.agents.a2a_client.a2a_connection_handler import A2AConnectionHandler
from src.common_a2a.client import A2AClient, A2ACardResolver
from src.common_a2a.types import AgentCard, AgentAuthentication, AgentCapabilities
from solace_ai_connector.common.log import log # Import the log object

class TestA2AClientAgentComponentConnection(unittest.TestCase):

    def setUp(self):
        self.server_url = "http://fake-a2a-server:1234"
        self.stop_event = threading.Event()
        self.mock_agent_card = MagicMock(spec=AgentCard)
        self.mock_agent_card.name = "FakeAgent"
        self.mock_agent_card.authentication = None # Default: no auth required
        self.mock_agent_card.capabilities = AgentCapabilities() # Default capabilities

    # Patch where the classes are *used* (in a2a_connection_handler)
    @patch('src.agents.a2a_client.a2a_connection_handler.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_connection_handler.A2AClient')
    def test_initialize_client_success_no_auth(self, MockA2AClient, MockA2ACardResolver):
        """Test successful client initialization when no auth is required."""
        # Configure mocks
        mock_resolver_instance = MockA2ACardResolver.return_value
        mock_resolver_instance.get_agent_card.return_value = self.mock_agent_card
        mock_client_instance = MockA2AClient.return_value

        # Instantiate handler
        handler = A2AConnectionHandler(self.server_url, None, self.stop_event)

        # Call the method
        handler.initialize_client()

        # Assertions
        MockA2ACardResolver.assert_called_once_with(self.server_url)
        mock_resolver_instance.get_agent_card.assert_called_once()
        MockA2AClient.assert_called_once_with(agent_card=self.mock_agent_card, auth_token=None)
        self.assertEqual(handler.agent_card, self.mock_agent_card)
        self.assertEqual(handler.a2a_client, mock_client_instance)

    @patch('src.agents.a2a_client.a2a_connection_handler.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_connection_handler.A2AClient')
    def test_initialize_client_success_bearer_required_token_provided(self, MockA2AClient, MockA2ACardResolver):
        """Test successful init with bearer auth required and token provided."""
        bearer_token = "my-secret-token"
        # Mock card requiring bearer auth
        self.mock_agent_card.authentication = AgentAuthentication(schemes=["bearer"])

        mock_resolver_instance = MockA2ACardResolver.return_value
        mock_resolver_instance.get_agent_card.return_value = self.mock_agent_card
        mock_client_instance = MockA2AClient.return_value

        handler = A2AConnectionHandler(self.server_url, bearer_token, self.stop_event)
        handler.initialize_client()

        MockA2ACardResolver.assert_called_once_with(self.server_url)
        mock_resolver_instance.get_agent_card.assert_called_once()
        # Verify A2AClient was called WITH the token
        MockA2AClient.assert_called_once_with(agent_card=self.mock_agent_card, auth_token=bearer_token)
        self.assertEqual(handler.agent_card, self.mock_agent_card)
        self.assertEqual(handler.a2a_client, mock_client_instance)

    @patch('src.agents.a2a_client.a2a_connection_handler.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_connection_handler.A2AClient')
    @patch('solace_ai_connector.common.log.log.warning') # Patch the correct log object
    def test_initialize_client_bearer_required_token_missing(self, mock_log_warning, MockA2AClient, MockA2ACardResolver):
        """Test init logs warning and proceeds without token if bearer required but token missing."""
        # Mock card requiring bearer auth
        self.mock_agent_card.authentication = AgentAuthentication(schemes=["bearer"])

        mock_resolver_instance = MockA2ACardResolver.return_value
        mock_resolver_instance.get_agent_card.return_value = self.mock_agent_card
        mock_client_instance = MockA2AClient.return_value

        handler = A2AConnectionHandler(self.server_url, None, self.stop_event) # No token provided
        handler.initialize_client()

        MockA2ACardResolver.assert_called_once_with(self.server_url)
        mock_resolver_instance.get_agent_card.assert_called_once()
        # Verify A2AClient was called WITHOUT the token
        MockA2AClient.assert_called_once_with(agent_card=self.mock_agent_card, auth_token=None)
        self.assertEqual(handler.agent_card, self.mock_agent_card)
        self.assertEqual(handler.a2a_client, mock_client_instance)
        # Verify warning was logged
        mock_log_warning.assert_called_once()
        self.assertIn("requires Bearer token, but none configured", mock_log_warning.call_args[0][0])

    @patch('src.agents.a2a_client.a2a_connection_handler.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_connection_handler.A2AClient')
    @patch('solace_ai_connector.common.log.log.info') # Patch the correct log object
    def test_initialize_client_bearer_not_required_token_provided(self, mock_log_info, MockA2AClient, MockA2ACardResolver):
        """Test init logs info and proceeds without token if token provided but not required."""
        bearer_token = "my-secret-token"
        # Mock card NOT requiring bearer auth (or no auth section)
        self.mock_agent_card.authentication = None

        mock_resolver_instance = MockA2ACardResolver.return_value
        mock_resolver_instance.get_agent_card.return_value = self.mock_agent_card
        mock_client_instance = MockA2AClient.return_value

        handler = A2AConnectionHandler(self.server_url, bearer_token, self.stop_event) # Token provided
        handler.initialize_client()

        MockA2ACardResolver.assert_called_once_with(self.server_url)
        mock_resolver_instance.get_agent_card.assert_called_once()
        # Verify A2AClient was called WITHOUT the token
        MockA2AClient.assert_called_once_with(agent_card=self.mock_agent_card, auth_token=None)
        self.assertEqual(handler.agent_card, self.mock_agent_card)
        self.assertEqual(handler.a2a_client, mock_client_instance)
        # Verify info was logged
        mock_log_info.assert_called() # Called multiple times, check specific call
        self.assertTrue(any("token is configured but not explicitly required" in call_args[0]
                            for call_args, call_kwargs in mock_log_info.call_args_list))


    @patch('src.agents.a2a_client.a2a_connection_handler.A2ACardResolver')
    def test_initialize_client_card_fetch_fails(self, MockA2ACardResolver):
        """Test initialize_client raises ValueError if card fetching fails."""
        # Configure mock resolver to raise an error
        mock_resolver_instance = MockA2ACardResolver.return_value
        fetch_error = ConnectionError("Failed to connect to agent card endpoint")
        mock_resolver_instance.get_agent_card.side_effect = fetch_error

        handler = A2AConnectionHandler(self.server_url, None, self.stop_event)

        # Assert ValueError is raised and check the cause
        with self.assertRaises(ValueError) as cm:
            handler.initialize_client()

        self.assertIn("Failed to get Agent Card", str(cm.exception))
        self.assertEqual(cm.exception.__cause__, fetch_error)
        self.assertIsNone(handler.agent_card)
        self.assertIsNone(handler.a2a_client)

    @patch('src.agents.a2a_client.a2a_connection_handler.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_connection_handler.A2AClient')
    def test_initialize_client_client_init_fails(self, MockA2AClient, MockA2ACardResolver):
        """Test initialize_client raises ValueError if A2AClient instantiation fails."""
        # Configure mocks
        mock_resolver_instance = MockA2ACardResolver.return_value
        mock_resolver_instance.get_agent_card.return_value = self.mock_agent_card
        # Configure mock client constructor to raise an error
        init_error = TypeError("Invalid argument for A2AClient")
        MockA2AClient.side_effect = init_error

        handler = A2AConnectionHandler(self.server_url, None, self.stop_event)

        # Assert ValueError is raised and check the cause
        with self.assertRaises(ValueError) as cm:
            handler.initialize_client()

        self.assertIn("Could not initialize A2AClient", str(cm.exception))
        self.assertEqual(cm.exception.__cause__, init_error)
        self.assertEqual(handler.agent_card, self.mock_agent_card) # Card was fetched
        self.assertIsNone(handler.a2a_client) # Client init failed

if __name__ == '__main__':
    unittest.main()
