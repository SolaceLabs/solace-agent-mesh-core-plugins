# SAM A2A Client Plugin - Software Design

## 1. Overview

This document outlines the software design for the `sam-a2a-client` plugin. This plugin enables Solace Agent Mesh (SAM) to interact with external agents implementing the Agent-to-Agent (A2A) protocol. It acts as a client bridge, discovering A2A agent capabilities (skills) and exposing them as SAM actions.

## 2. Directory Structure

```
sam-a2a-client/
├── pyproject.toml
├── README.md
├── sam-a2a-client-architecture.md
├── sam-a2a-client-design.md  # This file
├── sam-a2a-agent-plan.md     # Reference
├── solace-agent-mesh-plugin.yaml
└── src/
    ├── __init__.py
    └── agents/
        └── a2a_client/
            ├── __init__.py
            ├── a2a_client_agent_component.py  # Main component class
            └── actions/
                ├── __init__.py
                └── a2a_client_action.py       # Dynamic action class
```

## 3. Key Files and Classes

*   **`src/agents/a2a_client/a2a_client_agent_component.py`**:
    *   **`A2AClientAgentComponent(BaseAgentComponent)`**:
        *   **Responsibilities:**
            *   Parses configuration (command, URL, auth, etc.).
            *   Manages the lifecycle of the external A2A agent process (if `a2a_server_command` is provided) using `subprocess.Popen`. Includes monitoring and restart logic.
            *   Connects to the A2A agent (launched or pre-existing) via its URL.
            *   Uses `A2ACardResolver` to fetch and parse the `AgentCard`. Handles connection errors and timeouts.
            *   Instantiates and holds the `A2AClient` instance, configuring it with the URL and any required authentication (initially bearer token).
            *   Iterates through `AgentCard.skills`. For each skill, creates an instance of `A2AClientAction`.
            *   Dynamically builds the `ActionList` for the component.
            *   Defines the static `provide_required_input` action.
            *   Handles cleanup (terminating the managed process).
            *   Provides access to the `A2AClient` instance for its actions.
            *   Manages state for `INPUT_REQUIRED` follow-ups using the SAM Cache Service.
*   **`src/agents/a2a_client/actions/a2a_client_action.py`**:
    *   **`A2AClientAction(Action)`**:
        *   **Responsibilities:**
            *   Initialized dynamically by `A2AClientAgentComponent` for a specific A2A `skill`.
            *   Stores the `skill.id` and a reference to the parent `A2AClientAgentComponent` (to access `A2AClient` and `CacheService`).
            *   Implements the `invoke(params, meta)` method:
                *   Retrieves `session_id` from `meta`.
                *   Maps SAM `params` (including resolving file URLs via `FileService`) to an A2A `Message` with appropriate `Parts` (TextPart, FilePart, DataPart). Assumes a primary 'prompt' parameter derived from `skill.description` or a generic one if parsing fails.
                *   Constructs `TaskSendParams` using the `session_id` and a newly generated `taskId`.
                *   Calls `A2AClient.send_task()` (synchronous).
                *   Handles the A2A `Task` response:
                    *   **If `state == COMPLETED`:** Processes `Task.status.message` and `Task.artifacts`. Concatenates `TextPart`s into `ActionResponse.message`. Saves `FilePart`s/Artifacts using `FileService` and adds URLs to `ActionResponse.files`. Maps `DataPart`s to `ActionResponse.data`. Returns `ActionResponse(success=True, ...)`.
                    *   **If `state == FAILED`:** Extracts error details. Returns `ActionResponse(success=False, message=error_message, error_info=...)`.
                    *   **If `state == INPUT_REQUIRED`:**
                        *   Generates a unique `sam_follow_up_id` (e.g., UUID).
                        *   Stores the mapping `{sam_follow_up_id: a2a_taskId}` in the Cache Service with a TTL (e.g., 5 minutes).
                        *   Extracts the agent's question from the A2A response message.
                        *   Returns `ActionResponse(success=False, message=agent_question, data={'follow_up_id': sam_follow_up_id}, status='INPUT_REQUIRED')` (or similar indication).
                    *   **Other states:** Handle appropriately (e.g., log warnings, potentially treat as errors).
                *   Catches exceptions during A2A communication (e.g., connection errors, timeouts) and returns appropriate error `ActionResponse`.

## 4. Configuration (`A2AClientAgentComponent`)

The component configuration (`component_config`) will include:

