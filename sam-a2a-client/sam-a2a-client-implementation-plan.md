# SAM A2A Client Plugin - Implementation Plan

This document provides a step-by-step plan for implementing the `sam-a2a-client` plugin, based on the design document. Each step includes implementation details and suggested testing approaches.

**Assumptions:**

*   The `google/A2A` common library (`common.client`, `common.types`) is accessible within the Python environment. Configuration in `pyproject.toml` needs to be finalized for this.
*   Core SAM services (`BaseAgentComponent`, `Action`, `ActionList`, `ActionResponse`, `FileService`, `CacheService`, logging) are available.

---

Coding guidelines:

All code must follow Google's Python style guide (PEP 8). Use `black` for formatting and `mypy` for type checking. Ensure all new code is covered by unit tests.


**Phase 1: Project Setup and Core Component Structure**

**Step 1.1: Create Project Structure and Basic Files**

*   **1.1.1 Action:** Create the directory structure as defined in the design document (`sam-a2a-client/`, `src/`, `src/agents/`, etc.).
*   **1.1.2 Action:** Create initial `pyproject.toml`, `README.md`, `solace-agent-mesh-plugin.yaml`, `src/__init__.py`, `src/agents/__init__.py`, `src/agents/a2a_client/__init__.py`, `src/agents/a2a_client/actions/__init__.py`. Populate them based on the design doc and previous examples.
    *   *`pyproject.toml`*: Define project metadata, dependencies (including `requests` and placeholder/method for `a2a-common`).
    *   *`README.md`*: Basic overview, installation placeholder, configuration overview.
    *   *`solace-agent-mesh-plugin.yaml`*: Define the `a2a_client` agent type and point to the config template (to be created later).
*   **1.1.3 Testing:** None for this step (structure only).

**Step 1.2: Define `A2AClientAgentComponent` Skeleton**

*   **1.2.1 Action:** In `a2a_client_agent_component.py`, create the `A2AClientAgentComponent` class inheriting from `BaseAgentComponent`.
*   **1.2.2 Action:** Define the `info` class variable, copying from `base_agent_info` and adding/updating the A2A-specific configuration parameters as defined in the design doc (agent_name, a2a_server_url, etc.).
*   **1.2.3 Action:** Implement the `__init__` method:
    *   Call `super().__init__()`.
    *   Read configuration parameters using `self.get_config()` and store them as instance variables (e.g., `self.agent_name`, `self.a2a_server_url`).
    *   Initialize instance variables for state: `self.a2a_process = None`, `self.monitor_thread = None`, `self.stop_monitor = threading.Event()`, `self.agent_card = None`, `self.a2a_client = None`, `self.file_service = FileService()`, `self.cache_service = kwargs.get("cache_service")`, `self._initialized = threading.Event()`.
    *   Initialize `self.action_list = ActionList([], agent=self, config_fn=self.get_config)`.
    *   Add basic logging for initialization start.
*   **1.2.4 Action:** Implement a basic `run` method that calls `super().run()` (actual initialization logic will be added later).
*   **1.2.5 Action:** Implement a basic `stop_component` method (placeholder for process termination later).
*   **1.2.6 Testing:**
    *   Unit Test: Test that `__init__` correctly reads and stores configuration values (using mock config).
    *   Unit Test: Test that `info` dictionary is correctly defined.

**Step 1.3: Define `A2AClientAction` Skeleton**

*   **1.3.1 Action:** In `a2a_client_action.py`, create the `A2AClientAction` class inheriting from `Action`.
*   **1.3.2 Action:** Implement the `__init__` method:
    *   Accept `skill: AgentSkill`, `component: A2AClientAgentComponent`, and `inferred_params: List[Dict]` as arguments.
    *   Store `skill` and `component` as instance variables.
    *   Construct the `action_definition` dictionary for the `super().__init__()` call:
        *   `name`: Use `skill.id`.
        *   `prompt_directive`: Use `skill.description`.
        *   `params`: Use `inferred_params` (initially, this might just be the generic 'prompt' param).
        *   `required_scopes`: Define as `[f"{component.agent_name}:{skill.id}:execute"]`.
    *   Call `super().__init__(action_definition, agent=component, config_fn=component.get_config)`.
*   **1.3.3 Action:** Implement a placeholder `invoke(self, params: Dict, meta: Dict) -> ActionResponse` method that returns a simple "Not Implemented" error response.
*   **1.3.4 Testing:**
    *   Unit Test: Test that `__init__` correctly constructs the `action_definition` based on a mock `AgentSkill` and parameters.

