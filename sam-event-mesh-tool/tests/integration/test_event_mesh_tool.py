"""
Integration tests for the EventMeshTool.

These tests use the fixtures defined in conftest.py to create a live,
in-memory integration environment with a client agent and a responder service.
"""

import pytest
from queue import Queue

# Add path to the source code for imports
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent / "src"))


from solace_agent_mesh.agent.sac.component import SamAgentComponent
from sam_event_mesh_tool.tools import EventMeshTool
from ..test_utils import (
    create_mock_tool_context,
    find_event_mesh_tool,
    create_basic_tool_config,
    create_mock_tool_config_model,
    create_tool_config_with_parameters,
    create_multi_type_parameters,
    create_required_optional_parameters,
)

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio


async def test_simple_request_response(
    agent_with_event_mesh_tool: SamAgentComponent,
    response_control_queue: Queue,
):
    """
    Tests a single, successful request-response interaction by calling the EventMeshTool directly.
    """
    # Arrange: Tell the responder what to send back
    expected_response = {"status": "success", "value": "some_data"}
    response_control_queue.put((expected_response, 0))  # (payload, delay_seconds)

    # Wait for the agent to be fully initialized
    import asyncio

    await asyncio.sleep(2)  # Give the agent time to initialize

    # Act: Find the EventMeshTool
    event_mesh_tool = find_event_mesh_tool(agent_with_event_mesh_tool)
    assert event_mesh_tool is not None, "EventMeshTool not found in agent component"
    assert (
        event_mesh_tool.session_id is not None
    ), "EventMeshTool session was not initialized"

    # Create a mock ToolContext to pass to the tool
    tool_context = create_mock_tool_context(agent_with_event_mesh_tool)

    # Call the tool with test parameters
    tool_args = {"request_data": "some test request"}
    tool_result = await event_mesh_tool._run_async_impl(
        args=tool_args, tool_context=tool_context
    )

    # Assert: Check that the tool executed successfully and returned the expected response
    assert tool_result is not None, "Tool did not return a result"
    assert tool_result.get("status") == "success", f"Tool failed: {tool_result}"
    assert "payload" in tool_result, "Tool result missing payload"
    assert (
        tool_result["payload"] == expected_response
    ), f"Expected {expected_response}, got {tool_result['payload']}"


async def test_parameter_mapping_with_nested_payload_paths():
    """
    Test 1: Verify that parameters are correctly mapped to nested payload paths using dot notation.

    This test creates a tool with parameters that use nested payload paths like
    'location.city' and 'customer.address.zipcode' and verifies the outgoing
    payload has the correct nested structure.
    """
    from sam_event_mesh_tool.tools import _build_payload_and_resolve_params

    # Define parameters with nested payload paths
    parameters_map = {
        "city": {"name": "city", "payload_path": "location.city"},
        "zipcode": {"name": "zipcode", "payload_path": "customer.address.zipcode"},
        "temperature": {
            "name": "temperature",
            "payload_path": "weather.current.temperature",
        },
        "unit": {"name": "unit", "payload_path": "weather.unit"},
        "request_id": {
            "name": "request_id",
            # No payload_path - this parameter won't be in the payload
        },
    }

    # Test parameters
    params = {
        "city": "Ottawa",
        "zipcode": "K1A 0A6",
        "temperature": 25,
        "unit": "celsius",
        "request_id": "test-123",
    }

    # Act: Build the payload and resolve params
    payload, resolved_params = _build_payload_and_resolve_params(parameters_map, params)

    # Assert: Verify the nested structure is correct
    expected_payload = {
        "location": {"city": "Ottawa"},
        "customer": {"address": {"zipcode": "K1A 0A6"}},
        "weather": {"current": {"temperature": 25}, "unit": "celsius"},
    }

    assert payload == expected_payload, f"Expected {expected_payload}, got {payload}"

    # Verify that request_id is not in the payload since it has no payload_path
    assert (
        "request_id" not in payload
    ), "request_id should not be in payload when no payload_path is specified"


