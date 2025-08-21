# A2A SDK Migration: Webhook Gateway Implementation Plan

## 1. Introduction

This document provides a step-by-step implementation plan for developers to execute the refactoring of the Universal Webhook Gateway, as outlined in the corresponding design document. The goal is to migrate from the legacy A2A types to the official `a2a-sdk` and standardize A2A message structures.

## 2. Pre-requisites

Before starting, ensure the following are complete:
- The `a2a-sdk` is installed as a project dependency.
- The local `a2a.json` schema is synchronized with the installed SDK version.
- The `A2AMessageValidator` in the test suite has been updated to use the new schema.

## 3. Implementation Steps

### File: `sam-webhook-gateway/src/sam_webhook_gateway/main.py`

1.  **Update Error Type Imports:**
    -   Locate the import block for `solace_agent_mesh.common.types`.
    -   Remove the line: `from solace_agent_mesh.common.types import JSONRPCError, InternalError, InvalidRequestError`.
    -   Add the new line: `from a2a.types import JSONRPCError, InternalError, InvalidRequestError`.

### File: `sam-webhook-gateway/src/sam_webhook_gateway/component.py`

2.  **Update All A2A Type Imports:**
    -   Locate the import block for `solace_agent_mesh.common.types`.
    -   Remove the entire block: `from solace_agent_mesh.common.types import Part as A2APart, TextPart, Task, TaskStatusUpdateEvent, TaskArtifactUpdateEvent, JSONRPCError`.
    -   Add the new import block from `a2a.types`: `from a2a.types import Part as A2APart, TextPart, Task, TaskStatusUpdateEvent, TaskArtifactUpdateEvent, JSONRPCError`.

3.  **Refactor `_translate_external_input` Method:**
    -   Locate the line: `a2a_parts.append(TextPart(text=str(templated_text)))`.
    -   Modify it to wrap the `TextPart` inside the `A2APart` root model: `a2a_parts.append(A2APart(root=TextPart(text=str(templated_text))))`.

4.  **Update Method Signature Type Hints:**
    -   Update the signature for `_send_update_to_external` to change the type hint for the `event_data` parameter from `Any` to `Union[TaskStatusUpdateEvent, TaskArtifactUpdateEvent]`.
    -   The type hints for `_send_final_response_to_external` and `_send_error_to_external` will be implicitly corrected by the import changes made in Step 2. No direct code changes are needed for these signatures, but this confirms the design is being met.

## 4. Verification

-   After completing the steps, perform a full search across the `sam-webhook-gateway` module for any remaining imports from `solace_agent_mesh.common.types` and remove them.
-   Run the project's linter/type-checker to catch any inconsistencies.
-   The test suite is expected to fail. The next phase of work will be to update the tests to align with this new implementation.
