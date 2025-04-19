"""
Handles the connection establishment and client initialization for an A2A agent.
Includes readiness checks and AgentCard fetching.
"""

import time
import requests
import threading
from urllib.parse import urljoin
from typing import Optional

from ...common_a2a.client import A2AClient, A2ACardResolver
from ...common_a2a.types import AgentCard
from solace_ai_connector.common.log import log  # Use solace-ai-connector log


class A2AConnectionHandler:
    """
    Handles establishing the connection to an A2A agent, checking its readiness,
    fetching its AgentCard, and initializing the A2AClient.

    Attributes:
        server_url (str): The base URL of the target A2A agent.
        bearer_token (Optional[str]): Bearer token for authentication, if required.
        stop_event (threading.Event): Event to signal termination during waits.
        agent_card (Optional[AgentCard]): The fetched AgentCard of the target agent.
        a2a_client (Optional[A2AClient]): The initialized A2AClient instance.
    """

    def __init__(
        self,
        server_url: str,
        bearer_token: Optional[str],
        stop_event: threading.Event,
    ):
        """
        Initializes the A2AConnectionHandler.

        Args:
            server_url: The base URL of the target A2A agent.
            bearer_token: Optional Bearer token for authentication.
            stop_event: A threading.Event to signal termination.
        """
        self.server_url = server_url.rstrip("/")
        self.bearer_token = bearer_token
        self.stop_event = stop_event
        self.agent_card: Optional[AgentCard] = None
        self.a2a_client: Optional[A2AClient] = None
        log.debug("A2AConnectionHandler initialized for URL: %s", self.server_url)

    def wait_for_ready(self, timeout: int) -> bool:
        """
        Polls the A2A agent's '/.well-known/agent.json' endpoint until it
        responds successfully (HTTP 200) or the specified timeout is reached.

        Checks the `stop_event` periodically to allow for early termination.

        Args:
            timeout (int): Maximum time in seconds to wait for the agent to become ready.

        Returns:
            True if the agent becomes ready within the timeout, False otherwise.
        """
        agent_card_url = urljoin(self.server_url, "/.well-known/agent.json")
        deadline = time.time() + timeout
        check_interval = 1  # Seconds between readiness checks
        request_timeout = 5  # Seconds for the HTTP request itself

        log.info(
            "Waiting up to %ds for A2A agent at %s to become ready...",
            timeout,
            self.server_url,
        )

        while time.time() < deadline:
            if self.stop_event.is_set():
                log.info("Stop signal received while waiting for agent readiness.")
                return False
            try:
                # Use requests for simple GET polling
                response = requests.get(agent_card_url, timeout=request_timeout)
                if response.status_code == 200:
                    log.info("A2A agent is ready at %s.", self.server_url)
                    return True
                else:
                    # Log non-200 status codes as warnings for visibility
                    log.warning(
                        "A2A agent at %s responded with status %d. Retrying...",
                        agent_card_url,
                        response.status_code,
                    )
            except requests.exceptions.ConnectionError:
                log.debug(
                    "A2A agent connection refused at %s. Retrying in %ds...",
                    self.server_url,
                    check_interval,
                )
            except requests.exceptions.Timeout:
                log.warning(
                    "Request timed out connecting to %s. Retrying...", agent_card_url
                )
            except requests.exceptions.RequestException as e:
                # Log other request exceptions as warnings
                log.warning(
                    "Error checking A2A agent readiness at %s: %s. Retrying in %ds...",
                    agent_card_url,
                    e,
                    check_interval,
                )

            # Wait for the check interval, but break early if stop_event is set
            if self.stop_event.wait(timeout=check_interval):
                log.info("Stop signal received while waiting for agent readiness.")
                return False

        # Loop finished without success
        log.error(
            "A2A agent at %s did not become ready within %d seconds.",
            self.server_url,
            timeout,
        )
        return False

    def initialize_client(self):
        """
        Fetches the AgentCard using A2ACardResolver and initializes the A2AClient,
        handling authentication based on the card and configured token.

        Raises:
            ValueError: If fetching the AgentCard fails or initializing the A2AClient fails.
        """
        # 1. Fetch Agent Card
        log.info("Fetching Agent Card from %s", self.server_url)
        try:
            resolver = A2ACardResolver(self.server_url)
            # Assuming get_agent_card is synchronous or handled appropriately by the library
            self.agent_card = resolver.get_agent_card()
            if not self.agent_card:
                # Should not happen if resolver raises exceptions on failure, but check anyway
                raise ValueError("A2ACardResolver returned None.")
            log.info("Successfully fetched Agent Card for '%s'", self.agent_card.name)
        except Exception as e:
            log.error(
                "Error fetching/parsing Agent Card from %s: %s",
                self.server_url,
                e,
                exc_info=True,
            )
            # Wrap the original exception for better context
            raise ValueError(
                f"Failed to get Agent Card from {self.server_url}: {e}"
            ) from e

        # 2. Determine Authentication Token based on AgentCard
        auth_token: Optional[str] = None
        bearer_required = False
        if self.agent_card.authentication and self.agent_card.authentication.schemes:
            # Check if 'bearer' is listed in the supported schemes
            if any(
                str(scheme).lower() == "bearer"
                for scheme in self.agent_card.authentication.schemes
            ):
                bearer_required = True
                log.info(
                    "AgentCard for '%s' indicates Bearer authentication support.",
                    self.agent_card.name,
                )

        if bearer_required:
            if self.bearer_token:
                auth_token = self.bearer_token
                log.info(
                    "Using configured Bearer token for A2A client connecting to '%s'.",
                    self.agent_card.name,
                )
            else:
                # Log a warning if required but not provided, but proceed without it
                log.warning(
                    "A2A Agent Card for '%s' requires Bearer token, but none configured ('a2a_bearer_token'). "
                    "Proceeding without authentication.",
                    self.agent_card.name,
                )
        elif self.bearer_token:
            # Log if a token is configured but not required by the card
            log.info(
                "Bearer token is configured but not explicitly required by AgentCard for '%s'. "
                "A2AClient will be initialized without the token.",
                self.agent_card.name,
            )

        # TODO: Add logic here to handle other authentication schemes (e.g., API Key)
        # based on self.agent_card.authentication and component configuration.

        # 3. Initialize A2AClient
        try:
            # Pass the determined auth_token (which might be None)
            self.a2a_client = A2AClient(
                agent_card=self.agent_card, auth_token=auth_token
            )
            log.info(
                "A2AClient initialized successfully for '%s'.", self.agent_card.name
            )
        except Exception as e:
            log.error(
                "Failed to initialize A2AClient for '%s': %s",
                self.agent_card.name,
                e,
                exc_info=True,
            )
            # Wrap the original exception
            raise ValueError(f"Could not initialize A2AClient: {e}") from e
