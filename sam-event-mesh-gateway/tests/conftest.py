"""
Pytest configuration and fixtures for Event Mesh Gateway integration tests.
"""

import pytest
import asyncio
import time
import logging
from typing import Dict, Any, Generator, Optional

# Import from the main SAM test infrastructure
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'solace-agent-mesh', 'tests'))

from sam_test_infrastructure.llm_server.server import TestLLMServer
from sam_test_infrastructure.artifact_service.service import TestInMemoryArtifactService

# Import our local test infrastructure
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from sam_test_infrastructure.dev_broker import DevBroker, BrokerConfig
from sam_test_infrastructure.event_mesh_test_server import EventMeshTestServer

# Import the gateway components
from sam_event_mesh_gateway.app import EventMeshGatewayApp
from sam_event_mesh_gateway.component import EventMeshGatewayComponent

# Import SAM and SAC components
from solace_ai_connector.solace_ai_connector import SolaceAiConnector
from solace_agent_mesh.agent.sac.app import SamAgentApp
from solace_agent_mesh.agent.sac.component import SamAgentComponent


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_llm_server():
    """
    Session-scoped TestLLMServer fixture.
    Reuses the existing LLM server from the main SAM test infrastructure.
    """
    server = TestLLMServer(host="127.0.0.1", port=8089)  # Different port to avoid conflicts
    server.start()

    max_retries = 20
    retry_delay = 0.25
    ready = False
    for i in range(max_retries):
        await asyncio.sleep(retry_delay)
        try:
            if server.started:
                print(f"TestLLMServer confirmed started after {i+1} attempts.")
                ready = True
                break
            print(f"TestLLMServer not ready yet (attempt {i+1}/{max_retries})...")
        except Exception as e:
            print(f"TestLLMServer readiness check (attempt {i+1}/{max_retries}) encountered an error: {e}")

    if not ready:
        try:
            server.stop()
        except Exception:
            pass
        pytest.fail("TestLLMServer did not become ready in time.")

    print(f"TestLLMServer fixture: Server ready at {server.url}")
    yield server

    print("TestLLMServer fixture: Stopping server...")
    server.stop()
    print("TestLLMServer fixture: Server stopped.")


@pytest.fixture(autouse=True)
def clear_llm_server_configs(test_llm_server: TestLLMServer):
    """Automatically clear LLM server configurations between tests."""
    test_llm_server.clear_all_configurations()


@pytest.fixture(scope="session")
def test_artifact_service_instance() -> TestInMemoryArtifactService:
    """Session-scoped artifact service for testing."""
    service = TestInMemoryArtifactService()
    print("[SessionFixture] TestInMemoryArtifactService instance created for session.")
    yield service
    print("[SessionFixture] TestInMemoryArtifactService session ended.")


@pytest.fixture(autouse=True, scope="function")
async def clear_test_artifact_service_between_tests(
    test_artifact_service_instance: TestInMemoryArtifactService,
):
    """Clear artifact service state between tests."""
    yield
    await test_artifact_service_instance.clear_all_artifacts()


@pytest.fixture(scope="session")
async def event_mesh_test_server():
    """
    Session-scoped Event Mesh Test Server fixture.
    Provides a test Solace broker for Event Mesh Gateway testing.
    """
    broker_config = BrokerConfig(
        host="127.0.0.1",
        vpn="test_event_mesh_vpn",
        username="test_event_mesh_user",
        password="test_event_mesh_password",
        client_name="event_mesh_test_client"
    )
    
    server = EventMeshTestServer(broker_config)
    await server.start()
    
    print(f"EventMeshTestServer started on {server.broker_url}")
    yield server
    
    print("EventMeshTestServer: Stopping server...")
    await server.stop()
    print("EventMeshTestServer: Server stopped.")


@pytest.fixture(autouse=True, scope="function")
def clear_event_mesh_server_state(event_mesh_test_server: EventMeshTestServer):
    """Clear event mesh server state between tests."""
    yield
    event_mesh_test_server.clear_received_messages()
    event_mesh_test_server.dev_broker.clear_captured_messages()


@pytest.fixture(scope="session")
def session_monkeypatch():
    """A session-scoped monkeypatch object."""
    mp = pytest.MonkeyPatch()
    print("[SessionFixture] Session-scoped monkeypatch created.")
    yield mp
    print("[SessionFixture] Session-scoped monkeypatch undoing changes.")
    mp.undo()


