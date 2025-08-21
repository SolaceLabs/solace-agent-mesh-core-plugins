# A2A SDK Migration: Slack Gateway Implementation Checklist

This checklist provides a terse summary of the tasks required to complete the Slack Gateway refactoring, as detailed in the implementation plan.

## Phase 1: `utils.py` Refactoring

- [x] **1. Update Imports:** Change `solace_agent_mesh.common.types.DataPart` to `a2a.types.DataPart`.
- [x] **2. Refactor `format_data_part_for_slack`:**
    - [x] Remove the specific `agent_status_message` signal handling logic.
    - [x] Ensure the function acts as a generic JSON fallback for unexpected `DataPart` types.
    - [x] Update the function's type hint to use `a2a.types.DataPart`.

## Phase 2: `component.py` Refactoring

- [x] **3. Update All A2A Type Imports:**
    - [x] Remove all imports from `solace_agent_mesh.common.types`.
    - [x] Add corresponding imports from `a2a.types`.
    - [x] Add imports for `AgentProgressUpdateData` and `ArtifactCreationProgressData` from `common.data_parts`.

- [x] **4. Refactor `_translate_external_input`:**
    - [x] Replace `FileContent` instantiation with `a2a.types.FileWithUri`.
    - [x] Ensure all created `TextPart` and `FilePart` objects are wrapped in `A2APart(root=...)`.

- [ ] **5. Refactor `_send_error_to_external`:**
    - [ ] Update the `error_data` parameter's type hint to `a2a.types.JSONRPCError`.

- [ ] **6. Refactor `_send_final_response_to_external`:**
    - [ ] Update the `task_data` parameter's type hint to `a2a.types.Task`.
    - [ ] Confirm all task ID access uses `task_data.id`.
    - [ ] Confirm task state checks use the `a2a.types.TaskState` enum.

- [ ] **7. Refactor `_send_update_to_external`:**
    - [ ] Update `event_data` parameter type hint to `Union[TaskStatusUpdateEvent, TaskArtifactUpdateEvent]`.
    - [ ] Change task ID access from `event_data.id` to `event_data.task_id`.
    - [ ] In the `TaskStatusUpdateEvent` block, replace `metadata`-based signal checks with `DataPart` parsing.
    - [ ] Implement logic to parse `agent_progress_update` and `artifact_creation_progress` data parts using the new Pydantic models.
    - [ ] In the `TaskArtifactUpdateEvent` block, update logic to handle the `part.file` union (`FileWithBytes` vs. `FileWithUri`).

- [ ] **8. Review `resolve_and_format_for_slack`:**
    - [ ] Confirm the logic for constructing `session_context_data` is correct.
    - [ ] Verify that the call to `resolve_embeds_in_string` remains correct.

## Phase 3: Verification

- [ ] **9. Final Code Sweep:** Search the entire `sam-slack` module for any remaining imports from `solace_agent_mesh.common.types` and eliminate them.
- [ ] **10. Static Analysis:** Run the project's linter and type-checker to identify and fix any inconsistencies.
- [ ] **11. Acknowledge Next Steps:** Confirm that the implementation is complete and that the next phase will involve updating the test suite to validate these changes.
