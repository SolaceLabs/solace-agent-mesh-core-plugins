"""
Pytest test runner for declarative (YAML/JSON) REST Gateway test scenarios.
"""

import base64
import pytest
import yaml
import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Union, Optional, Tuple
from fastapi.testclient import TestClient
from fastapi import UploadFile
import io

from sam_test_infrastructure.llm_server.server import (
    TestLLMServer,
    ChatCompletionRequest,
)
from sam_test_infrastructure.artifact_service.service import (
    TestInMemoryArtifactService,
)
from sam_test_infrastructure.a2a_validator.validator import A2AMessageValidator

from solace_agent_mesh.common.types import (
    TextPart,
    DataPart,
    Task,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    JSONRPCError,
)
from solace_agent_mesh.agent.sac.app import SamAgentApp
from solace_agent_mesh.agent.sac.component import SamAgentComponent

from tests.integration.test_support.rest_gateway_test_component import RestGatewayTestComponent
from tests.integration.test_support.http_test_helpers import HTTPTestHelper


async def _setup_scenario_environment(
    declarative_scenario: Dict[str, Any],
    test_llm_server: TestLLMServer,
    test_artifact_service_instance: TestInMemoryArtifactService,
    scenario_id: str,
) -> None:
    """
    Primes the LLM server and sets up initial artifacts based on the scenario definition.
    """
    llm_interactions = declarative_scenario.get("llm_interactions", [])
    primed_llm_responses = []
    for interaction in llm_interactions:
        if "static_response" in interaction:
            try:
                primed_llm_responses.append(interaction["static_response"])
            except Exception as e:
                pytest.fail(
                    f"Scenario {scenario_id}: Error parsing LLM static_response: {e}\nResponse data: {interaction['static_response']}"
                )
        else:
            pytest.fail(
                f"Scenario {scenario_id}: 'static_response' missing in llm_interaction: {interaction}"
            )
    test_llm_server.prime_responses(primed_llm_responses)

    # Setup artifacts if specified
    setup_artifacts_spec = declarative_scenario.get("setup_artifacts", [])
    if setup_artifacts_spec:
        gateway_input_data_for_artifact_setup = declarative_scenario.get(
            "gateway_input", {}
        )
        user_identity_for_artifacts = gateway_input_data_for_artifact_setup.get(
            "user_identity", "default_artifact_user@example.com"
        )
        app_name_for_setup = gateway_input_data_for_artifact_setup.get(
            "target_agent_name", "TestAgent_Setup"
        )
        session_id_for_setup = gateway_input_data_for_artifact_setup.get(
            "session_id", f"setup_session_for_{user_identity_for_artifacts}"
        )

        for artifact_spec in setup_artifacts_spec:
            filename = artifact_spec["filename"]
            mime_type = artifact_spec.get("mime_type", "application/octet-stream")
            content_str = artifact_spec.get("content")
            content_base64 = artifact_spec.get("content_base64")

            content_bytes = b""
            if content_str is not None:
                content_bytes = content_str.encode("utf-8")
            elif content_base64 is not None:
                content_bytes = base64.b64decode(content_base64)
            else:
                pytest.fail(
                    f"Scenario {scenario_id}: Artifact spec for '{filename}' must have 'content' or 'content_base64'."
                )

            from google.genai import types as adk_types
            part_to_save = adk_types.Part(
                inline_data=adk_types.Blob(mime_type=mime_type, data=content_bytes)
            )

            await test_artifact_service_instance.save_artifact(
                app_name=app_name_for_setup,
                user_id=user_identity_for_artifacts,
                session_id=session_id_for_setup,
                filename=filename,
                artifact=part_to_save,
            )
            print(f"Scenario {scenario_id}: Setup artifact '{filename}' created.")


