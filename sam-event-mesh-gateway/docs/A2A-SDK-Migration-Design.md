# A2A SDK Migration Design: Event Mesh Gateway

## 1. Overview

This document details the design for refactoring the Event Mesh Gateway (`sam-event-mesh-gateway`) to align with the latest official Agent-to-Agent (A2A) protocol specification. The core of this effort involves migrating from our legacy, custom A2A type definitions to the official `a2a-sdk` for Python.

The Event Mesh Gateway acts as a non-interactive bridge, translating messages from a generic event-driven architecture (the "data plane") into A2A tasks, and translating final A2A task results back into data plane events. This design focuses on updating the gateway's internal A2A message handling to use the new, standardized `a2a.types` models.

## 2. Goals

*   **Protocol Compliance:** Fully align the Event Mesh Gateway with the official A2A JSON specification.
*   **SDK Adoption:** Replace all bespoke A2A type implementations in the `sam-event-mesh-gateway` module with types from the `a2a-sdk`.
*   **Improved Maintainability:** Simplify the gateway's logic by relying on the `a2a-sdk` for data validation and structure, reducing technical debt.

## 3. Core Design Changes

### 3.1. Type System Migration

All A2A-related data models within the `sam-event-mesh-gateway` module will be replaced with their counterparts from the `a2a.types` library. The `BaseGatewayComponent` will deliver fully parsed and validated `a2a.types` objects to the component's handler methods.

**Key Type Mappings:**

| Legacy Model (`common/types.py`) | New Model (`a2a.types`) | Key Changes |
| --- | --- | --- |
| `Part` (Union) | `Part` (RootModel) | The discriminator field changes from `type` to `kind`. All created parts must be wrapped in the `Part` root model (e.g., `Part(root=TextPart(...))`). |
| `FileContent` | `FileWithUri` | The `FilePart.file` field now contains a `FileWithUri` object. |
| `Task` | `Task` | The structure is updated to match the official spec. |
| `JSONRPCError` | `JSONRPCError` | No structural change, but the import source will change. |

For a complete mapping, refer to the [A2A Type Migration Map](../../docs/refactoring/A2A-Type-Migration-Map.md).

### 3.2. Outgoing A2A Message Generation

The process of creating A2A tasks from incoming data plane messages will be updated to use the new types.

*   **Component:** `EventMeshGatewayComponent`
*   **Method:** `_translate_external_input`
*   **Design:**
    *   The method will continue to be responsible for creating a list of `A2APart` objects from the incoming Solace message.
    *   When creating file-based parts, it will now instantiate an `a2a.types.FileWithUri` object to populate the `file` field of an `a2a.types.FilePart`.
    *   All created `TextPart` and `FilePart` objects will be wrapped in the `A2APart` root model (e.g., `A2APart(root=FilePart(...))`).
    *   The `BaseGatewayComponent.submit_a2a_task` method will consume these parts and construct the final, compliant `SendMessageRequest`.

### 3.3. Incoming A2A Message Processing

The methods responsible for handling the final events from the agent will be refactored to understand the new `a2a.types` structures.

*   **Component:** `EventMeshGatewayComponent`
*   **Methods:** `_send_final_response_to_external`, `_send_error_to_external`
*   **Design:**
    *   The type hints for the `task_data` and `error_data` parameters will be updated to `a2a.types.Task` and `a2a.types.JSONRPCError` respectively.
    *   The internal logic for transforming the result and publishing it to the data plane will be updated to operate on the new Pydantic models.

### 3.4. Artifact Content Handling for Output

The helper method for processing file artifacts before publishing them to the data plane will be updated.

*   **Component:** `EventMeshGatewayComponent`
*   **Method:** `_process_file_part_for_output`
*   **Design:**
    *   The method's `part` parameter type hint will be updated to `a2a.types.FilePart`.
    *   The internal logic will be adjusted to access the MIME type via `part.file.mime_type` instead of `part.file.mimeType`.

## 4. Component-Level Impact

*   **`sam-event-mesh-gateway/src/sam_event_mesh_gateway/component.py`:** This is the only file that requires modification.
    *   All `solace_agent_mesh.common.types` imports will be replaced with `a2a.types`.
    *   `_translate_external_input` will be updated to create compliant `a2a.types` objects.
    *   `_process_file_part_for_output` will be updated to use the new `FilePart` structure.
    *   `_send_final_response_to_external` and `_send_error_to_external` will be updated to handle the new `Task` and `JSONRPCError` models.

*   **Other Files (`app.py`, `__init__.py`):**
    *   No changes are required as these files are sufficiently abstracted from the A2A data models.

## 5. Testing Strategy

*   The test suite for the Event Mesh Gateway will be updated to use the new `a2a.types` models for creating mock agent responses.
*   Assertions in integration tests will be modified to validate the structure and content of the outgoing Solace messages produced by the gateway's output handlers.
