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

This MCP Server Gateway acts as a bridge between MCP clients and the Solace Agent Mesh (SAM). It exposes registered SAM agent actions as MCP tools, allowing MCP clients to interact with the agent mesh using the standard MCP protocol over an SSE/HTTP transport.

### Components

The gateway is built using the `solace-ai-connector` framework and consists of several interconnected flows and components:

1.  **MCP Connection Handling Flow (`mcp_connection_flow`):**
    *   **`mcp_server_input` (Custom Component):**
        *   Acts as an HTTP server listening for incoming connections.
        *   Handles the SSE handshake (`/sse` endpoint) for server-to-client communication.
        *   Handles HTTP POST requests (`/messages` endpoint) for client-to-server communication.
        *   Performs JWT authentication based on the `Authorization: Bearer <token>` header using a configured secret key. Extracts user identity (email) and potentially scopes.
        *   Manages client sessions, storing session state (user info, SSE stream reference, correlation IDs) likely using the flow's Key-Value store, keyed by a unique `mcp_client_session_id`.
        *   Parses incoming MCP JSON-RPC messages (requests and notifications) from POST requests.
        *   Forwards valid MCP requests (like `tools/call`, `tools/list`) to the `mcp_processing_flow`.
        *   Handles MCP initialization (`initialize`, `initialized`).
        *   Manages SSE connection lifecycle and cleanup on disconnect.
    *   **`mcp_server_output` (Custom Component):**
        *   Receives processed responses or notifications destined for a specific MCP client (identified by `mcp_client_session_id` in message properties).
        *   Retrieves the corresponding client session state (including the SSE stream reference) from the KV store.
        *   Formats the data as MCP JSON-RPC messages (responses or notifications).
        *   Sends the messages to the client via the established SSE connection.

2.  **MCP Request Processing Flow (`mcp_processing_flow`):**
    *   **`broker_input` (Standard Component):** Receives MCP requests forwarded from `mcp_server_input`.
    *   **`mcp_request_handler` (Custom Component):**
        *   Processes specific MCP requests.
        *   **`initialize`:** Responds with server capabilities (dynamically generated tool list based on registered agents and user scopes).
        *   **`tools/list`:** Retrieves the current list of registered agents/actions from the `agent_registry`, filters based on user scopes (from session state), formats them as MCP tools, and sends the list back via `mcp_server_output`.
        *   **`tools/call`:**
            *   Validates the requested tool/action against the user's scopes.
            *   Generates a unique `mcp_request_id` for correlation.
            *   Stores correlation info (MCP request ID -> `mcp_client_session_id`) in the KV store.
            *   Formats a direct action request message for the target agent. Adds `mcp_request_id` and `mcp_client_session_id` to user properties.
            *   Publishes the action request to a dedicated Solace topic (e.g., `${SAM_NAMESPACE}mcp-gateway/v1/actionRequest/agent/{agent_name}/{action_name}`).
        *   **Other MCP Requests (Resources, Prompts):** Handles these based on supported capabilities (initially basic file resources might be mapped).
    *   **`broker_output` (Standard Component):** Publishes direct action requests to the Solace broker.

3.  **Agent Registration Flow (`agent_registration_flow`):**
    *   **`broker_input` (Standard Component):** Subscribes to agent registration topics (`${SAM_NAMESPACE}solace-agent-mesh/v1/register/>`).
    *   **`agent_registry` (Custom Component):**
        *   Maintains an in-memory or KV-store-backed registry of active agents and their actions.
        *   Updates the registry based on incoming registration messages.
        *   Compares new registrations with the current state. If the list of available tools changes, it triggers a `tools/list_changed` notification.
        *   Handles agent expiry/deregistration based on TTL in registration messages or lack thereof.
    *   **`mcp_notification_output` (Custom Component):** If `tools/list_changed` is triggered, this component iterates through all active client sessions (from the KV store) and sends the `notifications/tools/list_changed` message via the `mcp_server_output` component.

4.  **Action Response Flow (`action_response_flow`):**
    *   **`broker_input` (Standard Component):** Subscribes to the standard agent action response topic (`${SAM_NAMESPACE}solace-agent-mesh/v1/actionResponse/>`).
    *   **`mcp_response_correlator` (Custom Component):**
        *   Inspects the user properties of incoming action responses.
        *   If `mcp_client_session_id` and `mcp_request_id` are present:
            *   Retrieves the original MCP request ID using the correlation data stored in the KV store.
            *   Formats the agent response (success or error) into an MCP `tools/call` result (JSON-RPC response). Handles translation of `ActionResponse` fields (including `error_info`) to MCP format (`isError`, `content`).
            *   Forwards the formatted MCP response to the `mcp_server_output` component, including the target `mcp_client_session_id` in properties.
            *   Acknowledges the message to prevent the orchestrator from processing it.
        *   If MCP properties are not present, the message is simply passed through (or discarded if no downstream component exists in this flow), allowing the orchestrator to handle it as usual.

