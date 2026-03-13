"""
Basic functionality tests for the Event Mesh Gateway.
"""

import pytest
import asyncio
import time
from typing import Dict, Any

from sam_test_infrastructure.llm_server.server import TestLLMServer
from sam_test_infrastructure.event_mesh_test_server import EventMeshTestServer
from sam_event_mesh_gateway.component import EventMeshGatewayComponent
from solace_agent_mesh.agent.sac.component import SamAgentComponent


class TestBasicFunctionality:
    """Test basic Event Mesh Gateway functionality."""
    
    def test_gateway_initialization(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_agent_component: SamAgentComponent,
    ):
        """Test that the gateway initializes correctly."""
        assert event_mesh_gateway_component is not None
        assert event_mesh_gateway_component.gateway_id == "TestEventMeshGateway_01"
        assert test_agent_component is not None
        assert test_agent_component.agent_name == "TestEventMeshAgent"
    
    def test_event_mesh_test_server_running(
        self,
        event_mesh_test_server: EventMeshTestServer,
    ):
        """Test that the event mesh test server is running."""
        assert event_mesh_test_server.is_running()
        stats = event_mesh_test_server.get_statistics()
        assert stats["running"] is True
        assert "broker_url" in event_mesh_test_server.sac_config
    
    def test_llm_server_running(
        self,
        test_llm_server: TestLLMServer,
    ):
        """Test that the LLM server is running."""
        assert test_llm_server.started
        assert test_llm_server.url.startswith("http://")
    
    def test_message_publishing_to_broker(
        self,
        event_mesh_test_server: EventMeshTestServer,
    ):
        """Test basic message publishing to the test broker."""
        # Publish a test message
        message = event_mesh_test_server.publish_json_message(
            topic="test/basic/message",
            json_data={"message": "Hello World", "test_id": "basic_test"}
        )
        
        assert message is not None
        assert message.topic == "test/basic/message"
        assert message.payload["message"] == "Hello World"
        
        # Check that the message was captured
        captured_messages = event_mesh_test_server.get_captured_messages()
        assert len(captured_messages) > 0
        
        # Find our message
        our_message = None
        for msg in captured_messages:
            if msg.topic == "test/basic/message":
                our_message = msg
                break
        
        assert our_message is not None
        assert our_message.payload["test_id"] == "basic_test"
    
    def test_topic_subscription_and_routing(
        self,
        event_mesh_test_server: EventMeshTestServer,
    ):
        """Test topic subscription and message routing."""
        received_messages = []
        
        def message_callback(topic: str, message):
            received_messages.append((topic, message))
        
        # Subscribe to a topic pattern
        success = event_mesh_test_server.subscribe_to_topic(
            client_id="test_client",
            topic_pattern="test/routing/>",
            callback=message_callback
        )
        assert success
        
        # Publish messages to matching topics
        event_mesh_test_server.publish_text_message(
            topic="test/routing/message1",
            text="First message"
        )
        
        event_mesh_test_server.publish_text_message(
            topic="test/routing/message2",
            text="Second message"
        )
        
        # Publish to non-matching topic
        event_mesh_test_server.publish_text_message(
            topic="other/topic",
            text="Should not be received"
        )
        
        # Give some time for message delivery
        time.sleep(0.1)
        
        # Check received messages
        assert len(received_messages) == 2
        
        topics = [msg[0] for msg in received_messages]
        assert "test/routing/message1" in topics
        assert "test/routing/message2" in topics
        assert "other/topic" not in topics
    
    def test_gateway_event_handler_configuration(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """Test that the gateway has the correct event handler configuration."""
        # Check that event handlers are configured
        assert hasattr(event_mesh_gateway_component, 'event_handlers_config')
        assert len(event_mesh_gateway_component.event_handlers_config) > 0
        
        # Check the test event handler
        test_handler = None
        for handler in event_mesh_gateway_component.event_handlers_config:
            if handler.get("name") == "test_event_handler":
                test_handler = handler
                break
        
        assert test_handler is not None
        assert test_handler["target_agent_name"] == "TestEventMeshAgent"
        assert len(test_handler["subscriptions"]) > 0
        assert test_handler["subscriptions"][0]["topic"] == "test/events/>"
    
    def test_gateway_output_handler_configuration(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """Test that the gateway has the correct output handler configuration."""
        # Check that output handlers are configured
        assert hasattr(event_mesh_gateway_component, 'output_handlers_config')
        assert len(event_mesh_gateway_component.output_handlers_config) > 0
        
        # Check for success and error handlers
        handler_names = [h.get("name") for h in event_mesh_gateway_component.output_handlers_config]
        assert "test_success_handler" in handler_names
        assert "test_error_handler" in handler_names
    
    def test_config_builder_fixture(
        self,
        test_config_builder,
        event_mesh_test_server: EventMeshTestServer,
    ):
        """Test the configuration builder fixture."""
        config = (test_config_builder
                 .with_broker_config(event_mesh_test_server.sac_config)
                 .with_event_handler(
                     name="dynamic_handler",
                     subscriptions=[{"topic": "dynamic/test/>"}],
                     input_expression="input.payload.content",
                     target_agent_name="TestAgent"
                 )
                 .with_output_handler(
                     name="dynamic_output",
                     topic_expression="dynamic/output/{{input.topic}}",
                     payload_expression="input.payload.result"
                 )
                 .build())
        
        assert config["gateway_id"] == "TestEventMeshGateway_Dynamic"
        assert "event_handlers" in config
        assert "output_handlers" in config
        assert "event_mesh_broker_config" in config
        
        # Check event handler
        handler = config["event_handlers"][0]
        assert handler["name"] == "dynamic_handler"
        assert handler["subscriptions"][0]["topic"] == "dynamic/test/>"
        
        # Check output handler
        output_handler = config["output_handlers"][0]
        assert output_handler["name"] == "dynamic_output"
    
    def test_message_expectation_functionality(
        self,
        event_mesh_test_server: EventMeshTestServer,
    ):
        """Test message expectation and waiting functionality."""
        # Start waiting for a message in the background
        async def wait_for_message():
            return event_mesh_test_server.expect_message_on_topic(
                topic_pattern="test/expect/*",
                timeout_seconds=2.0,
                payload_filter=lambda payload: "expected" in str(payload)
            )
        
        # Create an async task to wait for the message
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Start the waiting task
        wait_task = loop.create_task(wait_for_message())
        
        # Give it a moment to start waiting
        time.sleep(0.1)
        
        # Publish the expected message
        event_mesh_test_server.publish_text_message(
            topic="test/expect/message",
            text="This is the expected message"
        )
        
        # Wait for the result
        try:
            result = loop.run_until_complete(asyncio.wait_for(wait_task, timeout=3.0))
            assert result is not None
            assert result.topic == "test/expect/message"
            assert "expected" in result.payload
        finally:
            loop.close()
    
    def test_statistics_collection(
        self,
        event_mesh_test_server: EventMeshTestServer,
    ):
        """Test that statistics are collected correctly."""
        # Clear any existing messages
        event_mesh_test_server.clear_received_messages()
        
        # Get initial stats
        initial_stats = event_mesh_test_server.get_statistics()
        initial_published = initial_stats.get("messages_published", 0)
        
        # Publish some messages
        for i in range(3):
            event_mesh_test_server.publish_text_message(
                topic=f"test/stats/message{i}",
                text=f"Message {i}"
            )
        
        # Get updated stats
        updated_stats = event_mesh_test_server.get_statistics()
        
        # Check that message count increased
        assert updated_stats["messages_published"] >= initial_published + 3
        assert updated_stats["running"] is True
        assert "uptime_seconds" in updated_stats
        assert updated_stats["uptime_seconds"] > 0
