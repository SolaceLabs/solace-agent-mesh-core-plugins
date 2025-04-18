import unittest
from unittest.mock import patch, MagicMock
import threading
from typing import Any

# Adjust the import path based on how tests are run (e.g., from root)
from src.agents.a2a_client.a2a_client_agent_component import A2AClientAgentComponent, info as component_info

# Mock A2A types if not directly importable
try:
    from common.client import A2AClient, A2ACardResolver
    from common.types import AgentCard, Authentication, AuthenticationScheme
except ImportError:
    A2AClient = MagicMock()
    A2ACardResolver = MagicMock()
    AgentCard = MagicMock()
    Authentication = MagicMock()
    AuthenticationScheme = MagicMock()
    AuthenticationScheme.BEARER = "bearer" # Define mock value


# Helper to create a component instance with mocked dependencies
def create_test_component(config_overrides=None, mock_cache=True):
    """Creates a test instance of A2AClientAgentComponent with mocked dependencies."""
    base_config = {
        "agent_name": "test_a2a_agent",
        "a2a_server_url": "http://localhost:10001",
        "a2a_server_command": None, # Default to no command
        "a2a_server_startup_timeout": 10, # Use a shorter timeout for tests unless overridden
        "a2a_server_restart_on_crash": True,
        "a2a_bearer_token": None,
        "input_required_ttl": 300,
        "registration_interval": 60
    }
    if config_overrides:
        base_config.update(config_overrides)

    kwargs = {"cache_service": MagicMock() if mock_cache else None}

    # Mock self.get_config to return values from mock_config
    def mock_get_config(key, default=None):
        return base_config.get(key, default)

    # Patch BaseAgentComponent.__init__ and FileService during instantiation
    with patch('src.agents.a2a_client.a2a_client_agent_component.BaseAgentComponent.__init__'), \
         patch('src.agents.a2a_client.a2a_client_agent_component.FileService'):
        # Patch get_config specifically for the duration of the __init__ call
        with patch.object(A2AClientAgentComponent, 'get_config', side_effect=mock_get_config):
            component = A2AClientAgentComponent(module_info=component_info, **kwargs)

    # Re-apply the mock get_config to the instance for use within test methods
    component.get_config = MagicMock(side_effect=mock_get_config)
    return component
