"""
Pytest configuration and fixtures for Event Mesh Gateway unit tests.

These fixtures provide lightweight mocks that don't require the full broker setup.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from typing import Dict, Any, Optional


class MockArtifactService:
    """In-memory artifact service for testing."""

    def __init__(self):
        self.storage: Dict[str, Dict[int, bytes]] = {}
        self.metadata_storage: Dict[str, Dict[int, Dict]] = {}
        self._version_counters: Dict[str, int] = {}

    async def save_artifact(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        filename: str,
        content_bytes: bytes,
        mime_type: str = "application/octet-stream",
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Save an artifact and return version info."""
        key = f"{app_name}/{user_id}/{session_id}/{filename}"
        if key not in self._version_counters:
            self._version_counters[key] = 0
            self.storage[key] = {}
            self.metadata_storage[key] = {}

        self._version_counters[key] += 1
        version = self._version_counters[key]
        self.storage[key][version] = content_bytes
        self.metadata_storage[key][version] = {
            "mime_type": mime_type,
            "metadata": metadata or {},
        }

        return {
            "status": "success",
            "data_version": version,
        }

    async def load_artifact(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        filename: str,
        version: int = 0,
    ) -> Dict[str, Any]:
        """Load an artifact by key and version."""
        key = f"{app_name}/{user_id}/{session_id}/{filename}"
        if key not in self.storage:
            return {"status": "error", "message": "Artifact not found"}

        versions = self.storage[key]
        if version == 0:
            # Get latest version
            version = max(versions.keys())

        if version not in versions:
            return {"status": "error", "message": f"Version {version} not found"}

        return {
            "status": "success",
            "raw_bytes": versions[version],
            "metadata": self.metadata_storage[key].get(version, {}),
        }

    async def clear_all_artifacts(self):
        """Clear all stored artifacts."""
        self.storage.clear()
        self.metadata_storage.clear()
        self._version_counters.clear()


@pytest.fixture
def mock_artifact_service():
    """Provide a mock artifact service for testing."""
    return MockArtifactService()


@pytest.fixture
def mock_gateway_component():
    """Create a mock gateway component with key methods."""
    from sam_event_mesh_gateway.component import EventMeshGatewayComponent

    component = MagicMock(spec=EventMeshGatewayComponent)
    component.log_identifier = "[TestGateway]"
    component.gateway_id = "TestGateway"

    # Bind real methods to mock
    component._resolve_target_name = EventMeshGatewayComponent._resolve_target_name.__get__(
        component, EventMeshGatewayComponent
    )
    component._get_format_info = EventMeshGatewayComponent._get_format_info.__get__(
        component, EventMeshGatewayComponent
    )
    component._serialize_for_format = EventMeshGatewayComponent._serialize_for_format.__get__(
        component, EventMeshGatewayComponent
    )

    return component


@pytest.fixture
def sample_handler_config():
    """Sample event handler configuration for testing."""
    return {
        "name": "test_handler",
        "subscriptions": [{"topic": "test/events/>", "qos": 1}],
        "input_expression": "input.payload",
        "target_agent_name": "TestAgent",
    }


@pytest.fixture
def sample_structured_handler_config():
    """Sample structured invocation handler configuration."""
    return {
        "name": "structured_handler",
        "subscriptions": [{"topic": "test/structured/>", "qos": 1}],
        "input_expression": "input.payload",
        "target_workflow_name": "TestWorkflow",
        "payload_format": "json",
    }


@pytest.fixture
def sample_structured_agent_handler_config():
    """Sample structured invocation handler with agent and schemas."""
    return {
        "name": "structured_agent_handler",
        "subscriptions": [{"topic": "test/structured/agent/>", "qos": 1}],
        "input_expression": "input.payload",
        "target_agent_name": "TestAgent",
        "structured_invocation": {
            "input_schema": {
                "type": "object",
                "properties": {"data": {"type": "array"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {"result": {"type": "object"}},
            },
        },
        "payload_format": "json",
    }


@pytest.fixture
def sample_user_identity():
    """Sample user identity for testing."""
    return {
        "id": "test_user_123",
        "name": "Test User",
        "email": "test@example.com",
    }


@pytest.fixture
def sample_task_data():
    """Sample A2A Task data for response testing."""
    from a2a.types import Task, TaskStatus, TaskState, Message, TextPart, Part

    return Task(
        id="test_task_123",
        status=TaskStatus(
            state=TaskState.completed,
            message=Message(
                messageId="msg_123",
                role="assistant",
                parts=[Part(root=TextPart(text="Task completed successfully"))],
            ),
        ),
    )


@pytest.fixture
def sample_structured_task_data():
    """Sample A2A Task data with structured invocation result."""
    from a2a.types import Task, TaskStatus, TaskState, Message, TextPart, DataPart, Part

    structured_result = {
        "type": "structured_invocation_result",
        "status": "success",
        "output_artifact_ref": {"name": "output.json", "version": 1},
    }

    return Task(
        id="test_task_structured",
        status=TaskStatus(
            state=TaskState.completed,
            message=Message(
                messageId="msg_structured",
                role="assistant",
                parts=[
                    Part(root=DataPart(data=structured_result)),
                    Part(root=TextPart(text="Structured invocation completed")),
                ],
            ),
        ),
    )


@pytest.fixture
def sample_error_task_data():
    """Sample A2A Task data with structured invocation error."""
    from a2a.types import Task, TaskStatus, TaskState, Message, DataPart, Part

    error_result = {
        "type": "structured_invocation_result",
        "status": "error",
        "error_message": "Validation failed: missing required field",
        "validation_errors": ["Missing required field 'name'"],
    }

    return Task(
        id="test_task_error",
        status=TaskStatus(
            state=TaskState.failed,
            message=Message(
                messageId="msg_error",
                role="assistant",
                parts=[Part(root=DataPart(data=error_result))],
            ),
        ),
    )
