# SAM Event Mesh Gateway: User Guide

## Overview

The Solace Agent Mesh (SAM) Event Mesh Gateway is a powerful plugin that acts as a bridge between a Solace PubSub+ event mesh and the SAM agent ecosystem. It allows external systems to trigger AI agent tasks by publishing events to the mesh, and it enables agents to publish their results back to the mesh for consumption by other applications.

**Key Features:**

*   **Event-Driven Agent Invocation**: Subscribes to topics on a "data plane" event mesh and triggers agent tasks based on received messages.
*   **Flexible Message Transformation**: Uses the Solace AI Connector expression engine to transform incoming message payloads into prompts for AI agents.
*   **Dynamic Response Routing**: Publishes agent responses back to the event mesh on dynamically determined topics.
*   **Context Forwarding**: Preserves and forwards correlation data from an incoming event to the corresponding outgoing response, enabling request-reply patterns.
*   **Differentiated Success/Error Handling**: Routes successful agent responses and error conditions to different topics with different payload structures.
*   **Self-Contained Payloads**: Intelligently embeds agent-produced artifacts (text and binary files) directly into the output message payload.
*   **Workflow Integration**: Supports structured invocation mode for invoking SAM workflows with schema-validated input and output through artifacts.
*   **Deferred Acknowledgment**: Optionally defer Solace message acknowledgment until agent/workflow processing completes, providing at-least-once delivery semantics.

## Installation
To install the SAM Event Mesh Gateway plugin, run the following command in your SAM project directory:

```bash
solace-agent-mesh plugin add <your-new-component-name> --plugin sam-event-mesh-gateway
```
This will create a new component configuration at `configs/plugins/<your-new-component-name-kebab-case>.yaml`.

## Configuration

The gateway is configured within the `app_config` section of its app definition in your main SAM Host YAML file.

### Core Configuration

*   `event_mesh_broker_config` (object, required): Standard SAC broker connection parameters (`broker_url`, `broker_vpn`, etc.) for the dedicated data plane client.
*   `event_handlers` (list, required): Defines how to process incoming messages from the data plane.
*   `output_handlers` (list, optional): Defines how to format and publish agent responses back to the data plane.

### `event_handlers`

Each item in the `event_handlers` list defines a listener for one or more topics.

*   `name` (string, required): A unique name for the handler.
*   `subscriptions` (list, required): A list of topic subscriptions for the data plane.
*   `input_expression` (string, required): A SAC template expression that transforms the incoming Solace message into the main text prompt for the A2A task (or the input data for structured invocation).
*   `target_agent_name` (string, optional): The static name of the agent to send the task to.
*   `target_agent_name_expression` (string, optional): A SAC expression to dynamically determine the target agent.
*   `target_workflow_name` (string, optional): The static name of the target workflow. Mutually exclusive with `target_agent_name`. When specified, the gateway automatically uses structured invocation mode.
*   `target_workflow_name_expression` (string, optional): A SAC expression to dynamically determine the target workflow name. Automatically enables structured invocation mode.
*   `structured_invocation` (object, optional): Configuration for structured invocation mode when targeting an agent (not required for workflows). For more information, see Workflow Integration below.
    *   `input_schema` (object, optional): JSON Schema for input validation.
    *   `output_schema` (object, optional): JSON Schema for expected output validation.
*   `on_success` (string, optional): The name of the `output_handler` to use when the agent task completes successfully.
*   `on_error` (string, optional): The name of the `output_handler` to use when the agent task fails.
*   `forward_context` (object, optional): A dictionary for extracting and forwarding correlation data. Keys are custom names, and values are SAC expressions evaluated against the incoming message.

**Example `forward_context`:**
```yaml
forward_context:
  correlation_id: "input.user_properties:correlation_id"
  original_topic: "input.topic:"
```

#### Artifact Processing

The gateway can automatically create artifacts from incoming messages before generating the agent prompt. This is controlled by the optional `artifact_processing` block within an `event_handler`.

