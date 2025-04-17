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

<inst>
Give your thoughts for this project based on the answers above. Feel free ask any additional questions or make any additional comments.
</inst>
