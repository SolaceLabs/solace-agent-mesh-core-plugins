# A2A Helper Layer Refactoring: ContentPart Migration Plan

## 1. Overview

This document provides a detailed implementation plan for refactoring all gateway components to align with the latest `solace-agent-mesh` A2A helper layer design. This refactoring has two primary goals:

1.  **Adopt the `ContentPart` Type Alias:** Replace all instances of the verbose `Union[TextPart, DataPart, FilePart]` type hint with the cleaner `a2a.ContentPart` alias, which is exposed by the helper library.
2.  **Eliminate Manual Part Wrapping:** Remove all remaining calls to `a2a.create_part()`. The helper layer is now solely responsible for this logic, and the gateways must only create and pass lists of *unwrapped* parts.

This effort will improve code clarity, enhance maintainability, and ensure all gateways are consistently using the helper layer as intended.

## 2. Guiding Principles

-   **Use `ContentPart`:** All type hints for lists of unwrapped A2A parts must use `List[ContentPart]`.
-   **Import from the Facade:** The `ContentPart` alias should be imported directly from the `solace_agent_mesh.common.a2a` facade.
-   **No Manual Wrapping:** All calls to `a2a.create_part()` must be removed. The application code should never be responsible for wrapping `TextPart`, `DataPart`, or `FilePart` objects.
-   **Consistent Signatures:** All `_translate_external_input` methods across the gateways must be updated to reflect the new `List[ContentPart]` return type.

## 3. Component-by-Component Implementation Plan

### 3.1. REST Gateway (`sam-rest-gateway`)

**File:** `src/sam_rest_gateway/component.py`

1.  **Update Imports:**
    -   Remove `Part as A2APart` from the `a2a.types` import.
    -   Add `ContentPart` to the `solace_agent_mesh.common.a2a` import.
2.  **Refactor `_translate_external_input`:**
    -   Change the method's return type hint to `Tuple[str, List[ContentPart], Dict[str, Any]]`.
    -   Change the type hint for the `a2a_parts` local variable to `List[ContentPart]`.
    -   Remove the `a2a.create_part()` call when appending `file_part`.
    -   Remove the `a2a.create_part()` call when appending `text_part`.
3.  **Refactor `submit_a2a_task`:**
    -   Change the type hint for the `a2a_parts` parameter to `List[ContentPart]`.

### 3.2. Slack Gateway (`sam-slack`)

**File:** `src/sam_slack/component.py`

1.  **Update Imports:**
    -   Remove `Part as A2APart` from the `a2a.types` import.
    -   Add `ContentPart` to the `solace_agent_mesh.common.a2a` import.
2.  **Refactor `_translate_external_input`:**
    -   Change the method's return type hint to `Tuple[str, List[ContentPart], Dict[str, Any]]`.
    -   Change the type hint for the `a2a_parts` local variable to `List[ContentPart]`.
3.  **Refactor `_send_final_response_to_external`:**
    -   Change the type hint for the `all_final_parts` local variable to `List[ContentPart]`.

### 3.3. Event Mesh Gateway (`sam-event-mesh-gateway`)

**File:** `src/sam_event_mesh_gateway/component.py`

1.  **Update Imports:**
    -   Add `ContentPart` to the `solace_agent_mesh.common.a2a` import.
2.  **Refactor `_translate_external_input`:**
    -   Change the method's return type hint to `Tuple[Optional[str], List[ContentPart], Dict[str, Any]]`.
    -   Change the type hint for the `a2a_parts` local variable to `List[ContentPart]`.

### 3.4. Webhook Gateway (`sam-webhook-gateway`)

**File:** `src/sam_webhook_gateway/component.py`

1.  **Update Imports:**
    -   Remove `Part as A2APart` from the `a2a.types` import.
    -   Add `ContentPart` to the `solace_agent_mesh.common.a2a` import.
2.  **Refactor `_translate_external_input`:**
    -   Change the method's return type hint to `Tuple[str, List[ContentPart], Dict[str, Any]]`.
    -   Change the type hint for the `a2a_parts` local variable to `List[ContentPart]`.
    -   Remove the `a2a.create_part()` call when appending `text_part`.

## 4. Verification

After all code changes are complete, the following steps must be taken to verify the refactoring:

1.  **Global Search:** Perform a project-wide search for `a2a.create_part` to ensure no instances remain.
2.  **Static Analysis:** Run the project's linter and type-checker (e.g., `mypy`) to catch any type inconsistencies introduced by the changes.
3.  **Integration Testing:** Execute the full integration test suite for all gateways to ensure that functionality remains unchanged from a user's perspective.
