"""
HTTP test helper utilities for REST Gateway testing.
"""

import json
import base64
from typing import Dict, Any, List, Optional, Union
from fastapi.testclient import TestClient
import io


class HTTPTestHelper:
    """
    Helper class for HTTP testing operations.
    """

    @staticmethod
    def create_file_upload(
        filename: str,
        content: Union[str, bytes],
        mime_type: str = "text/plain"
    ) -> tuple:
        """
        Create a file upload tuple for FastAPI TestClient.
        
        Args:
            filename: Name of the file
            content: File content (string or bytes)
            mime_type: MIME type of the file
            
        Returns:
            Tuple suitable for FastAPI TestClient files parameter
        """
        if isinstance(content, str):
            content = content.encode("utf-8")
        
        return ("files", (filename, io.BytesIO(content), mime_type))

    @staticmethod
    def create_multipart_data(
        form_fields: Dict[str, Any],
        files: List[Dict[str, Any]]
    ) -> tuple:
        """
        Create multipart form data for testing.
        
        Args:
            form_fields: Dictionary of form field names and values
            files: List of file specifications with filename, content, mime_type
            
        Returns:
            Tuple of (form_data, files_list) for TestClient
        """
        files_list = []
        for file_spec in files:
            filename = file_spec["filename"]
            content = file_spec.get("content", "")
            mime_type = file_spec.get("mime_type", "text/plain")
            
            if "content_base64" in file_spec:
                content = base64.b64decode(file_spec["content_base64"])
            elif isinstance(content, str):
                content = content.encode("utf-8")
            
            files_list.append(HTTPTestHelper.create_file_upload(filename, content, mime_type))
        
        return form_fields, files_list

    @staticmethod
    def assert_json_response(
        response,
        expected_status: int,
        expected_keys: Optional[List[str]] = None,
        expected_values: Optional[Dict[str, Any]] = None
    ):
        """
        Assert JSON response properties.
        
        Args:
            response: HTTP response object
            expected_status: Expected HTTP status code
            expected_keys: List of keys that should be present in response
            expected_values: Dictionary of key-value pairs to check
        """
        assert response.status_code == expected_status, (
            f"Expected status {expected_status}, got {response.status_code}. "
            f"Response: {response.text}"
        )
        
        if expected_keys or expected_values:
            response_json = response.json()
            
            if expected_keys:
                for key in expected_keys:
                    assert key in response_json, (
                        f"Expected key '{key}' not found in response: {response_json}"
                    )
            
            if expected_values:
                for key, expected_value in expected_values.items():
                    assert key in response_json, (
                        f"Expected key '{key}' not found in response: {response_json}"
                    )
                    actual_value = response_json[key]
                    assert actual_value == expected_value, (
                        f"Expected {key}={expected_value}, got {actual_value}"
                    )

    @staticmethod
    def assert_error_response(
        response,
        expected_status: int,
        expected_error_message: Optional[str] = None
    ):
        """
        Assert error response properties.
        
        Args:
            response: HTTP response object
            expected_status: Expected HTTP status code
            expected_error_message: Expected error message (substring match)
        """
        assert response.status_code == expected_status, (
            f"Expected error status {expected_status}, got {response.status_code}. "
            f"Response: {response.text}"
        )
        
        if expected_error_message:
            response_text = response.text
            assert expected_error_message in response_text, (
                f"Expected error message '{expected_error_message}' not found in response: {response_text}"
            )

    @staticmethod
    def extract_task_id(response) -> Optional[str]:
        """
        Extract task ID from a v2 API response.
        
        Args:
            response: HTTP response object
            
        Returns:
            Task ID if found, None otherwise
        """
        if response.status_code == 202:
            try:
                response_json = response.json()
                return response_json.get("taskId")
            except:
                pass
        return None

    @staticmethod
    def create_auth_headers(token: str) -> Dict[str, str]:
        """
        Create authentication headers.
        
        Args:
            token: Bearer token
            
        Returns:
            Headers dictionary with Authorization header
        """
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def create_test_file_content(size_bytes: int = 1024) -> bytes:
        """
        Create test file content of specified size.
        
        Args:
            size_bytes: Size of content in bytes
            
        Returns:
            Test content as bytes
        """
        content = "Test file content. " * (size_bytes // 18 + 1)
        return content[:size_bytes].encode("utf-8")

    @staticmethod
    def validate_artifact_response(response, expected_filename: str):
        """
        Validate artifact download response.
        
        Args:
            response: HTTP response object
            expected_filename: Expected filename in response
        """
        assert response.status_code == 200, (
            f"Expected status 200 for artifact download, got {response.status_code}"
        )
        
        # Check content-disposition header if present
        content_disposition = response.headers.get("content-disposition")
        if content_disposition and expected_filename:
            assert expected_filename in content_disposition, (
                f"Expected filename '{expected_filename}' not found in content-disposition: {content_disposition}"
            )

    @staticmethod
    def poll_for_completion(
        test_client: TestClient,
        task_id: str,
        max_attempts: int = 10,
        poll_interval: float = 0.5
    ):
        """
        Poll for task completion using v2 API.
        
        Args:
            test_client: FastAPI test client
            task_id: Task ID to poll for
            max_attempts: Maximum number of polling attempts
            poll_interval: Interval between polls in seconds
            
        Returns:
            Final response when task completes or max attempts reached
        """
        import time
        
        for attempt in range(max_attempts):
            if attempt > 0:
                time.sleep(poll_interval)
            
            response = test_client.get(f"/api/v2/tasks/{task_id}")
            
            if response.status_code == 200:
                return response
            elif response.status_code != 202:
                raise AssertionError(
                    f"Unexpected polling response status {response.status_code} on attempt {attempt + 1}"
                )
        
        raise AssertionError(f"Task {task_id} did not complete within {max_attempts} attempts")
