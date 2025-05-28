import unittest
from unittest.mock import patch, MagicMock, ANY, call

# Adjust import paths as necessary
from src.agents.a2a_client.a2a_client_agent_component import A2AClientAgentComponent
from src.agents.a2a_client.actions.a2a_client_action import A2AClientAction
from src.agents.a2a_client.a2a_action_factory import ProvideInputAction
from src.common_a2a.types import AgentCard, AgentSkill, AgentCapabilities
from solace_agent_mesh.common.action_list import ActionList

# Import helper to create component instance
from .test_helpers import create_test_component


class TestA2AClientAgentComponentActionCreation(unittest.TestCase):

    def setUp(self):
        # Mock cache service needed for component creation
        self.mock_cache = MagicMock()
        # Create component using helper, passing the mock cache
        self.component = create_test_component(
            cache_service_instance=self.mock_cache
        )
        # Mock the connection handler and assign a mock AgentCard
        self.mock_connection_handler = MagicMock()
        self.mock_agent_card = MagicMock(spec=AgentCard)
        self.mock_agent_card.skills = [] # Start with no skills
        self.mock_connection_handler.agent_card = self.mock_agent_card
        self.component.connection_handler = self.mock_connection_handler

        # Patch the action factory functions where they are used
        self.patcher_create_actions = patch('src.agents.a2a_client.a2a_client_agent_component.create_actions_from_card')
        self.patcher_create_provide_input = patch('src.agents.a2a_client.a2a_client_agent_component.create_provide_input_action')
        self.mock_create_actions = self.patcher_create_actions.start()
        self.mock_create_provide_input = self.patcher_create_provide_input.start()

        # Mock the action instances returned by the factories
        # Explicitly set the name attribute after creation
        self.mock_dynamic_action1 = MagicMock(spec=A2AClientAction)
        self.mock_dynamic_action1.name = "dynamic_action_1"
        self.mock_dynamic_action2 = MagicMock(spec=A2AClientAction)
        self.mock_dynamic_action2.name = "dynamic_action_2"
        self.mock_static_action = MagicMock(spec=ProvideInputAction)
        self.mock_static_action.name = "provide_required_input"


        self.mock_create_actions.return_value = [] # Default to no dynamic actions
        self.mock_create_provide_input.return_value = self.mock_static_action

    def tearDown(self):
        self.patcher_create_actions.stop()
        self.patcher_create_provide_input.stop()

    def test_create_actions_no_skills(self):
        """Test _create_actions when AgentCard has no skills."""
        self.mock_agent_card.skills = []
        self.mock_create_actions.return_value = [] # Explicitly return empty list

        self.component._create_actions()

        # Verify factories were called
        self.mock_create_actions.assert_called_once_with(self.mock_agent_card, self.component)
        self.mock_create_provide_input.assert_called_once_with(self.component)

        # Verify action list contains only the static action
        self.assertEqual(len(self.component.action_list.actions), 1)
        self.assertIn(self.mock_static_action, self.component.action_list.actions)

        # Verify component description update
        self.assertIn("No dynamic actions discovered.", self.component.info["description"])

    def test_create_actions_one_skill(self):
        """Test _create_actions with one skill in AgentCard."""
        # Mock skill (no need for spec if AgentSkill is mocked/unavailable)
        mock_skill1 = MagicMock()
        mock_skill1.id = "skill1"
        mock_skill1.name = "Skill One"
        self.mock_agent_card.skills = [mock_skill1]
        self.mock_create_actions.return_value = [self.mock_dynamic_action1] # Factory returns one action

        self.component._create_actions()

        # Verify factories were called
        self.mock_create_actions.assert_called_once_with(self.mock_agent_card, self.component)
        self.mock_create_provide_input.assert_called_once_with(self.component)

        # Verify action list contains dynamic + static action
        self.assertEqual(len(self.component.action_list.actions), 2)
        self.assertIn(self.mock_dynamic_action1, self.component.action_list.actions)
        self.assertIn(self.mock_static_action, self.component.action_list.actions)

        # Verify component description update
        self.assertIn("Discovered Actions:", self.component.info["description"])
        self.assertIn(self.mock_dynamic_action1.name, self.component.info["description"])
        self.assertNotIn(self.mock_static_action.name, self.component.info["description"]) # Static action not listed

    def test_create_actions_multiple_skills(self):
        """Test _create_actions with multiple skills in AgentCard."""
        mock_skill1 = MagicMock(id="skill1", name="Skill One")
        mock_skill2 = MagicMock(id="skill2", name="Skill Two")
        self.mock_agent_card.skills = [mock_skill1, mock_skill2]
        # Factory returns multiple actions
        self.mock_create_actions.return_value = [self.mock_dynamic_action1, self.mock_dynamic_action2]

        self.component._create_actions()

        # Verify factories were called
        self.mock_create_actions.assert_called_once_with(self.mock_agent_card, self.component)
        self.mock_create_provide_input.assert_called_once_with(self.component)

        # Verify action list contains dynamic + static action
        self.assertEqual(len(self.component.action_list.actions), 3)
        self.assertIn(self.mock_dynamic_action1, self.component.action_list.actions)
        self.assertIn(self.mock_dynamic_action2, self.component.action_list.actions)
        self.assertIn(self.mock_static_action, self.component.action_list.actions)

        # Verify component description update
        self.assertIn("Discovered Actions:", self.component.info["description"])
        self.assertIn(self.mock_dynamic_action1.name, self.component.info["description"])
        self.assertIn(self.mock_dynamic_action2.name, self.component.info["description"])
        self.assertNotIn(self.mock_static_action.name, self.component.info["description"])

    @patch('solace_ai_connector.common.log.log.info') # Patch the correct log object
    def test_create_actions_logs_correctly(self, mock_log_info):
        """Test that logging occurs during action creation."""
        mock_skill1 = MagicMock(id="skill1", name="Skill One")
        self.mock_agent_card.skills = [mock_skill1]
        self.mock_create_actions.return_value = [self.mock_dynamic_action1]

        self.component._create_actions()

        # Check for specific log messages
        mock_log_info.assert_any_call("Creating SAM actions for '%s'...", self.component.agent_name)
        mock_log_info.assert_any_call(
            "Action creation complete for '%s'. Total actions: %d",
            self.component.agent_name,
            2 # 1 dynamic + 1 static
        )

if __name__ == '__main__':
    unittest.main()
