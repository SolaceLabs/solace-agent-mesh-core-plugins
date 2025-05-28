"""
Factory functions for creating SAM Actions based on A2A Agent capabilities.
"""

from typing import List, Dict, Any, TYPE_CHECKING

from solace_agent_mesh.common.action import Action
from solace_agent_mesh.common.action_response import (
    ActionResponse,
)  # Import ActionResponse
from .actions.a2a_client_action import A2AClientAction
from ...common_a2a.types import AgentCard, AgentSkill
from solace_ai_connector.common.log import log  # Use solace-ai-connector log

# Use TYPE_CHECKING to avoid circular import issues at runtime
if TYPE_CHECKING:
    from .a2a_client_agent_component import A2AClientAgentComponent


def infer_params_from_skill(skill: AgentSkill) -> List[Dict[str, Any]]:
    """
    Infers SAM action parameters from an A2A skill definition.

    This is a simplified initial implementation. It currently returns a generic
    set of parameters ('prompt' and 'files') regardless of the skill definition.
    Future enhancements could involve parsing skill descriptions or structured
    parameter definitions if they become part of the AgentCard standard.

    Args:
        skill: The A2A AgentSkill object.

    Returns:
        A list of dictionaries, each defining a SAM action parameter.
    """
    log.debug(
        "Inferring parameters for skill '%s'. Using generic 'prompt' and 'files'.",
        skill.id,
    )
    # TODO: Implement more sophisticated parameter inference based on skill details
    # For now, always return a standard 'prompt' and optional 'files'
    return [
        {
            "name": "prompt",
            "desc": "The user request or prompt for the agent skill.",
            "type": "string",
            "required": True,
        },
        {
            "name": "files",
            "desc": "Optional list of file URLs (e.g., from FileService) to include with the prompt. This list must be in json format.",
            "type": "string",  # SAM expects 'list' for array-like inputs
            "required": False,
        },
    ]


def create_actions_from_card(
    agent_card: AgentCard, component: "A2AClientAgentComponent"
) -> List[Action]:
    """
    Dynamically creates a list of SAM `A2AClientAction` instances based on the
    skills defined in the provided A2A AgentCard.

    Args:
        agent_card: The fetched AgentCard of the target A2A agent.
        component: The parent A2AClientAgentComponent instance.

    Returns:
        A list of initialized `A2AClientAction` objects. Returns an empty list
        if the agent_card is None or contains no skills.
    """
    actions: List[Action] = []
    if not agent_card or not agent_card.skills:
        log.warning(
            "No skills found in AgentCard for '%s'. No dynamic actions created.",
            component.agent_name,
        )
        return actions

    log.info(
        "Creating actions for agent '%s' based on %d AgentCard skills...",
        component.agent_name,
        len(agent_card.skills),
    )
    for skill in agent_card.skills:
        if not skill.id:
            log.warning(
                "Skipping skill with missing ID in AgentCard for '%s'. Skill: %s",
                component.agent_name,
                skill.name or "Unnamed",
            )
            continue
        try:
            # Infer parameters for the SAM action based on the A2A skill
            inferred_params = infer_params_from_skill(skill)
            # Create the specific action instance
            action = A2AClientAction(
                skill=skill, component=component, inferred_params=inferred_params
            )
            actions.append(action)
            log.info(
                "Created action '%s' for skill '%s' for agent '%s'.",
                action.name,
                skill.id,
                component.agent_name,
            )
        except Exception as e:
            # Log errors during individual action creation but continue with others
            log.error(
                "Failed to create action for skill '%s' for agent '%s': %s",
                skill.id,
                component.agent_name,
                e,
                exc_info=True,
            )
    return actions


# Define the concrete class for the static action
class ProvideInputAction(Action):
    """
    Concrete SAM Action class for the 'provide_required_input' functionality.
    """

    def __init__(
        self, attributes: Dict[str, Any], component: "A2AClientAgentComponent"
    ):
        """
        Initializes the ProvideInputAction.

        Args:
            attributes: The definition dictionary for this action.
            component: The parent A2AClientAgentComponent instance.
        """
        super().__init__(attributes, agent=component, config_fn=component.get_config)
        # Store component reference to call the handler method
        self.component = component

    def invoke(
        self, params: Dict[str, Any], meta: Dict[str, Any] = None
    ) -> ActionResponse:
        """
        Invokes the action by calling the handler method on the parent component.

        Args:
            params: Parameters provided to the action (follow_up_id, user_response, files).
            meta: Metadata associated with the action invocation (session_id).

        Returns:
            An ActionResponse containing the result of the follow-up A2A call.
        """
        # Directly call the handler method on the component instance
        if meta is None:
            meta = {}
        # The handler function expects the component instance as the first argument,
        # but the handler itself is now defined on the component, so we call it directly.
        return self.component._handle_provide_required_input(params, meta)


def create_provide_input_action(component: "A2AClientAgentComponent") -> Action:
    """
    Creates the static 'provide_required_input' SAM Action used for handling
    the A2A INPUT_REQUIRED state.

    Instantiates the concrete `ProvideInputAction` class.

    Args:
        component: The parent A2AClientAgentComponent instance.

    Returns:
        An initialized `ProvideInputAction` instance.
    """
    action_name = "provide_required_input"
    provide_input_action_def = {
        "name": action_name,
        "prompt_directive": "Provides the required input to continue a pending A2A task identified by a follow-up ID.",
        "params": [
            {
                "name": "follow_up_id",
                "desc": "The unique ID provided by the previous action call that requires input.",
                "type": "string",
                "required": True,
            },
            {
                "name": "user_response",
                "desc": "The user's response text to the agent's request for input.",
                "type": "string",
                "required": True,
            },
            {
                "name": "files",
                "desc": "Optional list of file URLs (e.g., from FileService) to include with the response. This list must be in json format.",
                "type": "list",
                "required": False,
            },
        ],
        # Scope matches the component's agent name
        "required_scopes": [f"{component.agent_name}:{action_name}:execute"],
    }
    # Instantiate the concrete ProvideInputAction class
    provide_input_action = ProvideInputAction(provide_input_action_def, component)

    log.info(
        "Created static action '%s' for agent '%s'.",
        provide_input_action.name,
        component.agent_name,
    )
    return provide_input_action
