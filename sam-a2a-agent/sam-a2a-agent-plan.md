# SAM A2A Agent Plugin

## Overview

We are adding a new plugin to support wrapping an A2A agent to allow us to be able to bring an 
A2A agent into the SAM ecosystem. This will allow us to use the A2A agent in a SAM framework.

## Clarifying Questions

*   **Configuration:**
    *   What specific environment variables or configuration parameters should be mandatory vs. optional for launching and connecting to the A2A agent (e.g., `A2A_SERVER_COMMAND`, `A2A_SERVER_URL`, `A2A_SERVER_STARTUP_TIMEOUT`)?
    - Just do your best to suggest reasonable defaults for now. We can always change them later.

    *   How should authentication mechanisms supported by A2A (e.g., API keys, bearer tokens specified in the Agent Card) be configured and passed from the SAM agent to the `A2AClient`?
    - We need to support what is in the Agent Card. We can start with a simple bearer token and then add more complex auth later.

*   **Process Management:**
    *   Should the SAM agent always launch and manage the lifecycle of the A2A agent process, or should it also support connecting to a pre-existing, externally managed A2A agent via its URL?
    - It should support both

    *   If launching the process, how should errors during startup or runtime crashes of the A2A agent be handled? Should SAM attempt automatic restarts?
    - We should try to restart the A2A agent if it crashes. We can add a config option to disable this if needed. We should have good logging around this so we can see what is going on.

*   **Capability Mapping (Skills to Actions):**
    *   Is a direct 1:1 mapping of A2A `skill.id` to SAM `action.name` the desired approach?
    - We should do a direct mapping. In the orchestrator any possible naming collisions shouldn't be a problem because of the agent's name should be part of the action name.

    *   How should the input parameters for a SAM action be defined? Should they be dynamically generated based on the A2A skill's description, or should we assume a generic 'prompt' parameter for most skills initially?
    - They should be dynamically generated based on the A2A skill's description. We can start with a generic 'prompt' parameter for most skills, but we should try to get the A2A agent to provide us with the input parameters.

    *   How should SAM action parameters (like text prompts, file URLs) be translated into the A2A `Message` structure with appropriate `Parts` (TextPart, FilePart, DataPart)? Will the `FileService` be used to resolve URLs for `FilePart`?
    - Yes, the FileService will be used to store the file data before moving into SAM and it will be used to resolve URLs for `FilePart`. We should also be able to handle the other types of parts as well.

    *   How should the A2A response `Parts` (from the final message or artifacts) be mapped back to the SAM `ActionResponse` fields (`message`, `files`, `data`)?
    - This plugin needs to receive the parts and create a single message that is a concatenation of all the parts. The plugin should also be able to handle the other types of parts as well.

*   **Streaming & Asynchronicity:**
    *   Should the initial version support A2A streaming (`tasks/sendSubscribe`) if the target agent's `AgentCard` indicates `capabilities.streaming: true`? Or should we start with only synchronous `tasks/send`?
    - We need to be able to support all A2A agents. Our plugin will not be streaming response back through the ActionResponse, so if A2A supports never requesting streaming then we should just do that. 

    *   If streaming is supported, how should intermediate `TaskStatusUpdateEvent` or `TaskArtifactUpdateEvent` events be handled? Should they be ignored, logged, or somehow propagated back through SAM (which might be complex)?
    - Streaming will not be used

*   **Task Lifecycle & State:**
    *   How should the SAM action handle an A2A task that returns with the state `INPUT_REQUIRED`? Should the action fail immediately with a message indicating more input is needed, or is there a more advanced pattern to consider? (Failing seems simpler initially).
    - We should just create an ActionResponse with the requested input and a unique id that the orchestrator will return to us through a action call specific to providing input required responses. The plugin will use that id to retrieve the state so that it can send the response to the A2A agent.
    - SAM will need to be sure to be able to store that id across user interactions, but that is outside the scope of the plugin

    *   Should the A2A `sessionId` be directly mapped from the SAM `meta['session_id']` provided to the `invoke` method?
    - Maybe. Use your best judgement here

*   **Naming Conventions:**
    *   What is the preferred name for the plugin directory (e.g., `sam-a2a-client`, `sam-a2a-wrapper`)?
    - `sam-a2a-client`

    *   What are the preferred names for the main component class (e.g., `A2AClientAgentComponent`) and the dynamically generated action class (e.g., `A2AClientAction`)?
    - Yes

