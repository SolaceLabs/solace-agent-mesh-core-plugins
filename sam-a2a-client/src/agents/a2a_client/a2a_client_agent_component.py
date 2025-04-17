"""
Main component for the SAM A2A Client Plugin.

This component manages the connection to an external A2A agent,
discovers its capabilities, and exposes them as SAM actions.
"""

from solace_agent_mesh.agents.base_agent_component import BaseAgentComponent
# Import other necessary types later, e.g., ActionList, ActionResponse, AgentCard, A2AClient etc.


class A2AClientAgentComponent(BaseAgentComponent):
    """
    SAM Agent Component that acts as a client to an external A2A agent.
    """
    pass
