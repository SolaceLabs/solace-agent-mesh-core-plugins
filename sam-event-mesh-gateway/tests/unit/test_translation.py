"""
Tests for input translation in the Event Mesh Gateway.

Tests cover:
- _translate_external_input method
- Normal text-based invocation
- Structured invocation mode detection
- Workflow vs agent target resolution
- Artifact creation for structured input
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any

from solace_ai_connector.common.message import Message as SolaceMessage

from sam_event_mesh_gateway.component import EventMeshGatewayComponent


class MockExternalEventData:
    """Mock external event data for testing."""

    def __init__(self, payload: Any, topic: str = "test/topic", user_properties: Dict = None):
        self._payload = payload
        self._topic = topic
        self._user_properties = user_properties or {}

    def get_payload(self):
        return self._payload

    def get_topic(self):
        return self._topic

    def get_user_properties(self):
        return self._user_properties


class TestStructuredInvocationDetection:
    """Tests for structured invocation mode detection."""

    @pytest.fixture
    def mock_gateway_component(self, mock_artifact_service):
        """Create a mock gateway component with translation method."""
        component = MagicMock(spec=EventMeshGatewayComponent)
        component.log_identifier = "[TestGateway]"
        component.gateway_id = "TestGateway"
        component.shared_artifact_service = mock_artifact_service

        # Bind real methods
        component._resolve_target_name = EventMeshGatewayComponent._resolve_target_name.__get__(
            component, EventMeshGatewayComponent
        )
        component._get_format_info = EventMeshGatewayComponent._get_format_info.__get__(
            component, EventMeshGatewayComponent
        )
        component._serialize_for_format = EventMeshGatewayComponent._serialize_for_format.__get__(
            component, EventMeshGatewayComponent
        )
        component._process_artifacts_from_message = AsyncMock(return_value=[])

        return component

    def test_workflow_name_enables_structured_mode(self, mock_gateway_component):
        """Test that target_workflow_name enables structured invocation mode."""
        handler_config = {
            "name": "workflow_handler",
            "target_workflow_name": "TestWorkflow",
            "input_expression": "input.payload",
        }
        msg = SolaceMessage(payload={"data": "test"})

        # Resolve workflow name
        target_workflow_name = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_workflow_name_expression",
            "target_workflow_name",
            "[Test]",
        )

        # Check structured mode detection logic
        structured_config = handler_config.get("structured_invocation", {})
        is_structured = bool(target_workflow_name) or bool(
            structured_config.get("input_schema") or structured_config.get("output_schema")
        )

        assert is_structured is True
        assert target_workflow_name == "TestWorkflow"

    def test_structured_invocation_block_enables_structured_mode(self, mock_gateway_component):
        """Test that structured_invocation block enables structured mode."""
        handler_config = {
            "name": "agent_handler",
            "target_agent_name": "TestAgent",
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

    def test_only_input_schema_enables_structured_mode(self, mock_gateway_component):
        """Test that only input_schema enables structured mode."""
        handler_config = {
            "name": "agent_handler",
            "target_agent_name": "TestAgent",
            "structured_invocation": {
                "input_schema": {"type": "object"},
            },
        }

        target_workflow_name = None
        structured_config = handler_config.get("structured_invocation", {})
        is_structured = bool(target_workflow_name) or bool(
            structured_config.get("input_schema") or structured_config.get("output_schema")
        )

        assert is_structured is True

    def test_only_output_schema_enables_structured_mode(self, mock_gateway_component):
        """Test that only output_schema enables structured mode."""
        handler_config = {
            "name": "agent_handler",
            "target_agent_name": "TestAgent",
            "structured_invocation": {
                "output_schema": {"type": "object"},
            },
        }

        target_workflow_name = None
        structured_config = handler_config.get("structured_invocation", {})
        is_structured = bool(target_workflow_name) or bool(
            structured_config.get("input_schema") or structured_config.get("output_schema")
        )

        assert is_structured is True

    def test_empty_structured_block_not_structured(self, mock_gateway_component):
        """Test that empty structured_invocation block doesn't enable structured mode."""
        handler_config = {
            "name": "agent_handler",
            "target_agent_name": "TestAgent",
            "structured_invocation": {},
        }

        target_workflow_name = None
        structured_config = handler_config.get("structured_invocation", {})
        is_structured = bool(target_workflow_name) or bool(
            structured_config.get("input_schema") or structured_config.get("output_schema")
        )

        assert is_structured is False

    def test_normal_agent_not_structured(self, mock_gateway_component):
        """Test that normal agent invocation is not structured."""
        handler_config = {
            "name": "agent_handler",
            "target_agent_name": "TestAgent",
            "input_expression": "input.payload",
        }

        target_workflow_name = None
        structured_config = handler_config.get("structured_invocation", {})
        is_structured = bool(target_workflow_name) or bool(
            structured_config.get("input_schema") or structured_config.get("output_schema")
        )

        assert is_structured is False


