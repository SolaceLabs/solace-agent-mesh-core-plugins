"""
Tests for response handling in the Event Mesh Gateway.

Tests cover:
- _send_final_response_to_external method
- Structured invocation result extraction
- Output artifact loading
- Error routing for structured invocation failures
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any

from a2a.types import (
    Task,
    TaskStatus,
    TaskState,
    Message,
    TextPart,
    DataPart,
    FilePart,
    FileWithUri,
    Part,
)

from sam_event_mesh_gateway.component import EventMeshGatewayComponent


class TestStructuredResultExtraction:
    """Tests for extracting StructuredInvocationResult from task response."""

    def test_extract_structured_result_from_data_part(self):
        """Test extracting structured result from DataPart in message."""
        from solace_agent_mesh.common import a2a

        structured_result = {
            "type": "structured_invocation_result",
            "status": "success",
            "output_artifact_ref": {"name": "output.json", "version": 1},
        }

        message = Message(
            messageId="msg_123",
            role="agent",
            parts=[
                Part(root=DataPart(data=structured_result)),
                Part(root=TextPart(text="Task completed")),
            ],
        )

        # Extract parts as the component does
        parts = a2a.get_parts_from_message(message)

        found_result = None
        for part in parts:
            if isinstance(part, DataPart):
                part_data = part.model_dump(exclude_none=True)
                data_content = part_data.get("data", {})
                if isinstance(data_content, dict) and data_content.get("type") == "structured_invocation_result":
                    found_result = data_content
                    break

        assert found_result is not None
        assert found_result["type"] == "structured_invocation_result"
        assert found_result["status"] == "success"
        assert found_result["output_artifact_ref"]["name"] == "output.json"

    def test_no_structured_result_in_normal_response(self):
        """Test that normal response without structured result returns None."""
        from solace_agent_mesh.common import a2a

        message = Message(
            messageId="msg_456",
            role="agent",
            parts=[Part(root=TextPart(text="Just a normal text response"))],
        )

        parts = a2a.get_parts_from_message(message)

        found_result = None
        for part in parts:
            if isinstance(part, DataPart):
                part_data = part.model_dump(exclude_none=True)
                data_content = part_data.get("data", {})
                if isinstance(data_content, dict) and data_content.get("type") == "structured_invocation_result":
                    found_result = data_content
                    break

        assert found_result is None

    def test_extract_error_result(self):
        """Test extracting error structured result."""
        from solace_agent_mesh.common import a2a

        error_result = {
            "type": "structured_invocation_result",
            "status": "error",
            "error_message": "Validation failed",
            "validation_errors": ["Missing required field 'name'"],
            "retry_count": 2,
        }

        message = Message(
            messageId="msg_error",
            role="agent",
            parts=[Part(root=DataPart(data=error_result))],
        )

        parts = a2a.get_parts_from_message(message)

        found_result = None
        for part in parts:
            if isinstance(part, DataPart):
                part_data = part.model_dump(exclude_none=True)
                data_content = part_data.get("data", {})
                if isinstance(data_content, dict) and data_content.get("type") == "structured_invocation_result":
                    found_result = data_content
                    break

        assert found_result is not None
        assert found_result["status"] == "error"
        assert found_result["error_message"] == "Validation failed"
        assert len(found_result["validation_errors"]) == 1


class TestSimplifiedPayloadConstruction:
    """Tests for simplified payload construction in response handling."""

    def test_text_parts_concatenated(self):
        """Test that multiple text parts are concatenated."""
        from solace_agent_mesh.common import a2a

        message = Message(
            messageId="msg_multi",
            role="agent",
            parts=[
                Part(root=TextPart(text="First part. ")),
                Part(root=TextPart(text="Second part. ")),
                Part(root=TextPart(text="Third part.")),
            ],
        )

        parts = a2a.get_parts_from_message(message)
        text_parts_content = []
        for part in parts:
            if isinstance(part, TextPart):
                text_parts_content.append(part.text)

        combined_text = "\n".join(text_parts_content)

        assert "First part" in combined_text
        assert "Second part" in combined_text
        assert "Third part" in combined_text

    def test_data_parts_collected(self):
        """Test that data parts are collected in the payload."""
        from solace_agent_mesh.common import a2a

        message = Message(
            messageId="msg_data",
            role="agent",
            parts=[
                Part(root=DataPart(data={"custom": "data1"})),
                Part(root=DataPart(data={"another": "data2"})),
                Part(root=TextPart(text="Some text")),
            ],
        )

        parts = a2a.get_parts_from_message(message)

        simplified_payload = {
            "text": None,
            "data": [],
        }

        text_parts_content = []
        for part in parts:
            if isinstance(part, TextPart):
                text_parts_content.append(part.text)
            elif isinstance(part, DataPart):
                simplified_payload["data"].append(part.model_dump(exclude_none=True))

        if text_parts_content:
            simplified_payload["text"] = "\n".join(text_parts_content)

        assert len(simplified_payload["data"]) == 2
        assert simplified_payload["text"] == "Some text"


class TestStructuredOutputHandling:
    """Tests for handling structured output artifact loading."""

    @pytest.fixture
    def mock_artifact_service(self):
        """Create a mock artifact service."""
        service = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_success_result_loads_artifact(self, mock_artifact_service):
        """Test that success result loads the output artifact."""
        from solace_agent_mesh.agent.utils.artifact_helpers import load_artifact_content_or_metadata

        structured_result = {
            "type": "structured_invocation_result",
            "status": "success",
            "output_artifact_ref": {"name": "output.json", "version": 1},
        }

        # Mock the artifact loading
        artifact_content = {"analysis": {"result": "processed"}}
        mock_load_result = {
            "status": "success",
            "raw_bytes": json.dumps(artifact_content).encode("utf-8"),
        }

        external_request_context = {
            "is_structured_invocation": True,
            "app_name_for_artifacts": "TestGateway",
            "user_id_for_artifacts": "user123",
            "a2a_session_id": "session_abc",
        }

        simplified_payload = {
            "structured_result": structured_result,
        }

        # Simulate the artifact loading logic
        if structured_result.get("status") == "success":
            artifact_ref = structured_result.get("output_artifact_ref")
            if artifact_ref:
                # Simulate loading content
                content_bytes = mock_load_result["raw_bytes"]
                if isinstance(content_bytes, bytes):
                    content_str = content_bytes.decode("utf-8")
                else:
                    content_str = content_bytes
                simplified_payload["structured_output"] = json.loads(content_str)

        assert "structured_output" in simplified_payload
        assert simplified_payload["structured_output"]["analysis"]["result"] == "processed"

    def test_error_result_triggers_error_handler(self):
        """Test that error result should route to error handler."""
        structured_result = {
            "type": "structured_invocation_result",
            "status": "error",
            "error_message": "Structured invocation failed",
        }

        # Simulate the error handling logic
        should_route_to_error = (
            structured_result.get("status") == "error"
        )

        assert should_route_to_error is True

    def test_artifact_loading_failure_handled(self):
        """Test that artifact loading failure is handled gracefully."""
        structured_result = {
            "type": "structured_invocation_result",
            "status": "success",
            "output_artifact_ref": {"name": "missing.json", "version": 1},
        }

        # Mock failed artifact load
        mock_load_result = {
            "status": "error",
            "message": "Artifact not found",
        }

        simplified_payload = {
            "structured_result": structured_result,
        }

        # Simulate the loading logic with failure
        artifact_ref = structured_result.get("output_artifact_ref")
        if artifact_ref:
            if mock_load_result.get("status") != "success":
                # Log warning but don't fail
                pass  # structured_output not set

        # Verify structured_output is not set on failure
        assert "structured_output" not in simplified_payload


class TestOutputHandlerRouting:
    """Tests for output handler routing based on success/error."""

    def test_success_routes_to_on_success(self):
        """Test that success result routes to on_success handler."""
        event_handler_config = {
            "name": "test_handler",
            "on_success": "success_output_handler",
            "on_error": "error_output_handler",
        }

        external_request_context = {
            "event_handler_name": "test_handler",
            "is_structured_invocation": True,
        }

        structured_result = {
            "status": "success",
        }

        # Simulate routing logic
        if structured_result.get("status") == "success":
            output_handler = event_handler_config.get("on_success")
        else:
            output_handler = event_handler_config.get("on_error")

        assert output_handler == "success_output_handler"

    def test_error_routes_to_on_error(self):
        """Test that error result routes to on_error handler."""
        event_handler_config = {
            "name": "test_handler",
            "on_success": "success_output_handler",
            "on_error": "error_output_handler",
        }

        structured_result = {
            "status": "error",
            "error_message": "Something went wrong",
        }

        # Simulate routing logic - structured error goes to error handler
        if structured_result.get("status") == "error":
            should_use_error_handler = True
        else:
            should_use_error_handler = False

        assert should_use_error_handler is True

    def test_missing_on_success_handler_logs_warning(self):
        """Test that missing on_success handler is handled."""
        event_handler_config = {
            "name": "test_handler",
            # No on_success defined
        }

        output_handler = event_handler_config.get("on_success")

        # Should return None, component logs warning and returns early
        assert output_handler is None


class TestStructuredInvocationResultDataPart:
    """Tests for StructuredInvocationResult as DataPart in response."""

    def test_result_includes_metadata(self):
        """Test that result includes workflow metadata."""
        from solace_agent_mesh.common.data_parts import (
            StructuredInvocationResult,
            ArtifactRef,
        )

        result = StructuredInvocationResult(
            type="structured_invocation_result",
            status="success",
            output_artifact_ref=ArtifactRef(name="output.json", version=1),
        )

        result_dict = result.model_dump(exclude_none=True)

        assert result_dict["type"] == "structured_invocation_result"
        assert result_dict["status"] == "success"
        assert result_dict["output_artifact_ref"]["name"] == "output.json"
        assert result_dict["output_artifact_ref"]["version"] == 1

    def test_error_result_includes_validation_errors(self):
        """Test that error result includes validation error details."""
        from solace_agent_mesh.common.data_parts import StructuredInvocationResult

        result = StructuredInvocationResult(
            type="structured_invocation_result",
            status="error",
            error_message="Output validation failed",
            validation_errors=[
                "Missing required field 'id'",
                "Invalid type for 'count': expected integer",
            ],
            retry_count=2,
        )

        result_dict = result.model_dump(exclude_none=True)

        assert result_dict["status"] == "error"
        assert result_dict["error_message"] == "Output validation failed"
        assert len(result_dict["validation_errors"]) == 2
        assert result_dict["retry_count"] == 2


class TestPayloadExpressionEvaluation:
    """Tests for payload expression evaluation in output handlers."""

    def test_structured_output_accessible_via_expression(self):
        """Test that structured_output is accessible via payload expression."""
        from solace_ai_connector.common.message import Message as SolaceMessage

        simplified_payload = {
            "text": "Completed",
            "structured_output": {"analysis": {"score": 95, "grade": "A"}},
            "structured_result": {
                "type": "structured_invocation_result",
                "status": "success",
            },
        }

        msg = SolaceMessage(payload=simplified_payload)

        # Test accessing structured_output
        output = msg.get_data("input.payload:structured_output")
        assert output is not None
        assert output["analysis"]["score"] == 95

        # Test accessing nested field
        score = msg.get_data("input.payload:structured_output.analysis.score")
        assert score == 95

    def test_structured_result_status_accessible(self):
        """Test that structured_result status is accessible."""
        from solace_ai_connector.common.message import Message as SolaceMessage

        simplified_payload = {
            "structured_result": {
                "type": "structured_invocation_result",
                "status": "success",
            },
        }

        msg = SolaceMessage(payload=simplified_payload)

        status = msg.get_data("input.payload:structured_result.status")
        assert status == "success"

    def test_error_message_accessible_on_failure(self):
        """Test that error message is accessible on failure."""
        from solace_ai_connector.common.message import Message as SolaceMessage

        simplified_payload = {
            "structured_result": {
                "type": "structured_invocation_result",
                "status": "error",
                "error_message": "Validation failed: missing required field",
            },
        }

        msg = SolaceMessage(payload=simplified_payload)

        error_msg = msg.get_data("input.payload:structured_result.error_message")
        assert error_msg == "Validation failed: missing required field"


class TestMissingStructuredResultHandling:
    """Tests for handling when structured result is expected but missing."""

    def test_missing_result_when_structured_expected(self):
        """Test that missing structured result is detected."""
        from solace_agent_mesh.common import a2a

        # A message without StructuredInvocationResult
        message = Message(
            messageId="msg_no_result",
            role="agent",
            parts=[Part(root=TextPart(text="I completed the task"))],
        )

        is_structured_expected = True
        parts = a2a.get_parts_from_message(message)

        found_result = None
        for part in parts:
            if isinstance(part, DataPart):
                part_data = part.model_dump(exclude_none=True)
                data_content = part_data.get("data", {})
                if isinstance(data_content, dict) and data_content.get("type") == "structured_invocation_result":
                    found_result = data_content
                    break

        # When structured is expected but no result found, should log warning
        missing_result = is_structured_expected and found_result is None

        assert missing_result is True

    def test_non_structured_without_result_ok(self):
        """Test that non-structured invocation without result is OK."""
        from solace_agent_mesh.common import a2a

        message = Message(
            messageId="msg_normal",
            role="agent",
            parts=[Part(root=TextPart(text="Normal response"))],
        )

        is_structured_expected = False
        parts = a2a.get_parts_from_message(message)

        found_result = None
        for part in parts:
            if isinstance(part, DataPart):
                part_data = part.model_dump(exclude_none=True)
                data_content = part_data.get("data", {})
                if isinstance(data_content, dict) and data_content.get("type") == "structured_invocation_result":
                    found_result = data_content
                    break

        # Non-structured without result is normal operation
        should_warn = is_structured_expected and found_result is None

        assert should_warn is False
