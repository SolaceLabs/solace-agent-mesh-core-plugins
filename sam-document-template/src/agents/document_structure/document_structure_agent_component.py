"""Document Structure agent component for generating document structure specifications."""

import copy
from typing import Dict, Any

from solace_agent_mesh.agents.base_agent_component import (
    agent_info,
    BaseAgentComponent,
)

from .actions.generate_structure import GenerateStructure

info = copy.deepcopy(agent_info)
info.update(
    {
        "agent_name": "document_structure",
        "class_name": "DocumentStructureAgentComponent",
        "description": "agent for generating standardized document structure specifications",
        "config_parameters": [
            {
                "name": "agent_name",
                "required": True,
                "description": "Name of this document structure agent instance",
                "type": "string"
            },
            {
                "name": "document_title",
                "required": True,
                "description": "Title of the document to be generated",
                "type": "string"
            },
            {
                "name": "document_description",
                "required": True,
                "description": "Description of the document to be generated",
                "type": "string"
            },
            {
                "name": "document_format",
                "required": True,
                "description": "Format of the document to be generated (html or md)",
                "type": "string"
            },
            {
                "name": "document_rules",
                "required": False,
                "description": "Rules for the overall document to be generated",
                "type": "dict"
            },
            {
                "name": "document_sections",
                "required": False,
                "description": "Sections of the document to be generated",
                "type": "dict"
            }
        ]
    }
)

class DocumentStructureAgentComponent(BaseAgentComponent):
    info = info
    actions = [GenerateStructure]

    def __init__(self, module_info: Dict[str, Any] = None, **kwargs):
        """Initialize the Document Structure agent component."""
        module_info = module_info or info
        super().__init__(module_info=module_info, **kwargs)

        self.agent_name = self.get_config("agent_name")
        self.document_title = self.get_config("document_title")
        self.document_description = self.get_config("document_description")
        self.document_format = self.get_config("document_format")
        self.document_rules = self.get_config("document_rules", {})
        self.document_sections = self.get_config("document_sections", {})
        print(f"Document sections: {self.document_sections}")

        self.action_list.fix_scopes("<agent_name>", self.agent_name)
        module_info["agent_name"] = self.agent_name

        self._generate_agent_description()

    def _generate_agent_description(self):
        """Generate and store the agent description."""

        description = (
            f"This agent generates structured specifications for creating this document only: {self.document_title}.\n\n" 
            "It provides detailed outlines with clear rules and guidelines for both the overall document "
            f"and each individual section. The orchestrator will handle the actual file creation in this format: {self.document_format}."
        )

        self._agent_description = {
            "agent_name": self.agent_name,
            "description": description.strip(),
            "always_open": self.info.get("always_open", False),
            "actions": self.get_actions_summary()
        }

    def get_agent_summary(self):
        """Get a summary of the agent's capabilities."""
        return self._agent_description
