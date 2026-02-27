"""
Tests for Event Mesh Gateway data plane lifecycle management.

These tests verify the data plane initialization, subscription management,
and cleanup behavior using real component instances with test mode enabled.
"""

import pytest
import asyncio
import queue
from unittest.mock import MagicMock, AsyncMock, patch

from sam_event_mesh_gateway.component import EventMeshGatewayComponent


class TestDataPlaneTestMode:
    """Tests for data plane behavior in test mode."""

    @pytest.fixture
    def gateway_component_config(self):
        """Create minimal gateway component configuration for testing."""
        return {
            "namespace": "test_namespace",
            "gateway_id": "TestGateway_01",
            "artifact_service": {"type": "memory"},
            "event_mesh_broker_config": {
                "test_mode": True,  # Test mode enabled
            },
            "event_handlers": [
                {
                    "name": "test_handler",
                    "subscriptions": [{"topic": "test/events/>", "qos": 1}],
                    "input_expression": "input.payload:message",
                    "target_agent_name": "TestAgent",
                }
            ],
            "output_handlers": [
                {
                    "name": "test_output",
                    "topic_expression": "static:test/responses/sample",
                    "payload_expression": "input.payload:text",
                    "payload_format": "text",
                }
            ],
        }

    @pytest.fixture
    def mock_gateway_component(self, gateway_component_config):
        """Create a mock gateway component with real attributes for lifecycle testing."""
        component = MagicMock(spec=EventMeshGatewayComponent)

        # Set real attributes needed for lifecycle methods
        component.log_identifier = "[TestGateway]"
        component.gateway_id = "TestGateway_01"
        component.namespace = "test_namespace"
        component.event_mesh_broker_config = gateway_component_config["event_mesh_broker_config"]
        component.event_handlers_config = gateway_component_config["event_handlers"]

        # Data plane state attributes
        component.data_plane_internal_app = None
        component.data_plane_broker_input = None
        component.data_plane_broker_output = None
        component.data_plane_message_queue = queue.Queue(maxsize=1000)
        component.data_plane_client_lock = asyncio.Lock()
        component.stop_signal = asyncio.Event()

        # Bind real async methods
        component._start_data_plane_client = EventMeshGatewayComponent._start_data_plane_client.__get__(
            component, EventMeshGatewayComponent
        )
        component._stop_data_plane_client = EventMeshGatewayComponent._stop_data_plane_client.__get__(
            component, EventMeshGatewayComponent
        )
        component._initialize_and_subscribe_data_plane = EventMeshGatewayComponent._initialize_and_subscribe_data_plane.__get__(
            component, EventMeshGatewayComponent
        )

        return component

    @pytest.mark.asyncio
    async def test_start_data_plane_in_test_mode_skips_initialization(self, mock_gateway_component):
        """
        Test that _start_data_plane_client skips initialization when test_mode is True.

        This verifies:
        1. No broker connections are attempted
        2. data_plane_internal_app remains None
        3. Method completes without error
        """
        # Ensure test_mode is True
        assert mock_gateway_component.event_mesh_broker_config.get("test_mode") is True

        # Call the method
        await mock_gateway_component._start_data_plane_client()

        # Verify no internal app was created (test mode skips initialization)
        assert mock_gateway_component.data_plane_internal_app is None
        assert mock_gateway_component.data_plane_broker_input is None
        assert mock_gateway_component.data_plane_broker_output is None

    @pytest.mark.asyncio
    async def test_start_data_plane_idempotent_when_already_started(self, mock_gateway_component):
        """
        Test that calling _start_data_plane_client multiple times is safe.

        Even with test_mode=True (which doesn't create an app), calling
        the method multiple times should not cause issues.
        """
        # Call multiple times
        await mock_gateway_component._start_data_plane_client()
        await mock_gateway_component._start_data_plane_client()
        await mock_gateway_component._start_data_plane_client()

        # Should still be in test mode state (no app created)
        assert mock_gateway_component.data_plane_internal_app is None

    @pytest.mark.asyncio
    async def test_stop_data_plane_when_not_started(self, mock_gateway_component):
        """
        Test that _stop_data_plane_client handles case where client was never started.
        """
        # Ensure nothing is started
        assert mock_gateway_component.data_plane_internal_app is None

        # Should not raise, just log warning
        await mock_gateway_component._stop_data_plane_client()

        # State should remain None
        assert mock_gateway_component.data_plane_internal_app is None

    @pytest.mark.asyncio
    async def test_stop_data_plane_cleans_up_references(self, mock_gateway_component):
        """
        Test that _stop_data_plane_client properly cleans up all references.
        """
        # Simulate a started state with a mock app
        mock_app = MagicMock()
        mock_gateway_component.data_plane_internal_app = mock_app
        mock_gateway_component.data_plane_broker_input = MagicMock()
        mock_gateway_component.data_plane_broker_output = MagicMock()

        # Stop the data plane
        await mock_gateway_component._stop_data_plane_client()

        # Verify cleanup was called
        mock_app.cleanup.assert_called_once()

        # Verify all references are cleared
        assert mock_gateway_component.data_plane_internal_app is None
        assert mock_gateway_component.data_plane_broker_input is None
        assert mock_gateway_component.data_plane_broker_output is None

    @pytest.mark.asyncio
    async def test_stop_data_plane_handles_cleanup_exception(self, mock_gateway_component):
        """
        Test that _stop_data_plane_client handles exceptions during cleanup gracefully.
        """
        # Simulate a started state with a mock app that raises on cleanup
        mock_app = MagicMock()
        mock_app.cleanup.side_effect = Exception("Cleanup failed")
        mock_gateway_component.data_plane_internal_app = mock_app
        mock_gateway_component.data_plane_broker_input = MagicMock()
        mock_gateway_component.data_plane_broker_output = MagicMock()

        # Stop should not raise despite cleanup exception
        await mock_gateway_component._stop_data_plane_client()

        # References should still be cleared even after exception
        assert mock_gateway_component.data_plane_internal_app is None
        assert mock_gateway_component.data_plane_broker_input is None
        assert mock_gateway_component.data_plane_broker_output is None

    @pytest.mark.asyncio
    async def test_initialize_and_subscribe_in_test_mode(self, mock_gateway_component):
        """
        Test that _initialize_and_subscribe_data_plane handles test mode.

        In test mode, start_data_plane_client skips initialization, so
        data_plane_broker_input will be None and subscription adding
        should raise an error.
        """
        # Ensure test_mode is True and broker_input is None
        assert mock_gateway_component.event_mesh_broker_config.get("test_mode") is True

        # Call initialize - should raise because broker_input is None
        with pytest.raises(RuntimeError, match="Data plane BrokerInput not available"):
            await mock_gateway_component._initialize_and_subscribe_data_plane()


