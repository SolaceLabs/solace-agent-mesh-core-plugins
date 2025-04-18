import unittest
from unittest.mock import patch, MagicMock, _is_instance_mock, call # Import _is_instance_mock and call
import threading

# Adjust the import path based on how tests are run (e.g., from root)
from .test_helpers import create_test_component, A2AClient, A2ACardResolver, AgentCard, Authentication, AuthenticationScheme # Import helper and mocked types

class TestA2AClientAgentComponentConnection(unittest.TestCase):

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._launch_a2a_process')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClient')
    @patch('src.agents.a2a_client.a2a_client_agent_component.threading.Thread')
    def test_initialize_connection_launch_mode_success(self, mock_thread_cls, mock_a2a_client_cls, mock_resolver_cls, mock_wait_ready, mock_launch):
        """Test successful initialization in launch mode."""
        # Provide a mock cache service to prevent init warning
        mock_cache = MagicMock()
        component = create_test_component(
            config_overrides={
                "a2a_server_command": "run_agent",
                "a2a_server_restart_on_crash": True
            },
            cache_service_instance=mock_cache
        )
        # Conditionally use spec based on whether AgentCard is a mock
        if _is_instance_mock(AgentCard):
            mock_card = MagicMock()
        else:
            mock_card = MagicMock(spec=AgentCard)
        mock_card.name = "Launched Agent"
        mock_card.authentication = None # No auth
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.return_value = mock_card
        mock_client_instance = mock_a2a_client_cls.return_value

        component._initialize_a2a_connection()

        mock_launch.assert_called_once()
        mock_wait_ready.assert_called_once()
        mock_resolver_cls.assert_called_once_with(component.a2a_server_url)
        mock_resolver_instance.get_agent_card.assert_called_once()
        mock_a2a_client_cls.assert_called_once_with(agent_card=mock_card, auth_token=None)
        mock_thread_cls.assert_called_once_with(target=component._monitor_a2a_process, daemon=True)
        mock_thread_cls.return_value.start.assert_called_once() # Check monitor thread started

        self.assertEqual(component.agent_card, mock_card)
        self.assertEqual(component.a2a_client, mock_client_instance)
        self.assertIsNotNone(component.monitor_thread)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._launch_a2a_process')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClient')
    @patch('src.agents.a2a_client.a2a_client_agent_component.threading.Thread')
    def test_initialize_connection_connect_mode_success(self, mock_thread_cls, mock_a2a_client_cls, mock_resolver_cls, mock_wait_ready, mock_launch):
        """Test successful initialization in connect mode."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(
            config_overrides={"a2a_server_command": None}, # No command
            cache_service_instance=mock_cache
        )
        # Conditionally use spec
        if _is_instance_mock(AgentCard):
            mock_card = MagicMock()
        else:
            mock_card = MagicMock(spec=AgentCard)
        mock_card.name = "Existing Agent"
        mock_card.authentication = None
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.return_value = mock_card
        mock_client_instance = mock_a2a_client_cls.return_value

        component._initialize_a2a_connection()

        mock_launch.assert_not_called()
        mock_wait_ready.assert_called_once() # Still checks readiness
        mock_resolver_cls.assert_called_once_with(component.a2a_server_url)
        mock_resolver_instance.get_agent_card.assert_called_once()
        mock_a2a_client_cls.assert_called_once_with(agent_card=mock_card, auth_token=None)
        mock_thread_cls.assert_not_called() # No monitor thread in connect mode

        self.assertEqual(component.agent_card, mock_card)
        self.assertEqual(component.a2a_client, mock_client_instance)
        self.assertIsNone(component.monitor_thread)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._launch_a2a_process', side_effect=FileNotFoundError("cmd not found"))
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent.stop_component') # Mock stop to prevent side effects
    def test_initialize_connection_launch_fail(self, mock_stop, mock_launch):
        """Test initialization fails if process launch fails."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(
            config_overrides={"a2a_server_command": "bad_cmd"},
            cache_service_instance=mock_cache
        )

        with self.assertRaises(FileNotFoundError):
            component._initialize_a2a_connection()

        mock_launch.assert_called_once()
        mock_stop.assert_called_once() # Ensure cleanup is called
        self.assertIsNone(component.agent_card)
        self.assertIsNone(component.a2a_client)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._launch_a2a_process')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=False) # Simulate timeout
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent.stop_component')
    def test_initialize_connection_readiness_timeout(self, mock_stop, mock_wait_ready, mock_launch):
        """Test initialization fails if agent readiness check times out."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(
            config_overrides={"a2a_server_command": "run_agent"},
            cache_service_instance=mock_cache
        )

        with self.assertRaises(TimeoutError):
            component._initialize_a2a_connection()

        mock_launch.assert_called_once()
        mock_wait_ready.assert_called_once()
        mock_stop.assert_called_once()
        self.assertIsNone(component.agent_card)
        self.assertIsNone(component.a2a_client)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent.stop_component')
    def test_initialize_connection_card_fetch_fail(self, mock_stop, mock_resolver_cls, mock_wait_ready):
        """Test initialization fails if Agent Card fetch fails."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache) # Connect mode
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.side_effect = ValueError("Fetch failed")

        with self.assertRaises(ValueError) as cm:
            component._initialize_a2a_connection()

        self.assertIn("Failed to get Agent Card", str(cm.exception))
        mock_wait_ready.assert_called_once()
        mock_resolver_instance.get_agent_card.assert_called_once()
        mock_stop.assert_called_once()
        self.assertIsNone(component.agent_card)
        self.assertIsNone(component.a2a_client)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClient', side_effect=Exception("Client init error")) # Mock A2AClient constructor failure
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent.stop_component')
    def test_initialize_connection_client_init_fail(self, mock_stop, mock_a2a_client_cls, mock_resolver_cls, mock_wait_ready):
        """Test initialization fails if A2AClient initialization fails."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache)
        # Conditionally use spec
        if _is_instance_mock(AgentCard):
            mock_card = MagicMock()
        else:
            mock_card = MagicMock(spec=AgentCard)
        mock_card.authentication = None
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.return_value = mock_card

        with self.assertRaises(ValueError) as cm:
            component._initialize_a2a_connection()

        self.assertIn("Could not initialize A2AClient", str(cm.exception))
        mock_wait_ready.assert_called_once()
        mock_resolver_instance.get_agent_card.assert_called_once()
        mock_a2a_client_cls.assert_called_once() # Constructor was called
        mock_stop.assert_called_once()
        self.assertEqual(component.agent_card, mock_card) # Card was fetched
        self.assertIsNone(component.a2a_client) # But client init failed

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClient')
    def test_initialize_connection_bearer_auth_success(self, mock_a2a_client_cls, mock_resolver_cls, mock_wait_ready):
        """Test initialization with bearer token required and provided."""
        token = "my-secret-token"
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(
            config_overrides={"a2a_bearer_token": token},
            cache_service_instance=mock_cache
        )
        # Conditionally use spec
        if _is_instance_mock(AgentCard):
            mock_card = MagicMock()
        else:
            mock_card = MagicMock(spec=AgentCard)
        mock_card.name = "Auth Agent"
        # Simulate AgentCard requiring bearer token
        # Conditionally use spec
        if _is_instance_mock(Authentication):
            mock_auth = MagicMock()
        else:
            mock_auth = MagicMock(spec=Authentication)
        mock_auth.schemes = [AuthenticationScheme.BEARER]
        mock_card.authentication = mock_auth
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.return_value = mock_card

        component._initialize_a2a_connection()

        mock_wait_ready.assert_called_once()
        mock_resolver_instance.get_agent_card.assert_called_once()
        # Verify A2AClient was called with the token
        mock_a2a_client_cls.assert_called_once_with(agent_card=mock_card, auth_token=token)
        self.assertIsNotNone(component.a2a_client)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClient')
    @patch('logging.Logger.warning')
    def test_initialize_connection_bearer_auth_missing(self, mock_log_warning, mock_a2a_client_cls, mock_resolver_cls, mock_wait_ready):
        """Test initialization logs warning if bearer token required but not provided."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(
            config_overrides={"a2a_bearer_token": None}, # No token configured
            cache_service_instance=mock_cache
        )
        # Conditionally use spec
        if _is_instance_mock(AgentCard):
            mock_card = MagicMock()
        else:
            mock_card = MagicMock(spec=AgentCard)
        mock_card.name = "Auth Agent Missing Token"
        # Simulate AgentCard requiring bearer token
        # Conditionally use spec
        if _is_instance_mock(Authentication):
            mock_auth = MagicMock()
        else:
            mock_auth = MagicMock(spec=Authentication)
        mock_auth.schemes = [AuthenticationScheme.BEARER]
        mock_card.authentication = mock_auth
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.return_value = mock_card

        component._initialize_a2a_connection()

        mock_wait_ready.assert_called_once()
        mock_resolver_instance.get_agent_card.assert_called_once()
        # Verify warning was logged for the bearer token
        mock_log_warning.assert_called_with(
            "A2A Agent Card requires Bearer token, but none configured ('a2a_bearer_token'). Proceeding without authentication."
        )
        # Verify A2AClient was still called, but without the token
        mock_a2a_client_cls.assert_called_once_with(agent_card=mock_card, auth_token=None)
        self.assertIsNotNone(component.a2a_client)

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAgentComponent._wait_for_agent_ready', return_value=True)
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2ACardResolver')
    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClient')
    @patch('logging.Logger.warning')
    def test_initialize_connection_bearer_auth_not_required(self, mock_log_warning, mock_a2a_client_cls, mock_resolver_cls, mock_wait_ready):
        """Test initialization proceeds normally if bearer token not required."""
        token = "my-secret-token"
        # Token is configured but card doesn't require it
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(
            config_overrides={"a2a_bearer_token": token},
            cache_service_instance=mock_cache
        )
        # Conditionally use spec
        if _is_instance_mock(AgentCard):
            mock_card = MagicMock()
        else:
            mock_card = MagicMock(spec=AgentCard)
        mock_card.name = "No Auth Agent"
        mock_card.authentication = None # No auth required
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.get_agent_card.return_value = mock_card

        component._initialize_a2a_connection()

        mock_wait_ready.assert_called_once()
        mock_resolver_instance.get_agent_card.assert_called_once()
        mock_log_warning.assert_not_called() # No warning about missing token
        # Verify A2AClient was called without the token (as it wasn't required)
        mock_a2a_client_cls.assert_called_once_with(agent_card=mock_card, auth_token=None)
        self.assertIsNotNone(component.a2a_client)

if __name__ == '__main__':
    unittest.main()
