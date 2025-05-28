# SAM A2A Client Plugin Architecture

## High-Level Architecture Overview

The `sam-a2a-client` plugin allows Solace Agent Mesh (SAM) to interact with external agents that conform to the Agent-to-Agent (A2A) protocol. It acts as a bridge, enabling SAM to leverage the capabilities of A2A agents.

The core of the plugin is a SAM `BaseAgentComponent` (`A2AClientAgentComponent`). This component orchestrates the interaction with the external A2A agent, delegating specific responsibilities to helper classes and modules:

1.  **Process Management (Optional):** If configured with a command (`a2a_server_command`), the `A2AProcessManager` helper class is used to launch, monitor, and manage the lifecycle of the external A2A agent process, including restarts on failure.
2.  **Connection & Readiness:** The `A2AConnectionHandler` helper class manages the connection to the A2A agent (launched or pre-existing). It checks for agent readiness by polling the `/.well-known/agent.json` endpoint and handles fetching the `AgentCard` using the `A2ACardResolver` library.
3.  **Client Initialization:** `A2AConnectionHandler` initializes the `A2AClient` library instance, configuring it with the agent's URL and any required authentication details (e.g., bearer token) derived from the component's configuration and the fetched `AgentCard`.
4.  **Capability Mapping:** The `a2a_action_factory` module is used by `A2AClientAgentComponent` to parse the `skills` listed in the `AgentCard` and dynamically create corresponding SAM `Action` instances (`A2AClientAction`). Each SAM action maps directly to an A2A skill.
5.  **Invocation Handling:** When the SAM orchestrator invokes one of these dynamic actions, the `A2AClientAction` instance translates the SAM action parameters into an A2A `Task` request.
6.  **A2A Communication:** `A2AClientAction` uses the `A2AClient` instance (held by `A2AConnectionHandler` and accessed via `A2AClientAgentComponent`) to send the `Task` request (via `tasks/send`) to the external A2A agent.
7.  **Response Handling:** `A2AClientAction` receives the A2A `Task` response, processes the result (including handling different `Parts` like text, files, data, and artifacts using the `FileService`), and translates it back into a SAM `ActionResponse`.
8.  **State Management (`INPUT_REQUIRED`):**
    *   If an A2A task returns `INPUT_REQUIRED`, `A2AClientAction` uses the `CacheService` to store the A2A `taskId` mapped to a unique `sam_follow_up_id` and returns this ID to the orchestrator.
    *   A static action, `ProvideInputAction` (created by `a2a_action_factory`), is defined to handle follow-up requests.
    *   When invoked, `ProvideInputAction` calls the `handle_provide_required_input` function (in `a2a_input_handler.py`), which retrieves the original `a2a_taskId` from the cache, constructs a new A2A request with the user's input, sends it via the `A2AClient`, and processes the final response.

This architecture allows the SAM orchestrator and LLM to interact with A2A agents as if they were native SAM agents, abstracting the underlying A2A protocol details and separating concerns like process management and connection handling.

## Component List

*   **`A2AClientAgentComponent`**: The main SAM component derived from `BaseAgentComponent`. Orchestrates the plugin's functionality, holds references to helper classes and core services, manages the `ActionList`, and defines the handler entry point for the static `provide_required_input` action.
*   **`A2AProcessManager`**: Helper class responsible for launching, monitoring, and stopping the external A2A agent process when `a2a_server_command` is configured.
*   **`A2AConnectionHandler`**: Helper class responsible for checking agent readiness, fetching the `AgentCard` (using `A2ACardResolver`), and initializing/holding the `A2AClient` instance.
*   **`a2a_action_factory` (Module)**: Contains factory functions (`create_actions_from_card`, `create_provide_input_action`, `infer_params_from_skill`) used by `A2AClientAgentComponent` to dynamically generate SAM `Action` instances based on the `AgentCard`. Also defines the `ProvideInputAction` class.
*   **`A2AClientAction`**: A dynamically created SAM `Action` class representing a specific A2A `skill`. Handles the invocation logic, parameter mapping, A2A communication (via `A2AClient`), and response processing (including `INPUT_REQUIRED` state initiation).
*   **`ProvideInputAction`**: A static SAM `Action` class created by the factory. Its `invoke` method calls the main handler function for follow-up input.
*   **`a2a_input_handler` (Module)**: Contains the `handle_provide_required_input` function, which implements the logic for retrieving state from the cache and sending follow-up requests to the A2A agent.
*   **`A2AClient` (External Library)**: From the `google/A2A` common library. Used to handle the actual HTTP/JSON-RPC communication with the A2A agent server.
*   **`A2ACardResolver` (External Library)**: From the `google/A2A` common library. Used to fetch and parse the `AgentCard`.
*   **`FileService` (SAM Core)**: Used by `A2AClientAction` and `handle_provide_required_input` to resolve file URLs into bytes for outgoing requests and to save incoming file parts/artifacts for the `ActionResponse`.
*   **Cache Service (SAM Core)**: Used by `A2AClientAction` and `handle_provide_required_input` to store and retrieve the mapping between `sam_follow_up_id` and A2A `taskId` for the `INPUT_REQUIRED` state.

