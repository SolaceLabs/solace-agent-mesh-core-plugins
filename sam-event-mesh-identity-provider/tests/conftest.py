"""Shared test fixtures for the Event Mesh Identity Provider plugin."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from solace_agent_mesh.common.utils.in_memory_cache import InMemoryCache


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the InMemoryCache singleton before each test to prevent leakage."""
    cache = InMemoryCache()
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def mock_component():
    """A mock SAM component with broker request-response capabilities."""
    component = MagicMock()
    component.create_request_response_session = MagicMock(return_value="test-session-id")
    component.do_broker_request_response_async = AsyncMock()
    component.destroy_request_response_session = MagicMock()
    return component


@pytest.fixture
def base_config():
    """A minimal valid configuration dictionary using per-operation topics."""
    return {
        "type": "event-mesh-identity-provider",
        "broker_url": "tcp://localhost:55555",
        "broker_vpn": "default",
        "broker_username": "user",
        "broker_password": "pass",
        "dev_mode": True,
        "lookup_key": "email",
        "cache_ttl_seconds": 3600,
        "request_expiry_ms": 120000,
        "response_topic_prefix": "test/response",
        "request_topic": {
            "user_profile": "test/user-profile/{request_id}",
            "search_users": "test/search-users/{request_id}",
            "employee_data": "test/employee-data/{request_id}",
            "employee_profile": "test/employee-profile/{request_id}",
            "time_off": "test/time-off/{request_id}",
            "profile_picture": "test/profile-picture/{request_id}",
        },
        "field_mapping_config": {},
    }


@pytest.fixture
def string_topic_config():
    """Configuration using a single string request_topic for all operations."""
    return {
        "type": "event-mesh-identity-provider",
        "broker_url": "tcp://localhost:55555",
        "broker_vpn": "default",
        "broker_username": "user",
        "broker_password": "pass",
        "dev_mode": True,
        "lookup_key": "email",
        "cache_ttl_seconds": 3600,
        "request_topic": "company/identity/request/v1/{request_id}",
        "field_mapping_config": {},
    }


@pytest.fixture
def sample_source_employee():
    """A sample employee record as returned by a backend HR system."""
    return {
        "email": "jane.doe@company.com",
        "firstName": "Jane",
        "middleName": "",
        "lastName": "Doe",
        "title": "Senior Engineer",
        "department": "Engineering",
        "location": "Toronto",
        "managerId": "mgr@company.com",
        "managerName": "John Manager",
        "company": "Acme Corp",
        "costCenter": "CC100",
        "country": "Canada",
    }