*   **`agent_name`** (String, Required): Unique name for this SAM agent instance (e.g., `crewai_image_agent`). Used in action names (`agent_name/skill_id`).
*   **`a2a_server_url`** (String, Required): The base URL of the target A2A agent (e.g., `http://localhost:10001`). Used for fetching the Agent Card and sending tasks.
*   **`a2a_server_command`** (String, Optional): The command line to launch the A2A agent process. If provided, the plugin manages the process. If omitted, the plugin connects to a pre-existing agent at `a2a_server_url`.
*   **`a2a_server_startup_timeout`** (Integer, Optional, Default: 30): Seconds to wait for the launched A2A agent to become responsive (checked by polling `/.well-known/agent.json`).
*   **`a2a_server_restart_on_crash`** (Boolean, Optional, Default: True): Whether to attempt restarting the managed A2A agent process if it terminates unexpectedly.
*   **`a2a_bearer_token`** (String, Optional): Bearer token to use for A2A requests if the Agent Card indicates bearer authentication.
*   **`input_required_ttl`** (Integer, Optional, Default: 300): Time-to-live in seconds for storing the `INPUT_REQUIRED` state in the cache.

Environment variables (e.g., `${A2A_IMAGE_AGENT_COMMAND}`, `${A2A_IMAGE_AGENT_URL}`, `${A2A_IMAGE_AGENT_TOKEN}`) will be used to populate these config values via the SAM config file.

## 5. Detailed Logic

### 5.1. `A2AClientAgentComponent` Initialization (`run` method)

1.  Read configuration values.
2.  **If `a2a_server_command` is provided:**
    *   Use `subprocess.Popen` to start the command. Store the process handle.
    *   Start a monitoring thread (if `a2a_server_restart_on_crash` is True) to check `process.poll()` and relaunch if needed. Log errors.
    *   Poll `a2a_server_url/.well-known/agent.json` using `requests` with retries and backoff until `a2a_server_startup_timeout`.
    *   If polling fails, log error, stop potential monitoring thread, terminate process (if possible), and raise an initialization error.
3.  **If `a2a_server_command` is NOT provided:**
    *   Poll `a2a_server_url/.well-known/agent.json` once to verify connectivity. If fails, raise error.
4.  **Fetch Agent Card:**
    *   Use `A2ACardResolver(a2a_server_url).get_agent_card()`. Store the `agent_card`. Handle potential errors.
5.  **Initialize `A2AClient`:**
    *   Check `agent_card.authentication` schemes.
    *   If bearer auth is listed and `a2a_bearer_token` is configured, create `A2AClient(agent_card, auth_token=a2a_bearer_token)`.
    *   Otherwise, create `A2AClient(agent_card)`. (Extend later for other auth types).
    *   Store the `a2a_client` instance.
6.  **Create Actions:**
    *   Initialize `self.action_list = ActionList(...)`.
    *   Iterate through `agent_card.skills`:
        *   For each `skill`, attempt to parse `skill.description` to infer parameters (simple initial approach: look for placeholders like `{param_name}`). If parsing fails or is complex, define a single generic parameter `prompt` (type: string, required: true).
        *   Create `A2AClientAction` instance: `A2AClientAction(skill=skill, component=self, inferred_params=...)`.
        *   Add the action: `self.action_list.add_action(action_instance)`.
    *   Define the static `provide_required_input` action:
        *   Name: `provide_required_input`.
        *   Params: `follow_up_id` (string, required), `user_response` (string, required), potentially `files` (list of file URLs, optional).
        *   Handler: A method within `A2AClientAgentComponent` (see section 5.3).
        *   Add this action to `self.action_list`.
7.  Update component description with agent name and discovered action names.
8.  Call `super().run()` to start the component's main loop (handling registration timers etc.).

### 5.2. `A2AClientAction.invoke` Logic

1.  Get `a2a_client` and `cache_service` from the parent component.
2.  Get `session_id` from `meta`. Generate a new `a2a_taskId` (UUID).
3.  **Map SAM `params` to A2A `Message.parts`:**
    *   Identify the main text prompt parameter (e.g., `prompt` or the primary inferred parameter). Create a `TextPart` for it.
    *   Identify any file parameters (e.g., a `files` list). For each file URL:
        *   Use `FileService.resolve_url(file_url)` to get file content (bytes) and metadata.
        *   Create a `FilePart` using the content and metadata. Handle potential resolution errors.
    *   (Future: Handle `DataPart` if skills require structured input).
    *   Assemble the `parts` list.
