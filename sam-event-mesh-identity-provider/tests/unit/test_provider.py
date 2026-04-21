"""Unit tests for the EventMeshIdentityProvider class."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd

from sam_event_mesh_identity_provider.provider import EventMeshIdentityProvider


# All operation names used by the provider.
ALL_OPS = {"user_profile", "search_users", "employee_data", "employee_profile", "time_off", "profile_picture"}


def _make_mock_service(configured_ops=None):
    """Create a mock EventMeshService with configurable operation availability."""
    if configured_ops is None:
        configured_ops = ALL_OPS
    service = MagicMock()
    service.send_request = AsyncMock(return_value=None)
    service.cleanup = MagicMock()
    service.is_operation_configured = MagicMock(side_effect=lambda op: op in configured_ops)
    return service


@pytest.fixture
def mock_service():
    """A mock EventMeshService with all operations configured."""
    return _make_mock_service(ALL_OPS)


@pytest.fixture
def provider(base_config, mock_component, mock_service):
    """An EventMeshIdentityProvider with mocked service layer (all ops)."""
    with patch(
        "sam_event_mesh_identity_provider.provider.EventMeshService",
        return_value=mock_service,
    ):
        p = EventMeshIdentityProvider(base_config, mock_component)
    return p


@pytest.fixture
def partial_provider(partial_config, mock_component):
    """Provider with only user_profile configured."""
    svc = _make_mock_service({"user_profile"})
    with patch(
        "sam_event_mesh_identity_provider.provider.EventMeshService",
        return_value=svc,
    ):
        p = EventMeshIdentityProvider(partial_config, mock_component)
    return p


class TestProviderInit:
    """Tests for provider initialization."""

    def test_init_success(self, base_config, mock_component):
        """Provider initializes correctly with valid config."""
        with patch("sam_event_mesh_identity_provider.provider.EventMeshService"):
            p = EventMeshIdentityProvider(base_config, mock_component)
        assert p.lookup_key == "email"
        assert p.field_mapper is not None

    def test_init_service_failure_propagates(self, base_config, mock_component):
        """If EventMeshService raises, provider re-raises."""
        with patch(
            "sam_event_mesh_identity_provider.provider.EventMeshService",
            side_effect=RuntimeError("Connection failed"),
        ):
            with pytest.raises(RuntimeError, match="Connection failed"):
                EventMeshIdentityProvider(base_config, mock_component)

    def test_del_calls_cleanup(self, provider, mock_service):
        """__del__ calls service.cleanup()."""
        provider.__del__()
        mock_service.cleanup.assert_called_once()


class TestGetUserProfile:
    """Tests for get_user_profile."""

    @pytest.mark.asyncio
    async def test_success(self, provider, mock_service):
        """Returns mapped profile on successful fetch."""
        mock_service.send_request.return_value = {
            "id": "jane@co.com",
            "displayName": "Jane Doe",
            "workEmail": "jane@co.com",
        }
        result = await provider.get_user_profile({"email": "jane@co.com"})
        assert result["displayName"] == "Jane Doe"
        mock_service.send_request.assert_called_once_with(
            "user_profile", {"email": "jane@co.com"}
        )

    @pytest.mark.asyncio
    async def test_cache_hit(self, provider, mock_service):
        """Second call returns cached result without calling service."""
        mock_service.send_request.return_value = {"id": "j@co.com", "name": "J"}
        await provider.get_user_profile({"email": "j@co.com"})
        await provider.get_user_profile({"email": "j@co.com"})
        assert mock_service.send_request.call_count == 1

    @pytest.mark.asyncio
    async def test_no_claims(self, provider):
        """Returns None when auth_claims is empty."""
        assert await provider.get_user_profile({}) is None
        assert await provider.get_user_profile(None) is None

    @pytest.mark.asyncio
    async def test_missing_lookup_key(self, provider):
        """Returns None when lookup_key not in auth_claims."""
        result = await provider.get_user_profile({"username": "jane"})
        assert result is None

    @pytest.mark.asyncio
    async def test_attribute_access(self, provider, mock_service):
        """Handles auth_claims with attribute access (not just dict)."""
        mock_service.send_request.return_value = {"id": "j@co.com"}

        class Claims:
            email = "j@co.com"

        result = await provider.get_user_profile(Claims())
        assert result is not None

    @pytest.mark.asyncio
    async def test_service_returns_none(self, provider, mock_service):
        """Returns None when backend returns nothing."""
        mock_service.send_request.return_value = None
        result = await provider.get_user_profile({"email": "missing@co.com"})
        assert result is None

    @pytest.mark.asyncio
    async def test_ensures_id_field(self, provider, mock_service):
        """When response has no id field, lookup value is used."""
        mock_service.send_request.return_value = {"displayName": "Jane"}
        result = await provider.get_user_profile({"email": "Jane@CO.com"})
        assert result["id"] == "jane@co.com"


class TestSearchUsers:
    """Tests for search_users."""

    @pytest.mark.asyncio
    async def test_success_list_response(self, provider, mock_service):
        """Returns mapped list when backend returns a list."""
        mock_service.send_request.return_value = [
            {"id": "1", "displayName": "Alice"},
            {"id": "2", "displayName": "Bob"},
        ]
        results = await provider.search_users("ali", limit=5)
        assert len(results) == 2
        assert results[0]["displayName"] == "Alice"

    @pytest.mark.asyncio
    async def test_success_dict_response(self, provider, mock_service):
        """Returns mapped list when backend returns a dict with 'results' key."""
        mock_service.send_request.return_value = {
            "results": [{"id": "1", "displayName": "Alice"}]
        }
        results = await provider.search_users("ali")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_short_query(self, provider, mock_service):
        """Returns empty list for queries shorter than 2 characters."""
        assert await provider.search_users("a") == []
        assert await provider.search_users("") == []
        mock_service.send_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit(self, provider, mock_service):
        """Second identical search returns cached results."""
        mock_service.send_request.return_value = [{"id": "1"}]
        await provider.search_users("alice", limit=10)
        await provider.search_users("alice", limit=10)
        assert mock_service.send_request.call_count == 1

    @pytest.mark.asyncio
    async def test_no_results(self, provider, mock_service):
        """Returns empty list when backend returns None."""
        mock_service.send_request.return_value = None
        assert await provider.search_users("nobody") == []


class TestGetEmployeeDataframe:
    """Tests for get_employee_dataframe."""

    @pytest.mark.asyncio
    async def test_success_list_response(self, provider, mock_service):
        """Returns DataFrame with mapped columns."""
        mock_service.send_request.return_value = [
            {"id": "1", "displayName": "Alice", "department": "Eng"},
            {"id": "2", "displayName": "Bob", "department": "Sales"},
        ]
        df = await provider.get_employee_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "displayName" in df.columns

    @pytest.mark.asyncio
    async def test_success_dict_response(self, provider, mock_service):
        """Returns DataFrame when backend returns dict with 'employees' key."""
        mock_service.send_request.return_value = {
            "employees": [{"id": "1", "displayName": "Alice"}]
        }
        df = await provider.get_employee_dataframe()
        assert len(df) == 1

    @pytest.mark.asyncio
    async def test_empty_response(self, provider, mock_service):
        """Returns empty DataFrame on no data."""
        mock_service.send_request.return_value = None
        df = await provider.get_employee_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert df.empty


class TestGetEmployeeProfile:
    """Tests for get_employee_profile."""

    @pytest.mark.asyncio
    async def test_success(self, provider, mock_service):
        """Returns mapped profile dict."""
        mock_service.send_request.return_value = {
            "id": "emp1",
            "displayName": "Alice",
            "department": "Eng",
        }
        result = await provider.get_employee_profile("emp1")
        assert result["displayName"] == "Alice"
        mock_service.send_request.assert_called_with(
            "employee_profile", {"employee_id": "emp1"}
        )

    @pytest.mark.asyncio
    async def test_not_found(self, provider, mock_service):
        """Returns None when employee not found."""
        mock_service.send_request.return_value = None
        assert await provider.get_employee_profile("missing") is None

    @pytest.mark.asyncio
    async def test_cache_hit(self, provider, mock_service):
        """Second call returns cached result."""
        mock_service.send_request.return_value = {"id": "emp1", "name": "A"}
        await provider.get_employee_profile("emp1")
        await provider.get_employee_profile("emp1")
        assert mock_service.send_request.call_count == 1


class TestGetTimeOffData:
    """Tests for get_time_off_data."""

    @pytest.mark.asyncio
    async def test_success_list_response(self, provider, mock_service):
        """Returns list of time-off entries."""
        mock_service.send_request.return_value = [
            {"start": "2025-07-04", "end": "2025-07-04", "type": "Holiday", "amount": "full_day"},
        ]
        result = await provider.get_time_off_data("emp1")
        assert len(result) == 1
        assert result[0]["type"] == "Holiday"

    @pytest.mark.asyncio
    async def test_success_dict_response(self, provider, mock_service):
        """Returns entries when backend returns dict with 'entries' key."""
        mock_service.send_request.return_value = {
            "entries": [
                {"start": "2025-08-01", "end": "2025-08-05", "type": "Vacation", "amount": "full_day"}
            ]
        }
        result = await provider.get_time_off_data("emp1")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_with_date_range(self, provider, mock_service):
        """start_date and end_date are passed in the request payload."""
        mock_service.send_request.return_value = []
        await provider.get_time_off_data("emp1", start_date="2025-01-01", end_date="2025-12-31")
        mock_service.send_request.assert_called_with(
            "time_off",
            {"employee_id": "emp1", "start_date": "2025-01-01", "end_date": "2025-12-31"},
        )

    @pytest.mark.asyncio
    async def test_no_data(self, provider, mock_service):
        """Returns empty list when no data available."""
        mock_service.send_request.return_value = None
        assert await provider.get_time_off_data("emp1") == []


class TestGetEmployeeProfilePicture:
    """Tests for get_employee_profile_picture."""

    @pytest.mark.asyncio
    async def test_success_string_response(self, provider, mock_service):
        """Returns data URI when backend returns a string directly."""
        mock_service.send_request.return_value = "data:image/jpeg;base64,abc123"
        result = await provider.get_employee_profile_picture("emp1")
        assert result == "data:image/jpeg;base64,abc123"

    @pytest.mark.asyncio
    async def test_success_dict_response(self, provider, mock_service):
        """Returns data URI from dict response with data_uri key."""
        mock_service.send_request.return_value = {"data_uri": "data:image/png;base64,xyz"}
        result = await provider.get_employee_profile_picture("emp1")
        assert result == "data:image/png;base64,xyz"

    @pytest.mark.asyncio
    async def test_not_found(self, provider, mock_service):
        """Returns None when no picture available."""
        mock_service.send_request.return_value = None
        assert await provider.get_employee_profile_picture("emp1") is None

    @pytest.mark.asyncio
    async def test_cache_hit(self, provider, mock_service):
        """Second call returns cached result."""
        mock_service.send_request.return_value = "data:image/jpeg;base64,abc"
        await provider.get_employee_profile_picture("emp1")
        await provider.get_employee_profile_picture("emp1")
        assert mock_service.send_request.call_count == 1


class TestUnconfiguredOperations:
    """Tests that unconfigured operations return None/empty with warnings."""

    @pytest.mark.asyncio
    async def test_unconfigured_user_profile(self, partial_provider):
        """user_profile IS configured in partial_provider, so it works."""
        partial_provider.service.send_request.return_value = {"id": "j@co.com"}
        result = await partial_provider.get_user_profile({"email": "j@co.com"})
        assert result is not None

    @pytest.mark.asyncio
    async def test_unconfigured_search_users(self, partial_provider):
        """search_users not configured — returns empty list."""
        result = await partial_provider.search_users("alice")
        assert result == []
        partial_provider.service.send_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_unconfigured_employee_dataframe(self, partial_provider):
        """employee_data not configured — returns empty DataFrame."""
        df = await partial_provider.get_employee_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert df.empty
        partial_provider.service.send_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_unconfigured_employee_profile(self, partial_provider):
        """employee_profile not configured — returns None."""
        result = await partial_provider.get_employee_profile("emp1")
        assert result is None
        partial_provider.service.send_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_unconfigured_time_off(self, partial_provider):
        """time_off not configured — returns empty list."""
        result = await partial_provider.get_time_off_data("emp1")
        assert result == []
        partial_provider.service.send_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_unconfigured_profile_picture(self, partial_provider):
        """profile_picture not configured — returns None."""
        result = await partial_provider.get_employee_profile_picture("emp1")
        assert result is None
        partial_provider.service.send_request.assert_not_called()
