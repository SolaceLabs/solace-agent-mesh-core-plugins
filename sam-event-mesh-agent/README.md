# SAM Event Mesh Agent Plugin

This agent plugin for Solace Agent Mesh (SAM) provides a powerful tool to send messages into a Solace event mesh and subscribe to a response. It acts as a bridge, allowing a Large Language Model (LLM) to interact with any microservice or application connected to the event mesh.

## Key Features

- **Dynamic Tool Creation**: Define custom tools in your agent's configuration file. Each tool can be tailored to a specific topic and payload structure.
- **Request-Response Interaction**: Sends a request message and waits for a response on a dynamically generated reply-to topic.
- **Structured Payloads**: Automatically construct complex JSON/YAML payloads from tool parameters using dot notation.
- **Dynamic Topics**: Use parameters to construct the request topic dynamically.
- **Synchronous & Asynchronous Modes**: Choose between blocking (synchronous) calls that wait for a response, or non-blocking (asynchronous) calls for long-running requests.

## Configuration

After installing the plugin, a configuration file will be created at `configs/agents/<your-new-component-name-kebab-case>.yaml`. You will need to customize this file to define how the agent interacts with the event mesh.

The most important section to configure is the `tools` array within the `app_config`.

### Tool Definition

Here is an example of a tool definition from the configuration file:

```yaml
# ... inside app_config ...
tools:
  - tool_type: python
    component_module: sam_event_mesh_agent.tools
    function_name: broker_request_response

    # 1. UPDATE: Give your tool a unique and descriptive name.
    tool_name: "GetWeather"
    
    # 2. UPDATE: Describe what the tool does for the LLM.
    description: |
      Gets the current weather for a specific city.
      
      This tool requires the following parameters:
      - city [string|required]: The city to get the weather for.
      - unit [string|optional]: The temperature unit (celsius or fahrenheit). Defaults to celsius.

    # 3. UPDATE: Configure the tool's behavior.
    tool_config:
      # 3a. Define the parameters the tool accepts.
      parameters:
        - name: city
          payload_path: location.city # Maps to payload: {"location": {"city": "..."}}
        - name: unit
          default: "celsius"
          payload_path: unit # Maps to payload: {"unit": "..."}
        - name: request_id # This parameter is used in the topic but not the payload
          default: "weather-req-123"

      # 3b. Define the topic for the request message.
      # Parameters can be injected using {{ param_name }}.
      topic: "acme/weather/request/{{ request_id }}"

      # 3c. (Optional) Set the response timeout in seconds.
      response_timeout: 10 # Defaults to 15 if not set

      # 3d. (Optional) Define the expected format of the response payload.
      # Can be 'json', 'yaml', 'text', or 'none'. Defaults to 'text'.
      response_format: "json"
```

### `tool_config` Details

-   `parameters`: A list of parameters your tool will accept.
    -   `name`: The parameter name used by the LLM.
    -   `default`: (Optional) A default value if the parameter is not provided.
    -   `payload_path`: (Optional) The path to map the parameter's value into the outgoing JSON payload. It supports dot notation for nested objects (e.g., `customer.address.city`). If omitted, the parameter is not included in the payload but can still be used in the topic template.
-   `topic`: The topic string for the outgoing request message. You can insert parameter values into the topic using `{{ parameter_name }}`.
-   `response_timeout`: (Optional) The number of seconds to wait for a response before timing out. The default is 15 seconds.
-   `response_format`: (Optional) The expected format of the response message payload.
    -   `json`: The tool will attempt to parse the response as JSON.
    -   `yaml`: The tool will attempt to parse the response as YAML.
    -   `text`: The tool will treat the response as a plain string (default).
    -   `none`: The tool will return the raw response payload without any parsing.

### Asynchronous Operation

For long-running backend tasks, you can make the tool operate asynchronously by including a parameter named `async` with a default value of `True`.

```yaml
parameters:
  - name: async
    default: True
  # ... other parameters
```

When called, the tool will immediately return a success message with an `async_response_id`. The actual response from the event mesh will be sent to the user session later when it arrives.

### Agent Persona

You should also update the agent's persona to match the tools you have defined.

-   `instruction`: Update the system prompt to guide the LLM on how to use the configured tools.
-   `agent_card`: Update the `description` and add entries to the `skills` list, one for each tool you've defined. This helps with agent discovery in the UI.

```yaml
# ... inside app_config ...
instruction: |
  You are a helpful assistant. You can use the GetWeather tool to
  find out the weather.

agent_card:
  description: "This agent can retrieve weather information from the event mesh."
  skills:
    - id: "get_weather"
      name: "Get Weather"
      description: "Gets the current weather for a given city."
```

## Installation

```bash
sam plugin add <your-new-component-name> --plugin sam-event-mesh-agent
```
This will create a new component configuration at `configs/agents/<your-new-component-name-kebab-case>.yaml`.