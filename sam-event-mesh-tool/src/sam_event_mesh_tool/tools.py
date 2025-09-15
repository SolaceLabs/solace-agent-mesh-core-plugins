import re
import yaml
import json
from typing import Any, Dict, Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_ai_connector.common.log import log
from solace_ai_connector.common.message import Message
from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool
from solace_agent_mesh.agent.sac.component import SamAgentComponent
from solace_agent_mesh.agent.tools.tool_config_types import AnyToolConfig


def _build_payload(
    parameters_map: Dict[str, Any], params: Dict[str, Any]
) -> Dict[str, Any]:
    """Build the message payload using parameter values and their payload paths."""
    payload = {}
    for name, value in params.items():
        if name in parameters_map and "payload_path" in parameters_map[name]:
            path = parameters_map[name]["payload_path"]
            current = payload
            parts = path.split(".")
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
    return payload


def _fill_topic_template(template: str, params: Dict[str, Any]) -> str:
    """Fill a topic template with parameter values."""

    def replace_param(match):
        param_expr = match.group(1).strip()
        if "://" in param_expr:
            _, param = param_expr.split("//")
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

    async def init(
        self, component: "SamAgentComponent", tool_config_model: "AnyToolConfig"
    ):
        """Initializes the dedicated request-response session for this tool instance."""
        log_identifier = f"[EventMeshTool:{self.tool_name}:init]"
        log.info(f"{log_identifier} Initializing event mesh session.")
        event_mesh_config = self.tool_config.get("event_mesh_config", {})
        try:
            self.session_id = component.create_request_response_session(
                session_config=event_mesh_config
            )
            log.info(f"{log_identifier} Session created with ID: {self.session_id}")
        except Exception as e:
            log.error(
                f"{log_identifier} Failed to create request/response session: {e}",
                exc_info=True,
            )
            raise

    async def cleanup(
        self, component: "SamAgentComponent", tool_config_model: "AnyToolConfig"
    ):
        """Destroys the dedicated request-response session for this tool instance."""
        log_identifier = f"[EventMeshTool:{self.tool_name}:cleanup]"
        if self.session_id:
            log.info(f"{log_identifier} Destroying session ID: {self.session_id}")
            component.destroy_request_response_session(self.session_id)
            self.session_id = None
            log.info(f"{log_identifier} Session destroyed.")

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

        type_map = {
            "string": adk_types.Type.STRING,
            "integer": adk_types.Type.INTEGER,
            "number": adk_types.Type.NUMBER,
            "boolean": adk_types.Type.BOOLEAN,
        }

        for param in config_params:
            param_name = param.get("name")
            if not param_name:
                continue

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
            response_format = self.tool_config.get("response_format", "text")
            wait_for_response = self.tool_config.get("wait_for_response", True)

            parameters_map = {param["name"]: param for param in config_params}
            defaulted_params = {
                param["name"]: param.get("default")
                for param in config_params
                if "default" in param
            }
            defaulted_params.update(args)

            topic = _fill_topic_template(topic_template, defaulted_params)
            payload = _build_payload(parameters_map, defaulted_params)
            message = Message(payload=payload, topic=topic)

            response = await host_component.do_broker_request_response_async(
                message,
                session_id=self.session_id,
                wait_for_response=wait_for_response,
            )

            if not wait_for_response:
                return {"status": "success", "message": "Request sent asynchronously."}

            if response is None:
                log.warning(f"{log_identifier} Received None response without timeout.")
                return {
                    "status": "error",
                    "message": "Request failed. No response received.",
                }

            response_payload = response.get_payload()

            if response_format == "json":
                if isinstance(response_payload, (str, bytes)):
                    response_payload = json.loads(response_payload)
            elif response_format == "yaml":
                if isinstance(response_payload, (str, bytes)):
                    response_payload = yaml.safe_load(response_payload)
            elif response_format == "text":
                response_payload = str(response_payload)

            return {
                "status": "success",
                "message": "Request processed successfully.",
                "payload": response_payload,
            }

        except Exception as e:
            log.error(
                f"{log_identifier} Error during tool execution: {e}", exc_info=True
            )
            return {
                "status": "error",
                "message": f"An unexpected error occurred: {str(e)}",
            }