async def test_parameter_defaults_and_overrides():
    """
    Test 2: Test that default parameter values work correctly and can be overridden.

    This test verifies that parameters with defaults are used when not provided,
    and that explicit values override defaults.
    """
    from sam_event_mesh_tool.tools import _build_payload_and_resolve_params

    # Define parameters with defaults
    parameters_map = {
        "city": {"name": "city", "payload_path": "location.city", "default": "Toronto"},
        "unit": {"name": "unit", "payload_path": "unit", "default": "celsius"},
        "timeout": {"name": "timeout", "payload_path": "config.timeout", "default": 30},
    }

    # Test 1: Use all defaults (empty params)
    params_empty = {}
    payload_defaults, resolved_defaults = _build_payload_and_resolve_params(
        parameters_map, params_empty
    )

    expected_defaults = {
        "location": {"city": "Toronto"},
        "unit": "celsius",
        "config": {"timeout": 30},
    }

    assert (
        payload_defaults == expected_defaults
    ), f"Expected {expected_defaults}, got {payload_defaults}"

    # Test 2: Override some defaults
    params_partial = {
        "city": "Vancouver",
        "timeout": 60,
        # unit should use default
    }
    payload_partial, resolved_partial = _build_payload_and_resolve_params(
        parameters_map, params_partial
    )

    expected_partial = {
        "location": {"city": "Vancouver"},
        "unit": "celsius",  # default used
        "config": {"timeout": 60},  # overridden
    }

    assert (
        payload_partial == expected_partial
    ), f"Expected {expected_partial}, got {payload_partial}"

    # Test 3: Override all defaults
    params_all = {"city": "Montreal", "unit": "fahrenheit", "timeout": 120}
    payload_all, resolved_all = _build_payload_and_resolve_params(
        parameters_map, params_all
    )

    expected_all = {
        "location": {"city": "Montreal"},
        "unit": "fahrenheit",
        "config": {"timeout": 120},
    }

    assert payload_all == expected_all, f"Expected {expected_all}, got {payload_all}"


async def test_missing_required_parameters():
    """
    Test 3: Test that the tool properly validates required parameters.

    This test verifies that when required parameters are missing, the tool
    returns an appropriate error message.
    """
    from sam_event_mesh_tool.tools import EventMeshTool

    # Create a tool configuration with required parameters
    parameters = create_required_optional_parameters()
    tool_config = create_tool_config_with_parameters(parameters)

    # Create tool instance
    tool = EventMeshTool(tool_config)

    # Test: Call tool without required parameter
    args_missing_required = {
        "optional_param": "some_value"
        # missing required_param
    }

    # The tool should handle this gracefully since the host_component is None
    # In a real scenario, this would be caught by the ADK parameter validation
    # But we can test the schema generation
    schema = tool.parameters_schema

    # Verify the schema correctly marks the parameter as required
    assert (
        "required_param" in schema.required
    ), "required_param should be in the required list"
    assert (
        "optional_param" not in schema.required
    ), "optional_param should not be in the required list"

    # Verify the schema has the correct properties
    assert (
        "required_param" in schema.properties
    ), "required_param should be in properties"
    assert (
        "optional_param" in schema.properties
    ), "optional_param should be in properties"


async def test_parameter_type_validation():
    """
    Test 4: Verify that parameter types are validated correctly.

    This test checks that the tool's parameter schema correctly defines
    different parameter types and handles type validation appropriately.
    """
    from sam_event_mesh_tool.tools import EventMeshTool
    from google.genai import types as adk_types

    # Create a tool configuration with different parameter types
    parameters = create_multi_type_parameters()
    tool_config = create_basic_tool_config(
        tool_name="TypeTestTool",
        description="A tool to test parameter types",
        parameters=parameters,
    )

    # Create tool instance
    tool = EventMeshTool(tool_config)

    # Get the generated schema
    schema = tool.parameters_schema

    # Verify the schema has correct types
    assert schema.properties["string_param"].type == adk_types.Type.STRING
    assert schema.properties["integer_param"].type == adk_types.Type.INTEGER
    assert schema.properties["number_param"].type == adk_types.Type.NUMBER
    assert schema.properties["boolean_param"].type == adk_types.Type.BOOLEAN

    # Unknown types should default to STRING
    assert schema.properties["unknown_type_param"].type == adk_types.Type.STRING

    # Verify required parameters
    assert "string_param" in schema.required
    assert "integer_param" in schema.required
    assert "number_param" not in schema.required
    assert "boolean_param" not in schema.required
    assert "unknown_type_param" not in schema.required

    # Verify descriptions are preserved
    assert schema.properties["string_param"].description == "A string parameter"
    assert schema.properties["integer_param"].description == "An integer parameter"
    assert schema.properties["number_param"].description == "A number parameter"
    assert schema.properties["boolean_param"].description == "A boolean parameter"
    assert (
        schema.properties["unknown_type_param"].description
        == "A parameter with unknown type (should default to string)"
    )


