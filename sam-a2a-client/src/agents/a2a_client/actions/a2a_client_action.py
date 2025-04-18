"""
Dynamically created SAM Action to represent and invoke a specific A2A skill.
"""

import logging
import uuid
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from solace_agent_mesh.common.action import Action
from solace_agent_mesh.common.action_response import ActionResponse, ErrorInfo

# Import A2A types - adjust path as needed based on dependency setup
try:
    from common.types import AgentSkill, TaskSendParams, Message as A2AMessage, TextPart, FilePart, FileContent, Task, TaskState
except ImportError as e:
    logging.getLogger(__name__).error(f"CRITICAL: Failed to import A2A common types: {e}. Using placeholders. Ensure 'a2a-samples/samples/python/common' is in PYTHONPATH or installed.", exc_info=True)
    # Placeholder if common library isn't directly available in this structure
    AgentSkill = Any # type: ignore
    TaskSendParams = Any # type: ignore
    A2AMessage = Any # type: ignore
    TextPart = Any # type: ignore
    FilePart = Any # type: ignore
    FileContent = Any # type: ignore
    Task = Any # type: ignore
    TaskState = Any # type: ignore


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
        component: 'A2AClientAgentComponent',
        inferred_params: List[Dict[str, Any]]
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
            "prompt_directive": skill.description or f"Execute the {skill.name or skill.id} skill.",
            "params": inferred_params,
            # Define required scopes based on agent name and skill id
            "required_scopes": [f"{component.agent_name}:{skill.id}:execute"],
        }

        super().__init__(
            action_definition,
            agent=component,
            config_fn=component.get_config
        )
        logger.debug(f"Initialized A2AClientAction for skill '{self.skill.id}'")

    def invoke(self, params: Dict[str, Any], meta: Dict[str, Any]) -> ActionResponse:
        """
        Invokes the A2A skill by mapping SAM parameters to an A2A Task request,
        sending the request, and handling the basic response states.
        """
        logger.info(f"Invoking action '{self.name}' with params: {params}")

        # 1. Get necessary services and IDs
        a2a_client = self.component.a2a_client
        cache_service = self.component.cache_service # Needed later for INPUT_REQUIRED
        file_service = self.component.file_service

        if not a2a_client:
            logger.error(f"A2AClient not initialized for component '{self.component.agent_name}'. Cannot invoke action '{self.name}'.")
            return ActionResponse(message="Internal Error: A2A Client not available.", error_info=ErrorInfo("A2A Client Missing"))
        if not file_service:
            logger.error(f"FileService not available for component '{self.component.agent_name}'. Cannot handle file parameters for action '{self.name}'.")
            return ActionResponse(message="Internal Error: File Service not available.", error_info=ErrorInfo("File Service Missing"))

        session_id = meta.get("session_id")
        if not session_id:
            # A2A requires a session ID, generate one if missing from SAM meta
            session_id = str(uuid.uuid4())
            logger.warning(f"No session_id found in meta for action '{self.name}'. Generated new one: {session_id}")

        a2a_taskId = str(uuid.uuid4())

        # 2. Map SAM params to A2A Message.parts
        parts: List[Any] = [] # List to hold TextPart, FilePart, etc.
        prompt_text = params.get("prompt") # Assuming generic 'prompt' for now

        if prompt_text is None:
            # Maybe try finding the first string param if 'prompt' doesn't exist?
            # For now, require 'prompt' based on simple inference.
            logger.error(f"Missing required 'prompt' parameter for action '{self.name}'.")
            return ActionResponse(message="Missing required 'prompt' parameter.", error_info=ErrorInfo("Missing Parameter"))

        try:
            # This might still fail if TextPart is Any due to import error
            parts.append(TextPart(text=str(prompt_text)))
        except Exception as e:
             logger.error(f"Failed to create TextPart for action '{self.name}': {e}", exc_info=True)
             # Removed success=False
             return ActionResponse(message=f"Internal Error: Could not process prompt text.", error_info=ErrorInfo(f"TextPart Error: {e}"))


        file_urls = params.get("files", []) # Expecting a list of URLs
        if isinstance(file_urls, str): # Handle single URL case
            file_urls = [file_urls]

        if file_urls and isinstance(file_urls, list):
            logger.info(f"Processing {len(file_urls)} file URLs for action '{self.name}'.")
            for file_url in file_urls:
                if not isinstance(file_url, str):
                    logger.warning(f"Skipping non-string item in 'files' list: {file_url}")
                    continue
                try:
                    logger.debug(f"Resolving file URL: {file_url}")
                    # Assuming resolve_url returns an object with attributes: bytes, name, mime_type
                    # TODO: Confirm exact return type/attributes of FileService.resolve_url
                    resolved_file = file_service.resolve_url(file_url, session_id=session_id)
                    if resolved_file and hasattr(resolved_file, 'bytes') and hasattr(resolved_file, 'name') and hasattr(resolved_file, 'mime_type'):
                        # This might still fail if FileContent/FilePart are Any
                        file_content = FileContent(
                            bytes=resolved_file.bytes, # Assuming bytes are raw bytes
                            name=resolved_file.name,
                            mimeType=resolved_file.mime_type
                        )
                        parts.append(FilePart(file=file_content))
                        logger.debug(f"Successfully added FilePart for {resolved_file.name}")
                    else:
                        logger.error(f"Failed to resolve file URL '{file_url}' or resolved object is invalid.")
                        # Decide: fail action or just skip file? Skipping for now.
                        # return ActionResponse(message=f"Failed to resolve file URL: {file_url}", error_info=ErrorInfo("File Resolution Failed"))
                except Exception as e:
                    logger.error(f"Error resolving file URL '{file_url}' for action '{self.name}': {e}", exc_info=True)
                    # Decide: fail action or just skip file? Skipping for now.
                    # return ActionResponse(message=f"Error resolving file: {file_url}", error_info=ErrorInfo(f"File Resolution Error: {e}"))

        # 3. Create TaskSendParams
        try:
            # This might still fail if A2AMessage is Any
            a2a_message = A2AMessage(role="user", parts=parts)
            # TODO: Determine acceptedOutputModes dynamically? From skill? Hardcode for now.
            accepted_modes = ["text", "text/plain", "image/*", "application/json"]
            # This might still fail if TaskSendParams is Any
            task_params = TaskSendParams(
                id=a2a_taskId,
                sessionId=session_id,
                message=a2a_message,
                acceptedOutputModes=accepted_modes
            )
            logger.debug(f"Constructed TaskSendParams for action '{self.name}': {task_params.model_dump_json(exclude_none=True)}") # Log constructed params
        except Exception as e:
            logger.error(f"Failed to construct TaskSendParams for action '{self.name}': {e}", exc_info=True)
            # Removed success=False
            return ActionResponse(message="Internal Error: Failed to prepare A2A request.", error_info=ErrorInfo(f"TaskSendParams Error: {e}"))

        # 4. Call A2A Agent and Handle Basic Response
        try:
            logger.info(f"Sending task '{a2a_taskId}' to A2A agent for action '{self.name}'...")
            # Assuming send_task is synchronous and returns a Task object
            # This might fail if Task is Any
            response_task: Task = self.component.a2a_client.send_task(task_params.model_dump())
            logger.info(f"Received response for task '{a2a_taskId}'. State: {response_task.status.state}")

            # --- Basic State Handling ---
            # This might fail if TaskState is Any
            if response_task.status.state == TaskState.COMPLETED:
                # Response mapping will be implemented in Step 4.1
                logger.info(f"Task '{a2a_taskId}' completed successfully.")
                # Return success, but message processing is TBD
                return ActionResponse(success=True, message="A2A Task Completed (Processing TBD)")

            # Handle FAILED state (basic) - Refined in Step 4.2
            elif response_task.status.state == TaskState.FAILED:
                logger.error(f"A2A Task '{a2a_taskId}' failed.")
                error_message = "A2A Task Failed"
                # Try to get more details from the response message if possible
                if response_task.status and response_task.status.message and response_task.status.message.parts:
                    try:
                        # Assuming the first part is text containing the error
                        error_details = response_task.status.message.parts[0].text
                        if error_details:
                            error_message += f": {error_details}"
                    except Exception:
                        pass # Ignore if parts structure is unexpected
                return ActionResponse(success=False, message=error_message, error_info=ErrorInfo("A2A Task Failed"))

            # Handle INPUT_REQUIRED state (basic) - Refined in Step 4.3
            elif response_task.status.state == TaskState.INPUT_REQUIRED:
                logger.warning(f"A2A Task '{a2a_taskId}' requires input.")
                # Return pending/error, but state management is TBD
                return ActionResponse(success=False, message="A2A Task requires further input (Handling TBD)", status="INPUT_REQUIRED")

            # Handle other unexpected states
            else:
                logger.error(f"A2A Task '{a2a_taskId}' returned unexpected state: {response_task.status.state}")
                return ActionResponse(success=False, message=f"A2A Task ended with unexpected state: {response_task.status.state}", error_info=ErrorInfo("Unexpected A2A State"))

        except Exception as e:
            # Catch communication errors or errors during send_task itself
            logger.error(f"Failed to communicate with A2A agent for action '{self.name}': {e}", exc_info=True)
            return ActionResponse(success=False, message="Failed to communicate with A2A agent", error_info=ErrorInfo(f"A2A Communication Error: {e}"))
