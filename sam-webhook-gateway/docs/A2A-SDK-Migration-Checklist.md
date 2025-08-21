# A2A SDK Migration: Webhook Gateway Implementation Checklist

This checklist provides a terse summary of the tasks required to complete the Webhook Gateway refactoring, as detailed in the implementation plan.

## Phase 1: Entrypoint and Core Component Refactoring

- [x] **1. Update `main.py` Imports:**
    - [x] Change `solace_agent_mesh.common.types` imports to `a2a.types` for `JSONRPCError`, `InternalError`, and `InvalidRequestError`.

- [x] **2. Update `component.py` A2A Type Imports:**
    - [x] Remove all imports from `solace_agent_mesh.common.types`.
    - [x] Add corresponding imports from `a2a.types` (`Part as A2APart`, `TextPart`, `Task`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`, `JSONRPCError`).

- [x] **3. Refactor `_translate_external_input` in `component.py`:**
    - [x] Ensure the created `TextPart` object is wrapped in `A2APart(root=...)`.

- [x] **4. Update Method Signatures in `component.py`:**
    - [x] Update `_send_update_to_external` parameter `event_data` type hint to `Union[TaskStatusUpdateEvent, TaskArtifactUpdateEvent]`.
    - [x] Verify that type hints for `_send_final_response_to_external` and `_send_error_to_external` are implicitly updated by the import changes.

## Phase 2: Verification

- [x] **5. Final Code Sweep:** Search the entire `sam-webhook-gateway` module for any remaining imports from `solace_agent_mesh.common.types` and eliminate them.
- [ ] **6. Static Analysis:** Run the project's linter and type-checker to identify and fix any inconsistencies.
- [ ] **7. Acknowledge Next Steps:** Confirm that the implementation is complete and that the next phase will involve updating the test suite to validate these changes.