@pytest.fixture(scope="session")
def shared_solace_connector(
    test_llm_server: TestLLMServer,
    test_artifact_service_instance: TestInMemoryArtifactService,
    event_mesh_test_server: EventMeshTestServer,
    session_monkeypatch,
    request,
) -> SolaceAiConnector:
    """
    Creates and manages a SolaceAiConnector with Event Mesh Gateway and test agents.
    """
    
    def create_agent_config(
        agent_name: str,
        description: str,
        allow_list: list,
        tools: list,
        model_suffix: str,
        session_behavior: str = "RUN_BASED",
    ):
        return {
            "namespace": "test_event_mesh_namespace",
            "supports_streaming": True,
            "agent_name": agent_name,
            "model": {
                "model": f"openai/test-model-{model_suffix}-{time.time_ns()}",
                "api_base": f"{test_llm_server.url}/v1",
                "api_key": f"fake_test_key_{model_suffix}",
            },
            "session_service": {"type": "memory", "default_behavior": session_behavior},
            "artifact_service": {"type": "test_in_memory"},
            "memory_service": {"type": "memory"},
            "agent_card": {
                "description": description,
                "defaultInputModes": ["text"],
                "defaultOutputModes": ["text"],
                "jsonrpc": "2.0",
                "id": "agent_card_pub",
            },
            "agent_card_publishing": {"interval_seconds": 1},
            "agent_discovery": {"enabled": True},
            "inter_agent_communication": {
                "allow_list": allow_list,
                "request_timeout_seconds": 5,
            },
            "tool_output_save_threshold_bytes": 50,
            "tool_output_llm_return_max_bytes": 200,
            "tools": tools,
        }

    # Test agent configuration
    test_agent_tools = [
        {"tool_type": "builtin-group", "group_name": "artifact_management"},
        {"tool_type": "builtin-group", "group_name": "data_analysis"},
        {"tool_type": "builtin", "tool_name": "web_request"},
    ]
    
    test_agent_config = create_agent_config(
        agent_name="TestEventMeshAgent",
        description="Test agent for Event Mesh Gateway testing",
        allow_list=[],
        tools=test_agent_tools,
        model_suffix="event_mesh_test",
    )

    # Event Mesh Gateway configuration
    event_mesh_gateway_config = {
        "namespace": "test_event_mesh_namespace",
        "gateway_id": "TestEventMeshGateway_01",
        "artifact_service": {"type": "test_in_memory"},
        "event_mesh_broker_config": {
            **event_mesh_test_server.sac_config,
            "test_mode": True  # Disable real broker connections in test mode
        },
        "event_handlers": [
            {
                "name": "test_event_handler",
                "subscriptions": [
                    {"topic": "test/events/>", "qos": 1}
                ],
                "input_expression": "input.payload:message",
                "target_agent_name": "TestEventMeshAgent",
                "user_identity_expression": "input.user_properties:user_id",
                "forward_context": {
                    "original_topic": "input.topic:"
                },
                "on_success": "test_success_handler",
                "on_error": "test_error_handler",
            }
        ],
        "output_handlers": [
            {
                "name": "test_success_handler",
                "topic_expression": "static:test/responses/basic/sample",
                "payload_expression": "input.payload:text",
                "payload_format": "text",
            },
            {
                "name": "test_error_handler",
                "topic_expression": "test/errors/{{user_data.forward_context.original_topic}}",
                "payload_expression": "input.payload.a2a_task_response.error.message",
                "payload_format": "text",
            }
        ],
    }

    app_infos = [
        {
            "name": "TestEventMeshAgent_App",
            "app_config": test_agent_config,
            "broker": {"dev_mode": True},
            "app_module": "solace_agent_mesh.agent.sac.app",
        },
        {
            "name": "TestEventMeshGateway_App",
            "app_config": event_mesh_gateway_config,
            "broker": {"dev_mode": True},
            "app_module": "sam_event_mesh_gateway.app",
        },
    ]

    session_monkeypatch.setattr(
        "solace_agent_mesh.agent.adk.services.TestInMemoryArtifactService",
        lambda: test_artifact_service_instance,
    )

    log_level_str = request.config.getoption("--log-cli-level") or "INFO"

    connector_config = {
        "apps": app_infos,
        "log": {
            "stdout_log_level": log_level_str.upper(),
            "log_file_level": "INFO",
            "enable_trace": False,
        },
    }
    
    print(f"\n[Conftest] Configuring SolaceAiConnector with stdout log level: {log_level_str.upper()}")
    connector = SolaceAiConnector(config=connector_config)
    connector.run()
    
    print(f"shared_solace_connector fixture: Started SolaceAiConnector with apps: {[app['name'] for app in connector_config['apps']]}")

    # Allow time for initialization
    print("shared_solace_connector fixture: Waiting for initialization...")
    time.sleep(3)
    print("shared_solace_connector fixture: Initialization wait complete.")

    yield connector

    print(f"shared_solace_connector fixture: Cleaning up SolaceAiConnector...")
    connector.stop()
    connector.cleanup()
    print(f"shared_solace_connector fixture: SolaceAiConnector cleaned up.")


