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
def create_test_component(config_overrides=None, cache_service_instance=None):
    """
    Creates a test instance of A2AClientAgentComponent with mocked dependencies.

    Args:
        config_overrides (dict, optional): Dictionary to override default config values.
        cache_service_instance (MagicMock | None, optional): An existing MagicMock for the cache service,
                                                             or None to pass None to the component.
                                                             Defaults to creating a new MagicMock if not provided.
    """
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

    # Use the provided cache service instance, or create a default mock if None was explicitly passed
    # but the intention was likely to have one (unless None was intended for testing no-cache scenario)
    # For clarity, let's default to creating one if None is passed, unless the test explicitly needs None.
    # A better approach might be to require the caller to always provide it.
    # Let's refine: if cache_service_instance is not provided (is None), create a default mock.
    # If the test needs to pass None explicitly, it can pass cache_service_instance=None.
    effective_cache_service = cache_service_instance if cache_service_instance is not None else MagicMock()

    kwargs = {"cache_service": effective_cache_service}

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
    # Store the cache service instance used, so tests can access it if needed
    component._test_cache_service_instance = effective_cache_service
    return component