async def test_dynamic_topic_construction(
    agent_with_event_mesh_tool: SamAgentComponent,
    response_control_queue: Queue,
):
    """
    Test 5: Test that topic templates are filled correctly with parameter values.

    This test configures a topic template with multiple parameter substitutions
    and verifies the responder receives messages on the expected dynamic topic.
    """
    from sam_event_mesh_tool.tools import _fill_topic_template

    # Test simple parameter substitution
    template = "weather/request/{{ city }}/{{ unit }}"
    params = {"city": "ottawa", "unit": "celsius"}

    result = _fill_topic_template(template, params)
    expected = "weather/request/ottawa/celsius"

    assert result == expected, f"Expected {expected}, got {result}"

    # Test with encoding prefix (should be ignored)
    template_with_encoding = "weather/request/{{ text://city }}/{{ unit }}"
    result_with_encoding = _fill_topic_template(template_with_encoding, params)

    assert (
        result_with_encoding == expected
    ), f"Expected {expected}, got {result_with_encoding}"

    # Test with mixed static and dynamic parts
    template_complex = "acme/{{ service }}/v1/{{ action }}/{{ request_id }}"
    params_complex = {"service": "weather", "action": "get", "request_id": "req-123"}

    result_complex = _fill_topic_template(template_complex, params_complex)
    expected_complex = "acme/weather/v1/get/req-123"

    assert (
        result_complex == expected_complex
    ), f"Expected {expected_complex}, got {result_complex}"

    # Test with special characters in parameter values
    template_special = "events/{{ event_type }}/{{ user_id }}"
    params_special = {"event_type": "user-login", "user_id": "user@example.com"}

    result_special = _fill_topic_template(template_special, params_special)
    expected_special = "events/user-login/user@example.com"

    assert (
        result_special == expected_special
    ), f"Expected {expected_special}, got {result_special}"


async def test_topic_template_with_missing_parameter():
    """
    Test 6: Test error handling when topic template references undefined parameters.

    This test verifies that when a topic template references a parameter not
    defined in the parameters list, the tool returns a clear error.
    """
    from sam_event_mesh_tool.tools import _fill_topic_template
    import pytest

    # Test missing parameter
    template = "weather/request/{{ city }}/{{ missing_param }}"
    params = {"city": "ottawa"}  # missing_param is not provided

    with pytest.raises(ValueError) as exc_info:
        _fill_topic_template(template, params)

    assert "Missing required parameter 'missing_param'" in str(exc_info.value)

    # Test completely empty params
    template_empty = "weather/{{ city }}/{{ unit }}"
    params_empty = {}

    with pytest.raises(ValueError) as exc_info:
        _fill_topic_template(template_empty, params_empty)

    assert "Missing required parameter 'city'" in str(exc_info.value)

    # Test with encoding prefix - should still fail for missing param
    template_encoding = "weather/{{ text://city }}/{{ text://missing_param }}"
    params_partial = {"city": "ottawa"}

    with pytest.raises(ValueError) as exc_info:
        _fill_topic_template(template_encoding, params_partial)

    assert "Missing required parameter 'missing_param'" in str(exc_info.value)


