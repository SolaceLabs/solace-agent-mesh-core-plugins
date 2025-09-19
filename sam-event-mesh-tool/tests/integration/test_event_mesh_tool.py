"""
Integration tests for the EventMeshTool.

These tests use the fixtures defined in conftest.py to create a live,
in-memory integration environment with a client agent and a responder service.
"""

import pytest
from queue import Queue

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
    from sam_event_mesh_tool.tools import _build_payload
    
    # Define parameters with nested payload paths
    parameters_map = {
        "city": {
            "name": "city",
            "payload_path": "location.city"
        },
        "zipcode": {
            "name": "zipcode", 
            "payload_path": "customer.address.zipcode"
        },
        "temperature": {
            "name": "temperature",
            "payload_path": "weather.current.temperature"
        },
        "unit": {
            "name": "unit",
            "payload_path": "weather.unit"
        },
        "request_id": {
            "name": "request_id",
            # No payload_path - this parameter won't be in the payload
        }
    }
    
    # Test parameters
    params = {
        "city": "Ottawa",
        "zipcode": "K1A 0A6", 
        "temperature": 25,
        "unit": "celsius",
        "request_id": "test-123"
    }
    
    # Act: Build the payload
    payload = _build_payload(parameters_map, params)
    
    # Assert: Verify the nested structure is correct
    expected_payload = {
        "location": {
            "city": "Ottawa"
        },
        "customer": {
            "address": {
                "zipcode": "K1A 0A6"
            }
        },
        "weather": {
            "current": {
                "temperature": 25
            },
            "unit": "celsius"
        }
    }
    
    assert payload == expected_payload, f"Expected {expected_payload}, got {payload}"
    
    # Verify that request_id is not in the payload since it has no payload_path
    assert "request_id" not in payload, "request_id should not be in payload when no payload_path is specified"
