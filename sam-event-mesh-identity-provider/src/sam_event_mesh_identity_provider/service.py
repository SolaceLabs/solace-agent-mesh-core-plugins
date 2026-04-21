"""Generic event mesh service for request-response communication via Solace broker."""

import logging
import uuid
from typing import Any, Dict, Optional

from solace_ai_connector.common.message import Message

log = logging.getLogger(__name__)

# All supported operation names.
ALL_OPERATIONS = (
    "user_profile",
    "search_users",
    "employee_data",
    "employee_profile",
    "time_off",
    "profile_picture",
)


class EventMeshService:
    """
    Sends requests to backend systems via Solace Event Mesh and waits for
    responses.  A single request-response session is shared across all
    operations; each operation is routed to its own configurable topic.

    ``request_topic`` accepts two forms:

    * **string** — the same topic template is used for every operation.
    * **dict**   — maps operation names to their individual topic templates.
      Operations missing from the dict will log a warning and return ``None``.
    """

    def __init__(self, config: Dict[str, Any], component):
        if not config:
            raise ValueError("EventMeshService requires a configuration dictionary.")
        if not component:
            raise ValueError(
                "EventMeshService requires a SAM component reference for broker communication."
            )

        self._config = config
        self.component = component
        self.log_identifier = "[EventMeshService]"
        self.session_id: Optional[str] = None

        # Broker connection
        self.dev_mode = self._config.get("dev_mode", False)
        self.broker_url = self._config.get("broker_url")
        self.broker_vpn = self._config.get("broker_vpn")
        self.broker_username = self._config.get("broker_username")
        self.broker_password = self._config.get("broker_password")

        # Response topic prefix
        self.response_topic_prefix = self._config.get(
            "response_topic_prefix", "sam/identity-provider/response"
        )

        # Request expiry
        self.default_request_expiry_ms = self._config.get("request_expiry_ms", 120000)

        # Build per-operation topic map from request_topic config.
        raw = self._config.get("request_topic", {})
        if isinstance(raw, str):
            # Single topic string → use for every operation.
            self.topic_map: Dict[str, str] = dict.fromkeys(ALL_OPERATIONS, raw)
        elif isinstance(raw, dict):
            self.topic_map = dict(raw)
        else:
            raise ValueError(
                f"'request_topic' must be a string or dict, got {type(raw).__name__}."
            )

        self._create_session()

        log.info(
            "%s Initialized for broker '%s' with %d configured operations.",
            self.log_identifier,
            self.broker_url,
            len(self.topic_map),
        )

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _create_session(self):
        """Creates a request-response session on the Solace broker."""
        event_mesh_config = {
            "broker_config": {
                "dev_mode": self.dev_mode,
                "broker_url": self.broker_url,
                "broker_username": self.broker_username,
                "broker_password": self.broker_password,
                "broker_vpn": self.broker_vpn,
            },
            "request_expiry_ms": self.default_request_expiry_ms,
            "payload_encoding": "utf-8",
            "payload_format": "json",
            "response_topic_prefix": self.response_topic_prefix,
            "response_queue_prefix": self.response_topic_prefix,
        }

        try:
            self.session_id = self.component.create_request_response_session(
                session_config=event_mesh_config
            )
            log.info(
                "%s Session created with ID: %s",
                self.log_identifier,
                self.session_id,
            )
        except Exception as e:
            log.error(
                "%s Failed to create request/response session: %s",
                self.log_identifier,
                e,
            )
            raise

    # ------------------------------------------------------------------
    # Generic request / response
    # ------------------------------------------------------------------

    async def send_request(
        self, operation: str, payload: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Send a request for *operation* and return the response payload.

        Args:
            operation: Operation name (must match a key in ``topic_map``).
            payload: Request payload dict forwarded to the backend.

        Returns:
            Parsed response payload, or ``None`` on failure.
        """
        topic_template = self.topic_map.get(operation)
        if not topic_template:
            log.warning(
                "%s No request_topic configured for operation '%s'. "
                "Available: %s",
                self.log_identifier,
                operation,
                list(self.topic_map.keys()),
            )
            return None

        request_id = str(uuid.uuid4())

        try:
            format_vars = {"request_id": request_id, **payload}
            request_topic = topic_template.format(**format_vars)
        except KeyError as e:
            log.error(
                "%s Topic template for operation '%s' requires variable %s "
                "not found in payload.",
                self.log_identifier,
                operation,
                e,
            )
            return None

        log.info(
            "%s Sending '%s' request (id: %s) to topic: %s",
            self.log_identifier,
            operation,
            request_id,
            request_topic,
        )

        try:
            message = Message(payload=payload, topic=request_topic)
            response_message: Message = (
                await self.component.do_broker_request_response_async(
                    message, session_id=self.session_id
                )
            )
            response = response_message.get_payload()

            log.info(
                "%s Received response for '%s' request (id: %s)",
                self.log_identifier,
                operation,
                request_id,
            )
            return response

        except Exception as e:
            log.exception(
                "%s Failed '%s' request (id: %s): %s",
                self.log_identifier,
                operation,
                request_id,
                e,
            )
            return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        """Destroys the request-response session."""
        log.info("%s Shutting down EventMeshService", self.log_identifier)
        if self.session_id and self.component:
            self.component.destroy_request_response_session(self.session_id)
            self.session_id = None
        log.info("%s Shutdown complete", self.log_identifier)