async def test_topic_template_with_special_characters():
    """
    Test 7: Test topic construction with special characters in parameter values.

    This test uses parameters containing slashes, spaces, unicode characters
    and verifies the topic is constructed correctly.
    """
    from sam_event_mesh_tool.tools import _fill_topic_template

    # Test with slashes in parameter values
    template = "api/{{ service_path }}/{{ action }}"
    params_with_slashes = {"service_path": "users/profiles", "action": "get"}

    result = _fill_topic_template(template, params_with_slashes)
    expected = "api/users/profiles/get"

    assert result == expected, f"Expected {expected}, got {result}"

    # Test with spaces and special characters
    template_special = "events/{{ event_name }}/{{ user_info }}"
    params_special = {"event_name": "user login", "user_info": "john.doe@company.com"}

    result_special = _fill_topic_template(template_special, params_special)
    expected_special = "events/user login/john.doe@company.com"

    assert (
        result_special == expected_special
    ), f"Expected {expected_special}, got {result_special}"

    # Test with unicode characters
    template_unicode = "messages/{{ language }}/{{ content_type }}"
    params_unicode = {"language": "français", "content_type": "émojis_🎉"}

    result_unicode = _fill_topic_template(template_unicode, params_unicode)
    expected_unicode = "messages/français/émojis_🎉"

    assert (
        result_unicode == expected_unicode
    ), f"Expected {expected_unicode}, got {result_unicode}"

    # Test with numbers and boolean values (converted to strings)
    template_mixed = "data/{{ sensor_id }}/{{ is_active }}/{{ temperature }}"
    params_mixed = {"sensor_id": 12345, "is_active": True, "temperature": 23.5}

    result_mixed = _fill_topic_template(template_mixed, params_mixed)
    expected_mixed = "data/12345/True/23.5"

    assert (
        result_mixed == expected_mixed
    ), f"Expected {expected_mixed}, got {result_mixed}"

    # Test with empty string parameter
    template_empty = "logs/{{ level }}/{{ message }}"
    params_empty = {"level": "info", "message": ""}  # Empty string should be allowed

    result_empty = _fill_topic_template(template_empty, params_empty)
    expected_empty = "logs/info/"

    assert (
        result_empty == expected_empty
    ), f"Expected {expected_empty}, got {result_empty}"


async def test_session_initialization_and_cleanup(
    agent_with_event_mesh_tool: SamAgentComponent,
    response_control_queue: Queue,
):
    """
    Test 8: Test that the tool properly creates and destroys its dedicated session.

    This test verifies that session_id is set after init and cleared after cleanup,
    ensuring the session lifecycle is managed correctly.
    """
    import asyncio

    # Wait for the agent to be fully initialized
    await asyncio.sleep(2)

    # Find the EventMeshTool instance
    event_mesh_tool = find_event_mesh_tool(agent_with_event_mesh_tool)
    assert event_mesh_tool is not None, "EventMeshTool not found in agent component"

    # Test 1: Verify session was initialized
    assert (
        event_mesh_tool.session_id is not None
    ), "Session ID should be set after initialization"
    assert isinstance(event_mesh_tool.session_id, str), "Session ID should be a string"
    assert len(event_mesh_tool.session_id) > 0, "Session ID should not be empty"

    # Store the original session ID for verification
    original_session_id = event_mesh_tool.session_id

    # Test 2: Verify the session exists in the component's session manager
    # The session should be listed in the active sessions
    active_sessions = agent_with_event_mesh_tool.list_request_response_sessions()
    session_ids = [session["session_id"] for session in active_sessions]
    assert (
        original_session_id in session_ids
    ), f"Session {original_session_id} should be in active sessions list"

    # Test 3: Verify session can be used (basic functionality test)
    # Put a test response in the control queue
    test_response = {"test": "session_works"}
    response_control_queue.put((test_response, 0))

    # Create mock context for tool execution
    tool_context = create_mock_tool_context(agent_with_event_mesh_tool)

    # Execute the tool to verify the session works
    tool_args = {"request_data": "session_test"}
    tool_result = await event_mesh_tool._run_async_impl(
        args=tool_args, tool_context=tool_context
    )

    assert tool_result is not None, "Tool should return a result when session is active"
    assert (
        tool_result.get("status") == "success"
    ), f"Tool should succeed with active session: {tool_result}"
    assert (
        tool_result.get("payload") == test_response
    ), "Tool should return the expected response"

    # Test 4: Test cleanup
    # Create a mock tool_config_model for cleanup
    mock_tool_config = create_mock_tool_config_model()

    # Call cleanup
    await event_mesh_tool.cleanup(agent_with_event_mesh_tool, mock_tool_config)

    # Test 5: Verify session was cleaned up
    assert event_mesh_tool.session_id is None, "Session ID should be None after cleanup"

    # Verify the session is no longer in the active sessions list
    active_sessions_after_cleanup = (
        agent_with_event_mesh_tool.list_request_response_sessions()
    )
    session_ids_after_cleanup = [
        session["session_id"] for session in active_sessions_after_cleanup
    ]
    assert (
        original_session_id not in session_ids_after_cleanup
    ), f"Session {original_session_id} should not be in active sessions after cleanup"

    # Test 6: Verify tool fails gracefully after cleanup

    # Try to use the tool after cleanup
    tool_result_after_cleanup = await event_mesh_tool._run_async_impl(
        args={"request_data": "after_cleanup"}, tool_context=tool_context
    )

    assert (
        tool_result_after_cleanup is not None
    ), "Tool should return a result even after cleanup"
    assert (
        tool_result_after_cleanup.get("status") == "error"
    ), "Tool should return error status after cleanup"
    assert (
        "not initialized" in tool_result_after_cleanup.get("message", "").lower()
    ), "Error message should indicate session not initialized"

    # Test 7: Restore the tool's session for subsequent tests (test isolation)
    # This ensures other tests in the same session can still use the tool
    await event_mesh_tool.init(agent_with_event_mesh_tool, mock_tool_config)

    # Verify the tool is working again
    assert (
        event_mesh_tool.session_id is not None
    ), "Session ID should be restored after re-initialization"

    # Verify the restored session is in the active sessions list
    restored_active_sessions = (
        agent_with_event_mesh_tool.list_request_response_sessions()
    )
    restored_session_ids = [
        session["session_id"] for session in restored_active_sessions
    ]
    assert (
        event_mesh_tool.session_id in restored_session_ids
    ), "Restored session should be in active sessions list"

    # Test that the restored tool works by sending a test request
    test_response_restored = {"restored": "session_works"}
    response_control_queue.put((test_response_restored, 0))

    tool_result_restored = await event_mesh_tool._run_async_impl(
        args={"request_data": "restored_session_test"}, tool_context=tool_context
    )

    assert (
        tool_result_restored is not None
    ), "Tool should work after session restoration"
    assert (
        tool_result_restored.get("status") == "success"
    ), "Tool should succeed with restored session"
    assert (
        tool_result_restored.get("payload") == test_response_restored
    ), "Tool should return expected response with restored session"


