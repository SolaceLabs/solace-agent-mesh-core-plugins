import unittest
from solace_ai_connector.test_utils.utils_for_test_files import create_test_flows


class TestEventMeshInput(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        config = {
            "flows": [
                {
                    "name": "test_flow",
                    "components": [
                        {
                            "component_name": "solace_event_mesh_input",
                            "component_module": "src.gateways.solace_event_mesh.solace_event_mesh_input",
                            "component_config": {
                                "event_handlers": [
                                    {
                                        "name": "jira_event_handler",
                                        "subscriptions": [
                                            {
                                                "topic": "ed_test/jira/issue/create/>",
                                                "qos": 1,
                                            }
                                        ],
                                        "input_expression": "template:Raise a standalone Jira Task in the EPT project that tracks the work to triage this newly created issue below. It must be in the EPT project and it should not link to any issues. Here is the new issue:{{text://input.payload}}",
                                        "payload_encoding": "utf-8",
                                        "payload_format": "json",
                                        "output_handler_name": "jira_output_handler",
                                    },
                                    {
                                        "name": "rt_event_handler",
                                        "subscriptions": [
                                            {
                                                "topic": "ed_test/rt/issue/created/>",
                                                "qos": 1,
                                            },
                                            {
                                                "topic": "ed_test/rt/issue/updated/>",
                                                "qos": 1,
                                            },
                                        ],
                                        "payload_encoding": "utf-8",
                                        "payload_format": "json",
                                        "attach_payload_as_file": True,
                                        "input_expression": "template:Do the XYZ processing on this file",
                                    },
                                ],
                                "output_handler_name_dest_expression": "input.user_properties:output_handler_name",
                                "identity": "test@example.com",
                                "broker_type": "dev_broker",
                                "broker_url": "tcp://localhost:55555",
                                "broker_username": "default",
                                "broker_password": "default",
                                "broker_vpn": "default",
                                "broker_queue_name": "test_queue",
                                "broker_subscriptions": [{"topic": "test/#", "qos": 1}],
                            },
                        }
                    ],
                }
            ]
        }
        self.connector, self.flows = create_test_flows(config)
        self.event_mesh_input = self.flows[0]["flow"].component_groups[0][0]

    def tearDown(self):
        if self.connector:
            self.connector.stop()

    def test_process_message_matching_handler(self):
        broker_message = {
            "topic": "ed_test/jira/issue/create/123",
            "payload": b'{"issue": "Test issue"}',
            "user_properties": {},
        }

        result = self.event_mesh_input.process_message(broker_message)

        self.assertIsNotNone(result)
        self.assertEqual(result.get_topic(), "ed_test/jira/issue/create/123")
        self.assertIn("Raise a standalone Jira Task", result.get_payload()["text"])
        self.assertEqual(
            result.get_user_properties()["output_handler_name"], "jira_output_handler"
        )
        self.assertEqual(result.get_user_properties()["identity"], "test@example.com")

    def test_process_message_no_matching_handler(self):
        broker_message = {
            "topic": "unmatched/topic",
            "payload": b'{"data": "Test data"}',
            "user_properties": {},
        }

        result = self.event_mesh_input.process_message(broker_message)

        self.assertIsNone(result)

    def test_process_message_attach_payload_as_file(self):
        broker_message = {
            "topic": "ed_test/rt/issue/created/456",
            "payload": b'{"issue": "Test RT issue"}',
            "user_properties": {},
        }

        result = self.event_mesh_input.process_message(broker_message)

        self.assertIsNotNone(result)
        self.assertEqual(result.get_topic(), "ed_test/rt/issue/created/456")
        self.assertEqual(
            result.get_payload()["text"], "Do the XYZ processing on this file"
        )
        self.assertEqual(len(result.get_payload()["files"]), 1)
        self.assertEqual(
            result.get_payload()["files"][0]["content"], b'{"issue": "Test RT issue"}'
        )

    def test_process_message_invalid_input_expression(self):
        self.event_mesh_input.event_handlers[0]["input_expression"] = (
            "invalid://expression"
        )
        broker_message = {
            "topic": "ed_test/jira/issue/create/789",
            "payload": b'{"issue": "Test issue"}',
            "user_properties": {},
        }

        result = self.event_mesh_input.process_message(broker_message)

        self.assertIsNone(result)

    def test_process_message_missing_input_expression(self):
        del self.event_mesh_input.event_handlers[0]["input_expression"]
        broker_message = {
            "topic": "ed_test/jira/issue/create/101",
            "payload": b'{"issue": "Test issue"}',
            "user_properties": {},
        }

        result = self.event_mesh_input.process_message(broker_message)

        self.assertIsNone(result)

    def test_process_message_different_encodings(self):
        test_cases = [
            ("utf-8", "json", b'{"key": "value"}', {"key": "value"}),
            ("utf-8", "text", b"plain text", "plain text"),
            ("base64", "json", b"eyJrZXkiOiAidmFsdWUifQ==", {"key": "value"}),
        ]

        for encoding, format, payload, expected in test_cases:
            with self.subTest(encoding=encoding, format=format):
                self.event_mesh_input.event_handlers[0]["payload_encoding"] = encoding
                self.event_mesh_input.event_handlers[0]["payload_format"] = format
                broker_message = {
                    "topic": "ed_test/jira/issue/create/202",
                    "payload": payload,
                    "user_properties": {},
                }

                result = self.event_mesh_input.process_message(broker_message)

                self.assertIsNotNone(result)
                self.assertIn(str(expected), result.get_payload()["text"])

    def test_process_message_custom_user_properties(self):
        broker_message = {
            "topic": "ed_test/jira/issue/create/303",
            "payload": b'{"issue": "Test issue"}',
            "user_properties": {"custom_prop": "custom_value"},
        }

        result = self.event_mesh_input.process_message(broker_message)

        self.assertIsNotNone(result)
        self.assertEqual(result.get_user_properties()["custom_prop"], "custom_value")
        self.assertIn("session_id", result.get_user_properties())
        self.assertEqual(result.get_user_properties()["input_type"], "event_mesh")

    def test_process_message_no_output_handler_name(self):
        # Remove the output_handler_name from the first event handler
        del self.event_mesh_input.event_handlers[0]["output_handler_name"]

        broker_message = {
            "topic": "ed_test/jira/issue/create/404",
            "payload": b'{"issue": "Test issue without output handler"}',
            "user_properties": {},
        }

        result = self.event_mesh_input.process_message(broker_message)

        self.assertIsNotNone(result)
        self.assertEqual(result.get_topic(), "ed_test/jira/issue/create/404")
        self.assertIn("Raise a standalone Jira Task", result.get_payload()["text"])
        self.assertNotIn("output_handler_name", result.get_user_properties())


if __name__ == "__main__":
    unittest.main()
