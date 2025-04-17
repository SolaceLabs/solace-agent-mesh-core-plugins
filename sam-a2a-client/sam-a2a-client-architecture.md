# SAM A2A Client Plugin Architecture

## High-Level Architecture Overview

The `sam-a2a-client` plugin allows Solace Agent Mesh (SAM) to interact with external agents that conform to the Agent-to-Agent (A2A) protocol. It acts as a bridge, enabling SAM to leverage the capabilities of A2A agents.

The core of the plugin is a SAM `BaseAgentComponent` (`A2AClientAgentComponent`). This component performs the following key functions:

1.  **Process Management (Optional):** It can launch and manage the lifecycle of an external A2A agent process based on a configured command (`A2A_SERVER_COMMAND`). It monitors this process and can attempt restarts upon failure.
2.  **Connection:** Alternatively, it can connect to a pre-existing, externally managed A2A agent via a configured URL (`A2A_SERVER_URL`).
3.  **Discovery:** Upon connection (or successful launch), it fetches the target A2A agent's `AgentCard` from its `/.well-known/agent.json` endpoint.
4.  **Capability Mapping:** It parses the `skills` listed in the `AgentCard` and dynamically creates corresponding SAM `Action` instances (`A2AClientAction`). Each SAM action maps directly to an A2A skill, using the `skill.id` as the action name.
5.  **Invocation Handling:** When the SAM orchestrator invokes one of these dynamic actions, the `A2AClientAction` translates the SAM action parameters into an A2A `Task` request.
6.  **A2A Communication:** It uses the `A2AClient` library (from the A2A reference implementation) to send the `Task` request (via `tasks/send`) to the external A2A agent.
7.  **Response Handling:** It receives the A2A `Task` response, processes the result (including handling different `Parts` like text, files, data, and artifacts), and translates it back into a SAM `ActionResponse`.
8.  **State Management (`INPUT_REQUIRED`):** It handles the A2A `INPUT_REQUIRED` state by storing the A2A `taskId`, returning a specific response to SAM with a follow-up ID, and providing a dedicated action (`provide_required_input`) for SAM to submit the required information back to the correct A2A task.

This allows the SAM orchestrator and LLM to interact with A2A agents as if they were native SAM agents, abstracting the underlying A2A protocol details.

## Component List

*   **`A2AClientAgentComponent`**: The main SAM component derived from `BaseAgentComponent`. Manages the connection/process, discovers skills, and holds the `A2AClient` instance. It also defines the static `provide_required_input` action.
*   **`A2AClientAction`**: A dynamically created SAM `Action` class. An instance is created for each discovered A2A `skill`. It handles the invocation logic for a specific skill, translating SAM requests to A2A tasks and A2A responses back to SAM `ActionResponse`.
*   **`A2AClient` (External Library)**: From the `google/A2A` common library. Used to handle the actual HTTP/JSON-RPC communication with the A2A agent server.
*   **`A2ACardResolver` (External Library)**: From the `google/A2A` common library. Used to fetch and parse the `AgentCard`.
*   **`FileService` (SAM Core)**: Used to resolve file URLs provided in SAM action parameters into bytes for A2A `FilePart` and to save incoming A2A `FilePart` or `Artifacts` as files accessible via URL in the `ActionResponse`.
*   **Cache Service (SAM Core)**: Used to store the mapping between `sam_follow_up_id` and A2A `taskId` when handling the `INPUT_REQUIRED` state, potentially with a TTL.

## Component Diagram

```mermaid
graph TD
    subgraph SAM Framework
        Orchestrator --> A2AClientAgentComponent;
        A2AClientAgentComponent --> ActionList[Action List];
        ActionList --> A2AClientAction["A2AClientAction (Dynamic)"];
        ActionList --> ProvideInputAction["provide_required_input (Static)"];
        A2AClientAgentComponent -- Uses --> CacheService[(Cache Service)];
        A2AClientAction -- Uses --> FileService[(File Service)];
        ProvideInputAction -- Uses --> FileService;
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

    A2AClientAgentComponent -- Manages/Connects --> A2AAgentServer;
    A2AClientAgentComponent -- Uses --> A2ACardResolverLib;
    A2AClientAgentComponent -- Creates/Holds --> A2AClientLib;

    A2AClientAction -- Uses --> A2AClientLib;
    ProvideInputAction -- Uses --> A2AClientLib;

    A2ACardResolverLib -- Fetches --> AgentCardEndpoint;
    A2AClientLib -- Sends/Receives --> A2AEndpoint;

    style SAM Framework fill:#f9f,stroke:#333,stroke-width:2px;
    style External A2A Agent Process fill:#ccf,stroke:#333,stroke-width:2px;
    style A2A Common Library fill:#cfc,stroke:#333,stroke-width:2px;

```

## Sequence Diagram - Happy Path (Synchronous `tasks/send`)

