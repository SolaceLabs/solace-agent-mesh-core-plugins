import pytest
import types
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from a2a.types import TextPart

from sam_webhook_gateway.main import app
from sam_webhook_gateway.component import WebhookGatewayComponent
from sam_webhook_gateway.dependencies import set_component_instance

# A mock configuration for the webhook endpoints
MOCK_WEBHOOK_ENDPOINTS_CONFIG = [
    {
        "path": "/hooks/test-data-feed",
        "method": "POST",
        "target_agent_name": "test-agent",
        "input_template": "Received data: {{ payload.data }}",
        "auth": {"type": "none"},
        "payload_format": "json",
    }
]


@pytest.fixture(scope="module")
def module_client():
    """
    Module-scoped fixture to set up the FastAPI app and TestClient once.
    """
    # Create a mock of the WebhookGatewayComponent
    mock_component = MagicMock(spec=WebhookGatewayComponent)
    mock_component.get_config.side_effect = lambda key, default: {
        "webhook_server_host": "127.0.0.1",
        "webhook_server_port": 8081,
        "cors_allowed_origins": ["*"],
        "webhook_endpoints": MOCK_WEBHOOK_ENDPOINTS_CONFIG,
    }.get(key, default)

    mock_component.log_identifier = "[TestComponent]"
    mock_component.submit_a2a_task = AsyncMock(return_value="test-task-id")
    mock_component.authenticate_and_enrich_user = AsyncMock(
        return_value={"id": "test-user"}
    )
    mock_component.shared_artifact_service = None
    mock_component.cors_allowed_origins = ["*"]
    mock_component.webhook_endpoints_config = MOCK_WEBHOOK_ENDPOINTS_CONFIG

    # Set the mock component instance for dependency injection
    set_component_instance(mock_component)

    # Simulate the component startup process to register routes
    from sam_webhook_gateway.main import setup_dependencies
    setup_dependencies(mock_component)

    # The _create_webhook_handler method creates a closure (dynamic_handler)
    # that captures the component instance (`self`). We need to use the real
    # method but have it operate on our mock_component.
    mock_component._create_webhook_handler = types.MethodType(
        WebhookGatewayComponent._create_webhook_handler, mock_component
    )

    # The dynamic_handler created by _create_webhook_handler calls _translate_external_input.
    # We need to mock this on our component.
    mock_component._translate_external_input = AsyncMock(
        return_value=(
            "test-agent",
            [TextPart(text="Received data: This is a test")],
            {"some": "context"},
        )
    )

    # Add the routes to the app
    for endpoint_config in MOCK_WEBHOOK_ENDPOINTS_CONFIG:
        handler = mock_component._create_webhook_handler(endpoint_config)
        app.add_api_route(
            endpoint_config["path"],
            handler,
            methods=[endpoint_config["method"]],
        )

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(module_client: TestClient):
    """
    Function-scoped fixture that provides the TestClient and resets mocks.
    """
    from sam_webhook_gateway.dependencies import get_sac_component

    mock_component = get_sac_component()
    mock_component.submit_a2a_task.reset_mock()
    mock_component._translate_external_input.reset_mock()
    yield module_client


def test_health_check(module_client: TestClient):
    """
    Tests the /health endpoint.
    """
    # This test doesn't involve mocks that need resetting,
    # so it can use the module-scoped client directly for efficiency.
    response = module_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "Universal Webhook Gateway is running"}


def test_webhook_endpoint_success(client: TestClient):
    """
    Tests a successful request to a configured webhook endpoint.
    """
    # The component instance is retrieved from the dependency injection system
    from sam_webhook_gateway.dependencies import get_sac_component

    mock_component = get_sac_component()

    # Make a request to the test endpoint
    response = client.post(
        "/hooks/test-data-feed", json={"data": "This is a test"}
    )

    # Assert the response is correct
    assert response.status_code == 202
    response_json = response.json()
    assert response_json["taskId"] == "test-task-id"
    assert response_json["message"] == "Webhook request received and acknowledged."

    # Assert that the _translate_external_input method was called
    mock_component._translate_external_input.assert_called_once()

    # Assert that the submit_a2a_task method was called with the correct arguments
    mock_component.submit_a2a_task.assert_called_once()
    call_args = mock_component.submit_a2a_task.call_args[1]
    assert call_args["target_agent_name"] == "test-agent"
    # The a2a_parts are now coming from the mocked _translate_external_input
    assert "Received data: This is a test" in str(call_args["a2a_parts"])


def test_webhook_endpoint_not_found(module_client: TestClient):
    """
    Tests a request to a non-existent webhook endpoint.
    """
    # This test also doesn't involve mocks that need resetting.
    response = module_client.post("/hooks/non-existent", json={"data": "test"})
    assert response.status_code == 404
    # When no route is found, FastAPI/Starlette returns a default 404 response.
    # The custom HTTPException handler is not triggered in this case.
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.asyncio
async def test_form_data_with_file_upload():
    """
    Tests translation of a form-data payload including a file upload.
    This should trigger artifact creation.
    """
    from fastapi import UploadFile

    # 1. Setup a mock component
    mock_component = MagicMock(spec=WebhookGatewayComponent)
    mock_component.log_identifier = "[TestComponent]"
    mock_component.gateway_id = "test-gateway"
    mock_component._save_file_as_artifact = AsyncMock(
        return_value="artifact://test-gateway/user-3/session-123/test.txt?version=0"
    )
    # Bind the real method to our mock component instance
    mock_component._translate_external_input = types.MethodType(
        WebhookGatewayComponent._translate_external_input, mock_component
    )

    # 2. Mock the incoming request and its form data
    mock_upload_file = MagicMock(spec=UploadFile)
    mock_upload_file.filename = "test.txt"
    mock_upload_file.content_type = "text/plain"
    mock_upload_file.read = AsyncMock(return_value=b"Hello, artifact!")
    mock_upload_file.close = AsyncMock()

    mock_form_data = {"text_field": "some value", "file_upload": mock_upload_file}

    mock_request = MagicMock()
    mock_request.form = AsyncMock(return_value=mock_form_data)
    mock_request.body = AsyncMock(return_value=b"") # Body is not read directly for form-data
    mock_request.url.path = "/upload"
    mock_request.query_params = {}
    mock_request.headers = {"Content-Type": "multipart/form-data"}
    mock_request.client.host = "127.0.0.1"


    # 3. Define the endpoint configuration
    endpoint_config = {
        "target_agent_name": "agent-3",
        "input_template": "Uploaded file '{{text://user_data.uploaded_files:0.filename}}' with content from field '{{text://input.payload:text_field}}'. URI: {{text://user_data.uploaded_files:0.uri}}",
        "payload_format": "form_data",
    }
    user_identity = {"id": "user-3"}

    # 4. Call the method under test
    _, parts, _ = await mock_component._translate_external_input(
        mock_request, endpoint_config, user_identity
    )

    # 5. Assert the results
    mock_component._save_file_as_artifact.assert_called_once()
    save_args = mock_component._save_file_as_artifact.call_args[1]
    assert save_args["filename"] == "test.txt"
    assert save_args["content_bytes"] == b"Hello, artifact!"
    assert save_args["mime_type"] == "text/plain"

    assert len(parts) == 1
    expected_text = "Uploaded file 'test.txt' with content from field 'some value'. URI: artifact://test-gateway/user-3/session-123/test.txt?version=0"
    assert parts[0].text == expected_text
