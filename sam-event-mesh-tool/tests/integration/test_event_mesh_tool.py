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
    Tests a single, successful request-response interaction.
    """
    # Arrange: Tell the responder what to send back
    expected_response = {"status": "success", "value": "some_data"}
    response_control_queue.put((expected_response, 0))  # (payload, delay_seconds)

    # Act: Find the tool to get its session_id and invoke the request
    event_mesh_tool = None
    for tool in agent_with_event_mesh_tool.tools:
        if isinstance(tool, EventMeshTool) and tool.tool_name == "EventMeshRequest":
            event_mesh_tool = tool
            break

    assert event_mesh_tool is not None, "EventMeshTool not found in agent component"
    assert (
        event_mesh_tool.session_id is not None
    ), "EventMeshTool session was not initialized"

    # Simulate the tool's action by calling the underlying request-response method
    request_message = Message(
        payload={"data": "some test request"}, topic="test/request/tool"
    )
    response_message = (
        await agent_with_event_mesh_tool.do_broker_request_response_async(
            request_message, session_id=event_mesh_tool.session_id
        )
    )

    # Assert
    assert response_message is not None, "Did not receive a response"
    assert response_message.get_payload() == expected_response
