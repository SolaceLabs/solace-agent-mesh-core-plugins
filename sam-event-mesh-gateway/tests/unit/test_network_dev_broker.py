"""Comprehensive tests for the network dev broker implementation.

Tests verify:
1. Basic connectivity and message exchange
2. Multiple clients with message routing
3. Subscribe/unsubscribe operations
4. Reconnection handling
5. Large payloads and special characters
6. Timeout behavior
"""

import sys
import os
import subprocess
import time
import threading
import json
import pytest

# Add solace-ai-connector to path
SAC_PATH = "/Users/edfunnekotter/github/solace-ai-connector/src"
sys.path.insert(0, SAC_PATH)

from solace_ai_connector.common.messaging.dev_broker_messaging import DevBroker
from solace_ai_connector.common.messaging.network_dev_broker import NetworkDevBroker


class MockFlowLockManager:
    """Mock lock manager for testing."""
    def __init__(self):
        self._locks = {}

    def get_lock(self, name):
        if name not in self._locks:
            self._locks[name] = threading.Lock()
        return self._locks[name]


class MockFlowKVStore:
    """Mock KV store for testing."""
    def __init__(self):
        self._store = {}

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value):
        self._store[key] = value


@pytest.fixture
def broker_server():
    """Create a DevBroker with network server enabled."""
    lock_manager = MockFlowLockManager()
    kv_store = MockFlowKVStore()

    broker_properties = {
        "queue_name": "server-queue",
        "subscriptions": [{"topic": "from-client/>"}],
    }

    broker = DevBroker(broker_properties, lock_manager, kv_store)
    broker.connect()
    port = broker.start_server(port=0)  # Auto-assign port

    yield broker, port

    broker.stop_server()
    broker.disconnect()


@pytest.fixture
def network_client(broker_server):
    """Create a NetworkDevBroker client connected to the server."""
    broker, port = broker_server

    client_properties = {
        "dev_broker_host": "localhost",
        "dev_broker_port": port,
        "queue_name": "client-queue",
        "subscriptions": [{"topic": "to-client/>"}],
    }

    client = NetworkDevBroker(client_properties)
    client.connect()

    yield client

    client.disconnect()


class TestBasicConnectivity:
    """Test basic connection and disconnection."""

    def test_client_connects_successfully(self, broker_server):
        """Test that a client can connect to the server."""
        broker, port = broker_server

        client_properties = {
            "dev_broker_host": "localhost",
            "dev_broker_port": port,
            "queue_name": "test-queue",
            "subscriptions": [],
        }

        client = NetworkDevBroker(client_properties)
        client.connect()

        assert client._connected is True
        client.disconnect()
        assert client._connected is False

    def test_client_reconnect(self, broker_server):
        """Test that a client can disconnect and reconnect."""
        broker, port = broker_server

        client_properties = {
            "dev_broker_host": "localhost",
            "dev_broker_port": port,
            "queue_name": "test-queue",
            "subscriptions": [],
        }

        client = NetworkDevBroker(client_properties)

        # First connection
        client.connect()
        assert client._connected is True
        client.disconnect()

        # Second connection
        client.connect()
        assert client._connected is True
        client.disconnect()

    def test_connection_status(self, network_client):
        """Test connection status reporting."""
        from solace_ai_connector.common.messaging.network_dev_broker import NetworkConnectionStatus

        status = network_client.get_connection_status()
        assert status == NetworkConnectionStatus.CONNECTED


class TestMessageExchange:
    """Test message sending and receiving."""

    def test_client_to_server_message(self, broker_server, network_client):
        """Test sending a message from client to server."""
        broker, port = broker_server

        # Client sends message
        network_client.send_message(
            "from-client/test",
            {"data": "hello server"},
            {"header": "value"}
        )

        # Server receives message
        msg = broker.receive_message(2000, "server-queue")
        assert msg is not None
        assert msg["topic"] == "from-client/test"
        assert msg["payload"]["data"] == "hello server"
        assert msg["user_properties"]["header"] == "value"

    def test_server_to_client_message(self, broker_server, network_client):
        """Test sending a message from server to client."""
        broker, port = broker_server

        # Server sends message (client must be subscribed first)
        broker.send_message(
            "to-client/test",
            {"data": "hello client"},
            {"source": "server"}
        )

        # Client receives message
        msg = network_client.receive_message(2000, "client-queue")
        assert msg is not None
        assert msg["topic"] == "to-client/test"
        assert msg["payload"]["data"] == "hello client"

    def test_receive_timeout(self, network_client):
        """Test that receive times out when no message available."""
        msg = network_client.receive_message(500, "client-queue")
        assert msg is None

    def test_large_payload(self, broker_server, network_client):
        """Test sending a large payload."""
        broker, port = broker_server

        # Create a large payload (100KB)
        large_data = "x" * 100000
        network_client.send_message(
            "from-client/large",
            {"data": large_data},
        )

        msg = broker.receive_message(2000, "server-queue")
        assert msg is not None
        assert len(msg["payload"]["data"]) == 100000

    def test_special_characters_in_payload(self, broker_server, network_client):
        """Test payloads with special characters."""
        broker, port = broker_server

        special_chars = {
            "unicode": "Hello 世界 🌍",
            "newlines": "line1\nline2\r\nline3",
            "quotes": 'He said "hello"',
            "backslash": "path\\to\\file",
            "json_chars": '{"nested": "json"}',
        }

        network_client.send_message("from-client/special", special_chars)

        msg = broker.receive_message(2000, "server-queue")
        assert msg is not None
        assert msg["payload"] == special_chars


