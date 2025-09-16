# Implementation Checklist: `sam-event-mesh-tool` Test Environment

This checklist provides a terse summary of the tasks required to implement the test environment as outlined in the design document.

## 1. Project Setup

- [ ] Create `tests/` directory.
- [ ] Create `tests/integration/` subdirectory.
- [ ] Create `tests/test_configs/` subdirectory.
- [ ] Create empty `__init__.py` files in `tests/` and `tests/integration/`.
- [ ] Add `pytest` and `pytest-asyncio` to `[project.optional-dependencies]` in `pyproject.toml`.

## 2. Configuration Files

- [ ] Create `tests/test_configs/agent_config.yaml`.
    - [ ] Define `SamAgentApp` with `dev_mode: true`.
    - [ ] Configure `EventMeshTool` with `tool_name`, `topic`, `parameters`, and `event_mesh_config` using `dev_mode: true`.
- [ ] Create `tests/test_configs/responder_config.yaml`.
    - [ ] Define a flow with `broker_input`, `handler_callback`, and `broker_output`.
    - [ ] Use `dev_mode: true` for the broker connection.
    - [ ] `broker_input` subscribes to the agent's request topic.
    - [ ] `handler_callback` is configured for a runtime-injected `invoke_handler`.
    - [ ] `broker_output` is configured to use `previous:topic` and `previous:payload`.

## 3. Test Fixtures (`tests/conftest.py`)

- [ ] **`response_control_queue` fixture**:
    - [ ] Create and `yield` a session-scoped `queue.Queue`.
- [ ] **`responder_invoke_handler` function**:
    - [ ] Implement the handler logic: `get` from control queue, `sleep`, extract `reply_to` topic, and return `{'topic': ..., 'payload': ...}`.
- [ ] **`responder_service` fixture**:
    - [ ] Load `responder_config.yaml`.
    - [ ] Use `functools.partial` to bind the `response_control_queue` to the `responder_invoke_handler`.
    - [ ] Inject the handler into the loaded config.
    - [ ] Instantiate and run `SolaceAiConnector` in a background thread.
    - [ ] `yield` the connector and `stop()` it on teardown.
- [ ] **`agent_with_event_mesh_tool` fixture**:
    - [ ] Depend on `responder_service` to ensure startup order.
    - [ ] Load `agent_config.yaml`.
    - [ ] Instantiate and run `SolaceAiConnector` in a background thread.
    - [ ] Find and `yield` the `SamAgentComponent` instance.
    - [ ] `stop()` the connector on teardown.

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
