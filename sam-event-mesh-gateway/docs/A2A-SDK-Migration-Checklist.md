# A2A SDK Migration: Event Mesh Gateway Implementation Checklist

This checklist provides a terse summary of the tasks required to complete the Event Mesh Gateway refactoring, as detailed in the implementation plan.

## Phase 1: Core Component Refactoring (`component.py`)

- [x] **1. Update All A2A Type Imports:**
    - [x] Remove all imports from `solace_agent_mesh.common.types`.
    - [x] Add corresponding imports from `a2a.types` (`Part as A2APart`, `TextPart`, `FilePart`, `DataPart`, `Task`, `JSONRPCError`, `FileWithUri`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`).

- [x] **2. Refactor `_translate_external_input`:**
    - [x] Replace `FileContent` instantiation with `a2a.types.FileWithUri`.
    - [x] Ensure all created `TextPart` and `FilePart` objects are wrapped in `A2APart(root=...)`.

- [x] **3. Refactor `_process_file_part_for_output`:**
    - [x] Change `part.file.mimeType` to `part.file.mime_type`.

- [x] **4. Confirm Method Signature Updates:**
    - [x] Verify that type hints for `_send_final_response_to_external`, `_send_error_to_external`, and `_send_update_to_external` are implicitly updated by the import changes.

## Phase 2: Verification

- [ ] **5. Final Code Sweep:** Search the entire `sam-event-mesh-gateway` module for any remaining imports from `solace_agent_mesh.common.types` and eliminate them.
- [ ] **6. Static Analysis:** Run the project's linter and type-checker to identify and fix any inconsistencies.
- [ ] **7. Acknowledge Next Steps:** Confirm that the implementation is complete and that the next phase will involve updating the test suite to validate these changes.
