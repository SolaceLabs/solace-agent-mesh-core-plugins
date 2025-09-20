# Test Framework Design for `sam-event-mesh-tool`

This document outlines the design and usage of the integration test framework for the `sam-event-mesh-tool`. The framework is built using `pytest` and is designed to be flexible, reliable, and fully isolated, enabling comprehensive testing of the tool's functionality without external dependencies.

## 1. Overall Approach

The test strategy is based on running two independent but communicating Solace AI Connector (SAC) flows within a single test process. This creates a self-contained integration test that mirrors a real-world client-server interaction.

-   **Agent Flow (The "Client"):** This flow hosts a `SamAgentComponent` configured with the `EventMeshTool`. This is the **System Under Test (SUT)**. When the tool is invoked during a test, it sends a request message into the event mesh.

-   **Responder Flow (The "Service"):** This flow simulates a backend microservice. It uses a `broker_input` to listen for requests from the Agent Flow, processes them using a flexible handler, and sends a correlated response back using a `broker_output`.

-   **Communication Channel:** Both flows are configured to use `dev_mode: true`. This activates the in-memory `dev_broker`, which uses shared Python `queue.Queue` objects for messaging. This allows the two flows to communicate directly and reliably within the same process, eliminating the need for an external broker.

## 2. Key Components & Fixtures

The test environment is constructed using a series of `pytest` fixtures defined in `conftest.py`.

### 2.1. Agent Fixture (`agent_with_event_mesh_tool`)
This `pytest` fixture sets up the "Client" side of the test. It loads the agent configuration, starts the agent in a background thread, and yields the running `SamAgentComponent` instance to the test function.

### 2.2. Responder Fixture (`responder_service`)
This fixture sets up the "Service" side. It loads the responder configuration and injects a dynamic handler function that allows tests to control the responder's behavior. The responder listens for requests, processes them according to instructions from the test, and sends back replies.

### 2.3. Test Control Mechanism (`response_control_queue`)
To allow each test to define the responder's behavior, a shared control queue is used.
-   A test function `put`s an instruction tuple onto this queue before invoking the agent's tool.
-   The instruction tuple typically contains `(response_payload, delay_seconds, should_send_reply)`.
-   The responder's handler blocks on `queue.get()` to retrieve this instruction, then acts accordingly (e.g., delays, sends a specific payload, or sends no reply at all).

## 3. Interaction Flow in a Typical Test

1.  **Setup:** `pytest` initializes the `agent_with_event_mesh_tool`, `responder_service`, and `response_control_queue` fixtures.
2.  **Arrange:** The test function `put`s a response instruction (e.g., `({'temp': 25}, 0, True)`) onto the `response_control_queue`.
3.  **Act:** The test function calls the `EventMeshTool` on the agent component.
4.  **Agent Flow (Request):** The `EventMeshTool` sends a request message via the `dev_broker`.
5.  **Responder Flow (Processing):** The responder's `broker_input` receives the message. Its handler gets the instruction from the control queue and uses it to construct and send a reply via its `broker_output`.
6.  **Agent Flow (Response):** The `EventMeshTool`, which has been waiting, receives the reply and returns the payload.
7.  **Assert:** The test function asserts that the returned payload matches the one it arranged.

## 4. Advanced Testing Capabilities

This design provides a highly flexible way to test a wide range of scenarios:

-   **Concurrency:** Tests can use `asyncio.gather` to initiate multiple tool calls concurrently. The framework's use of multiple handler instances in the responder allows for true parallel processing and out-of-order reply testing.
-   **Timeout Simulation:** A test can instruct the responder not to send a reply (`should_send_reply=False`), allowing the test to assert that the agent's tool call correctly times out.
-   **Error Responses:** The responder can be instructed to return a payload that simulates a server-side error, which the tool should then propagate.
-   **Fire-and-Forget:** Tests can configure the tool with `wait_for_response: false` and verify that the tool call returns immediately while the message is still processed by the responder.

This framework provides a robust, isolated, and maintainable foundation for thoroughly testing the `sam-event-mesh-tool`.
