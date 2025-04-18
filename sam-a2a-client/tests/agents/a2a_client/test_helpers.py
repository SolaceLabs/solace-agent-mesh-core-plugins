import unittest
from unittest.mock import patch, MagicMock
import threading
from typing import Any

# Adjust the import path based on how tests are run (e.g., from root)
from src.agents.a2a_client.a2a_client_agent_component import A2AClientAgentComponent, info as component_info

# Mock A2A types if not directly importable
from ...common-a2a.client import A2AClient, A2ACardResolver
from ...common-a2a.types import AgentCard, Authentication, AuthenticationScheme, AgentSkill # Added AgentSkill here


# Helper to create a component instance with mocked dependencies
def create_test_component(config_overrides=None, cache_service_instance=None):
    """
    Creates a test instance of A2AClientAgentComponent with mocked dependencies.

    Args:
        config_overrides (dict, optional): Dictionary to override default config values.
        cache_service_instance (MagicMock | None, optional): An existing MagicMock for the cache service,
                                                             or None to explicitly pass None to the component.
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

    # Pass the provided cache service instance directly.
    # If None was passed to the helper, None will be passed to the component.
    kwargs = {"cache_service": cache_service_instance}

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
    # Store the cache service instance that was actually passed, so tests can access it if needed
    component._test_cache_service_instance = cache_service_instance
    return component
