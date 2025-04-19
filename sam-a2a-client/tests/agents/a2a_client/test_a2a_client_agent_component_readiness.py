import unittest
from unittest.mock import patch, MagicMock
import threading
import time
import requests

# Adjust the import path based on how tests are run (e.g., from root)
from .test_helpers import create_test_component # Import helper
from solace_ai_connector.common.log import log # Import the log object

class TestA2AClientAgentComponentReadiness(unittest.TestCase):

    @patch('src.agents.a2a_client.a2a_connection_handler.requests.get') # Patch where requests is used
    @patch.object(threading.Event, 'wait', return_value=False) # Simulate wait timeout
    def test_wait_for_agent_ready_success_immediate(self, mock_event_wait, mock_requests_get):
        """Test wait_for_ready succeeds on the first try."""
        timeout = 5
        component = create_test_component({"a2a_server_startup_timeout": timeout})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests_get.return_value = mock_response

        # Instantiate the handler and call the method
        from src.agents.a2a_client.a2a_connection_handler import A2AConnectionHandler
        handler = A2AConnectionHandler(
            component.a2a_server_url, None, component.stop_monitor # Pass None for token
        )
        result = handler.wait_for_ready(timeout) # Pass timeout here

        self.assertTrue(result)
        mock_requests_get.assert_called_once_with(
            "http://localhost:10001/.well-known/agent.json",
            timeout=5
        )
        mock_event_wait.assert_not_called() # Should succeed before waiting

    @patch('src.agents.a2a_client.a2a_connection_handler.requests.get') # Patch where requests is used
    @patch.object(threading.Event, 'wait', return_value=False)
    def test_wait_for_agent_ready_success_retry(self, mock_event_wait, mock_requests_get):
        """Test wait_for_agent_ready succeeds after a few retries."""
        timeout = 5
        component = create_test_component({"a2a_server_startup_timeout": timeout})
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 503
        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_requests_get.side_effect = [mock_response_fail, mock_response_fail, mock_response_success]

        # Instantiate the handler and call the method
        from src.agents.a2a_client.a2a_connection_handler import A2AConnectionHandler
        handler = A2AConnectionHandler(
            component.a2a_server_url, None, component.stop_monitor # Pass None for token
        )
        result = handler.wait_for_ready(timeout) # Pass timeout here

        self.assertTrue(result)
        self.assertEqual(mock_requests_get.call_count, 3)
        self.assertEqual(mock_event_wait.call_count, 2) # Wait called twice before success
        mock_event_wait.assert_called_with(timeout=1) # Check last wait timeout

    @patch('src.agents.a2a_client.a2a_connection_handler.requests.get') # Patch where requests is used
    @patch.object(threading.Event, 'wait', return_value=False)
    @patch('src.agents.a2a_client.a2a_connection_handler.time.time') # Mock time where it's used
    def test_wait_for_agent_ready_timeout(self, mock_time, mock_event_wait, mock_requests_get):
        """Test wait_for_agent_ready returns False on timeout."""
        timeout = 3 # seconds for test
        component = create_test_component({"a2a_server_startup_timeout": timeout})
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 503
        mock_requests_get.return_value = mock_response_fail

        # Simulate time passing to exceed timeout
        start_time = 1000.0
        # Time sequence: start, check1, wait1, check2, wait2, check3, wait3 (timeout), logger call
        mock_time.side_effect = [
            start_time,       # Initial deadline calculation
            start_time + 0.1, # First check
            start_time + 1.2, # Second check
            start_time + 2.3, # Third check
            start_time + 3.4, # Final check (exceeds deadline)
            start_time + 3.5  # Extra call for logger.error
        ]

        # Instantiate the handler and call the method
        from src.agents.a2a_client.a2a_connection_handler import A2AConnectionHandler
        handler = A2AConnectionHandler(
            component.a2a_server_url, None, component.stop_monitor # Pass None for token
        )
        result = handler.wait_for_ready(timeout) # Pass timeout here

        self.assertFalse(result)
        self.assertEqual(mock_requests_get.call_count, 3) # Should try 3 times
        self.assertEqual(mock_event_wait.call_count, 3) # Wait after each failed attempt

    @patch('src.agents.a2a_client.a2a_connection_handler.requests.get', side_effect=requests.exceptions.ConnectionError("Connection failed")) # Patch where requests is used
    @patch.object(threading.Event, 'wait', return_value=False)
    @patch('src.agents.a2a_client.a2a_connection_handler.time.time') # Mock time where it's used
    def test_wait_for_agent_ready_connection_error(self, mock_time, mock_event_wait, mock_requests_get):
        """Test _wait_for_agent_ready handles ConnectionError and times out."""
        timeout = 2
        component = create_test_component({"a2a_server_startup_timeout": timeout})
        start_time = 1000.0
        # Time sequence: start, check1, wait1, check2 (timeout), logger call
        mock_time.side_effect = [
            start_time,       # Initial deadline calculation
            start_time + 0.1, # First check
            start_time + 1.2, # Second check
            start_time + 2.3, # Final check (exceeds deadline)
            start_time + 2.4  # Extra call for logger.error
        ]

        # Instantiate the handler and call the method
        from src.agents.a2a_client.a2a_connection_handler import A2AConnectionHandler
        handler = A2AConnectionHandler(
            component.a2a_server_url, None, component.stop_monitor # Pass None for token
        )
        result = handler.wait_for_ready(timeout) # Pass timeout here

        self.assertFalse(result)
        self.assertEqual(mock_requests_get.call_count, 2) # Tries twice before timeout
        self.assertEqual(mock_event_wait.call_count, 2) # Wait after each failed attempt

    @patch('src.agents.a2a_client.a2a_connection_handler.requests.get') # Patch where requests is used
    @patch.object(threading.Event, 'wait', return_value=True) # Simulate stop event set during wait
    def test_wait_for_agent_ready_stop_event(self, mock_event_wait, mock_requests_get):
        """Test _wait_for_agent_ready returns False immediately if stop event is set during wait."""
        timeout = 10
        component = create_test_component({"a2a_server_startup_timeout": timeout})
        # Simulate request failing once before wait detects stop
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 503
        mock_requests_get.return_value = mock_response_fail

        # Instantiate the handler and call the method
        from src.agents.a2a_client.a2a_connection_handler import A2AConnectionHandler
        handler = A2AConnectionHandler(
            component.a2a_server_url, None, component.stop_monitor # Pass None for token
        )
        result = handler.wait_for_ready(timeout) # Pass timeout here

        self.assertFalse(result)
        mock_requests_get.assert_called_once() # Request IS called once before wait detects stop
        mock_event_wait.assert_called_once_with(timeout=1) # wait is called after the first failed request

if __name__ == '__main__':
    unittest.main()