## Thoughts based on answers above

Based on the answers, here's a summary of the approach and potential considerations:

1.  **Core Functionality:** The plugin (`sam-a2a-client`) will contain a component (`A2AClientAgentComponent`) that can either launch an A2A agent process (via `A2A_SERVER_COMMAND`) or connect to a running one (via `A2A_SERVER_URL`). It will fetch the `AgentCard`, discover `skills`, and create corresponding SAM `Actions` (`A2AClientAction`) using the `skill.id` as the action name.
2.  **Process Management:** If launching, the component will monitor the process and attempt restarts on crashes (configurable). Robust logging is key here. Need to define clear config logic to differentiate launch vs. connect modes.
3.  **Action Invocation:**
    *   Input parameters for SAM actions will ideally be derived from A2A skill descriptions, falling back to a generic `prompt` if necessary. This dynamic generation needs a defined strategy (e.g., simple keyword parsing in the description?).
    *   SAM action parameters (text, file URLs) will be mapped to A2A `Message` `Parts`. `FileService` will resolve URLs to bytes for `FilePart`.
    *   A2A response `Parts` will be processed: `TextPart` concatenated into `ActionResponse.message`, `FilePart` saved via `FileService` and URL added to `ActionResponse.files`, `DataPart` mapped to `ActionResponse.data`. Handling multiple/mixed parts needs care.
4.  **Authentication:** Initial support for bearer tokens is required. The component will check the `AgentCard` and use a configured token (e.g., `A2A_BEARER_TOKEN`) if needed.
5.  **Streaming:** The plugin will *not* use A2A streaming (`tasks/sendSubscribe`) initially. It will rely solely on synchronous `tasks/send`. **Crucial Assumption:** We assume all A2A agents, even those advertising streaming capabilities, *must* also support the basic `tasks/send` method. This needs verification against the A2A spec or common practice. If an agent *only* supports streaming, this plugin won't work with it.
6.  **`INPUT_REQUIRED` Handling:** This is the most complex interaction. The plugin will adopt a stateful approach:
    *   On `INPUT_REQUIRED`, the `A2AClientAction`'s `invoke` method will:
        *   Store the A2A `taskId` internally (e.g., in component KV store or memory dict).
        *   Generate a unique `sam_follow_up_id`.
        *   Map the `sam_follow_up_id` to the A2A `taskId`.
        *   Return an `ActionResponse` containing the agent's question (from the A2A response message) and the `sam_follow_up_id`. This response should clearly signal that further input is needed (e.g., `success=False`, specific status field?).
    *   A new, dedicated SAM action (e.g., `provide_required_input`) must be defined within `A2AClientAgentComponent`.
    *   This action will accept `sam_follow_up_id` and the `user_response` as parameters.
    *   Its handler will look up the A2A `taskId` using the `sam_follow_up_id`, construct the follow-up A2A `tasks/send` request, send it, and process the subsequent A2A response (returning a final `ActionResponse` to the orchestrator).
7.  **Session ID:** Mapping SAM `meta['session_id']` directly to A2A `sessionId` seems reasonable and standard practice.
8.  **Error Handling:** Needs to be robust, covering process issues, connection problems, A2A task failures (`TaskState.FAILED`), validation errors, and internal plugin errors. Map errors clearly in the `ActionResponse`.

**Potential Challenges/Open Questions:**

*   **Dynamic Parameter Generation:** Defining a reliable method to parse skill descriptions into SAM action parameters might be difficult. The fallback to a generic `prompt` is essential.
*   **State Management for `INPUT_REQUIRED`:** Needs careful implementation regarding storage (memory vs. KV store), TTL/cleanup of pending states, and handling potential errors if a `sam_follow_up_id` is invalid or expired.
- the cache service can be used with TTL
*   **Handling Diverse `Parts`:** Defining the exact mapping logic for complex A2A responses (multiple parts, different types) to a single SAM `ActionResponse`.
*   **Authentication Expansion:** Planning for how to add support for other auth schemes beyond bearer tokens later.
*   **A2A Artifacts:** Clarify how A2A `Artifacts` (distinct from the final `message`) should be handled. Should they also be mapped to `ActionResponse.files` or `ActionResponse.data`?
- Files

Overall, the plan is feasible, leveraging existing patterns (`sam-mcp-server`) and A2A libraries. The `INPUT_REQUIRED` state management and dynamic parameter generation are the main areas requiring careful design.

