"""
Dynamically created SAM Action to represent and invoke a specific A2A skill.
"""

import logging
import uuid
import json  # Import json for formatting data
from typing import Dict, Any, List, TYPE_CHECKING

from solace_agent_mesh.common.action import Action
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo

from ....common_a2a.types import (
    AgentSkill,
    TaskSendParams,
    Message as A2AMessage,
    TextPart,
    FilePart,
    FileContent,
    Task,
    TaskState,
)

# Define string constants based on imported enum for robustness in comparisons
A2A_TASK_STATE_COMPLETED = TaskState.COMPLETED
A2A_TASK_STATE_FAILED = TaskState.FAILED
A2A_TASK_STATE_INPUT_REQUIRED = TaskState.INPUT_REQUIRED
A2A_PART_TYPE_TEXT = "text"
A2A_PART_TYPE_FILE = "file"
A2A_PART_TYPE_DATA = "data"


# Use TYPE_CHECKING to avoid circular import issues at runtime
if TYPE_CHECKING:
    from ..a2a_client_agent_component import A2AClientAgentComponent

logger = logging.getLogger(__name__)


class A2AClientAction(Action):
    """
    A SAM Action that wraps a specific skill discovered from an A2A agent.
    It handles invoking the skill via the A2A protocol.
    """

    def __init__(
        self,
        skill: AgentSkill,
        component: "A2AClientAgentComponent",
        inferred_params: List[Dict[str, Any]],
    ):
        """
        Initializes the A2AClientAction.

        Args:
            skill: The A2A AgentSkill this action represents.
            component: The parent A2AClientAgentComponent instance.
            inferred_params: The list of parameters inferred for this action.
        """
        self.skill = skill
        self.component = component

        action_definition = {
            "name": skill.id,
            "prompt_directive": skill.description
            or f"Execute the {skill.name or skill.id} skill.",
            "params": inferred_params,
            # Define required scopes based on agent name and skill id
            "required_scopes": [f"{component.agent_name}:{skill.id}:execute"],
        }

        super().__init__(
            action_definition, agent=component, config_fn=component.get_config
        )
        logger.debug(f"Initialized A2AClientAction for skill '{self.skill.id}'")

    def _process_parts(
        self, parts: List[Any], session_id: str, response_data: Dict
    ) -> tuple[str, List[Dict]]:
        """
        Helper method to process a list of A2A parts (from message or artifact).

        Args:
            parts: List of A2A Part objects (TextPart, FilePart, DataPart).
            session_id: The current session ID for file uploads.
            response_data: Dictionary to accumulate data from DataParts.

        Returns:
            A tuple containing:
            - response_message (str): Concatenated text from TextParts.
            - response_files (List[Dict]): List of file metadata dicts from FileParts.
        """
        response_message = ""
        response_files = []
        file_service = self.component.file_service

        if not parts:
            return response_message, response_files

        for part in parts:
            part_type = getattr(part, "type", None)  # Get type safely

            # Use string literals or constants for comparison
            if part_type == A2A_PART_TYPE_TEXT:
                try:
                    text_content = getattr(part, "text", "")
                    if text_content:
                        if response_message:
                            response_message += "\n"  # Add newline between text parts
                        response_message += text_content
                except Exception as e:
                    logger.warning(
                        f"Could not extract text from TextPart: {e}", exc_info=True
                    )

            elif part_type == A2A_PART_TYPE_FILE:
                try:
                    file_content = getattr(part, "file", None)
                    if (
                        file_content
                        and hasattr(file_content, "bytes")
                        and hasattr(file_content, "name")
                    ):
                        # Decode base64 bytes if necessary (A2A spec might send base64 string)
                        file_bytes_maybe_b64 = getattr(file_content, "bytes", "")
                        file_bytes = b""
                        if isinstance(file_bytes_maybe_b64, str):
                            try:
                                import base64

                                file_bytes = base64.b64decode(file_bytes_maybe_b64)
                            except Exception as b64_e:
                                logger.error(
                                    f"Failed to decode base64 FilePart content: {b64_e}"
                                )
                                continue  # Skip this file part
                        elif isinstance(file_bytes_maybe_b64, bytes):
                            file_bytes = file_bytes_maybe_b64
                        else:
                            logger.warning(
                                f"Skipping FilePart with unexpected bytes type: {type(file_bytes_maybe_b64)}"
                            )
                            continue

                        file_name = getattr(file_content, "name", "unknown_file")
                        mime_type = getattr(
                            file_content, "mimeType", "application/octet-stream"
                        )  # Default mime type

                        if file_bytes and file_name:
                            logger.debug(
                                f"Uploading FilePart '{file_name}' using FileService..."
                            )
                            try:
                                # Assuming upload_from_buffer returns a dict like {'url': ..., 'name': ...}
                                file_meta = file_service.upload_from_buffer(
                                    content=file_bytes,  # Pass raw bytes
                                    file_name=file_name,
                                    session_id=session_id,
                                    mime_type=mime_type,
                                    data_source=f"{self.component.agent_name}/{self.name}",  # Add data source info
                                )
                                if file_meta:
                                    response_files.append(file_meta)
                                    logger.debug(
                                        f"FilePart '{file_name}' uploaded successfully: {file_meta.get('url')}"
                                    )
                                else:
                                    logger.error(
                                        f"FileService.upload_from_buffer returned None for '{file_name}'."
                                    )
                            except Exception as upload_e:
                                logger.error(
                                    f"Failed to upload FilePart '{file_name}': {upload_e}",
                                    exc_info=True,
                                )
                        else:
                            logger.warning(
                                f"Skipping FilePart with missing bytes or name: {file_name}"
                            )
                    else:
                        logger.warning("Skipping invalid FilePart object.")
                except Exception as e:
                    logger.warning(f"Could not process FilePart: {e}", exc_info=True)

            elif part_type == A2A_PART_TYPE_DATA:
                try:
                    data_content = getattr(part, "data", None)
                    if isinstance(data_content, dict):
                        # Merge data - simple update, last one wins on conflict
                        response_data.update(data_content)
                        logger.debug(f"Merged DataPart content: {data_content}")
                    elif data_content is not None:
                        logger.warning(
                            f"Skipping DataPart with non-dictionary content: {type(data_content)}"
                        )
                except Exception as e:
                    logger.warning(f"Could not process DataPart: {e}", exc_info=True)

            else:
                logger.warning(
                    f"Encountered unknown or missing A2A Part type: '{part_type}'. Skipping."
                )

        return response_message, response_files

    def invoke(self, params: Dict[str, Any], meta: Dict[str, Any]) -> ActionResponse:
        """
        Invokes the A2A skill by mapping SAM parameters to an A2A Task request,
        sending the request, and handling the response states including COMPLETED,
        FAILED, and INPUT_REQUIRED mapping.
        """
        logger.info(f"Invoking action '{self.name}' with params: {params}")

        # 1. Get necessary services and IDs
        a2a_client = self.component.a2a_client
        cache_service = self.component.cache_service
        file_service = self.component.file_service

        if not a2a_client:
            logger.error(
                f"A2AClient not initialized for component '{self.component.agent_name}'. Cannot invoke action '{self.name}'."
            )
            return ActionResponse(
                message="Internal Error: A2A Client not available.",
                error_info=ErrorInfo("A2A Client Missing"),
            )
        if not file_service:
            logger.error(
                f"FileService not available for component '{self.component.agent_name}'. Cannot handle file parameters for action '{self.name}'."
            )
            return ActionResponse(
                message="Internal Error: File Service not available.",
                error_info=ErrorInfo("File Service Missing"),
            )

        session_id = meta.get("session_id")
        if not session_id:
            session_id = str(uuid.uuid4())
            logger.warning(
                f"No session_id found in meta for action '{self.name}'. Generated new one: {session_id}"
            )

        a2a_taskId = str(uuid.uuid4())

        # 2. Map SAM params to A2A Message.parts
        parts: List[Any] = []
        prompt_text = params.get("prompt")

        if prompt_text is None:
            logger.error(
                f"Missing required 'prompt' parameter for action '{self.name}'."
            )
            return ActionResponse(
                message="Missing required 'prompt' parameter.",
                error_info=ErrorInfo("Missing Parameter"),
            )

        try:
            parts.append(TextPart(text=str(prompt_text)))
        except Exception as e:
            logger.error(
                f"Failed to create TextPart for action '{self.name}': {e}",
                exc_info=True,
            )
            return ActionResponse(
                message="Internal Error: Could not process prompt text.",
                error_info=ErrorInfo(f"TextPart Error: {e}"),
            )

        file_urls = params.get("files", [])
        if isinstance(file_urls, str):
            file_urls = [file_urls]

        if file_urls and isinstance(file_urls, list):
            logger.info(
                f"Processing {len(file_urls)} file URLs for action '{self.name}'."
            )
            for file_url in file_urls:
                if not isinstance(file_url, str):
                    logger.warning(
                        f"Skipping non-string item in 'files' list: {file_url}"
                    )
                    continue
                try:
                    logger.debug(f"Resolving file URL: {file_url}")
                    resolved_file = file_service.resolve_url(
                        file_url, session_id=session_id
                    )
                    if (
                        resolved_file
                        and hasattr(resolved_file, "bytes")
                        and hasattr(resolved_file, "name")
                        and hasattr(resolved_file, "mime_type")
                    ):
                        # A2A FileContent expects base64 encoded string for bytes
                        import base64

                        encoded_bytes = base64.b64encode(resolved_file.bytes).decode(
                            "utf-8"
                        )
                        file_content = FileContent(
                            bytes=encoded_bytes,
                            name=resolved_file.name,
                            mimeType=resolved_file.mime_type,
                        )
                        parts.append(FilePart(file=file_content))
                        logger.debug(
                            f"Successfully added FilePart for {resolved_file.name}"
                        )
                    else:
                        logger.error(
                            f"Failed to resolve file URL '{file_url}' or resolved object is invalid."
                        )
                except Exception as e:
                    logger.error(
                        f"Error resolving file URL '{file_url}' for action '{self.name}': {e}",
                        exc_info=True,
                    )

        # 3. Create TaskSendParams
        try:
            a2a_message = A2AMessage(role="user", parts=parts)
            accepted_modes = [
                "text",
                "text/plain",
                "image/*",
                "application/json",
                "application/*",
            ]  # Added application/*
            task_params = TaskSendParams(
                id=a2a_taskId,
                sessionId=session_id,
                message=a2a_message,
                acceptedOutputModes=accepted_modes,
            )
            logger.debug(
                f"Constructed TaskSendParams for action '{self.name}': {task_params.model_dump_json(exclude_none=True)}"
            )
        except Exception as e:
            logger.error(
                f"Failed to construct TaskSendParams for action '{self.name}': {e}",
                exc_info=True,
            )
            return ActionResponse(
                message="Internal Error: Failed to prepare A2A request.",
                error_info=ErrorInfo(f"TaskSendParams Error: {e}"),
            )

        # 4. Call A2A Agent and Handle Response
        try:
            logger.info(
                f"Sending task '{a2a_taskId}' to A2A agent for action '{self.name}'..."
            )
            response_task: Task = self.component.a2a_client.send_task(
                task_params.model_dump()
            )
            task_state = getattr(
                getattr(response_task, "status", None), "state", None
            )  # Safely get state
            logger.info(
                f"Received response for task '{a2a_taskId}'. State: {task_state}"
            )

            # --- State Handling ---
            if task_state == A2A_TASK_STATE_COMPLETED:
                logger.info(f"Task '{a2a_taskId}' completed successfully.")
                final_message = ""
                final_files = []
                final_data = {}

                # Process status message parts
                status_message = getattr(response_task.status, "message", None)
                if status_message:
                    msg_parts = getattr(status_message, "parts", [])
                    msg_text, msg_files = self._process_parts(
                        msg_parts, session_id, final_data
                    )
                    if msg_text:
                        final_message += msg_text
                    final_files.extend(msg_files)

                # Process artifact parts
                artifacts = getattr(response_task, "artifacts", [])
                if artifacts:
                    for artifact in artifacts:
                        artifact_parts = getattr(artifact, "parts", [])
                        art_text, art_files = self._process_parts(
                            artifact_parts, session_id, final_data
                        )
                        if art_text:
                            if final_message:
                                final_message += "\n\n--- Artifact ---\n"  # Separator for artifact text
                            final_message += art_text
                        final_files.extend(art_files)

                # Append final_data to message if it exists
                response_msg = final_message.strip() or "Task completed."
                if final_data:
                    try:
                        data_str = json.dumps(final_data, indent=2)
                        response_msg += f"\n\nData:\n{data_str}"
                    except Exception as json_e:
                        logger.warning(f"Could not serialize final_data to JSON: {json_e}")
                        response_msg += "\n\nData: [Could not serialize]"


                return ActionResponse(
                    message=response_msg,
                    files=final_files or None,  # Return None if list is empty
                    # No data parameter
                )

            elif task_state == A2A_TASK_STATE_FAILED:
                logger.error(f"A2A Task '{a2a_taskId}' failed.")
                error_message = "A2A Task Failed"
                error_details = ""
                status_message = getattr(response_task.status, "message", None)
                if status_message:
                    msg_parts = getattr(status_message, "parts", [])
                    if msg_parts:
                        try:
                            # Attempt to extract text from the first part
                            first_part_text = getattr(msg_parts[0], "text", "")
                            if first_part_text:
                                error_details = first_part_text
                                error_message += f": {error_details}"
                        except Exception as e:
                            logger.warning(
                                f"Could not extract error details from FAILED task message parts: {e}"
                            )
                return ActionResponse(
                    message=error_message,
                    error_info=ErrorInfo(
                        error_details or "A2A Task Failed"
                    ),  # Use details if available
                )

            elif task_state == A2A_TASK_STATE_INPUT_REQUIRED:
                logger.warning(f"A2A Task '{a2a_taskId}' requires input.")
                # Check for cache service *before* generating UUID
                if not cache_service:
                    logger.error(
                        f"CacheService not available. Cannot handle INPUT_REQUIRED state for task '{a2a_taskId}'."
                    )
                    return ActionResponse(
                        message="Internal Error: Cannot handle required input state without CacheService.",
                        error_info=ErrorInfo("Cache Service Missing"),
                    )

                agent_question = "A2A Task requires further input."
                status_message = getattr(response_task.status, "message", None)
                if status_message:
                    msg_parts = getattr(status_message, "parts", [])
                    if msg_parts:
                        try:
                            # Assuming the first part is text containing the question
                            question_details = getattr(msg_parts[0], "text", "")
                            if question_details:
                                agent_question = question_details
                        except Exception as e:
                            logger.warning(
                                f"Could not extract question details from INPUT_REQUIRED task message parts: {e}"
                            )

                sam_follow_up_id = str(uuid.uuid4())
                a2a_original_taskId = getattr(
                    response_task, "id", a2a_taskId
                )  # Use original ID if available
                cache_key = f"a2a_follow_up:{sam_follow_up_id}"
                try:
                    cache_service.set(
                        cache_key,
                        a2a_original_taskId,
                        ttl=self.component.input_required_ttl,
                    )
                    logger.info(
                        f"Stored INPUT_REQUIRED state for task '{a2a_original_taskId}' with follow-up ID '{sam_follow_up_id}'."
                    )
                    # Return response indicating input is needed, include follow-up ID in message
                    response_msg = f"{agent_question}\n\nPlease provide the required input using follow-up ID: `{sam_follow_up_id}`"
                    return ActionResponse(
                        message=response_msg,
                        # No data parameter
                        # Consider adding a specific status field if ActionResponse supports it
                        # status='INPUT_REQUIRED' # Example if status field exists
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to store INPUT_REQUIRED state in cache for task '{a2a_original_taskId}': {e}",
                        exc_info=True,
                    )
                    return ActionResponse(
                        message="Internal Error: Failed to store required input state.",
                        error_info=ErrorInfo(f"Cache Error: {e}"),
                    )

            else:
                # Handle other potential states like 'working', 'submitted', 'canceled' gracefully
                logger.warning(
                    f"A2A Task '{a2a_taskId}' returned unhandled state: {task_state}. Treating as pending/error."
                )
                # Decide how to represent this. Maybe a generic message indicating the state?
                return ActionResponse(
                    message=f"A2A Task is currently in state: {task_state}",
                    error_info=ErrorInfo(
                        f"Unhandled A2A State: {task_state}"
                    ),  # Indicate it's not a final success
                )

        except Exception as e:
            logger.error(
                f"Failed to communicate with A2A agent for action '{self.name}': {e}",
                exc_info=True,
            )
            return ActionResponse(
                message="Failed to communicate with A2A agent",
                error_info=ErrorInfo(f"A2A Communication Error: {e}"),
            )