### Data Flow Diagram (Simplified Tool Call)

```mermaid
sequenceDiagram
    participant Client as MCP Client
    participant GatewayIn as mcp_server_input (HTTP/SSE)
    participant GatewayProc as mcp_request_handler
    participant Broker as Solace Broker
    participant Agent as Target SAM Agent
    participant GatewayResp as mcp_response_correlator
    participant GatewayOut as mcp_server_output (SSE)

    Client->>+GatewayIn: POST /messages (tools/call Request, JWT)
    GatewayIn->>GatewayIn: Validate JWT, Authz Check
    alt Auth Failure
        GatewayIn-->>Client: HTTP 401 / MCP Error
    else Auth Success
        GatewayIn->>Broker: Publish MCP Request (Internal Topic)
    end
    Broker->>+GatewayProc: Consume MCP Request
    GatewayProc->>GatewayProc: Generate mcp_request_id, Store Correlation (MCP ID -> Client Session ID)
    GatewayProc->>Broker: Publish Direct Action Request (Agent Topic, incl. mcp_request_id, mcp_client_session_id)
    Broker->>+Agent: Consume Direct Action Request
    Agent->>Agent: Execute Action
    Agent->>Broker: Publish Action Response (Standard Response Topic, incl. mcp_request_id, mcp_client_session_id)
    Broker->>+GatewayResp: Consume Action Response
    GatewayResp->>GatewayResp: Check for MCP properties, Correlate mcp_request_id
    alt Is MCP Response
        GatewayResp->>GatewayResp: Format MCP Result/Error
        GatewayResp->>Broker: Publish Formatted MCP Response (Internal Topic)
        Broker->>+GatewayOut: Consume Formatted MCP Response
        GatewayOut->>GatewayOut: Retrieve Client SSE Stream
        GatewayOut-->>-Client: Send MCP Result/Error via SSE
        GatewayResp-->>Broker: ACK Action Response
    else Is Not MCP Response
        GatewayResp-->>Broker: NACK/Ignore Action Response (Orchestrator handles)
    end
    deactivate Agent
    deactivate GatewayProc
    deactivate GatewayResp
    deactivate GatewayOut
```

### Key Interactions & Concepts

*   **SSE/HTTP Transport:** `mcp_server_input` manages the dual nature of SSE (server->client) and HTTP POST (client->server). Each client connection establishes an SSE stream for receiving messages and uses POST requests to a specific endpoint (containing a session ID) to send messages.
*   **Authentication:** Performed by `mcp_server_input` on every incoming HTTP POST request using the JWT Bearer token. The validated user identity (email) and potentially scopes are stored in the client's session state.
*   **Authorization:**
    *   `mcp_request_handler` filters the tool list in `tools/list` based on the user's scopes stored in the session state.
    *   `mcp_request_handler` re-validates scopes before publishing a direct action request for `tools/call`. Unauthorized calls result in an MCP error sent back via `mcp_server_output`.
*   **Agent Discovery & Tool Mapping:** The `agent_registry` component listens for standard SAM registration messages. It maps the `agent_name` and `action_name` to MCP tool names (e.g., `agent_name.action_name`). Action parameters are mapped to the MCP tool's `inputSchema`. Changes trigger `tools/list_changed` notifications.
*   **Direct Action Invocation:** Instead of sending a stimulus to the orchestrator, `mcp_request_handler` constructs a message mimicking an `ActionRequest` payload and publishes it to a topic targeting the specific agent directly (e.g., `${SAM_NAMESPACE}mcp-gateway/v1/actionRequest/agent/{agent_name}/{action_name}`). Crucially, it adds `mcp_request_id` and `mcp_client_session_id` to the user properties.
*   **Response Correlation:** `mcp_response_correlator` intercepts *all* action responses. It checks for the presence of `mcp_client_session_id` and `mcp_request_id`. If found, it uses this information to look up the original MCP client session and request ID, formats the response for MCP, and sends it to `mcp_server_output`. It then ACKs the message so the orchestrator doesn't see it.
*   **State Management:** The `solace-ai-connector` KV store is used extensively:
    *   `mcp_server_input`: Stores client session state (SSE stream reference, user info, scopes) keyed by `mcp_client_session_id`.
    *   `mcp_request_handler`: Stores correlation map (`mcp_request_id` -> `mcp_client_session_id`) to link agent responses back to MCP requests.
    *   `agent_registry`: Stores the current list of agents and their actions.
*   **Error Handling:**
    *   Authentication/Authorization errors: HTTP 401 or MCP `INVALID_PARAMS`/`INTERNAL_ERROR`.
    *   Agent action errors: `ActionResponse.error_info` is mapped to MCP `CallToolResult` with `isError: true` and the error message in `content`.
    *   Timeouts: If the gateway doesn't receive a response from the agent within a configured timeout, `mcp_request_handler` (or a dedicated timeout mechanism) should generate an MCP error response (e.g., `INTERNAL_ERROR` code -32603) indicating the timeout and send it via `mcp_server_output`.