## Component Diagram

```mermaid
graph TD
    subgraph SAM Framework
        Orchestrator --> A2AClientAgentComponent;
        A2AClientAgentComponent --> ActionList[Action List];
        ActionList --> A2AClientAction["A2AClientAction (Dynamic)"];
        ActionList --> ProvideInputAction["ProvideInputAction (Static)"];
        A2AClientAgentComponent -- Uses --> CacheService[(Cache Service)];
        A2AClientAction -- Uses --> FileService[(File Service)];
        ProvideInputAction -- Calls --> InputHandlerModule["a2a_input_handler.py"];
    end

    subgraph Plugin Internals
        A2AClientAgentComponent -- Uses --> ProcessManager["A2AProcessManager"];
        A2AClientAgentComponent -- Uses --> ConnectionHandler["A2AConnectionHandler"];
        A2AClientAgentComponent -- Uses --> ActionFactoryModule["a2a_action_factory.py"];
        ActionFactoryModule -- Creates --> A2AClientAction;
        ActionFactoryModule -- Creates --> ProvideInputAction;
        ConnectionHandler -- Creates/Holds --> A2AClientLib;
        ConnectionHandler -- Uses --> A2ACardResolverLib;
        A2AClientAction -- Uses --> A2AClientLib;
        InputHandlerModule["a2a_input_handler.py"] -- Uses --> A2AClientLib;
        InputHandlerModule -- Uses --> CacheService;
        InputHandlerModule -- Uses --> FileService;
    end

    subgraph A2A Common Library
        A2AClientLib[A2AClient];
        A2ACardResolverLib[A2ACardResolver];
    end

    subgraph External A2A Agent Process
        A2AAgentServer[A2A Agent Server];
        AgentCardEndpoint["/.well-known/agent.json"];
        A2AEndpoint["/a2a JSON-RPC"];
        A2AAgentServer -- Serves --> AgentCardEndpoint;
        A2AAgentServer -- Handles --> A2AEndpoint;
    end

    ProcessManager -- Manages --> A2AAgentServer;
    ConnectionHandler -- Checks --> AgentCardEndpoint;
    A2ACardResolverLib -- Fetches --> AgentCardEndpoint;
    A2AClientLib -- Sends/Receives --> A2AEndpoint;

    style SAM Framework fill:#f9f,stroke:#333,stroke-width:2px;
    style Plugin Internals fill:#ffc,stroke:#333,stroke-width:1px;
    style External A2A Agent Process fill:#ccf,stroke:#333,stroke-width:2px;
    style A2A Common Library fill:#cfc,stroke:#333,stroke-width:2px;

```

## Sequence Diagram - Happy Path (Synchronous `tasks/send`)

```mermaid
sequenceDiagram
    participant Orch as SAM Orchestrator
    participant Comp as A2AClientAgentComponent
    participant Action as A2AClientAction
    participant ConnHandler as A2AConnectionHandler
    participant A2AClient as A2AClient Lib
    participant A2AServer as External A2A Agent Server

    Note over Orch, A2AServer: Initial Setup: Comp uses ProcessManager (optional), ConnHandler fetches Card, creates A2AClient, Comp uses factory to create Action.

    Orch->>Comp: Invoke Action(skill_id, params, meta)
    Comp->>Action: invoke(params, meta)
    Action->>Comp: Get A2AClient instance (via ConnHandler)
    Action->>A2AClient: Prepare TaskSendParams (new taskId, sessionId, message parts)
    Note right of Action: Map SAM params to A2A Parts (using FileService if needed)
    Action->>A2AClient: send_task(TaskSendParams)
    A2AClient->>A2AServer: POST /a2a (JSON-RPC tasks/send)
    A2AServer-->>A2AClient: Process Task (State: SUBMITTED -> WORKING -> COMPLETED)
    A2AServer-->>A2AClient: HTTP Response (JSON-RPC result: Task object with state=COMPLETED, message/artifacts)
    A2AClient-->>Action: Return Task object
    Action->>Comp: Process Task result
    Note right of Action: Map A2A Parts/Artifacts to ActionResponse (using FileService if needed)
    Action-->>Comp: Return ActionResponse (success=true, message, files, data)
    Comp-->>Orch: Return ActionResponse
```

## Sequence Diagram - Error Path (e.g., A2A Task Fails)