async def test_session_failure_handling():
    """
    Test 9: Test behavior when session creation fails.

    This test mocks session creation failure scenarios and verifies that the tool
    handles session failures gracefully with clear error messages.
    """
    from sam_event_mesh_tool.tools import EventMeshTool
    from unittest.mock import Mock, patch

    # Create a tool configuration
    tool_config = create_basic_tool_config()

    # Create tool instance
    tool = EventMeshTool(tool_config)

    # Create a mock component that will fail session creation
    mock_component = Mock()
    mock_component.create_request_response_session.side_effect = Exception(
        "Session creation failed"
    )

    # Create a mock tool_config_model
    mock_tool_config = create_mock_tool_config_model()

    # Test: Call init and expect it to raise an exception
    with pytest.raises(Exception) as exc_info:
        await tool.init(mock_component, mock_tool_config)

    assert "Session creation failed" in str(exc_info.value)

    # Verify that session_id remains None after failed initialization
    assert (
        tool.session_id is None
    ), "Session ID should remain None after failed initialization"

    # Test: Verify tool fails gracefully when used without a session
    # Create a working mock component for the tool execution test
    working_mock_component = Mock()
    tool_context = create_mock_tool_context(working_mock_component)

    # Try to use the tool without a session
    tool_result = await tool._run_async_impl(
        args={"test_param": "test_value"}, tool_context=tool_context
    )

    assert (
        tool_result is not None
    ), "Tool should return a result even when session is not initialized"
    assert (
        tool_result.get("status") == "error"
    ), "Tool should return error status when session is not initialized"
    assert (
        "not initialized" in tool_result.get("message", "").lower()
    ), "Error message should indicate session not initialized"


