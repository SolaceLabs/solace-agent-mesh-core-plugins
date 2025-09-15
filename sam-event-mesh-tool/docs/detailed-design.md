# Detailed Design: Event Mesh Tool Plugin

## 1. Introduction

This document outlines the detailed design for the `sam-event-mesh-tool` plugin. This plugin provides a generic, configurable tool for Solace Agent Mesh agents to interact with a Solace event mesh via request-response messaging. It is designed to be highly reusable, allowing a single agent to communicate with multiple backend services on the mesh, each with its own dedicated connection and configuration.

## 2. Plugin File Structure

The new plugin will be structured as a standard SAM plugin:

```
sam-event-mesh-tool/
├── config.yaml
├── pyproject.toml
├── README.md
├── docs/
│   ├── detailed-design.md
│   └── feature-proposal.md
└── src/
    └── sam_event_mesh_tool/
        ├── __init__.py
        └── tools.py
```

-   `config.yaml`: A template configuration file for users.
-   `pyproject.toml`: Project metadata and dependency definitions.
-   `README.md`: User-facing documentation.
-   `docs/`: Internal design and proposal documents.
-   `src/sam_event_mesh_tool/tools.py`: Contains the core `EventMeshTool` class implementation.

## 3. Core Component: `EventMeshTool`

The plugin's core logic will be encapsulated in a single `EventMeshTool` class within `tools.py`. This class will inherit from `solace_agent_mesh.agent.tools.dynamic_tool.DynamicTool`.

The framework will create a separate instance of this class for each `tool_type: python` block defined in the agent's YAML configuration.

### 3.1. Class Attributes and Methods

-   `__init__(self, tool_config: Dict)`:
    -   The constructor receives the `tool_config` dictionary from the agent's YAML.
    -   It stores this configuration in `self.tool_config` for later use by other methods.
    -   It initializes `self.session_id = None`.

-   `async init(self, component: "SamAgentComponent", tool_config_model: "AnyToolConfig")`:
    -   This lifecycle hook is called by the framework on agent startup for each tool instance.
    -   It extracts the `event_mesh_config` dictionary from `self.tool_config`.
    -   It calls `component.create_request_response_session(session_config=event_mesh_config)` to establish a dedicated session.
    -   It stores the returned session identifier in `self.session_id`.

-   `async cleanup(self, component: "SamAgentComponent", tool_config_model: "AnyToolConfig")`:
    -   This lifecycle hook is called on agent shutdown.
    -   It calls `component.destroy_request_response_session(self.session_id)` to gracefully terminate the session and clean up all associated broker resources.

-   `tool_name` (property):
    -   Returns `self.tool_config.get("tool_name")`.

-   `tool_description` (property):
    -   Returns `self.tool_config.get("description")`.

-   `parameters_schema` (property):
    -   Programmatically generates an `adk_types.Schema` object for the LLM.
    -   It iterates through the `parameters` list in `self.tool_config`.
    -   For each parameter, it creates an `adk_types.Schema` property, mapping the `name`, `type`, `description`, and `required` fields from the YAML.

-   `async _run_async_impl(self, args: dict, tool_context: ToolContext, ...)`:
    -   This method contains the core runtime logic when the tool is called by the LLM.
    -   It builds the outgoing message payload by mapping the `args` provided by the LLM to the `payload_path` specified for each parameter in the configuration.
    -   It constructs the destination topic by substituting placeholders in the `topic` template with values from `args`.
    -   It calls `await component.do_broker_request_response_async(...)`, passing the constructed message and `session_id=self.session_id`. The `wait_for_response` argument will be sourced from the tool's YAML config.
    -   If waiting for a response, it parses the received payload according to the `response_format` from the config (`json`, `yaml`, `text`, or `none`).
    -   It returns a dictionary containing the status and the processed response payload.

## 4. Configuration (`config.yaml`)

The `config.yaml` file will serve as a template demonstrating how to configure the tool.

**Prerequisite:** The host agent's configuration must enable multi-session request-response:

```yaml
# In the agent's app_config or component_config
multi_session_request_response:
  enabled: true
```

**Example Tool Configuration:**

```yaml
# In the agent's app_config:
tools:
  - tool_type: python
    component_module: "sam_event_mesh_tool.tools"
    class_name: "EventMeshTool"
    tool_config:
      # --- Connection & Session Configuration ---
      # This block configures the dedicated event mesh session for this tool.
      event_mesh_config:
        broker_config: *broker_connection # Anchor to shared broker settings
        request_expiry_ms: 15000
        payload_format: "json" # Format of the outgoing request payload
        # ... any other valid session_config key ...

      # --- Tool Definition for LLM ---
      tool_name: "GetWeather"
      description: "Gets the current weather for a specific city."
      
      # --- Tool Parameters ---
      parameters:
        - name: "city"
          type: "string"
          required: true
          description: "The city to get the weather for."
          payload_path: "location.city"
        - name: "unit"
          type: "string"
          required: false
          default: "celsius"
          payload_path: "unit"
      
      # --- Per-Request Configuration ---
      topic: "acme/weather/request/{{ request_id }}"
      wait_for_response: true
      response_format: "json" # How to parse the incoming response payload
```

