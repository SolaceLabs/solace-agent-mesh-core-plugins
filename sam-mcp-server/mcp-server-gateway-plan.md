## Building an MCP Server Gateway for Agent Mesh

We are planning out how to build a Gateway for Agent Mesh that will act as an MCP server to MCP clients. 

This gateway is going to be a bit different from other Solace Agent Mesh gateways. This gateway will act
as an MCP server so that MCP clients can connect to it via SSE (Server-Sent Events) and this gateway will
learn about all the agents in the Agent Mesh and will provide all those agents' actions as MCP tools.

The gateway will take in a JWT token in the header and will use that token to authenticate the client
using a secret key that is provided in the .yaml configuration file for the gateway. The JWT token will
contain the email address of the client and the secret key will be used to verify the token. 

The gateway can be configured with a list of scopes that will control which actions are provided to the MCP clients. The scopes
will be used to filter the agents that are available to the MCP clients. 

In addition to listening to the agent register messages, the gateway will have to listen to agent response messages that would be destined for
the orchestrator so that it can transform them into MCP responses.

The basic structure of the gateway will be as follows:
 - mcp_server_app.py - this is a solace-ai-connector app (inheriting from app.py) that contains all the flows for the gateways
 - mcp_server_input.py - this is a solace-ai-connector component that will handle the SSE input from the MCP clients and pass
   the messages to gateway_input
 - mcp_server_output.py - this is a solace-ai-connector component that will handle the SSE output to the MCP clients and receive
   messages from the gateway_output


In order for this to work, the solace-agent-mesh orchestrator (and gateway components) will also need some changes so that
the gateway can direct it to call the exact agent with the correct action and parameters. Then the orchestrator will need to
send that agent's response back to the gateway so that it can be sent to the MCP client. We won't be changing the orchestrator
or gateway components now since they live in other repos, but we should include in this file a description of the changes that will be needed
to those components so that we can make sure that the gateway is able to work with them.

## Clarifying Questions

<inst>
Review and edit the description above to make it more clear and concise. Then fill in this section with any clarifying questions
that you have about the gateway and how it will work. Let's make sure we are all on the same page before we start building this thing.
</inst>
