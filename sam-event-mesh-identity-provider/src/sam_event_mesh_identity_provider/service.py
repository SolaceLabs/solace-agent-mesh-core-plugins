"""Generic event mesh service for request-response communication via Solace broker."""

import logging
import uuid
from typing import Any, Dict, Optional

from solace_ai_connector.common.message import Message

log = logging.getLogger(__name__)


class EventMeshService:
    """
    Sends requests to backend systems via Solace Event Mesh and waits for
    responses.  A single request-response session is shared across all
    operations; each operation is routed to its own configurable request
    and response topic pair.

    Only operations explicitly listed under the ``operations`` config key are
    available.  Calling :meth:`send_request` for an operation that is not
    configured returns ``None`` with a warning log — this is by design so
    that deployments can enable only the operations they need.
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

        # Response topic prefix (used for session-level correlation)
        self.response_topic_prefix = self._config.get(
            "response_topic_prefix", "sam/identity-provider/response"
        )

        # Request expiry
        self.default_request_expiry_ms = self._config.get("request_expiry_ms", 120000)

        # Operation topics — each entry must have request_topic and response_topic.
        self.operations: Dict[str, Dict[str, str]] = self._config.get("operations", {})

        self._create_session()

        log.info(
            "%s Initialized for broker '%s' with %d configured operations: %s",
            self.log_identifier,
            self.broker_url,
            len(self.operations),
            list(self.operations.keys()),
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

    def is_operation_configured(self, operation: str) -> bool:
        """Check whether *operation* has been configured."""
        return operation in self.operations

    async def send_request(
        self, operation: str, payload: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Send a request for *operation* and return the response payload.

        Args:
            operation: Operation name — must match a key under ``operations``
                in the YAML configuration.
            payload: Request payload dict forwarded to the backend.

        Returns:
            Parsed response payload, or ``None`` if the operation is not
            configured or the request fails.
        """
        op_config = self.operations.get(operation)
        if not op_config:
            log.warning(
                "%s Operation '%s' is not configured. "
                "Add it to the 'operations' section in your config to enable it. "
                "Currently configured operations: %s",
                self.log_identifier,
                operation,
                list(self.operations.keys()),
            )
            return None

        request_topic_template = op_config.get("request_topic", "")
        request_id = str(uuid.uuid4())

        try:
            format_vars = {"request_id": request_id, **payload}
            request_topic = request_topic_template.format(**format_vars)
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
