"""
Integration tests for the EventMeshTool.

These tests use the fixtures defined in conftest.py to create a live,
in-memory integration environment with a client agent and a responder service.
"""

import pytest
from queue import Queue

from solace_ai_connector.common.message import Message
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
    
    class MockInvocationContext:
        def __init__(self, agent):
            self.agent = agent
    
    mock_agent = MockAgent(agent_with_event_mesh_tool)
    mock_invocation_context = MockInvocationContext(mock_agent)
    tool_context = ToolContext(invocation_context=mock_invocation_context)

    # Call the tool with test parameters
    tool_args = {"request_data": "some test request"}
    tool_result = await event_mesh_tool._run_async_impl(
        args=tool_args,
        tool_context=tool_context
    )

    # Assert: Check that the tool executed successfully and returned the expected response
    assert tool_result is not None, "Tool did not return a result"
    assert tool_result.get("status") == "success", f"Tool failed: {tool_result}"
    assert "payload" in tool_result, "Tool result missing payload"
    assert tool_result["payload"] == expected_response, f"Expected {expected_response}, got {tool_result['payload']}"