---

**Phase 2: A2A Connection and Discovery**

**Step 2.1: Implement Process Management (Launch Mode)**

*   **2.1.1 Action:** In `A2AClientAgentComponent`, create a private method `_launch_a2a_process()`.
    *   Use `subprocess.Popen` to start `self.a2a_server_command` (consider `shell=True` implications or splitting the command). Store the process handle in `self.a2a_process`. Handle potential `FileNotFoundError` or other launch exceptions.
*   **2.1.2 Action:** Create a private method `_monitor_a2a_process()`.
    *   This method will run in a separate thread (`self.monitor_thread`).
    *   Loop while `not self.stop_monitor.is_set()`:
        *   Check `self.a2a_process.poll()`.
        *   If the process terminated unexpectedly (`returncode` is not None and not 0):
            *   Log an error.
            *   If `self.restart_on_crash` is True, attempt to relaunch using `_launch_a2a_process()` after a short delay. Log success/failure of restart.
            *   If restart fails repeatedly, maybe stop trying after N attempts.
        *   Sleep for a few seconds.
*   **2.1.3 Action:** Update `stop_component` to set `self.stop_monitor.set()`, terminate `self.a2a_process` (e.g., `self.a2a_process.terminate()`, `self.a2a_process.wait()`), and join `self.monitor_thread`.
*   **2.1.4 Testing:**
    *   Integration Test (Difficult without a dummy process): Test `_launch_a2a_process` can start a simple external script. Test `stop_component` terminates it. Mock `subprocess.Popen` for finer unit tests if needed.
    *   Unit Test: Test the logic within `_monitor_a2a_process` by mocking `self.a2a_process.poll()` to simulate crashes and verify restart attempts (or lack thereof based on config).

**Step 2.2: Implement Agent Readiness Check**

*   **2.2.1 Action:** In `A2AClientAgentComponent`, create a private method `_wait_for_agent_ready()`.
    *   Calculate deadline (`time.time() + self.startup_timeout`).
    *   Loop until deadline:
        *   Try fetching `self.a2a_server_url + "/.well-known/agent.json"` using `requests.get()`.
        *   If successful (status 200), return `True`.
        *   If connection error or non-200 status, log warning and sleep briefly (e.g., 1 second).
        *   Handle `requests.exceptions.RequestException`.
    *   If loop finishes without success, return `False`.
*   **2.2.2 Testing:**
    *   Unit Test: Mock `requests.get` to simulate different scenarios: immediate success, eventual success, persistent failure, connection errors. Verify return value and timeout behavior.

**Step 2.3: Implement Agent Card Fetching and Client Initialization**

*   **2.3.1 Action:** In `A2AClientAgentComponent`, create a private method `_initialize_a2a_connection()`. This will be called by `run`.
    *   **If `self.a2a_server_command`:**
        *   Call `_launch_a2a_process()`.
        *   Call `_wait_for_agent_ready()`. If it returns `False`, raise `TimeoutError`.
        *   If `self.restart_on_crash`, start the `_monitor_a2a_process` in `self.monitor_thread`.
    *   **Else (connecting to existing):**
        *   Call `_wait_for_agent_ready()` once (with a shorter timeout?). If `False`, raise `ConnectionError`.
    *   **Fetch Card:**
        *   `resolver = A2ACardResolver(self.a2a_server_url)`
        *   `self.agent_card = await resolver.get_agent_card()` (Need to run this async or adapt A2A lib if possible, or use `requests` directly if `A2ACardResolver` is strictly async). *Correction: A2AClient likely handles sync fetch, check library.* If `A2ACardResolver` is async only, might need `asyncio.run()` or adapt component structure. *Assume sync fetch for now.* Handle exceptions.
    *   **Initialize Client:**
        *   Check `self.agent_card.authentication`.
        *   If bearer required and `self.bearer_token` exists: `self.a2a_client = A2AClient(self.agent_card, auth_token=self.bearer_token)`
        *   Else: `self.a2a_client = A2AClient(self.agent_card)`
        *   Handle case where `self.a2a_client` fails to initialize.
    *   Log success.
*   **2.3.2 Action:** Update `run` to call `_initialize_a2a_connection()`.
*   **2.3.3 Testing:**
    *   Integration Test: Test connecting to a *real* simple A2A server (if available) or mock the `/agent.json` endpoint. Verify `agent_card` and `a2a_client` are populated.
    *   Unit Test: Mock `A2ACardResolver` and `A2AClient` constructors. Test logic for launch vs. connect modes. Test auth token handling. Test error handling for connection/fetch failures.

