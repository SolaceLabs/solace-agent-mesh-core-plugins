"""
Pytest configuration and fixtures for REST Gateway integration tests.
"""

import pytest
import time
import asyncio
from typing import Dict, Any

from solace_ai_connector.solace_ai_connector import SolaceAiConnector
from sam_test_infrastructure.llm_server.server import TestLLMServer
from sam_test_infrastructure.artifact_service.service import TestInMemoryArtifactService
from sam_test_infrastructure.a2a_validator.validator import A2AMessageValidator

from sam_rest_gateway.app import RestGatewayApp
from sam_rest_gateway.component import RestGatewayComponent
from tests.integration.test_support.rest_gateway_test_component import (
    RestGatewayTestComponent,
)
from tests.integration.test_support.mock_auth_server import MockAuthServer


@pytest.fixture
def mock_gemini_client(monkeypatch):
    """
    Mocks the google.genai.Client and PIL.Image.open to prevent real API calls
    and allow for deterministic testing.
    """

    class MockPILImage:
        def __init__(self):
            self.size = (1, 1)
            self.mode = "RGB"

        def split(self):
            return []

        def save(self, fp, format=None, quality=None):
            fp.write(b"mock_image_bytes")

    def mock_open(fp):
        return MockPILImage()

    try:
        from PIL import Image

        monkeypatch.setattr(Image, "open", mock_open)
    except ImportError:
        pass

    class MockPart:
        def __init__(self, text=None, inline_data=None):
            self.text = text
            self.inline_data = inline_data

    class MockContent:
        def __init__(self, parts):
            self.parts = parts

    class MockCandidate:
        def __init__(self, content):
            self.content = content

    class MockGenerateContentResponse:
        def __init__(self, candidates):
            self.candidates = candidates

    class MockGeminiClient:
        def __init__(self, api_key=None):
            self._api_key = api_key
            self.models = self

        def generate_content(self, model, contents, config):
            if self._api_key != "fake-gemini-api-key":
                raise Exception(
                    "400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. Please pass a valid API key.'}}"
                )

            edited_image_bytes = b"edited_image_bytes"
            mock_response = MockGenerateContentResponse(
                candidates=[
                    MockCandidate(
                        content=MockContent(
                            parts=[
                                MockPart(text="Image edited successfully."),
                                MockPart(
                                    inline_data=type(
                                        "obj", (object,), {"data": edited_image_bytes}
                                    )()
                                ),
                            ]
                        )
                    )
                ]
            )
            return mock_response

    monkeypatch.setattr("google.genai.Client", MockGeminiClient)


@pytest.fixture(scope="session")
def test_llm_server():
    """
    Manages the lifecycle of the TestLLMServer for the test session.
    """
    server = TestLLMServer(
        host="127.0.0.1", port=8089
    )  # Different port from main tests
    server.start()

    max_retries = 20
    retry_delay = 0.25
    ready = False
    for i in range(max_retries):
        time.sleep(retry_delay)
        try:
            if server.started:
                print(
                    f"REST Gateway TestLLMServer confirmed started after {i+1} attempts."
                )
                ready = True
                break
            print(
                f"REST Gateway TestLLMServer not ready yet (attempt {i+1}/{max_retries})..."
            )
        except Exception as e:
            print(
                f"REST Gateway TestLLMServer readiness check (attempt {i+1}/{max_retries}) encountered an error: {e}"
            )

    if not ready:
        try:
            server.stop()
        except Exception:
            pass
        pytest.fail("REST Gateway TestLLMServer did not become ready in time.")

    print(f"REST Gateway TestLLMServer fixture: Server ready at {server.url}")
    yield server

    print("REST Gateway TestLLMServer fixture: Stopping server...")
    server.stop()
    print("REST Gateway TestLLMServer fixture: Server stopped.")


@pytest.fixture(autouse=True)
def clear_llm_server_configs(test_llm_server: TestLLMServer):
    """
    Automatically clears any primed responses and captured requests from the
    TestLLMServer before each test.
    """
    test_llm_server.clear_all_configurations()


@pytest.fixture(scope="session")
def test_artifact_service_instance() -> TestInMemoryArtifactService:
    """
    Provides a single instance of TestInMemoryArtifactService for the test session.
    """
    service = TestInMemoryArtifactService()
    print(
        "[REST Gateway SessionFixture] TestInMemoryArtifactService instance created for session."
    )
    yield service
    print("[REST Gateway SessionFixture] TestInMemoryArtifactService session ended.")