```mermaid
sequenceDiagram
    participant Orch as SAM Orchestrator
    participant Comp as A2AClientAgentComponent
    participant Action as A2AClientAction
    participant A2AClient as A2AClient Lib
    participant A2AServer as External A2A Agent Server

    Orch->>Comp: Invoke Action(skill_id, params, meta)
    Comp->>Action: invoke(params, meta)
    Action->>A2AClient: Prepare TaskSendParams
    Action->>A2AClient: send_task(TaskSendParams)
    A2AClient->>A2AServer: POST /a2a (JSON-RPC tasks/send)
    A2AServer-->>A2AClient: Process Task (State: SUBMITTED -> WORKING -> FAILED)
    A2AServer-->>A2AClient: HTTP Response (JSON-RPC result: Task object with state=FAILED, error message)
    A2AClient-->>Action: Return Task object
    Action->>Comp: Process Task result (detects FAILED state)
    Action-->>Comp: Return ActionResponse (success=false, message=error, error_info)
    Comp-->>Orch: Return ActionResponse (indicating failure)

    alt A2A Server Connection Error
        Orch->>Comp: Invoke Action(...)
        Comp->>Action: invoke(...)
        Action->>A2AClient: send_task(...)
        A2AClient->>A2AServer: POST /a2a
        Note right of A2AClient: Connection fails / Timeout
        A2AClient-->>Action: Raise Exception (e.g., ConnectionError)
        Action->>Comp: Catch Exception
        Action-->>Comp: Return ActionResponse (success=false, message="Failed to connect", error_info)
        Comp-->>Orch: Return ActionResponse (indicating failure)
    end
```

## Sequence Diagram - Input Required Path

```mermaid
sequenceDiagram
    participant Orch as SAM Orchestrator
    participant Comp as A2AClientAgentComponent
    participant Action as A2AClientAction
    participant InputHandler as a2a_input_handler.py
    participant Cache as Cache Service
    participant A2AClient as A2AClient Lib
    participant A2AServer as External A2A Agent Server

    %% Initial Request %%
    Orch->>Comp: Invoke Action(skill_id, params, meta{session_id})
    Comp->>Action: invoke(params, meta)
    Action->>A2AClient: Prepare TaskSendParams (new a2a_taskId, session_id)
    Action->>A2AClient: send_task(TaskSendParams)
    A2AClient->>A2AServer: POST /a2a (JSON-RPC tasks/send)
    A2AServer-->>A2AClient: Process Task (State: SUBMITTED -> WORKING -> INPUT_REQUIRED)
    A2AServer-->>A2AClient: HTTP Response (JSON-RPC result: Task object with state=INPUT_REQUIRED, agent_question_message)
    A2AClient-->>Action: Return Task object
    Action->>Comp: Process Task result (detects INPUT_REQUIRED)
    Action->>Comp: Generate unique sam_follow_up_id
    Action->>Cache: Store mapping: sam_follow_up_id -> a2a_taskId (with TTL)
    Action-->>Comp: Return ActionResponse (success=false/pending, message=agent_question, data={follow_up_id: sam_follow_up_id})
    Comp-->>Orch: Return ActionResponse (indicating input needed + follow_up_id)

    %% Orchestrator gets user input %%
    Note over Orch: Orchestrator/LLM gets user_response based on agent_question

    %% Follow-up Request %%
    Orch->>Comp: Invoke Action(provide_required_input, params={follow_up_id: sam_follow_up_id, user_response: ...}, meta)
    Comp->>InputHandler: handle_provide_required_input(comp, params, meta)
    InputHandler->>Cache: Retrieve a2a_taskId using sam_follow_up_id
    alt Follow-up ID Found
        Cache-->>InputHandler: Return a2a_taskId
        InputHandler->>A2AClient: Prepare TaskSendParams (using retrieved a2a_taskId, session_id, new message with user_response)
        InputHandler->>A2AClient: send_task(TaskSendParams)
        A2AClient->>A2AServer: POST /a2a (JSON-RPC tasks/send with existing a2a_taskId)
        A2AServer-->>A2AClient: Process Task (State: WORKING -> COMPLETED)
        A2AServer-->>A2AClient: HTTP Response (JSON-RPC result: Task object with state=COMPLETED, final_message/artifacts)
        A2AClient-->>InputHandler: Return Task object
        InputHandler->>Comp: Process final Task result (using Action._process_parts)
        InputHandler-->>Comp: Return ActionResponse (success=true, final message/files/data)
        Comp-->>Orch: Return ActionResponse
    else Follow-up ID Not Found / Expired
        Cache-->>InputHandler: Indicate ID not found
        InputHandler-->>Comp: Return ActionResponse (success=false, message="Follow-up context expired or invalid")
        Comp-->>Orch: Return ActionResponse
    end

```
