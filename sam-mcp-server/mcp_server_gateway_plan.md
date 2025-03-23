## Building an MCP Server Gateway for Agent Mesh

We are planning out how to build a Gateway for Agent Mesh that will act as an MCP server to MCP clients. 

This gateway is going to be very different from normal gateways in the Agent Mesh. Normally, the gateway will
simply forward incoming requests to the Orchestrator, and the orchestrator will decide which agents to call and how
to call them. 

Instead, this gateway is going to call the agents directly. It will also listen to the Agent register messages itself so that
it can build a registry of agents that it can call and provide that information to the MCP clients as tools that they can use.
When the MCP client wants to call an agent, it will call the gateway, and the gateway will call the agent. The response from the agent
will be transformed into an MCP response and sent back to the MCP client.

The gateway can be configured with a list of scopes that will control which actions are provided to the MCP clients. The scopes
will be used to filter the agents that are available to the MCP clients. 

In addition to listening to the agent register messages, the gateway will have to listen to agent response messages that would be destined for
the orchestrator so that it can transform them into MCP responses.

### Architecture

<inst>
Fill in the architecture here
</inst>