---

**Phase 3: Dynamic Action Creation and Basic Invocation**

**Step 3.1: Implement Dynamic Parameter Inference (Simple)**

*   **3.1.1 Action:** In `A2AClientAgentComponent`, create a helper method `_infer_params_from_skill(skill: AgentSkill) -> List[Dict]`.
    *   *Initial Simple Logic:* Always return `[{ "name": "prompt", "desc": "The user request or prompt for the agent.", "type": "string", "required": True }]`.
    *   *Future Enhancement:* Attempt to parse `skill.description` or look for a structured `parameters` field (if added to A2A spec/AgentCard) to create more specific parameters.
*   **3.1.2 Testing:**
    *   Unit Test: Test the simple logic returns the generic 'prompt' parameter.

**Step 3.2: Implement Action Creation Logic**

*   **3.2.1 Action:** In `A2AClientAgentComponent`, create `_create_actions()`. Call this after `_initialize_a2a_connection` in `run`.
    *   Check if `self.agent_card` and `self.agent_card.skills` exist.
    *   Loop `for skill in self.agent_card.skills:`
        *   `inferred_params = self._infer_params_from_skill(skill)`
        *   `action = A2AClientAction(skill=skill, component=self, inferred_params=inferred_params)`
        *   `self.action_list.add_action(action)`
    *   Define and add the static `provide_required_input` action (handler method to be implemented later).
        *   `provide_input_action = Action(...)` # Define params: follow_up_id, user_response, files
        *   Set its handler: `provide_input_action.set_handler(self._handle_provide_required_input)`
        *   `self.action_list.add_action(provide_input_action)`
    *   Update `self.info['description']` to include the list of discovered action names.
*   **3.2.2 Testing:**
    *   Unit Test: Provide a mock `AgentCard` with skills. Verify that `_create_actions` populates `self.action_list` with the correct number of `A2AClientAction` instances and the static `provide_required_input` action. Check action names and parameters.

**Step 3.3: Implement `A2AClientAction.invoke` - Request Mapping**

*   **3.3.1 Action:** In `A2AClientAction.invoke`:
    *   Get `a2a_client`, `cache_service`, `file_service` from `self.component`. Check they exist.
    *   Get `session_id` from `meta`. Generate `a2a_taskId = str(uuid.uuid4())`.
    *   Create `parts = []`.
    *   Find the main text prompt in `params` (e.g., `params['prompt']`). Add `parts.append(TextPart(text=prompt_text))`. Handle missing prompt.
    *   Check for a `files` parameter in `params` (expecting a list of URLs).
        *   Loop through file URLs:
            *   `try...except` block for file resolution.
            *   `resolved_file = self.component.file_service.resolve_url(file_url)` (This needs to return bytes and metadata).
            *   If successful, `parts.append(FilePart(file=FileContent(bytes=resolved_file.bytes, name=resolved_file.name, mimeType=resolved_file.mime_type)))`.
            *   If resolution fails, log error, potentially add an error message to the response or fail the action.
    *   Create `a2a_message = A2AMessage(role="user", parts=parts)`.
    *   Create `task_params = TaskSendParams(id=a2a_taskId, sessionId=session_id, message=a2a_message, acceptedOutputModes=["text", "image/*", "application/json"])`.
    *   Store `task_params` for the next step.
*   **3.3.2 Testing:**
    *   Unit Test: Test mapping various `params` (text only, text + valid file URL, text + invalid file URL) to `TaskSendParams`. Mock `FileService.resolve_url`. Verify correct `Parts` are created.

**Step 3.4: Implement `A2AClientAction.invoke` - Basic A2A Call (Happy Path COMPLETED)**

*   **3.4.1 Action:** Continue in `A2AClientAction.invoke`:
    *   Wrap the call in `try...except Exception as e:`.
    *   `response_task: Task = self.component.a2a_client.send_task(task_params.model_dump())`
    *   **If `response_task.status.state == TaskState.COMPLETED`:**
        *   *(Response mapping in next step)* - For now, just return `ActionResponse(success=True, message="A2A Task Completed (Processing TBD)")`.
    *   **Else (other states for now):**
        *   Return `ActionResponse(success=False, message=f"A2A Task ended with unexpected state: {response_task.status.state}")`.
    *   **In `except` block:**
        *   Log the error `e`.
        *   Return `ActionResponse(success=False, message="Failed to communicate with A2A agent", error_info=ErrorInfo(str(e)))`.