*   `artifact_processing` (object, optional): If present, enables artifact creation.
    *   `extract_artifacts_expression` (string, required): A SAC expression that resolves to the data to be processed. This can be a single item (like the raw payload) or a list of items (like a list of file objects in a JSON payload).
    *   `artifact_definition` (object, required): Defines how to extract the necessary fields for each artifact.
        *   `filename` (string, required): An expression to get the artifact's filename.
        *   `content` (string, required): An expression to get the artifact's content.
        *   `mime_type` (string, required): An expression to get the artifact's MIME type.
        *   `content_encoding` (string, optional): An expression to get the content's encoding (`base64`, `text`, or `binary`). This is crucial for correctly handling binary data.

**The `list_item:` Selector**

When `extract_artifacts_expression` resolves to a list, the gateway iterates through it. Inside the `artifact_definition` block, you must use the special `list_item:` selector to refer to fields of the current item in the list. The standard `input.payload:` selector always refers to the original, complete message payload.

### `output_handlers`

Each item in the `output_handlers` list defines a template for publishing a response.

*   `name` (string, required): A unique name for the handler.
*   `topic_expression` (string, required): A SAC expression to generate the output topic.
*   `payload_expression` (string, required): A SAC expression to generate the output payload.
*   `max_file_size_for_base64_bytes` (integer, optional, default: 1048576): The maximum size in bytes for an artifact file to be embedded in the payload.
*   `output_transforms` (list, optional): A list of standard SAC transforms to process the agent response before the payload expression is evaluated.

### `acknowledgment_policy`

The acknowledgment policy controls when and how the gateway acknowledges (ACKs) incoming Solace messages from the data plane. This is critical for controlling message delivery guarantees.

#### Default Behavior: Immediate Acknowledgment (`on_receive`)

By default, the gateway ACKs each message immediately upon receipt, before any processing begins. This is a **fire-and-forget** model: if the gateway crashes mid-processing or the agent/workflow fails, the message is lost and will not be redelivered.

This is suitable for:
*   Non-critical events where occasional message loss is acceptable.
*   High-throughput scenarios where redelivery would cause problems.
*   Events that are idempotent or where duplicates are undesirable.

#### Deferred Acknowledgment (`on_completion`)

When `mode` is set to `"on_completion"`, the gateway defers the ACK until the A2A task has been fully processed and the response has been successfully published back to the data plane. This provides **at-least-once delivery semantics**: if the gateway crashes or processing fails, the message remains unacknowledged and the broker will redeliver it.

This is suitable for:
*   Critical events that must not be lost (orders, financial transactions, compliance events).
*   Workflows where processing failure should trigger automatic retry via broker redelivery.
*   Scenarios where the cost of processing a duplicate message is lower than the cost of losing a message.

#### Configuration

The acknowledgment policy can be set at two levels:

1.  **Gateway level** (top-level `acknowledgment_policy`): Sets the default for all event handlers.
2.  **Handler level** (inside an `event_handlers` item): Overrides the gateway default for a specific handler. Any field set at the handler level takes precedence.

**Full schema:**

```yaml
acknowledgment_policy:
  mode: "on_receive"          # "on_receive" (default) | "on_completion"
  on_failure:
    action: "nack"            # "nack" (default) | "ack"
    nack_outcome: "rejected"  # "rejected" (default) | "failed"
  timeout_seconds: 300        # Default: 300 (5 minutes)
```

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | string | `"on_receive"` | When to ACK. `"on_receive"`: immediately on receipt. `"on_completion"`: after successful processing. |
| `on_failure.action` | string | `"nack"` | What to do when processing fails. `"nack"`: negatively acknowledge (triggers redelivery or DLQ). `"ack"`: acknowledge even on failure (discard the message). |
| `on_failure.nack_outcome` | string | `"rejected"` | The NACK outcome when `action` is `"nack"`. `"rejected"`: message is redelivered to the queue. `"failed"`: message is moved to the dead letter queue (DLQ). |
| `timeout_seconds` | integer | `300` | Maximum seconds to wait for task completion. If the task has not completed within this time, the message is settled as a failure using the `on_failure` policy. |

