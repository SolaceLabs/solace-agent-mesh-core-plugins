import json
import logging
from typing import Any, Dict, Optional, List
import uuid

from solace_agent_mesh.agent.utils.context_helpers import get_original_session_id
from google.adk.tools import ToolContext

from .bedrock_agent_runtime import BedrockAgentRuntime

import base64
import os
import asyncio
import inspect

log = logging.getLogger(__name__)

MAX_FILE_LENGTH = 10485760  # 10MB
MAX_NUM_FILES = 5
SUPPORTED_FILE_TYPES = [
    ".pdf",
    ".txt",
    ".doc",
    ".csv",
    ".xls",
    ".xlsx",
]  # Bedrock supported types


async def _process_files_for_bedrock(
    file_uris_or_names: List[str], tool_context: ToolContext, log_identifier_prefix: str
) -> Dict[str, Any]:
    """
    Loads artifacts from the provided list of URIs or filenames, validates them,
    and prepares them in the format expected by Bedrock Agent's sessionState.
    """
    log_fn = lambda msg, level="info", exc_info=False: getattr(log, level)(
        f"{log_identifier_prefix} [_process_files_for_bedrock] {msg}", exc_info=exc_info
    )

    if not file_uris_or_names:
        return {"status": "success", "bedrock_files_payload": []}

    if len(file_uris_or_names) > MAX_NUM_FILES:
        msg = f"Too many files. Maximum is {MAX_NUM_FILES}, got {len(file_uris_or_names)}."
        log_fn(msg, level="error")
        return {"status": "error", "message": msg}

    bedrock_files_payload = []
    total_size = 0

    inv_context = tool_context._invocation_context
    artifact_service = inv_context.artifact_service
    app_name = inv_context.app_name
    user_id = inv_context.user_id
    artifact_session_id = get_original_session_id(inv_context)

    for file_ref in file_uris_or_names:
        try:
            parts = file_ref.rsplit(":", 1)
            filename_base = parts[0]
            version_str = parts[1] if len(parts) > 1 and parts[1].isdigit() else None
            version_to_load = int(version_str) if version_str else None

            log_fn(
                f"Processing file reference: '{file_ref}'. Base: '{filename_base}', Version: {version_to_load or 'latest'}"
            )

            _, ext = os.path.splitext(filename_base)
            if ext.lower() not in SUPPORTED_FILE_TYPES:
                msg = f"Unsupported file type: '{filename_base}'. Supported types are: {SUPPORTED_FILE_TYPES}"
                log_fn(msg, level="error")
                return {"status": "error", "message": msg}

            load_artifact_method = getattr(artifact_service, "load_artifact")
            if inspect.iscoroutinefunction(load_artifact_method):
                artifact_part = await load_artifact_method(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=artifact_session_id,
                    filename=filename_base,
                    version=version_to_load,
                )
            else:
                artifact_part = await asyncio.to_thread(
                    load_artifact_method,
                    app_name=app_name,
                    user_id=user_id,
                    session_id=artifact_session_id,
                    filename=filename_base,
                    version=version_to_load,
                )

            if (
                not artifact_part
                or not artifact_part.inline_data
                or not artifact_part.inline_data.data
            ):
                msg = f"Could not load content for artifact: '{file_ref}'"
                log_fn(msg, level="error")
                return {"status": "error", "message": msg}

            file_bytes = artifact_part.inline_data.data
            file_mime_type = (
                artifact_part.inline_data.mime_type or "application/octet-stream"
            )

            actual_filename = filename_base
            try:
                metadata_filename = f"{filename_base}.metadata.json"

                load_metadata_method = getattr(artifact_service, "load_artifact")
                if inspect.iscoroutinefunction(load_metadata_method):
                    metadata_part = await load_metadata_method(
                        app_name=app_name,
                        user_id=user_id,
                        session_id=artifact_session_id,
                        filename=metadata_filename,
                        version=version_to_load,
                    )
                else:
                    metadata_part = await asyncio.to_thread(
                        load_metadata_method,
                        app_name=app_name,
                        user_id=user_id,
                        session_id=artifact_session_id,
                        filename=metadata_filename,
                        version=version_to_load,
                    )

                if (
                    metadata_part
                    and metadata_part.inline_data
                    and metadata_part.inline_data.data
                ):
                    metadata_content = json.loads(
                        metadata_part.inline_data.data.decode("utf-8")
                    )
                    actual_filename = metadata_content.get("filename", filename_base)
                    file_mime_type = metadata_content.get("mime_type", file_mime_type)
                    log_fn(
                        f"Loaded metadata for '{filename_base}', actual name: '{actual_filename}', MIME: '{file_mime_type}'"
                    )
            except Exception as meta_e:
                log_fn(
                    f"Could not load or parse metadata for '{filename_base}': {meta_e}. Using base filename and loaded MIME type.",
                    level="warning",
                )

            current_file_size = len(file_bytes)
            if current_file_size > MAX_FILE_LENGTH:
                msg = f"File '{actual_filename}' size ({current_file_size} bytes) exceeds individual limit of {MAX_FILE_LENGTH} bytes."
                log_fn(msg, level="error")
                return {"status": "error", "message": msg}

            total_size += current_file_size
            if total_size > MAX_FILE_LENGTH:
                msg = f"Total file size ({total_size} bytes) exceeds limit of {MAX_FILE_LENGTH} bytes."
                log_fn(msg, level="error")
                return {"status": "error", "message": msg}

            base64_encoded_data = base64.b64encode(file_bytes).decode("utf-8")

            bedrock_files_payload.append(
                {
                    "name": actual_filename,
                    "source": {
                        "byteContent": {
                            "data": base64_encoded_data,
                            "mediaType": file_mime_type,
                        },
                        "sourceType": "BYTE_CONTENT",
                    },
                    "useCase": "CHAT",
                }
            )
            log_fn(
                f"Successfully processed and added file: '{actual_filename}' ({current_file_size} bytes)"
            )

        except FileNotFoundError:
            msg = f"Artifact '{file_ref}' not found."
            log_fn(msg, level="error")
            return {"status": "error", "message": msg}
        except Exception as e:
            msg = f"Error processing file '{file_ref}': {str(e)}"
            log_fn(msg, level="error", exc_info=True)
            return {"status": "error", "message": msg}

    log_fn(
        f"All {len(bedrock_files_payload)} files processed successfully. Total size: {total_size} bytes."
    )
    return {"status": "success", "bedrock_files_payload": bedrock_files_payload}


