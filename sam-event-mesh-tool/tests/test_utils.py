"""
Test utilities for the Event Mesh Tool integration tests.

This module provides helper functions to reduce code duplication across tests.
"""

from typing import Optional, Dict, Any
from google.adk.tools import ToolContext
from pydantic import BaseModel
from solace_agent_mesh.agent.sac.component import SamAgentComponent
from sam_event_mesh_tool.tools import EventMeshTool


def create_mock_tool_context(host_component: SamAgentComponent) -> ToolContext:
    """
    Create a mock ToolContext for testing tool execution.
    
    Args:
        host_component: The SamAgentComponent to use as the host component
        
    Returns:
        A configured ToolContext instance
    """
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

    mock_agent = MockAgent(host_component)
    mock_invocation_context = MockInvocationContext(mock_agent)
    return ToolContext(invocation_context=mock_invocation_context)


def find_event_mesh_tool(
    agent_component: SamAgentComponent, 
    tool_name: str = "EventMeshRequest"
) -> Optional[EventMeshTool]:
    """
    Find an EventMeshTool instance in the agent's tools list.
    
    Args:
        agent_component: The SamAgentComponent to search
        tool_name: The name of the tool to find
        
    Returns:
        The EventMeshTool instance if found, None otherwise
    """
    for tool in agent_component.adk_agent.tools:
        if isinstance(tool, EventMeshTool) and tool.tool_name == tool_name:
            return tool
    return None


def create_basic_tool_config(
    tool_name: str = "TestTool",
    description: str = "A test tool",
    topic: str = "test/topic",
    **overrides
) -> Dict[str, Any]:
    """
    Create a basic tool configuration for testing.
    
    Args:
        tool_name: Name of the tool
        description: Description of the tool
        topic: Topic for the tool
        **overrides: Additional configuration to merge in
        
    Returns:
        A tool configuration dictionary
    """
    base_config = {
        "tool_name": tool_name,
        "description": description,
        "parameters": [
            {
                "name": "test_param",
                "type": "string",
                "required": True,
                "description": "A test parameter",
                "payload_path": "data.test"
            }
        ],
        "topic": topic,
        "event_mesh_config": {
            "broker_config": {
                "dev_mode": True,
                "broker_url": "dev-broker",
                "broker_username": "dev-user",
                "broker_password": "dev-password",
                "broker_vpn": "dev-vpn"
            }
        }
    }
    
    # Merge in any overrides
    if overrides:
        base_config.update(overrides)
    
    return base_config


def create_mock_tool_config_model():
    """
    Create a mock tool config model for testing lifecycle methods.
    
    Returns:
        A mock Pydantic BaseModel instance
    """
    class MockToolConfig(BaseModel):
        pass
    
    return MockToolConfig()


def create_tool_config_with_parameters(parameters: list) -> Dict[str, Any]:
    """
    Create a tool configuration with custom parameters.
    
    Args:
        parameters: List of parameter definitions
        
    Returns:
        A tool configuration dictionary with the specified parameters
    """
    return create_basic_tool_config(
        parameters=parameters
    )


def create_multi_type_parameters() -> list:
    """
    Create a list of parameters with different types for type validation testing.
    
    Returns:
        List of parameter definitions with various types
    """
    return [
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
    ]


def create_required_optional_parameters() -> list:
    """
    Create a list of parameters with both required and optional parameters.
    
    Returns:
        List of parameter definitions for testing required parameter validation
    """
    return [
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
    ]
