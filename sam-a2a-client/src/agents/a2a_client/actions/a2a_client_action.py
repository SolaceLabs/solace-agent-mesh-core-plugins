"""
Dynamically created SAM Action to represent and invoke a specific A2A skill.
Handles mapping SAM parameters to A2A requests and A2A responses back to SAM.
"""

import uuid
import json
import base64
import asyncio  # Import asyncio
from typing import Dict, Any, List, TYPE_CHECKING, Optional  # Added Optional

from solace_agent_mesh.common.action import Action
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo
from solace_agent_mesh.services.file_service import FS_PROTOCOL
from solace_ai_connector.common.log import log  # Use solace-ai-connector log
from ....common_a2a.types import (
    AgentSkill,
    TaskSendParams,
    Message as A2AMessage,
    TextPart,
    FilePart,
    FileContent,
    Task,
    TaskState,
    SendTaskResponse,  # Import SendTaskResponse
)


# Define string constants based on imported enum for robustness in comparisons
# Use getattr to avoid errors if TaskState failed to import
A2A_TASK_STATE_COMPLETED = getattr(TaskState, "COMPLETED", "completed")
A2A_TASK_STATE_FAILED = getattr(TaskState, "FAILED", "failed")
A2A_TASK_STATE_INPUT_REQUIRED = getattr(TaskState, "INPUT_REQUIRED", "input-required")
A2A_PART_TYPE_TEXT = "text"
A2A_PART_TYPE_FILE = "file"
A2A_PART_TYPE_DATA = "data"


# Use TYPE_CHECKING to avoid circular import issues at runtime
if TYPE_CHECKING:
    from ..a2a_client_agent_component import A2AClientAgentComponent


