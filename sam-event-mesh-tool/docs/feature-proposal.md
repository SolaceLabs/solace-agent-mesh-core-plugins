# Feature Proposal: Event Mesh Tool Plugin

## 1. Goals

The primary goal of this initiative is to refactor the existing `sam-event-mesh-agent` from a standalone agent into a generic, reusable **tool plugin**. This will significantly enhance the modularity and flexibility of the Solace Agent Mesh ecosystem.

The key objectives are:
- **Decouple Functionality from Agent:** Abstract the logic for sending and receiving messages on the event mesh into a tool that can be added to *any* agent, rather than requiring a dedicated agent for this purpose.
- **Promote Reusability:** Create a single, well-defined tool plugin that can be configured for various use cases, reducing code duplication and simplifying agent development.
- **Enable Multi-Faceted Agents:** Allow a single agent to be configured with multiple, independent event mesh tools, each interacting with different topics, services, or even different brokers.
- **Improve Configuration Experience:** Provide a clear, intuitive, and powerful configuration experience for defining how an agent tool interacts with the event mesh.

## 2. Requirements

To achieve these goals, the new tool plugin must meet the following requirements:

### Functional Requirements
- The tool must be implemented as a `DynamicTool`, allowing its name, description, and parameters to be defined entirely within the agent's YAML configuration.
- It must be possible to configure multiple instances of the tool within a single agent, with each instance operating independently.
- Each tool instance must manage its own dedicated request-response session with the event mesh, leveraging the `solace-ai-connector`'s multi-session request-response capability.
- The tool must support both synchronous (blocking, wait-for-response) and asynchronous (non-blocking, fire-and-forget) communication patterns.
- The tool must gracefully manage the lifecycle of its event mesh session, establishing a connection on agent startup and terminating it on shutdown.

### Configuration Requirements
- The tool's connection and session parameters (broker URL, VPN, timeouts, etc.) must be fully configurable from the agent's YAML file.
- The tool's parameter schema (name, type, requirement, description) must be definable in the YAML to allow for robust, programmatic generation of the tool definition for the LLM.
- The outgoing request topic must support dynamic population from tool parameters.
- The structure of the outgoing request payload must be definable from tool parameters, including support for nested JSON objects.
- The expected format of the incoming response payload (`json`, `yaml`, `text`, `none`) must be configurable.

## 3. Key Decisions

The following key architectural and design decisions have been made:

- **Plugin Name:** The new plugin will be named `sam-event-mesh-tool`.
- **Implementation Strategy:** The plugin will be implemented as a single `DynamicTool` class. Users will create multiple tool instances by adding multiple `tool_type: python` blocks to their agent's YAML configuration, each pointing to the same class. A `DynamicToolProvider` is not necessary and would add unneeded complexity.
- **Configuration Structure:**
    - All configuration for a tool instance will be nested under the `tool_config` key.
    - Connection and session-related settings will be grouped under a user-friendly key named `event_mesh_config`. This key will directly map to the `session_config` parameter of the underlying `create_request_response_session` API call.
- **Parameter Definition:** Tool parameters in the YAML will be defined with `name`, `type` (e.g., "string", "boolean"), `required` (true/false), `description`, and an optional `default` value. This provides sufficient information to generate a valid ADK schema.
- **Asynchronous Mode:** The choice between synchronous and asynchronous behavior will be controlled by a `wait_for_response: <boolean>` flag in the tool's YAML configuration, defaulting to `true`. This is a cleaner approach than relying on a runtime parameter.
- **Prerequisites:** Any agent using this tool must have `multi_session_request_response: { enabled: true }` configured at the component level. This will be a documented requirement.
