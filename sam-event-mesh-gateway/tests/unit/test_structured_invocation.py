"""
Tests for structured invocation functionality in the Event Mesh Gateway.

Tests cover:
- Target name resolution (expression vs static, workflow vs agent)
- Payload format handling (JSON, YAML, CSV, text)
- Structured invocation request/response flow
- Error handling paths
"""

import pytest
import json
import yaml
from unittest.mock import MagicMock, AsyncMock
from typing import Dict, Any

from solace_ai_connector.common.message import Message as SolaceMessage

from sam_event_mesh_gateway.component import EventMeshGatewayComponent


class TestResolveTargetName:
    """Tests for the _resolve_target_name helper method."""

    @pytest.fixture
    def mock_gateway_component(self):
        """Create a mock gateway component with the _resolve_target_name method."""
        component = MagicMock(spec=EventMeshGatewayComponent)
        component.log_identifier = "[TestGateway]"
        # Bind the real method to our mock
        component._resolve_target_name = EventMeshGatewayComponent._resolve_target_name.__get__(
            component, EventMeshGatewayComponent
        )
        return component

    def test_resolve_static_value(self, mock_gateway_component):
        """Test resolution of a static target name."""
        handler_config = {"target_agent_name": "MyAgent"}
        msg = SolaceMessage(payload={"data": "test"})

        result = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_agent_name_expression",
            "target_agent_name",
            "[Test]",
        )

        assert result == "MyAgent"

    def test_resolve_expression_from_payload(self, mock_gateway_component):
        """Test resolution of target name from payload expression."""
        handler_config = {
            "target_agent_name_expression": "input.payload:agent_name",
            "target_agent_name": "FallbackAgent",
        }
        msg = SolaceMessage(payload={"agent_name": "DynamicAgent"})

        result = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_agent_name_expression",
            "target_agent_name",
            "[Test]",
        )

        assert result == "DynamicAgent"

    def test_resolve_expression_from_user_properties(self, mock_gateway_component):
        """Test resolution of target name from user properties."""
        handler_config = {
            "target_agent_name_expression": "input.user_properties:target",
        }
        msg = SolaceMessage(payload={}, user_properties={"target": "PropertyAgent"})

        result = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_agent_name_expression",
            "target_agent_name",
            "[Test]",
        )

        assert result == "PropertyAgent"

    def test_expression_fallback_to_static(self, mock_gateway_component):
        """Test that failed expression falls back to static value."""
        handler_config = {
            "target_agent_name_expression": "input.payload:nonexistent",
            "target_agent_name": "FallbackAgent",
        }
        msg = SolaceMessage(payload={"other_field": "value"})

        result = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_agent_name_expression",
            "target_agent_name",
            "[Test]",
        )

        assert result == "FallbackAgent"

    def test_expression_returns_none_falls_back(self, mock_gateway_component):
        """Test that expression returning None falls back to static."""
        handler_config = {
            "target_agent_name_expression": "input.payload:empty_field",
            "target_agent_name": "FallbackAgent",
        }
        msg = SolaceMessage(payload={"empty_field": None})

        result = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_agent_name_expression",
            "target_agent_name",
            "[Test]",
        )

        # None from expression should fall back to static
        assert result == "FallbackAgent"

    def test_no_config_returns_none(self, mock_gateway_component):
        """Test that missing config returns None."""
        handler_config = {}
        msg = SolaceMessage(payload={})

        result = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_agent_name_expression",
            "target_agent_name",
            "[Test]",
        )

        assert result is None

    def test_workflow_name_resolution(self, mock_gateway_component):
        """Test resolution works for workflow names too."""
        handler_config = {
            "target_workflow_name_expression": "input.payload:workflow",
            "target_workflow_name": "DefaultWorkflow",
        }
        msg = SolaceMessage(payload={"workflow": "DynamicWorkflow"})

        result = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_workflow_name_expression",
            "target_workflow_name",
            "[Test]",
        )

        assert result == "DynamicWorkflow"


