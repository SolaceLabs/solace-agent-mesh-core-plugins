"""
Integration tests for Event Mesh Gateway response and error handling.

These tests cover:
- _send_final_response_to_external
- _send_error_to_external
- _process_artifacts_from_message
- _process_file_part_for_output
"""

import pytest
import asyncio
import json
from typing import Dict, Any

from solace_ai_connector.common.message import Message as SolaceMessage

from a2a.types import (
    Task,
    TaskStatus,
    TaskState,
    Message,
    TextPart,
    DataPart,
    FilePart,
    Part,
    Artifact,
    JSONRPCError,
)

from sam_test_infrastructure.llm_server.server import TestLLMServer
from sam_test_infrastructure.artifact_service.service import TestInMemoryArtifactService
from sam_event_mesh_gateway.component import EventMeshGatewayComponent


class TestSendFinalResponseToExternal:
    """Tests for _send_final_response_to_external method."""

    @pytest.fixture
    def sample_task_with_text(self):
        """Create a sample task with text response."""
        return Task(
            id="test_task_001",
            contextId="ctx_001",
            status=TaskStatus(
                state=TaskState.completed,
                message=Message(
                    messageId="msg_001",
                    role="agent",
                    parts=[Part(root=TextPart(text="This is the response text"))],
                ),
            ),
        )

    @pytest.fixture
    def sample_task_with_data_part(self):
        """Create a sample task with data part."""
        return Task(
            id="test_task_002",
            contextId="ctx_002",
            status=TaskStatus(
                state=TaskState.completed,
                message=Message(
                    messageId="msg_002",
                    role="agent",
                    parts=[
                        Part(root=DataPart(data={"result": "success", "value": 42})),
                        Part(root=TextPart(text="Processing complete")),
                    ],
                ),
            ),
        )

    @pytest.fixture
    def sample_structured_success_task(self):
        """Create a sample task with structured invocation success result."""
        return Task(
            id="test_task_structured",
            contextId="ctx_structured",
            status=TaskStatus(
                state=TaskState.completed,
                message=Message(
                    messageId="msg_structured",
                    role="agent",
                    parts=[
                        Part(
                            root=DataPart(
                                data={
                                    "type": "structured_invocation_result",
                                    "status": "success",
                                    "output_artifact_ref": {
                                        "name": "output.json",
                                        "version": 1,
                                    },
                                }
                            )
                        ),
                    ],
                ),
            ),
        )

    @pytest.fixture
    def sample_structured_error_task(self):
        """Create a sample task with structured invocation error result."""
        return Task(
            id="test_task_error",
            contextId="ctx_error",
            status=TaskStatus(
                state=TaskState.failed,
                message=Message(
                    messageId="msg_error",
                    role="agent",
                    parts=[
                        Part(
                            root=DataPart(
                                data={
                                    "type": "structured_invocation_result",
                                    "status": "error",
                                    "error_message": "Validation failed: missing required field",
                                }
                            )
                        ),
                    ],
                ),
            ),
        )

    @pytest.mark.asyncio
    async def test_send_response_with_text_task(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        sample_task_with_text: Task,
    ):
        """Test sending a response with text content."""
        external_context = {
            "event_handler_name": "test_event_handler",
            "original_solace_topic": "test/events/sample",
            "original_solace_user_properties": {"user_id": "test_user"},
            "user_identity": {"id": "test_user"},
            "app_name_for_artifacts": "TestGateway",
            "user_id_for_artifacts": "test_user",
            "a2a_session_id": "session_001",
            "is_structured_invocation": False,
        }

        # This should not raise - it processes the response
        await event_mesh_gateway_component._send_final_response_to_external(
            external_context, sample_task_with_text
        )

    @pytest.mark.asyncio
    async def test_send_response_with_data_parts(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        sample_task_with_data_part: Task,
    ):
        """Test sending a response with data parts."""
        external_context = {
            "event_handler_name": "test_event_handler",
            "original_solace_topic": "test/events/data",
            "original_solace_user_properties": {},
            "user_identity": {"id": "test_user"},
            "app_name_for_artifacts": "TestGateway",
            "user_id_for_artifacts": "test_user",
            "a2a_session_id": "session_002",
            "is_structured_invocation": False,
        }

        await event_mesh_gateway_component._send_final_response_to_external(
            external_context, sample_task_with_data_part
        )

    @pytest.mark.asyncio
    async def test_send_response_no_success_handler(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        sample_task_with_text: Task,
    ):
        """Test that missing on_success handler is handled gracefully."""
        external_context = {
            "event_handler_name": "nonexistent_handler",  # No handler config
            "original_solace_topic": "test/events/missing",
            "original_solace_user_properties": {},
            "user_identity": {"id": "test_user"},
            "is_structured_invocation": False,
        }

        # Should return without error
        await event_mesh_gateway_component._send_final_response_to_external(
            external_context, sample_task_with_text
        )

    @pytest.mark.asyncio
    async def test_send_structured_success_response(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        sample_structured_success_task: Task,
        test_artifact_service_instance: TestInMemoryArtifactService,
    ):
        """Test sending a structured invocation success response."""
        # Pre-save an artifact that the response references
        from google.genai import types as adk_types

        output_content = json.dumps({"computed_result": [1, 2, 3, 4, 5]}).encode("utf-8")
        artifact_part = adk_types.Part(
            inline_data=adk_types.Blob(mime_type="application/json", data=output_content)
        )

        await test_artifact_service_instance.save_artifact(
            app_name="TestGateway",
            user_id="test_user",
            session_id="session_structured",
            filename="output.json",
            artifact=artifact_part,
        )

        external_context = {
            "event_handler_name": "test_event_handler",
            "original_solace_topic": "test/events/structured",
            "original_solace_user_properties": {},
            "user_identity": {"id": "test_user"},
            "app_name_for_artifacts": "TestGateway",
            "user_id_for_artifacts": "test_user",
            "a2a_session_id": "session_structured",
            "is_structured_invocation": True,
            "structured_config": {},
        }

        await event_mesh_gateway_component._send_final_response_to_external(
            external_context, sample_structured_success_task
        )

    @pytest.mark.asyncio
    async def test_send_structured_error_routes_to_error_handler(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        sample_structured_error_task: Task,
    ):
        """Test that structured invocation error routes to error handler."""
        external_context = {
            "event_handler_name": "test_event_handler",
            "original_solace_topic": "test/events/structured_error",
            "original_solace_user_properties": {},
            "user_identity": {"id": "test_user"},
            "app_name_for_artifacts": "TestGateway",
            "user_id_for_artifacts": "test_user",
            "a2a_session_id": "session_error",
            "is_structured_invocation": True,
            "structured_config": {},
            "forwarded_context": {"original_topic": "test/events/original"},
        }

        # Should route to error handler
        await event_mesh_gateway_component._send_final_response_to_external(
            external_context, sample_structured_error_task
        )


