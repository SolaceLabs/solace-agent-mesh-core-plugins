# Solace Event Mesh Plugin for Solace Agent Mesh (SAM)

This plugin provides components to integrate SAM with Solace PubSub+ Event Brokers and the wider Solace Event Mesh. It includes:

- **[Event Mesh Gateway](./docs/event_mesh_gateway.md)**: Enables bidirectional communication, allowing external applications to interact with SAM agents via Solace events, and allowing SAM to publish events back to the mesh.
- **Event Mesh Agent**: An agent that dynamically creates actions based on configuration, allowing SAM to send requests to topics on the event mesh and receive synchronous or asynchronous responses.

## Add the Plugin

If you haven't already, add the plugin to your SAM instance:
```sh
solace-agent-mesh plugin add solace-event-mesh --pip -u git+https://github.com/SolaceLabs/solace-agent-mesh-core-plugins#subdirectory=solace-event-mesh
```

## Using the Event Mesh Gateway

See the [Event Mesh Gateway Documentation](./docs/event_mesh_gateway.md) for details on creating and configuring gateway instances.

## Using the Event Mesh Agent

The Event Mesh Agent allows you to define custom actions within SAM that correspond to request/reply interactions over the Solace Event Mesh.

### Instantiate the Agent

Since this agent's behavior is entirely defined by its configuration (specifically the `actions` list), it's most common to have only **one instance** of this agent.

*   **Option A: Editing `solace-agent-mesh.yaml` (Recommended):**
    Directly load the agent in your main `solace-agent-mesh.yaml`:
    ```yaml
    # solace-agent-mesh.yaml
    ...
    plugins:
      ...
      - name: solace-event-mesh
        load_unspecified_files: false
        includes_gateway_interface: true # Keep true if using the gateway
        load:
          agents:
            - solace_event_mesh # Loads configs/agents/solace_event_mesh.yaml by default
          gateways: [] # Add gateway instances here if needed
          overwrites: []
      ...
    ```
    You will then configure the agent's behavior by editing `configs/agents/solace_event_mesh.yaml`. The default agent name is `solace_event_mesh`.

*   **Option B: Using `add agent` (Less Common):**
    If you have a specific reason to create a distinct instance (e.g., separating action groups logically), use the `add agent` command. Replace `<new_agent_name>` with your chosen name.
    ```sh
    solace-agent-mesh add agent <new_agent_name> --copy-from solace-event-mesh:solace_event_mesh
    ```
    This creates `<new_agent_name>.yaml` in `configs/agents/`. You will configure the agent by editing this new file.

### Configuration (`configs/agents/solace_event_mesh.yaml`)

The core of the agent's configuration is the `actions` list within the `component_config` section. Each item in this list defines an action that the agent will expose.

```yaml
# ... other config ...
flows:
  - name: {{SNAKE_CASE_NAME}}_action_request_processor # or solace_event_mesh_action_request_processor if using Option A
    components:
      # ... broker_input ...
      - component_name: action_request_processor
        component_module: {{MODULE_DIRECTORY}}.agents.solace_event_mesh.solace_event_mesh_agent_component
        component_config:
          agent_name: {{SNAKE_CASE_NAME}} # or solace_event_mesh if using Option A
          # ... other component settings ...
          actions:
            - name: "my_request_action"              # Name exposed via SAM
              description: "Sends a request to system X" # Description for LLM/user
              parameters:                           # Parameters the action accepts
                - name: "user_id"
                  required: true
                  description: "The ID of the user"
                  type: "string"
                  payload_path: "request.userId"    # Dot notation path in outgoing JSON
                - name: "details"
                  required: false
                  description: "Optional details"
                  type: "string"
                  payload_path: "request.details"
              topic: "systemX/requests/{{text://user_id}}" # Topic to publish request to (can use param substitution)
              response_timeout: 10                  # Seconds to wait for a reply
              response_format: "json"               # Expected format of reply (json, yaml, text, none)
              # required_scope: "<agent_name>:my_request_action:write" # Optional scope override
            # --- Add more actions ---
      # ... broker_request_response, broker_output ...
```

**Key Action Fields:**

-   `name`: The name used to invoke the action via SAM.
-   `description`: Helps LLMs and users understand what the action does.
-   `parameters`: Defines the inputs the action takes.
    -   `name`, `required`, `description`, `type`: Standard parameter definitions.
    -   `payload_path`: Specifies where the parameter's value should be placed in the outgoing JSON payload using dot notation (e.g., `customer.address.city`). Array indices can be specified like `items.0.name`.
-   `topic`: The Solace topic to publish the request message to. Can include parameter substitution using `{{text://param_name}}`.
-   `response_timeout`: How long (in seconds) the agent should wait for a reply message.
-   `response_format`: How the agent should interpret the payload of the reply message (`json`, `yaml`, `text`, `none`).

### Environment Variables

Only the standard Solace connection variables are required for the agent itself:
- **SOLACE_BROKER_URL**
- **SOLACE_BROKER_USERNAME**
- **SOLACE_BROKER_PASSWORD**
- **SOLACE_BROKER_VPN**
- **SOLACE_AGENT_MESH_NAMESPACE**

Any environment variables needed by specific actions (e.g., API keys used within the receiving application) are handled outside this agent's direct configuration but might be referenced if your action parameters or topics need them indirectly.

### Actions

The actions available are dynamically created based on the `actions` list in the agent's configuration file (`configs/agents/solace_event_mesh.yaml` or the file created by `add agent`). Each configured action allows sending a structured request to a specific Solace topic and waiting for a response.
