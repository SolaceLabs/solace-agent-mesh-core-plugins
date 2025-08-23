# A2A Helper Layer: ContentPart Migration Checklist

This checklist tracks the implementation of the `ContentPart` refactoring across all gateway components.

## Phase 1: REST Gateway (`src/sam_rest_gateway/component.py`)

- [x] **Update Imports:**
    - [x] Remove `Part as A2APart` from `a2a.types` import.
    - [x] Add `ContentPart` to `solace_agent_mesh.common.a2a` import.
- [x] **Refactor `_translate_external_input`:**
    - [x] Update method signature to return `List[ContentPart]`.
    - [x] Update `a2a_parts` local variable to be `List[ContentPart]`.
    - [x] Remove `a2a.create_part()` calls.
- [x] **Refactor `submit_a2a_task`:**
    - [x] Update `a2a_parts` parameter to be `List[ContentPart]`.

## Phase 2: Slack Gateway (`src/sam_slack/component.py`)

- [x] **Update Imports:**
    - [x] Remove `Part as A2APart` from `a2a.types` import.
    - [x] Add `ContentPart` to `solace_agent_mesh.common.a2a` import.
- [x] **Refactor `_translate_external_input`:**
    - [x] Update method signature to return `List[ContentPart]`.
    - [x] Update `a2a_parts` local variable to be `List[ContentPart]`.
- [x] **Refactor `_send_final_response_to_external`:**
    - [x] Update `all_final_parts` local variable to be `List[ContentPart]`.

## Phase 3: Event Mesh Gateway (`src/sam_event_mesh_gateway/component.py`)

- [x] **Update Imports:**
    - [x] Add `ContentPart` to `solace_agent_mesh.common.a2a` import.
- [x] **Refactor `_translate_external_input`:**
    - [x] Update method signature to return `List[ContentPart]`.
    - [x] Update `a2a_parts` local variable to be `List[ContentPart]`.

## Phase 4: Webhook Gateway (`src/sam_webhook_gateway/component.py`)

- [x] **Update Imports:**
    - [x] Remove `Part as A2APart` from `a2a.types` import.
    - [x] Add `ContentPart` to `solace_agent_mesh.common.a2a` import.
- [x] **Refactor `_translate_external_input`:**
    - [x] Update method signature to return `List[ContentPart]`.
    - [x] Update `a2a_parts` local variable to be `List[ContentPart]`.
    - [x] Remove `a2a.create_part()` call.

## Phase 5: Verification

- [ ] **Global Search:** Confirm no instances of `a2a.create_part()` remain in the codebase.
- [ ] **Static Analysis:** Run `mypy` and linters to ensure type consistency.
- [ ] **Integration Testing:** Run the full integration test suite for all gateways.