@pytest.fixture(scope="session")
def event_mesh_gateway_app(shared_solace_connector: SolaceAiConnector) -> EventMeshGatewayApp:
    """Retrieves the Event Mesh Gateway app instance."""
    app_instance = shared_solace_connector.get_app("TestEventMeshGateway_App")
    assert isinstance(app_instance, EventMeshGatewayApp), "Failed to retrieve EventMeshGatewayApp."
    print(f"event_mesh_gateway_app fixture: Retrieved app {app_instance.name} from shared SolaceAiConnector.")
    yield app_instance


@pytest.fixture(scope="session")
def test_agent_app(shared_solace_connector: SolaceAiConnector) -> SamAgentApp:
    """Retrieves the test agent app instance."""
    app_instance = shared_solace_connector.get_app("TestEventMeshAgent_App")
    assert isinstance(app_instance, SamAgentApp), "Failed to retrieve TestEventMeshAgent_App."
    yield app_instance


def get_gateway_component_from_app(app: EventMeshGatewayApp) -> EventMeshGatewayComponent:
    """Helper to get the gateway component from an app."""
    if app.flows and app.flows[0].component_groups:
        for group in app.flows[0].component_groups:
            for component_wrapper in group:
                component = (
                    component_wrapper.component
                    if hasattr(component_wrapper, "component")
                    else component_wrapper
                )
                if isinstance(component, EventMeshGatewayComponent):
                    return component
    raise RuntimeError("EventMeshGatewayComponent not found in the application flow.")


def get_agent_component_from_app(app: SamAgentApp) -> SamAgentComponent:
    """Helper to get the agent component from an app."""
    if app.flows and app.flows[0].component_groups:
        for group in app.flows[0].component_groups:
            for component_wrapper in group:
                component = (
                    component_wrapper.component
                    if hasattr(component_wrapper, "component")
                    else component_wrapper
                )
                if isinstance(component, SamAgentComponent):
                    return component
    raise RuntimeError("SamAgentComponent not found in the application flow.")


@pytest.fixture(scope="session")
def event_mesh_gateway_component(event_mesh_gateway_app: EventMeshGatewayApp) -> EventMeshGatewayComponent:
    """Retrieves the Event Mesh Gateway component instance."""
    return get_gateway_component_from_app(event_mesh_gateway_app)


@pytest.fixture(scope="session")
def test_agent_component(test_agent_app: SamAgentApp) -> SamAgentComponent:
    """Retrieves the test agent component instance."""
    return get_agent_component_from_app(test_agent_app)


@pytest.fixture(autouse=True, scope="function")
def clear_gateway_state_between_tests(event_mesh_gateway_component: EventMeshGatewayComponent):
    """Clear gateway component state between tests."""
    yield
    # Clear any gateway-specific state if needed
    pass


@pytest.fixture(autouse=True, scope="function")
def clear_agent_state_between_tests(test_agent_component: SamAgentComponent):
    """Clear agent component state between tests."""
    yield
    # Clear agent state
    with test_agent_component.active_tasks_lock:
        test_agent_component.active_tasks.clear()


@pytest.fixture(scope="function")
def test_config_builder():
    """Provides a configuration builder for dynamic test configurations."""
    
    class TestConfigBuilder:
        def __init__(self):
            self.base_config = {
                "namespace": "test_event_mesh_namespace",
                "gateway_id": "TestEventMeshGateway_Dynamic",
                "artifact_service": {"type": "test_in_memory"},
            }
        
        def with_event_handler(self, name: str, subscriptions: list, **kwargs) -> "TestConfigBuilder":
            if "event_handlers" not in self.base_config:
                self.base_config["event_handlers"] = []
            
            handler_config = {
                "name": name,
                "subscriptions": subscriptions,
                **kwargs
            }
            self.base_config["event_handlers"].append(handler_config)
            return self
        
        def with_output_handler(self, name: str, **kwargs) -> "TestConfigBuilder":
            if "output_handlers" not in self.base_config:
                self.base_config["output_handlers"] = []
            
            handler_config = {
                "name": name,
                **kwargs
            }
            self.base_config["output_handlers"].append(handler_config)
            return self
        
        def with_broker_config(self, broker_config: Dict[str, Any]) -> "TestConfigBuilder":
            self.base_config["event_mesh_broker_config"] = broker_config
            return self
        
        def build(self) -> Dict[str, Any]:
            return self.base_config.copy()
    
    return TestConfigBuilder()
