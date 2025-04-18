import unittest
from unittest.mock import patch, MagicMock, call, ANY

# Adjust import paths as necessary
from .test_helpers import (
    create_test_component,
    AgentCard,
    AgentSkill,
)  # Import helper and mocked types

# Import the factory functions directly to patch them
from src.agents.a2a_client import a2a_action_factory
from src.agents.a2a_client.actions.a2a_client_action import A2AClientAction
from solace_agent_mesh.common.action import Action


class TestA2AClientAgentComponentActionCreation(unittest.TestCase):

    @patch(
        "src.agents.a2a_client.a2a_action_factory.A2AClientAction"
    )  # Patch where dynamic action is created
    @patch(
        "src.agents.a2a_client.a2a_action_factory.Action"
    )  # Patch where static action is created
    @patch("logging.Logger.info")
    def test_create_actions_with_skills(
        self, mock_log_info, mock_base_action_cls, mock_a2a_action_cls
    ):
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
        # Simulate the agent_card being set by the connection handler during run
        component.connection_handler = MagicMock()
        component.connection_handler.agent_card = mock_card

        # Mock parameter inference within the factory module
        mock_params = [{"name": "prompt", "type": "string", "required": True}]
        a2a_action_factory.infer_params_from_skill = MagicMock(return_value=mock_params)

        # Mock the handler method on the component instance
        component.handle_provide_required_input = MagicMock()

        # Configure mock action instances to have a name attribute
        mock_a2a_action_instance1 = MagicMock(spec=A2AClientAction)
        mock_a2a_action_instance1.name = "skill_one"
        mock_a2a_action_instance2 = MagicMock(spec=A2AClientAction)
        mock_a2a_action_instance2.name = "skill_two"
        mock_a2a_action_cls.side_effect = [
            mock_a2a_action_instance1,
            mock_a2a_action_instance2,
        ]

        # Configure mock static action instance
        mock_static_action_instance = MagicMock(spec=Action)
        mock_static_action_instance.name = "provide_required_input"
        # *** FIX: Explicitly add set_handler method to the mock instance ***
        mock_static_action_instance.set_handler = MagicMock()
        mock_base_action_cls.return_value = mock_static_action_instance


        # --- Call the relevant part of the run method logic ---
        # Directly call the factory functions as they would be called in `run`
        dynamic_actions = a2a_action_factory.create_actions_from_card(
            component.agent_card, component
        )
        static_action = a2a_action_factory.create_provide_input_action(component)
        # Now this call should work
        static_action.set_handler(
            lambda params, meta: component.handle_provide_required_input(
                component, params, meta
            )
        ) # Simulate setting the handler
        # Use add_action in a loop
        for action in dynamic_actions:
            component.action_list.add_action(action)
        component.action_list.add_action(static_action)

        # Simulate description update
        original_description = component.info.get(
            "description", "Component to interact with an external A2A agent."
        )
        action_names = [a.name for a in component.action_list.actions]
        if action_names:
            component.info["description"] = (
                f"{original_description}\nDiscovered Actions: {', '.join(action_names)}"
            )
        # --- End of simulated run logic ---


        # Assertions for dynamic actions
        self.assertEqual(a2a_action_factory.infer_params_from_skill.call_count, 2)
        a2a_action_factory.infer_params_from_skill.assert_has_calls(
            [call(mock_skill1), call(mock_skill2)]
        )

        self.assertEqual(mock_a2a_action_cls.call_count, 2)
        mock_a2a_action_cls.assert_has_calls(
            [
                call(
                    skill=mock_skill1, component=component, inferred_params=mock_params
                ),
                call(
                    skill=mock_skill2, component=component, inferred_params=mock_params
                ),
            ],
            any_order=True,
        )

        # Assertions for static action
        expected_static_def = {
            "name": "provide_required_input",
            "prompt_directive": "Provides the required input to continue a pending A2A task.",
            "params": [
                {
                    "name": "follow_up_id",
                    "desc": ANY,
                    "type": "string",
                    "required": True,
                },
                {
                    "name": "user_response",
                    "desc": ANY,
                    "type": "string",
                    "required": True,
                },
                {"name": "files", "desc": ANY, "type": "list", "required": False},
            ],
            "required_scopes": [
                f"{component.agent_name}:provide_required_input:execute"
            ],
        }
        mock_base_action_cls.assert_called_once_with(
            expected_static_def, agent=component, config_fn=component.get_config
        )
        # Check handler was set on the instance created by the mock constructor
        mock_static_action_instance.set_handler.assert_called_once()
        # Verify the lambda was set (checking the object directly is tricky, check it was called)
        self.assertTrue(callable(mock_static_action_instance.set_handler.call_args[0][0]))


        # Assert action_list population
        self.assertEqual(len(component.action_list.actions), 3)  # 2 dynamic + 1 static
        self.assertIn(mock_a2a_action_instance1, component.action_list.actions)
        self.assertIn(mock_a2a_action_instance2, component.action_list.actions)
        self.assertIn(mock_static_action_instance, component.action_list.actions)

        # Assert component description update
        self.assertIn("Discovered Actions:", component.info["description"])
        self.assertIn(mock_a2a_action_instance1.name, component.info["description"])
        self.assertIn(mock_a2a_action_instance2.name, component.info["description"])
        self.assertIn(mock_static_action_instance.name, component.info["description"])

    @patch(
        "src.agents.a2a_client.a2a_action_factory.A2AClientAction"
    )  # Patch where dynamic action is created
    @patch(
        "src.agents.a2a_client.a2a_action_factory.Action"
    )  # Patch where static action is created
    @patch("logging.Logger.warning")
    @patch("logging.Logger.info")
    def test_create_actions_no_skills(
        self, mock_log_info, mock_log_warning, mock_base_action_cls, mock_a2a_action_cls
    ):
        """Test _create_actions handles AgentCard with no skills."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache)

        # Mock AgentCard with empty skills list
        mock_card = MagicMock(spec=AgentCard)
        mock_card.skills = []
        # Simulate the agent_card being set by the connection handler during run
        component.connection_handler = MagicMock()
        component.connection_handler.agent_card = mock_card

        # Mock parameter inference within the factory module
        a2a_action_factory.infer_params_from_skill = MagicMock()

        # Mock the handler method on the component instance
        component.handle_provide_required_input = MagicMock()

        # Configure mock static action instance
        mock_static_action_instance = MagicMock(spec=Action)
        mock_static_action_instance.name = "provide_required_input"
        # *** FIX: Explicitly add set_handler method to the mock instance ***
        mock_static_action_instance.set_handler = MagicMock()
        mock_base_action_cls.return_value = mock_static_action_instance

        # --- Call the relevant part of the run method logic ---
        dynamic_actions = a2a_action_factory.create_actions_from_card(
            component.agent_card, component
        )
        static_action = a2a_action_factory.create_provide_input_action(component)
        # Now this call should work
        static_action.set_handler(
            lambda params, meta: component.handle_provide_required_input(
                component, params, meta
            )
        )
        # Use add_action in a loop (dynamic_actions is empty here)
        for action in dynamic_actions:
            component.action_list.add_action(action)
        component.action_list.add_action(static_action)

        # Simulate description update
        original_description = component.info.get(
            "description", "Component to interact with an external A2A agent."
        )
        action_names = [a.name for a in component.action_list.actions]
        if action_names:
            component.info["description"] = (
                f"{original_description}\nDiscovered Actions: {', '.join(action_names)}"
            )
        # --- End of simulated run logic ---

        # Assertions
        mock_log_warning.assert_called_once_with(
            f"No skills found in AgentCard for '{component.agent_name}'. No dynamic actions created."
        )
        a2a_action_factory.infer_params_from_skill.assert_not_called()
        mock_a2a_action_cls.assert_not_called()

        # Static action should still be added
        mock_base_action_cls.assert_called_once()
        mock_static_action_instance.set_handler.assert_called_once()

        self.assertEqual(len(component.action_list.actions), 1)
        self.assertIn(mock_static_action_instance, component.action_list.actions)

        # Assert component description update
        self.assertIn(
            "Discovered Actions: provide_required_input", component.info["description"]
        )

    @patch(
        "src.agents.a2a_client.a2a_action_factory.A2AClientAction"
    )  # Patch where dynamic action is created
    @patch(
        "src.agents.a2a_client.a2a_action_factory.Action"
    )  # Patch where static action is created
    @patch("logging.Logger.warning")
    @patch("logging.Logger.info")
    def test_create_actions_no_agent_card(
        self, mock_log_info, mock_log_warning, mock_base_action_cls, mock_a2a_action_cls
    ):
        """Test _create_actions handles case where agent_card is None."""
        # Provide a mock cache service
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache)
        # Simulate agent_card being None after connection attempt
        component.connection_handler = MagicMock()
        component.connection_handler.agent_card = None

        # Mock parameter inference within the factory module
        a2a_action_factory.infer_params_from_skill = MagicMock()

        # Mock the handler method on the component instance
        component.handle_provide_required_input = MagicMock()

        # Configure mock static action instance
        mock_static_action_instance = MagicMock(spec=Action)
        mock_static_action_instance.name = "provide_required_input"
        # *** FIX: Explicitly add set_handler method to the mock instance ***
        mock_static_action_instance.set_handler = MagicMock()
        mock_base_action_cls.return_value = mock_static_action_instance

        # --- Call the relevant part of the run method logic ---
        dynamic_actions = a2a_action_factory.create_actions_from_card(
            component.agent_card, component # Pass None here
        )
        static_action = a2a_action_factory.create_provide_input_action(component)
        # Now this call should work
        static_action.set_handler(
            lambda params, meta: component.handle_provide_required_input(
                component, params, meta
            )
        )
        # Use add_action in a loop (dynamic_actions is empty here)
        for action in dynamic_actions:
            component.action_list.add_action(action)
        component.action_list.add_action(static_action)

        # Simulate description update
        original_description = component.info.get(
            "description", "Component to interact with an external A2A agent."
        )
        action_names = [a.name for a in component.action_list.actions]
        if action_names:
            component.info["description"] = (
                f"{original_description}\nDiscovered Actions: {', '.join(action_names)}"
            )
        # --- End of simulated run logic ---

        # Assertions
        mock_log_warning.assert_called_once_with(
            f"No skills found in AgentCard for '{component.agent_name}'. No dynamic actions created."
        )
        a2a_action_factory.infer_params_from_skill.assert_not_called()
        mock_a2a_action_cls.assert_not_called()

        # Static action should still be added
        mock_base_action_cls.assert_called_once()
        mock_static_action_instance.set_handler.assert_called_once()

        self.assertEqual(len(component.action_list.actions), 1)
        self.assertIn(mock_static_action_instance, component.action_list.actions)

        # Assert component description update
        self.assertIn(
            "Discovered Actions: provide_required_input", component.info["description"]
        )


if __name__ == "__main__":
    unittest.main()
