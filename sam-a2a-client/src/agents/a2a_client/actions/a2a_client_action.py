"""
Dynamically created SAM Action to represent and invoke a specific A2A skill.
"""

from typing import Dict, Any, List, Optional

from solace_agent_mesh.common.action import Action
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo

# Forward declaration for type hinting if needed, or import later
# class A2AClientAgentComponent:
#     pass

# Import A2A types later when needed
# from common.types import AgentSkill


class A2AClientAction(Action):
    """
    A SAM Action that wraps a specific skill discovered from an A2A agent.
    It handles invoking the skill via the A2A protocol.
    """
    pass