*   **3.4.2 Testing:**
    *   Integration-like Test: Mock `self.component.a2a_client.send_task`.
        *   Test case where mock returns a `Task` with `state=COMPLETED`. Verify `invoke` returns success.
        *   Test case where mock returns a `Task` with another state (e.g., `WORKING`). Verify `invoke` returns failure (for now).
        *   Test case where mock raises `ConnectionError`. Verify `invoke` catches it and returns the connection error response.

---

**Phase 4: Response Handling and State Management**

**Step 4.1: Implement `A2AClientAction.invoke` - Response Mapping (COMPLETED)**

*   **4.1.1 Action:** Enhance the `if response_task.status.state == TaskState.COMPLETED:` block in `A2AClientAction.invoke`:
    *   Initialize `response_message = ""`, `response_files = []`, `response_data = {}`.
    *   Define a helper function `process_parts(parts: List[Any])` inside `invoke` or as a private method:
        *   Iterate through `parts`:
            *   If `TextPart`, append `part.text` to `response_message` (add newline if needed).
            *   If `FilePart`, use `self.component.file_service.upload_from_buffer(...)` to save `part.file.bytes`. Add the result (file metadata dict) to `response_files`. Handle upload errors.
            *   If `DataPart`, merge `part.data` into `response_data` (e.g., `response_data.update(part.data)`).
    *   Call `process_parts` for `response_task.status.message.parts` if the message exists.
    *   Call `process_parts` for parts within each artifact in `response_task.artifacts` if artifacts exist.
    *   Return `ActionResponse(success=True, message=response_message.strip(), files=response_files, data=response_data)`.
*   **4.1.2 Testing:**
    *   Unit Test: Create mock `Task` objects with `state=COMPLETED` and various combinations of `Parts` (text, file, data) in `status.message` and `artifacts`. Mock `FileService.upload_from_buffer`. Verify that `invoke` correctly populates the `message`, `files`, and `data` fields of the `ActionResponse`.

**Step 4.2: Implement `A2AClientAction.invoke` - Error Handling (FAILED)**

*   **4.2.1 Action:** Add specific handling for `elif response_task.status.state == TaskState.FAILED:` in `A2AClientAction.invoke`:
    *   Try to extract an error message, e.g., from `response_task.status.message.parts[0].text` if available. Default to a generic failure message.
    *   Return `ActionResponse(success=False, message=f"A2A Task Failed: {error_message}", error_info=ErrorInfo(details_if_any))`.
*   **4.2.2 Testing:**
    *   Unit Test: Mock `send_task` to return a `Task` with `state=FAILED` and an error message. Verify `invoke` returns the correct error `ActionResponse`.

**Step 4.3: Implement `A2AClientAction.invoke` - State Handling (INPUT_REQUIRED)**

*   **4.3.1 Action:** Add specific handling for `elif response_task.status.state == TaskState.INPUT_REQUIRED:` in `A2AClientAction.invoke`:
    *   Check if `self.component.cache_service` is available. If not, return an error `ActionResponse` ("INPUT_REQUIRED not supported without CacheService").
    *   Generate `sam_follow_up_id = str(uuid.uuid4())`.
    *   Extract the original `a2a_taskId` from `response_task.id`.
    *   Store the mapping in cache: `self.component.cache_service.set(f"a2a_follow_up:{sam_follow_up_id}", a2a_taskId, ttl=self.component.input_required_ttl)`. Handle potential cache errors.
    *   Extract the agent's question (assume `TextPart` in `response_task.status.message`).
    *   Return `ActionResponse(success=False, message=agent_question, data={'follow_up_id': sam_follow_up_id}, status='INPUT_REQUIRED')`. *Note: Need to decide on the best way to signal 'pending' status vs. outright failure.* Using a `status` field in `ActionResponse` might be clearer.
*   **4.3.2 Testing:**
    *   Unit Test: Mock `send_task` to return `state=INPUT_REQUIRED` with a question. Mock `CacheService.set`. Verify `invoke` calls `set` correctly and returns the specific `ActionResponse` with the question and `follow_up_id`. Test the case where `CacheService` is None.

**Step 4.4: Implement `provide_required_input` Handler**