> **Note:** The `on_failure`, `nack_outcome`, and `timeout_seconds` fields only apply when `mode` is `"on_completion"`. They are ignored in `"on_receive"` mode.

#### Message Settlement Behavior

The following table summarizes when and how messages are settled under each configuration:

| Scenario | `on_receive` mode | `on_completion` mode |
|----------|-------------------|----------------------|
| Message received | ACK immediately | Hold (no ACK yet) |
| No matching handler | ACK (already done) | NACK (using `on_failure` policy) |
| Authentication failure | ACK (already done) | NACK (using `on_failure` policy) |
| Translation/submission failure | ACK (already done) | NACK (using `on_failure` policy) |
| Task completes successfully, response published | N/A | ACK |
| Task completes successfully, no `on_success` handler | N/A | ACK |
| Task fails (agent error) | N/A | Settle per `on_failure` policy |
| Response publish fails | N/A | Settle per `on_failure` policy |
| Timeout exceeded | N/A | Settle per `on_failure` policy |
| Gateway shutdown | N/A | NACK all pending (redelivered on restart) |

#### Per-Handler Override Example

You can set a gateway-wide default and override it for specific handlers:

```yaml
app_config:
  # Gateway-level default: immediate ACK
  acknowledgment_policy:
    mode: "on_receive"

  event_handlers:
    # This handler uses the gateway default (on_receive)
    - name: "low_priority_handler"
      subscriptions:
        - topic: "telemetry/>"
      input_expression: "template:Process telemetry: {{json://input.payload}}"
      target_agent_name: "TelemetryAgent"

    # This handler overrides to deferred ACK
    - name: "critical_order_handler"
      subscriptions:
        - topic: "orders/>"
      input_expression: "template:Process order: {{json://input.payload}}"
      target_agent_name: "OrderAgent"
      on_success: "order_success_handler"
      on_error: "order_error_handler"
      acknowledgment_policy:
        mode: "on_completion"
        on_failure:
          action: "nack"
          nack_outcome: "failed"  # Send to DLQ on failure
        timeout_seconds: 120       # 2 minute timeout for orders
```

#### Failure Handling Patterns

**Pattern 1: Retry via redelivery (default)**

Messages that fail processing are redelivered by the broker for another attempt. This is the default behavior when `on_failure.nack_outcome` is `"rejected"`.

```yaml
acknowledgment_policy:
  mode: "on_completion"
  on_failure:
    action: "nack"
    nack_outcome: "rejected"  # Broker redelivers the message
```

> **Warning:** Ensure your processing is idempotent when using this pattern, as messages may be delivered more than once.

**Pattern 2: Dead letter queue**

Messages that fail processing are moved to a dead letter queue (DLQ) for later inspection and manual reprocessing.

```yaml
acknowledgment_policy:
  mode: "on_completion"
  on_failure:
    action: "nack"
    nack_outcome: "failed"  # Broker moves message to DLQ
```

**Pattern 3: Rate-limiting with broker-side flow control**

Deferred acknowledgment can be combined with Solace broker queue settings to rate-limit how many events the gateway processes concurrently. When `mode` is `"on_completion"`, messages remain unacknowledged while they are being processed. The Solace broker tracks the number of delivered-but-unacknowledged messages per consumer flow, and you can cap this using the queue's **Max Delivered Unacked Msgs Per Flow** setting.

For example, if you set `max-delivered-unacked-msgs-per-flow` to `5` on the queue, the broker will deliver at most 5 messages to the gateway at a time. Once 5 messages are in-flight (delivered but not yet ACKed), the broker stops delivering new messages until the gateway ACKs one of the in-flight messages. This provides natural backpressure without any gateway-side configuration.

