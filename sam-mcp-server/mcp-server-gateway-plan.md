## Building an MCP Server Gateway for Agent Mesh

The plan is to build a Solace Agent Mesh (SAM) Gateway that acts as a Model Context Protocol (MCP) server. This gateway will allow MCP clients (like Claude Desktop) to connect via Server-Sent Events (SSE) and interact with the agents registered within the SAM instance.

Key functionalities:

1.  **MCP Server Implementation:** The gateway will expose SAM agents' actions as MCP tools.
2.  **SSE Transport:** Communication with MCP clients will use SSE for server-to-client messages and HTTP POST for client-to-server messages.
3.  **Agent Discovery:** The gateway will listen for agent registration messages to dynamically discover available agents and their actions.
4.  **Action Mapping:** Discovered agent actions will be mapped to MCP tools.
5.  **Authentication:** MCP clients will authenticate using a JWT token provided in the request header. The gateway will validate this token using a configured secret key. The JWT should contain user identity information (e.g., email).
6.  **Authorization (Scopes):** The gateway configuration will allow defining scopes to filter which agent actions (MCP tools) are exposed to connected clients based on the authenticated user's permissions (derived from the JWT or configuration).
7.  **Orchestrator/Agent Interaction:**
    *   When an MCP client invokes a tool, the gateway will need to formulate a request (potentially bypassing the usual LLM planning step) to the SAM orchestrator or directly to the target agent.
    *   The gateway must listen for action responses destined for the orchestrator to capture results and forward them back to the appropriate MCP client via SSE.
8.  **Component Structure:** The gateway will likely consist of several `solace-ai-connector` components:
    *   `mcp_server_app.py`: Manages the gateway's flows.
    *   `mcp_server_input.py`: Handles incoming SSE/HTTP connections and client requests.
    *   `mcp_server_output.py`: Sends responses and notifications back to clients via SSE.
    *   Components for listening to agent registrations and action responses.

**Note:** This design requires modifications to the core SAM orchestrator and potentially gateway components to handle direct action invocation requests from this MCP gateway and to route responses back correctly. These changes are outside the scope of this specific gateway implementation but are necessary for end-to-end functionality.

## Clarifying Questions

1.  **Authentication (JWT):**
    *   What specific claims are expected within the JWT (e.g., `email`, `sub`, `scopes`)?
    *   How will the secret key for JWT validation be managed and configured? Is it a single key, or per-client?
    *   What is the expected token expiration handling?
    *   How should authentication failures be reported back to the MCP client (e.g., HTTP error code, MCP error response)?
2.  **Authorization (Scopes):**
    *   Where are the user's allowed scopes defined? Within the JWT, or mapped via gateway configuration based on email/user ID?
    *   How exactly will the scope filtering work? Will it filter the list of tools sent during initialization (`tools/list`), or just reject unauthorized `tools/call` requests at runtime?
    *   What is the proposed format for scopes (e.g., `agent_name:action_name:permission`)?
3.  **Orchestrator/Agent Interaction:**
    *   What is the proposed message format and topic structure for the gateway to request direct action execution from an agent (bypassing the orchestrator's LLM planning)?
    *   How will the gateway correlate incoming action responses (originally intended for the orchestrator) with the originating MCP client request? Will a unique ID (e.g., MCP request ID) be added to the message user properties when the gateway forwards the request?
    *   What specific changes are anticipated in the orchestrator to support this gateway? (e.g., new input topic for direct requests, modified response routing logic based on user properties).
4.  **MCP Protocol Implementation:**
    *   Which specific MCP capabilities will this gateway support initially? (Tools are primary, but what about Resources, Prompts, Sampling, Logging)?
    *   How will MCP errors (e.g., `METHOD_NOT_FOUND`, `INVALID_PARAMS`) be handled and reported back to the client?
    *   How will agent action errors (received in the action response) be translated into MCP tool call error responses (e.g., `isError: true` with details in `content`)?
5.  **SSE Transport:**
    *   How will multiple simultaneous client connections via SSE be managed within the `solace-ai-connector` framework?
    *   What is the expected behavior if an MCP client disconnects unexpectedly? How is connection state and potential pending requests cleaned up?
6.  **State Management:**
    *   Does the gateway need to maintain session state for each connected MCP client? If so, what information needs to be stored (e.g., authenticated user info, correlation IDs)?
    *   How will the list of available agents/tools be kept up-to-date? Will it rely solely on registration messages, or periodically refresh/expire agents?
7.  **Configuration:**
    *   What are the essential configuration parameters vs. optional ones for the gateway (e.g., JWT secret, scopes, SSE endpoint paths, Solace connection details)?
8.  **Error Handling:**
    *   How should errors originating from the target agent (during action execution) be propagated back to the MCP client?
    *   How should timeouts (e.g., waiting for an agent response) be handled and reported to the MCP client?
