# A2A SDK Migration: Slack Gateway Implementation Plan

## 1. Introduction

This document provides a step-by-step implementation plan for developers to execute the refactoring of the Slack Gateway, as outlined in the corresponding design document. The goal is to migrate from the legacy A2A types to the official `a2a-sdk` and standardize status update communication.

## 2. Pre-requisites

Before starting, ensure the following are complete:
- The `a2a-sdk` is installed as a project dependency.
- The local `a2a.json` schema is synchronized with the installed SDK version.
- The `A2AMessageValidator` in the test suite has been updated to use the new schema.

## 3. Implementation Steps

### File: `sam_slack/utils.py`

1.  **Update Imports:**
    -   Locate the import `from solace_agent_mesh.common.types import DataPart`.
    -   Change it to `from a2a.types import DataPart`.

2.  **Refactor `format_data_part_for_slack`:**
    -   This function's role is changing. It will no longer handle specific status signals.
    -   Remove the entire `if data_part.data.get("a2a_signal_type") == "agent_status_message":` block.
    -   The function will now act as a generic fallback for displaying any unexpected `DataPart` as a formatted JSON block. The existing logic for this (JSON dumping and header creation) is sufficient.
    -   Update the function's type hint to `def format_data_part_for_slack(data_part: DataPart) -> str:`.

### File: `sam_slack/component.py`

3.  **Update All A2A Type Imports:**
    -   Go through the import section at the top of the file.
    -   Remove all imports from `solace_agent_mesh.common.types`.
    -   Add the corresponding imports from `a2a.types`. This will include `Part as A2APart`, `TextPart`, `FilePart`, `DataPart`, `FileWithUri`, `FileWithBytes`, `Task`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`, `JSONRPCError`, and `TaskState`.
    -   Add imports for the new status data models: `from ...common.data_parts import AgentProgressUpdateData, ArtifactCreationProgressData`.

4.  **Refactor `_translate_external_input`:**
    -   In the section that handles file uploads (`if files_info and self.shared_artifact_service:`).
    -   Locate the line `file_content_a2a = FileContent(...)`.
    -   Replace it to create an `a2a.types.FileWithUri` instance: `file_content_a2a = FileWithUri(name=original_filename, mime_type=mime_type, uri=artifact_uri)`.
    -   Locate the line `a2a_parts.append(FilePart(file=file_content_a2a))`.
    -   Modify it to wrap the `FilePart` inside the `A2APart` root model: `a2a_parts.append(A2APart(root=FilePart(file=file_content_a2a)))`.
    -   Ensure the `TextPart` creation is also wrapped: `a2a_parts.append(A2APart(root=TextPart(text=processed_text_for_a2a)))`.

5.  **Refactor `_send_error_to_external`:**
    -   Update the method signature's type hint for the `error_data` parameter to `a2a.types.JSONRPCError`.
    -   The internal logic should not require changes, as the field names are consistent.

6.  **Refactor `_send_final_response_to_external`:**
    -   Update the method signature's type hint for the `task_data` parameter to `a2a.types.Task`.
    -   Verify that all accesses to the task ID use `task_data.id`.
    -   Verify that checks for the task's state use the imported `a2a.types.TaskState` enum (e.g., `TaskState.FAILED`).

7.  **Refactor `_send_update_to_external` (Major Change):**
    -   Update the method signature's type hint for `event_data` to `Union[TaskStatusUpdateEvent, TaskArtifactUpdateEvent]`.
    -   Change the task ID access from `event_data.id` to `event_data.task_id`.
    -   **Handle `TaskStatusUpdateEvent`:**
        -   Inside the `isinstance(event_data, TaskStatusUpdateEvent)` block, iterate through `event_data.status.message.parts`.
        -   For each `part_wrapper` in the list, get the actual part object: `part = part_wrapper.root`.
        -   Check `isinstance(part, TextPart)` and `isinstance(part, DataPart)`.
        -   **Remove the old signal handling:** Delete the logic that checks `part.data.get("a2a_signal_type")`.
        -   **Add new signal handling:** If the part is a `DataPart`, get its `type` from `part.data.get("type")`.
            -   If `type == "agent_progress_update"`, validate the payload using `AgentProgressUpdateData.model_validate(part.data)` and format the `status_text` into `status_signal_text` (e.g., `f":thinking_face: {progress_data.status_text}"`).
            -   If `type == "artifact_creation_progress"`, validate using `ArtifactCreationProgressData` and format the text (e.g., `f":floppy_disk: Creating artifact \`{progress_data.filename}\`..."`).
            -   Wrap these parsing blocks in `try...except` blocks to handle potential validation errors gracefully.
    -   **Handle `TaskArtifactUpdateEvent`:**
        -   Inside the `isinstance(event_data, TaskArtifactUpdateEvent)` block, iterate through `event_data.artifact.parts`.
        -   For each `part_wrapper`, get the part: `part = part_wrapper.root`.
        -   If `isinstance(part, FilePart)`, the `part.file` attribute is now a union.
        -   Use `isinstance(part.file, FileWithBytes)` and `isinstance(part.file, FileWithUri)` to determine the type and access the `bytes` or `uri` field correctly.

8.  **Review `resolve_and_format_for_slack`:**
    -   This method is now located inside `SlackGatewayComponent`.
    -   The logic for constructing `session_context_data` is critical for embed resolution. Verify that it correctly uses `generate_a2a_session_id`.
    -   The method `resolve_embeds_in_string` is called via `asyncio.to_thread`. This is a recent change and should be correct. No further changes are anticipated here, but a review is prudent.

## 4. Verification

-   After completing the steps, perform a full search across the `sam-slack` module for any remaining imports from `solace_agent_mesh.common.types` and remove them.
-   Run the project's linter/type-checker to catch any inconsistencies.
-   The test suite is expected to fail. The next phase of work will be to update the tests to align with this new implementation.