@pytest.fixture(autouse=True, scope="function")
async def clear_test_artifact_service_between_tests(
    test_artifact_service_instance: TestInMemoryArtifactService,
):
    """
    Clears all artifacts from the session-scoped TestInMemoryArtifactService after each test.
    """
    yield
    await test_artifact_service_instance.clear_all_artifacts()


@pytest.fixture(scope="session")
def session_monkeypatch():
    """A session-scoped monkeypatch object."""
    mp = pytest.MonkeyPatch()
    print("[REST Gateway SessionFixture] Session-scoped monkeypatch created.")
    yield mp
    print("[REST Gateway SessionFixture] Session-scoped monkeypatch undoing changes.")
    mp.undo()


@pytest.fixture(scope="session")
def mock_auth_server():
    """
    Manages the lifecycle of the MockAuthServer for the test session.
    """
    server = MockAuthServer(host="127.0.0.1", port=8090)
    server.start()

    print(f"Mock Auth Server fixture: Server ready at {server.url}")
    yield server

    print("Mock Auth Server fixture: Stopping server...")
    server.stop()
    print("Mock Auth Server fixture: Server stopped.")


@pytest.fixture(autouse=True)
def clear_auth_server_tokens(mock_auth_server: MockAuthServer):
    """
    Automatically clears any custom test tokens from the MockAuthServer before each test.
    """
    yield
    mock_auth_server.clear_test_tokens()


@pytest.fixture
def auth_tokens(mock_auth_server: MockAuthServer):
    """
    Provides test authentication tokens for use in tests.
    """
    return mock_auth_server.get_test_tokens()


@pytest.fixture
def test_users(mock_auth_server: MockAuthServer):
    """
    Provides test user profiles for use in tests.
    """
    return mock_auth_server.get_test_users()


@pytest.fixture(scope="session")
def shared_solace_connector(
    test_llm_server: TestLLMServer,
    test_artifact_service_instance: TestInMemoryArtifactService,
    mock_auth_server: MockAuthServer,
    session_monkeypatch,
    request,
) -> SolaceAiConnector:
    """
    Creates and manages a single SolaceAiConnector instance with REST Gateway and test agents.
    """

    def create_agent_config(agent_name, description, tools, model_suffix):
        return {
            "namespace": "test_namespace",
            "supports_streaming": True,
            "agent_name": agent_name,
            "model": {
                "model": f"openai/test-model-{model_suffix}-{time.time_ns()}",
                "api_base": f"{test_llm_server.url}/v1",
                "api_key": f"fake_test_key_{model_suffix}",
            },
            "session_service": {"type": "memory", "default_behavior": "RUN_BASED"},
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
                "allow_list": [],
                "request_timeout_seconds": 5,
            },
            "tool_output_save_threshold_bytes": 50,
            "tool_output_llm_return_max_bytes": 200,
            "tools": tools,
        }

    # Test agent configuration
    test_agent_tools = [
        {"tool_type": "builtin-group", "group_name": "artifact_management"},
        {"tool_type": "builtin-group", "group_name": "test"},
    ]

    test_agent_config = create_agent_config(
        agent_name="TestAgent",
        description="Test agent for REST Gateway testing",
        tools=test_agent_tools,
        model_suffix="rest_test",
    )

    # REST Gateway configuration with production authentication
    rest_gateway_config = {
        "namespace": "test_namespace",
        "gateway_id": "TestRestGateway",
        "artifact_service": {"type": "test_in_memory"},
        "rest_api_server_host": "127.0.0.1",
        "rest_api_server_port": 8081,  # Different port to avoid conflicts
        # Production Authentication Settings
        "enforce_authentication": True,
        "external_auth_service_url": mock_auth_server.url,
        "external_auth_service_provider": "azure",
        "sync_mode_timeout_seconds": 30,
    }

    app_infos = [
        {
            "name": "TestRestGatewayApp",
            "app_config": rest_gateway_config,
            "broker": {"dev_mode": True},
            "app_module": "sam_rest_gateway.app",
        },
        {
            "name": "TestAgentApp",
            "app_config": test_agent_config,
            "broker": {"dev_mode": True},
            "app_module": "solace_agent_mesh.agent.sac.app",
        },
    ]

    # Patch the artifact service
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

    print(
        f"\n[REST Gateway Conftest] Configuring SolaceAiConnector with stdout log level: {log_level_str.upper()}"
    )
    connector = SolaceAiConnector(config=connector_config)
    connector.run()
    print(
        f"REST Gateway shared_solace_connector fixture: Started SolaceAiConnector with apps: {[app['name'] for app in connector_config['apps']]}"
    )

    # Allow time for initialization
    print("REST Gateway shared_solace_connector fixture: Waiting for initialization...")
    time.sleep(3)
    print("REST Gateway shared_solace_connector fixture: Initialization wait complete.")

    yield connector

    print(
        f"REST Gateway shared_solace_connector fixture: Cleaning up SolaceAiConnector..."
    )
    connector.stop()
    connector.cleanup()
    print(
        f"REST Gateway shared_solace_connector fixture: SolaceAiConnector cleaned up."
    )