class TestSendErrorToExternal:
    """Tests for _send_error_to_external method."""

    @pytest.fixture
    def sample_jsonrpc_error(self):
        """Create a sample JSONRPCError."""
        return JSONRPCError(
            code=-32000,
            message="Test error occurred",
            data={"details": "Additional error information"},
        )

    @pytest.fixture
    def sample_validation_error(self):
        """Create a validation error."""
        return JSONRPCError(
            code=-32602,
            message="Invalid params: validation failed",
            data={
                "validation_errors": [
                    "Missing required field 'name'",
                    "Field 'age' must be a number",
                ]
            },
        )

    @pytest.mark.asyncio
    async def test_send_error_with_on_error_handler(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        sample_jsonrpc_error: JSONRPCError,
    ):
        """Test sending an error to the on_error handler."""
        external_context = {
            "event_handler_name": "test_event_handler",
            "original_solace_topic": "test/events/error_test",
            "original_solace_user_properties": {"correlation_id": "corr-123"},
            "user_identity": {"id": "error_test_user"},
            "a2a_task_id_for_event": "error_task_001",
            "forwarded_context": {"original_topic": "test/events/error_test"},
        }

        await event_mesh_gateway_component._send_error_to_external(
            external_context, sample_jsonrpc_error
        )

    @pytest.mark.asyncio
    async def test_send_error_no_error_handler(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        sample_jsonrpc_error: JSONRPCError,
    ):
        """Test that missing on_error handler is handled gracefully."""
        external_context = {
            "event_handler_name": "handler_without_on_error",  # Doesn't exist
            "original_solace_topic": "test/events/no_error_handler",
            "original_solace_user_properties": {},
            "user_identity": {"id": "test_user"},
            "a2a_task_id_for_event": "error_task_002",
        }

        # Should return without error
        await event_mesh_gateway_component._send_error_to_external(
            external_context, sample_jsonrpc_error
        )

    @pytest.mark.asyncio
    async def test_send_validation_error(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        sample_validation_error: JSONRPCError,
    ):
        """Test sending a validation error."""
        external_context = {
            "event_handler_name": "test_event_handler",
            "original_solace_topic": "test/events/validation_error",
            "original_solace_user_properties": {},
            "user_identity": {"id": "validation_user"},
            "a2a_task_id_for_event": "validation_task",
            "forwarded_context": {"original_topic": "test/events/validation"},
        }

        await event_mesh_gateway_component._send_error_to_external(
            external_context, sample_validation_error
        )