class TestFormatHelpers:
    """Tests for payload format helper methods."""

    @pytest.fixture
    def mock_gateway_component(self):
        """Create a mock gateway component with format helper methods."""
        component = MagicMock(spec=EventMeshGatewayComponent)
        # Bind the real methods to our mock
        component._get_format_info = EventMeshGatewayComponent._get_format_info.__get__(
            component, EventMeshGatewayComponent
        )
        component._serialize_for_format = EventMeshGatewayComponent._serialize_for_format.__get__(
            component, EventMeshGatewayComponent
        )
        return component

    def test_get_format_info_json(self, mock_gateway_component):
        """Test format info for JSON."""
        result = mock_gateway_component._get_format_info("json")
        assert result["mime_type"] == "application/json"
        assert result["extension"] == "json"

    def test_get_format_info_yaml(self, mock_gateway_component):
        """Test format info for YAML."""
        result = mock_gateway_component._get_format_info("yaml")
        assert result["mime_type"] == "application/yaml"
        assert result["extension"] == "yaml"

    def test_get_format_info_text(self, mock_gateway_component):
        """Test format info for text."""
        result = mock_gateway_component._get_format_info("text")
        assert result["mime_type"] == "text/plain"
        assert result["extension"] == "txt"

    def test_get_format_info_csv(self, mock_gateway_component):
        """Test format info for CSV."""
        result = mock_gateway_component._get_format_info("csv")
        assert result["mime_type"] == "text/csv"
        assert result["extension"] == "csv"

    def test_get_format_info_unknown_defaults_to_json(self, mock_gateway_component):
        """Test that unknown format defaults to JSON."""
        result = mock_gateway_component._get_format_info("unknown_format")
        assert result["mime_type"] == "application/json"
        assert result["extension"] == "json"

    def test_serialize_json(self, mock_gateway_component):
        """Test JSON serialization."""
        data = {"key": "value", "number": 42}
        result = mock_gateway_component._serialize_for_format(data, "json")

        assert isinstance(result, bytes)
        parsed = json.loads(result.decode("utf-8"))
        assert parsed == data

    def test_serialize_yaml(self, mock_gateway_component):
        """Test YAML serialization."""
        data = {"key": "value", "nested": {"a": 1, "b": 2}}
        result = mock_gateway_component._serialize_for_format(data, "yaml")

        assert isinstance(result, bytes)
        parsed = yaml.safe_load(result.decode("utf-8"))
        assert parsed == data

    def test_serialize_text(self, mock_gateway_component):
        """Test text serialization."""
        data = {"message": "Hello World"}
        result = mock_gateway_component._serialize_for_format(data, "text")

        assert isinstance(result, bytes)
        # Text serialization just converts to string
        assert b"message" in result
        assert b"Hello World" in result

    def test_serialize_csv_list_of_dicts(self, mock_gateway_component):
        """Test CSV serialization with list of dicts."""
        data = [
            {"name": "Alice", "age": "30"},
            {"name": "Bob", "age": "25"},
        ]
        result = mock_gateway_component._serialize_for_format(data, "csv")

        assert isinstance(result, bytes)
        content = result.decode("utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 3  # Header + 2 rows
        assert "name" in lines[0]
        assert "age" in lines[0]
        assert "Alice" in lines[1]
        assert "Bob" in lines[2]

    def test_serialize_csv_non_list_falls_back_to_json(self, mock_gateway_component):
        """Test that non-list data for CSV falls back to JSON."""
        data = {"not": "a list"}
        result = mock_gateway_component._serialize_for_format(data, "csv")

        # Should fall back to JSON
        parsed = json.loads(result.decode("utf-8"))
        assert parsed == data

    def test_serialize_unknown_format_defaults_to_json(self, mock_gateway_component):
        """Test that unknown format defaults to JSON serialization."""
        data = {"key": "value"}
        result = mock_gateway_component._serialize_for_format(data, "unknown")

        parsed = json.loads(result.decode("utf-8"))
        assert parsed == data


class TestStructuredInvocationConfiguration:
    """Tests for structured invocation configuration handling."""

    @pytest.fixture
    def mock_gateway_component(self):
        """Create a mock gateway component."""
        component = MagicMock(spec=EventMeshGatewayComponent)
        component.log_identifier = "[TestGateway]"
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

    def test_workflow_name_enables_structured_invocation(self, mock_gateway_component):
        """Test that target_workflow_name enables structured invocation mode."""
        handler_config = {
            "target_workflow_name": "MyWorkflow",
            "input_expression": "input.payload",
        }

        # Simulate the logic from _translate_external_input
        target_workflow_name = mock_gateway_component._resolve_target_name(
            handler_config,
            SolaceMessage(payload={}),
            "target_workflow_name_expression",
            "target_workflow_name",
            "[Test]",
        )

        structured_config = handler_config.get("structured_invocation", {})
        is_structured = bool(target_workflow_name) or bool(
            structured_config.get("input_schema") or structured_config.get("output_schema")
        )

        assert is_structured is True
        assert target_workflow_name == "MyWorkflow"

    def test_structured_invocation_block_enables_structured_mode(self, mock_gateway_component):
        """Test that structured_invocation block with schemas enables structured mode."""
        handler_config = {
            "target_agent_name": "MyAgent",
            "structured_invocation": {
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
            },
        }

        target_workflow_name = None
        structured_config = handler_config.get("structured_invocation", {})
        is_structured = bool(target_workflow_name) or bool(
            structured_config.get("input_schema") or structured_config.get("output_schema")
        )

        assert is_structured is True

    def test_regular_agent_without_structured_block_not_structured(self, mock_gateway_component):
        """Test that regular agent without structured_invocation is not structured."""
        handler_config = {
            "target_agent_name": "MyAgent",
            "input_expression": "input.payload",
        }

        target_workflow_name = None
        structured_config = handler_config.get("structured_invocation", {})
        is_structured = bool(target_workflow_name) or bool(
            structured_config.get("input_schema") or structured_config.get("output_schema")
        )

        assert is_structured is False

    def test_workflow_takes_precedence_over_agent(self, mock_gateway_component):
        """Test that workflow name takes precedence over agent name."""
        handler_config = {
            "target_workflow_name": "MyWorkflow",
            "target_agent_name": "MyAgent",  # Should be ignored
        }

        target_workflow_name = mock_gateway_component._resolve_target_name(
            handler_config,
            SolaceMessage(payload={}),
            "target_workflow_name_expression",
            "target_workflow_name",
            "[Test]",
        )

        # Logic: workflow takes precedence
        if target_workflow_name:
            target_agent_name = target_workflow_name
        else:
            target_agent_name = handler_config.get("target_agent_name")

        assert target_agent_name == "MyWorkflow"

    def test_payload_format_affects_filename_extension(self, mock_gateway_component):
        """Test that payload_format determines the file extension."""
        test_cases = [
            ("json", "json"),
            ("yaml", "yaml"),
            ("text", "txt"),
            ("csv", "csv"),
        ]

        for payload_format, expected_extension in test_cases:
            format_info = mock_gateway_component._get_format_info(payload_format)
            assert format_info["extension"] == expected_extension, f"Failed for {payload_format}"


class TestStructuredInvocationRequestCreation:
    """Tests for StructuredInvocationRequest creation."""

    def test_structured_invocation_request_fields(self):
        """Test that StructuredInvocationRequest has the required fields."""
        from solace_agent_mesh.common.data_parts import StructuredInvocationRequest

        request = StructuredInvocationRequest(
            type="structured_invocation_request",
            workflow_name="TestGateway",
            node_id="test_handler",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            suggested_output_filename="output.json",
        )

        assert request.type == "structured_invocation_request"
        assert request.workflow_name == "TestGateway"
        assert request.node_id == "test_handler"
        assert request.input_schema == {"type": "object"}
        assert request.output_schema == {"type": "object"}
        assert request.suggested_output_filename == "output.json"

    def test_structured_invocation_request_optional_schemas(self):
        """Test that schemas are optional in StructuredInvocationRequest."""
        from solace_agent_mesh.common.data_parts import StructuredInvocationRequest

        request = StructuredInvocationRequest(
            type="structured_invocation_request",
            workflow_name="TestGateway",
            node_id="test_handler",
        )

        assert request.input_schema is None
        assert request.output_schema is None
        assert request.suggested_output_filename is None


class TestStructuredInvocationResultHandling:
    """Tests for StructuredInvocationResult handling."""

    def test_structured_invocation_result_success(self):
        """Test StructuredInvocationResult for success case."""
        from solace_agent_mesh.common.data_parts import (
            StructuredInvocationResult,
            ArtifactRef,
        )

        result = StructuredInvocationResult(
            type="structured_invocation_result",
            status="success",
            output_artifact_ref=ArtifactRef(name="output.json", version=1),
        )

        assert result.type == "structured_invocation_result"
        assert result.status == "success"
        assert result.output_artifact_ref.name == "output.json"
        assert result.output_artifact_ref.version == 1
        assert result.error_message is None

    def test_structured_invocation_result_error(self):
        """Test StructuredInvocationResult for error case."""
        from solace_agent_mesh.common.data_parts import StructuredInvocationResult

        result = StructuredInvocationResult(
            type="structured_invocation_result",
            status="error",
            error_message="Something went wrong",
        )

        assert result.status == "error"
        assert result.error_message == "Something went wrong"
        assert result.output_artifact_ref is None

    def test_structured_invocation_result_serialization(self):
        """Test that StructuredInvocationResult can be serialized to dict."""
        from solace_agent_mesh.common.data_parts import (
            StructuredInvocationResult,
            ArtifactRef,
        )

        result = StructuredInvocationResult(
            type="structured_invocation_result",
            status="success",
            output_artifact_ref=ArtifactRef(name="output.json", version=1),
        )

        data = result.model_dump()

        assert data["type"] == "structured_invocation_result"
        assert data["status"] == "success"
        assert data["output_artifact_ref"]["name"] == "output.json"
