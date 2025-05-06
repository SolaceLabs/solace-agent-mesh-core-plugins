"""Action for generating document structure specifications."""

from typing import Dict, Any, List
import yaml


from solace_agent_mesh.common.action import Action
from solace_agent_mesh.common.action_response import (
    ActionResponse,
    ErrorInfo,
    InlineFile
)


class GenerateStructure(Action):
    """Action for generating document structure specifications."""
    def __init__(self, **kwargs):
        super().__init__(
            {
                "name": "generate_structure",
                "prompt_directive": (
                    "Generate a structured specification for creating a document. "
                    "This provides a clear outline with rules for the overall document "
                    "and each section. The orchestrator will handle the actual file creation."
                ),
                "params": [
                    {
                        "name": "extra_information",
                        "desc": "Extra information to be included in the document",
                        "type": "string",
                        "required": False
                    }
                ],
                "required_scopes": ["<agent_name>:generate_structure:execute"],
            },
            **kwargs,
        )

    def invoke(self, params: Dict[str, Any], meta: Dict[str, Any] = None) -> ActionResponse:
        """
        Generate a document structure specification.
        
        Args:
            params: Action parameters including title, description, format, document_rules, and sections.
            meta: Metadata for the action invocation.
        
        Returns:
            ActionResponse: The response containing the generated structure.
        """
        try:
            agent = self.get_agent()
            # Get the agent's parameters
            document_title = agent.document_title
            document_description = agent.document_description
            document_format = agent.document_format.lower()
            if document_format not in ["html", "md"]:
                raise ValueError("Invalid format. Supported formats are 'html' and 'md'.")
            
            document_rules = agent.document_rules
            document_sections = agent.document_sections

            # Generate the structure specification
            structure_spec = {
                "title": document_title,
                "description": document_description,
                "format": document_format,
                "document_rules": document_rules,
                "sections": []
            }
            for section in document_sections:
                section_title = section.get("title")
                section_description = section.get("description")
                section_rules = section.get("rules", [])
                
                if not section_title or not section_description:
                    raise ValueError("Each section must have a title and description.")
                
                structure_spec["sections"].append({
                    "title": section_title,
                    "description": section_description,
                    "rules": section_rules
                })

            # Format the output
            content = yaml.dump(structure_spec, default_flow_style=False)

            return ActionResponse(
                inline_files=[InlineFile(content, "document_structure_spec.yaml")]
            )
        except Exception as e:
            return ActionResponse(
                message=f"Error generating document structure specification: {str(e)}",
                error_info=ErrorInfo(str(e))
            )