class TestSubscriptions:
    """Test subscription management."""

    def test_add_subscription_after_connect(self, broker_server):
        """Test adding a subscription after connecting."""
        broker, port = broker_server

        client_properties = {
            "dev_broker_host": "localhost",
            "dev_broker_port": port,
            "queue_name": "sub-test-queue",
            "subscriptions": [],  # No initial subscriptions
        }

        client = NetworkDevBroker(client_properties)
        client.connect()

        # Add subscription
        result = client.add_topic_to_queue("dynamic/topic/>", "sub-test-queue")
        assert result is True

        # Send a message to that topic
        broker.send_message("dynamic/topic/test", {"data": "dynamic"})

        # Should receive it
        msg = client.receive_message(2000, "sub-test-queue")
        assert msg is not None
        assert msg["topic"] == "dynamic/topic/test"

        client.disconnect()

    def test_remove_subscription(self, broker_server):
        """Test removing a subscription."""
        broker, port = broker_server

        client_properties = {
            "dev_broker_host": "localhost",
            "dev_broker_port": port,
            "queue_name": "unsub-test-queue",
            "subscriptions": [{"topic": "removable/>"}],
        }

        client = NetworkDevBroker(client_properties)
        client.connect()

        # Verify subscription works
        broker.send_message("removable/test", {"data": "before"})
        msg = client.receive_message(2000, "unsub-test-queue")
        assert msg is not None

        # Remove subscription
        result = client.remove_topic_from_queue("removable/>", "unsub-test-queue")
        assert result is True

        # Send another message - should not receive
        broker.send_message("removable/test2", {"data": "after"})
        msg = client.receive_message(500, "unsub-test-queue")
        assert msg is None

        client.disconnect()

    def test_wildcard_subscriptions(self, broker_server):
        """Test wildcard subscription patterns."""
        broker, port = broker_server

        client_properties = {
            "dev_broker_host": "localhost",
            "dev_broker_port": port,
            "queue_name": "wildcard-queue",
            "subscriptions": [
                {"topic": "wild/*/test"},  # Single level wildcard
                {"topic": "deep/>"},       # Multi-level wildcard
            ],
        }

        client = NetworkDevBroker(client_properties)
        client.connect()

        # Test single-level wildcard
        broker.send_message("wild/foo/test", {"match": "single"})
        msg = client.receive_message(2000, "wildcard-queue")
        assert msg is not None
        assert msg["topic"] == "wild/foo/test"

        # Test multi-level wildcard
        broker.send_message("deep/a/b/c", {"match": "multi"})
        msg = client.receive_message(2000, "wildcard-queue")
        assert msg is not None
        assert msg["topic"] == "deep/a/b/c"

        # Test non-matching topic
        broker.send_message("wild/foo/bar/test", {"match": "none"})  # Doesn't match */
        msg = client.receive_message(500, "wildcard-queue")
        # This shouldn't match because * only matches one level
        assert msg is None

        client.disconnect()