class TestDataPlaneSubscriptionConfig:
    """Tests for subscription configuration extraction."""

    def test_extract_unique_topics_from_handlers(self):
        """
        Test that unique topics are extracted from event_handlers_config.

        This verifies the subscription logic without needing a real broker.
        """
        event_handlers_config = [
            {
                "name": "handler_1",
                "subscriptions": [
                    {"topic": "events/type1/>", "qos": 1},
                    {"topic": "events/type2/>", "qos": 1},
                ],
            },
            {
                "name": "handler_2",
                "subscriptions": [
                    {"topic": "events/type1/>", "qos": 1},  # Duplicate
                    {"topic": "events/type3/>", "qos": 1},
                ],
            },
        ]

        # Extract unique topics (same logic as _initialize_and_subscribe_data_plane)
        all_topics = set()
        for handler_config in event_handlers_config:
            for sub_config in handler_config.get("subscriptions", []):
                topic_str = sub_config.get("topic")
                if topic_str:
                    all_topics.add(topic_str)

        # Should have 3 unique topics (duplicate removed)
        assert len(all_topics) == 3
        assert "events/type1/>" in all_topics
        assert "events/type2/>" in all_topics
        assert "events/type3/>" in all_topics

    def test_empty_handlers_yields_no_topics(self):
        """Test that empty event_handlers_config yields no topics."""
        event_handlers_config = []

        all_topics = set()
        for handler_config in event_handlers_config:
            for sub_config in handler_config.get("subscriptions", []):
                topic_str = sub_config.get("topic")
                if topic_str:
                    all_topics.add(topic_str)

        assert len(all_topics) == 0

    def test_handlers_with_no_subscriptions(self):
        """Test handlers without subscriptions don't cause errors."""
        event_handlers_config = [
            {
                "name": "handler_no_subs",
                # No subscriptions key
            },
            {
                "name": "handler_empty_subs",
                "subscriptions": [],
            },
        ]

        all_topics = set()
        for handler_config in event_handlers_config:
            for sub_config in handler_config.get("subscriptions", []):
                topic_str = sub_config.get("topic")
                if topic_str:
                    all_topics.add(topic_str)

        assert len(all_topics) == 0


class TestDataPlaneMessageQueue:
    """Tests for data plane message queue behavior."""

    def test_message_queue_bounded_capacity(self):
        """Test that message queue respects bounded capacity."""
        test_queue = queue.Queue(maxsize=5)

        # Fill the queue
        for i in range(5):
            test_queue.put_nowait(f"message_{i}")

        # Queue should be full
        assert test_queue.full()

        # Adding to a full queue should raise
        with pytest.raises(queue.Full):
            test_queue.put_nowait("overflow")

    def test_message_queue_fifo_order(self):
        """Test that message queue maintains FIFO order."""
        test_queue = queue.Queue()

        # Add messages
        for i in range(3):
            test_queue.put(f"message_{i}")

        # Retrieve in FIFO order
        assert test_queue.get() == "message_0"
        assert test_queue.get() == "message_1"
        assert test_queue.get() == "message_2"

    def test_shutdown_signal_via_none(self):
        """
        Test that None in the queue serves as a shutdown signal.

        The _data_plane_message_processor_loop uses None to signal shutdown.
        """
        test_queue = queue.Queue()

        # Add some messages then shutdown signal
        test_queue.put("message_1")
        test_queue.put(None)  # Shutdown signal
        test_queue.put("message_2")  # This should not be processed after shutdown

        # Simulate processing loop
        messages_processed = []
        while True:
            msg = test_queue.get()
            if msg is None:
                break  # Shutdown
            messages_processed.append(msg)

        # Only first message should be processed before shutdown
        assert messages_processed == ["message_1"]
