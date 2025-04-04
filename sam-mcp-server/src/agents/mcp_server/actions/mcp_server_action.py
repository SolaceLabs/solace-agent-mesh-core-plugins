"""Action for invoking MCP server operations.

This module provides an action class that handles invocation of MCP server
operations including tools, resources, and prompts.
"""

import logging
import random
from typing import Any, Dict, Optional

from solace_agent_mesh.common.action import Action
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo
from solace_agent_mesh.services.file_service import FileService

import mcp.types as types

logger = logging.getLogger(__name__)


class MCPServerAction(Action):
    """Action for invoking operations on an MCP server.

    This action handles validation and execution of tool calls, resource retrievals,
    and prompt usage on a configured MCP server instance.

    Attributes:
        server: The AsyncServerThread instance to invoke operations on.
        operation_type: The type of operation (tool, resource, or prompt).
        schema: The parameter schema for validation.
    """

    def __init__(
        self,
        server: Any,
        operation_type: str,
        name: str,
        description: str,
        schema: Dict[str, Any],
        **kwargs,
    ):
        """Initialize the MCP server action.

        Args:
            server: The AsyncServerThread instance to invoke operations on.
            operation_type: Type of operation ('tool', 'resource', or 'prompt').
            name: Name of the specific operation.
            description: Description of what the operation does.
            schema: JSON schema for parameter validation.
        """
        respond_as_param = {
            "name": "respond_as",
            "description": "One of 'file' or 'text'. Determines how the response should be returned. default is 'text'",
            "type": "string",
        }
        params = [
            {
                "name": param_name,
                "desc": self._format_description(param_props),
                "type": param_props.get("type", "string"),
                "required": param_name in schema.get("required", []),
            }
            for param_name, param_props in schema.get("properties", {}).items()
        ]
        params.append(
            {
                "name": respond_as_param["name"],
                "desc": self._format_description(respond_as_param),
                "type": respond_as_param.get("type", "string"),
                "required": respond_as_param.get("required", False),
            }
        )

        super().__init__(
            {
                "name": name,
                "prompt_directive": description,
                "params": params,
                "required_scopes": [f"<agent_name>:{name}:execute"],
            },
            **kwargs,
        )

        self.server = server
        self.operation_type = operation_type
        self.schema = schema

    def _format_description(self, param_props: Dict[str, Any]) -> str:
        """Format a parameter description for the action prompt directive.

        Args:
            param_props: Parameter properties dictionary.

        Returns:
            Formatted parameter description string.
        """
        desc = param_props.get("description", "")
        desc += ", " if desc else ""
        desc += param_props.get("type", "string")
        return desc

    def _validate_parameters(self, params: Dict[str, Any]) -> Optional[str]:
        """Validate parameters against the operation's schema.

        Args:
            params: Dictionary of parameter values to validate.

        Returns:
            Error message string if validation fails, None if validation passes.
        """
        # Check required parameters
        required = self.schema.get("required", [])
        for param in required:
            if param not in params:
                return f"Missing required parameter: {param}"

        # Validate parameter types
        properties = self.schema.get("properties", {})
        for name, value in params.items():
            if name in properties:
                param_type = properties[name].get("type")
                if param_type == "number":
                    if not isinstance(value, (int, float)):
                        return f"Parameter {name} must be a number"
                elif param_type == "integer":
                    if not isinstance(value, int):
                        return f"Parameter {name} must be an integer"
                elif param_type == "string":
                    if not isinstance(value, str):
                        return f"Parameter {name} must be a string"
                elif param_type == "boolean":
                    if not isinstance(value, bool):
                        return f"Parameter {name} must be a boolean"

        return None

    def invoke(
        self, params: Dict[str, Any], meta: Dict[str, Any] = None
    ) -> ActionResponse:
        """Execute the MCP server operation.

        Args:
            params: Parameters for the operation.
            meta: Optional metadata dictionary.

        Returns:
            ActionResponse containing the operation result or error information.
        """
        try:
            # Validate parameters
            validation_error = self._validate_parameters(params)
            if validation_error:
                return ActionResponse(
                    message=f"Parameter validation failed: {validation_error}",
                    error_info=ErrorInfo(validation_error),
                )

            respond_as = params.pop("respond_as", "text")
            if respond_as not in ["text", "file"]:
                logger.warning(
                    "Invalid 'respond_as' value: %s. Setting to default", respond_as
                )
                respond_as = "text"

            # Execute the operation via the async server thread
            try:
                result = self.server.execute(self.operation_type, self.name, params)
            except Exception as e:
                logger.error(
                    "MCP server operation failed: %s - %s",
                    self.operation_type,
                    str(e),
                    exc_info=True,
                )
                raise RuntimeError(f"MCP server operation failed: {str(e)}") from e

            # Convert MCP response types to string representation
            # Handle list of content objects
            contents = []
            for item in result.content:
                if isinstance(item, types.TextContent):
                    contents.append(item.text)
                elif isinstance(item, types.ImageContent):
                    contents.append(f"[Image: {item.mime_type}]")
                elif isinstance(item, types.EmbeddedResource):
                    contents.append(f"[Resource: {item.name}]")
                else:
                    contents.append(str(item))
            response_text = "\n".join(contents)

            if respond_as == "file":
                # Save response text to a file
                file_service = FileService()
                file_name = (
                    self.name
                    + "_response"
                    + str(random.randint(100000, 999999))
                    + ".txt"
                )
                agent = self.get_agent()
                file_meta = file_service.upload_from_buffer(
                    response_text,
                    file_name,
                    meta.get("session_id"),
                    data_source=f"{agent.agent_name} - {self.name}",
                )

                return ActionResponse(
                    message=f"Response saved to file: {file_name}", files=[file_meta]
                )
            else:
                return ActionResponse(message=response_text)

        except Exception as e:
            error_msg = f"Error executing {self.operation_type} '{self.name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            return ActionResponse(message=error_msg, error_info=ErrorInfo(str(e)))
