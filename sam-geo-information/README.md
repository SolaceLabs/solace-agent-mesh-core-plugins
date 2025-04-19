# Solace Agent Mesh Geographic Information

A plugin that provides comprehensive geographic information services including location lookup, timezone data, and weather information.

---

## Features

- Convert city names to geographic coordinates
- Look up timezone information for cities
- Get current weather conditions and forecasts for locations

---

## Prerequisites

Before starting, make sure you have:

- [Installed Solace Agent Mesh and the SAM CLI](https://solacelabs.github.io/solace-agent-mesh/docs/documentation/getting-started/installation/)
- [Created a new Solace Agent Mesh project](https://solacelabs.github.io/solace-agent-mesh/docs/documentation/getting-started/quick-start)

---

## 🚀 Quick Start

### ✅ Recommended: Add and create the agent via CLI

#### 1. Add the plugin

```bash
sam plugin add sam_geo_information --pip -u git+https://github.com/SolaceLabs/solace-agent-mesh-core-plugins#subdirectory=sam-geo-information
```

#### 2. Create the agent

This creates a new agent named `geo_information`:

```bash
sam add agent geo_information --copy-from sam_geo_information
```

You can now run Solace Agent Mesh and try it out! 🎉

```bash
sam run -b
```

Here are two example prompts you can try with your agent:

- *What are the coordinates of Ottawa?*
- *What’s the current weather and forecast in Tokyo?*

---

### Alternative: Edit your `solace-agent-mesh.yaml` config manually

You can add the following to your `solace-agent-mesh.yaml` file:

```yaml
plugins:
  - name: sam_geo_information
    load_unspecified_files: false
    includes_gateway_interface: false
    load:
      agents: 
        - geo_information  # Add this line
      gateways: []
      overwrites: []
    from_url: 
      git+https://github.com/SolaceLabs/solace-agent-mesh-core-plugins#subdirectory=sam-geo-information
```

---

## Available Actions

### `city_to_coordinates`
Converts a city name to its geographic coordinates. If multiple matches are found, all possibilities will be returned.

### `city_to_timezone`
Converts a city name to its timezone information, including current UTC offset and DST status.

### `get_weather`
Gets current weather conditions and optional forecast for a location. Supports both metric and imperial units.

---

## APIs Used

### GeoCode API
Uses [geocode.maps.co](https://geocode.maps.co/)  
Sign up for an API key for higher request volume.

### Weather API
Uses [Open Meteo](https://open-meteo.com/)  
Free for non-commercial use. For commercial use, get an API key.

---

## Want to go further?

To unlock more functionality or customize your agent, go to the generated config file in your agent configs directory (typically: `configs/agents/geo_information.yaml`) and update:

```yaml
agent_name: geo_information
geocoding_api_key: ${GEOCODING_API_KEY}
weather_api_key: ${WEATHER_API_KEY}
```

You can:
- Rename the agent by changing `agent_name`
- Add your API keys here, or supply them as environment variables

---
