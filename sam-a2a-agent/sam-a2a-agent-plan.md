# SAM A2A Agent Plugin

## Overview

We are adding a new plugin to support wrapping an A2A agent to allow us to be able to bring an 
A2A agent into the SAM ecosystem. This will allow us to use the A2A agent in a SAM framework.

## Clarifying Questions

*   **Configuration:**
    *   What specific environment variables or configuration parameters should be mandatory vs. optional for launching and connecting to the A2A agent (e.g., `A2A_SERVER_COMMAND`, `A2A_SERVER_URL`, `A2A_SERVER_STARTUP_TIMEOUT`)?
    *   How should authentication mechanisms supported by A2A (e.g., API keys, bearer tokens specified in the Agent Card) be configured and passed from the SAM agent to the `A2AClient`?
*   **Process Management:**
    *   Should the SAM agent always launch and manage the lifecycle of the A2A agent process, or should it also support connecting to a pre-existing, externally managed A2A agent via its URL?
    *   If launching the process, how should errors during startup or runtime crashes of the A2A agent be handled? Should SAM attempt automatic restarts?
*   **Capability Mapping (Skills to Actions):**
    *   Is a direct 1:1 mapping of A2A `skill.id` to SAM `action.name` the desired approach?
    *   How should the input parameters for a SAM action be defined? Should they be dynamically generated based on the A2A skill's description, or should we assume a generic 'prompt' parameter for most skills initially?
    *   How should SAM action parameters (like text prompts, file URLs) be translated into the A2A `Message` structure with appropriate `Parts` (TextPart, FilePart, DataPart)? Will the `FileService` be used to resolve URLs for `FilePart`?
    *   How should the A2A response `Parts` (from the final message or artifacts) be mapped back to the SAM `ActionResponse` fields (`message`, `files`, `data`)?
*   **Streaming & Asynchronicity:**
    *   Should the initial version support A2A streaming (`tasks/sendSubscribe`) if the target agent's `AgentCard` indicates `capabilities.streaming: true`? Or should we start with only synchronous `tasks/send`?
    *   If streaming is supported, how should intermediate `TaskStatusUpdateEvent` or `TaskArtifactUpdateEvent` events be handled? Should they be ignored, logged, or somehow propagated back through SAM (which might be complex)?
*   **Task Lifecycle & State:**
    *   How should the SAM action handle an A2A task that returns with the state `INPUT_REQUIRED`? Should the action fail immediately with a message indicating more input is needed, or is there a more advanced pattern to consider? (Failing seems simpler initially).
    *   Should the A2A `sessionId` be directly mapped from the SAM `meta['session_id']` provided to the `invoke` method?
*   **Naming Conventions:**
    *   What is the preferred name for the plugin directory (e.g., `sam-a2a-client`, `sam-a2a-wrapper`)?
    *   What are the preferred names for the main component class (e.g., `A2AClientAgentComponent`) and the dynamically generated action class (e.g., `A2AClientAction`)?
