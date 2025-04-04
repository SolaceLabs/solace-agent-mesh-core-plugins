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

    *   **Option A: Editing `solace-agent-mesh.yaml` (Recommended for a single instance):**
        If you only need one Mermaid agent (which is common), you can directly load it in your main `solace-agent-mesh.yaml`:
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

    *   **Option B: Using `add agent` (For multiple instances):**
        If you need multiple Mermaid agents, use the `solace-agent-mesh add agent` command. Replace `<new_agent_name>` with a descriptive name (e.g., `mermaid_docs`, `mermaid_arch`).
        ```sh
        solace-agent-mesh add agent <new_agent_name> --copy-from sam_mermaid:mermaid
        ```
        This creates `<new_agent_name>.yaml` in `configs/agents/` with template variables automatically replaced.

## Environment Variables

The following environment variables are required for **Solace connection** (used by all agents):
- **SOLACE_BROKER_URL**
- **SOLACE_BROKER_USERNAME**
- **SOLACE_BROKER_PASSWORD**
- **SOLACE_BROKER_VPN**
- **SOLACE_AGENT_MESH_NAMESPACE**

For **each Mermaid agent instance**, you need to set the following environment variable:

- **`<AGENT_NAME>_MERMAID_SERVER_URL`** (Required): The full URL of your running [mermaid-server](https://github.com/TomWright/mermaid-server) instance (e.g., `http://localhost:8080`).

Replace `<AGENT_NAME>` with the uppercase version of the agent's name:
  - If you used **Option A** (editing `solace-agent-mesh.yaml`), the default agent name is `mermaid`, so use `MERMAID`.
  - If you used **Option B** (`add agent`), use the uppercase version of the `<new_agent_name>` you provided (e.g., `MERMAID_DOCS`, `MERMAID_ARCH`).

**Example Environment Variables:**

For the default agent loaded via `solace-agent-mesh.yaml` (Option A):
```bash
export MERMAID_MERMAID_SERVER_URL="http://127.0.0.1:9000"
```

For an agent named `mermaid_docs` created via `add agent` (Option B):
```bash
export MERMAID_DOCS_MERMAID_SERVER_URL="http://mermaid.internal.example.com"
```

## Actions

### draw
Generates a diagram (currently PNG format) from the provided Mermaid.js syntax string by sending it to the configured `mermaid-server`.

Parameters:
- **mermaid_code** (required): The Mermaid.js syntax string to render.
