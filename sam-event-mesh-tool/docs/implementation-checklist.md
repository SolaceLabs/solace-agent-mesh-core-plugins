# Implementation Checklist: `sam-event-mesh-tool` Test Environment

This checklist provides a terse summary of the tasks required to implement the test environment as outlined in the design document.

## 1. Project Setup

- [x] Create `tests/` directory.
- [x] Create `tests/integration/` subdirectory.
- [x] Create `tests/test_configs/` subdirectory.
- [x] Create empty `__init__.py` files in `tests/` and `tests/integration/`.
- [x] Add `pytest` and `pytest-asyncio` to `[project.optional-dependencies]` in `pyproject.toml`.

## 2. Configuration Files

- [x] Create `tests/test_configs/agent_config.yaml`.
    - [x] Define `SamAgentApp` with `dev_mode: true`.
    - [x] Configure `EventMeshTool` with `tool_name`, `topic`, `parameters`, and `event_mesh_config` using `dev_mode: true`.
- [x] Create `tests/test_configs/responder_config.yaml`.
    - [x] Define a flow with `broker_input`, `handler_callback`, and `broker_output`.
    - [x] Use `dev_mode: true` for the broker connection.
    - [x] `broker_input` subscribes to the agent's request topic.
    - [x] `handler_callback` is configured for a runtime-injected `invoke_handler`.
    - [x] `broker_output` is configured to use `previous:topic` and `previous:payload`.

## 3. Test Fixtures (`tests/conftest.py`)

- [x] **`response_control_queue` fixture**:
    - [x] Create and `yield` a session-scoped `queue.Queue`.
- [x] **`responder_invoke_handler` function**:
    - [x] Implement the handler logic: `get` from control queue, `sleep`, extract `reply_to` topic, and return `{'topic': ..., 'payload': ...}`.
- [x] **`responder_service` fixture**:
    - [x] Load `responder_config.yaml`.
    - [x] Use `functools.partial` to bind the `response_control_queue` to the `responder_invoke_handler`.
    - [x] Inject the handler into the loaded config.
    - [x] Instantiate and run `SolaceAiConnector` in a background thread.
    - [x] `yield` the connector and `stop()` it on teardown.
- [x] **`agent_with_event_mesh_tool` fixture**:
    - [x] Depend on `responder_service` to ensure startup order.
    - [x] Load `agent_config.yaml`.
    - [x] Instantiate and run `SolaceAiConnector` in a background thread.
    - [x] Find and `yield` the `SamAgentComponent` instance.
    - [x] `stop()` the connector on teardown.

## 4. Test Cases (`tests/integration/test_event_mesh_tool.py`)

- [ ] **`test_simple_request_response`**:
    - [ ] Arrange: `put` a response payload on the control queue.
    - [ ] Act: `await` a single tool call.
    - [ ] Assert: Check if the returned payload matches.
- [ ] **`test_concurrent_requests`**:
    - [ ] Arrange: `put` two responses with different delays on the control queue.
    - [ ] Act: Use `asyncio.gather` to run two tool calls concurrently.
    - [ ] Assert: Check if both responses are correct, confirming out-of-order correlation.
- [ ] **`test_request_timeout`**:
    - [ ] Arrange: Do not put anything on the control queue.
    - [ ] Act/Assert: Use `pytest.raises(TimeoutError)` to verify the tool call times out.
- [ ] **`test_fire_and_forget`**:
    - [ ] Arrange: Set `wait_for_response: false` in the agent's YAML config for this test (or use a separate config).
    - [ ] Act: `await` the tool call.
    - [ ] Assert: Verify the tool returns an immediate success message and that the responder still received the request.
