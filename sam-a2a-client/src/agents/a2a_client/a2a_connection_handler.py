import time
import requests
import logging
from urllib.parse import urljoin
from typing import Optional

from ...common_a2a.client import A2AClient, A2ACardResolver
from ...common_a2a.types import AgentCard

logger = logging.getLogger(__name__)


class A2AConnectionHandler:
    """Handles establishing connection and initializing the client for an A2A agent."""

    def __init__(
        self,
        server_url: str,
        startup_timeout: int,
        bearer_token: Optional[str],
        stop_event: threading.Event,
    ):
        self.server_url = server_url.rstrip("/")
        self.startup_timeout = startup_timeout
        self.bearer_token = bearer_token
        self.stop_event = stop_event
        self.agent_card: Optional[AgentCard] = None
        self.a2a_client: Optional[A2AClient] = None

    def wait_for_ready(self) -> bool:
        """Polls the A2A agent's well-known endpoint until it's ready or timeout occurs."""
        agent_card_url = urljoin(self.server_url, "/.well-known/agent.json")
        deadline = time.time() + self.startup_timeout
        check_interval = 1
        request_timeout = 5

        logger.info(
            f"Waiting up to {self.startup_timeout}s for A2A agent at {self.server_url} to become ready..."
        )

        while time.time() < deadline:
            if self.stop_event.is_set():
                logger.info("Stop signal received while waiting for agent readiness.")
                return False
            try:
                response = requests.get(agent_card_url, timeout=request_timeout)
                if response.status_code == 200:
                    logger.info(f"A2A agent is ready at {self.server_url}.")
                    return True
                else:
                    logger.debug(
                        f"A2A agent not ready yet (Status: {response.status_code}). Retrying in {check_interval}s..."
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
                logger.warning(
                    f"Error checking A2A agent readiness: {e}. Retrying in {check_interval}s..."
                )

            if self.stop_event.wait(timeout=check_interval):
                logger.info("Stop signal received while waiting for agent readiness.")
                return False

        logger.error(
            f"A2A agent at {self.server_url} did not become ready within {self.startup_timeout} seconds."
        )
        return False

    def initialize_client(self):
        """Fetches the AgentCard and initializes the A2AClient."""
        # 1. Fetch Agent Card
        logger.info(f"Fetching Agent Card from {self.server_url}")
        try:
            resolver = A2ACardResolver(self.server_url)
            self.agent_card = resolver.get_agent_card()
            if not self.agent_card:
                raise ValueError("Failed to fetch or parse Agent Card.")
            logger.info(f"Successfully fetched Agent Card for '{self.agent_card.name}'")
        except Exception as e:
            logger.error(f"Error fetching/parsing Agent Card: {e}", exc_info=True)
            raise ValueError(
                f"Failed to get Agent Card from {self.server_url}: {e}"
            ) from e

        # 2. Determine Authentication
        auth_token = None
        bearer_required = False
        if self.agent_card.authentication and self.agent_card.authentication.schemes:
            if any(
                str(scheme).lower() == "bearer"
                for scheme in self.agent_card.authentication.schemes
            ):
                bearer_required = True

        if bearer_required:
            if self.bearer_token:
                auth_token = self.bearer_token
                logger.info("Using configured Bearer token for A2A client.")
            else:
                logger.warning(
                    "A2A Agent Card requires Bearer token, but none configured ('a2a_bearer_token'). Proceeding without authentication."
                )
        # TODO: Add support for other auth schemes

        # 3. Initialize A2AClient
        try:
            self.a2a_client = A2AClient(agent_card=self.agent_card, auth_token=auth_token)
            logger.info("A2AClient initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize A2AClient: {e}", exc_info=True)
            raise ValueError(f"Could not initialize A2AClient: {e}") from e
