"""
Test component for REST Gateway that provides HTTP testing capabilities.
"""

import asyncio
import threading
import time
from typing import Dict, Any, List, Optional, Tuple
from fastapi.testclient import TestClient
from fastapi import UploadFile
import io

from solace_ai_connector.common.log import log
from sam_rest_gateway.app import RestGatewayApp
from sam_rest_gateway.component import RestGatewayComponent


class RestGatewayTestComponent:
    """
    Test component that wraps a REST Gateway for testing purposes.
    Provides HTTP client capabilities for making requests to the gateway.
    """

    def __init__(
        self,
        rest_gateway_app: RestGatewayApp,
        test_artifact_service,
        test_llm_server,
    ):
        self.rest_gateway_app = rest_gateway_app
        self.test_artifact_service = test_artifact_service
        self.test_llm_server = test_llm_server
        
        # Get the actual REST gateway component
        self.rest_gateway_component = self._get_rest_gateway_component()
        
        # Create test client
        self.test_client = None
        self._setup_test_client()

    def _get_rest_gateway_component(self) -> RestGatewayComponent:
        """Extract the RestGatewayComponent from the app."""
        if (
            self.rest_gateway_app.flows
            and self.rest_gateway_app.flows[0].component_groups
        ):
            for group in self.rest_gateway_app.flows[0].component_groups:
                for comp_wrapper in group:
                    actual_comp = getattr(comp_wrapper, "component", comp_wrapper)
                    if isinstance(actual_comp, RestGatewayComponent):
                        return actual_comp
        raise RuntimeError("RestGatewayComponent not found in the application flow.")

    def _setup_test_client(self):
        """Setup the FastAPI test client."""
        # Wait for the FastAPI app to be initialized
        max_wait = 10  # seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                fastapi_app = getattr(self.rest_gateway_component, 'fastapi_app', None)
                if fastapi_app:
                    self.test_client = TestClient(fastapi_app)
                    log.info("REST Gateway test client initialized successfully")
                    return
            except Exception as e:
                log.debug(f"Exception while accessing fastapi_app: {e}")
            time.sleep(0.1)
        
        raise RuntimeError("Failed to initialize REST Gateway test client - FastAPI app not ready")

    async def make_request(
        self,
        method: str,
        endpoint: str,
        form_data: Optional[Dict[str, Any]] = None,
        files: Optional[List[Tuple[str, Tuple[str, io.BytesIO, str]]]] = None,
        headers: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Make an HTTP request to the REST gateway.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            form_data: Form data for POST requests
            files: List of files to upload
            headers: HTTP headers
            query_params: Query parameters
            json_data: JSON data for requests
            
        Returns:
            Response object from the test client
        """
        if not self.test_client:
            raise RuntimeError("Test client not initialized")

        # Prepare request parameters
        request_kwargs = {}
        
        if headers:
            request_kwargs["headers"] = headers
            
        if query_params:
            request_kwargs["params"] = query_params

        # Handle different request types
        if method.upper() == "GET":
            response = self.test_client.get(endpoint, **request_kwargs)
        elif method.upper() == "POST":
            if files or form_data:
                # Multipart form data request
                if form_data:
                    request_kwargs["data"] = form_data
                if files:
                    request_kwargs["files"] = files
                response = self.test_client.post(endpoint, **request_kwargs)
            elif json_data:
                # JSON request
                request_kwargs["json"] = json_data
                response = self.test_client.post(endpoint, **request_kwargs)
            else:
                # Empty POST
                response = self.test_client.post(endpoint, **request_kwargs)
        elif method.upper() == "PUT":
            if json_data:
                request_kwargs["json"] = json_data
            response = self.test_client.put(endpoint, **request_kwargs)
        elif method.upper() == "DELETE":
            response = self.test_client.delete(endpoint, **request_kwargs)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        log.debug(
            f"REST Gateway test request: {method} {endpoint} -> {response.status_code}"
        )
        
        return response

    async def make_authenticated_request(
        self,
        method: str,
        endpoint: str,
        token: Optional[str] = None,
        form_data: Optional[Dict[str, Any]] = None,
        files: Optional[List[Tuple[str, Tuple[str, io.BytesIO, str]]]] = None,
        headers: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Make an HTTP request to the REST gateway with optional Bearer token authentication.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            token: Bearer token for authentication (optional)
            form_data: Form data for POST requests
            files: List of files to upload
            headers: HTTP headers
            query_params: Query parameters
            json_data: JSON data for requests
            
        Returns:
            Response object from the test client
        """
        # Prepare headers with authentication
        auth_headers = headers.copy() if headers else {}
        
        if token:
            auth_headers["Authorization"] = f"Bearer {token}"
            log.debug(f"REST Gateway authenticated request: Adding Bearer token {token[:10]}...")
        
        return await self.make_request(
            method=method,
            endpoint=endpoint,
            form_data=form_data,
            files=files,
            headers=auth_headers,
            query_params=query_params,
            json_data=json_data,
        )

    def clear_captured_outputs(self):
        """Clear any captured outputs for test isolation."""
        # Clear any internal state if needed
        pass

    def get_gateway_id(self) -> str:
        """Get the gateway ID."""
        return getattr(self.rest_gateway_component, 'gateway_id', 'test_rest_gateway')

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value from the REST gateway component."""
        return self.rest_gateway_component.get_config(key, default)
