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

The MCP Server Gateway architecture consists of the following components:

1. **MCP Server Gateway Component**
   - Implements the MCP server interface to communicate with MCP clients
   - Manages client connections and sessions
   - Translates MCP requests into Agent Mesh actions
   - Transforms Agent Mesh responses back to MCP responses

2. **Agent Registry**
   - Listens to agent registration messages on the event mesh
   - Maintains a catalog of available agents and their capabilities
   - Filters agents based on configured scopes
   - Exposes agent actions as MCP tools

3. **Direct Agent Invocation**
   - Bypasses the Orchestrator for efficiency
   - Sends action requests directly to appropriate agents
   - Listens for action responses from agents
   - Handles timeouts and error conditions

4. **Response Transformation**
   - Converts agent action responses to MCP-compatible format
   - Handles different response types (text, files, etc.)
   - Manages streaming responses when needed

5. **Security & Scoping**
   - Enforces scope-based access control
   - Validates client permissions
   - Ensures only authorized actions are exposed

#### Data Flow

1. **Client Connection**:
   - MCP client connects to the gateway
   - Gateway authenticates the client and establishes session

2. **Tool Discovery**:
   - Client requests available tools
   - Gateway filters registered agents based on scopes
   - Gateway returns available agent actions as MCP tools

3. **Tool Invocation**:
   - Client sends tool request
   - Gateway translates to agent action request
   - Gateway sends request directly to agent
   - Agent processes request and returns response
   - Gateway transforms response to MCP format
   - Gateway sends response back to client

4. **Resource Handling**:
   - For file/resource responses, gateway stores in file service
   - Gateway provides appropriate references in MCP response

#### Implementation Components

The implementation will require:

1. **Gateway Interface Components**:
   - `MCPServerGatewayComponent`: Main gateway component
   - `MCPServerGatewayInput`: Handles incoming MCP requests
   - `MCPServerGatewayOutput`: Formats responses for MCP clients

2. **Agent Registry Components**:
   - `AgentRegistryListener`: Subscribes to agent registration topics
   - `AgentCatalog`: Maintains registry of available agents and actions

3. **Action Invocation Components**:
   - `DirectAgentInvoker`: Sends requests to agents
   - `ResponseListener`: Listens for agent responses

4. **Utility Components**:
   - `MCPTransformer`: Converts between MCP and Agent Mesh formats
   - `ScopeValidator`: Enforces scope-based access control

This architecture provides a direct bridge between MCP clients and Agent Mesh agents, bypassing the orchestrator for efficiency while maintaining security through scope-based access control.

### Topics and Queues

<inst>
Describe all the topics that will need to be subscribed to and which topics will be used for publishing messages.

Also, describe the queues that will be used for storing messages and how they will be managed.
</inst>