*   **4.4.1 Action:** Implement the `_handle_provide_required_input(self, params: Dict, meta: Dict) -> ActionResponse` method in `A2AClientAgentComponent`.
    *   Get `follow_up_id`, `user_response`, optional `files` from `params`.
    *   Get `a2a_client`, `cache_service`, `file_service`. Check they exist. Get `session_id` from `meta`.
    *   Retrieve `a2a_taskId = self.cache_service.get(f"a2a_follow_up:{follow_up_id}")`.
    *   If `a2a_taskId` is None, return error `ActionResponse` ("Invalid or expired follow-up ID.").
    *   *(Optional but recommended)* Delete the cache entry: `self.cache_service.delete(f"a2a_follow_up:{follow_up_id}")`.
    *   Map `user_response` and `files` to A2A `Message.parts` (similar to Step 3.3, using `file_service`).
    *   Create `TaskSendParams` using the *retrieved* `a2a_taskId`, `session_id`, and the new message.
    *   Call `self.a2a_client.send_task()` with these params (wrap in `try...except`).
    *   Process the `response_task` using the *same logic* as in `A2AClientAction.invoke` (handle `COMPLETED`, `FAILED`, or even another `INPUT_REQUIRED`). Return the resulting `ActionResponse`.
    *   Handle communication exceptions.
*   **4.4.2 Testing:**
    *   Unit Test: Mock `CacheService` (`get`, `delete`). Mock `A2AClient.send_task`.
        *   Test case: Valid `follow_up_id` found. Mock `send_task` returns `COMPLETED`. Verify handler returns success `ActionResponse`. Verify `cache.delete` was called.
        *   Test case: Valid `follow_up_id` found. Mock `send_task` returns `FAILED`. Verify handler returns error `ActionResponse`.
        *   Test case: Valid `follow_up_id` found. Mock `send_task` returns *another* `INPUT_REQUIRED`. Verify handler saves *new* state and returns the new question/follow-up ID.
        *   Test case: Invalid/expired `follow_up_id` (mock `cache.get` returns None). Verify handler returns the "Invalid ID" error.
        *   Test case: `send_task` raises exception. Verify handler returns communication error.

---

**Phase 5: Configuration and Finalization**

**Step 5.1: Create Configuration Template**

*   **5.1.1 Action:** Create `src/agents/a2a_client/a2a_client_agent_config_template.yaml`.
*   **5.1.2 Action:** Define the standard SAM agent config structure, including flows for registration and action processing.
*   **5.1.3 Action:** In the `action_request_processor` component definition:
    *   Set `component_module: src.agents.a2a_client.a2a_client_agent_component`.
    *   Include the necessary `component_config` parameters, using environment variable placeholders (e.g., `agent_name: ${AGENT_NAME}`, `a2a_server_url: ${AGENT_NAME_UPPER}_A2A_SERVER_URL`, etc.). Match the parameters defined in the component's `info` dict.
    *   Ensure `broker_request_response` is enabled if needed (e.g., for potential future LLM calls within the component, though not strictly required for basic A2A wrapping).
*   **5.1.4 Testing:** Manual review against component config definition.

**Step 5.2: Refinement and Documentation**

*   **5.2.1 Action:** Review all code for clarity, comments, docstrings, and logging. Ensure consistent error handling and messaging.
*   **5.2.2 Action:** Update `README.md` with final installation instructions, detailed configuration steps, examples, and usage notes.
*   **5.2.3 Action:** Update `pyproject.toml` with correct author info, final dependencies, and version.
*   **5.2.4 Testing:** Code review, documentation review.

**Step 5.3: End-to-End Testing (Optional but Recommended)**

*   **5.3.1 Action:** If possible, set up a real (or mock) A2A agent (like the CrewAI sample).
*   **5.3.2 Action:** Configure and run SAM with the `sam-a2a-client` plugin instance pointing to the test A2A agent.
*   **5.3.3 Action:** Use a SAM client (like the REST API gateway or Slack gateway) to send requests that trigger the dynamic actions.
*   **5.3.4 Testing:** Verify:
    *   Successful completion for simple requests.
    *   Correct handling of file inputs/outputs.
    *   Correct handling of the `INPUT_REQUIRED` cycle.
    *   Graceful handling of A2A agent errors or connection issues.

---
This plan breaks down the implementation into manageable phases, allowing for testing at each stage. Remember to adjust A2A library import paths and async handling based on the specifics of the chosen `a2a-common` dependency method.
```