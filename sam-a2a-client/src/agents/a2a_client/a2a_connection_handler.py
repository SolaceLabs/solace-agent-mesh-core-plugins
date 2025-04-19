"""
Handles the connection establishment and client initialization for an A2A agent.
Includes readiness checks and AgentCard fetching.
"""

import time
import requests
import logging
import threading
from urllib.parse import urljoin
from typing import Optional

from ...common_a2a.client import A2AClient, A2ACardResolver
from ...common_a2a.types import AgentCard

logger = logging.getLogger(__name__)


class A2AConnectionHandler:
    """
    Handles establishing the connection to an A2A agent, checking its readiness,
    fetching its AgentCard, and initializing the A2AClient.

    Attributes:
        server_url (str): The base URL of the target A2A agent.
        startup_timeout (int): Maximum time in seconds to wait for the agent to become ready.
        bearer_token (Optional[str]): Bearer token for authentication, if required.
        stop_event (threading.Event): Event to signal termination during waits.
        agent_card (Optional[AgentCard]): The fetched AgentCard of the target agent.
        a2a_client (Optional[A2AClient]): The initialized A2AClient instance.
    """

    def __init__(
        self,
        server_url: str,
        startup_timeout: int,
        bearer_token: Optional[str],
        stop_event: threading.Event,
    ):
        """
        Initializes the A2AConnectionHandler.

        Args:
            server_url: The base URL of the target A2A agent.
            startup_timeout: Seconds to wait for the agent to become ready.
            bearer_token: Optional Bearer token for authentication.
            stop_event: A threading.Event to signal termination.
        """
        self.server_url = server_url.rstrip("/")
        self.startup_timeout = startup_timeout
        self.bearer_token = bearer_token
        self.stop_event = stop_event
        self.agent_card: Optional[AgentCard] = None
        self.a2a_client: Optional[A2AClient] = None
        logger.debug(f"A2AConnectionHandler initialized for URL: {self.server_url}")

    def wait_for_ready(self) -> bool:
        """
        Polls the A2A agent's '/.well-known/agent.json' endpoint until it
        responds successfully (HTTP 200) or the startup timeout is reached.

        Checks the `stop_event` periodically to allow for early termination.

        Returns:
            True if the agent becomes ready within the timeout, False otherwise.
        """
        agent_card_url = urljoin(self.server_url, "/.well-known/agent.json")
        deadline = time.time() + self.startup_timeout
        check_interval = 1  # Seconds between readiness checks
        request_timeout = 5 # Seconds for the HTTP request itself

        logger.info(
            f"Waiting up to {self.startup_timeout}s for A2A agent at {self.server_url} to become ready..."
        )

        while time.time() < deadline:
            if self.stop_event.is_set():
                logger.info("Stop signal received while waiting for agent readiness.")
                return False
            try:
                # Use requests for simple GET polling
                response = requests.get(agent_card_url, timeout=request_timeout)
                if response.status_code == 200:
                    logger.info(f"A2A agent is ready at {self.server_url}.")
                    return True
                else:
                    # Log non-200 status codes as warnings for visibility
                    logger.warning(
                        f"A2A agent at {agent_card_url} responded with status {response.status_code}. Retrying..."
                    )
            except requests.exceptions.ConnectionError:
                logger.debug(
                    f"A2A agent connection refused at {self.server_url}. Retrying in {check_interval}s..."
                )
            except requests.exceptions.Timeout:
                logger.warning(
                    f"Request timed out connecting to {agent_card_url}. Retrying..."
                )
            except requests.exceptions.RequestException as e:
                # Log other request exceptions as warnings
                logger.warning(
                    f"Error checking A2A agent readiness at {agent_card_url}: {e}. Retrying in {check_interval}s..."
                )

            # Wait for the check interval, but break early if stop_event is set
            if self.stop_event.wait(timeout=check_interval):
                logger.info("Stop signal received while waiting for agent readiness.")
                return False

        # Loop finished without success
        logger.error(
            f"A2A agent at {self.server_url} did not become ready within {self.startup_timeout} seconds."
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
        logger.info(f"Fetching Agent Card from {self.server_url}")
        try:
            resolver = A2ACardResolver(self.server_url)
            # Assuming get_agent_card is synchronous or handled appropriately by the library
            self.agent_card = resolver.get_agent_card()
            if not self.agent_card:
                # Should not happen if resolver raises exceptions on failure, but check anyway
                raise ValueError("A2ACardResolver returned None.")
            logger.info(f"Successfully fetched Agent Card for '{self.agent_card.name}'")
        except Exception as e:
            logger.error(f"Error fetching/parsing Agent Card from {self.server_url}: {e}", exc_info=True)
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
                logger.info(f"AgentCard for '{self.agent_card.name}' indicates Bearer authentication support.")

        if bearer_required:
            if self.bearer_token:
                auth_token = self.bearer_token
                logger.info(f"Using configured Bearer token for A2A client connecting to '{self.agent_card.name}'.")
            else:
                # Log a warning if required but not provided, but proceed without it
                logger.warning(
                    f"A2A Agent Card for '{self.agent_card.name}' requires Bearer token, but none configured ('a2a_bearer_token'). "
                    "Proceeding without authentication."
                )
        elif self.bearer_token:
             # Log if a token is configured but not required by the card
             logger.info(
                  f"Bearer token is configured but not explicitly required by AgentCard for '{self.agent_card.name}'. "
                  "A2AClient will be initialized without the token."
             )

        # TODO: Add logic here to handle other authentication schemes (e.g., API Key)
        # based on self.agent_card.authentication and component configuration.

        # 3. Initialize A2AClient
        try:
            # Pass the determined auth_token (which might be None)
            self.a2a_client = A2AClient(agent_card=self.agent_card, auth_token=auth_token)
            logger.info(f"A2AClient initialized successfully for '{self.agent_card.name}'.")
        except Exception as e:
            logger.error(f"Failed to initialize A2AClient for '{self.agent_card.name}': {e}", exc_info=True)
            # Wrap the original exception
            raise ValueError(f"Could not initialize A2AClient: {e}") from e