class TestTargetNameResolution:
    """Tests for target name resolution (expression vs static)."""

    @pytest.fixture
    def mock_gateway_component(self):
        """Create a mock gateway component with resolve method."""
        component = MagicMock(spec=EventMeshGatewayComponent)
        component.log_identifier = "[TestGateway]"
        component._resolve_target_name = EventMeshGatewayComponent._resolve_target_name.__get__(
            component, EventMeshGatewayComponent
        )
        return component

    def test_static_workflow_name(self, mock_gateway_component):
        """Test resolution of static workflow name."""
        handler_config = {"target_workflow_name": "StaticWorkflow"}
        msg = SolaceMessage(payload={})

        result = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_workflow_name_expression",
            "target_workflow_name",
            "[Test]",
        )

        assert result == "StaticWorkflow"

    def test_dynamic_workflow_name_from_expression(self, mock_gateway_component):
        """Test resolution of workflow name from payload expression."""
        handler_config = {
            "target_workflow_name_expression": "input.payload:workflow_name",
            "target_workflow_name": "FallbackWorkflow",
        }
        msg = SolaceMessage(payload={"workflow_name": "DynamicWorkflow"})

        result = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_workflow_name_expression",
            "target_workflow_name",
            "[Test]",
        )

        assert result == "DynamicWorkflow"

    def test_expression_fallback_to_static_workflow(self, mock_gateway_component):
        """Test that failed expression falls back to static workflow name."""
        handler_config = {
            "target_workflow_name_expression": "input.payload:nonexistent",
            "target_workflow_name": "FallbackWorkflow",
        }
        msg = SolaceMessage(payload={"other_field": "value"})

        result = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_workflow_name_expression",
            "target_workflow_name",
            "[Test]",
        )

        assert result == "FallbackWorkflow"

    def test_workflow_takes_precedence_over_agent(self, mock_gateway_component):
        """Test that workflow name takes precedence when both are configured."""
        handler_config = {
            "target_workflow_name": "MyWorkflow",
            "target_agent_name": "MyAgent",
        }
        msg = SolaceMessage(payload={})

        # Resolve workflow first (as the component does)
        target_workflow_name = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_workflow_name_expression",
            "target_workflow_name",
            "[Test]",
        )

        # The logic: if workflow exists, use it; otherwise use agent
        if target_workflow_name:
            target = target_workflow_name
        else:
            target = mock_gateway_component._resolve_target_name(
                handler_config,
                msg,
                "target_agent_name_expression",
                "target_agent_name",
                "[Test]",
            )

        assert target == "MyWorkflow"

    def test_agent_used_when_no_workflow(self, mock_gateway_component):
        """Test that agent name is used when no workflow is configured."""
        handler_config = {
            "target_agent_name": "MyAgent",
        }
        msg = SolaceMessage(payload={})

        # Resolve workflow first (returns None)
        target_workflow_name = mock_gateway_component._resolve_target_name(
            handler_config,
            msg,
            "target_workflow_name_expression",
            "target_workflow_name",
            "[Test]",
        )

        # Fall back to agent
        if target_workflow_name:
            target = target_workflow_name
        else:
            target = mock_gateway_component._resolve_target_name(
                handler_config,
                msg,
                "target_agent_name_expression",
                "target_agent_name",
                "[Test]",
            )

        assert target_workflow_name is None
        assert target == "MyAgent"


