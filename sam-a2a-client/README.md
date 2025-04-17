# Solace Agent Mesh - A2A Client Plugin

This plugin allows Solace Agent Mesh (SAM) to act as a client to external agents that implement the Google Agent-to-Agent (A2A) protocol.

## Overview

The `sam-a2a-client` plugin provides a SAM agent component (`A2AClientAgentComponent`) that can connect to an A2A-compliant agent. It discovers the target agent's capabilities (skills) via its `AgentCard` and dynamically exposes these skills as standard SAM actions. This enables SAM workflows to seamlessly incorporate the functionality of external A2A agents.

The plugin can either connect to a pre-existing A2A agent running at a specified URL or launch and manage the A2A agent process itself based on a configured command.

## Features

*   Connects to any A2A protocol compliant agent.
*   Optionally manages the lifecycle of the A2A agent process (start, monitor, restart).
*   Discovers A2A agent skills via the `AgentCard`.
*   Dynamically creates SAM actions corresponding to discovered A2A skills.
*   Translates SAM action parameters to A2A `Task` requests (including text and file parts).
*   Translates A2A `Task` responses (including text, files, data, artifacts) back to SAM `ActionResponse`.
*   Handles the A2A `INPUT_REQUIRED` state for multi-turn interactions.
*   Supports bearer token authentication.

## Installation

*(Instructions assume you have solace-agent-mesh CLI installed)*

1.  Add the plugin to your SAM project:
    ```bash
    # Replace <plugin_source> with the correct pip install target
    # e.g., git+https://github.com/SolaceLabs/solace-agent-mesh-core-plugins.git#subdirectory=sam-a2a-client
    solace-agent-mesh plugin add sam-a2a-client --pip -u <plugin_source>
    ```

2.  Instantiate an agent using the plugin:
    ```bash
    # Replace <your_agent_name> with a descriptive name (e.g., crewai_image_gen)
    solace-agent-mesh add agent <your_agent_name> --copy-from sam-a2a-client:a2a_client
    ```
    This creates a configuration file in `configs/agents/<your_agent_name>.yaml`.

## Configuration

Configure the agent instance by editing `configs/agents/<your_agent_name>.yaml` and setting the required environment variables.

**Key Configuration Parameters (in `<your_agent_name>.yaml`):**

*   `agent_name`: (String, Required) Must match `<your_agent_name>`.
*   `a2a_server_url`: (String, Required) The base URL of the target A2A agent (e.g., `http://localhost:10001`).
*   `a2a_server_command`: (String, Optional) Command to launch the A2A agent process. If omitted, connects to a pre-existing agent at `a2a_server_url`.
*   `a2a_server_startup_timeout`: (Integer, Optional, Default: 30) Seconds to wait for a launched agent to become ready.
*   `a2a_server_restart_on_crash`: (Boolean, Optional, Default: True) Attempt to restart the managed process if it crashes.
*   `a2a_bearer_token`: (String, Optional) Bearer token for A2A requests.
*   `input_required_ttl`: (Integer, Optional, Default: 300) TTL for pending `INPUT_REQUIRED` state.

**Environment Variables:**

Set these according to your deployment:

*   `SOLACE_BROKER_URL`, `SOLACE_BROKER_USERNAME`, `SOLACE_BROKER_PASSWORD`, `SOLACE_BROKER_VPN`, `SOLACE_AGENT_MESH_NAMESPACE` (Standard SAM variables)
*   `<YOUR_AGENT_NAME_UPPER>_A2A_SERVER_URL`: URL of the A2A agent.
*   `<YOUR_AGENT_NAME_UPPER>_A2A_SERVER_COMMAND`: (Optional) Command to launch the agent.
*   `<YOUR_AGENT_NAME_UPPER>_A2A_BEARER_TOKEN`: (Optional) Bearer token.
*   *(Other config parameters can also be sourced from environment variables)*

**Example (`crewai_image_gen.yaml` snippet):**

```yaml
# ... inside components: - component_config:
          agent_name: crewai_image_gen
          a2a_server_url: ${CREWAI_IMAGE_GEN_A2A_SERVER_URL}
          # a2a_server_command: ${CREWAI_IMAGE_GEN_A2A_SERVER_COMMAND} # Optional
          # a2a_bearer_token: ${CREWAI_IMAGE_GEN_A2A_BEARER_TOKEN} # Optional
# ...
```

## Usage

Once configured and SAM is running, the orchestrator can invoke actions on the `<your_agent_name>` agent. The available actions will correspond to the skills discovered from the target A2A agent's `AgentCard`. Action names will typically be in the format `<your_agent_name>/<skill_id>`.

If an action results in the A2A agent requiring more input, the `ActionResponse` will contain `status: 'INPUT_REQUIRED'`, a message with the agent's question, and a `follow_up_id` in the `data` field. To provide the required input, invoke the special action `<your_agent_name>/provide_required_input` with parameters `follow_up_id` and `user_response`.

## Development

*(Placeholder for development setup instructions)*

## License

Apache License 2.0
