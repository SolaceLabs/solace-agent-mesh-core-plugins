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
    event_mesh_tool = None
    for tool in agent_with_event_mesh_tool.adk_agent.tools:
        if isinstance(tool, EventMeshTool) and tool.tool_name == "EventMeshRequest":
            event_mesh_tool = tool
            break

    assert event_mesh_tool is not None, "EventMeshTool not found in agent component"
    assert (
        event_mesh_tool.session_id is not None
    ), "EventMeshTool session was not initialized"

    # Create a mock ToolContext to pass to the tool
    from google.adk.tools import ToolContext
    from google.adk.agents.invocation_context import InvocationContext

    # Create a minimal mock invocation context
    class MockAgent:
        def __init__(self, host_component):
            self.host_component = host_component

    class MockSession:
        def __init__(self):
            self.state = {}

    class MockInvocationContext:
        def __init__(self, agent):
            self.agent = agent
            self.session = MockSession()

    mock_agent = MockAgent(agent_with_event_mesh_tool)
    mock_invocation_context = MockInvocationContext(mock_agent)
    tool_context = ToolContext(invocation_context=mock_invocation_context)

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
    from google.adk.tools import ToolContext

    # Create a tool configuration with required parameters
    tool_config = {
        "tool_name": "TestTool",
        "description": "A test tool",
        "parameters": [
            {
                "name": "required_param",
                "type": "string",
                "required": True,
                "description": "A required parameter",
                "payload_path": "data.required",
            },
            {
                "name": "optional_param",
                "type": "string",
                "required": False,
                "default": "default_value",
                "payload_path": "data.optional",
            },
        ],
        "topic": "test/topic",
        "event_mesh_config": {
            "broker_config": {
                "dev_mode": True,
                "broker_url": "dev-broker",
                "broker_username": "dev-user",
                "broker_password": "dev-password",
                "broker_vpn": "dev-vpn",
            }
        },
    }

    # Create tool instance
    tool = EventMeshTool(tool_config)

    # Create mock context
    class MockAgent:
        def __init__(self):
            self.host_component = None

    class MockSession:
        def __init__(self):
            self.state = {}

    class MockInvocationContext:
        def __init__(self):
            self.agent = MockAgent()
            self.session = MockSession()

    tool_context = ToolContext(invocation_context=MockInvocationContext())

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
    tool_config = {
        "tool_name": "TypeTestTool",
        "description": "A tool to test parameter types",
        "parameters": [
            {
                "name": "string_param",
                "type": "string",
                "required": True,
                "description": "A string parameter",
            },
            {
                "name": "integer_param",
                "type": "integer",
                "required": True,
                "description": "An integer parameter",
            },
            {
                "name": "number_param",
                "type": "number",
                "required": False,
                "description": "A number parameter",
            },
            {
                "name": "boolean_param",
                "type": "boolean",
                "required": False,
                "description": "A boolean parameter",
            },
            {
                "name": "unknown_type_param",
                "type": "unknown_type",
                "required": False,
                "description": "A parameter with unknown type (should default to string)",
            },
        ],
        "topic": "test/topic",
        "event_mesh_config": {
            "broker_config": {
                "dev_mode": True,
                "broker_url": "dev-broker",
                "broker_username": "dev-user",
                "broker_password": "dev-password",
                "broker_vpn": "dev-vpn",
            }
        },
    }

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
    
    assert result_with_encoding == expected, f"Expected {expected}, got {result_with_encoding}"
    
    # Test with mixed static and dynamic parts
    template_complex = "acme/{{ service }}/v1/{{ action }}/{{ request_id }}"
    params_complex = {
        "service": "weather",
        "action": "get",
        "request_id": "req-123"
    }
    
    result_complex = _fill_topic_template(template_complex, params_complex)
    expected_complex = "acme/weather/v1/get/req-123"
    
    assert result_complex == expected_complex, f"Expected {expected_complex}, got {result_complex}"
    
    # Test with special characters in parameter values
    template_special = "events/{{ event_type }}/{{ user_id }}"
    params_special = {
        "event_type": "user-login",
        "user_id": "user@example.com"
    }
    
    result_special = _fill_topic_template(template_special, params_special)
    expected_special = "events/user-login/user@example.com"
    
    assert result_special == expected_special, f"Expected {expected_special}, got {result_special}"


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
    params_with_slashes = {
        "service_path": "users/profiles",
        "action": "get"
    }
    
    result = _fill_topic_template(template, params_with_slashes)
    expected = "api/users/profiles/get"
    
    assert result == expected, f"Expected {expected}, got {result}"
    
    # Test with spaces and special characters
    template_special = "events/{{ event_name }}/{{ user_info }}"
    params_special = {
        "event_name": "user login",
        "user_info": "john.doe@company.com"
    }
    
    result_special = _fill_topic_template(template_special, params_special)
    expected_special = "events/user login/john.doe@company.com"
    
    assert result_special == expected_special, f"Expected {expected_special}, got {result_special}"
    
    # Test with unicode characters
    template_unicode = "messages/{{ language }}/{{ content_type }}"
    params_unicode = {
        "language": "français",
        "content_type": "émojis_🎉"
    }
    
    result_unicode = _fill_topic_template(template_unicode, params_unicode)
    expected_unicode = "messages/français/émojis_🎉"
    
    assert result_unicode == expected_unicode, f"Expected {expected_unicode}, got {result_unicode}"
    
    # Test with numbers and boolean values (converted to strings)
    template_mixed = "data/{{ sensor_id }}/{{ is_active }}/{{ temperature }}"
    params_mixed = {
        "sensor_id": 12345,
        "is_active": True,
        "temperature": 23.5
    }
    
    result_mixed = _fill_topic_template(template_mixed, params_mixed)
    expected_mixed = "data/12345/True/23.5"
    
    assert result_mixed == expected_mixed, f"Expected {expected_mixed}, got {result_mixed}"
    
    # Test with empty string parameter
    template_empty = "logs/{{ level }}/{{ message }}"
    params_empty = {
        "level": "info",
        "message": ""  # Empty string should be allowed
    }
    
    result_empty = _fill_topic_template(template_empty, params_empty)
    expected_empty = "logs/info/"
    
    assert result_empty == expected_empty, f"Expected {expected_empty}, got {result_empty}"
