import unittest
from unittest.mock import MagicMock, patch, ANY

# Adjust import paths as necessary
from src.agents.a2a_client.actions.a2a_client_action import A2AClientAction, AgentSkill

# Mock the parent component class if needed for type hints or instantiation
class MockA2AClientAgentComponent:
    def __init__(self, agent_name="mock_agent"):
        self.agent_name = agent_name
        self.get_config = MagicMock() # Mock the config function

class TestA2AClientAction(unittest.TestCase):

    @patch('src.agents.a2a_client.actions.a2a_client_action.Action.__init__')
    def test_init_method(self, mock_super_init):
        """Test the __init__ method initializes the Action correctly."""

        # Mock A2A AgentSkill (replace Any with actual AgentSkill if import works)
        mock_skill = MagicMock(spec=AgentSkill)
        mock_skill.id = "test_skill_id"
        mock_skill.name = "Test Skill Name"
        mock_skill.description = "This is a test skill description."

        # Mock the parent component
        mock_component = MockA2AClientAgentComponent(agent_name="test_sam_agent")

        # Mock inferred parameters
        mock_params = [
            {"name": "prompt", "desc": "User prompt", "type": "string", "required": True}
        ]

        # Instantiate the action
        action = A2AClientAction(
            skill=mock_skill,
            component=mock_component, # type: ignore
            inferred_params=mock_params
        )

        # Assert that super().__init__ was called with the correct definition
        expected_definition = {
            "name": "test_skill_id",
            "prompt_directive": "This is a test skill description.",
            "params": mock_params,
            "required_scopes": ["test_sam_agent:test_skill_id:execute"],
        }
        mock_super_init.assert_called_once_with(
            expected_definition,
            agent=mock_component,
            config_fn=mock_component.get_config
        )

        # Assert instance variables are stored
        self.assertEqual(action.skill, mock_skill)
        self.assertEqual(action.component, mock_component)

    @patch('src.agents.a2a_client.actions.a2a_client_action.Action.__init__')
    def test_init_method_no_skill_description(self, mock_super_init):
        """Test __init__ uses a default prompt_directive if skill description is missing."""

        mock_skill = MagicMock(spec=AgentSkill)
        mock_skill.id = "skill_no_desc"
        mock_skill.name = "Skill Without Description"
        mock_skill.description = None # Explicitly None

        mock_component = MockA2AClientAgentComponent(agent_name="test_sam_agent")
        mock_params = [{"name": "prompt", "desc": "User prompt", "type": "string", "required": True}]

        A2AClientAction(
            skill=mock_skill,
            component=mock_component, # type: ignore
            inferred_params=mock_params
        )

        expected_definition = {
            "name": "skill_no_desc",
            "prompt_directive": "Execute the Skill Without Description skill.", # Default generated
            "params": mock_params,
            "required_scopes": ["test_sam_agent:skill_no_desc:execute"],
        }
        mock_super_init.assert_called_once_with(
            expected_definition,
            agent=mock_component,
            config_fn=mock_component.get_config
        )

if __name__ == '__main__':
    unittest.main()
