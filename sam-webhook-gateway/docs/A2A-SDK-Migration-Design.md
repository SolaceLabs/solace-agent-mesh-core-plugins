# A2A SDK Migration Design: Webhook Gateway

## 1. Overview

This document details the design for refactoring the Universal Webhook Gateway (`sam-webhook-gateway`) to align with the latest official Agent-to-Agent (A2A) protocol specification. The primary effort involves migrating from our legacy, custom A2A type definitions to the official `a2a-sdk` for Python.

The Webhook Gateway is a non-interactive component that acts as a configurable HTTP ingress for external systems. It translates incoming webhook requests into A2A tasks and immediately acknowledges them, without waiting for a final response. This design focuses on updating the gateway's internal A2A message handling to use the new, standardized `a2a.types` models.

## 2. Goals

*   **Protocol Compliance:** Fully align the Webhook Gateway with the official A2A JSON specification.
*   **SDK Adoption:** Replace all bespoke A2A type implementations in the `sam-webhook-gateway` module with types from the `a2a-sdk`.
*   **Standardized Communication:** Ensure all A2A message creation and handling uses the official `a2a.types` models.
*   **Improved Maintainability:** Simplify the gateway's logic by relying on the `a2a-sdk` for data validation and structure.

## 3. Core Design Changes

### 3.1. Type System Migration

All A2A-related data models within the `sam-webhook-gateway` module will be replaced with their counterparts from the `a2a.types` library. The `BaseGatewayComponent` will deliver fully parsed and validated `a2a.types` objects to the component's handler methods.

**Key Type Mappings:**

| Legacy Model (`common/types.py`) | New Model (`a2a.types`) | Key Changes |
| --- | --- | --- |
| `Part` (Union) | `Part` (RootModel) | The discriminator field changes from `type` to `kind`. All created parts must be wrapped in the `Part` root model (e.g., `Part(root=TextPart(...))`). |
| `Task` | `Task` | The structure is updated to match the official spec. |
| `TaskStatusUpdateEvent` | `TaskStatusUpdateEvent` | The `id` field is renamed to `taskId`. |
| `JSONRPCError` | `JSONRPCError` | No structural change, but the import source will change. |
| `InternalError` | `InternalError` | No structural change, but the import source will change. |
| `InvalidRequestError` | `InvalidRequestError` | No structural change, but the import source will change. |

For a complete mapping, refer to the [A2A Type Migration Map](../../docs/refactoring/A2A-Type-Migration-Map.md).

### 3.2. Outgoing A2A Message Generation

The process of creating A2A tasks from incoming webhook requests will be updated to use the new types.

*   **Component:** `WebhookGatewayComponent`
*   **Method:** `_translate_external_input`
*   **Design:**
    *   The method will continue to be responsible for creating a list of `A2APart` objects from the request data.
    *   The creation of the `TextPart` will be updated to wrap the object in the `A2APart` root model: `a2a_parts.append(A2APart(root=TextPart(text=str(templated_text))))`.
    *   The `BaseGatewayComponent.submit_a2a_task` method will consume these parts and construct the final, compliant `SendMessageRequest`.

### 3.3. Incoming A2A Message Processing

The methods responsible for handling events from the agent (`_send_update_to_external`, `_send_final_response_to_external`, `_send_error_to_external`) are non-operational in this gateway (they only log that they were called).

*   **Design:** The type hints for the parameters of these methods (`event_data`, `task_data`, `error_data`) will be updated to their `a2a.types` counterparts. The internal logic (logging) will remain unchanged.

### 3.4. Exception Handling

The FastAPI exception handlers format errors into a JSONRPC-like structure. This will be updated to use the official error types.

*   **File:** `sam-webhook-gateway/src/sam_webhook_gateway/main.py`
*   **Design:** The imports for `JSONRPCError`, `InternalError`, and `InvalidRequestError` will be changed from `solace_agent_mesh.common.types` to `a2a.types`. The exception handlers will continue to function as before with the new types.

## 4. Component-Level Impact

*   **`sam-webhook-gateway/src/sam_webhook_gateway/component.py`:**
    *   All `solace_agent_mesh.common.types` imports will be replaced with `a2a.types`.
    *   `_translate_external_input` will be updated to wrap the created `TextPart` in `A2APart(root=...)`.
    *   The type hints for the `_send_*_to_external` methods will be updated.

*   **`sam-webhook-gateway/src/sam_webhook_gateway/main.py`:**
    *   The imports for `JSONRPCError`, `InternalError`, and `InvalidRequestError` will be changed from `solace_agent_mesh.common.types` to `a2a.types`.

*   **Other Files (`app.py`, `dependencies.py`):**
    *   No changes are required as these files are sufficiently abstracted from the A2A data models.

## 5. Testing Strategy

*   The test suite for the Webhook Gateway will be updated to use the new `a2a.types` models for creating mock agent responses.
*   Assertions in integration tests will be modified to validate the structure and content of the HTTP responses.
