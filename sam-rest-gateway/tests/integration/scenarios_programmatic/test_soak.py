import asyncio
import pytest
import time
from typing import Dict, Any, List

from sam_test_infrastructure.llm_server.server import TestLLMServer
from tests.integration.test_support.rest_gateway_test_component import RestGatewayTestComponent

# --- Test Parameters ---
TEST_DURATION_SECONDS = 30
CONCURRENT_USERS = 5
RAMP_UP_SECONDS = 5
SUCCESS_RATE_THRESHOLD = 0.99
MAX_RESPONSE_TIME_SECONDS = 10.0

@pytest.mark.asyncio
async def test_gateway_soak(
    test_rest_gateway: RestGatewayTestComponent,
    test_llm_server: TestLLMServer,
    auth_tokens: Dict[str, str],
):
    """
    A soak test to verify the gateway's stability under sustained load.
    """
    start_time = time.time()
    stats = {
        "success_count": 0,
        "failure_count": 0,
        "response_times": [],
    }

    async def user_task(user_id: int):
        """Simulates a single user's behavior."""
        while time.time() - start_time < TEST_DURATION_SECONDS:
            task_start_time = time.time()
            try:
                # Submit a task
                form_data = {
                    "agent_name": "TestAgent",
                    "prompt": f"Soak test request from user {user_id}",
                }
                response = await test_rest_gateway.make_authenticated_request(
                    method="POST",
                    endpoint="/api/v2/tasks",
                    token=auth_tokens["valid"],
                    form_data=form_data,
                )
                
                if response.status_code != 202:
                    stats["failure_count"] += 1
                    continue

                task_id = response.json().get("taskId")
                if not task_id:
                    stats["failure_count"] += 1
                    continue

                # Poll for the result
                for _ in range(20):  # Max 20 polls
                    poll_response = await test_rest_gateway.make_authenticated_request(
                        method="GET",
                        endpoint=f"/api/v2/tasks/{task_id}",
                        token=auth_tokens["valid"],
                    )
                    if poll_response.status_code == 200:
                        stats["success_count"] += 1
                        stats["response_times"].append(time.time() - task_start_time)
                        break
                    await asyncio.sleep(0.5)
                else:
                    stats["failure_count"] += 1

            except Exception:
                stats["failure_count"] += 1

    # Prime the LLM with a generic response
    llm_response = {
        "id": "chatcmpl-soak-test",
        "object": "chat.completion",
        "model": "test-llm-model",
        "choices": [{"message": {"role": "assistant", "content": "Soak test response"}, "finish_reason": "stop"}],
    }
    test_llm_server.prime_responses([llm_response] * (CONCURRENT_USERS * TEST_DURATION_SECONDS))

    # Ramp-up and run user tasks
    user_tasks = []
    for i in range(CONCURRENT_USERS):
        task = asyncio.create_task(user_task(i + 1))
        user_tasks.append(task)
        await asyncio.sleep(RAMP_UP_SECONDS / CONCURRENT_USERS)

    await asyncio.gather(*user_tasks)

    # --- Assertions ---
    total_requests = stats["success_count"] + stats["failure_count"]
    assert total_requests > 0, "No requests were made during the soak test."

    success_rate = stats["success_count"] / total_requests
    avg_response_time = sum(stats["response_times"]) / len(stats["response_times"]) if stats["response_times"] else 0

    print(f"\n--- Soak Test Results ---")
    print(f"Total Requests: {total_requests}")
    print(f"Successful: {stats['success_count']}")
    print(f"Failed: {stats['failure_count']}")
    print(f"Success Rate: {success_rate:.2%}")
    print(f"Average Response Time: {avg_response_time:.2f}s")

    assert success_rate >= SUCCESS_RATE_THRESHOLD, f"Success rate ({success_rate:.2%}) was below the threshold of {SUCCESS_RATE_THRESHOLD:.2%}"
    assert avg_response_time < MAX_RESPONSE_TIME_SECONDS, f"Average response time ({avg_response_time:.2f}s) exceeded the limit of {MAX_RESPONSE_TIME_SECONDS}s"