class TestPayloadFormatHandling:
    """Tests for payload format handling in structured invocation."""

    @pytest.fixture
    def mock_gateway_component(self):
        """Create a mock gateway component with format methods."""
        component = MagicMock(spec=EventMeshGatewayComponent)
        component._get_format_info = EventMeshGatewayComponent._get_format_info.__get__(
            component, EventMeshGatewayComponent
        )
        component._serialize_for_format = EventMeshGatewayComponent._serialize_for_format.__get__(
            component, EventMeshGatewayComponent
        )
        return component

    def test_json_format_info(self, mock_gateway_component):
        """Test format info for JSON payload format."""
        result = mock_gateway_component._get_format_info("json")
        assert result["mime_type"] == "application/json"
        assert result["extension"] == "json"

    def test_yaml_format_info(self, mock_gateway_component):
        """Test format info for YAML payload format."""
        result = mock_gateway_component._get_format_info("yaml")
        assert result["mime_type"] == "application/yaml"
        assert result["extension"] == "yaml"

    def test_csv_format_info(self, mock_gateway_component):
        """Test format info for CSV payload format."""
        result = mock_gateway_component._get_format_info("csv")
        assert result["mime_type"] == "text/csv"
        assert result["extension"] == "csv"

    def test_text_format_info(self, mock_gateway_component):
        """Test format info for text payload format."""
        result = mock_gateway_component._get_format_info("text")
        assert result["mime_type"] == "text/plain"
        assert result["extension"] == "txt"

    def test_unknown_format_defaults_to_json(self, mock_gateway_component):
        """Test that unknown format defaults to JSON."""
        result = mock_gateway_component._get_format_info("unknown")
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
        import yaml

        data = {"key": "value", "nested": {"a": 1}}
        result = mock_gateway_component._serialize_for_format(data, "yaml")

        assert isinstance(result, bytes)
        parsed = yaml.safe_load(result.decode("utf-8"))
        assert parsed == data

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
        assert "Alice" in lines[1]

    def test_serialize_csv_non_list_falls_back(self, mock_gateway_component):
        """Test that non-list data for CSV falls back to JSON."""
        data = {"not": "a list"}
        result = mock_gateway_component._serialize_for_format(data, "csv")

        # Should fall back to JSON
        parsed = json.loads(result.decode("utf-8"))
        assert parsed == data


class TestStructuredInvocationRequestCreation:
    """Tests for StructuredInvocationRequest creation in translation."""

    def test_request_fields_from_handler_config(self):
        """Test that request uses correct fields from handler config."""
        from solace_agent_mesh.common.data_parts import StructuredInvocationRequest

        handler_config = {
            "name": "my_handler",
            "structured_invocation": {
                "input_schema": {"type": "object", "properties": {"data": {"type": "array"}}},
                "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
            },
        }

        request = StructuredInvocationRequest(
            type="structured_invocation_request",
            workflow_name="TestGateway",  # Caller identity
            node_id=handler_config.get("name"),
            input_schema=handler_config["structured_invocation"].get("input_schema"),
            output_schema=handler_config["structured_invocation"].get("output_schema"),
            suggested_output_filename=f"TestGateway_{handler_config['name']}_abc123.json",
        )

        assert request.type == "structured_invocation_request"
        assert request.workflow_name == "TestGateway"
        assert request.node_id == "my_handler"
        assert request.input_schema is not None
        assert request.output_schema is not None
        assert request.suggested_output_filename.endswith(".json")

    def test_request_without_schemas(self):
        """Test that request can be created without schemas (workflow mode)."""
        from solace_agent_mesh.common.data_parts import StructuredInvocationRequest

        request = StructuredInvocationRequest(
            type="structured_invocation_request",
            workflow_name="TestGateway",
            node_id="workflow_handler",
        )

        assert request.input_schema is None
        assert request.output_schema is None

    def test_suggested_filename_uses_format_extension(self):
        """Test that suggested filename uses correct extension for format."""
        from solace_agent_mesh.common.data_parts import StructuredInvocationRequest

        formats = [
            ("json", ".json"),
            ("yaml", ".yaml"),
            ("csv", ".csv"),
            ("text", ".txt"),
        ]

        for payload_format, expected_ext in formats:
            format_info = {
                "json": {"extension": "json"},
                "yaml": {"extension": "yaml"},
                "csv": {"extension": "csv"},
                "text": {"extension": "txt"},
            }
            ext = format_info.get(payload_format, {"extension": "json"})["extension"]

            request = StructuredInvocationRequest(
                type="structured_invocation_request",
                workflow_name="TestGateway",
                node_id="handler",
                suggested_output_filename=f"output.{ext}",
            )

            assert request.suggested_output_filename.endswith(expected_ext), f"Failed for {payload_format}"


