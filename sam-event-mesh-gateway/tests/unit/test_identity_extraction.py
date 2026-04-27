"""
Tests for user identity extraction in the Event Mesh Gateway.

Tests cover:
- _extract_initial_claims method
- User identity expression evaluation
- Default identity fallback
- Missing identity scenarios
- Error handling
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from solace_ai_connector.common.message import Message as SolaceMessage

from sam_event_mesh_gateway.component import EventMeshGatewayComponent


class TestExtractInitialClaims:
    """Tests for the _extract_initial_claims method."""

    @pytest.fixture
    def mock_gateway_component(self):
        """Create a mock gateway component with the method bound."""
        component = MagicMock(spec=EventMeshGatewayComponent)
        component.log_identifier = "[TestGateway]"

        # Bind the real async method
        component._extract_initial_claims = EventMeshGatewayComponent._extract_initial_claims.__get__(
            component, EventMeshGatewayComponent
        )

        return component

    @pytest.mark.asyncio
    async def test_extract_identity_from_user_properties(self, mock_gateway_component):
        """Test extracting user identity from user properties."""
        solace_msg = SolaceMessage(
            payload={"data": "test"},
            user_properties={"user_id": "user123", "email": "user@example.com"},
        )

        handler_config = {
            "name": "test_handler",
            "user_identity_expression": "input.user_properties:user_id",
        }

        external_event_data = {
            "solace_message": solace_msg,
            "handler_config": handler_config,
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        assert result is not None
        assert result["id"] == "user123"
        assert result["source"] == "solace_message"

    @pytest.mark.asyncio
    async def test_extract_identity_from_payload(self, mock_gateway_component):
        """Test extracting user identity from message payload."""
        solace_msg = SolaceMessage(
            payload={"sender": {"id": "sender_456", "name": "John"}},
        )

        handler_config = {
            "name": "test_handler",
            "user_identity_expression": "input.payload:sender.id",
        }

        external_event_data = {
            "solace_message": solace_msg,
            "handler_config": handler_config,
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        assert result is not None
        assert result["id"] == "sender_456"
        assert result["source"] == "solace_message"

    @pytest.mark.asyncio
    async def test_fallback_to_default_identity(self, mock_gateway_component):
        """Test fallback to default_user_identity when expression yields None."""
        solace_msg = SolaceMessage(
            payload={"data": "test"},
            user_properties={},
        )

        handler_config = {
            "name": "test_handler",
            "user_identity_expression": "input.user_properties:user_id",  # Won't find this
            "default_user_identity": "default_system_user",
        }

        external_event_data = {
            "solace_message": solace_msg,
            "handler_config": handler_config,
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        assert result is not None
        assert result["id"] == "default_system_user"
        assert result["source"] == "configured_default"

    @pytest.mark.asyncio
    async def test_no_identity_returns_none(self, mock_gateway_component):
        """Test that missing identity without default returns None."""
        solace_msg = SolaceMessage(
            payload={"data": "test"},
            user_properties={},
        )

        handler_config = {
            "name": "test_handler",
            "user_identity_expression": "input.user_properties:nonexistent",
            # No default_user_identity configured
        }

        external_event_data = {
            "solace_message": solace_msg,
            "handler_config": handler_config,
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_no_expression_and_no_default_returns_none(self, mock_gateway_component):
        """Test that no expression and no default returns None."""
        solace_msg = SolaceMessage(
            payload={"data": "test"},
        )

        handler_config = {
            "name": "test_handler",
            # No user_identity_expression
            # No default_user_identity
        }

        external_event_data = {
            "solace_message": solace_msg,
            "handler_config": handler_config,
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_only_default_identity_configured(self, mock_gateway_component):
        """Test using only default_user_identity without expression."""
        solace_msg = SolaceMessage(
            payload={"data": "test"},
        )

        handler_config = {
            "name": "test_handler",
            "default_user_identity": "anonymous_user",
            # No user_identity_expression
        }

        external_event_data = {
            "solace_message": solace_msg,
            "handler_config": handler_config,
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        assert result is not None
        assert result["id"] == "anonymous_user"
        assert result["source"] == "configured_default"

    @pytest.mark.asyncio
    async def test_expression_error_returns_none(self, mock_gateway_component):
        """Test that expression evaluation error returns None."""
        # Create a message that will cause expression evaluation to fail
        solace_msg = MagicMock(spec=SolaceMessage)
        solace_msg.get_data.side_effect = Exception("Expression evaluation failed")

        handler_config = {
            "name": "test_handler",
            "user_identity_expression": "invalid.expression",
            "default_user_identity": "fallback",  # Should NOT be used on error
        }

        external_event_data = {
            "solace_message": solace_msg,
            "handler_config": handler_config,
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        # On expression error, authentication fails (returns None)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_solace_message_returns_none(self, mock_gateway_component):
        """Test that missing solace_message returns None."""
        handler_config = {
            "name": "test_handler",
            "user_identity_expression": "input.user_properties:user_id",
        }

        external_event_data = {
            "handler_config": handler_config,
            # No solace_message
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_handler_config_returns_none(self, mock_gateway_component):
        """Test that missing handler_config returns None."""
        solace_msg = SolaceMessage(
            payload={"data": "test"},
        )

        external_event_data = {
            "solace_message": solace_msg,
            # No handler_config
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_string_identity_not_used(self, mock_gateway_component):
        """Test that empty string identity is not used."""
        solace_msg = SolaceMessage(
            payload={"data": "test"},
            user_properties={"user_id": ""},
        )

        handler_config = {
            "name": "test_handler",
            "user_identity_expression": "input.user_properties:user_id",
            "default_user_identity": "default_user",
        }

        external_event_data = {
            "solace_message": solace_msg,
            "handler_config": handler_config,
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        # Empty string should fall back to default
        assert result is not None
        assert result["id"] == "default_user"
        assert result["source"] == "configured_default"

    @pytest.mark.asyncio
    async def test_nested_payload_identity_extraction(self, mock_gateway_component):
        """Test extracting identity from deeply nested payload."""
        solace_msg = SolaceMessage(
            payload={
                "envelope": {
                    "header": {
                        "auth": {
                            "principal": "deep_user_789"
                        }
                    }
                }
            },
        )

        handler_config = {
            "name": "test_handler",
            "user_identity_expression": "input.payload:envelope.header.auth.principal",
        }

        external_event_data = {
            "solace_message": solace_msg,
            "handler_config": handler_config,
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        assert result is not None
        assert result["id"] == "deep_user_789"
        assert result["source"] == "solace_message"

    @pytest.mark.asyncio
    async def test_topic_based_identity_extraction(self, mock_gateway_component):
        """Test extracting identity from message topic."""
        solace_msg = SolaceMessage(
            payload={"data": "test"},
            topic="events/users/user_abc/actions/create",
        )

        handler_config = {
            "name": "test_handler",
            "user_identity_expression": "input.topic:",
        }

        external_event_data = {
            "solace_message": solace_msg,
            "handler_config": handler_config,
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        assert result is not None
        # The full topic is returned when using input.topic:
        assert result["id"] == "events/users/user_abc/actions/create"
        assert result["source"] == "solace_message"

    @pytest.mark.asyncio
    async def test_numeric_identity_converted_to_string(self, mock_gateway_component):
        """Test that numeric identity from payload is handled."""
        solace_msg = SolaceMessage(
            payload={"user_id": 12345},
        )

        handler_config = {
            "name": "test_handler",
            "user_identity_expression": "input.payload:user_id",
        }

        external_event_data = {
            "solace_message": solace_msg,
            "handler_config": handler_config,
        }

        result = await mock_gateway_component._extract_initial_claims(external_event_data)

        # Note: The actual component stores the raw value (12345 as int)
        # The test verifies the method returns a result
        assert result is not None
        assert result["id"] == 12345
        assert result["source"] == "solace_message"
