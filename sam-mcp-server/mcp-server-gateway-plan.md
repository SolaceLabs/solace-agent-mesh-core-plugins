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
    A: Just the email address of the user. The gateway will use this to determine the user's identity and permissions.
    *   How will the secret key for JWT validation be managed and configured? Is it a single key, or per-client?
    A: Per-client. We will create a script to generate a JWT token for each client. The secret key will be stored in the configuration of the gateway app.
    *   What is the expected token expiration handling?
    A: The token will have a configurable expiration time. The gateway will check the expiration time before processing requests. If the token is expired, the request will be rejected.
    *   How should authentication failures be reported back to the MCP client (e.g., HTTP error code, MCP error response)?
    A: The gateway will return an HTTP 401 Unauthorized error for authentication failures. For MCP errors, it will return an MCP error response with a specific error code (e.g., `INVALID_PARAMS`) and a message indicating the authentication failure.
2.  **Authorization (Scopes):**
    *   Where are the user's allowed scopes defined? Within the JWT, or mapped via gateway configuration based on email/user ID?
    A: The scopes can either be set as a claim in the JWT, a configuration for the mcp gateway app or the system can use some auth tools to look them up in a separate database.
    *   How exactly will the scope filtering work? Will it filter the list of tools sent during initialization (`tools/list`), or just reject unauthorized `tools/call` requests at runtime?
    A: The gateway will filter the list of tools sent during initialization based on the user's scopes. For `tools/call` requests, it will check the scopes again and reject unauthorized requests with an appropriate error response.
    *   What is the proposed format for scopes (e.g., `agent_name:action_name:permission`)?
    A: Yes, though the agent does control the definition. For our purposes, we just need to check the 3 elements and support wildcards.
3.  **Orchestrator/Agent Interaction:**
    *   What is the proposed message format and topic structure for the gateway to request direct action execution from an agent (bypassing the orchestrator's LLM planning)?
    A: You will suggest what will be used based on what you learn from the other files and document it in the arch description below.
    *   How will the gateway correlate incoming action responses (originally intended for the orchestrator) with the originating MCP client request? Will a unique ID (e.g., MCP request ID) be added to the message user properties when the gateway forwards the request?
    A: Yes, the gateway will add a unique ID to the message user properties when forwarding the request. This ID will be used to correlate the response with the original request.
    *   What specific changes are anticipated in the orchestrator to support this gateway? (e.g., new input topic for direct requests, modified response routing logic based on user properties).
    A; The orchestrator will need to listen for messages on a new input topic specifically for direct requests from the MCP gateway. It will also need to modify the response routing logic to check the user properties and route the response back to the correct MCP client.
4.  **MCP Protocol Implementation:**
    *   Which specific MCP capabilities will this gateway support initially? (Tools are primary, but what about Resources, Prompts, Sampling, Logging)?
    A: The gateway will initially support the following MCP capabilities:
        *   Tools: Exposing agent actions as MCP tools.
        *   Resources: Exposing files and other resources as MCP resources.
        *   Logging: Basic logging of requests and responses.
    *   How will MCP errors (e.g., `METHOD_NOT_FOUND`, `INVALID_PARAMS`) be handled and reported back to the client?
    A: The gateway will handle MCP errors by returning the appropriate error response to the client. For example, if a method is not found, it will return an `INVALID_PARAMS` error with a message indicating the issue.
    *   How will agent action errors (received in the action response) be translated into MCP tool call error responses (e.g., `isError: true` with details in `content`)?
    A: The gateway will translate agent action errors into MCP tool call error responses by checking the response from the agent. If the response indicates an error, the gateway will return an `isError: true` response with the error details in the `content` field.
5.  **SSE Transport:**
    *   How will multiple simultaneous client connections via SSE be managed within the `solace-ai-connector` framework?
    A: This must be supported. You can suggest a design based on your knowledge of the framework and document it in the arch description below.
    *   What is the expected behavior if an MCP client disconnects unexpectedly? How is connection state and potential pending requests cleaned up?
    A: The gateway will monitor client connections and clean up any pending requests if a client disconnects unexpectedly.
6.  **State Management:**
    *   Does the gateway need to maintain session state for each connected MCP client? If so, what information needs to be stored (e.g., authenticated user info, correlation IDs)?
    A: Yes, the gateway will need to maintain session state for each connected MCP client. The information stored will include:
        *   Authenticated user info (e.g., email, scopes).
        *   Correlation IDs for tracking requests and responses.
        *   Connection state (e.g., active/inactive).
    *   How will the list of available agents/tools be kept up-to-date? Will it rely solely on registration messages, or periodically refresh/expire 
    agents?
    A: Registration messages are periodically sent in to the broker, which will be forwarded to the gateway. The gateway will also periodically refresh the list of available agents/tools to ensure it is up-to-date. If there are updates, then the gateway will send a `tools/list_changed` notification to the connected clients.
7.  **Configuration:**
    *   What are the essential configuration parameters vs. optional ones for the gateway (e.g., JWT secret, scopes, SSE endpoint paths, Solace connection details)?
    A: You can determine this
8.  **Error Handling:**
    *   How should errors originating from the target agent (during action execution) be propagated back to the MCP client?
    A: Do your best
    *   How should timeouts (e.g., waiting for an agent response) be handled and reported to the MCP client?
    A: Do your best


## Architecture

<inst>
Fill in this section with a detailed description of the architecture, including:
- Components involved
- Data flow between components
- Key interactions with the SAM orchestrator and agents
- How SSE and HTTP POST are used for communication
- How JWT authentication and authorization are implemented
- How agent registration and action invocation are handled
- How errors are managed and reported

You can use mermaid diagrams to illustrate the architecture and data flow.
</inst>



