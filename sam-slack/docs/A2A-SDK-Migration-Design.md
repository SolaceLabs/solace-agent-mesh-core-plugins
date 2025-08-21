# A2A SDK Migration Design: Slack Gateway

## 1. Overview

This document details the design for refactoring the Slack Gateway (`sam-slack`) to align with the latest official Agent-to-Agent (A2A) protocol specification. The primary effort involves migrating from our legacy, custom A2A type definitions to the official `a2a-sdk` for Python.

This refactoring is a critical architectural improvement that will ensure the Slack Gateway is fully compliant and interoperable with the broader A2A ecosystem, reduce technical debt, and standardize communication patterns.

The design leverages the already-updated `BaseGatewayComponent`, which handles the low-level parsing of A2A messages from the message bus. The focus of this design is on adapting the Slack-specific logic to consume and produce messages using the new, standardized `a2a.types` models.

## 2. Goals

*   **Protocol Compliance:** Fully align the Slack Gateway with the official A2A JSON specification.
*   **SDK Adoption:** Replace all bespoke A2A type implementations in the `sam-slack` module with types from the `a2a-sdk`.
*   **Standardized Status Updates:** Refactor the handling of non-visible status updates (e.g., agent progress) to use the official `DataPart` structure, moving away from custom `metadata` fields.
*   **Improved Maintainability:** Simplify the Slack Gateway's logic by relying on the `a2a-sdk` for data validation and structure.

## 3. Core Design Changes

### 3.1. Type System Migration

All A2A-related data models within the `sam-slack` module will be replaced with their counterparts from the `a2a.types` library. This is a direct replacement of legacy types with the official SDK's Pydantic models.

The `BaseGatewayComponent` will deliver fully parsed and validated `a2a.types` objects to the Slack component's handler methods.

**Key Type Mappings:**

| Legacy Model (`common/types.py`) | New Model (`a2a.types`) | Key Changes |
| --- | --- | --- |
| `Part` (Union) | `Part` (RootModel) | The discriminator field changes from `type` to `kind`. |
| `FileContent` | `FileWithUri` / `FileWithBytes` | The `FilePart.file` field now contains a union of these two more specific types. |
| `Task` | `Task` | The `sessionId` field is replaced by `contextId`. |
| `TaskStatusUpdateEvent` | `TaskStatusUpdateEvent` | The `id` field is renamed to `taskId`. A new `contextId` field is added. |

For a complete mapping, refer to the [A2A Type Migration Map](../refactoring/A2A-Type-Migration-Map.md).

### 3.2. Standardized Status Updates via `DataPart`

This is the most significant design change, impacting how the Slack Gateway provides real-time feedback to the user. The legacy approach of embedding status signals in a `Message`'s `metadata` field will be replaced entirely.

**New Design:**

1.  The A2A Agent will send status updates (e.g., "I am now analyzing the data") as a `TaskStatusUpdateEvent`.
2.  The `result` of this event will contain a `status.message` object.
3.  This `Message` will contain a `parts` array with a single `DataPart`.
4.  The `DataPart`'s `data` field will contain a structured JSON object corresponding to a predefined schema (e.g., `agent_progress_update.json`).
5.  The `SlackGatewayComponent` will parse this `DataPart` using the Pydantic models defined in `solace_agent_mesh.common.data_parts` to extract the status text.

**Example: Agent Progress Update**

**Legacy Format (Using `metadata`):**
```json
{
  "result": {
    "id": "task-123",
    "status": {
      "state": "working",
      "message": {
        "role": "agent",
        "metadata": {
          "a2a_signal_type": "agent_status_message",
          "text": "Analyzing the report..."
        }
      }
    }
  }
}
```

**New Compliant Format (Using `DataPart`):**
```json
{
  "result": {
    "kind": "status-update",
    "taskId": "task-123",
    "contextId": "session-456",
    "status": {
      "state": "working",
      "message": {
        "kind": "message",
        "role": "agent",
        "parts": [
          {
            "kind": "data",
            "data": {
              "type": "agent_progress_update",
              "status_text": "Analyzing the report..."
            }
          }
        ]
      }
    }
  }
}
```

The Slack Gateway will be responsible for handling `agent_progress_update` and `artifact_creation_progress` data parts. Other types, like `tool_invocation_start` or `llm_invocation`, will be ignored as per requirements.

### 3.3. Outgoing Message Generation

The process of creating A2A tasks from Slack events will be updated to use the new types.

*   **Component:** `SlackGatewayComponent`
*   **Method:** `_translate_external_input`
*   **Design:**
    *   The method will continue to be responsible for creating a list of `A2APart` objects.
    *   When handling file uploads, it will now create an `a2a.types.FileWithUri` object to populate the `file` field of an `a2a.types.FilePart`.
    *   The `BaseGatewayComponent.submit_a2a_task` method will consume these parts and construct the final, compliant `SendMessageRequest`.

### 3.4. Incoming Message Processing

The methods responsible for handling events from the agent and updating the Slack UI will be refactored to understand the new `a2a.types` structures.

*   **Component:** `SlackGatewayComponent`
*   **Methods:** `_send_update_to_external`, `_send_final_response_to_external`, `_send_error_to_external`
*   **Design:**
    *   The type hints for the `event_data`, `task_data`, and `error_data` parameters will be updated to `a2a.types.TaskStatusUpdateEvent`, `a2a.types.Task`, and `a2a.types.JSONRPCError` respectively.
    *   The logic within `_send_update_to_external` will be rewritten to iterate through the `parts` of the incoming message. It will use `isinstance()` checks on the `part.root` to differentiate between `TextPart` and `DataPart`.
    *   When a `DataPart` is found, it will use the Pydantic models from `common.data_parts` (e.g., `AgentProgressUpdateData`) to validate and parse the `data` payload, extracting the human-readable status text.
    *   The `_update_slack_ui_state` method will be called with the extracted status text.

## 4. Component-Level Impact

*   **`sam_slack/component.py`:** This file will see the most significant changes.
    *   All `solace_agent_mesh.common.types` imports will be replaced with `a2a.types`.
    *   `_translate_external_input` will be updated to create `a2a.types.FileWithUri`.
    *   `_send_update_to_external` will be refactored to parse `DataPart` for status signals.
    *   `_send_final_response_to_external` will be updated to handle the new `a2a.types.Task` structure.
    *   `_send_error_to_external` will be updated to use `a2a.types.JSONRPCError`.

*   **`sam_slack/utils.py`:**
    *   `format_data_part_for_slack` will be deprecated. Its logic for handling specific status signals will be moved directly into `SlackGatewayComponent._send_update_to_external`. The function may be kept as a simple fallback for displaying unexpected `DataPart` objects as raw JSON.
    *   `resolve_and_format_for_slack` will be updated to receive and process `a2a.types` objects.
    *   Other utility functions will be reviewed for type hint consistency.

*   **`sam_slack/handlers.py`:**
    *   This file is expected to have minimal changes, as it delegates all A2A-related logic to the component.

## 5. Testing Strategy

*   The test suite will be updated to use the new `a2a.types` models for creating mock agent responses.
*   Assertions in integration tests will be modified to validate the new Slack message content, which is derived from the `DataPart` structure.
*   The `A2AMessageValidator` (in `test_support`) will be relied upon to ensure all mock payloads sent to the gateway conform to the official `a2a.json` schema.
