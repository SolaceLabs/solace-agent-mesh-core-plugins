# A2A SDK Migration: REST Gateway Implementation Checklist

This checklist provides a terse summary of the tasks required to complete the REST Gateway refactoring, as detailed in the implementation plan.

## Phase 1: Dependencies and Entrypoint Refactoring

- [x] **1. Update `main.py` Imports:**
    - [x] Change `solace_agent_mesh.common.types` imports to `a2a.types` for `JSONRPCErrorResponse`, `InternalError`, and `InvalidRequestError`.

## Phase 2: Core Component Refactoring (`component.py`)

- [x] **2. Update All A2A Type Imports:**
    - [x] Remove all imports from `solace_agent_mesh.common.types`.
    - [x] Add corresponding imports from `a2a.types` (`Part as A2APart`, `Task`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`, `JSONRPCError`, `TextPart`, `FilePart`, `FileWithUri`, `Artifact as A2AArtifact`).

- [x] **3. Refactor `_translate_external_input`:**
    - [x] Replace `FileContent` instantiation with `a2a.types.FileWithUri`.
    - [x] Ensure all created `TextPart` and `FilePart` objects are wrapped in `A2APart(root=...)`.

- [ ] **4. Refactor `_send_update_to_external`:**
    - [ ] Update `event_data` parameter type hint to `Union[TaskStatusUpdateEvent, TaskArtifactUpdateEvent]`.
    - [ ] Change task ID access from `event_data.id` to `event_data.task_id`.

- [ ] **5. Refactor `_send_final_response_to_external`:**
    - [ ] Update `task_data` parameter type hint to `a2a.types.Task`.

- [ ] **6. Refactor `_send_error_to_external`:**
    - [ ] Update `error_data` parameter type hint to `a2a.types.JSONRPCError`.

## Phase 3: Verification

- [ ] **7. Final Code Sweep:** Search the entire `sam-rest-gateway` module for any remaining imports from `solace_agent_mesh.common.types` and eliminate them.
- [ ] **8. Static Analysis:** Run the project's linter and type-checker to identify and fix any inconsistencies.
- [ ] **9. Acknowledge Next Steps:** Confirm that the implementation is complete and that the next phase will involve updating the test suite to validate these changes.
