"""
Handler function for the 'provide_required_input' static SAM action.
This function orchestrates the process of sending follow-up input to an A2A agent
when it previously returned an INPUT_REQUIRED state.
"""

import uuid
import json
import base64
import asyncio  # Import asyncio
from typing import Dict, Any, List, TYPE_CHECKING, Optional

from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo
from solace_ai_connector.common.log import log  # Use solace-ai-connector log

# Import A2A types directly. If these fail, the module load will fail.
from ...common_a2a.types import (
    TaskSendParams,
    Message as A2AMessage,
    TextPart,
    FilePart,
    FileContent,
    Task,
    TaskState,  # Import TaskState directly
    SendTaskResponse,  # Import SendTaskResponse
)

# Use constants defined in a2a_client_action for consistency
from .actions.a2a_client_action import (
    A2A_TASK_STATE_COMPLETED,
    A2A_TASK_STATE_FAILED,
    A2A_TASK_STATE_INPUT_REQUIRED,
)

# Use TYPE_CHECKING to avoid circular import issues at runtime
if TYPE_CHECKING:
    from .a2a_client_agent_component import A2AClientAgentComponent


def handle_provide_required_input(
    component: "A2AClientAgentComponent", params: Dict[str, Any], meta: Dict[str, Any]
) -> ActionResponse:
    """
    Handles the 'provide_required_input' SAM action.

    1.  Validates input parameters (`follow_up_id`, `user_response`).
    2.  Retrieves the original A2A `taskId` from the Cache Service using the `follow_up_id`.
    3.  Maps the `user_response` and optional `files` to A2A `Message.parts`.
    4.  Constructs `TaskSendParams` using the retrieved A2A `taskId`.
    5.  Sends the follow-up request to the A2A agent using `A2AClient.send_task()` via `asyncio.run()`.
    6.  Processes the subsequent A2A `Task` response (handling `COMPLETED`, `FAILED`,
        or even another `INPUT_REQUIRED` state) and returns the final `ActionResponse`.

    Args:
        component: The parent A2AClientAgentComponent instance.
        params: Dictionary containing action parameters: 'follow_up_id', 'user_response',
                and optionally 'files' (list of URLs).
        meta: Metadata dictionary, expected to contain 'session_id'.

    Returns:
        An ActionResponse containing the result of the follow-up A2A call or error information.
    """
    action_name = "provide_required_input"  # For logging context
    log.info(
        "Handling '%s' for agent '%s' with params: %s",
        action_name,
        component.agent_name,
        params,
    )

    follow_up_id = params.get("follow_up_id")
    user_response_text = params.get("user_response")
    file_urls_json = params.get("files") # Expecting JSON string list or None

    # 1. Validate Input Parameters
    if not follow_up_id:
        log.error("Missing 'follow_up_id' parameter for '%s'.", action_name)
        return ActionResponse(
            message="Missing required parameter: 'follow_up_id'.",
            error_info=ErrorInfo("Missing Parameter"),
        )
    if user_response_text is None:  # Allow empty string, but not None
        log.error("Missing 'user_response' parameter for '%s'.", action_name)
        return ActionResponse(
            message="Missing required parameter: 'user_response'.",
            error_info=ErrorInfo("Missing Parameter"),
        )

    # Parse file URLs if provided
    file_urls = []
    if file_urls_json:
        try:
            parsed_files = json.loads(file_urls_json)
            if isinstance(parsed_files, list):
                file_urls = [str(url) for url in parsed_files if isinstance(url, str)]
            else:
                log.warning("Ignoring 'files' parameter as it's not a valid JSON list string.")
        except json.JSONDecodeError:
            log.warning("Ignoring 'files' parameter due to JSON decoding error.")


    # 2. Check Availability of Services
    cache_service = component.cache_service
    a2a_client = component.a2a_client
    file_service = component.file_service

    if not cache_service:
        log.error(
            "CacheService not available for '%s'. Cannot handle '%s'.",
            component.agent_name,
            action_name,
        )
        return ActionResponse(
            message="Internal Error: Cache Service not available for follow-up.",
            error_info=ErrorInfo("Cache Service Missing"),
        )
    if not a2a_client:
        log.error(
            "A2AClient not available for '%s'. Cannot handle '%s'.",
            component.agent_name,
            action_name,
        )
        return ActionResponse(
            message="Internal Error: A2A Client not available for follow-up.",
            error_info=ErrorInfo("A2A Client Missing"),
        )
    if not file_service:
        # File service is needed even if no files are provided in *this* call,
        # because the *response* might contain files that need processing.
        log.error(
            "FileService not available for '%s'. Cannot handle '%s'.",
            component.agent_name,
            action_name,
        )
        return ActionResponse(
            message="Internal Error: File Service not available for follow-up.",
            error_info=ErrorInfo("File Service Missing"),
        )

    # 3. Retrieve Original A2A Task ID from Cache
    cache_key = f"a2a_follow_up:{follow_up_id}"
    a2a_taskId: Optional[str] = None
    try:
        # Use get_data() instead of get()
        a2a_taskId = cache_service.get_data(cache_key)
        if a2a_taskId is None:
            log.warning(
                "Follow-up ID '%s' not found in cache or expired for agent '%s'. Please start the task again.",
                follow_up_id,
                component.agent_name,
            )
            # The follow-up ID may have expired or been invalid. All we can do is inform the caller
            return ActionResponse(
                message="Invalid or expired follow-up ID. Please start the task again.",
                error_info=ErrorInfo("Invalid Follow-up ID"),
            )
        # Delete the entry immediately after retrieval to prevent reuse
        # Use remove_data() instead of delete()
        cache_service.remove_data(cache_key)
        log.info(
            "Retrieved original A2A task ID '%s' for follow-up ID '%s' (agent '%s'). Cache entry deleted.",
            a2a_taskId,
            follow_up_id,
            component.agent_name,
        )
    except Exception as e:
        log.error(
            "Error retrieving task ID from cache for follow-up ID '%s' (agent '%s'): %s",
            follow_up_id,
            component.agent_name,
            e,
            exc_info=True,
        )
        return ActionResponse(
            message="Internal Error: Failed to retrieve follow-up state from cache.",
            error_info=ErrorInfo(f"Cache Error: {e}"),
        )

    # 4. Map Input to A2A Message Parts
    session_id = meta.get("session_id")
    if not session_id:
        log.error(
            "No session_id found in meta for follow-up action '%s' (follow_up_id: %s). Cannot proceed.",
            action_name,
            follow_up_id,
        )
        return ActionResponse(
            message="Internal Error: Session context lost. Cannot process follow-up input.",
            error_info=ErrorInfo("Missing Session ID"),
        )

    parts: List[Any] = []
    # Add TextPart for the user's response
    try:
        parts.append(TextPart(text=str(user_response_text)))  # Ensure string
    except Exception as e:
        log.error(
            "Failed to create TextPart for follow-up response (task '%s'): %s",
            a2a_taskId,
            e,
            exc_info=True,
        )
        return ActionResponse(
            message="Internal Error: Could not process user response text for follow-up.",
            error_info=ErrorInfo(f"TextPart Error: {e}"),
        )

    # Add FileParts if file URLs are provided
    if file_urls: # Already ensured it's a list of strings
        log.debug(
            "Processing %d file URLs for follow-up (task '%s').",
            len(file_urls),
            a2a_taskId,
        )
        for file_url in file_urls:
            try:
                # Corrected logic: Use return_extra=True to get original bytes and metadata
                log.debug("Resolving follow-up file URL: %s", file_url)
                # resolved_content is the potentially transformed content (bytes or str)
                # original_bytes is the raw file content
                # file_metadata contains name, mime_type, etc.
                resolved_content, original_bytes, file_metadata = (
                    file_service.resolve_url(
                        file_url, session_id=session_id, return_extra=True
                    )
                )

                if original_bytes and file_metadata:
                    file_name = file_metadata.get(
                        "name", f"a2a_file_{uuid.uuid4().hex}"
                    )
                    mime_type = file_metadata.get(
                        "mime_type", "application/octet-stream"
                    )

                    try:
                        # Encode the *original* bytes for the FilePart
                        encoded_bytes = base64.b64encode(original_bytes).decode("utf-8")
                    except Exception as b64_e:
                        log.error(
                            "Failed to base64 encode follow-up file content for '%s': %s",
                            file_name,
                            b64_e,
                        )
                        continue  # Skip this file

                    file_content = FileContent(
                        bytes=encoded_bytes,
                        name=file_name,
                        mimeType=mime_type,
                    )
                    parts.append(FilePart(file=file_content))
                    log.debug(
                        "Successfully created FilePart for follow-up file '%s'.",
                        file_name,
                    )
                else:
                    # Log if resolve_url didn't return expected tuple
                    log.error(
                        "Failed to resolve follow-up file URL '%s' or resolve_url did not return expected data.",
                        file_url,
                    )
                    # Return error if file resolution fails
                    return ActionResponse(
                        message=f"Error: Could not resolve file URL: {file_url}",
                        error_info=ErrorInfo("File Resolution Error")
                    )
            except Exception as e:
                log.error(
                    "Error resolving follow-up file URL '%s' (task '%s'): %s",
                    file_url,
                    a2a_taskId,
                    e,
                    exc_info=True,
                )
                # Return error if file resolution fails
                return ActionResponse(
                    message=f"Error resolving file URL: {file_url}",
                    error_info=ErrorInfo(f"File Processing Error: {e}")
                )

    # 5. Create TaskSendParams (using retrieved a2a_taskId)
    try:
        a2a_message = A2AMessage(role="user", parts=parts)
        # Use the same broad accepted modes as the initial action
        accepted_modes = [
            "text",
            "text/plain",
            "image/*",
            "application/json",
            "application/*",
        ]
        # Crucially, use the *retrieved* a2a_taskId here
        task_params = TaskSendParams(
            id=a2a_taskId,
            sessionId=session_id,
            message=a2a_message,
            acceptedOutputModes=accepted_modes,
        )
        log.debug(
            "Constructed follow-up TaskSendParams for task '%s': %s",
            a2a_taskId,
            task_params.model_dump_json(exclude_none=True),
        )
    except Exception as e:
        log.error(
            "Failed to construct follow-up TaskSendParams for task '%s': %s",
            a2a_taskId,
            e,
            exc_info=True,
        )
        return ActionResponse(
            message="Internal Error: Failed to prepare follow-up A2A request.",
            error_info=ErrorInfo(f"TaskSendParams Error: {e}"),
        )

    # 6. Call A2A Agent and Process Response
    send_task_response: Optional[SendTaskResponse] = None # Initialize before try block
    try:
        log.info("Sending follow-up input for A2A task '%s'...", a2a_taskId)
        # Send the follow-up request using asyncio.run()
        # The result of asyncio.run is the return value of the coroutine
        send_task_response = asyncio.run(
            a2a_client.send_task(task_params.model_dump())
        )

        # Check for JSON-RPC level errors first
        if send_task_response.error:
            log.error(
                "A2A agent returned a JSON-RPC error during follow-up for task '%s': Code %d, Message: %s",
                a2a_taskId,
                send_task_response.error.code,
                send_task_response.error.message,
            )
            return ActionResponse(
                message=f"A2A agent reported an error during follow-up: {send_task_response.error.message}",
                error_info=ErrorInfo(
                    f"A2A Error Code {send_task_response.error.code}: {send_task_response.error.message}"
                ),
            )

        # Get the Task object from the result
        response_task: Optional[Task] = send_task_response.result

        # Check if the result (Task) is actually present
        if response_task is None:
            log.error(
                "A2A agent follow-up response did not contain a valid Task object for task '%s'.",
                a2a_taskId,
            )
            return ActionResponse(
                message="Internal Error: Received invalid follow-up response from A2A agent.",
                error_info=ErrorInfo("Invalid A2A Follow-up Response Structure"),
            )

        task_state = response_task.get_state()

        log.info(
            "Received follow-up response for task '%s'. New A2A State: %s",
            a2a_taskId,
            task_state,
        )

        # Find *any* A2AClientAction instance on the component to reuse its _process_parts logic.
        # This avoids duplicating the response processing logic here.
        action_instance_for_processing: Optional["A2AClientAction"] = None
        if hasattr(component, "action_list") and component.action_list:
            for act in component.action_list.actions:
                # Import locally only if needed, reducing initial load time
                from .actions.a2a_client_action import A2AClientAction

                if isinstance(act, A2AClientAction):
                    action_instance_for_processing = act
                    break  # Found one, no need to look further

        if not action_instance_for_processing:
            # This should not happen if the component initialized correctly
            log.error(
                "Cannot process A2A response for task '%s': No A2AClientAction instance found on component '%s'.",
                a2a_taskId,
                component.agent_name,
            )
            return ActionResponse(
                message="Internal Error: Cannot process A2A response due to component setup issue.",
                error_info=ErrorInfo("Processing Setup Error"),
            )

        # --- Process the response based on the *new* state ---
        if task_state == A2A_TASK_STATE_COMPLETED:
            log.info("Follow-up for task '%s' resulted in COMPLETED state.", a2a_taskId)
            final_message = ""
            final_files = []
            final_data = {}  # Accumulator for DataParts

            # Process final status message parts
            status_message = getattr(response_task.status, "message", None)
            if status_message:
                msg_parts = getattr(status_message, "parts", [])
                msg_text, msg_files = action_instance_for_processing._process_parts(
                    msg_parts, session_id, final_data  # Pass accumulator
                )
                if msg_text:
                    final_message += msg_text
                final_files.extend(msg_files)

            # Process final artifact parts
            artifacts = getattr(response_task, "artifacts", [])
            if artifacts:
                for artifact in artifacts:
                    artifact_parts = getattr(artifact, "parts", [])
                    art_text, art_files = action_instance_for_processing._process_parts(
                        artifact_parts, session_id, final_data  # Pass accumulator
                    )
                    if art_text:
                        if final_message:
                            final_message += "\n\n--- Artifact ---\n"
                        final_message += art_text
                    final_files.extend(art_files)

            # Construct final message, including data if present
            # Use extracted text if available, otherwise use default
            response_msg = final_message.strip() or "Task completed after follow-up."
            if final_data:
                try:
                    data_str = json.dumps(final_data, indent=2)
                    response_msg += f"\n\n--- Data ---\n{data_str}"
                except Exception as json_e:
                    log.warning(
                        "Could not serialize final_data to JSON (follow-up task '%s'): %s",
                        a2a_taskId,
                        json_e,
                    )
                    response_msg += "\n\n--- Data ---\n[Could not serialize data]"

            return ActionResponse(
                message=response_msg,
                files=final_files or None,
            )

        elif task_state == A2A_TASK_STATE_FAILED:
            log.error("Follow-up for task '%s' resulted in FAILED state.", a2a_taskId)
            error_message = f"A2A Task '{action_name}' Failed (after follow-up)"
            error_details = ""
            status_message = getattr(response_task.status, "message", None)
            if status_message:
                msg_parts = getattr(status_message, "parts", [])
                if msg_parts:
                    try:
                        # Extract text from *all* text parts in the message
                        extracted_texts = [
                            str(p.text) for p in msg_parts if hasattr(p, 'text') and p.text
                        ]
                        if extracted_texts:
                            error_details = "\n".join(extracted_texts)
                            error_message += f": {error_details}" # Append extracted details
                    except Exception as e:
                        log.warning(
                            "Could not extract error details from FAILED follow-up task '%s': %s",
                            a2a_taskId,
                            e,
                        )

            return ActionResponse(
                message=error_message,
                error_info=ErrorInfo(error_details or f"A2A Task {action_name} Failed"),
            )

        elif task_state == A2A_TASK_STATE_INPUT_REQUIRED:
            # Handle the case where the agent asks for *more* input after the follow-up
            log.warning(
                "Follow-up for task '%s' resulted in *another* INPUT_REQUIRED state.",
                a2a_taskId,
            )
            agent_question = (
                "A2A Task requires even more input."  # Default nested question
            )
            status_message = getattr(response_task.status, "message", None)
            if status_message:
                msg_parts = getattr(status_message, "parts", [])
                if msg_parts:
                    try:
                        # Extract text from *all* text parts in the message
                        extracted_texts = [
                            str(p.text) for p in msg_parts if hasattr(p, 'text') and p.text
                        ]
                        if extracted_texts:
                            agent_question = "\n".join(extracted_texts) # Use extracted question
                    except Exception as e:
                        log.warning(
                            "Could not extract nested question details from task '%s': %s",
                            a2a_taskId,
                            e,
                        )

            # Generate a *new* SAM follow-up ID for this nested request
            new_sam_follow_up_id = str(uuid.uuid4())
            new_cache_key = f"a2a_follow_up:{new_sam_follow_up_id}"
            try:
                # Store the *original* A2A task ID again, associated with the *new* follow-up ID
                # Use add_data() instead of set()
                cache_service.add_data(
                    key=new_cache_key,
                    value=a2a_taskId,
                    expiry=component.input_required_ttl,
                )
                log.info(
                    "Stored *nested* INPUT_REQUIRED state for A2A task '%s' with new SAM follow-up ID '%s'.",
                    a2a_taskId,
                    new_sam_follow_up_id,
                )
                # Inform the user with the new question and the *new* follow-up ID
                response_msg = f"{agent_question}\n\nPlease provide the required input using the 'provide_required_input' action with follow-up ID: `{new_sam_follow_up_id}`"
                return ActionResponse(
                    message=response_msg,
                    # error_info=ErrorInfo("Input Required", code="INPUT_REQUIRED") # Optional signal
                )
            except Exception as e:
                log.error(
                    "Failed to store nested INPUT_REQUIRED state in cache for task '%s': %s",
                    a2a_taskId,
                    e,
                    exc_info=True,
                )
                return ActionResponse(
                    message="Internal Error: Failed to store required input state after follow-up.",
                    error_info=ErrorInfo(f"Cache Error: {e}"),
                )
        else:
            # Handle other unexpected states after follow-up (including None)
            log.warning(
                "A2A Task '%s' returned unhandled or missing state after follow-up: %s. Treating as error.",
                a2a_taskId,
                task_state,
            )
            return ActionResponse(
                message=f"A2A Task is currently in an unexpected state after follow-up: {task_state}",
                error_info=ErrorInfo(f"Unhandled or Missing A2A State: {task_state}"),
            )

    except Exception as e:
        # Catch communication errors or processing errors during the follow-up call
        log.error(
            "Failed to communicate with or process response from A2A agent during follow-up for task '%s': %s",
            a2a_taskId,
            e,
            exc_info=True,
        )
        # Include the original exception message in the ErrorInfo
        return ActionResponse(
            message=f"Failed to execute follow-up for action '{action_name}' due to communication or processing error.",
            error_info=ErrorInfo(f"A2A Communication/Processing Error: {e}"),
        )