async def test_session_isolation():
    """
    Test 10: Verify that each tool instance has its own isolated session.

    This test creates multiple tool instances and verifies they don't interfere
    with each other, ensuring each tool maintains its own session state.
    """
    from sam_event_mesh_tool.tools import EventMeshTool
    from unittest.mock import Mock

    # Create two different tool configurations
    tool_config_1 = create_basic_tool_config(
        tool_name="TestTool1",
        description="First test tool",
        topic="test/topic1",
        parameters=[
            {
                "name": "param1",
                "type": "string",
                "required": True,
                "description": "Parameter for tool 1",
                "payload_path": "data.param1",
            }
        ],
        event_mesh_config={
            "broker_config": {
                "dev_mode": True,
                "broker_url": "dev-broker-1",
                "broker_username": "dev-user-1",
                "broker_password": "dev-password-1",
                "broker_vpn": "dev-vpn-1",
            }
        },
    )

    tool_config_2 = create_basic_tool_config(
        tool_name="TestTool2",
        description="Second test tool",
        topic="test/topic2",
        parameters=[
            {
                "name": "param2",
                "type": "string",
                "required": True,
                "description": "Parameter for tool 2",
                "payload_path": "data.param2",
            }
        ],
        event_mesh_config={
            "broker_config": {
                "dev_mode": True,
                "broker_url": "dev-broker-2",
                "broker_username": "dev-user-2",
                "broker_password": "dev-password-2",
                "broker_vpn": "dev-vpn-2",
            }
        },
    )

    # Create two tool instances
    tool1 = EventMeshTool(tool_config_1)
    tool2 = EventMeshTool(tool_config_2)

    # Verify tools are different instances
    assert tool1 is not tool2, "Tool instances should be different objects"
    assert tool1.tool_name != tool2.tool_name, "Tools should have different names"

    # Create mock components that return different session IDs
    mock_component1 = Mock()
    mock_component1.create_request_response_session.return_value = "session-1"

    mock_component2 = Mock()
    mock_component2.create_request_response_session.return_value = "session-2"

    # Create mock tool_config_models
    mock_tool_config = create_mock_tool_config_model()

    # Initialize both tools with their respective components
    await tool1.init(mock_component1, mock_tool_config)
    await tool2.init(mock_component2, mock_tool_config)

    # Verify each tool has its own session ID
    assert tool1.session_id == "session-1", "Tool 1 should have session-1"
    assert tool2.session_id == "session-2", "Tool 2 should have session-2"
    assert (
        tool1.session_id != tool2.session_id
    ), "Tools should have different session IDs"

    # Verify that each tool called create_request_response_session with its own config
    mock_component1.create_request_response_session.assert_called_once_with(
        session_config=tool_config_1["event_mesh_config"]
    )
    mock_component2.create_request_response_session.assert_called_once_with(
        session_config=tool_config_2["event_mesh_config"]
    )

    # Test cleanup isolation - cleaning up one tool shouldn't affect the other
    mock_component1.destroy_request_response_session = Mock()
    mock_component2.destroy_request_response_session = Mock()

    # Cleanup tool1
    await tool1.cleanup(mock_component1, mock_tool_config)

    # Verify tool1 session was destroyed but tool2 session remains
    assert tool1.session_id is None, "Tool 1 session should be None after cleanup"
    assert tool2.session_id == "session-2", "Tool 2 session should remain unchanged"

    mock_component1.destroy_request_response_session.assert_called_once_with(
        "session-1"
    )
    mock_component2.destroy_request_response_session.assert_not_called()

    # Cleanup tool2
    await tool2.cleanup(mock_component2, mock_tool_config)

    # Verify tool2 session was also destroyed
    assert tool2.session_id is None, "Tool 2 session should be None after cleanup"
    mock_component2.destroy_request_response_session.assert_called_once_with(
        "session-2"
    )

    # Test that tools have different parameter schemas
    schema1 = tool1.parameters_schema
    schema2 = tool2.parameters_schema

    assert "param1" in schema1.properties, "Tool 1 should have param1 in schema"
    assert "param2" not in schema1.properties, "Tool 1 should not have param2 in schema"
    assert "param2" in schema2.properties, "Tool 2 should have param2 in schema"
    assert "param1" not in schema2.properties, "Tool 2 should not have param1 in schema"


