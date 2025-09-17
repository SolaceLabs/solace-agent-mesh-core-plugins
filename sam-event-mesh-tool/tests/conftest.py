"""
Pytest fixtures for the Event Mesh Tool integration tests.

This file sets up a complete, in-memory test environment with two communicating
Solace AI Connector instances:
1. An "agent" app that hosts the EventMeshTool (the System Under Test).
2. A "responder" flow that simulates a backend microservice, which receives
   requests from the tool and sends back controlled responses.
"""

import pytest
import queue
import time
import functools
import yaml
from pathlib import Path
from typing import Generator, Dict, Any

from solace_ai_connector.solace_ai_connector import SolaceAiConnector
from solace_ai_connector.common.message import Message
from solace_ai_connector.common.utils import get_data_value
from solace_agent_mesh.agent.sac.component import SamAgentComponent

# --- Constants ---
CONFIG_PATH = Path(__file__).parent / "test_configs"
AGENT_CONFIG_FILE = CONFIG_PATH / "agent_config.yaml"
RESPONDER_CONFIG_FILE = CONFIG_PATH / "responder_config.yaml"
# Default key used by BrokerRequestResponse to store the reply-to topic
REPLY_TOPIC_KEY = "__solace_ai_connector_broker_request_response_topic__"


# --- Fixture 1: Control Queue ---
@pytest.fixture(scope="session")
def response_control_queue() -> queue.Queue:
    """A queue to control the responder's behavior from within a test."""
    return queue.Queue()


# --- Fixture 2: Responder Handler Logic ---
def responder_invoke_handler(
    message: Message,
    data: Dict[str, Any],
    control_queue: queue.Queue,
) -> Dict[str, Any]:
    """
    The invoke logic for the responder's handler_callback component.
    It waits for instructions from the control_queue to generate a response.
    """
    try:
        # Instruction is a tuple: (response_payload, delay_seconds)
        response_payload, delay_seconds = control_queue.get(timeout=5)

        if delay_seconds > 0:
            time.sleep(delay_seconds)

        # Extract the dynamic reply-to topic from the request's user properties
        reply_to_topic = get_data_value(message.get_user_properties(), REPLY_TOPIC_KEY)
        if not reply_to_topic:
            raise ValueError("Could not find reply-to topic in request message")

        # The dictionary returned here becomes the "previous" data for the broker_output
        return {"topic": reply_to_topic, "payload": response_payload}

    except queue.Empty:
        pytest.fail("Responder did not receive control message from the test.")
        return {}  # Should not be reached


# --- Fixture 3: Responder Service ---
@pytest.fixture(scope="session")
def responder_service(
    response_control_queue: queue.Queue,
) -> Generator[SolaceAiConnector, None, None]:
    """
    Starts the responder flow in a background thread.
    This simulates the backend microservice.
    """
    # Create a specific handler for this session by binding the control queue
    handler = functools.partial(
        responder_invoke_handler, control_queue=response_control_queue
    )

    # Load the config, inject the handler, and then create the connector
    with open(RESPONDER_CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Find the handler_callback component in the config dict and inject the handler
    for app in config.get("apps", []):
        if app.get("name") == "responder-app":
            for flow in app.get("flows", []):
                if flow.get("name") == "responder-flow":
                    for component in flow.get("components", []):
                        if component.get("component_name") == "response_handler":
                            component["component_config"]["invoke_handler"] = handler
                            break
                    break
            break

    connector = SolaceAiConnector(config)
    connector.run()
    yield connector
    connector.stop()


# --- Fixture 4: Agent with Tool ---
@pytest.fixture(scope="session")
def agent_with_event_mesh_tool(
    responder_service: SolaceAiConnector,
) -> Generator[SamAgentComponent, None, None]:
    """
    Starts the agent with the EventMeshTool in a background thread.
    This is the System Under Test (SUT).
    """
    # The responder_service fixture is included to ensure it starts first.
    with open(AGENT_CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    connector = SolaceAiConnector(config)
    connector.run()

    # Find the running agent component instance to yield to the test
    agent_app = connector.get_app("test-agent-app")
    
    # In simplified mode, the component is in the first flow
    if agent_app.flows:
        flow = agent_app.flows[0]
        # Find the SamAgentComponent in the flow's components
        agent_component = None
        for component in flow.components:
            if isinstance(component, SamAgentComponent):
                agent_component = component
                break
        
        if not agent_component:
            pytest.fail("Could not find SamAgentComponent in the test agent app flow.")
    else:
        pytest.fail("No flows found in test agent app.")

    yield agent_component
    connector.stop()
