import logging
import uuid
import json
import base64
from typing import Dict, Any, List, TYPE_CHECKING

from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo
from ...common_a2a.types import (
    TaskSendParams,
    Message as A2AMessage,
    TextPart,
    FilePart,
    FileContent,
    Task,
    TaskState,
)
from .actions.a2a_client_action import (
    A2A_TASK_STATE_COMPLETED,
    A2A_TASK_STATE_FAILED,
    A2A_TASK_STATE_INPUT_REQUIRED,
)

# Use TYPE_CHECKING to avoid circular import issues at runtime
if TYPE_CHECKING:
    from .a2a_client_agent_component import A2AClientAgentComponent

logger = logging.getLogger(__name__)


def handle_provide_required_input(
    component: "A2AClientAgentComponent", params: Dict[str, Any], meta: Dict[str, Any]
) -> ActionResponse:
    """
    Handles the 'provide_required_input' action. Retrieves the original A2A task ID,
    sends the user's response to the A2A agent, and processes the subsequent result.
    """
    logger.info(f"Handling 'provide_required_input' with params: {params}")

    follow_up_id = params.get("follow_up_id")
    user_response_text = params.get("user_response")
    file_urls = params.get("files", [])

    # 1. Validate Input
    if not follow_up_id or not user_response_text:
        return ActionResponse(
            message="Missing required parameters: 'follow_up_id' and 'user_response'.",
            error_info=ErrorInfo("Missing Parameters"),
        )

    # 2. Check Services
    cache_service = component.cache_service
    a2a_client = component.a2a_client
    file_service = component.file_service

    if not cache_service:
        logger.error(
            "CacheService not available. Cannot handle 'provide_required_input'."
        )
        return ActionResponse(
            message="Internal Error: Cache Service not available.",
            error_info=ErrorInfo("Cache Service Missing"),
        )
    if not a2a_client:
        logger.error("A2AClient not available. Cannot handle 'provide_required_input'.")
        return ActionResponse(
            message="Internal Error: A2A Client not available.",
            error_info=ErrorInfo("A2A Client Missing"),
        )
    if not file_service:
        logger.error(
            "FileService not available. Cannot handle 'provide_required_input' with files."
        )
        return ActionResponse(
            message="Internal Error: File Service not available.",
            error_info=ErrorInfo("File Service Missing"),
        )

    # 3. Retrieve Original Task ID
    cache_key = f"a2a_follow_up:{follow_up_id}"
    try:
        a2a_taskId = cache_service.get(cache_key)
        if a2a_taskId is None:
            logger.warning(
                f"Follow-up ID '{follow_up_id}' not found in cache or expired."
            )
            return ActionResponse(
                message="Invalid or expired follow-up ID. Please start the task again.",
                error_info=ErrorInfo("Invalid Follow-up ID"),
            )
        cache_service.delete(cache_key)
        logger.info(
            f"Retrieved original A2A task ID '{a2a_taskId}' for follow-up ID '{follow_up_id}'."
        )
    except Exception as e:
        logger.error(
            f"Error retrieving task ID from cache for follow-up ID '{follow_up_id}': {e}",
            exc_info=True,
        )
        return ActionResponse(
            message="Internal Error: Failed to retrieve follow-up state.",
            error_info=ErrorInfo(f"Cache Error: {e}"),
        )

    # 4. Map Input to A2A Message Parts
    session_id = meta.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        logger.warning(
            f"No session_id in meta for follow-up. Generated new one: {session_id}"
        )

    parts: List[Any] = []
    try:
        parts.append(TextPart(text=str(user_response_text)))
    except Exception as e:
        logger.error(
            f"Failed to create TextPart for follow-up response: {e}", exc_info=True
        )
        return ActionResponse(
            message="Internal Error: Could not process user response text.",
            error_info=ErrorInfo(f"TextPart Error: {e}"),
        )

    if isinstance(file_urls, str):
        file_urls = [file_urls]
    if file_urls and isinstance(file_urls, list):
        logger.info(f"Processing {len(file_urls)} file URLs for follow-up.")
        for file_url in file_urls:
            if not isinstance(file_url, str):
                continue
            try:
                resolved_file = file_service.resolve_url(
                    file_url, session_id=session_id
                )
                if (
                    resolved_file
                    and hasattr(resolved_file, "bytes")
                    and hasattr(resolved_file, "name")
                    and hasattr(resolved_file, "mime_type")
                ):
                    encoded_bytes = base64.b64encode(resolved_file.bytes).decode(
                        "utf-8"
                    )
                    file_content = FileContent(
                        bytes=encoded_bytes,
                        name=resolved_file.name,
                        mimeType=resolved_file.mime_type,
                    )
                    parts.append(FilePart(file=file_content))
                else:
                    logger.error(
                        f"Failed to resolve file URL '{file_url}' for follow-up."
                    )
            except Exception as e:
                logger.error(
                    f"Error resolving file URL '{file_url}' for follow-up: {e}",
                    exc_info=True,
                )

    # 5. Create TaskSendParams (using retrieved a2a_taskId)
    try:
        a2a_message = A2AMessage(role="user", parts=parts)
        accepted_modes = [
            "text",
            "text/plain",
            "image/*",
            "application/json",
            "application/*",
        ]
        task_params = TaskSendParams(
            id=a2a_taskId,
            sessionId=session_id,
            message=a2a_message,
            acceptedOutputModes=accepted_modes,
        )
        logger.debug(
            f"Constructed follow-up TaskSendParams for task '{a2a_taskId}': {task_params.model_dump_json(exclude_none=True)}"
        )
    except Exception as e:
        logger.error(
            f"Failed to construct follow-up TaskSendParams for task '{a2a_taskId}': {e}",
            exc_info=True,
        )
        return ActionResponse(
            message="Internal Error: Failed to prepare follow-up A2A request.",
            error_info=ErrorInfo(f"TaskSendParams Error: {e}"),
        )

    # 6. Call A2A Agent and Process Response
    try:
        logger.info(f"Sending follow-up input for A2A task '{a2a_taskId}'...")
        response_task: Task = a2a_client.send_task(task_params.model_dump())
        task_state = getattr(getattr(response_task, "status", None), "state", None)
        logger.info(
            f"Received follow-up response for task '{a2a_taskId}'. State: {task_state}"
        )

        # Find *any* A2AClientAction instance to call its _process_parts helper
        # This relies on the component having processed actions already.
        action_instance_for_processing = None
        for act in component.action_list.actions:
            # Import locally to avoid circular dependency at module level
            from .actions.a2a_client_action import A2AClientAction
            if isinstance(act, A2AClientAction):
                action_instance_for_processing = act
                break

        if not action_instance_for_processing:
            logger.error(
                "Cannot process A2A response: No A2AClientAction instance found on component."
            )
            return ActionResponse(
                message="Internal Error: Cannot process A2A response.",
                error_info=ErrorInfo("Processing Setup Error"),
            )

        # Process the response using the helper method from an action instance
        if task_state == A2A_TASK_STATE_COMPLETED:
            final_message = ""
            final_files = []
            final_data = {}
            status_message = getattr(response_task.status, "message", None)
            if status_message:
                msg_parts = getattr(status_message, "parts", [])
                msg_text, msg_files = action_instance_for_processing._process_parts(
                    msg_parts, session_id, final_data
                )
                if msg_text:
                    final_message += msg_text
                final_files.extend(msg_files)
            artifacts = getattr(response_task, "artifacts", [])
            if artifacts:
                for artifact in artifacts:
                    artifact_parts = getattr(artifact, "parts", [])
                    art_text, art_files = action_instance_for_processing._process_parts(
                        artifact_parts, session_id, final_data
                    )
                    if art_text:
                        if final_message:
                            final_message += "\n\n--- Artifact ---\n"
                        final_message += art_text
                    final_files.extend(art_files)

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
                files=final_files or None,
                # No data parameter
            )

        elif task_state == A2A_TASK_STATE_FAILED:
            error_message = "A2A Task Failed (after follow-up)"
            error_details = ""
            status_message = getattr(response_task.status, "message", None)
            if status_message:
                msg_parts = getattr(status_message, "parts", [])
                if msg_parts:
                    try:
                        first_part_text = getattr(msg_parts[0], "text", "")
                        if first_part_text:
                            error_details = first_part_text
                            error_message += f": {error_details}"
                    except Exception:
                        pass
            return ActionResponse(
                message=error_message,
                error_info=ErrorInfo(error_details or "A2A Task Failed"),
            )

        elif task_state == A2A_TASK_STATE_INPUT_REQUIRED:
            agent_question = "A2A Task requires further input (again)."
            status_message = getattr(response_task.status, "message", None)
            if status_message:
                msg_parts = getattr(status_message, "parts", [])
                if msg_parts:
                    try:
                        question_details = getattr(msg_parts[0], "text", "")
                        if question_details:
                            agent_question = question_details
                    except Exception:
                        pass

            new_sam_follow_up_id = str(uuid.uuid4())
            new_cache_key = f"a2a_follow_up:{new_sam_follow_up_id}"
            try:
                cache_service.set(
                    new_cache_key, a2a_taskId, ttl=component.input_required_ttl
                )
                logger.info(
                    f"Stored *nested* INPUT_REQUIRED state for task '{a2a_taskId}' with follow-up ID '{new_sam_follow_up_id}'."
                )
                response_msg = f"{agent_question}\n\nPlease provide the required input using follow-up ID: `{new_sam_follow_up_id}`"
                return ActionResponse(
                    message=response_msg,
                    # No data parameter
                )
            except Exception as e:
                logger.error(
                    f"Failed to store nested INPUT_REQUIRED state in cache for task '{a2a_taskId}': {e}",
                    exc_info=True,
                )
                return ActionResponse(
                    message="Internal Error: Failed to store required input state.",
                    error_info=ErrorInfo(f"Cache Error: {e}"),
                )
        else:
            logger.warning(
                f"A2A Task '{a2a_taskId}' returned unhandled state after follow-up: {task_state}."
            )
            return ActionResponse(
                message=f"A2A Task is currently in state: {task_state}",
                error_info=ErrorInfo(f"Unhandled A2A State: {task_state}"),
            )

    except Exception as e:
        logger.error(
            f"Failed to communicate with A2A agent during follow-up for task '{a2a_taskId}': {e}",
            exc_info=True,
        )
        return ActionResponse(
            message="Failed to communicate with A2A agent during follow-up",
            error_info=ErrorInfo(f"A2A Communication Error: {e}"),
        )