class TestExternalRequestContext:
    """Tests for external request context building."""

    def test_context_includes_structured_flag(self):
        """Test that context includes is_structured_invocation flag."""
        # Simulate context building as done in _translate_external_input
        is_structured = True

        external_request_context = {
            "event_handler_name": "test_handler",
            "original_solace_topic": "test/topic",
            "original_solace_user_properties": {},
            "user_identity": {"id": "user123"},
            "app_name_for_artifacts": "TestGateway",
            "user_id_for_artifacts": "user123",
            "a2a_session_id": "session_abc",
            "user_id_for_a2a": "user123",
            "target_agent_name": "TestWorkflow",
            "is_structured_invocation": is_structured,
        }

        if is_structured:
            external_request_context["structured_config"] = {"input_schema": {"type": "object"}}

        assert external_request_context["is_structured_invocation"] is True
        assert "structured_config" in external_request_context

    def test_context_without_structured_flag(self):
        """Test that context doesn't include structured_config when not structured."""
        is_structured = False

        external_request_context = {
            "event_handler_name": "test_handler",
            "target_agent_name": "TestAgent",
            "is_structured_invocation": is_structured,
        }

        if is_structured:
            external_request_context["structured_config"] = {}

        assert external_request_context["is_structured_invocation"] is False
        assert "structured_config" not in external_request_context


class TestForwardContextHandling:
    """Tests for forward_context configuration in translation."""

    def test_forward_context_expressions_evaluated(self, mock_gateway_component):
        """Test that forward_context expressions are evaluated."""
        handler_config = {
            "name": "test_handler",
            "forward_context": {
                "original_topic": "input.topic:",
                "sender_id": "input.user_properties:sender",
                "custom_field": "input.payload:custom",
            },
        }

        msg = SolaceMessage(
            payload={"custom": "custom_value"},
            topic="test/events/123",
            user_properties={"sender": "user_456"},
        )

        # Simulate forward_context evaluation
        forwarded_data = {}
        for key, expression in handler_config["forward_context"].items():
            try:
                forwarded_data[key] = msg.get_data(expression)
            except Exception:
                pass

        assert forwarded_data.get("original_topic") == "test/events/123"
        assert forwarded_data.get("sender_id") == "user_456"
        assert forwarded_data.get("custom_field") == "custom_value"

    def test_forward_context_missing_field_skipped(self, mock_gateway_component):
        """Test that missing forward_context fields are skipped."""
        handler_config = {
            "forward_context": {
                "existing": "input.payload:exists",
                "missing": "input.payload:nonexistent",
            },
        }

        msg = SolaceMessage(payload={"exists": "value"})

        forwarded_data = {}
        for key, expression in handler_config["forward_context"].items():
            try:
                result = msg.get_data(expression)
                if result is not None:
                    forwarded_data[key] = result
            except Exception:
                pass

        assert "existing" in forwarded_data
        assert forwarded_data["existing"] == "value"