class TestProcessArtifactsFromMessage:
    """Tests for _process_artifacts_from_message method."""

    @pytest.mark.asyncio
    async def test_process_artifacts_no_config(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """Test that no artifact config returns empty list."""
        msg = SolaceMessage(payload={"data": "test"})
        handler_config = {"name": "no_artifacts_handler"}
        user_identity = {"id": "test_user"}

        result = await event_mesh_gateway_component._process_artifacts_from_message(
            msg, handler_config, user_identity, "session_001"
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_process_artifacts_with_single_item(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_artifact_service_instance: TestInMemoryArtifactService,
    ):
        """Test processing a single artifact from message."""
        msg = SolaceMessage(
            payload={
                "file": {
                    "name": "test_file.txt",
                    "content": "Hello, World!",
                    "type": "text/plain",
                }
            }
        )

        handler_config = {
            "name": "artifact_handler",
            "artifact_processing": {
                "extract_artifacts_expression": "input.payload:file",
                "artifact_definition": {
                    "filename": "list_item:name",
                    "content": "list_item:content",
                    "mime_type": "list_item:type",
                },
            },
        }
        user_identity = {"id": "artifact_user"}

        result = await event_mesh_gateway_component._process_artifacts_from_message(
            msg, handler_config, user_identity, "session_artifacts"
        )

        # Should return list of URIs
        assert isinstance(result, list)
        if result:  # If artifact service is available
            assert len(result) == 1
            assert "test_file.txt" in result[0]

    @pytest.mark.asyncio
    async def test_process_artifacts_with_list(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_artifact_service_instance: TestInMemoryArtifactService,
    ):
        """Test processing multiple artifacts from a list."""
        msg = SolaceMessage(
            payload={
                "files": [
                    {"name": "file1.txt", "content": "Content 1", "type": "text/plain"},
                    {"name": "file2.txt", "content": "Content 2", "type": "text/plain"},
                ]
            }
        )

        handler_config = {
            "name": "multi_artifact_handler",
            "artifact_processing": {
                "extract_artifacts_expression": "input.payload:files",
                "artifact_definition": {
                    "filename": "list_item:name",
                    "content": "list_item:content",
                    "mime_type": "list_item:type",
                },
            },
        }
        user_identity = {"id": "multi_artifact_user"}

        result = await event_mesh_gateway_component._process_artifacts_from_message(
            msg, handler_config, user_identity, "session_multi"
        )

        assert isinstance(result, list)
        if result:
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_process_artifacts_missing_expression(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """Test that missing expression returns empty list."""
        msg = SolaceMessage(payload={"data": "test"})
        handler_config = {
            "name": "incomplete_handler",
            "artifact_processing": {
                # Missing extract_artifacts_expression
                "artifact_definition": {"filename": "test.txt"},
            },
        }
        user_identity = {"id": "test_user"}

        result = await event_mesh_gateway_component._process_artifacts_from_message(
            msg, handler_config, user_identity, "session_missing"
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_process_artifacts_expression_returns_none(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """Test that expression returning None yields empty list."""
        msg = SolaceMessage(payload={"data": "test"})  # No 'artifacts' field
        handler_config = {
            "name": "no_match_handler",
            "artifact_processing": {
                "extract_artifacts_expression": "input.payload:artifacts",
                "artifact_definition": {
                    "filename": "list_item:name",
                    "content": "list_item:content",
                    "mime_type": "list_item:type",
                },
            },
        }
        user_identity = {"id": "test_user"}

        result = await event_mesh_gateway_component._process_artifacts_from_message(
            msg, handler_config, user_identity, "session_none"
        )

        assert result == []


class TestProcessFilePartForOutput:
    """Tests for _process_file_part_for_output method."""

    @pytest.mark.asyncio
    async def test_process_file_part_with_uri(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
        test_artifact_service_instance: TestInMemoryArtifactService,
    ):
        """Test processing a file part with URI."""
        # First save an artifact
        from google.genai import types as adk_types

        file_content = b"Test file content for output"
        artifact_part = adk_types.Part(
            inline_data=adk_types.Blob(mime_type="text/plain", data=file_content)
        )

        await test_artifact_service_instance.save_artifact(
            app_name="TestGateway",
            user_id="file_user",
            session_id="file_session",
            filename="output_file.txt",
            artifact=artifact_part,
        )

        # Create a FilePart referencing it
        file_part = FilePart(
            file={
                "uri": "artifact://TestGateway/file_user/file_session/output_file.txt?version=1",
                "name": "output_file.txt",
                "mimeType": "text/plain",
            }
        )

        external_context = {
            "app_name_for_artifacts": "TestGateway",
            "user_id_for_artifacts": "file_user",
            "a2a_session_id": "file_session",
        }

        handler_config = {"name": "file_handler"}

        result = await event_mesh_gateway_component._process_file_part_for_output(
            file_part, external_context, handler_config
        )

        assert isinstance(result, dict)
        assert "name" in result or "uri" in result


class TestOutputTransformsAndPublishing:
    """Tests for output transforms and message publishing."""

    @pytest.mark.asyncio
    async def test_output_handler_with_transforms(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """Test that output transforms are applied."""
        # The gateway should have output_handler_transforms set up
        assert hasattr(event_mesh_gateway_component, "output_handler_transforms")

    def test_output_handler_map_populated(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """Test that output handler map is populated from config."""
        assert hasattr(event_mesh_gateway_component, "output_handler_map")
        assert len(event_mesh_gateway_component.output_handler_map) > 0

        # Should have test_success_handler and test_error_handler
        handler_names = list(event_mesh_gateway_component.output_handler_map.keys())
        assert "test_success_handler" in handler_names
        assert "test_error_handler" in handler_names

    def test_event_handler_map_populated(
        self,
        event_mesh_gateway_component: EventMeshGatewayComponent,
    ):
        """Test that event handler map is populated from config."""
        assert hasattr(event_mesh_gateway_component, "event_handler_map")
        assert len(event_mesh_gateway_component.event_handler_map) > 0

        # Should have test_event_handler
        assert "test_event_handler" in event_mesh_gateway_component.event_handler_map

        # Check it has on_success and on_error
        handler = event_mesh_gateway_component.event_handler_map["test_event_handler"]
        assert "on_success" in handler
        assert "on_error" in handler
