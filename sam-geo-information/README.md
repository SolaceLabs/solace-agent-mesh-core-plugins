# Solace Agent Mesh Geographic Information

A plugin that provides comprehensive geographic information services including location lookup, timezone data, and weather information.

## Features

- Convert city names to geographic coordinates
- Look up timezone information for cities
- Get current weather conditions and forecasts for locations

## Add a Geographic Location Agent to SAM

Add the plugin to your SAM instance:

```sh
solace-agent-mesh plugin add sam_geo_information --pip -u git+https://github.com/SolaceLabs/solace-agent-mesh-core-plugins#subdirectory=sam-geo-information
```

2.  **Instantiate the Agent:**
    Use the `solace-agent-mesh add agent` command to create a configuration file for your specific geographic information agent instance. Replace `<new_agent_name>` with a descriptive name (e.g., `geo_info_primary`, `weather_lookup`).
    ```sh
    solace-agent-mesh add agent <new_agent_name> --copy-from sam_geo_information:geo_information
    ```
    This command creates a new YAML file in `configs/agents/` named `<new_agent_name>.yaml`. The template variables (`{{SNAKE_CASE_NAME}}`, `{{SNAKE_UPPER_CASE_NAME}}`) inside the copied file will be automatically replaced with your chosen agent name.

## Environment Variables

The following environment variables are required for **Solace connection** (used by all agents):
- **SOLACE_BROKER_URL**
- **SOLACE_BROKER_USERNAME**
- **SOLACE_BROKER_PASSWORD**
- **SOLACE_BROKER_VPN**
- **SOLACE_AGENT_MESH_NAMESPACE**

For **each Geographic Information agent instance**, you may need to set the following environment variables, replacing `<AGENT_NAME>` with the uppercase version of the name you chose during the `add agent` step (e.g., `GEO_INFO_PRIMARY`, `WEATHER_LOOKUP`):

- **`<AGENT_NAME>_GEOCODING_API_KEY`** (Optional): API key for the geocode.maps.co service. Required for substantial volume usage.
- **`<AGENT_NAME>_WEATHER_API_KEY`** (Optional): API key for the open-meteo.com service. Required only for commercial use.

**Example Environment Variables:**

For an agent named `geo_info_primary`:
```bash
# Optional: export GEO_INFO_PRIMARY_GEOCODING_API_KEY="your_maps.co_api_key"
# Optional: export GEO_INFO_PRIMARY_WEATHER_API_KEY="your_open-meteo_api_key"
```

## Actions

### city_to_coordinates
Converts a city name to its geographic coordinates. If multiple matches are found, all possibilities will be returned.

### city_to_timezone
Converts a city name to its timezone information, including current UTC offset and DST status.

### get_weather
Gets current weather conditions and optional forecast for a location. Supports both metric and imperial units.


## GeoCode API

Currently, this agent uses geocode.maps.co as the GeoCode API. You will need to sign up for an API key at [https://geocode.maps.co/](https://geocode.maps.co/) if you want to use it with any substantial volume.

## Weather API

Currently, this agent uses Open Meteo as the weather API. You may use this for free as long as it is for non-commercial purposes. For commercial use, you will need to sign up for an API key at [https://open-meteo.com/](https://open-meteo.com/).
