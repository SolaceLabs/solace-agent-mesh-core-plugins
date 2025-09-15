# Event Mesh Tool Plugin

This plugin for Solace Agent Mesh (SAM) provides a powerful and dynamic tool for sending messages into a Solace event mesh and receiving a response. It acts as a generic bridge, allowing a Large Language Model (LLM) to interact with any microservice or application connected to the event mesh.

Unlike a standalone agent, this is a **tool** that can be added to any existing or new agent, allowing you to create multi-faceted agents that can communicate with multiple backend services.

## Key Features

- **Dynamic Tool Creation**: Define custom tools directly in your agent's YAML configuration. Each tool instance is completely independent.
- **Dedicated Sessions**: Each tool instance creates its own dedicated request-response session, allowing for fine-grained configuration and connection to different brokers if needed.
- **Request-Response Interaction**: Sends a request message and waits for a correlated response on a dynamically managed reply topic.
- **Structured Payloads**: Automatically construct complex JSON payloads from tool parameters using dot notation.
- **Dynamic Topics**: Use tool parameters to construct the request topic dynamically.
- **Synchronous & Asynchronous Modes**: Choose between blocking calls that wait for a response, or non-blocking "fire-and-forget" calls.

## Installation

To add this tool to a new or existing agent, you must manually add the tool configuration to your agent's YAML file. If installing from a separate repository, you would first run:

```bash
sam plugin add <your-agent-name> --plugin sam-event-mesh-tool
```

## Configuration

To use the tool, add one or more `tool_type: python` blocks to the `tools` list in your agent's `app_config`. Each block will create a new, independent tool instance.

### Example Tool Configuration

Here is an example of configuring a tool to get weather information.

```yaml
# In your agent's app_config:
tools:
  - tool_type: python
    component_module: "sam_event_mesh_tool.tools"
    class_name: "EventMeshTool"
    tool_config:
      # --- Connection & Session Configuration ---
      # This block configures the dedicated event mesh session for this tool.
      event_mesh_config:
        broker_config: *broker_connection # Anchor to shared broker settings
        request_expiry_ms: 10000          # Timeout for requests in milliseconds
        payload_format: "json"            # Format of the outgoing request payload

      # --- Tool Definition for LLM ---
      tool_name: "GetWeather"
      description: "Gets the current weather for a specific city."
      
      # --- Tool Parameters ---
      parameters:
        - name: "city"
          type: "string"
          required: true
          description: "The city to get the weather for."
          payload_path: "location.city" # Maps to payload: {"location": {"city": "..."}}
        - name: "unit"
          type: "string"
          required: false
          default: "celsius"
          payload_path: "unit" # Maps to payload: {"unit": "..."}
        - name: "request_id" # Used in topic, but not in payload
          type: "string"
          required: true
          description: "A unique identifier for this request."
      
      # --- Per-Request Configuration ---
      topic: "acme/weather/request/{{ request_id }}"
      wait_for_response: true
      response_format: "json" # How to parse the incoming response payload
```

### `tool_config` Details

-   `event_mesh_config`: Configures the dedicated session for this tool.
    -   This dictionary is passed directly to the `create_request_response_session` function.
    -   It should contain a `broker_config` block and can include other session settings like `request_expiry_ms`, `response_topic_prefix`, etc.
    -   For a full list of options, refer to the "Broker Request-Response Guide" in the Solace AI Connector documentation.
-   `tool_name`: The function name the LLM will use to call the tool.
-   `description`: A clear description for the LLM explaining what the tool does.
-   `parameters`: A list of parameters the tool accepts.
    -   `name`: The parameter name.
    -   `type`: The data type. Must be one of `string`, `integer`, `number`, or `boolean`.
    -   `required`: `true` or `false`.
    -   `description`: (Optional) A description of the parameter for the LLM.
    -   `default`: (Optional) A default value if the parameter is not provided.
    -   `payload_path`: (Optional) The path to map the parameter's value into the outgoing JSON payload. It supports dot notation for nested objects (e.g., `customer.address.city`). If omitted, the parameter is not included in the payload but can still be used in the topic template.
-   `topic`: The topic string for the outgoing request message. You can insert parameter values into the topic using `{{ parameter_name }}`.
-   `wait_for_response`: (Optional) `true` (default) for synchronous requests that wait for a reply. Set to `false` for asynchronous "fire-and-forget" requests.
-   `response_format`: (Optional) The expected format of the response message payload.
    -   `json`: The tool will parse the response as JSON.
    -   `yaml`: The tool will parse the response as YAML.
    -   `text`: The tool will treat the response as a plain string (default).
    -   `none`: The tool will return the raw response payload without any parsing.

### Advanced Usage: Multiple Tools

You can configure multiple tools in the same agent, each with its own session and configuration. This is useful for interacting with different backend systems from a single agent.

```yaml
# In your agent's app_config:
tools:
  # --- Tool 1: Get Weather ---
  - tool_type: python
    component_module: "sam_event_mesh_tool.tools"
    class_name: "EventMeshTool"
    tool_config:
      event_mesh_config:
        broker_config: *weather_broker_connection
      tool_name: "GetWeather"
      # ... rest of weather tool config ...

  # --- Tool 2: Update CRM ---
  - tool_type: python
    component_module: "sam_event_mesh_tool.tools"
    class_name: "EventMeshTool"
    tool_config:
      event_mesh_config:
        broker_config: *crm_broker_connection # Potentially a different broker
      tool_name: "UpdateCrmRecord"
      description: "Updates a customer record in the CRM."
      wait_for_response: false # Fire-and-forget
      # ... rest of CRM tool config ...
```
