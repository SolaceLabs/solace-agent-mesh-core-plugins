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
    Infers SAM action parameters from an A2A skill.
    Simple initial implementation: always returns a generic 'prompt'.
    """
    logger.debug(f"Inferring parameters for skill '{skill.id}'. Using generic 'prompt'.")
    return [
        {
            "name": "prompt",
            "desc": "The user request or prompt for the agent.",
            "type": "string",
            "required": True,
        },
        {
            "name": "files",
            "desc": "Optional list of file URLs to include with the prompt.",
            "type": "list",
            "required": False,
        },
    ]


def create_actions_from_card(
    agent_card: AgentCard, component: "A2AClientAgentComponent"
) -> List[Action]:
    """
    Dynamically creates SAM actions based on the skills found in the AgentCard.
    """
    actions = []
    if not agent_card or not agent_card.skills:
        logger.warning(
            f"No skills found in AgentCard for '{component.agent_name}'. No dynamic actions created."
        )
        return actions

    logger.info(
        f"Creating actions for agent '{component.agent_name}' based on {len(agent_card.skills)} AgentCard skills..."
    )
    for skill in agent_card.skills:
        try:
            inferred_params = infer_params_from_skill(skill)
            action = A2AClientAction(
                skill=skill, component=component, inferred_params=inferred_params
            )
            actions.append(action)
            logger.info(f"Created action '{action.name}' for skill '{skill.id}'")
        except Exception as e:
            logger.error(
                f"Failed to create action for skill '{skill.id}': {e}", exc_info=True
            )
    return actions


def create_provide_input_action(component: "A2AClientAgentComponent") -> Action:
    """
    Creates the static 'provide_required_input' action.
    """
    provide_input_action_def = {
        "name": "provide_required_input",
        "prompt_directive": "Provides the required input to continue a pending A2A task.",
        "params": [
            {
                "name": "follow_up_id",
                "desc": "The ID provided by the previous action call that requires input.",
                "type": "string",
                "required": True,
            },
            {
                "name": "user_response",
                "desc": "The user's response to the agent's request for input.",
                "type": "string",
                "required": True,
            },
            {
                "name": "files",
                "desc": "Optional list of file URLs to include with the response.",
                "type": "list",
                "required": False,
            },
        ],
        "required_scopes": [f"{component.agent_name}:provide_required_input:execute"],
    }
    provide_input_action = Action(
        provide_input_action_def, agent=component, config_fn=component.get_config
    )
    # The handler is set in the main component after creation
    logger.info(f"Created static action '{provide_input_action.name}'")
    return provide_input_action