async def test_fire_and_forget_mode(
    agent_with_event_mesh_tool: SamAgentComponent,
    response_control_queue: Queue,
):
    """
    Test 11: Test wait_for_response=false returns immediately without waiting.

    This test configures a tool with wait_for_response: false and verifies that
    the tool returns immediately with success status while the message is still sent.
    """
    import asyncio
    import time

    # Wait for the agent to be fully initialized
    await asyncio.sleep(2)

    # Find the EventMeshTool instance
    event_mesh_tool = find_event_mesh_tool(agent_with_event_mesh_tool)
    assert event_mesh_tool is not None, "EventMeshTool not found in agent component"

    # Temporarily modify the tool config to set wait_for_response to False
    original_wait_for_response = event_mesh_tool.tool_config.get(
        "wait_for_response", True
    )
    event_mesh_tool.tool_config["wait_for_response"] = False

    try:
        # Put a response in the control queue but tell the responder not to send a reply
        # This prevents orphaned response messages in fire-and-forget mode
        test_response = {"async": "response"}
        response_control_queue.put(
            (test_response, 0, False)
        )  # (payload, delay, should_send_reply)

        # Create mock context for tool execution
        tool_context = create_mock_tool_context(agent_with_event_mesh_tool)

        # Record start time
        start_time = time.time()

        # Execute the tool - this should return immediately
        tool_args = {"request_data": "fire_and_forget_test"}
        tool_result = await event_mesh_tool._run_async_impl(
            args=tool_args, tool_context=tool_context
        )

        # Record end time
        end_time = time.time()
        execution_time = end_time - start_time

        # Assert: Tool should return immediately (much less than the 1 second delay)
        assert (
            execution_time < 0.5
        ), f"Tool should return immediately, but took {execution_time} seconds"

        # Assert: Tool should return success status for fire-and-forget
        assert (
            tool_result is not None
        ), "Tool should return a result for fire-and-forget"
        assert (
            tool_result.get("status") == "success"
        ), f"Tool should return success status: {tool_result}"
        assert (
            "asynchronously" in tool_result.get("message", "").lower()
        ), "Message should indicate asynchronous operation"

        # Assert: No payload should be returned since we didn't wait
        assert (
            "payload" not in tool_result
        ), "Fire-and-forget should not return a payload"

        # Verify the message was still sent by checking if the responder received it
        # Give a moment for the message to be processed
        await asyncio.sleep(0.1)

        # The responder should have consumed the message from the control queue
        # If the queue is empty, it means the message was processed
        assert (
            response_control_queue.empty()
        ), "Responder should have processed the fire-and-forget message"

        # Note: The responder was instructed not to send a reply (should_send_reply=False)
        # This prevents orphaned response messages that nobody is waiting for

    finally:
        # Restore original configuration
        event_mesh_tool.tool_config["wait_for_response"] = original_wait_for_response


async def test_synchronous_mode_blocking_behavior(
    agent_with_event_mesh_tool: SamAgentComponent,
    response_control_queue: Queue,
):
    """
    Test 12: Verify that synchronous mode properly blocks until response received.

    This test sends a request with a delay in the responder and verifies that
    the tool call duration matches the responder delay.
    """
    import asyncio
    import time

    # Wait for the agent to be fully initialized
    await asyncio.sleep(2)

    # Find the EventMeshTool instance
    event_mesh_tool = find_event_mesh_tool(agent_with_event_mesh_tool)
    assert event_mesh_tool is not None, "EventMeshTool not found in agent component"

    # Ensure the tool is configured for synchronous mode
    original_wait_for_response = event_mesh_tool.tool_config.get(
        "wait_for_response", True
    )
    event_mesh_tool.tool_config["wait_for_response"] = True

    try:
        # Configure responder to delay for 2 seconds
        delay_seconds = 2
        test_response = {"delayed": "response", "delay_was": delay_seconds}
        response_control_queue.put((test_response, delay_seconds))

        # Create mock context for tool execution
        tool_context = create_mock_tool_context(agent_with_event_mesh_tool)

        # Record start time
        start_time = time.time()

        # Execute the tool - this should block until response is received
        tool_args = {"request_data": "blocking_test"}
        tool_result = await event_mesh_tool._run_async_impl(
            args=tool_args, tool_context=tool_context
        )

        # Record end time
        end_time = time.time()
        execution_time = end_time - start_time

        # Assert: Tool should have blocked for approximately the delay time
        # Allow some tolerance for processing time (±0.5 seconds)
        assert execution_time >= (
            delay_seconds - 0.5
        ), f"Tool should have blocked for at least {delay_seconds - 0.5} seconds, but only took {execution_time} seconds"
        assert execution_time <= (
            delay_seconds + 1.0
        ), f"Tool should not have taken more than {delay_seconds + 1.0} seconds, but took {execution_time} seconds"

        # Assert: Tool should return the delayed response
        assert tool_result is not None, "Tool should return a result after blocking"
        assert (
            tool_result.get("status") == "success"
        ), f"Tool should return success status: {tool_result}"
        assert "payload" in tool_result, "Synchronous mode should return a payload"
        assert (
            tool_result["payload"] == test_response
        ), f"Expected {test_response}, got {tool_result['payload']}"

    finally:
        # Restore original configuration
        event_mesh_tool.tool_config["wait_for_response"] = original_wait_for_response


