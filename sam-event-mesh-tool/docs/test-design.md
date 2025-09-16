# Test Environment Design for `sam-event-mesh-tool`

This document outlines the design for a comprehensive integration test environment for the `sam-event-mesh-tool`. The goal is to create a flexible, reliable, and isolated test setup using `pytest` fixtures to validate the tool's functionality, including its ability to handle concurrent requests.

## 1. Overall Approach

The test strategy is based on running two independent but communicating Solace AI Connector (SAC) flows within a single test process. This creates a self-contained integration test that mirrors a real-world client-server interaction without external dependencies.

-   **Agent Flow (The "Client"):** This flow hosts a `SamAgentComponent` configured with the `EventMeshTool`. This is the **System Under Test (SUT)**. When the tool is invoked during a test, it sends a request message into the event mesh.

-   **Responder Flow (The "Service"):** This flow simulates a backend microservice. It uses a `broker_input` to listen for requests from the Agent Flow, processes them using a flexible handler, and sends a correlated response back using a `broker_output`.

-   **Communication Channel:** Both flows will be configured to use `dev_mode: true`. This activates the in-memory `dev_broker`, which uses shared Python `queue.Queue` objects for messaging. This allows the two flows to communicate directly and reliably within the same process, eliminating the need for an external broker.

## 2. Key Components & Fixtures

The test environment will be constructed using a series of `pytest` fixtures.

### 2.1. The `dev_broker`
The `dev_broker` is the cornerstone of this design. By setting `dev_mode: true` in the broker configurations for both the agent and the responder, they will automatically share the same underlying set of in-memory queues and topic subscriptions. This enables fast, deterministic, and isolated communication.

### 2.2. Agent Fixture (`agent_with_event_mesh_tool`)
This `pytest` fixture will be responsible for setting up the "Client" side of the test.

-   **Responsibilities:**
    -   Load a YAML configuration for a `SamAgentApp`.
    -   Configure the `EventMeshTool` within the agent's `tools` list. The `event_mesh_config` for the tool will specify a `dev_mode` broker connection.
    -   Instantiate and run a `SolaceAiConnector` instance with this agent app in a background thread.
    -   Yield the running `SamAgentComponent` instance to the test function, providing an interface to invoke the tool.
    -   Handle cleanup by stopping the connector instance.

### 2.3. Responder Fixture (`responder_service`)
This fixture sets up the "Service" side and is designed for maximum flexibility.

-   **Responsibilities:**
    -   Load a separate YAML configuration for the responder flow.
    -   The flow will consist of three components:
        1.  **`broker_input`**: Subscribes to the topic the `EventMeshTool` is configured to publish to (e.g., `test/request/>`).
        2.  **`handler_callback`**: A generic component whose `invoke` logic is defined by a dynamically created Python function. This function will be the key to controlling the responder's behavior from the test.
        3.  **`broker_output`**: Takes the output from the `handler_callback` and publishes it as a response. The handler is responsible for ensuring the reply is sent to the correct `reply_to` topic from the original request's user properties.
    -   Instantiate and run a second `SolaceAiConnector` instance with this responder flow in a background thread.
    -   Handle cleanup.

### 2.4. Test Control Mechanism (`response_control_queue`)
To allow each test to define the responder's behavior, a shared control queue will be used.

-   **Responsibilities:**
    -   A simple `pytest` fixture will create and yield a standard Python `queue.Queue`.
    -   The test function will `put` the desired response payload (or an error/delay instruction) onto this queue before invoking the agent's tool.
    -   The `handler_callback` function within the `responder_service` will block on `queue.get()` to retrieve this instruction. It will then use the retrieved data to construct and send the reply message.

## 3. Interaction Flow in a Typical Test

1.  **Setup:** `pytest` initializes the `agent_with_event_mesh_tool`, `responder_service`, and `response_control_queue` fixtures. Both the agent and responder flows are now running in background threads.
2.  **Arrange:** The test function determines the expected outcome and `put`s a response dictionary (e.g., `{'temp': 25, 'unit': 'celsius'}`) onto the `response_control_queue`.
3.  **Act:** The test function calls the `EventMeshTool`'s interface on the yielded agent component (e.g., `await agent.invoke_tool('GetWeather', {'city': 'Ottawa'})`).
4.  **Agent Flow (Request):**
    -   The `EventMeshTool` receives the call.
    -   It constructs the request payload and topic.
    -   It calls `do_broker_request_response_async` using its dedicated session.
    -   The `dev_broker` places the request message onto the in-memory queue corresponding to the request topic.
5.  **Responder Flow (Processing):**
    -   The `broker_input` component receives the message from the queue.
    -   The message is passed to the `handler_callback`.
    -   The handler function calls `response_control_queue.get()` and retrieves the response dictionary.
    -   The handler constructs a reply message, setting the payload to the retrieved dictionary and the destination topic to the `reply_to` topic found in the incoming message's user properties.
    -   The `broker_output` component sends the reply message.
6.  **Agent Flow (Response):**
    -   The `EventMeshTool`'s `do_broker_request_response_async` call, which has been waiting, receives the reply message from the `dev_broker`.
    -   The tool call completes, and its result (the response payload) is returned to the test function.
7.  **Assert:** The test function asserts that the returned payload matches the dictionary it originally placed on the control queue.

## 4. Concurrency and Asynchronous Testing

This design inherently supports testing complex asynchronous scenarios.

-   **Simultaneous Requests:** A test can use `asyncio.gather` to initiate multiple tool calls concurrently. The `dev_broker` and the agent's `BrokerRequestResponse` component are thread-safe and designed to handle this. The test can verify that all responses are received correctly, even if they arrive out of order.
-   **Simulating Delays:** The control queue can pass delay instructions to the responder's handler, allowing tests to simulate slow backend services and verify that responses are still correlated correctly.
-   **Fire-and-Forget:** Tests can configure the tool with `wait_for_response: false` and verify that the tool call returns immediately while the message is still processed by the responder flow.

## 5. Flexibility and Test Scenarios

The control queue mechanism provides a highly flexible way to test a wide range of scenarios beyond the "happy path":

-   **Malformed Responses:** The test can instruct the responder to send back invalid JSON or malformed data to verify the tool's error handling.
-   **Timeout Simulation:** The test can simply not put anything on the control queue, causing the responder to never reply and allowing the test to assert that the agent's tool call correctly raises a `TimeoutError`.
-   **Error Responses:** The responder can be instructed to return a payload indicating a server-side error, which the tool should then propagate.

This design provides a robust, isolated, and maintainable foundation for thoroughly testing the `sam-event-mesh-tool`.