async def invoke_bedrock_agent(
    input_text: str,
    files: Optional[List[str]] = None,
    tool_context: Optional[ToolContext] = None,
    tool_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Invokes an Amazon Bedrock Agent with the given input text and optional files.

    Args:
        input_text: The primary text input to send to the Bedrock Agent.
        files: Optional. A list of artifact filenames to be processed and sent to the agent.
        tool_context: The ADK ToolContext, providing access to services like logging and artifacts.
        tool_config: Configuration specific to this tool instance, including:
            - bedrock_agent_id (str): The ID of the Amazon Bedrock agent.
            - bedrock_agent_alias_id (str): The alias ID of the Amazon Bedrock agent.
            - allow_files (bool): Whether file processing is enabled for this agent.
    Returns:
        A dictionary containing the status of the invocation and the agent's response or an error message.
    """
    plugin_name = "sam-bedrock-agent"
    log_identifier = f"[{plugin_name}:invoke_bedrock_agent]"
    log.info("%s Received request. Input text: '%s...'", log_identifier, input_text[:100])

    if not tool_context or not tool_context._invocation_context:
        log.error("%s ToolContext or InvocationContext is missing.", log_identifier)
        return {
            "status": "error",
            "message": "ToolContext or InvocationContext is missing.",
        }

    if not tool_config:
        log.error("%s Tool configuration (tool_config) is missing.", log_identifier)
        return {"status": "error", "message": "Tool configuration is missing."}

    bedrock_agent_id = tool_config.get("bedrock_agent_id")
    bedrock_agent_alias_id = tool_config.get("bedrock_agent_alias_id")
    allow_files_config = tool_config.get("allow_files", False)
    amazon_bedrock_runtime_config = tool_config.get("amazon_bedrock_runtime_config")

    if not bedrock_agent_id or not bedrock_agent_alias_id:
        log.error(
            "%s Missing bedrock_agent_id or bedrock_agent_alias_id in tool_config.",
            log_identifier
        )
        return {
            "status": "error",
            "message": "Bedrock agent ID or alias ID is missing in configuration.",
        }

    if not amazon_bedrock_runtime_config:
        log.error(
            "%s Missing amazon_bedrock_runtime_config in agent configuration.", log_identifier
        )
        return {
            "status": "error",
            "message": "Amazon Bedrock runtime configuration is missing.",
        }

    boto3_config = amazon_bedrock_runtime_config.get("boto3_config")
    endpoint_url = amazon_bedrock_runtime_config.get("endpoint_url")

    if not boto3_config:
        log.error(
            "%s Missing boto3_config in amazon_bedrock_runtime_config.", log_identifier
        )
        return {
            "status": "error",
            "message": "Boto3 configuration is missing in Bedrock runtime configuration.",
        }

    try:
        bedrock_runtime = BedrockAgentRuntime(
            boto3_config=boto3_config, endpoint_url=endpoint_url
        )
        session_id = get_original_session_id(tool_context._invocation_context) or str(
            uuid.uuid4()
        )

        session_state_for_bedrock = {"files": []}
        if allow_files_config:
            if files and isinstance(files, list) and len(files) > 0:
                log.info(
                    "%s File processing enabled by config and files provided. Processing %d files.",
                    log_identifier,
                    len(files)
                )
                file_processing_result = await _process_files_for_bedrock(
                    files, tool_context, log_identifier
                )

                if file_processing_result.get("status") == "error":
                    log.error(
                        "%s Error processing files: %s",
                        log_identifier,
                        file_processing_result.get("message")
                    )
                    return file_processing_result

                processed_payload = file_processing_result.get("bedrock_files_payload")
                if processed_payload:
                    session_state_for_bedrock["files"] = processed_payload
                    log.info(
                        "%s Files processed successfully for Bedrock session state.",
                        log_identifier
                    )
                else:
                    log.info(
                        "%s No files were processed or payload was empty, session_state will be None.",
                        log_identifier
                    )
            elif files:
                log.warning(
                    "%s 'files' parameter provided but is not a valid list or is empty. Ignoring files. Value: %s",
                    log_identifier,
                    files
                )
            else:
                log.info(
                    "%s File processing enabled, but no files provided by user.",
                    log_identifier
                )
        elif files:
            log.warning(
                "%s Files provided by user, but 'allow_files' is false in tool_config. Ignoring files.",
                log_identifier
            )

        log.debug(
            "%s Invoking Bedrock agent %s (alias %s) for session %s. Session state: %s",
            log_identifier,
            bedrock_agent_id,
            bedrock_agent_alias_id,
            session_id,
            'Set' if session_state_for_bedrock else 'Not set'
        )
        response_text = bedrock_runtime.invoke_agent(
            agent_id=bedrock_agent_id,
            agent_alias_id=bedrock_agent_alias_id,
            session_id=session_id,
            prompt=input_text,
            session_state=session_state_for_bedrock,
        )
        log.info(
            "%s Successfully invoked Bedrock agent. Response length: %d",
            log_identifier,
            len(response_text)
        )
        return {
            "status": "success",
            "message": "Bedrock agent invoked successfully.",
            "response": response_text,
            "session_id": session_id,
        }

    except RuntimeError as r_err:
        log.exception(
            "%s Runtime error during Bedrock agent invocation: %s",
            log_identifier,
            r_err,
        )
        return {"status": "error", "message": f"Runtime error: {r_err}"}
    except Exception as e:
        log.exception(
            "%s Error invoking Bedrock agent: %s",
            log_identifier,
            e,
        )
        return {
            "status": "error",
            "message": f"Failed to invoke Bedrock agent: {str(e)}",
        }