@pytest.fixture(scope="session")
def rest_gateway_app(shared_solace_connector: SolaceAiConnector) -> RestGatewayApp:
    """
    Retrieves the REST Gateway app instance from the session-scoped SolaceAiConnector.
    """
    app_instance = shared_solace_connector.get_app("TestRestGatewayApp")
    assert isinstance(
        app_instance, RestGatewayApp
    ), "Failed to retrieve RestGatewayApp from shared connector."
    print(
        f"REST Gateway app fixture: Retrieved app {app_instance.name} from shared SolaceAiConnector."
    )
    yield app_instance


@pytest.fixture(scope="session")
def test_rest_gateway(
    rest_gateway_app: RestGatewayApp,
    test_artifact_service_instance: TestInMemoryArtifactService,
    test_llm_server: TestLLMServer,
) -> RestGatewayTestComponent:
    """
    Creates a REST Gateway test component for making HTTP requests.
    """
    test_component = RestGatewayTestComponent(
        rest_gateway_app=rest_gateway_app,
        test_artifact_service=test_artifact_service_instance,
        test_llm_server=test_llm_server,
    )

    print(
        f"[REST Gateway SessionFixture] RestGatewayTestComponent instance created for session."
    )
    yield test_component
    print(f"[REST Gateway SessionFixture] RestGatewayTestComponent session ended.")


@pytest.fixture(autouse=True, scope="function")
def clear_rest_gateway_state_between_tests(
    test_rest_gateway: RestGatewayTestComponent,
):
    """
    Clears state from the session-scoped RestGatewayTestComponent after each test.
    """
    yield
    test_rest_gateway.clear_captured_outputs()


@pytest.fixture(scope="function")
def a2a_message_validator(
    rest_gateway_app: RestGatewayApp,
    shared_solace_connector: SolaceAiConnector,
) -> A2AMessageValidator:
    """
    Provides an instance of A2AMessageValidator for REST Gateway tests.
    """
    validator = A2AMessageValidator()

    # Get the REST gateway component
    rest_gateway_component = None
    if rest_gateway_app.flows and rest_gateway_app.flows[0].component_groups:
        for group in rest_gateway_app.flows[0].component_groups:
            for comp_wrapper in group:
                actual_comp = getattr(comp_wrapper, "component", comp_wrapper)
                if isinstance(actual_comp, RestGatewayComponent):
                    rest_gateway_component = actual_comp
                    break

    # Get the test agent component
    test_agent_app = shared_solace_connector.get_app("TestAgentApp")
    test_agent_component = None
    if (
        test_agent_app
        and test_agent_app.flows
        and test_agent_app.flows[0].component_groups
    ):
        for group in test_agent_app.flows[0].component_groups:
            for comp_wrapper in group:
                actual_comp = getattr(comp_wrapper, "component", comp_wrapper)
                if hasattr(actual_comp, "agent_name"):  # SamAgentComponent
                    test_agent_component = actual_comp
                    break

    components_to_patch = [
        comp
        for comp in [rest_gateway_component, test_agent_component]
        if comp is not None
    ]

    if not components_to_patch:
        pytest.skip("No suitable components found to patch for A2A validation.")

    print(
        f"REST Gateway A2A Validator activating on components: {[getattr(c, 'name', str(c)) for c in components_to_patch]}"
    )
    validator.activate(components_to_patch)
    yield validator
    validator.deactivate()