class TestMultipleClients:
    """Test multiple clients connecting simultaneously."""

    def test_two_clients_different_subscriptions(self, broker_server):
        """Test two clients with different subscriptions."""
        broker, port = broker_server

        # Client 1
        client1_props = {
            "dev_broker_host": "localhost",
            "dev_broker_port": port,
            "queue_name": "client1-queue",
            "subscriptions": [{"topic": "client1/>"}],
        }
        client1 = NetworkDevBroker(client1_props)
        client1.connect()

        # Client 2
        client2_props = {
            "dev_broker_host": "localhost",
            "dev_broker_port": port,
            "queue_name": "client2-queue",
            "subscriptions": [{"topic": "client2/>"}],
        }
        client2 = NetworkDevBroker(client2_props)
        client2.connect()

        # Send to client1
        broker.send_message("client1/msg", {"to": "client1"})

        # Send to client2
        broker.send_message("client2/msg", {"to": "client2"})

        # Each client should only get their message
        msg1 = client1.receive_message(2000, "client1-queue")
        assert msg1 is not None
        assert msg1["payload"]["to"] == "client1"

        msg2 = client2.receive_message(2000, "client2-queue")
        assert msg2 is not None
        assert msg2["payload"]["to"] == "client2"

        # Neither should have extra messages
        assert client1.receive_message(500, "client1-queue") is None
        assert client2.receive_message(500, "client2-queue") is None

        client1.disconnect()
        client2.disconnect()

    def test_broadcast_to_multiple_clients(self, broker_server):
        """Test broadcasting a message to multiple clients."""
        broker, port = broker_server

        clients = []
        for i in range(3):
            props = {
                "dev_broker_host": "localhost",
                "dev_broker_port": port,
                "queue_name": f"broadcast-queue-{i}",
                "subscriptions": [{"topic": "broadcast/>"}],
            }
            client = NetworkDevBroker(props)
            client.connect()
            clients.append(client)

        # Broadcast message
        broker.send_message("broadcast/all", {"data": "for everyone"})

        # All clients should receive it
        for i, client in enumerate(clients):
            msg = client.receive_message(2000, f"broadcast-queue-{i}")
            assert msg is not None, f"Client {i} didn't receive broadcast"
            assert msg["payload"]["data"] == "for everyone"

        for client in clients:
            client.disconnect()


class TestSubprocessIntegration:
    """Test with actual subprocess to simulate container scenario."""

    def test_subprocess_client(self, broker_server):
        """Test a client running in a subprocess."""
        broker, port = broker_server

        client_script = f'''
import sys
sys.path.insert(0, "{SAC_PATH}")

from solace_ai_connector.common.messaging.network_dev_broker import NetworkDevBroker

props = {{
    "dev_broker_host": "localhost",
    "dev_broker_port": {port},
    "queue_name": "subprocess-queue",
    "subscriptions": [{{"topic": "to-subprocess/>"}}],
}}

client = NetworkDevBroker(props)
client.connect()

# Send message to server
client.send_message("from-client/subprocess", {{"source": "subprocess"}})

# Receive message from server
msg = client.receive_message(3000, "subprocess-queue")
if msg:
    print(f"RECEIVED: {{msg['payload']}}")
else:
    print("TIMEOUT")

client.disconnect()
print("DONE")
'''

        # Start subprocess
        proc = subprocess.Popen(
            [sys.executable, "-c", client_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Give subprocess time to connect and send
        time.sleep(0.5)

        # Check message from subprocess
        msg = broker.receive_message(2000, "server-queue")
        assert msg is not None
        assert msg["payload"]["source"] == "subprocess"

        # Send message to subprocess
        broker.send_message("to-subprocess/test", {"greeting": "hello subprocess"})

        # Wait for subprocess to complete
        stdout, stderr = proc.communicate(timeout=10)

        assert "RECEIVED:" in stdout
        assert "hello subprocess" in stdout
        assert "DONE" in stdout


class TestErrorHandling:
    """Test error conditions and edge cases."""

    def test_send_before_connect(self):
        """Test that sending before connect raises error."""
        client_props = {
            "dev_broker_host": "localhost",
            "dev_broker_port": 99999,  # Invalid port
            "queue_name": "test-queue",
            "subscriptions": [],
        }
        client = NetworkDevBroker(client_props)

        with pytest.raises(RuntimeError):
            client.send_message("topic", {"data": "test"})

    def test_receive_before_connect(self):
        """Test that receiving before connect raises error."""
        client_props = {
            "dev_broker_host": "localhost",
            "dev_broker_port": 99999,
            "queue_name": "test-queue",
            "subscriptions": [],
        }
        client = NetworkDevBroker(client_props)

        with pytest.raises(RuntimeError):
            client.receive_message(1000, "test-queue")

    def test_connect_to_invalid_port(self):
        """Test connection to invalid port fails gracefully."""
        client_props = {
            "dev_broker_host": "localhost",
            "dev_broker_port": 1,  # Invalid/unavailable port
            "queue_name": "test-queue",
            "subscriptions": [],
        }
        client = NetworkDevBroker(client_props)

        with pytest.raises(Exception):
            client.connect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
