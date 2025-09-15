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

To add this tool to a new or existing agent, you must first install it and then manually add the tool configuration to your agent's YAML file:

```bash
sam plugin install sam-event-mesh-tool
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
```

### `tool_config` Details

-   `event_mesh_config`: Configures the dedicated session for this tool. This dictionary is passed directly to the `create_request_response_session` function. Key options include:
    -   `broker_config`: (Required) A block containing the connection details for the broker (`broker_url`, `broker_username`, `broker_password`, `broker_vpn`).
    -   `request_expiry_ms`: (Optional) Timeout in milliseconds for a request to receive a response. Defaults to `60000`.
    -   `payload_format`: (Optional) The format for the payload (e.g., `json`, `yaml`, `text`). This controls both the encoding of the outgoing request and the decoding of the incoming response. Defaults to `json`.
    -   `payload_encoding`: (Optional) The encoding for the payload (e.g., `utf-8`, `base64`). Defaults to `utf-8`.
    -   `response_topic_prefix`: (Optional) A custom prefix for the dynamically generated reply topics. Defaults to `reply`.
    -   `response_topic_suffix`: (Optional) A custom suffix for the dynamically generated reply topics. Defaults to `""`.
    -   `response_queue_prefix`: (Optional) A custom prefix for the dynamically generated reply queues. Defaults to `reply-queue`.
    -   `response_topic_insertion_expression`: (Optional) An expression to insert the reply topic directly into the request message's payload (e.g., `input.payload:reply_to`).
    -   `user_properties_reply_topic_key`: (Optional) The key used to store the reply topic in the request message's user properties.
    -   `user_properties_reply_metadata_key`: (Optional) The key used to store the reply metadata in the request message's user properties.
    -   For a full list of all available options, refer to the "Broker Request-Response Guide" in the Solace AI Connector documentation.
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
