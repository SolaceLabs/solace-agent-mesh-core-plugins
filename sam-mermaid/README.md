# Solace Agent Mesh MERMAID

A plugin used to generate visualizations using Mermaid.js

## Add a Mermaid Agent to SAM

1.  **Add the Plugin:**
    If you haven't already, add the plugin to your SAM instance:
    ```sh
    solace-agent-mesh plugin add sam_mermaid --pip -u git+https://github.com/SolaceLabs/solace-agent-mesh-core-plugins#subdirectory=sam-mermaid
    ```

2.  **Instantiate the Agent:**
    You have two options:

    *   **Option A: Using `add agent` (Recommended for multiple instances):**
        Use the `solace-agent-mesh add agent` command. Replace `<new_agent_name>` with a descriptive name (e.g., `mermaid_primary`, `diagram_generator`).
        ```sh
        solace-agent-mesh add agent <new_agent_name> --copy-from sam_mermaid:mermaid
        ```
        This creates `<new_agent_name>.yaml` in `configs/agents/` with template variables automatically replaced.

    *   **Option B: Editing `solace-agent-mesh.yaml` (For a single instance):**
        If you only need one Mermaid agent, you can directly load it in your main `solace-agent-mesh.yaml`:
        ```yaml
        # solace-agent-mesh.yaml
        ...
        plugins:
          ...
          - name: sam_mermaid
            load_unspecified_files: false
            includes_gateway_interface: false
            load:
              agents:
                - mermaid # Loads configs/agents/mermaid.yaml by default
              gateways: []
              overwrites: []
          ...
        ```
        **Note:** If using this method, you'll need to manually edit `configs/agents/mermaid.yaml` if you want to change the default agent name (`mermaid`) or other settings not controlled by environment variables. The environment variable name will use `MERMAID` as the prefix (see below).

## Environment Variables

The following environment variables are required for **Solace connection** (used by all agents):
- **SOLACE_BROKER_URL**
- **SOLACE_BROKER_USERNAME**
- **SOLACE_BROKER_PASSWORD**
- **SOLACE_BROKER_VPN**
- **SOLACE_AGENT_MESH_NAMESPACE**

For **each Mermaid agent instance**, you need to set the following environment variable, replacing `<AGENT_NAME>` with the uppercase version of the name you chose during the `add agent` step (e.g., `MERMAID_PRIMARY`, `DIAGRAM_GENERATOR`). If you used Option B above, use `MERMAID`.

- **`<AGENT_NAME>_MERMAID_SERVER_URL`** (Required): The full URL of your running [mermaid-server](https://github.com/TomWright/mermaid-server) instance (e.g., `http://localhost:8080`).

**Example Environment Variables:**

For an agent named `mermaid_primary` (created via `add agent`):
```bash
export MERMAID_PRIMARY_MERMAID_SERVER_URL="http://mermaid.internal.example.com"
```

For the default agent loaded via `solace-agent-mesh.yaml`:
```bash
export MERMAID_MERMAID_SERVER_URL="http://127.0.0.1:9000"
```

## Actions

### draw
Generates a diagram (currently PNG format) from the provided Mermaid.js syntax string by sending it to the configured `mermaid-server`.

Parameters:
- **mermaid_code** (required): The Mermaid.js syntax string to render.
