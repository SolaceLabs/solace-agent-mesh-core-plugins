# A2A SDK Migration: REST Gateway Implementation Plan

## 1. Introduction

This document provides a step-by-step implementation plan for developers to execute the refactoring of the REST Gateway, as outlined in the corresponding design document. The goal is to migrate from the legacy A2A types to the official `a2a-sdk` and standardize A2A message structures.

## 2. Pre-requisites

Before starting, ensure the following are complete:
- The `a2a-sdk` is installed as a project dependency.
- The local `a2a.json` schema is synchronized with the installed SDK version.
- The `A2AMessageValidator` in the test suite has been updated to use the new schema.

## 3. Implementation Steps

### File: `sam-rest-gateway/src/sam_rest_gateway/dependencies.py`

1.  **Update Imports:**
    -   Locate the import block for `solace_agent_mesh.common.types`.
    -   This will be handled in a later step when we refactor `main.py`.

### File: `sam-rest-gateway/src/sam_rest_gateway/main.py`

2.  **Update Imports:**
    -   Locate the import block for `solace_agent_mesh.common.types`.
    -   Remove the line: `from solace_agent_mesh.common.types import JSONRPCResponse as A2AJSONRPCResponse, InternalError, InvalidRequestError`.
    -   Add the new line: `from a2a.types import JSONRPCErrorResponse as A2AJSONRPCErrorResponse, InternalError, InvalidRequestError`.

### File: `sam-rest-gateway/src/sam_rest_gateway/component.py`

3.  **Update All A2A Type Imports:**
    -   Go through the import section at the top of the file.
    -   Remove the entire import block from `solace_agent_mesh.common.types`.
    -   Add the corresponding imports from `a2a.types`. This will include: `Part as A2APart`, `Task`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`, `JSONRPCError`, `TextPart`, `FilePart`, `FileWithUri`, and `Artifact as A2AArtifact`.

4.  **Refactor `_translate_external_input`:**
    -   In the section that handles file uploads (`if files and self.shared_artifact_service:`).
    -   Locate the line: `a2a_parts.append(FilePart(file=FileContent(name=upload_file.filename, uri=uri)))`.
    -   Modify it to create a `FileWithUri` object and wrap the `FilePart` inside the `A2APart` root model: `a2a_parts.append(A2APart(root=FilePart(file=FileWithUri(name=upload_file.filename, uri=uri))))`.
    -   Locate the line: `a2a_parts.append(TextPart(text=prompt))`.
    -   Modify it to wrap the `TextPart` inside the `A2APart` root model: `a2a_parts.append(A2APart(root=TextPart(text=prompt)))`.

5.  **Refactor `_send_update_to_external`:**
    -   Update the method signature's type hint for `event_data` to `Union[TaskStatusUpdateEvent, TaskArtifactUpdateEvent]`.
    -   Change the task ID access from `task_id = event_data.id` to `task_id = event_data.task_id`.

6.  **Refactor `_send_final_response_to_external`:**
    -   Update the method signature's type hint for the `task_data` parameter to `a2a.types.Task`.
    -   The internal logic should not require changes, as it operates on `model_dump()` and the `Artifact` structure is compatible.

7.  **Refactor `_send_error_to_external`:**
    -   Update the method signature's type hint for the `error_data` parameter to `a2a.types.JSONRPCError`.
    -   The internal logic should not require changes.

## 4. Verification

-   After completing the steps, perform a full search across the `sam-rest-gateway` module for any remaining imports from `solace_agent_mesh.common.types` and remove them.
-   Run the project's linter/type-checker to catch any inconsistencies.
-   The test suite is expected to fail. The next phase of work will be to update the tests to align with this new implementation.
