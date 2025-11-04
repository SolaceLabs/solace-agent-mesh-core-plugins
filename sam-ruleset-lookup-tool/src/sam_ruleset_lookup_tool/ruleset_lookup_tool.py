"""
Implements the Ruleset Lookup Tool for Solace Agent Mesh.
"""

import re
from typing import Any, Dict, List, Optional

from google.genai import types as adk_types
from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool


class RulesetLookupTool(DynamicTool):
    """
    A generic, configuration-driven tool that provides text-based rulesets
    to an LLM for reasoning.
    """

    _ADK_TYPE_MAP = {
        "string": adk_types.Type.STRING,
        "boolean": adk_types.Type.BOOLEAN,
        "integer": adk_types.Type.INTEGER,
        "number": adk_types.Type.NUMBER,
    }

    def __init__(self, tool_config: Optional[Dict[str, Any]] = None):
        """
        Initializes the tool by loading and validating its configuration.
        """
        super().__init__(tool_config)

        # 1. Validate and store decision data
        self._data = self.tool_config.get("decision_data")
        if not self._data:
            raise ValueError("Tool config must contain 'decision_data'")

        required_keys = [
            "name",
            "description",
            "grouping_parameter",
            "input_parameters",
            "decision_tree_groups",
        ]
        for key in required_keys:
            if key not in self._data:
                raise ValueError(f"'decision_data' is missing required key: '{key}'")

        # 2. Parse optional behavior-controlling config
        self._default_group_key = self.tool_config.get("default_group_key", "_default")
        self._include_topics = self.tool_config.get(
            "include_topics_in_description", False
        )
        self._include_groups = self.tool_config.get(
            "include_groups_in_description", False
        )

        # 3. Pre-process and cache data for properties
        self._grouping_parameter = self._data["grouping_parameter"]
        self._all_topics = self._get_all_unique_topics()
        self._all_groups = list(self._data["decision_tree_groups"].keys())
        self._case_insensitive_groups = {
            key.lower(): value
            for key, value in self._data["decision_tree_groups"].items()
        }

    def _get_all_unique_topics(self) -> List[str]:
        """Extracts a unique, sorted list of all ruleset names."""
        all_topics = set()
        for group in self._data["decision_tree_groups"].values():
            for tree in group.get("decision_trees", []):
                if "name" in tree:
                    all_topics.add(tree["name"])
        return sorted(list(all_topics))

    def _sanitize_name(self, name: str) -> str:
        """Sanitizes a string to be a valid part of a Python function name."""
        sanitized = name.lower()
        # Replace any non-alphanumeric characters with an underscore
        sanitized = re.sub(r"[^a-z0-9]+", "_", sanitized)
        # Remove leading/trailing underscores
        return sanitized.strip("_")

    @property
    def tool_name(self) -> str:
        """Returns the sanitized and prefixed tool's name from the configuration."""
        sanitized_name = self._sanitize_name(self._data["name"])
        return f"get_rulesets_{sanitized_name}"

    @property
    def tool_description(self) -> str:
        """Dynamically generates the tool's description from the configuration."""
        description_parts = [self._data["description"]]

        if self._include_topics and self._all_topics:
            topics_str = ", ".join(self._all_topics)
            description_parts.append(
                f"\nThis tool can be used to determine outcomes for the following topics: {topics_str}."
            )

        if self._include_groups and self._all_groups:
            # Exclude default key from public list
            public_groups = [
                g for g in self._all_groups if g != self._default_group_key
            ]
            if public_groups:
                groups_str = ", ".join(sorted(public_groups))
                description_parts.append(
                    f"\nValid values for '{self._grouping_parameter}' are: {groups_str}."
                )

        description_parts.append(
            f"\nTo use this tool, you must provide the '{self._grouping_parameter}' to select the correct set of rules."
        )

        return "".join(description_parts)

    @property
    def parameters_schema(self) -> adk_types.Schema:
        """Dynamically generates the parameter schema from the configuration."""
        properties = {}
        required = []

        for param in self._data["input_parameters"]:
            param_name = param["name"]
            param_type_str = param.get("type", "string")
            adk_type = self._ADK_TYPE_MAP.get(param_type_str, adk_types.Type.STRING)

            properties[param_name] = adk_types.Schema(
                type=adk_type,
                description=param.get("description", ""),
            )

            if param.get("required", False):
                required.append(param_name)

        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties=properties,
            required=required or None,  # ADK expects None for empty list
        )

    async def _run_async_impl(
        self, args: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Selects and returns the appropriate ruleset logic based on the
        grouping parameter provided by the LLM.
        """
        group_value = args.get(self._grouping_parameter)
        if group_value is None:
            return {
                "error": f"The required parameter '{self._grouping_parameter}' was not provided."
            }

        # Find the group case-insensitively, falling back to the default key.
        # Assumes group_value is a string as per schema.
        selected_group_data = self._case_insensitive_groups.get(
            group_value.lower(),
            self._case_insensitive_groups.get(self._default_group_key.lower()),
        )

        if not selected_group_data:
            return {
                "error": f"No ruleset logic found for group '{group_value}', and no default group is configured."
            }

        # Format the rulesets into a single string
        tree_texts = []
        for tree in selected_group_data.get("decision_trees", []):
            tree_texts.append(
                f"Ruleset Name: {tree.get('name', 'N/A')}\n"
                f"Description: {tree.get('description', 'N/A')}\n"
                f"Logic:\n{tree.get('decision_logic', 'N/A')}"
            )

        final_logic = "\n\n---\n\n".join(tree_texts)

        return {"decision_logic": final_logic}