To configure this on the broker (CLI example):

```
solace(configure)# message-spool
solace(configure/message-spool)# queue <queue-name>
solace(configure/message-spool/queue)# max-delivered-unacked-msgs-per-flow 5
```

On the gateway side, simply enable deferred acknowledgment:

```yaml
acknowledgment_policy:
  mode: "on_completion"  # Messages stay unacked while processing
```

The broker default for this setting is 10,000, which effectively means no rate limiting. By lowering it, you can control concurrency to match the capacity of your agents or workflows. This is especially useful for resource-intensive tasks (e.g., LLM inference, image processing) where you want to avoid overwhelming downstream systems.

> **Tip:** This pattern works because the gateway holds a single consumer flow to the queue. Each unacknowledged message counts against the flow's limit, so the broker naturally throttles delivery to match the gateway's processing rate.

**Pattern 4: Acknowledge on failure (discard)**

Messages are acknowledged even when processing fails. Use this when you want deferred ACK for crash protection but don't want failed messages to be redelivered.

```yaml
acknowledgment_policy:
  mode: "on_completion"
  on_failure:
    action: "ack"  # ACK even on failure — message is discarded
```

## Data Flow and Expression Selectors

The gateway introduces two special selectors to simplify configuration.

1.  **Incoming Message**: An event arrives on the data plane. The matching `event_handler` processes it.
    *   If `artifact_processing` is configured, artifacts are created from the message payload and saved. Their URIs are stored in `user_data.created_artifacts:uris`.
    *   `forward_context` expressions are evaluated against the incoming message. The results are stored.
    *   `input_expression` is evaluated to create the agent prompt. This expression can reference the newly created artifact URIs.
    *   The task, including the prompt and file parts for the created artifacts, is submitted to the agent.

2.  **Agent Response**: The agent completes the task and returns a final response.
    *   The gateway receives the A2A `Task` object and transforms it into a **Simplified Response Object**.
    *   The matching `output_handler` (`on_success` or `on_error`) is selected.

3.  **Outgoing Message**: The `output_handler` generates the response.
    *   The **Simplified Response Object** is made available to expressions via the `task_response:` selector.
    *   The data from `forward_context` is available via the `user_data.forward_context:` selector.
    *   `topic_expression` and `payload_expression` are evaluated to create the final message, which is then published to the data plane.

### The Simplified Response Object (`task_response:`)

This object is the primary source for the `payload_expression`.

**Structure:**
```json
{
  "text": "Combined text from the agent's response.",
  "files": [
    {
      "name": "notes.md",
      "mimeType": "text/markdown",
      "content": "Raw text content...",
      "bytes": null,
      "error": null
    },
    {
      "name": "logo.png",
      "mimeType": "image/png",
      "content": null,
      "bytes": "iVBORw0KGgo...",
      "error": null
    }
  ],
  "data": [ { "data": {"key": "value"}, ... } ],
  "structured_result": { /* StructuredInvocationResult data part (structured invocation only) */ },
  "structured_output": { /* Parsed output artifact content (structured invocation only) */ },
  "a2a_task_response": { /* The original, full A2A Task or Error object */ }
}
```

*   `task_response:text`: Access the combined text.
*   `task_response:files`: Access the list of file objects.
*   `task_response:data`: Access the list of data objects.
*   `task_response:structured_result`: Access the structured invocation result metadata (status, output artifact reference).
*   `task_response:structured_output`: Access the parsed content of the output artifact (for structured invocations).
*   `task_response:a2a_task_response`: Access the raw A2A object for advanced use cases.

### Forwarded Context (`user_data.forward_context:`)

This selector allows you to use data from the original incoming message when creating the outgoing response.

