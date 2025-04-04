# Agent Templating Testing Checklist

This checklist covers testing the changes made to agent configuration templating for easier multi-instance setup. Test each agent type that was modified (`sam-mcp-server`, `sam-geo-information`, `sam-mermaid`, `sam-mongodb`, `solace-event-mesh`).

## General Tests (Apply to each modified agent type)

1.  **Instantiation via `add agent` Command:**
    *   [ ] Run `solace-agent-mesh add agent test_<agent_type> --copy-from <plugin_name>:<template_name>` (e.g., `solace-agent-mesh add agent test_mongo --copy-from sam_mongodb:mongodb`).
    *   [ ] Verify `configs/agents/test_<agent_type>.yaml` is created.
    *   [ ] Inspect the created YAML file:
        *   [ ] Check that `{{SNAKE_CASE_NAME}}` is replaced with `test_<agent_type>`.
        *   [ ] Check that `{{SNAKE_UPPER_CASE_NAME}}` is replaced with `TEST_<AGENT_TYPE>`.
        *   [ ] Check that environment variable placeholders use the correct uppercase prefix (e.g., `${TEST_<AGENT_TYPE>_...}`).

2.  **Environment Variable Handling (using the `add agent` instance):**
    *   [ ] Set **required** environment variables using the new convention (e.g., `export TEST_<AGENT_TYPE>_VAR=value`).
    *   [ ] Start SAM with the new agent instance enabled.
    *   [ ] Verify the agent starts without errors related to missing required configuration.
    *   [ ] If applicable, set **optional** environment variables (e.g., API keys, descriptions, timeouts) using the new convention.
    *   [ ] Restart SAM and verify the agent picks up the optional settings (check logs or agent summary/behavior).
    *   [ ] If applicable, unset optional environment variables that have defaults.
    *   [ ] Restart SAM and verify the agent uses the default values correctly.

3.  **Basic Agent Functionality (using the `add agent` instance):**
    *   [ ] Perform a simple, core action specific to the agent type to ensure basic operation.
        *   `sam-mcp-server`: Connect to a server, invoke a basic tool/resource action.
        *   `sam-geo-information`: Use `city_to_coordinates` or `get_weather`.
        *   `sam-mermaid`: Use the `draw` action.
        *   `sam-mongodb`: Use `search_query` (ensure schema detection/loading works if applicable).
        *   `solace-event-mesh`: Use a configured request/reply action.
    *   [ ] Check SAM logs for any errors during the action.

4.  **Agent Summary/Registration:**
    *   [ ] Check how the agent registers with the orchestrator (if used) or inspect its `get_agent_summary()` output.
    *   [ ] Verify the `agent_name` matches the instance name (`test_<agent_type>`).
    *   [ ] Verify the agent's `description` is correctly populated (potentially including the instance name or purpose).

## Single Instance Tests (Apply where relevant, e.g., `sam-mermaid`, `solace-event-mesh`)

5.  **Instantiation via `solace-agent-mesh.yaml`:**
    *   [ ] Ensure the agent is loaded directly in `solace-agent-mesh.yaml` using its default config name (e.g., `mermaid`, `solace_event_mesh`).
    *   [ ] Set required environment variables using the **default** uppercase prefix (e.g., `export MERMAID_MERMAID_SERVER_URL=...`).
    *   [ ] Start SAM.
    *   [ ] Verify the agent starts correctly using the default configuration file (`configs/agents/<default_name>.yaml`).
    *   [ ] Perform a basic functional test (as in step 3) for this default instance.
    *   [ ] Check the agent summary: verify `agent_name` matches the default name.

## Documentation Review

6.  **README Check:**
    *   [ ] Briefly review the `README.md` for each modified agent.
    *   [ ] Verify the instructions for both `add agent` and `solace-agent-mesh.yaml` instantiation methods are clear and accurate.
    *   [ ] Verify the environment variable naming convention is correctly explained for both methods.

## Agent-Specific Notes

*   **sam-mongodb:** Pay close attention to schema detection/loading. Test with `AUTO_DETECT_SCHEMA=true` (default) and `AUTO_DETECT_SCHEMA=false` (requires manual schema or will raise an error).
*   **solace-event-mesh:** Ensure the dynamically created actions based on the `actions:` list in the config work correctly for both instantiation methods.
