import logging
import re
import yaml
import json
import uuid
from typing import Any, Dict, Optional
from google.adk.tools import ToolContext
from solace_ai_connector.common.message import Message

log = logging.getLogger(__name__)

def _validate_topic_template(topic: str, params) -> str:
    """Validate that a topic template is properly formatted.

    Valid formats include:
    - Plain text: my/topic/path
    - With parameter: my/topic/{{ param1 }}/path
    - With encoding: my/topic/{{ text://param1 }}/path

    Args:
        topic: The topic template string to validate.

    Returns:
        string: If the topic template is invalid.
    """
    # Match {{ optional_encoding://param_name }}
    template_pattern = r"\{\{(\s*(text://)?\s*[a-zA-Z_][a-zA-Z0-9_]*\s*)\}\}"

    for match in re.finditer(template_pattern, topic):
        param_expr = match.group(1).strip()
        if "://" in param_expr:
            encoding, param = param_expr.split("://")
            if encoding.strip() != "text":
                return f"Invalid encoding '{encoding}' in topic template '{topic}'. Only 'text' encoding is supported."
            param = param.strip()
        else:
            param = param_expr

        # Verify parameter exists in config
        if not any(p["name"] == param for p in params):
            return f"Topic template '{topic}' references undefined parameter '{param}'"

def _build_payload(
    parameters_map: Dict[str, Any], params: Dict[str, Any]
) -> Dict[str, Any]:
    """Build the message payload using parameter values and their payload paths.

    Supports both dot notation and bracket notation for array indices:
    - field1.0.field2
    - field1[0].field2

    Args:
        params: Dictionary of parameter values.

    Returns:
        Dict containing the structured payload.

    Raises:
        ValueError: If a negative array index is encountered.
    """
    payload = {}

    for name, value in params.items():
        if name in parameters_map and "payload_path" in parameters_map[name]:
            path = parameters_map[name]["payload_path"]
            current = payload

            # Split on dots but preserve array brackets
            parts = []
            current_part = ""
            for char in path:
                if char == "." and not (
                    current_part.startswith("[") and "]" not in current_part
                ):
                    if current_part:
                        parts.append(current_part)
                        current_part = ""
                else:
                    current_part += char
            if current_part:
                parts.append(current_part)

            # Navigate to the correct nested location
            for part in parts[:-1]:
                next_key = None
                # Handle array indices
                if part.startswith("[") and part.endswith("]"):
                    # Bracket notation
                    index = int(part[1:-1])
                    if index < 0:
                        raise ValueError(f"Negative array index {index} not allowed")
                    if not isinstance(current, list):
                        current = []
                    while len(current) <= index:
                        current.append({})
                    next_key = index
                elif part.isdigit():
                    # Dot notation for array index
                    index = int(part)
                    if index < 0:
                        raise ValueError(f"Negative array index {index} not allowed")
                    if not isinstance(current, list):
                        current = []
                    while len(current) <= index:
                        current.append({})
                    next_key = index
                else:
                    # Regular dict key
                    if part not in current:
                        current[part] = {}
                    next_key = part

                current = current[next_key]

            # Handle the final part
            last_part = parts[-1]
            if last_part.startswith("[") and last_part.endswith("]"):
                index = int(last_part[1:-1])
                if index < 0:
                    raise ValueError(f"Negative array index {index} not allowed")
                if not isinstance(current, list):
                    current = []
                while len(current) <= index:
                    current.append(None)
                current[index] = value
            elif last_part.isdigit():
                index = int(last_part)
                if index < 0:
                    raise ValueError(f"Negative array index {index} not allowed")
                if not isinstance(current, list):
                    current = []
                while len(current) <= index:
                    current.append(None)
                current[index] = value
            else:
                current[last_part] = value

    return payload


def _fill_topic_template(template: str, params: Dict[str, Any]) -> str:
    """Fill a topic template with parameter values.

    Args:
        template: The topic template string.
        params: Dictionary of parameter values.

    Returns:
        The filled topic string.

    Raises:
        ValueError: If parameter substitution fails.
    """

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