**Example:**
If `forward_context` was `{ correlation_id: "input.user_properties:correlation_id" }`, you can use it in the output handler like this:
```yaml
topic_expression: "template:my_app/response/{{text://user_data.forward_context:correlation_id}}"
```

## Advanced Examples: Artifact Handling

Here are two examples demonstrating how to use the `artifact_processing` feature.

### Processing a Raw Binary Payload

This example configures a handler to listen for raw image data on a topic. It saves the entire payload as a JPEG artifact and then asks an agent to analyze it.

```yaml
# In your event_handlers list:
- name: "iot_image_handler"
  subscriptions:
    - topic: "iot/camera/+/image"
  payload_format: "binary" # Treat payload as raw bytes
  # --- Artifact Processing Block ---
  artifact_processing:
    extract_artifacts_expression: "input.payload" # The item to process is the raw payload
    artifact_definition:
      filename: "template:iot-image-{{text://input.user_properties:deviceId}}-{{text://input.user_properties:timestamp}}.jpg"
      content: "list_item:" # The content is the item itself (the raw payload)
      mime_type: "static:image/jpeg"
      content_encoding: "static:binary" # Explicitly state the content is raw bytes
  # --- Main Prompt ---
  input_expression: "template:Analyze the attached security camera image for anomalies. The device ID is {{text://input.user_properties:deviceId}}."
  target_agent_name: "ImageAnalysisAgent"
```

### Extracting Base64 Files from a JSON Payload

This example processes a JSON event that contains a list of embedded documents. It iterates through the list, decodes each base64 file, saves it as an artifact, and includes all artifact URIs in the final prompt.

**Incoming JSON Payload on `claims/new`:**
```json
{
  "caseId": "C-12345",
  "documents": [
    { "docName": "claim_form.pdf", "docContent": "JVBERi...", "docType": "application/pdf", "encoding": "base64" },
    { "docName": "notes.txt", "docContent": "This is a note.", "docType": "text/plain", "encoding": "text" }
  ]
}
```

**Handler Configuration:**
```yaml
# In your event_handlers list:
- name: "insurance_claim_handler"
  subscriptions:
    - topic: "claims/new"
  payload_format: "json"
  # --- Artifact Processing Block ---
  artifact_processing:
    extract_artifacts_expression: "input.payload:documents" # The item list
    artifact_definition:
      # These expressions are evaluated for EACH item in the 'documents' list
      filename: "list_item:docName"
      content: "list_item:docContent"
      mime_type: "list_item:docType"
      content_encoding: "list_item:encoding" # Dynamically get encoding from payload
  # --- Main Prompt ---
  input_expression: "template:Process insurance case {{text://input.payload:caseId}}. The relevant documents have been attached."
  target_agent_name: "ClaimsProcessingAgent"
```

## Workflow Integration

The gateway supports structured invocation mode for invoking SAM workflows. Unlike text-based agent invocation, structured invocation passes data through artifacts with optional JSON Schema validation.

### When Structured Invocation Is Enabled

Structured invocation mode activates automatically when either of the following conditions is true:

*   `target_workflow_name` or `target_workflow_name_expression` is specified.
*   The `structured_invocation` block contains `input_schema` or `output_schema`.

When using `target_workflow_name`, the gateway targets a workflow directly. When using `target_agent_name` with the `structured_invocation` block, the gateway targets an agent but uses the structured data protocol.

### How Structured Invocation Works

1.  The gateway evaluates `input_expression` to extract the input data.
2.  The input data is serialized (JSON, YAML, CSV, or text based on `payload_format`) and saved as an artifact.
3.  A `StructuredInvocationRequest` data part is created with the input/output schemas and artifact reference.
4.  The task is submitted using `RUN_BASED` session behavior (required for workflows).
5.  The workflow processes the request and returns a `StructuredInvocationResult` with an output artifact.
6.  The gateway loads the output artifact content and makes it available via `task_response:structured_output`.

### Invoking a Workflow

The following example shows how to invoke a data processing workflow from an incoming event.

