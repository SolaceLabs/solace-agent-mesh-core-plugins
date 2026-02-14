"""
Tests for Event Mesh Gateway message processing loop behavior.

These tests verify the message queue processing, shutdown handling,
and error recovery in the data plane message processor loop.
"""

import pytest
import asyncio
import queue
from unittest.mock import MagicMock, AsyncMock, patch

from solace_ai_connector.common.message import Message as SolaceMessage

from sam_event_mesh_gateway.component import EventMeshGatewayComponent


class TestMessageProcessorLoopBehavior:
    """Tests for _data_plane_message_processor_loop behavior."""

    @pytest.fixture
    def mock_gateway_for_processor(self):
        """Create a mock gateway component for processor loop testing."""
        component = MagicMock(spec=EventMeshGatewayComponent)
        component.log_identifier = "[TestGateway]"
        component.data_plane_message_queue = queue.Queue(maxsize=100)
        component.stop_signal = asyncio.Event()

        component.any_handler_defers_ack = False

        # Mock the message handler
        component._handle_incoming_solace_message = AsyncMock(return_value=True)

        # Bind the real processor loop
        component._data_plane_message_processor_loop = EventMeshGatewayComponent._data_plane_message_processor_loop.__get__(
            component, EventMeshGatewayComponent
        )

        return component

    @pytest.mark.asyncio
    async def test_processor_exits_on_none_message(self, mock_gateway_for_processor):
        """
        Test that the processor loop exits when it receives None (shutdown signal).
        """
        # Queue a None message (shutdown signal)
        mock_gateway_for_processor.data_plane_message_queue.put(None)

        # Run the processor - should exit quickly on None
        await asyncio.wait_for(
            mock_gateway_for_processor._data_plane_message_processor_loop(),
            timeout=2.0
        )

        # Handler should not have been called (None is not a real message)
        mock_gateway_for_processor._handle_incoming_solace_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_processor_exits_on_stop_signal(self, mock_gateway_for_processor):
        """
        Test that the processor loop exits when stop_signal is set.
        """
        # Set the stop signal
        mock_gateway_for_processor.stop_signal.set()

        # Run the processor - should exit on next iteration after timeout
        await asyncio.wait_for(
            mock_gateway_for_processor._data_plane_message_processor_loop(),
            timeout=3.0  # Allow time for one queue.get timeout (1s) + buffer
        )

        # No messages were queued, so handler should not be called
        mock_gateway_for_processor._handle_incoming_solace_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_processor_processes_single_message(self, mock_gateway_for_processor):
        """
        Test that the processor correctly processes a single message then exits.
        """
        # Create a real SolaceMessage
        solace_msg = SolaceMessage(
            payload={"data": "test"},
            topic="test/events/sample",
            user_properties={"user_id": "test_user"},
        )

        # Queue the message and then shutdown signal
        mock_gateway_for_processor.data_plane_message_queue.put(solace_msg)
        mock_gateway_for_processor.data_plane_message_queue.put(None)  # Shutdown

        # Run the processor
        await asyncio.wait_for(
            mock_gateway_for_processor._data_plane_message_processor_loop(),
            timeout=3.0
        )

        # Handler should have been called exactly once with our message
        mock_gateway_for_processor._handle_incoming_solace_message.assert_called_once_with(
            solace_msg
        )

    @pytest.mark.asyncio
    async def test_processor_processes_multiple_messages_in_order(self, mock_gateway_for_processor):
        """
        Test that the processor processes multiple messages in FIFO order.
        """
        # Create multiple messages
        messages = [
            SolaceMessage(
                payload={"index": i},
                topic=f"test/events/msg_{i}",
                user_properties={},
            )
            for i in range(3)
        ]

        # Queue all messages then shutdown
        for msg in messages:
            mock_gateway_for_processor.data_plane_message_queue.put(msg)
        mock_gateway_for_processor.data_plane_message_queue.put(None)

        # Run the processor
        await asyncio.wait_for(
            mock_gateway_for_processor._data_plane_message_processor_loop(),
            timeout=5.0
        )

        # All messages should have been processed
        assert mock_gateway_for_processor._handle_incoming_solace_message.call_count == 3

        # Verify FIFO order
        calls = mock_gateway_for_processor._handle_incoming_solace_message.call_args_list
        for i, call in enumerate(calls):
            processed_msg = call[0][0]
            assert processed_msg.get_topic() == f"test/events/msg_{i}"

    @pytest.mark.asyncio
    async def test_processor_continues_after_handler_exception(self, mock_gateway_for_processor):
        """
        Test that the processor continues processing after handler raises exception.
        """
        # Create messages
        msg1 = SolaceMessage(payload={"id": 1}, topic="test/events/1")
        msg2 = SolaceMessage(payload={"id": 2}, topic="test/events/2")

        # First call raises, second succeeds
        mock_gateway_for_processor._handle_incoming_solace_message.side_effect = [
            Exception("Handler error"),
            True
        ]

        # Queue messages and shutdown
        mock_gateway_for_processor.data_plane_message_queue.put(msg1)
        mock_gateway_for_processor.data_plane_message_queue.put(msg2)
        mock_gateway_for_processor.data_plane_message_queue.put(None)

        # Run the processor - should not raise despite handler exception
        await asyncio.wait_for(
            mock_gateway_for_processor._data_plane_message_processor_loop(),
            timeout=5.0
        )

        # Both messages should have been attempted
        assert mock_gateway_for_processor._handle_incoming_solace_message.call_count == 2

    @pytest.mark.asyncio
    async def test_processor_calls_task_done_for_real_messages(self, mock_gateway_for_processor):
        """
        Test that task_done is called after processing each real message.

        Note: The processor only calls task_done when solace_msg is not None.
        This matches the expected behavior since None is a shutdown signal,
        not a real message that needs tracking.
        """
        # Create a spy queue to track task_done calls
        original_queue = mock_gateway_for_processor.data_plane_message_queue

        task_done_count = {"count": 0}
        original_task_done = original_queue.task_done

        def tracking_task_done():
            task_done_count["count"] += 1
            return original_task_done()

        original_queue.task_done = tracking_task_done

        # Queue two real messages then shutdown
        msg1 = SolaceMessage(payload={"id": 1}, topic="test/events/1")
        msg2 = SolaceMessage(payload={"id": 2}, topic="test/events/2")
        original_queue.put(msg1)
        original_queue.put(msg2)
        original_queue.put(None)  # Shutdown - task_done NOT called for this

        # Run the processor
        await asyncio.wait_for(
            mock_gateway_for_processor._data_plane_message_processor_loop(),
            timeout=5.0
        )

        # task_done should have been called twice (once per real message)
        assert task_done_count["count"] == 2