4.  Create `TaskSendParams` with `id=a2a_taskId`, `sessionId=session_id`, `message={'role': 'user', 'parts': parts}`, `acceptedOutputModes=["text", "image/*", "application/json"]` (or derive from skill?).
5.  **Call A2A Agent:**
    *   `try...except` block around the `a2a_client.send_task()` call.
    *   `response_task = a2a_client.send_task(task_send_params.model_dump())`
6.  **Process Response:**
    *   Check `response_task.status.state`.
    *   **If `COMPLETED`:**
        *   Initialize `response_message = ""`, `response_files = []`, `response_data = {}`.
        *   Process `response_task.status.message.parts` and `response_task.artifacts`:
            *   For `TextPart`: Append `part.text` to `response_message`.
            *   For `FilePart`: Use `FileService.upload_from_buffer(part.file.bytes, part.file.name, session_id)` to save the file. Add the returned file metadata (URL) to `response_files`.
            *   For `DataPart`: Merge `part.data` into `response_data`.
        *   Return `ActionResponse(success=True, message=response_message, files=response_files, data=response_data)`.
    *   **If `FAILED`:**
        *   Extract error from `response_task.status.message` or a dedicated error field if available.
        *   Return `ActionResponse(success=False, message=error_message, ...)`.
    *   **If `INPUT_REQUIRED`:**
        *   Generate `sam_follow_up_id = str(uuid.uuid4())`.
        *   `cache_service.set(f"a2a_follow_up:{sam_follow_up_id}", a2a_taskId, ttl=self.get_config('input_required_ttl'))`.
        *   Extract agent question from `response_task.status.message.parts` (assuming TextPart).
        *   Return `ActionResponse(success=False, message=agent_question, data={'follow_up_id': sam_follow_up_id}, status='INPUT_REQUIRED')`.
    *   **Other states:** Log warning, return error `ActionResponse`.
7.  **Catch Exceptions:** If `send_task` raised an exception (e.g., `requests.exceptions.ConnectionError`), return `ActionResponse(success=False, message="Failed to communicate with A2A agent", error_info=ErrorInfo(str(e)))`.

### 5.3. `provide_required_input` Action Handler (Method in `A2AClientAgentComponent`)

1.  Get parameters: `follow_up_id`, `user_response`, optional `files`.
2.  Get `a2a_client` and `cache_service`. Get `session_id` from `meta`.
3.  **Retrieve State:**
    *   `a2a_taskId = cache_service.get(f"a2a_follow_up:{follow_up_id}")`.
    *   If `a2a_taskId` is `None` (not found or expired): Return `ActionResponse(success=False, message="Invalid or expired follow-up ID.")`.
    *   Optionally, delete the cache entry now: `cache_service.delete(f"a2a_follow_up:{follow_up_id}")`.
4.  **Map Input to A2A `Message.parts`:** Similar to step 3 in 5.2, using `user_response` for `TextPart` and resolving `files` URLs for `FilePart`s.
5.  Create `TaskSendParams` using the *retrieved* `a2a_taskId`, the current `session_id`, and the new message parts.
6.  **Call A2A Agent:** Use `a2a_client.send_task()` again with these params.
7.  **Process Response:** Process the `response_task` exactly as in step 6 of 5.2 (handle `COMPLETED`, `FAILED`, or even another `INPUT_REQUIRED`). Return the resulting `ActionResponse`.
8.  Handle exceptions as in step 7 of 5.2.

## 6. Error Handling Summary

*   **Configuration Errors:** Validation during component initialization.
*   **Process Launch/Management Errors:** Logged, potentially trigger restarts. Failure to start/connect prevents component readiness.
*   **Agent Card Fetch Errors:** Logged, prevent component readiness.
*   **A2A Communication Errors (Connection, Timeout):** Caught by `A2AClientAction`, return error `ActionResponse`.
*   **A2A Task Failures (`FAILED` state):** Detected by `A2AClientAction`, return error `ActionResponse`.
*   **`INPUT_REQUIRED` State:** Handled via state caching and the `provide_required_input` action. Invalid/expired follow-up IDs result in an error `ActionResponse`.
*   **Internal Plugin Errors:** Standard Python exception handling, should ideally result in error `ActionResponse`.

## 7. State Management (`INPUT_REQUIRED`)

*   The SAM Core Cache Service (`self.cache_service`) is used.
*   Key format: `a2a_follow_up:<sam_follow_up_id>`
*   Value: `a2a_taskId` (String)
*   TTL: Configurable (`input_required_ttl`), defaults to 300 seconds.
*   The `provide_required_input` action retrieves the `a2a_taskId` using the provided `sam_follow_up_id` and then proceeds with the A2A call.
```