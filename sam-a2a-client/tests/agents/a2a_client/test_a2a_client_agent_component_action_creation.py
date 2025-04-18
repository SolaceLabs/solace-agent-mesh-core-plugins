import unittest
from unittest.mock import patch, MagicMock, call, ANY

# Adjust import paths as necessary
from .test_helpers import create_test_component, AgentCard, AgentSkill # Import helper and mocked types
from src.agents.a2a_client.actions.a2a_client_action import A2AClientAction
from solace_agent_mesh.common.action import Action

class TestA2AClientAgentComponentActionCreation(unittest.TestCase):

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAction') # Mock the dynamic action class
    @patch('src.agents.a2a_client.a2a_client_agent_component.Action') # Mock the base action class for static one
    @patch('logging.Logger.info')
    def test_create_actions_with_skills(self, mock_log_info, mock_base_action_cls, mock_a2a_action_cls):
        """Test _create_actions populates action_list from AgentCard skills and adds static action."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache)

        # Mock AgentCard and Skills
        mock_skill1 = MagicMock(spec=AgentSkill)
        mock_skill1.id = "skill_one"
        mock_skill1.name = "Skill One"
        mock_skill1.description = "Does one thing."

        mock_skill2 = MagicMock(spec=AgentSkill)
        mock_skill2.id = "skill_two"
        mock_skill2.name = "Skill Two"
        mock_skill2.description = "Does another thing."

        mock_card = MagicMock(spec=AgentCard)
        mock_card.skills = [mock_skill1, mock_skill2]
        component.agent_card = mock_card

        # Mock parameter inference
        mock_params = [{"name": "prompt", "type": "string", "required": True}]
        component._infer_params_from_skill = MagicMock(return_value=mock_params)

        # Mock the handler for the static action
        component._handle_provide_required_input = MagicMock()

        # Call the method under test
        component._create_actions()

        # Assertions for dynamic actions
        self.assertEqual(component._infer_params_from_skill.call_count, 2)
        component._infer_params_from_skill.assert_has_calls([call(mock_skill1), call(mock_skill2)])

        self.assertEqual(mock_a2a_action_cls.call_count, 2)
        mock_a2a_action_cls.assert_has_calls([
            call(skill=mock_skill1, component=component, inferred_params=mock_params),
            call(skill=mock_skill2, component=component, inferred_params=mock_params)
        ], any_order=True)

        # Assertions for static action
        expected_static_def = {
            "name": "provide_required_input",
            "prompt_directive": "Provides the required input to continue a pending A2A task.",
            "params": [
                {"name": "follow_up_id", "desc": ANY, "type": "string", "required": True},
                {"name": "user_response", "desc": ANY, "type": "string", "required": True},
                {"name": "files", "desc": ANY, "type": "list", "required": False},
            ],
            "required_scopes": [f"{component.agent_name}:provide_required_input:execute"],
        }
        mock_base_action_cls.assert_called_once_with(
            expected_static_def,
            agent=component,
            config_fn=component.get_config
        )
        # Check handler was set on the instance created by the mock constructor
        mock_static_action_instance = mock_base_action_cls.return_value
        mock_static_action_instance.set_handler.assert_called_once_with(component._handle_provide_required_input)


        # Assert action_list population
        # The list contains instances created by the mocked constructors
        self.assertEqual(len(component.action_list.actions), 3) # 2 dynamic + 1 static
        # Check that the instances added were the ones returned by the mocks
        self.assertIn(mock_a2a_action_cls.return_value, component.action_list.actions)
        self.assertIn(mock_base_action_cls.return_value, component.action_list.actions)

        # Assert component description update
        self.assertIn("Discovered Actions:", component.info["description"])
        # Check that the names from the mocked instances are in the description
        # Note: Mock instances might have default names unless configured.
        # We rely on the fact that add_action uses the name from the definition.
        self.assertIn(mock_skill1.id, component.info["description"])
        self.assertIn(mock_skill2.id, component.info["description"])
        self.assertIn("provide_required_input", component.info["description"])

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAction')
    @patch('src.agents.a2a_client.a2a_client_agent_component.Action')
    @patch('logging.Logger.warning')
    @patch('logging.Logger.info')
    def test_create_actions_no_skills(self, mock_log_info, mock_log_warning, mock_base_action_cls, mock_a2a_action_cls):
        """Test _create_actions handles AgentCard with no skills."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache)

        # Mock AgentCard with empty skills list
        mock_card = MagicMock(spec=AgentCard)
        mock_card.skills = []
        component.agent_card = mock_card

        component._infer_params_from_skill = MagicMock()
        component._handle_provide_required_input = MagicMock()

        # Call the method under test
        component._create_actions()

        # Assertions
        mock_log_warning.assert_called_once_with(f"No skills found in AgentCard for '{component.agent_name}'. No dynamic actions created.")
        component._infer_params_from_skill.assert_not_called()
        mock_a2a_action_cls.assert_not_called()

        # Static action should still be added
        mock_base_action_cls.assert_called_once()
        mock_static_action_instance = mock_base_action_cls.return_value
        mock_static_action_instance.set_handler.assert_called_once_with(component._handle_provide_required_input)

        self.assertEqual(len(component.action_list.actions), 1)
        self.assertIn(mock_base_action_cls.return_value, component.action_list.actions)

        # Assert component description update
        self.assertIn("No actions discovered or created.", component.info["description"])

    @patch('src.agents.a2a_client.a2a_client_agent_component.A2AClientAction')
    @patch('src.agents.a2a_client.a2a_client_agent_component.Action')
    @patch('logging.Logger.warning')
    @patch('logging.Logger.info')
    def test_create_actions_no_agent_card(self, mock_log_info, mock_log_warning, mock_base_action_cls, mock_a2a_action_cls):
        """Test _create_actions handles case where agent_card is None."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache)
        component.agent_card = None # Explicitly None

        component._infer_params_from_skill = MagicMock()
        component._handle_provide_required_input = MagicMock()

        # Call the method under test
        component._create_actions()

        # Assertions
        mock_log_warning.assert_called_once_with(f"No skills found in AgentCard for '{component.agent_name}'. No dynamic actions created.")
        component._infer_params_from_skill.assert_not_called()
        mock_a2a_action_cls.assert_not_called()

        # Static action should still be added
        mock_base_action_cls.assert_called_once()
        mock_static_action_instance = mock_base_action_cls.return_value
        mock_static_action_instance.set_handler.assert_called_once_with(component._handle_provide_required_input)

        self.assertEqual(len(component.action_list.actions), 1)
        self.assertIn(mock_base_action_cls.return_value, component.action_list.actions)

        # Assert component description update
        self.assertIn("No actions discovered or created.", component.info["description"])

if __name__ == '__main__':
    unittest.main()
