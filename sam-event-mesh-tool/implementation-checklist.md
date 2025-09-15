# Implementation Checklist: Event Mesh Tool Plugin

This checklist outlines the high-level steps required to refactor the `sam-event-mesh-agent` into the new `sam-event-mesh-tool` plugin.

## Phase 1: New Plugin Scaffolding & Definition

- [x] Create the directory structure for `sam-event-mesh-tool`.
- [x] Create the `src/sam_event_mesh_tool/` subdirectory and `__init__.py` file.
- [x] Create the `src/sam_event_mesh_tool/tools.py` file for the core implementation.
- [x] Create and populate `pyproject.toml` with project metadata, dependencies (`solace-agent-mesh`, `solace-ai-connector`), and the `sam.plugins` entry point.

## Phase 2: Core Tool Implementation (`EventMeshTool`)

- [ ] In `tools.py`, create the `EventMeshTool` class inheriting from `DynamicTool`.
- [ ] Implement the `__init__` method to store `tool_config` and initialize `self.session_id`.
- [ ] Implement the `init` lifecycle method to call `create_request_response_session` and store the resulting `session_id`.
- [ ] Implement the `cleanup` lifecycle method to call `destroy_request_response_session`.
- [ ] Implement the `tool_name` and `tool_description` properties to read from the configuration.
- [ ] Implement the `parameters_schema` property to programmatically generate the ADK schema from the `parameters` list in the YAML config.
- [ ] Implement the `_run_async_impl` method with the core request-response logic, using `do_broker_request_response_async`.
- [ ] Adapt helper functions (`_build_payload`, `_fill_topic_template`) from the legacy agent into `tools.py`.

## Phase 3: Documentation & Configuration

- [ ] Create `sam-event-mesh-tool/README.md` with comprehensive user documentation, including prerequisites and configuration examples.
- [ ] Create `sam-event-mesh-tool/config.yaml` with a well-commented example configuration for users to adapt.

## Phase 4: Deprecate and Remove Legacy Agent

- [ ] Update `sam-event-mesh-agent/README.md` with a prominent deprecation notice that directs users to the new `sam-event-mesh-tool`.
- [ ] Delete the core logic from `sam-event-mesh-agent/src/sam_event_mesh_agent/tools.py`.
- [ ] Clear the example configuration from `sam-event-mesh-agent/config.yaml`.
- [ ] Once the new tool is stable and released, remove the entire `sam-event-mesh-agent` directory from the repository.
