## Building an MCP Server Gateway for Agent Mesh

We are planning out how to build a Gateway for Agent Mesh that will act as an MCP server to MCP clients. 

This gateway is going to be a bit different from other Solace Agent Mesh gateways. This gateway will act
as an MCP server so that MCP clients can connect to it via SSE (Server-Sent Events) and this gateway will
learn about all the agents in the Agent Mesh and will provide all those agents' actions as MCP tools.
The configuration for the gateway will alos

