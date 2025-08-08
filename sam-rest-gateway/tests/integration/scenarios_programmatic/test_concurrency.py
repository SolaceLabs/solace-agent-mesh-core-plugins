import asyncio
import pytest
from typing import Dict, Any

from sam_test_infrastructure.llm_server.server import TestLLMServer
from tests.integration.test_support.rest_gateway_test_component import RestGatewayTestComponent

CONCURRENT_REQUESTS = 10

@pytest.mark.asyncio
async def test_v2_concurrent_requests(
    test_rest_gateway: RestGatewayTestComponent,
    test_llm_server: TestLLMServer,
    auth_tokens: Dict[str, str],
):
    """
    Tests that the v2 API can handle multiple concurrent requests.
    """
    # 1. Prime the LLM server with a simple response for all requests
    llm_response = {
        "id": "chatcmpl-test-concurrent",
        "object": "chat.completion",
        "model": "test-llm-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "This is a concurrent test response.",
                },
                "finish_reason": "stop",
            }
        ],
    }
    test_llm_server.prime_responses([llm_response] * CONCURRENT_REQUESTS)

    # 2. Submit tasks concurrently
    submission_tasks = []
    for i in range(CONCURRENT_REQUESTS):
        form_data = {
            "agent_name": "TestAgent",
            "prompt": f"Concurrent request {i + 1}",
        }
        submission_tasks.append(
            test_rest_gateway.make_authenticated_request(
                method="POST",
                endpoint="/api/v2/tasks",
                token=auth_tokens["valid"],
                form_data=form_data,
            )
        )
    
    submission_responses = await asyncio.gather(*submission_tasks)

    task_ids = []
    for response in submission_responses:
        assert response.status_code == 202
        task_id = response.json().get("taskId")
        assert task_id
        task_ids.append(task_id)

    # 3. Poll for results concurrently
    async def poll_for_result(task_id: str):
        for _ in range(10):  # Max 10 polls
            response = await test_rest_gateway.make_authenticated_request(
                method="GET",
                endpoint=f"/api/v2/tasks/{task_id}",
                token=auth_tokens["valid"],
            )
            if response.status_code == 200:
                return response.json()
            await asyncio.sleep(0.5)
        pytest.fail(f"Task {task_id} did not complete in time.")

    polling_tasks = [poll_for_result(task_id) for task_id in task_ids]
    final_results = await asyncio.gather(*polling_tasks)

    # 4. Assert the final results
    assert len(final_results) == CONCURRENT_REQUESTS
    for result in final_results:
        assert result["status"]["state"] == "completed"
