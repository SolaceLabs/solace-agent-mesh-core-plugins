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
    """A minimal valid configuration dictionary."""
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
        "operations": {
            "user_profile": {
                "request_topic": "test/user-profile/{request_id}",
            },
            "search_users": {
                "request_topic": "test/search-users/{request_id}",
            },
            "employee_data": {
                "request_topic": "test/employee-data/{request_id}",
            },
            "employee_profile": {
                "request_topic": "test/employee-profile/{request_id}",
            },
            "time_off": {
                "request_topic": "test/time-off/{request_id}",
            },
            "profile_picture": {
                "request_topic": "test/profile-picture/{request_id}",
            },
        },
        "field_mapping_config": {},
    }


@pytest.fixture
def flat_config():
    """Configuration using the legacy flat-topic format (backward compat)."""
    return {
        "type": "event-mesh-identity-provider",
        "broker_url": "tcp://localhost:55555",
        "broker_vpn": "default",
        "broker_username": "user",
        "broker_password": "pass",
        "dev_mode": True,
        "lookup_key": "email",
        "cache_ttl_seconds": 3600,
        "request_topic": "TI/AI/HRM/user/requested/v1/{request_id}",
        "response_topic": "TI/AI/HRM/user/retrieved/v1/",
        "field_mapping_config": {},
    }


@pytest.fixture
def jde_field_mapping_config():
    """JDE-specific field mapping configuration for backward compat testing."""
    return {
        "field_mapping": {
            "email": "workEmail",
            "positionTitle": "jobTitle",
        },
        "computed_fields": [
            {
                "target": "displayName",
                "source_fields": ["userFirstName", "userMiddleName", "userSurname"],
                "separator": " ",
            },
            {
                "target": "id",
                "source_fields": ["email"],
                "separator": "",
            },
        ],
        "pass_through_unmapped": True,
    }


@pytest.fixture
def sample_jde_employee():
    """A sample employee record as returned by JDE/SuccessFactor."""
    return {
        "email": "jane.doe@company.com",
        "userFirstName": "Jane",
        "userMiddleName": "",
        "userSurname": "Doe",
        "positionTitle": "Senior Engineer",
        "department": "Engineering",
        "location": "Toronto",
        "manager": "mgr@company.com",
        "managerName": "John Manager",
        "company": "Acme Corp",
        "costCenter": "CC100",
        "country": "Canada",
    }
