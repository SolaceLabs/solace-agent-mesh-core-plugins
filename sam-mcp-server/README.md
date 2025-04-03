# Solace Agent Mesh MCP Server Plugin

This plugin adds capabilities to Solace Agent Mesh (SAM) for interacting with servers that implement the Model Context Protocol (MCP). It provides:

1.  **An Agent (`mcp_server`)**: Allows SAM to act as an MCP client, connecting to an external MCP server (like `server-filesystem` or `server-everything`) and exposing its tools, resources, and prompts as SAM actions.
2.  **A Gateway Interface**: Allows SAM itself to act as an MCP server, exposing its own agents and capabilities to external MCP clients (This part might be less commonly used but is included in the plugin structure).

## Add an MCP Server Agent to SAM

1.  **Add the Plugin:**
    If you haven't already, add the plugin to your SAM instance:
    ```sh
    solace-agent-mesh plugin add sam_mcp_server --pip -u git+https://github.com/SolaceLabs/solace-agent-mesh-core-plugins#subdirectory=sam-mcp-server
    ```

2.  **Instantiate the Agent:**
    Use the `solace-agent-mesh add agent` command to create a configuration file for your specific MCP server instance. Replace `<new_agent_name>` with a descriptive name (e.g., `filesystem_docs`, `server_everything_dev`).
    ```sh
    solace-agent-mesh add agent <new_agent_name> --copy-from sam_mcp_server:mcp_server
    ```
    This command creates a new YAML file in `configs/agents/` named `<new_agent_name>.yaml`. The template variables (`{{SNAKE_CASE_NAME}}`, `{{SNAKE_UPPER_CASE_NAME}}`) inside the copied file will be automatically replaced with your chosen agent name.

## Environment Variables

The following environment variables are required for **Solace connection** (used by all agents):
- **SOLACE_BROKER_URL**
- **SOLACE_BROKER_USERNAME**
- **SOLACE_BROKER_PASSWORD**
- **SOLACE_BROKER_VPN**
- **SOLACE_AGENT_MESH_NAMESPACE**

For **each MCP Server agent instance**, you need to set the following environment variables, replacing `<AGENT_NAME>` with the uppercase version of the name you chose during the `add agent` step (e.g., `FILESYSTEM_DOCS`, `SERVER_EVERYTHING_DEV`):

- **`<AGENT_NAME>_SERVER_COMMAND`** (Required): The full command line needed to start the target MCP server process.
- **`<AGENT_NAME>_SERVER_DESCRIPTION`** (Optional): A description of what this MCP server provides. If not set, it defaults to "Provides access to the `<agent_name>` MCP server".

**Example Environment Variables:**

For an agent named `filesystem_docs`:
```bash
export FILESYSTEM_DOCS_SERVER_COMMAND="npx -y @modelcontextprotocol/server-filesystem /path/to/your/documents"
export FILESYSTEM_DOCS_SERVER_DESCRIPTION="Provides access to project documentation via MCP."
```

For an agent named `server_everything_dev`:
```bash
export SERVER_EVERYTHING_DEV_SERVER_COMMAND="npx -y @modelcontextprotocol/server-everything"
# Optional: export SERVER_EVERYTHING_DEV_SERVER_DESCRIPTION="General purpose MCP server for development."
```

## How it Works

The `mcp_server` agent starts the process specified by the `*_SERVER_COMMAND` environment variable. It communicates with this process using standard input/output (stdio) according to the MCP specification.

When the agent starts, it connects to the MCP server, queries its capabilities (tools, resources, prompts), and dynamically creates corresponding SAM actions. For example, if the MCP server exposes a tool named `readFile`, the SAM agent will create an action named `readFile` that can be invoked through SAM. Similarly, resources become `get_<resource_name>` actions, and prompts become `use_prompt_<prompt_name>` actions.

This allows you to interact with various MCP-compliant tools and servers seamlessly within the Solace Agent Mesh ecosystem.
