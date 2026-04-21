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
    """A minimal valid configuration dictionary with all operations."""
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
                "response_topic": "test/user-profile/response/",
            },
            "search_users": {
                "request_topic": "test/search-users/{request_id}",
                "response_topic": "test/search-users/response/",
            },
            "employee_data": {
                "request_topic": "test/employee-data/{request_id}",
                "response_topic": "test/employee-data/response/",
            },
            "employee_profile": {
                "request_topic": "test/employee-profile/{request_id}",
                "response_topic": "test/employee-profile/response/",
            },
            "time_off": {
                "request_topic": "test/time-off/{request_id}",
                "response_topic": "test/time-off/response/",
            },
            "profile_picture": {
                "request_topic": "test/profile-picture/{request_id}",
                "response_topic": "test/profile-picture/response/",
            },
        },
        "field_mapping_config": {},
    }


@pytest.fixture
def partial_config():
    """Configuration with only user_profile operation configured."""
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
                "response_topic": "test/user-profile/response/",
            },
        },
        "field_mapping_config": {},
    }


@pytest.fixture
def hr_field_mapping_config():
    """Field mapping config for a typical HR system with non-canonical field names."""
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
def sample_hr_employee():
    """A sample employee record from an HR system with non-canonical field names."""
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
