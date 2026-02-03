"""Unit tests for REST gateway token authentication middleware."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_gateway_token_auth_success():
    """Test successful authentication with gateway token."""
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint(request):
        return {"user": request.state.user}

    mock_component = Mock()
    mock_component.get_config = Mock(side_effect=lambda key, default=None: {
        "enforce_authentication": True,
        "token_hash": "$2b$12$test_hash",
        "default_user_identity": "test-user"
    }.get(key, default))

    with patch("sam_rest_gateway.main.verify_token", return_value=True):
        from sam_rest_gateway.main import setup_dependencies
        setup_dependencies(mock_component)

        client = TestClient(app)
        response = client.get(
            "/test",
            headers={"Authorization": "Bearer valid_token"}
        )

        assert response.status_code == 200


def test_gateway_token_auth_failure():
    """Test failed authentication with invalid gateway token."""
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    mock_component = Mock()
    mock_component.get_config = Mock(side_effect=lambda key, default=None: {
        "enforce_authentication": True,
        "token_hash": "$2b$12$test_hash"
    }.get(key, default))

    with patch("sam_rest_gateway.main.verify_token", return_value=False):
        from sam_rest_gateway.main import setup_dependencies
        setup_dependencies(mock_component)

        client = TestClient(app)
        response = client.get(
            "/test",
            headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401
        assert "Invalid or expired token" in response.json()["detail"]


def test_no_auth_header():
    """Test request without authorization header."""
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    mock_component = Mock()
    mock_component.get_config = Mock(side_effect=lambda key, default=None: {
        "enforce_authentication": True
    }.get(key, default))

    from sam_rest_gateway.main import setup_dependencies
    setup_dependencies(mock_component)

    client = TestClient(app)
    response = client.get("/test")

    assert response.status_code == 401
    assert "Bearer token not provided" in response.json()["detail"]


def test_health_endpoint_no_auth():
    """Test health endpoint bypasses authentication."""
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    mock_component = Mock()
    mock_component.get_config = Mock(side_effect=lambda key, default=None: {
        "enforce_authentication": True,
        "token_hash": "$2b$12$test_hash"
    }.get(key, default))

    from sam_rest_gateway.main import setup_dependencies
    setup_dependencies(mock_component)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