async def broker_request_response(
    params: Optional[Dict[str, Any]]=None,
    tool_context: Optional[ToolContext] = None,
    tool_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a broker request and wait for a response.

    Args:
        params: Dictionary of parameters to fill the topic and payload.
    """
    plugin_name = "sam_event_mesh_agent"
    log_identifier = f"[{plugin_name}:broker_request_response]"

    if params is None:
        params = {}
    config_params = tool_config.get("parameters") or []
    topic_template = tool_config.get("topic", "")
    response_timeout = tool_config.get("response_timeout", 15)
    response_format = tool_config.get("response_format", "text")

    if response_format not in ["json", "yaml", "text", "none"]:
        log.error(
            "%s Invalid response_format '%s'. "
            "Must be one of: json, yaml, text, none",
            log_identifier,
            response_format
        )
        return {
            "status": "error",
            "message": f"Invalid response_format '{response_format}'. Must be one of: json, yaml, text, none",
        }

    validation_error = _validate_topic_template(topic_template, config_params)
    if validation_error:
        log.error("%s Topic validation failed: %s", log_identifier, validation_error)
        return {
            "status": "error",
            "message": f"Invalid topic template: {validation_error}",
        }

    if not isinstance(params, dict):
        log.error("%s Invalid params type: %s. Expected dict.", log_identifier, type(params))
        return {
            "status": "error",
            "message": f"Invalid params type: {type(params)}. Expected dict.",
        }

    parameters_map = {param["name"]: param for param in config_params}
    defaulted_params = {
        **{
            param["name"]: param.get("default", None)
            for param in config_params
        },
        **params,
    }
    
    try:
        # Fill topic templates
        try:
            topic = _fill_topic_template(topic_template, defaulted_params)
        except ValueError as e:
            log.error("%s Error filling topic template: %s", log_identifier, str(e))
            return {
                "status": "error",
                "message": f"Error filling topic template: {str(e)}",
            }

        payload = _build_payload(parameters_map, defaulted_params)

        message = Message(
            payload=payload,
            topic=topic,
        )

        host_component = getattr(
            tool_context._invocation_context.agent, "host_component", None
        )
        if not host_component:
            log.error("%s Host component not found", log_identifier)
            return {
                "status": "error",
                "error_message": "Host component not found, cannot access request response functionality.",
            }

        if not host_component.is_broker_request_response_enabled():
            log.error(
                "%s Broker request/response is not enabled for this agent", log_identifier
            )
            return {
                "status": "error",
                "message": "Broker request/response is not enabled for this agent",
            }

        # Check if this should be an async request
        is_async = defaulted_params.get("async", False)
        if is_async:
            # Generate a unique ID for this async request
            async_response_id = str(uuid.uuid4())

            # Store request context in cache
            cache_key = f"event_mesh_agent:async_request:{async_response_id}"
            cache_data = {"params": defaulted_params, "response_format": response_format}
            host_component.cache_service.add_data(
                key=cache_key,
                value=cache_data,
                expiry=response_timeout,
                component=host_component,
            )

            # Send async request
            host_component.do_broker_request_response(
                message=message,
                stream=True,
                streaming_complete_expression=None,
            )

            return {
                "status": "success",
                "message": "Request sent for async processing",
                "is_async": True,
                "async_response_id": async_response_id,
            }
        else:
            # Synchronous request
            response = host_component.do_broker_request_response(
                message=message, stream=False, streaming_complete_expression=None
            )

            if response is None:
                return {
                    "status": "error",
                    "message": f"Request timed out after {response_timeout} seconds",
                }

        payload = response.get_payload()

        try:
            if response_format == "json":
                # Attempt JSON parsing even if format not specified
                if isinstance(payload, str):
                    payload = json.loads(payload)
            elif response_format == "yaml":
                if isinstance(payload, str):
                    payload = yaml.safe_load(payload)
            elif response_format == "text":
                payload = str(payload)
            # For "none", return payload as-is

            return {
                "status": "success",
                "message": "Request processed successfully",
                "payload": payload,
            }

        except Exception as e:
            error_msg = f"Error parsing response payload as {response_format}: {str(e)}"
            log.error("%s\nPayload: %s", error_msg, payload)
            return {
                "status": "error",
                "message": error_msg,
                "payload": payload,
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error executing broker request: {str(e)}",
        }
