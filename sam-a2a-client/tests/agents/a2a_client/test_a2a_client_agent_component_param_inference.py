import unittest
from unittest.mock import MagicMock

# Adjust import paths as necessary
from .test_helpers import create_test_component, AgentSkill # Import helper and mocked types

class TestA2AClientAgentComponentParamInference(unittest.TestCase):

    def test_infer_params_from_skill_simple(self):
        """Test _infer_params_from_skill returns the generic 'prompt' parameter."""
        # Provide a mock cache service to prevent init warning
        mock_cache = MagicMock()
        component = create_test_component(cache_service_instance=mock_cache)

        # Mock A2A AgentSkill - Remove spec=AgentSkill as AgentSkill is already a mock here
        mock_skill = MagicMock()
        mock_skill.id = "test_skill"
        mock_skill.name = "Test Skill"
        mock_skill.description = "Does something."

        # Call the method under test
        inferred_params = component._infer_params_from_skill(mock_skill)

        # Assertions
        self.assertIsInstance(inferred_params, list)
        self.assertEqual(len(inferred_params), 1)

        expected_param = {
            "name": "prompt",
            "desc": "The user request or prompt for the agent.",
            "type": "string",
            "required": True,
        }
        self.assertEqual(inferred_params[0], expected_param)

if __name__ == '__main__':
    unittest.main()
