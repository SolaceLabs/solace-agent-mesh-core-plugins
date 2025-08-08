import asyncio
import pytest
from typing import Dict, Any
import io

from sam_test_infrastructure.llm_server.server import TestLLMServer
from tests.integration.test_support.rest_gateway_test_component import RestGatewayTestComponent
from tests.integration.test_support.fake_large_file import FakeLargeFile

@pytest.mark.asyncio
async def test_v2_large_text_payload(
    test_rest_gateway: RestGatewayTestComponent,
    test_llm_server: TestLLMServer,
    auth_tokens: Dict[str, str],
):
    """
    Tests that the v2 API can handle a large text payload.
    """
    # 1. Create a large text payload
    large_text = "a" * (1024 * 512)  # 0.5 MB of text

    # 2. Prime the LLM server with a simple response
    llm_response = {
        "id": "chatcmpl-test-large-text",
        "object": "chat.completion",
        "model": "test-llm-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Large text payload processed.",
                },
                "finish_reason": "stop",
            }
        ],
    }
    test_llm_server.prime_responses([llm_response])

    # 3. Submit the task
    form_data = {
        "agent_name": "TestAgent",
        "prompt": large_text,
    }
    response = await test_rest_gateway.make_authenticated_request(
        method="POST",
        endpoint="/api/v2/tasks",
        token=auth_tokens["valid"],
        form_data=form_data,
    )
    assert response.status_code == 202
    task_id = response.json().get("taskId")
    assert task_id

    # 4. Poll for the result
    for _ in range(240):  # Max 240 polls for larger payload
        response = await test_rest_gateway.make_authenticated_request(
            method="GET",
            endpoint=f"/api/v2/tasks/{task_id}",
            token=auth_tokens["valid"],
        )
        if response.status_code == 200:
            break
        await asyncio.sleep(0.5)
    else:
        pytest.fail(f"Task {task_id} did not complete in time.")

    # 5. Assert the final result
    result = response.json()
    assert result["status"]["state"] == "completed"

@pytest.mark.asyncio
async def test_v2_large_file_payload(
    test_rest_gateway: RestGatewayTestComponent,
    test_llm_server: TestLLMServer,
    auth_tokens: Dict[str, str],
):
    """
    Tests that the v2 API can handle a large file payload.
    """
    # 1. Create a large file payload
    # Use a file-like object that simulates a 5MB file without allocating all bytes in memory
    large_file = ("files", ("large_file.txt", FakeLargeFile(5 * 1024 * 1024), "text/plain"))

    # 2. Prime the LLM server with a simple response
    llm_response = {
        "id": "chatcmpl-test-large-file",
        "object": "chat.completion",
        "model": "test-llm-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Large file payload processed.",
                },
                "finish_reason": "stop",
            }
        ],
    }
    test_llm_server.prime_responses([llm_response])

    # 3. Submit the task
    form_data = {
        "agent_name": "TestAgent",
        "prompt": "Process the large file.",
    }
    response = await test_rest_gateway.make_authenticated_request(
        method="POST",
        endpoint="/api/v2/tasks",
        token=auth_tokens["valid"],
        form_data=form_data,
        files=[large_file],
    )
    assert response.status_code == 202
    task_id = response.json().get("taskId")
    assert task_id

    # 4. Poll for the result
    for _ in range(240):  # Max 240 polls for larger file
        response = await test_rest_gateway.make_authenticated_request(
            method="GET",
            endpoint=f"/api/v2/tasks/{task_id}",
            token=auth_tokens["valid"],
        )
        if response.status_code == 200:
            break
        await asyncio.sleep(0.5)
    else:
        pytest.fail(f"Task {task_id} did not complete in time.")

    # 5. Assert the final result
    result = response.json()
    assert result["status"]["state"] == "completed"