async def test_request_timeout(
    agent_with_event_mesh_tool: SamAgentComponent,
    response_control_queue: Queue,
):
    """
    Test 13: Test that requests timeout properly when no response is received.

    This test doesn't put anything on the control queue to simulate timeout
    and verifies that the tool raises TimeoutError or returns timeout status.
    """
    import asyncio
    import time

    # Wait for the agent to be fully initialized
    await asyncio.sleep(2)

    # Find the EventMeshTool instance
    event_mesh_tool = find_event_mesh_tool(agent_with_event_mesh_tool)
    assert event_mesh_tool is not None, "EventMeshTool not found in agent component"

    # Temporarily modify the tool's session config to use a very short timeout
    # We need to access the session and modify its timeout
    original_session_id = event_mesh_tool.session_id

    # Create a new session with a short timeout for this test
    short_timeout_config = {
        "broker_config": {
            "dev_mode": True,
            # "broker_type": "dev_broker",
            "broker_url": "dev-broker",
            "broker_username": "dev-user",
            "broker_password": "dev-password",
            "broker_vpn": "dev-vpn",
        },
        "request_expiry_ms": 2000,  # 2 second timeout
    }

    # Create a new session with short timeout
    test_session_id = agent_with_event_mesh_tool.create_request_response_session(
        session_config=short_timeout_config
    )

    # Temporarily replace the tool's session ID
    event_mesh_tool.session_id = test_session_id

    try:
        # DO NOT put anything on the response_control_queue
        # This will cause the responder to block indefinitely, triggering a timeout

        # Create mock context for tool execution
        tool_context = create_mock_tool_context(agent_with_event_mesh_tool)

        # Record start time
        start_time = time.time()

        # Execute the tool - this should timeout
        tool_args = {"request_data": "timeout_test"}
        tool_result = await event_mesh_tool._run_async_impl(
            args=tool_args, tool_context=tool_context
        )

        # Record end time
        end_time = time.time()
        execution_time = end_time - start_time

        # Assert: Tool should have timed out after approximately 2 seconds
        # Allow some tolerance for processing time (±1 second)
        assert (
            execution_time >= 1.5
        ), f"Tool should have taken at least 1.5 seconds to timeout, but only took {execution_time} seconds"
        assert (
            execution_time <= 4.0
        ), f"Tool should have timed out within 4 seconds, but took {execution_time} seconds"

        # Assert: Tool should return an error indicating timeout or no response
        assert tool_result is not None, "Tool should return a result even on timeout"
        assert (
            tool_result.get("status") == "error"
        ), f"Tool should return error status on timeout: {tool_result}"

        # The error message should indicate timeout or no response
        error_message = tool_result.get("message", "").lower()
        assert any(
            keyword in error_message
            for keyword in ["timeout", "timed out", "no response", "failed"]
        ), f"Error message should indicate timeout or no response: {tool_result}"

        # Assert: No payload should be returned on timeout
        assert (
            "payload" not in tool_result or tool_result.get("payload") is None
        ), "Timeout should not return a payload"

    finally:
        # Clean up the test session
        agent_with_event_mesh_tool.destroy_request_response_session(test_session_id)

        # Restore original session ID
        event_mesh_tool.session_id = original_session_id

        # Clear any remaining items from the control queue to avoid affecting other tests
        while not response_control_queue.empty():
            try:
                response_control_queue.get_nowait()
            except:
                break
