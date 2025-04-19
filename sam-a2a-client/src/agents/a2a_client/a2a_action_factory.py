"""
Factory functions for creating SAM Actions based on A2A Agent capabilities.
"""

import logging
from typing import List, Dict, Any, TYPE_CHECKING

from solace_agent_mesh.common.action import Action
from .actions.a2a_client_action import A2AClientAction
from ...common_a2a.types import AgentCard, AgentSkill

# Use TYPE_CHECKING to avoid circular import issues at runtime
if TYPE_CHECKING:
    from .a2a_client_agent_component import A2AClientAgentComponent

logger = logging.getLogger(__name__)


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
    logger.debug(f"Inferring parameters for skill '{skill.id}'. Using generic 'prompt' and 'files'.")
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
            "desc": "Optional list of file URLs (e.g., from FileService) to include with the prompt.",
            "type": "list", # SAM expects 'list' for array-like inputs
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
        logger.warning(
            f"No skills found in AgentCard for '{component.agent_name}'. No dynamic actions created."
        )
        return actions

    logger.info(
        f"Creating actions for agent '{component.agent_name}' based on {len(agent_card.skills)} AgentCard skills..."
    )
    for skill in agent_card.skills:
        if not skill.id:
             logger.warning(f"Skipping skill with missing ID in AgentCard for '{component.agent_name}'. Skill: {skill.name or 'Unnamed'}")
             continue
        try:
            # Infer parameters for the SAM action based on the A2A skill
            inferred_params = infer_params_from_skill(skill)
            # Create the specific action instance
            action = A2AClientAction(
                skill=skill, component=component, inferred_params=inferred_params
            )
            actions.append(action)
            logger.info(f"Created action '{action.name}' for skill '{skill.id}' for agent '{component.agent_name}'.")
        except Exception as e:
            # Log errors during individual action creation but continue with others
            logger.error(
                f"Failed to create action for skill '{skill.id}' for agent '{component.agent_name}': {e}", exc_info=True
            )
    return actions


def create_provide_input_action(component: "A2AClientAgentComponent") -> Action:
    """
    Creates the static 'provide_required_input' SAM Action used for handling
    the A2A INPUT_REQUIRED state.

    The actual handler logic for this action is implemented in the
    `A2AClientAgentComponent._handle_provide_required_input` method and
    set using `action.set_handler()`.

    Args:
        component: The parent A2AClientAgentComponent instance.

    Returns:
        An initialized SAM `Action` instance for providing follow-up input.
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
                "desc": "Optional list of file URLs (e.g., from FileService) to include with the response.",
                "type": "list",
                "required": False,
            },
        ],
        # Scope matches the component's agent name
        "required_scopes": [f"{component.agent_name}:{action_name}:execute"],
    }
    # Create a standard SAM Action instance
    provide_input_action = Action(
        provide_input_action_def, agent=component, config_fn=component.get_config
    )
    # Note: The handler function needs to be set on this action instance
    # by the component after creation, e.g.,
    # provide_input_action.set_handler(component._handle_provide_required_input)
    logger.info(f"Created static action '{provide_input_action.name}' for agent '{component.agent_name}'.")
    return provide_input_action
