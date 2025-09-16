"""
Custom Solace AI Connector App class for the Slack Gateway.
Defines configuration schema and programmatically creates the SlackGatewayComponent.
"""

from typing import Any, Dict, List
from pydantic import Field
from solace_ai_connector.common.log import log
from solace_agent_mesh.gateway.base.app import (
    BaseGatewayApp, BaseGatewayAppConfig
)
from solace_agent_mesh.gateway.base.component import (
    BaseGatewayComponent
)
from .component import SlackGatewayComponent

info = {
    "class_name": "SlackGatewayApp",
    "description": "Custom App class for the A2A Slack Gateway with automatic subscription generation.",
}

class SlackBackendAppConfig(BaseGatewayAppConfig):
    """Pydantic model for the Web UI Backend application configuration."""
    slack_bot_token: str = Field(
        ..., description="Slack Bot Token (xoxb-...). Should use ${ENV_VAR}."
    )
    slack_app_token: str = Field(
        ..., description="Slack App Token (xapp-...) for Socket Mode. Should use ${ENV_VAR}."
    )
    default_agent_name: str = Field(
        default=None,
        description="Default agent to route messages to if not specified via mention.",
    )
    slack_initial_status_message: str = Field(
        default="Got it, thinking...",
        description="Message posted to Slack upon receiving a user request (set empty to disable).",
    )
    correct_markdown_formatting: bool = Field(
        default=True,
        description="Attempt to convert common Markdown (e.g., links) to Slack's format.",
    )
    feedback_enabled: bool = Field(
        default=False,
        description="Enable thumbs up/down feedback buttons on final Slack messages.",
    )
    feedback_post_url: str = Field(
        default=None,
        description="URL to POST feedback results to (required if feedback_enabled is true).",
    )
    feedback_post_headers: Dict[str, str] = Field(
        default={},
        description="Optional HTTP headers to include in the feedback POST request.",
    )
    slack_email_cache_ttl_seconds: int = Field(
        default=3600,
        description="TTL in seconds for caching Slack user email addresses. Set to 0 to disable caching.",
    )
    system_purpose: str = Field(
        default="",
        description="Global system purpose for tasks initiated via this Slack gateway. This can be used by agents to understand the broader context of requests originating from Slack.",
    )
    response_format: str = Field(
        default="",
        description="Global response format guidelines for tasks initiated via this Slack gateway. Agents can use this to tailor their responses appropriately for Slack.",
    )


class SlackGatewayApp(BaseGatewayApp):
    """
    Custom App class for the A2A Slack Gateway.
    - Extends BaseGatewayApp for common gateway functionalities.
    - Defines Slack-specific configuration parameters.
    """

    SPECIFIC_APP_SCHEMA_PARAMS: List[Dict[str, Any]] = []

    def __init__(self, app_info: Dict[str, Any], **kwargs):
        """
        Initializes the SlackGatewayApp.
        Most setup is handled by BaseGatewayApp.
        """
        log.debug(
            "%s Initializing SlackGatewayApp...",
            app_info.get("name", "SlackGatewayApp"),
        )
        super().__init__(app_info=app_info, gateway_app_config=SlackBackendAppConfig, **kwargs)
        log.debug("%s SlackGatewayApp initialization complete.", self.name)

    def _get_gateway_component_class(self) -> type[BaseGatewayComponent]:
        """
        Returns the specific gateway component class for this app.
        """
        return SlackGatewayComponent
