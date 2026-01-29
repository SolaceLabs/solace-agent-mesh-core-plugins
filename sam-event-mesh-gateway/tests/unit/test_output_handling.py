"""
Tests for output handling in the Event Mesh Gateway.

Tests cover:
- Output schema validation behavior
- Transforms application
- Payload encoding
- Message data access patterns
"""

import pytest
import json

from solace_ai_connector.common.message import Message as SolaceMessage
from solace_ai_connector.transforms.transforms import Transforms


class TestOutputSchemaValidation:
    """Tests for output schema validation using real jsonschema."""

    def test_valid_payload_passes_validation(self):
        """Test that valid payload passes JSON schema validation."""
        import jsonschema

        output_schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "result": {"type": "number"},
            },
            "required": ["status"],
        }

        payload = {"status": "success", "result": 42}

        # Should not raise
        jsonschema.validate(instance=payload, schema=output_schema)

    def test_invalid_payload_fails_validation(self):
        """Test that invalid payload fails JSON schema validation."""
        import jsonschema

        output_schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "result": {"type": "number"},
            },
            "required": ["status"],
        }

        # Missing required field
        payload = {"result": 42}

        with pytest.raises(jsonschema.ValidationError) as exc_info:
            jsonschema.validate(instance=payload, schema=output_schema)

        assert "'status' is a required property" in str(exc_info.value)

    def test_type_mismatch_fails_validation(self):
        """Test that type mismatch fails validation."""
        import jsonschema

        output_schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
            },
        }

        payload = {"count": "not a number"}

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=payload, schema=output_schema)

    def test_nested_object_validation(self):
        """Test validation of nested objects."""
        import jsonschema

        output_schema = {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["items"],
                }
            },
            "required": ["data"],
        }

        valid_payload = {"data": {"items": ["a", "b", "c"]}}
        jsonschema.validate(instance=valid_payload, schema=output_schema)

        invalid_payload = {"data": {"items": [1, 2, 3]}}  # Wrong item type
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=invalid_payload, schema=output_schema)


class TestOutputTransforms:
    """Tests for output transforms using real Transforms class."""

    def test_copy_transform_moves_data(self):
        """Test that copy transform moves data between locations."""
        transforms_config = [
            {
                "type": "copy",
                "source_expression": "input.payload:text",
                "dest_expression": "user_data.processed_text",
            }
        ]

        transforms = Transforms(transforms_config, log_identifier="[Test]")
        msg = SolaceMessage(payload={"text": "Original text"})

        transforms.transform(msg, calling_object=None)

        result = msg.get_data("user_data.processed_text")
        assert result == "Original text"

    def test_multiple_transforms_applied_in_order(self):
        """Test that multiple transforms are applied sequentially."""
        transforms_config = [
            {
                "type": "copy",
                "source_expression": "input.payload:value",
                "dest_expression": "user_data.step1",
            },
            {
                "type": "copy",
                "source_expression": "user_data.step1",
                "dest_expression": "user_data.step2",
            },
        ]

        transforms = Transforms(transforms_config, log_identifier="[Test]")
        msg = SolaceMessage(payload={"value": "test_data"})

        transforms.transform(msg, calling_object=None)

        assert msg.get_data("user_data.step1") == "test_data"
        assert msg.get_data("user_data.step2") == "test_data"


class TestPayloadEncoding:
    """Tests for payload encoding using real encoder."""

    def test_json_encoding(self):
        """Test JSON payload encoding."""
        from solace_ai_connector.common.utils import encode_payload

        payload = {"key": "value", "number": 42}
        encoded = encode_payload(
            payload=payload, encoding="utf-8", payload_format="json"
        )

        assert isinstance(encoded, bytes)
        decoded = json.loads(encoded.decode("utf-8"))
        assert decoded == payload

    def test_text_encoding(self):
        """Test text payload encoding."""
        from solace_ai_connector.common.utils import encode_payload

        payload = "Plain text message"
        encoded = encode_payload(
            payload=payload, encoding="utf-8", payload_format="text"
        )

        assert isinstance(encoded, bytes)
        assert encoded == b"Plain text message"

    def test_json_encoding_preserves_unicode(self):
        """Test that JSON encoding preserves unicode characters."""
        from solace_ai_connector.common.utils import encode_payload

        payload = {"message": "Hello 世界 🌍"}
        encoded = encode_payload(
            payload=payload, encoding="utf-8", payload_format="json"
        )

        decoded = json.loads(encoded.decode("utf-8"))
        assert decoded["message"] == "Hello 世界 🌍"


class TestSolaceMessageDataAccess:
    """Tests for SolaceMessage data access patterns used in output handling."""

    def test_access_nested_payload_data(self):
        """Test accessing nested data from payload."""
        msg = SolaceMessage(
            payload={
                "response": {
                    "data": {"result": "success", "count": 42}
                }
            }
        )

        assert msg.get_data("input.payload:response.data.result") == "success"
        assert msg.get_data("input.payload:response.data.count") == 42

    def test_access_user_data_storage(self):
        """Test storing and retrieving from user_data."""
        msg = SolaceMessage(payload={"text": "test"})

        msg.set_data("user_data.forward_context", {
            "correlation_id": "corr_123",
            "sender": "system_a",
        })

        assert msg.get_data("user_data.forward_context:correlation_id") == "corr_123"
        assert msg.get_data("user_data.forward_context:sender") == "system_a"

    def test_access_user_properties(self):
        """Test accessing user properties from message."""
        original_props = {"prop1": "value1", "prop2": "value2"}
        msg = SolaceMessage(
            payload={"text": "response"},
            user_properties=original_props,
        )

        assert msg.get_user_properties() == original_props
        assert msg.get_data("input.user_properties:prop1") == "value1"

    def test_access_topic(self):
        """Test accessing topic from message."""
        msg = SolaceMessage(
            payload={"data": "test"},
            topic="events/orders/created",
        )

        assert msg.get_data("input.topic:") == "events/orders/created"

    def test_missing_nested_data_returns_none(self):
        """Test that missing nested data returns None."""
        msg = SolaceMessage(payload={"data": "test"})

        result = msg.get_data("input.payload:nonexistent.path")
        assert result is None