## 5. Project Definition (`pyproject.toml`)

The `pyproject.toml` will define the plugin for packaging and installation by `sam-cli`.

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sam-event-mesh-tool"
version = "0.1.0"
description = "A dynamic tool for sending requests into the Solace event mesh."
authors = [
    { name = "SolaceLabs", email = "solacelabs@solace.com" }
]
dependencies = [
    "solace-agent-mesh>=0.1.0",
    "solace-ai-connector>=0.1.0"
]

[project.entry-points."sam.plugins"]
sam-event-mesh-tool = "sam_event_mesh_tool"
```

## 6. User Documentation (`README.md`)

The `README.md` will be the primary user-facing documentation. It will contain:

-   **Overview:** A clear explanation of what the tool does and its key features (dynamic configuration, dedicated sessions, sync/async modes).
-   **Prerequisites:** A prominent section explaining that the host agent must have `multi_session_request_response` enabled.
-   **Installation:** The `sam plugin add` command.
-   **Configuration:**
    -   A simple, well-annotated example of a single tool configuration.
    -   A detailed breakdown of each key in the `tool_config`:
        -   `event_mesh_config`: What it's for and a link to the `solace-ai-connector` documentation for all possible options.
        -   `tool_name`, `description`: How they are used by the LLM.
        -   `parameters`: How to define parameters with `name`, `type`, `required`, `description`, `default`, and `payload_path`.
        -   `topic`: How to define the topic and use `{{...}}` for templating.
        -   `wait_for_response`: How to enable asynchronous mode.
        -   `response_format`: The available options and their behavior.
-   **Advanced Usage:** An example showing two tool instances configured in the same agent.

## 7. Implementation Plan

1.  **Create Plugin Scaffolding**:
    -   Create the directory structure for `sam-event-mesh-tool`.
    -   Create the initial files: `pyproject.toml`, `README.md`, `config.yaml`, `src/sam_event_mesh_tool/__init__.py`, and `src/sam_event_mesh_tool/tools.py`.

2.  **Define Project Metadata**:
    -   Populate `sam-event-mesh-tool/pyproject.toml` with the project name, version, dependencies (`solace-agent-mesh`, `solace-ai-connector`), and the `sam.plugins` entry point.

3.  **Implement the `EventMeshTool` Class**:
    -   In `src/sam_event_mesh_tool/tools.py`, create the `EventMeshTool` class inheriting from `DynamicTool`.
    -   Adapt helper functions `_build_payload` and `_fill_topic_template` from the legacy `sam-event-mesh-agent/src/sam_event_mesh_agent/tools.py` file. These can be private functions within the `tools.py` module.
    -   Implement the `__init__` method to store the `tool_config` and initialize `self.session_id`.
    -   Implement the `init` lifecycle method to call `component.create_request_response_session` using the `event_mesh_config` from the tool's configuration and store the returned `session_id`.
    -   Implement the `cleanup` lifecycle method to call `component.destroy_request_response_session` with the stored `session_id`.
    -   Implement the `tool_name` and `tool_description` properties to read from `self.tool_config`.
    -   Implement the `parameters_schema` property. This method will parse the `parameters` list from the config and build a valid `adk_types.Schema` object, correctly mapping types (string, integer, boolean, number) and the `required` flag.
    -   Implement the `_run_async_impl` method. This is the core logic that will be executed when the tool is called. It will:
        -   Merge default parameter values with arguments provided by the LLM.
        -   Use the adapted helper functions to build the payload and construct the topic.
        -   Create a `solace_ai_connector.common.message.Message` object.
        -   Call `await component.do_broker_request_response_async(...)`, passing the message, `session_id`, and the `wait_for_response` flag.
        -   If a response is expected, parse it based on `response_format` and return a structured dictionary.

4.  **Create User-Facing Documentation and Configuration**:
    -   Populate `sam-event-mesh-tool/README.md` with a comprehensive guide covering the tool's purpose, prerequisites (`multi_session_request_response`), installation, and a detailed configuration example. This will be adapted from the legacy agent's README.
    -   Populate `sam-event-mesh-tool/config.yaml` with a well-commented example configuration that users can adapt.

5.  **Deprecate and Remove the Legacy `sam-event-mesh-agent`**:
    -   Update `sam-event-mesh-agent/README.md` to clearly state that the plugin is deprecated and direct users to the new `sam-event-mesh-tool`.
    -   Remove the core implementation from `sam-event-mesh-agent/src/sam_event_mesh_agent/tools.py` and `sam-event-mesh-agent/config.yaml`.
    -   Finally, remove the entire `sam-event-mesh-agent` directory from the repository.
