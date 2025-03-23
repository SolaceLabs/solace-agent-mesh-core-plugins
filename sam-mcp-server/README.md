# MCP Server for Solace Agent Mesh

This plugin adds two powerful capabilities to Solace Agent Mesh:

1. **MCP Server Gateway**: Allows MCP clients to connect to Solace Agent Mesh and interact with agents through the Model Context Protocol
2. **MCP Server Agent**: Enables Solace Agent Mesh to connect to external MCP servers and expose their capabilities as agent actions

## What is the Model Context Protocol (MCP)?

The [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) is an open protocol that standardizes how applications provide context to LLMs. It enables:

- Secure access to tools and data sources
- Standardized communication between LLMs and external systems
- Consistent interfaces for resources, tools, and prompts

## MCP Server Gateway

The MCP Server Gateway acts as a bridge between MCP clients and Solace Agent Mesh agents. It:

- Exposes agent actions as MCP tools
- Translates MCP requests into agent actions
- Transforms agent responses into MCP responses
- Manages client sessions and authentication

### Installation

Add the plugin to your SAM instance:

```sh
solace-agent-mesh plugin add sam_mcp_server --pip -u git+https://github.com/SolaceLabs/solace-agent-mesh-core-plugins#subdirectory=sam-mcp-server
```

Then add the gateway interface to your configuration:

```sh
solace-agent-mesh add gateway mcp-server --interface mcp_server
```

### Configuration

The MCP Server Gateway supports the following configuration options:

| Option | Description | Default |
|--------|-------------|---------|
| `MCP_SERVER_SCOPES` | Scopes to filter agents by | `*:*:*` |
| `MCP_SERVER_PORT` | Port for the MCP server (SSE mode) | `8080` |
| `MCP_SERVER_HOST` | Host for the MCP server (SSE mode) | `0.0.0.0` |
| `MCP_SERVER_TRANSPORT` | Transport type (`stdio` or `sse`) | `sse` |

You can set these options in your environment or in the gateway configuration file.

### Architecture

The MCP Server Gateway consists of several components:

1. **Agent Registry**: Maintains a catalog of available agents and their capabilities
2. **MCP Server**: Implements the MCP server interface to communicate with clients
3. **Direct Agent Invocation**: Sends action requests directly to agents and processes responses
4. **Session Management**: Handles client authentication and authorization

### Usage

Once configured, MCP clients can connect to the gateway and:

1. Discover available tools (agent actions)
2. Execute tools with parameters
3. Access agent resources
4. Use agent prompt templates

## MCP Server Agent

The MCP Server Agent allows Solace Agent Mesh to connect to external MCP servers and expose their capabilities as agent actions.

### Installation

To use a single MCP server, update your `solace-agent-mesh.yaml` file:

```yaml
plugins:
  - name: sam_mcp_server
    load_unspecified_files: false
    includes_gateway_interface: true
    load:
      agents:
        - mcp_server
      gateways: []
      overwrites: []
```

And provide the following environment variables:
- `MCP_SERVER_NAME`: Name of the MCP server
- `MCP_SERVER_COMMAND`: Command to start the MCP server

### Multiple MCP Servers

To use multiple MCP servers, create a new agent for each server:

```sh
solace-agent-mesh add agent mcp_server --copy-from sam_mcp_server
```

This will create a new config file in your agent config directory. Rename this file to your MCP server name.
You can also rename or hard-code the following environment variables:
- `MCP_SERVER_NAME`
- `MCP_SERVER_COMMAND`

### Example Configuration

```
MCP_SERVER_NAME=filesystem
MCP_SERVER_COMMAND=npx -y @modelcontextprotocol/server-filesystem /Path/To/Allow/Access
```

or

```
MCP_SERVER_NAME=server-everything
MCP_SERVER_COMMAND=npx -y @modelcontextprotocol/server-everything
```

### Advanced Configuration

The MCP Server Agent supports additional configuration options:

| Option | Description | Default |
|--------|-------------|---------|
| `server_name` | Name of the MCP server | Required |
| `server_description` | Description of the MCP server | Required |
| `mode` | Communication mode (`stdio` or `sse`) | `stdio` |
| `timeout` | Request timeout in seconds | `90` |
| `sse_base_url` | Base URL for SSE mode | Required for SSE mode |
| `server_command` | Command to start the server | Required for stdio mode |
| `server_startup_timeout` | Timeout for server startup in seconds | `30` |

## Security Considerations

- The MCP Server Gateway enforces scope-based access control
- Client sessions are authenticated and authorized
- Resource access is controlled by agent permissions
- Tool execution is validated and monitored

## Troubleshooting

### Common Issues

1. **Gateway not starting**:
   - Check configuration values
   - Verify environment variables
   - Check logs for errors

2. **Client connection failures**:
   - Verify transport configuration
   - Check network connectivity
   - Ensure client is using compatible MCP version

3. **Tool execution errors**:
   - Verify agent is registered and available
   - Check parameter validation
   - Look for timeout or connection issues

### Logging

The MCP Server Gateway and Agent log to the standard Solace Agent Mesh log files. Set the log level to `DEBUG` for more detailed information.

## Examples

### Example 1: Using the Filesystem MCP Server

```
MCP_SERVER_NAME=filesystem
MCP_SERVER_COMMAND=npx -y @modelcontextprotocol/server-filesystem /home/user/documents
```

This exposes the filesystem server's capabilities as agent actions, allowing access to files in the specified directory.

### Example 2: Using the GitHub MCP Server

```
MCP_SERVER_NAME=github
MCP_SERVER_COMMAND=npx -y @modelcontextprotocol/server-github
```

This exposes GitHub repository operations as agent actions, enabling repository management through the agent.

## Contributing

Contributions to the MCP Server plugin are welcome! Please see the [contributing guidelines](CONTRIBUTING.md) for more information.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
