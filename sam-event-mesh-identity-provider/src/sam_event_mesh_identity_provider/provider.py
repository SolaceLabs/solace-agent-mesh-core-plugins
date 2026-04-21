"""Generic Event Mesh Identity and Employee Service Provider."""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from solace_agent_mesh.common.services.identity_service import BaseIdentityService
from solace_agent_mesh.common.services.employee_service import BaseEmployeeService
from solace_agent_mesh.common.sac.sam_component_base import SamComponentBase

from .field_mapper import FieldMapper
from .service import EventMeshService

log = logging.getLogger(__name__)


class EventMeshIdentityProvider(BaseIdentityService, BaseEmployeeService):
    """
    Generic identity and employee service that communicates with any backend
    system via Solace Event Mesh request-response messaging.

    Implements both :class:`BaseIdentityService` and :class:`BaseEmployeeService`,
    allowing it to be used for gateway identity enrichment **and** agent employee
    queries.  All data transformation is driven by the YAML ``field_mapping_config``
    section, making this provider completely vendor-agnostic.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        component: Optional[SamComponentBase] = None,
    ):
        # BaseIdentityService.__init__ sets self.config, self.component,
        # self.log_identifier, self.cache_ttl, self.cache
        super().__init__(config, component)

        self.lookup_key: str = self.config.get("lookup_key", "email")
        self.payload_key: str = self.config.get("payload_key", self.lookup_key)
        self.field_mapper = FieldMapper(self.config.get("field_mapping_config", {}))

        try:
            self.service = EventMeshService(config, component)
            log.info(
                "%s Initialized. Lookup key: '%s'.",
                self.log_identifier,
                self.lookup_key,
            )
        except Exception as e:
            log.exception(
                "%s Failed to initialize EventMeshService: %s",
                self.log_identifier,
                e,
            )
            raise

    def __del__(self):
        try:
            service = getattr(self, "service", None)
            if service is not None:
                service.cleanup()
        except Exception:
            # __del__ must never raise; interpreter shutdown can tear down
            # dependencies before this runs.
            pass

    # ------------------------------------------------------------------
    # BaseIdentityService
    # ------------------------------------------------------------------

    async def get_user_profile(
        self, auth_claims: Any
    ) -> Optional[Dict[str, Any]]:
        """Fetch a user profile via the event mesh using an auth claim."""
        if not auth_claims or not self.lookup_key:
            log.warning(
                "%s No auth claims provided for user profile lookup.",
                self.log_identifier,
            )
            return None

        if isinstance(auth_claims, dict):
            lookup_value = auth_claims.get(self.lookup_key)
        else:
            lookup_value = getattr(auth_claims, self.lookup_key, None)

        if not lookup_value:
            log.warning(
                "%s Lookup key '%s' not found in auth_claims.",
                self.log_identifier,
                self.lookup_key,
            )
            return None

        lookup_str = str(lookup_value).lower()
        cache_key = f"user_profile_{lookup_str}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                log.debug(
                    "%s Cache hit for user profile '%s'.",
                    self.log_identifier,
                    lookup_value,
                )
                return cached

        response = await self.service.send_request(
            "user_profile", {self.payload_key: lookup_value}
        )
        if not response:
            log.warning(
                "%s No profile found for '%s'.",
                self.log_identifier,
                lookup_value,
            )
            return None

        profile = self.field_mapper.map_record(response)

        # Ensure the id field is always present.
        if profile and "id" not in profile:
            profile["id"] = lookup_str

        if self.cache and profile:
            self.cache.set(cache_key, profile, ttl=self.cache_ttl)

        return profile

    async def search_users(
        self, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for users via the event mesh."""
        if not query or len(query) < 2:
            return []

        cache_key = f"search_{query.lower()}_{limit}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        response = await self.service.send_request(
            "search_users", {"query": query, "limit": limit}
        )
        if not response:
            return []

        users = response if isinstance(response, list) else response.get("results", [])
        results = self.field_mapper.map_records(users)

        if self.cache:
            self.cache.set(cache_key, results, ttl=min(self.cache_ttl, 60))

        return results

    # ------------------------------------------------------------------
    # BaseEmployeeService
    # ------------------------------------------------------------------

    async def get_employee_dataframe(self) -> pd.DataFrame:
        """Return the entire employee directory as a DataFrame."""
        cache_key = "employee_dataframe"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        response = await self.service.send_request("employee_data", {})
        if not response:
            return pd.DataFrame()

        employees = (
            response
            if isinstance(response, list)
            else response.get("employees", [])
        )
        mapped = self.field_mapper.map_records(employees)
        df = pd.DataFrame(mapped)

        if self.cache:
            self.cache.set(cache_key, df, ttl=self.cache_ttl)

        return df

    async def get_employee_profile(
        self, employee_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single employee profile via the event mesh."""
        cache_key = f"employee_profile_{employee_id.lower()}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached

        response = await self.service.send_request(
            "employee_profile", {"employee_id": employee_id}
        )
        if not response:
            return None

        profile = self.field_mapper.map_record(response)

        if self.cache and profile:
            self.cache.set(cache_key, profile, ttl=self.cache_ttl)

        return profile

    async def get_time_off_data(
        self,
        employee_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve time-off entries for an employee via the event mesh."""
        payload: Dict[str, Any] = {"employee_id": employee_id}
        if start_date:
            payload["start_date"] = start_date
        if end_date:
            payload["end_date"] = end_date

        response = await self.service.send_request("time_off", payload)
        if not response:
            return []

        # Time-off data follows a fixed schema (start, end, type, amount)
        # so field mapping is not applied.
        return response if isinstance(response, list) else response.get("entries", [])

    async def get_employee_profile_picture(
        self, employee_id: str
    ) -> Optional[str]:
        """Fetch an employee's profile picture (data URI) via the event mesh."""
        cache_key = f"profile_picture_{employee_id.lower()}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached

        response = await self.service.send_request(
            "profile_picture", {"employee_id": employee_id}
        )
        if not response:
            return None

        picture_uri = (
            response if isinstance(response, str) else response.get("data_uri")
        )

        if self.cache and picture_uri:
            self.cache.set(cache_key, picture_uri, ttl=self.cache_ttl)

        return picture_uri