class TestMessageProcessorCancellation:
    """Tests for processor loop cancellation behavior."""

    @pytest.fixture
    def mock_gateway_for_cancellation(self):
        """Create a mock gateway for cancellation testing."""
        component = MagicMock(spec=EventMeshGatewayComponent)
        component.log_identifier = "[TestGateway]"
        component.data_plane_message_queue = queue.Queue(maxsize=100)
        component.stop_signal = asyncio.Event()

        # Handler that tracks if it was called
        component.handler_called = False

        async def tracking_handler(msg):
            component.handler_called = True
            return True

        component._handle_incoming_solace_message = tracking_handler

        # Bind the real processor loop
        component._data_plane_message_processor_loop = EventMeshGatewayComponent._data_plane_message_processor_loop.__get__(
            component, EventMeshGatewayComponent
        )

        return component

    @pytest.mark.asyncio
    async def test_processor_exits_cleanly_when_stop_signal_set_during_wait(self, mock_gateway_for_cancellation):
        """
        Test that the processor exits cleanly when stop_signal is set while waiting.

        The processor catches CancelledError internally and exits gracefully,
        so the task completes without raising.
        """
        # Don't queue any messages - processor will block on queue.get timeout

        # Start the processor task
        task = asyncio.create_task(
            mock_gateway_for_cancellation._data_plane_message_processor_loop()
        )

        # Give it a moment to start waiting on the queue
        await asyncio.sleep(0.1)

        # Set the stop signal
        mock_gateway_for_cancellation.stop_signal.set()

        # Task should complete gracefully (not raise)
        await asyncio.wait_for(task, timeout=3.0)

        # Handler should not have been called (no messages queued)
        assert not mock_gateway_for_cancellation.handler_called


class TestMessageProcessorQueueBehavior:
    """Tests for queue-specific behavior in the processor."""

    def test_queue_get_with_timeout_raises_empty(self):
        """
        Test that queue.get with timeout raises queue.Empty.

        This is the behavior used by the processor loop to check stop_signal.
        """
        test_queue = queue.Queue()

        with pytest.raises(queue.Empty):
            test_queue.get(block=True, timeout=0.1)

    def test_queue_task_done_tracking(self):
        """
        Test that queue properly tracks task completion via join.
        """
        test_queue = queue.Queue()

        # Add items
        test_queue.put("item1")
        test_queue.put("item2")

        # Process items
        test_queue.get()
        test_queue.task_done()
        test_queue.get()
        test_queue.task_done()

        # Join should return immediately (all tasks done)
        # If this hangs, task_done wasn't called properly
        test_queue.join()

    def test_queue_put_nowait_to_full_queue(self):
        """
        Test that put_nowait to a full queue raises queue.Full.

        This is the behavior in EventForwarderComponent.
        """
        test_queue = queue.Queue(maxsize=1)
        test_queue.put("item")

        with pytest.raises(queue.Full):
            test_queue.put_nowait("overflow")


class TestSolaceMessageAccess:
    """Tests for SolaceMessage data access patterns used in the processor."""

    def test_solace_message_get_topic(self):
        """Test accessing topic from SolaceMessage."""
        msg = SolaceMessage(
            payload={"data": "test"},
            topic="test/events/sample/topic",
        )
        assert msg.get_topic() == "test/events/sample/topic"

    def test_solace_message_get_payload(self):
        """Test accessing payload from SolaceMessage."""
        payload = {"key": "value", "nested": {"data": 123}}
        msg = SolaceMessage(payload=payload)
        assert msg.get_payload() == payload

    def test_solace_message_get_user_properties(self):
        """Test accessing user properties from SolaceMessage."""
        user_props = {"user_id": "user123", "correlation_id": "corr-456"}
        msg = SolaceMessage(
            payload={},
            user_properties=user_props,
        )
        result = msg.get_user_properties()
        assert result["user_id"] == "user123"
        assert result["correlation_id"] == "corr-456"

    def test_solace_message_get_data_with_expression(self):
        """Test using get_data with expression paths."""
        msg = SolaceMessage(
            payload={"user": {"name": "John", "id": 123}},
            topic="events/users/create",
            user_properties={"source": "api"},
        )

        # Access nested payload data
        assert msg.get_data("input.payload:user.name") == "John"
        assert msg.get_data("input.payload:user.id") == 123

        # Access topic
        assert msg.get_data("input.topic:") == "events/users/create"

        # Access user properties
        assert msg.get_data("input.user_properties:source") == "api"

    def test_solace_message_get_data_missing_path_returns_none(self):
        """Test that get_data returns None for missing paths."""
        msg = SolaceMessage(payload={"exists": True})

        result = msg.get_data("input.payload:does_not_exist")
        assert result is None
