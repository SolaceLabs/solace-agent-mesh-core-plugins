"""Geographic location agent component for handling location-based operations."""

import copy
from typing import Dict, Any

from solace_agent_mesh.agents.base_agent_component import (
    agent_info,
    BaseAgentComponent,
)

from .actions.city_to_coordinates import CityToCoordinates
from .actions.city_to_timezone import CityToTimezone
from .actions.get_weather import GetWeather


info = copy.deepcopy(agent_info)
info.update(
    {
        "agent_name": None,  # Template variable replaced at agent creation
        "class_name": "GeoInformationAgentComponent",
        "description": None,
        "config_parameters": [
            {
                "name": "agent_name",
                "required": True,
                "description": "Name of this geographic information agent instance (used for topics, queues, etc.)",
                "type": "string",
            },
            {
                "name": "geocoding_api_key",
                "required": False,
                "description": "API key for the geocoding service (maps.co). Set via {{SNAKE_UPPER_CASE_NAME}}_GEOCODING_API_KEY env var.",
                "type": "string",
            },
            {
                "name": "weather_api_key",
                "required": False,
                "description": "API key for the weather service (open-meteo). Set via {{SNAKE_UPPER_CASE_NAME}}_WEATHER_API_KEY env var.",
                "type": "string",
            },
        ],
    }
)


class GeoInformationAgentComponent(BaseAgentComponent):
    """Component for handling geographic information operations including location, timezone, and weather."""

    info = info
    actions = [CityToCoordinates, CityToTimezone, GetWeather]

    def __init__(self, module_info: Dict[str, Any] = None, **kwargs):
        """Initialize this agent component.

        Args:
            module_info: Optional module configuration.
            **kwargs: Additional keyword arguments.
        """
        module_info = module_info or info
        super().__init__(module_info, **kwargs)

        # Get core config values
        self.agent_name = self.get_config("agent_name")
        self.geocoding_api_key = self.get_config(
            "geocoding_api_key"
        )  # Fetches default "" if env var not set
        self.weather_api_key = self.get_config(
            "weather_api_key"
        )  # Fetches default "" if env var not set

        # Update component info with specific instance details
        module_info["agent_name"] = self.agent_name
        self.info = module_info  # Ensure self.info uses the updated module_info

        # Update action scopes
        self.action_list.fix_scopes("<agent_name>", self.agent_name)

        # Note: API keys are not stored directly on self but are retrieved via get_config
        # when needed by the actions/services to avoid storing potentially sensitive info longer than necessary.
        # Actions will need to access config via self.get_config("geocoding_api_key") etc.

    def get_agent_summary(self):
        """Get a summary of the agent's capabilities."""
        # Use the updated description from self.info
        summary = {
            "agent_name": self.agent_name,
            "description": (
                "This agent provides comprehensive geographic information services including:\n"
                "- Location Services: Converting city names to precise coordinates\n"
                "- Timezone Information: Looking up timezone data, UTC offsets, and DST status\n"
                "- Weather Services: Current conditions, forecasts, and historical weather data\n\n"
                "All of these services work together to provide detailed geographic insights for any location."
            ),
            "always_open": self.info.get("always_open", False),
            "actions": self.get_actions_summary(),
        }
        return summary
