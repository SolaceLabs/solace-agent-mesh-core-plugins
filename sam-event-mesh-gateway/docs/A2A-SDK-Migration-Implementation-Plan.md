# A2A SDK Migration: Event Mesh Gateway Implementation Plan

## 1. Introduction

This document provides a step-by-step implementation plan for developers to execute the refactoring of the Event Mesh Gateway, as outlined in the corresponding design document. The goal is to migrate from the legacy A2A types to the official `a2a-sdk` and standardize A2A message structures.

## 2. Pre-requisites

Before starting, ensure the following are complete:
- The `a2a-sdk` is installed as a project dependency.
- The local `a2a.json` schema is synchronized with the installed SDK version.
- The `A2AMessageValidator` in the test suite has been updated to use the new schema.

## 3. Implementation Steps

All changes will be made within the file `sam-event-mesh-gateway/src/sam_event_mesh_gateway/component.py`.

1.  **Update All A2A Type Imports:**
    -   Locate the import block for `solace_agent_mesh.common.types`.
    -   Remove the entire block: `from solace_agent_mesh.common.types import Part as A2APart, TextPart, FilePart, DataPart, Task, JSONRPCError, FileContent`.
    -   Add the new import block from `a2a.types`: `from a2a.types import Part as A2APart, TextPart, FilePart, DataPart, Task, JSONRPCError, FileWithUri, TaskStatusUpdateEvent, TaskArtifactUpdateEvent`.

2.  **Refactor `_translate_external_input` Method:**
    -   In the section that processes created artifact URIs.
    -   Locate the line: `file_content = FileContent(name=filename, uri=uri)`.
    -   Modify it to create a `FileWithUri` object: `file_content = FileWithUri(name=filename, uri=uri)`.
    -   Locate the line: `a2a_parts.append(FilePart(file=file_content))`.
    -   Modify it to wrap the `FilePart` inside the `A2APart` root model: `a2a_parts.append(A2APart(root=FilePart(file=file_content)))`.
    -   Locate the line: `a2a_parts.append(TextPart(text=str(transformed_text)))`.
    -   Modify it to wrap the `TextPart` inside the `A2APart` root model: `a2a_parts.append(A2APart(root=TextPart(text=str(transformed_text))))`.

3.  **Refactor `_process_file_part_for_output` Method:**
    -   Locate the line: `file_info["mimeType"] = part.file.mimeType`.
    -   Modify it to use the correct field name from the new model: `file_info["mimeType"] = part.file.mime_type`.

4.  **Update Method Signature Type Hints:**
    -   The type hints for `_send_final_response_to_external`, `_send_error_to_external`, and `_send_update_to_external` will be implicitly corrected by the import changes made in Step 1. No direct code changes are needed for the signatures themselves, but this confirms the design is being met.

## 4. Verification

-   After completing the steps, perform a full search across the `sam-event-mesh-gateway` module for any remaining imports from `solace_agent_mesh.common.types` and remove them.
-   Run the project's linter/type-checker to catch any inconsistencies.
-   The test suite is expected to fail. The next phase of work will be to update the tests to align with this new implementation.