async def _execute_rest_gateway_request(
    test_rest_gateway: RestGatewayTestComponent,
    gateway_input_data: Dict[str, Any],
    scenario_id: str,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Executes a REST gateway request and returns the response and optional task_id.
    """
    endpoint = gateway_input_data.get("endpoint")
    if not endpoint:
        pytest.fail(f"Scenario {scenario_id}: 'endpoint' is required in gateway_input")

    method = gateway_input_data.get("method", "POST")
    form_data = gateway_input_data.get("form_data", {})
    files_spec = gateway_input_data.get("files", [])
    headers = gateway_input_data.get("headers", {})
    query_params = gateway_input_data.get("query_params", {})

    # Prepare files for upload
    files = []
    for file_spec in files_spec:
        filename = file_spec["filename"]
        content = file_spec.get("content", "")
        mime_type = file_spec.get("mime_type", "text/plain")
        
        if "content_base64" in file_spec:
            content = base64.b64decode(file_spec["content_base64"])
        else:
            content = content.encode("utf-8")
        
        files.append(("files", (filename, io.BytesIO(content), mime_type)))

    print(f"Scenario {scenario_id}: Making {method} request to {endpoint}")
    
    response = await test_rest_gateway.make_request(
        method=method,
        endpoint=endpoint,
        form_data=form_data,
        files=files,
        headers=headers,
        query_params=query_params,
    )

    task_id = None
    if response.status_code == 202 and response.headers.get("content-type", "").startswith("application/json"):
        try:
            response_data = response.json()
            task_id = response_data.get("taskId")
        except:
            pass  # Not JSON response, no task_id

    return response, task_id


def _assert_http_response(
    actual_response: Any,
    expected_response_spec: Dict[str, Any],
    scenario_id: str,
    response_index: int,
) -> None:
    """
    Asserts HTTP response against expected specifications.
    """
    if "status_code" in expected_response_spec:
        expected_status = expected_response_spec["status_code"]
        assert actual_response.status_code == expected_status, (
            f"Scenario {scenario_id}: Response {response_index + 1} - "
            f"Status code mismatch. Expected {expected_status}, Got {actual_response.status_code}"
        )

    if "response_contains" in expected_response_spec:
        response_text = actual_response.text
        expected_content = expected_response_spec["response_contains"]
        if isinstance(expected_content, dict):
            response_json = actual_response.json()
            for key, value in expected_content.items():
                assert key in response_json, (
                    f"Scenario {scenario_id}: Response {response_index + 1} - "
                    f"Expected key '{key}' not found in response"
                )
                if value is not None:
                    assert response_json[key] == value, (
                        f"Scenario {scenario_id}: Response {response_index + 1} - "
                        f"Value mismatch for key '{key}'. Expected {value}, Got {response_json[key]}"
                    )
        else:
            assert str(expected_content) in response_text, (
                f"Scenario {scenario_id}: Response {response_index + 1} - "
                f"Expected content '{expected_content}' not found in response"
            )

    if "response_json_matches" in expected_response_spec:
        response_json = actual_response.json()
        expected_json = expected_response_spec["response_json_matches"]
        _assert_dict_subset(expected_json, response_json, scenario_id, response_index)

    if "headers_contain" in expected_response_spec:
        expected_headers = expected_response_spec["headers_contain"]
        for header_name, expected_value in expected_headers.items():
            assert header_name in actual_response.headers, (
                f"Scenario {scenario_id}: Response {response_index + 1} - "
                f"Expected header '{header_name}' not found"
            )
            if expected_value is not None:
                actual_value = actual_response.headers[header_name]
                assert actual_value == expected_value, (
                    f"Scenario {scenario_id}: Response {response_index + 1} - "
                    f"Header '{header_name}' value mismatch. Expected {expected_value}, Got {actual_value}"
                )


def _assert_dict_subset(
    expected_subset: Dict,
    actual_superset: Dict,
    scenario_id: str,
    response_index: int,
    context_path: str = "response",
):
    """Helper to assert that expected_subset is contained in actual_superset."""
    for key, expected_value in expected_subset.items():
        assert key in actual_superset, (
            f"Scenario {scenario_id}: Response {response_index + 1} - "
            f"Expected key '{key}' not found in {context_path}"
        )
        
        actual_value = actual_superset[key]
        if isinstance(expected_value, dict) and isinstance(actual_value, dict):
            _assert_dict_subset(
                expected_value, actual_value, scenario_id, response_index, f"{context_path}.{key}"
            )
        else:
            assert actual_value == expected_value, (
                f"Scenario {scenario_id}: Response {response_index + 1} - "
                f"Value mismatch for {context_path}.{key}. Expected {expected_value}, Got {actual_value}"
            )


DECLARATIVE_TEST_DATA_DIR = Path(__file__).parent / "test_data"


def load_declarative_test_cases():
    """
    Loads all declarative test cases from the specified directory.
    """
    test_cases = []
    if not DECLARATIVE_TEST_DATA_DIR.is_dir():
        return []

    for filepath in sorted(DECLARATIVE_TEST_DATA_DIR.glob("**/*.yaml")):
        try:
            with open(filepath, "r") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    relative_path = filepath.relative_to(DECLARATIVE_TEST_DATA_DIR)
                    test_id = str(relative_path.with_suffix("")).replace(
                        os.path.sep, "/"
                    )
                    tags = data.get("tags", [])
                    test_cases.append(
                        pytest.param(data, id=test_id, marks=[getattr(pytest.mark, tag) for tag in tags])
                    )
                else:
                    print(f"Warning: Skipping file with non-dict content: {filepath}")
        except Exception as e:
            print(f"Warning: Could not load or parse test case file {filepath}: {e}")
    return test_cases


def pytest_generate_tests(metafunc):
    """
    Pytest hook to discover and parameterize tests based on declarative files.
    """
    if "declarative_scenario" in metafunc.fixturenames:
        test_cases = load_declarative_test_cases()
        metafunc.parametrize("declarative_scenario", test_cases)


@pytest.mark.asyncio
async def test_declarative_scenario(
    declarative_scenario: Dict[str, Any],
    test_llm_server: TestLLMServer,
    test_rest_gateway: RestGatewayTestComponent,
    test_artifact_service_instance: TestInMemoryArtifactService,
    a2a_message_validator: A2AMessageValidator,
    mock_gemini_client: None,
):
    """
    Executes a single declarative REST Gateway test scenario.
    """
    scenario_id = declarative_scenario.get("test_case_id", "N/A")
    scenario_description = declarative_scenario.get("description", "No description")

    print(f"\nRunning REST Gateway declarative scenario: {scenario_id} - {scenario_description}")

    # Phase 1: Setup Environment
    await _setup_scenario_environment(
        declarative_scenario,
        test_llm_server,
        test_artifact_service_instance,
        scenario_id,
    )

    gateway_input_data = declarative_scenario.get("gateway_input")
    if not gateway_input_data:
        pytest.fail(f"Scenario {scenario_id}: 'gateway_input' is missing.")

    # Phase 2: Execute REST Gateway Request
    response, task_id = await _execute_rest_gateway_request(
        test_rest_gateway, gateway_input_data, scenario_id
    )

    print(f"Scenario {scenario_id}: Initial request completed with status {response.status_code}")

    # Phase 3: Handle polling for v2 API if needed
    all_responses = [response]
    
    if task_id and declarative_scenario.get("enable_polling", False):
        # Poll for completion
        max_polls = declarative_scenario.get("max_polling_attempts", 10)
        poll_interval = declarative_scenario.get("polling_interval_seconds", 0.5)
        
        for attempt in range(max_polls):
            await asyncio.sleep(poll_interval)
            poll_response = await test_rest_gateway.make_request(
                method="GET",
                endpoint=f"/api/v2/tasks/{task_id}",
            )
            all_responses.append(poll_response)
            
            if poll_response.status_code == 200:
                print(f"Scenario {scenario_id}: Task {task_id} completed after {attempt + 1} polls")
                break
            elif poll_response.status_code != 202:
                pytest.fail(
                    f"Scenario {scenario_id}: Unexpected polling response status {poll_response.status_code}"
                )
        else:
            pytest.fail(f"Scenario {scenario_id}: Task {task_id} did not complete within {max_polls} polls")

    # Phase 4: Assert responses
    expected_responses = declarative_scenario.get("expected_gateway_output", [])
    
    assert len(all_responses) >= len(expected_responses), (
        f"Scenario {scenario_id}: Expected at least {len(expected_responses)} responses, "
        f"but got {len(all_responses)}"
    )

    for i, expected_response_spec in enumerate(expected_responses):
        if i < len(all_responses):
            _assert_http_response(all_responses[i], expected_response_spec, scenario_id, i)

    # Phase 5: Assert LLM interactions if specified
    expected_llm_interactions = declarative_scenario.get("llm_interactions", [])
    if expected_llm_interactions:
        captured_llm_requests = test_llm_server.get_captured_requests()
        assert len(captured_llm_requests) == len(expected_llm_interactions), (
            f"Scenario {scenario_id}: LLM interaction count mismatch. "
            f"Expected {len(expected_llm_interactions)}, Got {len(captured_llm_requests)}"
        )

    # Phase 6: Assert artifacts if specified
    expected_artifacts_spec_list = declarative_scenario.get("expected_artifacts", [])
    if expected_artifacts_spec_list:
        await _assert_generated_artifacts(
            expected_artifacts_spec_list=expected_artifacts_spec_list,
            test_artifact_service_instance=test_artifact_service_instance,
            gateway_input_data=gateway_input_data,
            scenario_id=scenario_id,
        )

    print(f"Scenario {scenario_id}: Test completed successfully.")


async def _assert_generated_artifacts(
    expected_artifacts_spec_list: List[Dict[str, Any]],
    test_artifact_service_instance: TestInMemoryArtifactService,
    gateway_input_data: Dict[str, Any],
    scenario_id: str,
) -> None:
    """
    Asserts that artifacts generated during the test match the expected specifications.
    """
    if not expected_artifacts_spec_list:
        return

    # For REST Gateway, we need to determine the correct app_name, user_id, and session_id
    # These should match what was used during artifact setup
    app_name_for_artifacts = "TestAgent_Setup"  # From setup
    user_id_for_artifacts = "default_artifact_user@example.com"  # From setup
    session_id_for_artifacts = f"setup_session_for_{user_id_for_artifacts}"  # From setup

    print(f"Scenario {scenario_id}: Checking artifacts with app={app_name_for_artifacts}, user={user_id_for_artifacts}, session={session_id_for_artifacts}")

    for i, expected_artifact_spec in enumerate(expected_artifacts_spec_list):
        context_path = f"expected_artifacts[{i}]"
        filename_from_spec = expected_artifact_spec.get("filename")
        
        if not filename_from_spec:
            pytest.fail(f"Scenario {scenario_id}: '{context_path}' - Must specify 'filename'.")

        # Check if artifact exists
        versions = await test_artifact_service_instance.list_versions(
            app_name=app_name_for_artifacts,
            user_id=user_id_for_artifacts,
            session_id=session_id_for_artifacts,
            filename=filename_from_spec,
        )
        
        assert versions, (
            f"Scenario {scenario_id}: No versions found for expected artifact '{filename_from_spec}' "
            f"(app: {app_name_for_artifacts}, user: {user_id_for_artifacts}, session: {session_id_for_artifacts})."
        )
        
        latest_version = max(versions)
        version_to_check = expected_artifact_spec.get("version", latest_version)
        if version_to_check == "latest":
            version_to_check = latest_version

        details = await test_artifact_service_instance.get_artifact_details(
            app_name=app_name_for_artifacts,
            user_id=user_id_for_artifacts,
            session_id=session_id_for_artifacts,
            filename=filename_from_spec,
            version=version_to_check,
        )
        
        assert details is not None, (
            f"Scenario {scenario_id}: Artifact '{filename_from_spec}' version {version_to_check} not found."
        )

        content_bytes, mime_type = details

        if "mime_type" in expected_artifact_spec:
            assert mime_type == expected_artifact_spec["mime_type"], (
                f"Scenario {scenario_id}: Artifact '{filename_from_spec}' MIME type mismatch. "
                f"Expected '{expected_artifact_spec['mime_type']}', Got '{mime_type}'"
            )

        if "content_contains" in expected_artifact_spec:
            try:
                content_str = content_bytes.decode("utf-8")
                assert expected_artifact_spec["content_contains"] in content_str, (
                    f"Scenario {scenario_id}: Artifact '{filename_from_spec}' content mismatch. "
                    f"Expected to contain '{expected_artifact_spec['content_contains']}', Got '{content_str[:200]}...'"
                )
            except UnicodeDecodeError:
                pytest.fail(
                    f"Scenario {scenario_id}: Artifact '{filename_from_spec}' content could not be decoded as UTF-8 for 'content_contains' check."
                )

        print(f"Scenario {scenario_id}: Artifact '{filename_from_spec}' assertion passed.")