```yaml
# In your event_handlers list:
- name: "data_processor_handler"
  subscriptions:
    - topic: "data/process/>"
  payload_format: "json"
  input_expression: "input.payload:data"  # Extract the data object to send
  target_workflow_name: "DataProcessingWorkflow"
  on_success: "data_success_handler"
  on_error: "data_error_handler"
  forward_context:
    request_id: "input.user_properties:requestId"
```

### Using Structured Invocation with an Agent

You can use structured invocation with a regular agent by specifying schemas in the `structured_invocation` block.

```yaml
# In your event_handlers list:
- name: "validated_agent_handler"
  subscriptions:
    - topic: "api/validated/>"
  payload_format: "json"
  input_expression: "input.payload"
  target_agent_name: "ValidationAgent"
  structured_invocation:
    input_schema:
      type: "object"
      properties:
        items:
          type: "array"
          items:
            type: "object"
      required: ["items"]
    output_schema:
      type: "object"
      properties:
        results:
          type: "array"
        status:
          type: "string"
  on_success: "validation_success_handler"
```

### Accessing Structured Output

In your output handler, use `task_response:structured_output` to access the parsed output data.

```yaml
# In your output_handlers list:
- name: "data_success_handler"
  topic_expression: "template:data/results/{{text://user_data.forward_context:request_id}}"
  payload_expression: "task_response:structured_output"  # Returns the parsed output artifact
```

## Full Configuration Example

```yaml
# In your main SAC config file, under the 'apps:' list
- name: my_event_mesh_gateway_app
  app_module: sam_event_mesh_gateway.app
  app_base_path: plugins/sam-event-mesh-gateway/src
  broker: # A2A Control Plane Connection
    <<: *broker_connection # Using a YAML anchor for connection details
  app_config:
    namespace: "my-org/dev"
    gateway_id: "event-mesh-gw-01"
    artifact_service:
      type: "filesystem"
      base_path: "/tmp/sam_artifacts"
    
    # Data Plane Connection
    event_mesh_broker_config:
      broker_url: ${DATAPLANE_SOLACE_BROKER_URL}
      broker_vpn: ${DATAPLANE_SOLACE_BROKER_VPN}
      broker_username: ${DATAPLANE_SOLACE_BROKER_USERNAME}
      broker_password: ${DATAPLANE_SOLACE_BROKER_PASSWORD}

    # --- Acknowledgment Policy: Gateway-level default ---
    acknowledgment_policy:
      mode: "on_completion"       # Defer ACK until processing completes
      on_failure:
        action: "nack"
        nack_outcome: "rejected"  # Redeliver on failure
      timeout_seconds: 300        # 5 minute timeout

    # --- Event Handlers: Define how to process incoming messages ---
    event_handlers:
      - name: "process_json_order_handler"
        subscriptions:
          - topic: "acme/orders/json/>"
        input_expression: "template:Summarize this order and check for issues: {{json://input.payload}}"
        target_agent_name: "OrderProcessingAgent"
        on_success: "order_success_handler"
        on_error: "order_error_handler"
        forward_context:
          order_id: "json://input.payload:orderId"
          reply_topic: "input.user_properties:replyTo"
        # Override: send failed orders to DLQ instead of redelivering
        acknowledgment_policy:
          on_failure:
            nack_outcome: "failed"

    # --- Output Handlers: Define how to publish agent responses ---
    output_handlers:
      - name: "order_success_handler"
        max_file_size_for_base64_bytes: 2097152 # 2MB
        topic_expression: "user_data.forward_context:reply_topic" # Use replyTo from original message
        payload_expression: "task_response:" # Send the whole simplified object as JSON

      - name: "order_error_handler"
        topic_expression: "template:acme/orders/error/{{text://user_data.forward_context:order_id}}"
        payload_expression: "task_response:a2a_task_response.error" # Send just the error details
        payload_format: "json"
```