class A2AClientAction(Action):
    """
    A SAM Action that wraps a specific skill discovered from an A2A agent.

    It translates SAM action invocations into A2A `tasks/send` requests,
    handles the A2A response (including `COMPLETED`, `FAILED`, and
    `INPUT_REQUIRED` states), and maps the results back to a SAM
    `ActionResponse`. It utilizes the parent component's `A2AClient`,
    `FileService`, and `CacheService`.
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
            inferred_params: The list of parameters inferred for this action
                             (e.g., from `infer_params_from_skill`).
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
        log.debug(
            "Initialized A2AClientAction for skill '%s' in agent '%s'",
            self.skill.id,
            component.agent_name,
        )

    def _process_parts(
        self, parts: List[Any], session_id: str, response_data: Dict
    ) -> tuple[str, List[Dict]]:
        """
        Helper method to process a list of A2A parts (from message or artifact).

        Iterates through parts, concatenating text from TextParts, uploading
        content from FileParts using the FileService, and merging data from
        DataParts into the `response_data` dictionary.

        Args:
            parts: List of A2A Part objects (TextPart, FilePart, DataPart).
            session_id: The current session ID for file uploads.
            response_data: Dictionary to accumulate data from DataParts.

        Returns:
            A tuple containing:
            - response_message (str): Concatenated text from TextParts.
            - response_files (List[Dict]): List of file metadata dicts from FileParts
              uploaded via FileService.
        """
        response_message = ""
        response_files = []
        file_service = self.component.file_service  # Get service from component

        if not parts:
            log.debug("No parts provided to _process_parts.")
            return response_message, response_files

        log.debug("Processing %d A2A parts...", len(parts))
        for i, part in enumerate(parts):
            part_type = getattr(part, "type", None)
            log.debug("Processing part %d: type='%s'", i + 1, part_type)

            if part_type == A2A_PART_TYPE_TEXT:
                try:
                    text_content = getattr(part, "text", "")
                    if text_content:
                        if response_message:
                            response_message += "\n"  # Add newline between text parts
                        response_message += str(text_content)  # Ensure string
                        log.debug(
                            "  Appended text content (length %d).", len(text_content)
                        )
                except Exception as e:
                    log.warning(
                        "Could not extract text from TextPart at index %d: %s",
                        i,
                        e,
                        exc_info=True,
                    )

            elif part_type == A2A_PART_TYPE_FILE:
                try:
                    file_content: Optional[FileContent] = getattr(part, "file", None)
                    if not file_content:
                        log.warning(
                            "FilePart at index %d has missing 'file' attribute.", i
                        )
                        continue

                    file_bytes_b64: Optional[str] = getattr(file_content, "bytes", None)
                    file_uri: Optional[str] = getattr(file_content, "uri", None)
                    file_name: str = getattr(
                        file_content, "name", f"a2a_file_{uuid.uuid4().hex}"
                    )
                    mime_type: str = getattr(
                        file_content, "mimeType", "application/octet-stream"
                    )

                    file_bytes: Optional[bytes] = None

                    if file_bytes_b64:
                        try:
                            file_bytes = base64.b64decode(file_bytes_b64)
                            log.debug(
                                "  Decoded base64 content for FilePart '%s' (size %d).",
                                file_name,
                                len(file_bytes),
                            )
                        except Exception as b64_e:
                            log.error(
                                "Failed to decode base64 FilePart content for '%s': %s",
                                file_name,
                                b64_e,
                            )
                            continue  # Skip this file part if decoding fails
                    elif file_uri:
                        # TODO: Implement fetching file content from URI if needed.
                        # This might require additional configuration or security considerations.
                        # For now, we only handle inline bytes.
                        log.warning(
                            "FilePart '%s' provided URI '%s', but URI fetching is not implemented. Skipping.",
                            file_name,
                            file_uri,
                        )
                        continue
                    else:
                        log.warning(
                            "FilePart '%s' has neither 'bytes' nor 'uri'. Skipping.",
                            file_name,
                        )
                        continue

                    if file_bytes is not None:  # Check if we have bytes to upload
                        log.debug(
                            "Uploading FilePart '%s' (mime: %s) using FileService...",
                            file_name,
                            mime_type,
                        )
                        try:
                            # Use the FileService from the component
                            file_meta = file_service.upload_from_buffer(
                                buffer=file_bytes,  # Correct parameter name
                                file_name=file_name,
                                session_id=session_id,
                                mime_type=mime_type,
                                data_source=f"{self.component.agent_name}/{self.name}",  # Add context
                            )
                            if (
                                file_meta
                                and isinstance(file_meta, dict)
                                and file_meta.get("url")
                            ):
                                response_files.append(file_meta)
                                log.info(  # Log successful upload at INFO level
                                    "FilePart '%s' uploaded successfully: %s",
                                    file_name,
                                    file_meta.get("url"),
                                )
                            else:
                                log.error(
                                    "FileService.upload_from_buffer returned invalid metadata or None for '%s'.",
                                    file_name,
                                )
                        except Exception as upload_e:
                            log.error(
                                "Failed to upload FilePart '%s' using FileService: %s",
                                file_name,
                                upload_e,
                                exc_info=True,
                            )
                    # else: bytes were None (already handled by checks above)

                except Exception as e:
                    log.warning(
                        "Could not process FilePart at index %d: %s",
                        i,
                        e,
                        exc_info=True,
                    )

            elif part_type == A2A_PART_TYPE_DATA:
                try:
                    data_content = getattr(part, "data", None)
                    if isinstance(data_content, dict):
                        # Merge data - simple update, last key wins on conflict
                        response_data.update(data_content)
                        log.debug("  Merged DataPart content: %s", data_content)
                    elif data_content is not None:
                        log.warning(
                            "Skipping DataPart at index %d with non-dictionary content: %s",
                            i,
                            type(data_content),
                        )
                    else:
                        log.warning(
                            "DataPart at index %d has missing 'data' attribute.", i
                        )
                except Exception as e:
                    log.warning(
                        "Could not process DataPart at index %d: %s",
                        i,
                        e,
                        exc_info=True,
                    )

            else:
                log.warning(
                    "Encountered unknown or missing A2A Part type: '%s' at index %d. Skipping.",
                    part_type,
                    i,
                )

        return response_message, response_files

    def invoke(self, params: Dict[str, Any], meta: Dict[str, Any]) -> ActionResponse:
        """
        Invokes the A2A skill associated with this action.

        1.  Retrieves necessary services (A2AClient, FileService, CacheService) from the parent component.
        2.  Maps the input `params` (including resolving file URLs) to A2A `Message.parts`.
        3.  Constructs `TaskSendParams` with a unique A2A task ID and session ID.
        4.  Calls the A2A agent using `A2AClient.send_task()` via `asyncio.run()`.
        5.  Processes the A2A `Task` response based on its state:
            *   `COMPLETED`: Maps response parts/artifacts to `ActionResponse.message` and `ActionResponse.files`.
            *   `FAILED`: Extracts error details and returns an error `ActionResponse`.
            *   `INPUT_REQUIRED`: Stores the A2A task ID in the cache mapped to a new follow-up ID,
                and returns an `ActionResponse` containing the agent's question and the follow-up ID.
            *   Other states: Returns an error `ActionResponse` indicating the unhandled state.
        6.  Handles communication errors with the A2A agent.

        Args:
            params: Dictionary of parameters provided to the SAM action. Expected to contain
                    'prompt' and optionally 'files' (list of URLs).
            meta: Metadata dictionary associated with the SAM action invocation, expected
                  to contain 'session_id'.

        Returns:
            An `ActionResponse` object containing the result or error information.
        """
        action_name = self.name  # Use the action's name for logging
        log.info(
            "Invoking action '%s' for agent '%s' with params: %s",
            action_name,
            self.component.agent_name,
            params,
        )

        # 1. Get necessary services and IDs
        a2a_client = self.component.a2a_client
        cache_service = self.component.cache_service
        file_service = self.component.file_service

        if not a2a_client:
            log.error(
                "A2AClient not initialized for component '%s'. Cannot invoke action '%s'.",
                self.component.agent_name,
                action_name,
            )
            return ActionResponse(
                message="Internal Error: A2A Client not available.",
                error_info=ErrorInfo("A2A Client Missing"),
            )
        if not file_service:
            log.error(
                "FileService not available for component '%s'. Cannot handle file parameters for action '%s'.",
                self.component.agent_name,
                action_name,
            )
            return ActionResponse(
                message="Internal Error: File Service not available.",
                error_info=ErrorInfo("File Service Missing"),
            )
        # Cache service is optional for basic invocation, checked later for INPUT_REQUIRED

        session_id = meta.get("session_id")
        if not session_id:
            # Generate a session ID if none is provided in metadata
            session_id = str(uuid.uuid4())
            log.warning(
                "No session_id found in meta for action '%s'. Generated new one: %s",
                action_name,
                session_id,
            )

        # Generate a unique ID for this specific A2A task invocation
        a2a_taskId = str(uuid.uuid4())

        # 2. Map SAM params to A2A Message.parts
        parts: List[Any] = []
        prompt_text = params.get("prompt")

        # Validate required 'prompt' parameter
        if prompt_text is None:
            log.error(
                "Missing required 'prompt' parameter for action '%s'.", action_name
            )
            return ActionResponse(
                message="Missing required 'prompt' parameter.",
                error_info=ErrorInfo("Missing Parameter"),
            )

        # Create TextPart for the prompt
        try:
            parts.append(TextPart(text=str(prompt_text)))  # Ensure prompt is string
        except Exception as e:
            log.error(
                "Failed to create TextPart for action '%s' prompt: %s",
                action_name,
                e,
                exc_info=True,
            )
            return ActionResponse(
                message="Internal Error: Could not process prompt text.",
                error_info=ErrorInfo(f"TextPart Error: {e}"),
            )

        # Process optional 'files' parameter
        file_urls = params.get("files", [])
        # Ensure file_urls is a list, handle single string case
        if file_urls and isinstance(file_urls, str):
            try:
                file_urls = json.loads(file_urls)  # Attempt to parse JSON string
            except json.JSONDecodeError:
                if file_urls.startswith(FS_PROTOCOL):
                    # If it's a file URL, treat it as a single-item list
                    file_urls = [file_urls]
                else:
                    log.error(
                        "Invalid file URL string provided for action '%s': %s",
                        action_name,
                        file_urls,
                    )
                    return ActionResponse(
                        message="Invalid file URL format.",
                        error_info=ErrorInfo("Invalid File URL"),
                    )
        if file_urls and isinstance(file_urls, list):
            log.info(
                "Processing %d file URLs for action '%s' (task ID %s).",
                len(file_urls),
                action_name,
                a2a_taskId,
            )
            for file_url in file_urls:
                if not isinstance(file_url, str):
                    log.warning(
                        "Skipping non-string item in 'files' list for action '%s': %s",
                        action_name,
                        file_url,
                    )
                    continue
                try:
                    log.debug(
                        "Resolving file URL for action '%s': %s", action_name, file_url
                    )
                    # Use FileService to get file content and metadata
                    # Corrected: Use return_extra=True
                    resolved_content, original_bytes, file_metadata = (
                        file_service.resolve_url(
                            file_url, session_id=session_id, return_extra=True
                        )
                    )

                    # Check if resolution was successful and returned expected data
                    if original_bytes and file_metadata:
                        file_name = file_metadata.get(
                            "name", f"a2a_file_{uuid.uuid4().hex}"
                        )
                        mime_type = file_metadata.get(
                            "mime_type", "application/octet-stream"
                        )

                        # A2A FileContent expects base64 encoded string for bytes
                        try:
                            # Use original_bytes for encoding
                            encoded_bytes = base64.b64encode(original_bytes).decode(
                                "utf-8"
                            )
                        except Exception as b64_e:
                            log.error(
                                "Failed to base64 encode file content for '%s': %s",
                                file_name,
                                b64_e,
                            )
                            continue  # Skip this file if encoding fails

                        file_content = FileContent(
                            bytes=encoded_bytes,
                            name=file_name,
                            mimeType=mime_type,
                        )
                        parts.append(FilePart(file=file_content))
                        log.debug(
                            "Successfully created FilePart for '%s' for action '%s'.",
                            file_name,
                            action_name,
                        )
                    else:
                        # Log if resolution failed or returned unexpected object
                        log.error(
                            "Failed to resolve file URL '%s' for action '%s' or resolved object is invalid.",
                            file_url,
                            action_name,
                        )
                        # Return an error ActionResponse here if file resolution failure is critical
                        return ActionResponse(
                            message=f"Error: Could not resolve file URL: {file_url}",
                            error_info=ErrorInfo("File Resolution Error")
                        )
                except Exception as e:
                    # Log errors during file resolution
                    log.error(
                        "Error resolving file URL '%s' for action '%s': %s",
                        file_url,
                        action_name,
                        e,
                        exc_info=True,
                    )
                    # Return an error ActionResponse immediately
                    return ActionResponse(
                        message=f"Error resolving file URL: {file_url}",
                        error_info=ErrorInfo(f"File Processing Error: {e}")
                    )

        # 3. Create TaskSendParams
        try:
            # Construct the A2A message with the collected parts
            a2a_message = A2AMessage(role="user", parts=parts)
            # Define the output modes this SAM action is prepared to accept
            accepted_modes = [
                "text",  # Plain text
                "text/plain",  # Explicit plain text
                "image/*",  # Any image type
                "application/json",  # JSON data
                "application/*",  # Other application types (e.g., pdf)
            ]
            # Create the parameters for the A2A tasks/send request
            task_params = TaskSendParams(
                id=a2a_taskId,  # Unique ID for this A2A task
                sessionId=session_id,  # Session ID from SAM metadata
                message=a2a_message,  # The message constructed above
                acceptedOutputModes=accepted_modes,  # Inform agent what we accept
            )
            log.debug(
                "Constructed TaskSendParams for action '%s' (task ID %s): %s",
                action_name,
                a2a_taskId,
                task_params.model_dump_json(
                    exclude_none=True
                ),  # Log the request structure
            )
        except Exception as e:
            log.error(
                "Failed to construct TaskSendParams for action '%s': %s",
                action_name,
                e,
                exc_info=True,
            )
            return ActionResponse(
                message="Internal Error: Failed to prepare A2A request.",
                error_info=ErrorInfo(f"TaskSendParams Error: {e}"),
            )

        # 4. Call A2A Agent and Handle Response
        try:
            log.info(
                "Sending task '%s' to A2A agent '%s' for action '%s'...",
                a2a_taskId,
                self.component.agent_name,
                action_name,
            )
            # Make the call to the async A2A client method using asyncio.run()
            send_task_response: SendTaskResponse = asyncio.run(
                self.component.a2a_client.send_task(task_params.model_dump())
            )

            # Check for JSON-RPC level errors first
            if send_task_response.error:
                log.error(
                    "A2A agent returned a JSON-RPC error for task '%s': Code %d, Message: %s",
                    a2a_taskId,
                    send_task_response.error.code,
                    send_task_response.error.message,
                )
                return ActionResponse(
                    message=f"A2A agent reported an error: {send_task_response.error.message}",
                    error_info=ErrorInfo(
                        f"A2A Error Code {send_task_response.error.code}: {send_task_response.error.message}"
                    ),
                )

            # Get the Task object from the result
            response_task: Optional[Task] = send_task_response.result

            # Check if the result (Task) is actually present
            if response_task is None:
                log.error(
                    "A2A agent response did not contain a valid Task object for task '%s'.",
                    a2a_taskId,
                )
                return ActionResponse(
                    message="Internal Error: Received invalid response from A2A agent.",
                    error_info=ErrorInfo("Invalid A2A Response Structure"),
                )

            # Safely get the task state using the new helper method
            task_state = response_task.get_state()

            log.info(
                "Received response for task '%s'. A2A State: %s", a2a_taskId, task_state
            )

            # --- Process response based on A2A Task State ---
            if task_state == A2A_TASK_STATE_COMPLETED:
                log.info("Task '%s' completed successfully.", a2a_taskId)
                final_message = ""
                final_files = []
                final_data = {}  # Dictionary to hold data from DataParts

                # Process parts from the final status message, if any
                status_message = getattr(response_task.status, "message", None)
                if status_message:
                    msg_parts = getattr(status_message, "parts", [])
                    log.debug(
                        "Processing %d parts from status message...", len(msg_parts)
                    )
                    msg_text, msg_files = self._process_parts(
                        msg_parts, session_id, final_data  # Pass final_data dict
                    )
                    if msg_text:
                        final_message += msg_text
                    final_files.extend(msg_files)

                # Process parts from artifacts, if any
                artifacts = getattr(response_task, "artifacts", [])
                if artifacts:
                    log.debug("Processing %d artifacts...", len(artifacts))
                    for i, artifact in enumerate(artifacts):
                        artifact_parts = getattr(artifact, "parts", [])
                        log.debug(
                            "  Processing %d parts from artifact %d...",
                            len(artifact_parts),
                            i + 1,
                        )
                        art_text, art_files = self._process_parts(
                            artifact_parts,
                            session_id,
                            final_data,  # Pass final_data dict
                        )
                        if art_text:
                            # Add a separator if combining text from multiple sources
                            if final_message:
                                final_message += "\n\n--- Artifact ---\n"
                            final_message += art_text
                        final_files.extend(art_files)

                # Construct the final SAM ActionResponse message
                # Use a default message if no text was extracted
                response_msg = final_message.strip() or "Task completed successfully."

                # Append JSON representation of collected data if any exists
                if final_data:
                    try:
                        # Format the JSON data nicely for inclusion in the message
                        data_str = json.dumps(final_data, indent=2)
                        response_msg += f"\n\n--- Data ---\n{data_str}"
                    except Exception as json_e:
                        log.warning(
                            "Could not serialize final_data to JSON for task '%s': %s",
                            a2a_taskId,
                            json_e,
                        )
                        response_msg += "\n\n--- Data ---\n[Could not serialize data]"

                # Return the successful ActionResponse
                return ActionResponse(
                    message=response_msg,
                    files=final_files or None,  # Return None if the list is empty
                    # Note: SAM ActionResponse currently doesn't have a dedicated 'data' field.
                    # Data is included in the message string for now.
                )

            elif task_state == A2A_TASK_STATE_FAILED:
                log.error("A2A Task '%s' failed.", a2a_taskId)
                error_message = (
                    f"A2A Task '{action_name}' Failed"  # Default error message
                )
                error_details = ""  # Placeholder for details from A2A response

                # Attempt to extract more specific error details from the response message
                status_message = getattr(response_task.status, "message", None)
                if status_message:
                    msg_parts = getattr(status_message, "parts", [])
                    if msg_parts:
                        try:
                            # Assume the first text part contains the error detail
                            first_part_text = getattr(msg_parts[0], "text", "")
                            if first_part_text:
                                error_details = str(first_part_text)
                                error_message += f": {error_details}"  # Append details
                        except Exception as e:
                            log.warning(
                                "Could not extract error details from FAILED task '%s' message parts: %s",
                                a2a_taskId,
                                e,
                            )
                # Return an error ActionResponse
                return ActionResponse(
                    message=error_message,
                    error_info=ErrorInfo(
                        error_details
                        or f"A2A Task {action_name} Failed"  # Use details if available
                    ),
                )

            elif task_state == A2A_TASK_STATE_INPUT_REQUIRED:
                log.warning("A2A Task '%s' requires input.", a2a_taskId)
                # Check if CacheService is available, required for this state
                if not cache_service:
                    log.error(
                        "CacheService not available. Cannot handle INPUT_REQUIRED state for task '%s'.",
                        a2a_taskId,
                    )
                    return ActionResponse(
                        message="Internal Error: Cannot handle required input state without CacheService.",
                        error_info=ErrorInfo("Cache Service Missing"),
                    )

                # Extract the question/prompt from the A2A agent
                agent_question = "A2A Task requires further input."  # Default message
                status_message = getattr(response_task.status, "message", None)
                if status_message:
                    msg_parts = getattr(status_message, "parts", [])
                    if msg_parts:
                        try:
                            # Assume the first text part contains the question
                            question_details = getattr(msg_parts[0], "text", "")
                            if question_details:
                                agent_question = str(question_details)
                        except Exception as e:
                            log.warning(
                                "Could not extract question details from INPUT_REQUIRED task '%s' message parts: %s",
                                a2a_taskId,
                                e,
                            )

                # Generate a unique follow-up ID for SAM
                sam_follow_up_id = str(uuid.uuid4())
                # Get the original A2A task ID from the response
                a2a_original_taskId = getattr(response_task, "id", a2a_taskId)
                cache_key = f"a2a_follow_up:{sam_follow_up_id}"

                try:
                    # Store the mapping: SAM follow-up ID -> A2A Task ID in cache with TTL
                    # Use add_data instead of set
                    cache_service.add_data(
                        key=cache_key,
                        value=a2a_original_taskId,
                        expiry=self.component.input_required_ttl,  # Use configured TTL
                    )
                    log.info(
                        "Stored INPUT_REQUIRED state for A2A task '%s' with SAM follow-up ID '%s' (TTL: %ds).",
                        a2a_original_taskId,
                        sam_follow_up_id,
                        self.component.input_required_ttl,
                    )
                    # Construct the message for the SAM user, including the follow-up ID
                    response_msg = f"{agent_question}\n\nPlease provide the required input using the 'provide_required_input' action with follow-up ID: `{sam_follow_up_id}`\n\nNOTE - when requesting this information from the user, include the follow-up ID in the request so that it is stored in the session history and be available for future use."
                    # Return an ActionResponse indicating input is needed
                    # Note: SAM ActionResponse doesn't have a standard 'status' field.
                    # We convey the need for input via the message and potentially error_info.
                    return ActionResponse(
                        message=response_msg,
                        # Consider using error_info to signal non-completion if needed by orchestrator
                        # error_info=ErrorInfo("Input Required", code="INPUT_REQUIRED") # Example
                    )
                except Exception as e:
                    log.error(
                        "Failed to store INPUT_REQUIRED state in cache for task '%s': %s",
                        a2a_original_taskId,
                        e,
                        exc_info=True,
                    )
                    return ActionResponse(
                        message="Internal Error: Failed to store required input state.",
                        error_info=ErrorInfo(f"Cache Error: {e}"),
                    )

            else:
                # Handle any other unexpected A2A task states (including None)
                log.warning(
                    "A2A Task '%s' returned unhandled or missing state: %s. Treating as error.",
                    a2a_taskId,
                    task_state,
                )
                return ActionResponse(
                    message=f"A2A Task is currently in an unexpected state: {task_state}",
                    error_info=ErrorInfo(
                        f"Unhandled or Missing A2A State: {task_state}"
                    ),
                )

        except Exception as e:
            # Catch potential communication errors (e.g., ConnectionError, Timeout)
            # or errors during response processing
            log.error(
                "Failed to communicate with or process response from A2A agent for action '%s' (task ID %s): %s",
                action_name,
                a2a_taskId,
                e,
                exc_info=True,
            )
            return ActionResponse(
                message=f"Failed to execute action '{action_name}' due to communication or processing error.",
                error_info=ErrorInfo(f"A2A Communication/Processing Error: {e}"),
            )
