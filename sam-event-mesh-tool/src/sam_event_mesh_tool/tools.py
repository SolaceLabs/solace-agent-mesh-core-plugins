import re
from typing import Any, Dict, Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_ai_connector.common.log import log
from solace_ai_connector.common.message import Message
from solace_ai_connector.common.utils import get_data_value
from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool
from solace_agent_mesh.agent.sac.component import SamAgentComponent
from solace_agent_mesh.agent.tools.tool_config_types import AnyToolConfig


def _build_payload_and_resolve_params(
    parameters_map: Dict[str, Any],
    params: Dict[str, Any],
    tool_context: ToolContext,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Build the message payload and resolve all parameters with defaults applied.

    Args:
        parameters_map: Dictionary mapping parameter names to their configuration.
        params: Dictionary of provided parameter values from the LLM.
        tool_context: The tool context, used to source context-based parameters.

    Returns:
        Tuple of (payload, resolved_params) where:
        - payload: Dict containing the structured payload with nested paths.
        - resolved_params: Dict containing all parameters with defaults and context values applied.
    """
    payload = {}
    resolved_params = {}
    a2a_context = tool_context.state.get("a2a_context", {})

    # Iterate over all defined parameters, not just provided ones
    for param_name, param_config in parameters_map.items():
        value = None
        if "context_expression" in param_config:
            # Source value from context
            expr = param_config["context_expression"]
            value = get_data_value(a2a_context, expr, True)
        elif param_name in params:
            # Use provided value from LLM
            value = params[param_name]
        elif "default" in param_config:
            # Use default value
            value = param_config["default"]
        else:
            # No value provided and no default - skip this parameter entirely
            continue

        # Add to resolved params (used for topic template and debugging)
        resolved_params[param_name] = value

        # Only add to payload if parameter has a payload_path
        if "payload_path" in param_config:
            # Build the nested structure
            path = param_config["payload_path"]
            current = payload
            parts = path.split(".")
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value

    return payload, resolved_params


def _fill_topic_template(template: str, params: Dict[str, Any]) -> str:
    """Fill a topic template with parameter values."""

    def replace_param(match):
        param_expr = match.group(1).strip()
        if "://" in param_expr:
            _, param = param_expr.split("//", 1)
            param = param.strip()
        else:
            param = param_expr

        if param not in params:
            raise ValueError(f"Missing required parameter '{param}' for topic template")
        return str(params[param])

    return re.sub(r"\{\{(.*?)\}\}", replace_param, template)


class EventMeshTool(DynamicTool):
    """A dynamic tool to send requests into the Solace event mesh."""

    def __init__(self, tool_config: Dict[str, Any]):
        super().__init__(tool_config)
        self.session_id: Optional[str] = None

    async def init(self, component: "SamAgentComponent", tool_config: "AnyToolConfig"):
        """Initializes the dedicated request-response session for this tool instance."""
        log_identifier = f"[EventMeshTool:{self.tool_name}:init]"
        log.info("%s Initializing event mesh session.", log_identifier)

        # Fail fast if configuration is missing
        if "event_mesh_config" not in self.tool_config:
            raise ValueError(
                f"Configuration error in tool '{self.tool_name}': "
                "'event_mesh_config' is a required block."
            )
        event_mesh_config = self.tool_config["event_mesh_config"]
        if "broker_config" not in event_mesh_config:
            raise ValueError(
                f"Configuration error in tool '{self.tool_name}': "
                "'broker_config' is a required block inside 'event_mesh_config'."
            )

        try:
            self.session_id = component.create_request_response_session(
                session_config=event_mesh_config
            )
            log.info("%s Session created with ID: %s", log_identifier, self.session_id)
        except Exception as e:
            log.error(
                "%s Failed to create request/response session: %s", log_identifier, e
            )
            raise

    async def cleanup(
        self, component: "SamAgentComponent", tool_config: "AnyToolConfig"
    ):
        """Destroys the dedicated request-response session for this tool instance."""
        log_identifier = f"[EventMeshTool:{self.tool_name}:cleanup]"
        if self.session_id:
            log.info("%s Destroying session ID: %s", log_identifier, self.session_id)
            component.destroy_request_response_session(self.session_id)
            self.session_id = None
            log.info("%s Session destroyed.", log_identifier)

    @property
    def tool_name(self) -> str:
        """Return the function name that the LLM will call."""
        return self.tool_config.get("tool_name", "unnamed_event_mesh_tool")

    @property
    def tool_description(self) -> str:
        """Return the description of what this tool does."""
        return self.tool_config.get("description", "")

    @property
    def parameters_schema(self) -> adk_types.Schema:
        """Return the ADK Schema defining the tool's parameters."""
        properties = {}
        required = []
        config_params = self.tool_config.get("parameters", [])

        if not isinstance(config_params, list):
            raise ValueError(
                f"Configuration error in tool '{self.tool_name}': "
                f"'parameters' must be a list, but found type '{type(config_params).__name__}'."
            )

        type_map = {
            "string": adk_types.Type.STRING,
            "integer": adk_types.Type.INTEGER,
            "number": adk_types.Type.NUMBER,
            "boolean": adk_types.Type.BOOLEAN,
        }

        for i, param in enumerate(config_params):
            if not isinstance(param, dict):
                raise ValueError(
                    f"Configuration error in tool '{self.tool_name}': "
                    f"Parameter at index {i} is not a valid dictionary. Found: '{param}'"
                )

            # Skip parameters that are sourced from context, they are not for the LLM
            if "context_expression" in param:
                continue

            param_name = param.get("name")
            if not param_name:
                raise ValueError(
                    f"Configuration error in tool '{self.tool_name}': "
                    f"Parameter at index {i} is missing the required 'name' key."
                )

            param_type_str = param.get("type", "string").lower()
            adk_type = type_map.get(param_type_str, adk_types.Type.STRING)

            properties[param_name] = adk_types.Schema(
                type=adk_type, description=param.get("description", "")
            )

            if param.get("required", False):
                required.append(param_name)

        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties=properties,
            required=required,
        )

    async def _run_async_impl(
        self, args: dict, tool_context: ToolContext, **kwargs
    ) -> dict:
        """Execute the broker request and wait for a response."""
        log_identifier = f"[EventMeshTool:{self.tool_name}:run]"

        host_component = getattr(
            tool_context._invocation_context.agent, "host_component", None
        )
        if not host_component:
            log.error(f"{log_identifier} Host component not found.")
            return {
                "status": "error",
                "message": "Host component not found, cannot access request/response functionality.",
            }

        if not self.session_id:
            log.error(
                f"{log_identifier} Session not initialized. Tool's init() method may have failed."
            )
            return {
                "status": "error",
                "message": "Event Mesh session is not initialized for this tool.",
            }

        try:
            config_params = self.tool_config.get("parameters", [])
            topic_template = self.tool_config.get("topic", "")
            wait_for_response = self.tool_config.get("wait_for_response", True)

            parameters_map = {param["name"]: param for param in config_params}

            # Build payload and resolve all parameters (including defaults) in one place
            payload, resolved_params = _build_payload_and_resolve_params(
                parameters_map, args, tool_context
            )
            topic = _fill_topic_template(topic_template, resolved_params)

            if not topic:
                log.error(
                    f"{log_identifier} Topic is empty after template resolution. Check 'topic' configuration."
                )
                return {
                    "status": "error",
                    "message": "Configuration error: Resulting topic is empty. Please define a 'topic' in the tool's configuration.",
                }

            message = Message(payload=payload, topic=topic)

            response = await host_component.do_broker_request_response_async(
                message,
                session_id=self.session_id,
                wait_for_response=wait_for_response,
            )

            if not wait_for_response:
                return {"status": "success", "message": "Request sent asynchronously."}

            if response is None:
                log.warning(
                    "%s Received None response without timeout.", log_identifier
                )
                return {
                    "status": "error",
                    "message": "Request failed. No response received.",
                }

            return {
                "status": "success",
                "message": "Request processed successfully.",
                "payload": response.get_payload(),
            }

        except Exception as e:
            log.error(
                f"{log_identifier} Error during tool execution: {e}", exc_info=True
            )
            return {
                "status": "error",
                "message": f"An unexpected error occurred: {str(e)}",
            }
