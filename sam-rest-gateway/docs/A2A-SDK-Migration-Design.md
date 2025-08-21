# A2A SDK Migration Design: REST Gateway

## 1. Overview

This document details the design for refactoring the REST Gateway (`sam-rest-gateway`) to align with the latest official Agent-to-Agent (A2A) protocol specification. The primary effort involves migrating from our legacy, custom A2A type definitions to the official `a2a-sdk` for Python.

This refactoring is a critical architectural improvement that will ensure the REST Gateway is fully compliant and interoperable with the broader A2A ecosystem, reduce technical debt, and standardize communication patterns.

The design leverages the already-updated `BaseGatewayComponent`, which handles the low-level parsing of A2A messages from the message bus. The focus of this design is on adapting the REST-specific logic to consume and produce messages using the new, standardized `a2a.types` models.

## 2. Goals

*   **Protocol Compliance:** Fully align the REST Gateway with the official A2A JSON specification.
*   **SDK Adoption:** Replace all bespoke A2A type implementations in the `sam-rest-gateway` module with types from the `a2a-sdk`.
*   **Standardized Communication:** Ensure all A2A message creation and handling uses the official `a2a.types` models.
*   **Improved Maintainability:** Simplify the REST Gateway's logic by relying on the `a2a-sdk` for data validation and structure.

## 3. Core Design Changes

### 3.1. Type System Migration

All A2A-related data models within the `sam-rest-gateway` module will be replaced with their counterparts from the `a2a.types` library. This is a direct replacement of legacy types with the official SDK's Pydantic models. The `BaseGatewayComponent` will deliver fully parsed and validated `a2a.types` objects to the REST component's handler methods.

**Key Type Mappings:**

| Legacy Model (`common/types.py`) | New Model (`a2a.types`) | Key Changes |
| --- | --- | --- |
| `Part` (Union) | `Part` (RootModel) | The discriminator field changes from `type` to `kind`. All created parts must be wrapped in the `Part` root model (e.g., `Part(root=TextPart(...))`). |
| `FileContent` | `FileWithUri` / `FileWithBytes` | The `FilePart.file` field now contains a union of these two more specific types. |
| `Task` | `Task` | The `sessionId` field is replaced by `contextId`. |
| `TaskStatusUpdateEvent` | `TaskStatusUpdateEvent` | The `id` field is renamed to `taskId`. A new `contextId` field is added. |
| `JSONRPCError` | `JSONRPCError` | No structural change, but the import source will change. |

For a complete mapping, refer to the [A2A Type Migration Map](../../docs/refactoring/A2A-Type-Migration-Map.md).

### 3.2. Handling of Status Updates

The REST Gateway is non-streaming and does not provide real-time updates to its clients. It either waits for a final result (v1) or makes a final result available for polling (v2).

*   **`_send_update_to_external`:** This method's current logic of ignoring most `TaskStatusUpdateEvent` messages and only aggregating `TaskArtifactUpdateEvent` data is correct for this gateway's purpose. This logic will be preserved. The design change is to update the method's type hints and internal field access (`event_data.id` -> `event_data.task_id`) to align with the new `a2a.types` models.

### 3.3. Outgoing Message Generation

The process of creating A2A tasks from incoming REST API calls will be updated to use the new types.

*   **Component:** `RestGatewayComponent`
*   **Method:** `_translate_external_input`
*   **Design:**
    *   The method will continue to be responsible for creating a list of `A2APart` objects from the request data (prompt, files).
    *   When handling file uploads, it will now create an `a2a.types.FileWithUri` object to populate the `file` field of an `a2a.types.FilePart`.
    *   All created `TextPart` and `FilePart` objects will be wrapped in the `A2APart` root model (e.g., `A2APart(root=FilePart(...))`).
    *   The `BaseGatewayComponent.submit_a2a_task` method will consume these parts and construct the final, compliant `SendMessageRequest`.

### 3.4. Incoming Message Processing

The methods responsible for handling the final events from the agent will be refactored to understand the new `a2a.types` structures.

*   **Component:** `RestGatewayComponent`
*   **Methods:** `_send_final_response_to_external`, `_send_error_to_external`
*   **Design:**
    *   The type hints for the `task_data` and `error_data` parameters will be updated to `a2a.types.Task` and `a2a.types.JSONRPCError` respectively.
    *   The internal logic for caching results (v2) or setting sync events (v1) will remain the same, as it operates on the Pydantic model's dictionary representation (`model_dump()`), which is compatible.
    *   The logic for enriching artifacts in `_send_final_response_to_external` will be updated to handle `a2a.types.Artifact` objects.

## 4. Component-Level Impact

*   **`sam-rest-gateway/src/sam_rest_gateway/component.py`:** This file will see the most significant changes.
    *   All `solace_agent_mesh.common.types` imports will be replaced with `a2a.types`.
    *   `_translate_external_input` will be updated to create `a2a.types.FileWithUri` and wrap parts correctly.
    *   `_send_update_to_external` will be updated to use the new event types and field names (`taskId`).
    *   `_send_final_response_to_external` will be updated to handle the new `a2a.types.Task` structure.
    *   `_send_error_to_external` will be updated to use `a2a.types.JSONRPCError`.

*   **`sam-rest-gateway/src/sam_rest_gateway/dependencies.py`:**
    *   The imports for `JSONRPCResponse`, `InternalError`, and `InvalidRequestError` will be changed from `solace_agent_mesh.common.types` to `a2a.types`.

*   **`sam-rest-gateway/src/sam_rest_gateway/routers/artifacts.py`:**
    *   No changes are required. The `ArtifactInfo` type it uses will remain in `solace_agent_mesh.common.types`.

*   **Other Files (`app.py`, `main.py`, `routers/v1.py`, `routers/v2.py`):**
    *   No changes are required as these files are sufficiently abstracted from the A2A data models.

## 5. Testing Strategy

*   The test suite will be updated to use the new `a2a.types` models for creating mock agent responses.
*   Assertions in integration tests will be modified to validate the API responses, which are derived from the new `Task` and `JSONRPCError` structures.
*   The `A2AMessageValidator` (in `test_support`) will be relied upon to ensure all mock payloads sent to the gateway conform to the official `a2a.json` schema.
