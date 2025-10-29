"""
Custom Solace AI Connector Component to host the FastAPI backend for the REST API Gateway.
"""

import logging
import threading
from typing import Any, Dict, Optional, List, Tuple, Union
import uuid
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, Request as FastAPIRequest, UploadFile


from solace_agent_mesh.gateway.base.component import BaseGatewayComponent

from a2a.types import (
    Task,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    JSONRPCError,
)
from solace_agent_mesh.common import a2a
from solace_agent_mesh.common.a2a import ContentPart
from solace_agent_mesh.common.utils.in_memory_cache import InMemoryCache
from solace_agent_mesh.agent.utils.artifact_helpers import (
    save_artifact_with_metadata,
)

log = logging.getLogger(__name__)

info = {
    "class_name": "RestGatewayComponent",
    "description": ("Hosts the FastAPI backend server for the REST API Gateway."),
    "config_parameters": [],
    "input_schema": {},
    "output_schema": {},
}


class RestGatewayComponent(BaseGatewayComponent):
    """
    Hosts the FastAPI backend for the REST API Gateway.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        log.info("%s Initializing REST API Gateway Component...", self.log_identifier)

        self.fastapi_host = self.get_config("rest_api_server_host", "127.0.0.1")
        self.fastapi_port = self.get_config("rest_api_server_port", 8080)
        self.fastapi_https_port = self.get_config("rest_api_https_port", 1943)
        self.ssl_keyfile = self.get_config("ssl_keyfile", "")
        self.ssl_certfile = self.get_config("ssl_certfile", "")
        self.ssl_keyfile_password = self.get_config("ssl_keyfile_password", "")

        self.fastapi_app: Optional[FastAPI] = None
        self.uvicorn_server: Optional[uvicorn.Server] = None
        self.fastapi_thread: Optional[threading.Thread] = None

        self.result_cache = InMemoryCache()

        self.sync_wait_events: Dict[str, Dict[str, Any]] = {}
        self.sync_wait_lock = threading.Lock()

        if not self.get_config("enforce_authentication"):
            log.warning("=" * 60)
            log.warning("!! SECURITY WARNING !!")
            log.warning("REST Gateway is running with 'enforce_authentication: false'.")
            log.warning("This configuration is for DEVELOPMENT ONLY.")
            log.warning(
                "Do NOT use this setting in a staging or production environment."
            )
            log.warning("=" * 60)

        log.info("%s REST API Gateway Component initialized.", self.log_identifier)

    def _start_fastapi_server(self):
        """Starts the Uvicorn server in a separate thread."""
        log.info(
            "%s Attempting to start FastAPI/Uvicorn server...",
            self.log_identifier,
        )
        if self.fastapi_thread and self.fastapi_thread.is_alive():
            log.warning(
                "%s FastAPI server thread already started.", self.log_identifier
            )
            return

        try:
            from .main import app as fastapi_app_instance, setup_dependencies

            self.fastapi_app = fastapi_app_instance
            setup_dependencies(self)

            config = uvicorn.Config(
                app=self.fastapi_app,
                host=self.fastapi_host,
                port=(
                    self.fastapi_https_port
                    if (self.ssl_keyfile and self.ssl_certfile)
                    else self.fastapi_port
                ),
                ssl_keyfile=self.ssl_keyfile,
                ssl_certfile=self.ssl_certfile,
                ssl_keyfile_password=self.ssl_keyfile_password,
                log_level="info",
            )
            self.uvicorn_server = uvicorn.Server(config)

            self.fastapi_thread = threading.Thread(
                target=self.uvicorn_server.run,
                daemon=True,
                name="RestGateway_FastAPI_Thread",
            )
            self.fastapi_thread.start()
            log.info(
                "%s FastAPI/Uvicorn server starting in background thread on http://%s:%d",
                self.log_identifier,
                self.fastapi_host,
                self.fastapi_port,
            )
        except Exception as e:
            log.exception(
                "%s Failed to start FastAPI/Uvicorn server: %s",
                self.log_identifier,
                e,
            )
            self.stop_signal.set()
            raise

    def _start_listener(self) -> None:
        """GDK Hook: Starts the FastAPI/Uvicorn server."""
        self._start_fastapi_server()

    def _stop_listener(self) -> None:
        """GDK Hook: Signals the Uvicorn server to shut down."""
        log.info(
            "%s _stop_listener called. Signaling Uvicorn server to exit.",
            self.log_identifier,
        )
        if self.uvicorn_server:
            self.uvicorn_server.should_exit = True

    async def _extract_initial_claims(
        self, external_event_data: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Extracts initial identity claims from the incoming external event.
        - Prioritizes forced identity for development.
        - Then checks for an authenticated user set by middleware.
        - Finally, falls back to a default identity if configured and auth is not enforced.
        """
        log_id_prefix = f"{self.log_identifier}[ExtractClaims]"
        if not isinstance(external_event_data, FastAPIRequest):
            log.warning(
                "%s Expected FastAPIRequest, got %s.",
                log_id_prefix,
                type(external_event_data).__name__,
            )
            return None

        force_identity = self.get_config("force_user_identity")
        if force_identity:
            log.warning(
                "%s DEVELOPMENT MODE: Forcing user identity to '%s'",
                log_id_prefix,
                force_identity,
            )
            return {"id": force_identity, "name": force_identity}

        request = external_event_data
        if hasattr(request.state, "user") and request.state.user:
            log.debug("%s Found user info in request.state.", log_id_prefix)
            return request.state.user

        enforce_auth = self.get_config("enforce_authentication", False)
        if not enforce_auth:
            default_identity = self.get_config("default_user_identity")
            if default_identity:
                log.debug(
                    "%s No authenticated user; using default_user_identity: '%s'",
                    log_id_prefix,
                    default_identity,
                )
                return {"id": default_identity, "name": default_identity}

        log.warning(
            "%s No authenticated user found and no default identity available.",
            log_id_prefix,
        )
        return None

    async def submit_a2a_task(
        self,
        target_agent_name: str,
        a2a_parts: List[ContentPart],
        external_request_context: Dict[str, Any],
        user_identity: Any,
        is_streaming: bool = True,
        api_version: str = "v2",
    ) -> str:
        """
        Overrides the base method to inject REST-specific context before submission.
        """
        log_id_prefix = f"{self.log_identifier}[SubmitA2ATask-REST]"
        log.debug(
            "%s Initializing REST-specific context. API Version: %s",
            log_id_prefix,
            api_version,
        )

        external_request_context["aggregated_artifacts"] = []

        return await super().submit_a2a_task(
            target_agent_name=target_agent_name,
            a2a_parts=a2a_parts,
            external_request_context=external_request_context,
            user_identity=user_identity,
            is_streaming=is_streaming,
            api_version=api_version,
        )

    async def _translate_external_input(
        self, external_event: Any
    ) -> Tuple[str, List[ContentPart], Dict[str, Any]]:
        """Translates raw HTTP request data into A2A task parameters."""
        log_id_prefix = f"{self.log_identifier}[TranslateInput]"

        agent_name = external_event.get("agent_name")
        prompt = external_event.get("prompt")
        files: List[UploadFile] = external_event.get("files", [])
        user_identity = external_event.get("user_identity")

        if not agent_name or not user_identity:
            raise ValueError("Agent name and user identity are required.")

        a2a_parts: List[ContentPart] = []
        user_id = user_identity.get("id")
        a2a_session_id = f"rest-session-{uuid.uuid4().hex}"

        if files and self.shared_artifact_service:
            file_metadata_summary_parts = []
            for upload_file in files:
                try:
                    content_bytes = await upload_file.read()
                    if not content_bytes:
                        continue

                    save_result = await save_artifact_with_metadata(
                        artifact_service=self.shared_artifact_service,
                        app_name=self.gateway_id,
                        user_id=user_id,
                        session_id=a2a_session_id,
                        filename=upload_file.filename,
                        content_bytes=content_bytes,
                        mime_type=upload_file.content_type
                        or "application/octet-stream",
                        metadata_dict={"source": "rest_gateway_upload"},
                        timestamp=datetime.now(timezone.utc),
                    )

                    if save_result["status"] in ["success", "partial_success"]:
                        version = save_result.get("data_version", 0)
                        uri = f"artifact://{self.gateway_id}/{user_id}/{a2a_session_id}/{upload_file.filename}?version={version}"
                        file_part = a2a.create_file_part_from_uri(
                            uri=uri, name=upload_file.filename
                        )
                        a2a_parts.append(file_part)
                        file_metadata_summary_parts.append(
                            f"- {upload_file.filename} ({len(content_bytes)} bytes)"
                        )
                    else:
                        log.error(
                            "%s Failed to save artifact %s: %s",
                            log_id_prefix,
                            upload_file.filename,
                            save_result.get("message"),
                        )
                finally:
                    await upload_file.close()

            if file_metadata_summary_parts:
                prompt = (
                    "The user uploaded the following file(s):\n"
                    + "\n".join(file_metadata_summary_parts)
                    + f"\n\nUser message: {prompt}"
                )

        if prompt:
            text_part = a2a.create_text_part(text=prompt)
            a2a_parts.append(text_part)

        external_request_context = {
            "user_id_for_artifacts": user_id,
            "a2a_session_id": a2a_session_id,
        }

        log.debug(
            "%s Translated input. Target: %s, Parts: %d",
            log_id_prefix,
            agent_name,
            len(a2a_parts),
        )
        return agent_name, a2a_parts, external_request_context

    async def _send_update_to_external(
        self,
        external_request_context: Dict[str, Any],
        event_data: Union[TaskStatusUpdateEvent, TaskArtifactUpdateEvent],
        is_final_chunk_of_update: bool,
    ) -> None:
        """
        Intercepts artifact updates to aggregate them. Suppresses all other updates.
        """
        log_id_prefix = f"{self.log_identifier}[SendUpdate]"
        task_id = event_data.task_id

        if isinstance(event_data, TaskArtifactUpdateEvent):
            context = self.task_context_manager.get_context(task_id)
            if context:
                if "aggregated_artifacts" not in context:
                    context["aggregated_artifacts"] = []
                artifact = a2a.get_artifact_from_artifact_update(event_data)
                if artifact:
                    context["aggregated_artifacts"].append(artifact)
                self.task_context_manager.store_context(task_id, context)
                log.debug(
                    "%s Aggregated artifact for task %s. Total artifacts: %d",
                    log_id_prefix,
                    task_id,
                    len(context["aggregated_artifacts"]),
                )
            else:
                log.warning(
                    "%s Received artifact update for task %s, but no context found.",
                    log_id_prefix,
                    task_id,
                )
        else:
            log.debug(
                "%s Suppressing intermediate status update for task %s.",
                log_id_prefix,
                task_id,
            )
        pass

    async def _send_final_response_to_external(
        self, external_request_context: Dict[str, Any], task_data: Task
    ) -> None:
        """
        Handles the final task result by enriching artifact data and then either
        caching it for v2 polling or resolving content for a v1 synchronous call.
        """
        task_id = a2a.get_task_id(task_data)
        log_id_prefix = f"{self.log_identifier}[SendFinalResponse:{task_id}]"

        context = self.task_context_manager.get_context(task_id)

        # If there are aggregated artifacts from streaming, update the main task object.
        if context and "aggregated_artifacts" in context:
            task_data.artifacts = context["aggregated_artifacts"]
            log.debug(
                "%s Injected %d aggregated artifacts into final task object.",
                log_id_prefix,
                len(task_data.artifacts),
            )

        api_version = context.get("api_version", "v2") if context else "v2"
        log.debug(
            "%s Processing final response for API version: %s",
            log_id_prefix,
            api_version,
        )

        # The base gateway has already resolved artifact URIs.
        # We just need to format the final task object and either set the sync event or cache it.
        final_task_dict = task_data.model_dump(exclude_none=True, by_alias=True)

        if api_version == "v1":
            with self.sync_wait_lock:
                wait_context = self.sync_wait_events.get(task_id)
            if wait_context:
                log.debug(
                    "%s Synchronous v1 call detected. Setting event with resolved task.",
                    log_id_prefix,
                )
                wait_context["result"] = final_task_dict
                wait_context["event"].set()
            else:
                log.warning(
                    "%s Received v1 final response for task %s, but no synchronous waiter was found.",
                    log_id_prefix,
                    task_id,
                )
        else:  # api_version == "v2"
            log.debug(
                "%s Storing final task result in cache for v2 polling.", log_id_prefix
            )
            self.result_cache.set(task_id, final_task_dict, ttl=600)

    async def _send_error_to_external(
        self, external_request_context: Dict[str, Any], error_data: JSONRPCError
    ) -> None:
        """
        Handles a final error result by either caching it for v2 polling
        or setting the event for a waiting synchronous call (v1).
        """
        task_id = external_request_context.get("a2a_task_id_for_event")
        if not task_id:
            log.error(
                "%s Cannot store error: task_id not found in context.",
                self.log_identifier,
            )
            return

        log_id_prefix = f"{self.log_identifier}[SendError:{task_id}]"
        context = self.task_context_manager.get_context(task_id)
        api_version = context.get("api_version", "v2") if context else "v2"
        log.debug(
            "%s Processing error response for API version: %s",
            log_id_prefix,
            api_version,
        )

        if api_version == "v1":
            with self.sync_wait_lock:
                wait_context = self.sync_wait_events.get(task_id)
            if wait_context:
                log.warning(
                    "%s Synchronous v1 call detected. Setting event with error.",
                    log_id_prefix,
                )
                wait_context["result"] = error_data.model_dump(exclude_none=True)
                wait_context["event"].set()
            else:
                log.warning(
                    "%s Received v1 error for task %s, but no synchronous waiter was found.",
                    log_id_prefix,
                    task_id,
                )
        else:
            log.warning(
                "%s Storing error result in cache for v2 polling: %s",
                log_id_prefix,
                a2a.get_error_message(error_data),
            )
            self.result_cache.set(
                task_id, error_data.model_dump(exclude_none=True), ttl=600
            )