```mermaid
sequenceDiagram
    participant Orch as SAM Orchestrator
    participant Plugin as A2AClientAgentComponent
    participant Action as A2AClientAction
    participant A2AClient as A2AClient Lib
    participant A2AServer as External A2A Agent Server

    Note over Orch, A2AServer: Initial Setup: Plugin launches/connects to A2AServer, fetches AgentCard, creates Action.

    Orch->>Plugin: Invoke Action(skill_id, params, meta)
    Plugin->>Action: invoke(params, meta)
    Action->>Plugin: Get A2AClient instance
    Action->>A2AClient: Prepare TaskSendParams (new taskId, sessionId, message parts)
    Note right of Action: Map SAM params to A2A Parts (using FileService if needed)
    Action->>A2AClient: send_task(TaskSendParams)
    A2AClient->>A2AServer: POST /a2a (JSON-RPC tasks/send)
    A2AServer-->>A2AClient: Process Task (State: SUBMITTED -> WORKING -> COMPLETED)
    A2AServer-->>A2AClient: HTTP Response (JSON-RPC result: Task object with state=COMPLETED, message/artifacts)
    A2AClient-->>Action: Return Task object
    Action->>Plugin: Process Task result
    Note right of Action: Map A2A Parts/Artifacts to ActionResponse (using FileService if needed)
    Action-->>Plugin: Return ActionResponse (success=true, message, files, data)
    Plugin-->>Orch: Return ActionResponse
```

## Sequence Diagram - Error Path (e.g., A2A Task Fails)

```mermaid
sequenceDiagram
    participant Orch as SAM Orchestrator
    participant Plugin as A2AClientAgentComponent
    participant Action as A2AClientAction
    participant A2AClient as A2AClient Lib
    participant A2AServer as External A2A Agent Server

    Orch->>Plugin: Invoke Action(skill_id, params, meta)
    Plugin->>Action: invoke(params, meta)
    Action->>A2AClient: Prepare TaskSendParams
    Action->>A2AClient: send_task(TaskSendParams)
    A2AClient->>A2AServer: POST /a2a (JSON-RPC tasks/send)
    A2AServer-->>A2AClient: Process Task (State: SUBMITTED -> WORKING -> FAILED)
    A2AServer-->>A2AClient: HTTP Response (JSON-RPC result: Task object with state=FAILED, error message)
    A2AClient-->>Action: Return Task object
    Action->>Plugin: Process Task result (detects FAILED state)
    Action-->>Plugin: Return ActionResponse (success=false, message=error, error_info)
    Plugin-->>Orch: Return ActionResponse (indicating failure)

    alt A2A Server Connection Error
        Orch->>Plugin: Invoke Action(...)
        Plugin->>Action: invoke(...)
        Action->>A2AClient: send_task(...)
        A2AClient->>A2AServer: POST /a2a
        Note right of A2AClient: Connection fails / Timeout
        A2AClient-->>Action: Raise Exception (e.g., ConnectionError)
        Action->>Plugin: Catch Exception
        Action-->>Plugin: Return ActionResponse (success=false, message="Failed to connect", error_info)
        Plugin-->>Orch: Return ActionResponse (indicating failure)
    end
```

## Sequence Diagram - Input Required Path

```mermaid
sequenceDiagram
    participant Orch as SAM Orchestrator
    participant Plugin as A2AClientAgentComponent
    participant Action as A2AClientAction
    participant Cache as Cache Service
    participant A2AClient as A2AClient Lib
    participant A2AServer as External A2A Agent Server

    %% Initial Request %%
    Orch->>Plugin: Invoke Action(skill_id, params, meta{session_id})
    Plugin->>Action: invoke(params, meta)
    Action->>A2AClient: Prepare TaskSendParams (new a2a_taskId, session_id)
    Action->>A2AClient: send_task(TaskSendParams)
    A2AClient->>A2AServer: POST /a2a (JSON-RPC tasks/send)
    A2AServer-->>A2AClient: Process Task (State: SUBMITTED -> WORKING -> INPUT_REQUIRED)
    A2AServer-->>A2AClient: HTTP Response (JSON-RPC result: Task object with state=INPUT_REQUIRED, agent_question_message)
    A2AClient-->>Action: Return Task object
    Action->>Plugin: Process Task result (detects INPUT_REQUIRED)
    Action->>Plugin: Generate unique sam_follow_up_id
    Action->>Cache: Store mapping: sam_follow_up_id -> a2a_taskId (with TTL)
    Action-->>Plugin: Return ActionResponse (success=false/pending, message=agent_question, data={follow_up_id: sam_follow_up_id})
    Plugin-->>Orch: Return ActionResponse (indicating input needed + follow_up_id)

    %% Orchestrator gets user input %%
    Note over Orch: Orchestrator/LLM gets user_response based on agent_question

    %% Follow-up Request %%
    Orch->>Plugin: Invoke Action(provide_required_input, params={follow_up_id: sam_follow_up_id, user_response: ...}, meta)
    Plugin->>Plugin: Handle provide_required_input action
    Plugin->>Cache: Retrieve a2a_taskId using sam_follow_up_id
    alt Follow-up ID Found
        Cache-->>Plugin: Return a2a_taskId
        Plugin->>A2AClient: Prepare TaskSendParams (using retrieved a2a_taskId, session_id, new message with user_response)
        Plugin->>A2AClient: send_task(TaskSendParams)
        A2AClient->>A2AServer: POST /a2a (JSON-RPC tasks/send with existing a2a_taskId)
        A2AServer-->>A2AClient: Process Task (State: WORKING -> COMPLETED)
        A2AServer-->>A2AClient: HTTP Response (JSON-RPC result: Task object with state=COMPLETED, final_message/artifacts)
        A2AClient-->>Plugin: Return Task object
        Plugin->>Plugin: Process final Task result
        Plugin-->>Orch: Return ActionResponse (success=true, final message/files/data)
    else Follow-up ID Not Found / Expired
        Cache-->>Plugin: Indicate ID not found
        Plugin-->>Orch: Return ActionResponse (success=false, message="Follow-up context expired or invalid")
    end

```
