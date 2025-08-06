# REST Gateway Test Infrastructure

This directory contains the declarative test infrastructure for the SAM REST Gateway. The tests are designed to validate the REST API endpoints, file upload functionality, authentication, and integration with the underlying agent mesh.

## Structure

```
tests/
├── integration/
│   ├── conftest.py                         # Pytest fixtures and configuration
│   ├── scenarios_declarative/
│   │   ├── test_rest_gateway_runner.py     # Main test runner
│   │   └── test_data/
│   │       ├── v1_api/                     # V1 API test scenarios
│   │       └── v2_api/                     # V2 API test scenarios
│   └── test_support/
│       ├── rest_gateway_test_component.py  # REST Gateway test wrapper
│       └── http_test_helpers.py            # HTTP testing utilities
└── README.md
```

## Key Components

### RestGatewayTestComponent

The `RestGatewayTestComponent` wraps the actual REST Gateway and provides:
- HTTP client capabilities using FastAPI's TestClient
- Request/response handling for all HTTP methods
- File upload support
- Integration with the test infrastructure

### HTTPTestHelper

Utility class providing:
- File upload creation helpers
- Response assertion methods
- Authentication header creation
- Polling utilities for async operations

### Test Fixtures

The `conftest.py` provides several key fixtures:
- `test_rest_gateway`: Main REST Gateway test component
- `test_llm_server`: Mock LLM server for deterministic responses
- `test_artifact_service_instance`: In-memory artifact storage
- `shared_solace_connector`: Configured SolaceAiConnector with test agents