# Test Implementation Plan for `sam-event-mesh-tool`

This document provides a comprehensive plan for implementing integration tests for the EventMeshTool. The tests are organized by category and priority to ensure systematic coverage of all functionality.

## Test Categories and Descriptions

### 1. Core Functionality Tests

#### 1.1 Parameter Handling Tests

**`test_parameter_mapping_with_nested_payload_paths`**
- **Purpose**: Verify that parameters are correctly mapped to nested payload paths using dot notation
- **Test Scenario**: Configure a tool with parameters using nested payload paths like `location.city` and `customer.address.zipcode`
- **Expected Result**: The outgoing payload should have the correct nested structure
- **Priority**: High

**`test_parameter_defaults_and_overrides`**
- **Purpose**: Test that default parameter values work correctly and can be overridden
- **Test Scenario**: Configure parameters with defaults, call tool with and without explicit values
- **Expected Result**: Defaults are used when not provided, explicit values override defaults
- **Priority**: High

**`test_missing_required_parameters`**
- **Purpose**: Test that the tool properly validates required parameters
- **Test Scenario**: Call tool without providing required parameters
- **Expected Result**: Tool should return an error indicating missing required parameters
- **Priority**: High

**`test_parameter_type_validation`**
- **Purpose**: Verify that parameter types are validated correctly
- **Test Scenario**: Pass wrong types for parameters (string instead of integer, etc.)
- **Expected Result**: Tool should handle type mismatches gracefully
- **Priority**: Medium

#### 1.2 Topic Template Tests

**`test_dynamic_topic_construction`**
- **Purpose**: Test that topic templates are filled correctly with parameter values
- **Test Scenario**: Configure topic template with multiple parameter substitutions
- **Expected Result**: Responder receives messages on the expected dynamic topic
- **Priority**: High

**`test_topic_template_with_missing_parameter`**
- **Purpose**: Test error handling when topic template references undefined parameters
- **Test Scenario**: Topic template references parameter not defined in parameters list
- **Expected Result**: Tool should return clear error about missing parameter
- **Priority**: High

**`test_topic_template_with_special_characters`**
- **Purpose**: Test topic construction with special characters in parameter values
- **Test Scenario**: Use parameters containing slashes, spaces, unicode characters
- **Expected Result**: Topic should be constructed correctly or fail gracefully
- **Priority**: Medium

### 2. Session Management Tests

#### 2.1 Session Lifecycle Tests

**`test_session_initialization_and_cleanup`**
- **Purpose**: Test that the tool properly creates and destroys its dedicated session
- **Test Scenario**: Verify session_id is set after init and cleared after cleanup
- **Expected Result**: Session lifecycle is managed correctly
- **Priority**: High

**`test_session_failure_handling`**
- **Purpose**: Test behavior when session creation fails
- **Test Scenario**: Mock session creation failure scenarios
- **Expected Result**: Tool should handle session failures gracefully with clear error messages
- **Priority**: Medium

**`test_session_isolation`**
- **Purpose**: Verify that each tool instance has its own isolated session
- **Test Scenario**: Create multiple tool instances and verify they don't interfere
- **Expected Result**: Each tool maintains its own session state
- **Priority**: Medium

### 3. Request-Response Pattern Tests

#### 3.1 Synchronous vs Asynchronous Tests

**`test_fire_and_forget_mode`**
- **Purpose**: Test `wait_for_response=false` returns immediately without waiting
- **Test Scenario**: Configure tool with `wait_for_response: false`
- **Expected Result**: Tool returns immediately with success status, message still sent
- **Priority**: High

**`test_synchronous_mode_blocking_behavior`**
- **Purpose**: Verify that synchronous mode properly blocks until response received
- **Test Scenario**: Send request with delay in responder, verify timing
- **Expected Result**: Tool call duration should match responder delay
- **Priority**: Medium

#### 3.2 Timeout and Error Handling Tests

**`test_request_timeout`**
- **Purpose**: Test that requests timeout properly when no response is received
- **Test Scenario**: Don't put anything on control queue to simulate timeout
- **Expected Result**: Tool should raise TimeoutError or return timeout status
- **Priority**: High

**`test_malformed_response_handling`**
- **Purpose**: Test handling of malformed or invalid responses
- **Test Scenario**: Put invalid JSON, corrupted data, or wrong format on control queue
- **Expected Result**: Tool should handle gracefully and return appropriate error
- **Priority**: High

**`test_broker_connection_failure`**
- **Purpose**: Test behavior when broker connection is unavailable
- **Test Scenario**: Configure tool with invalid broker settings
- **Expected Result**: Tool should fail gracefully with connection error
- **Priority**: Medium

**`test_response_correlation_failure`**
- **Purpose**: Test handling when response correlation fails
- **Test Scenario**: Simulate response with wrong correlation ID
- **Expected Result**: Tool should timeout or handle correlation mismatch
- **Priority**: Medium

### 4. Concurrency Tests

#### 4.1 Concurrent Request Tests

**`test_concurrent_requests_with_correlation`**
- **Purpose**: Test that multiple concurrent requests are properly correlated
- **Test Scenario**: Send multiple requests simultaneously with different delays
- **Expected Result**: Each request gets the correct response despite out-of-order arrival
- **Priority**: High

**`test_multiple_tool_instances_isolation`**
- **Purpose**: Test that multiple EventMeshTool instances don't interfere with each other
- **Test Scenario**: Configure agent with multiple tools, use them concurrently
- **Expected Result**: Tools operate independently without interference
- **Priority**: Medium

**`test_high_concurrency_stress`**
- **Purpose**: Test tool behavior under high concurrent load
- **Test Scenario**: Send many concurrent requests (50-100)
- **Expected Result**: All requests should be handled correctly
- **Priority**: Low

### 5. Payload Format Tests

#### 5.1 Different Payload Formats

**`test_json_payload_format`**
- **Purpose**: Test JSON payload encoding and response decoding
- **Test Scenario**: Configure tool with `payload_format: json`, send complex objects
- **Expected Result**: JSON is properly encoded/decoded
- **Priority**: High

**`test_yaml_payload_format`**
- **Purpose**: Test YAML payload format handling
- **Test Scenario**: Configure tool with `payload_format: yaml`
- **Expected Result**: YAML is properly encoded/decoded
- **Priority**: Medium

**`test_text_payload_format`**
- **Purpose**: Test plain text payload format
- **Test Scenario**: Configure tool with `payload_format: text`
- **Expected Result**: Text is handled as plain strings
- **Priority**: Medium

**`test_payload_encoding_options`**
- **Purpose**: Test different payload encoding options (utf-8, base64)
- **Test Scenario**: Configure different encoding options
- **Expected Result**: Encoding/decoding works correctly
- **Priority**: Low

### 6. Edge Cases and Error Conditions

#### 6.1 Edge Case Tests

**`test_empty_payload`**
- **Purpose**: Test tool behavior with empty or minimal payloads
- **Test Scenario**: Call tool with no parameters or empty values
- **Expected Result**: Tool should handle empty payloads gracefully
- **Priority**: Medium

**`test_large_payload_handling`**
- **Purpose**: Test handling of large request/response payloads
- **Test Scenario**: Send payloads approaching message size limits
- **Expected Result**: Large payloads should be handled or fail gracefully
- **Priority**: Low

**`test_special_characters_in_parameters`**
- **Purpose**: Test parameter values with special characters, unicode, etc.
- **Test Scenario**: Use parameters with emojis, special chars, different languages
- **Expected Result**: Special characters should be handled correctly
- **Priority**: Low

**`test_null_and_undefined_parameter_values`**
- **Purpose**: Test handling of null, undefined, or empty parameter values
- **Test Scenario**: Pass null, None, empty string values
- **Expected Result**: Tool should handle edge cases appropriately
- **Priority**: Medium

### 7. Integration and Real-world Scenarios

#### 7.1 Realistic Workflow Tests

**`test_weather_service_simulation`**
- **Purpose**: Test a realistic weather service request-response workflow
- **Test Scenario**: Simulate complete weather API interaction with realistic data
- **Expected Result**: End-to-end workflow should work as expected
- **Priority**: Medium

**`test_error_response_from_service`**
- **Purpose**: Test handling when the backend service returns an error response
- **Test Scenario**: Responder returns error payload with error codes/messages
- **Expected Result**: Tool should propagate service errors appropriately
- **Priority**: High

**`test_service_unavailable_scenario`**
- **Purpose**: Test behavior when backend service is completely unavailable
- **Test Scenario**: Responder doesn't respond at all
- **Expected Result**: Tool should timeout gracefully
- **Priority**: Medium

**`test_partial_service_failure`**
- **Purpose**: Test handling of intermittent service failures
- **Test Scenario**: Responder fails randomly for some requests
- **Expected Result**: Tool should handle individual failures without affecting other requests
- **Priority**: Low

### 8. Configuration Validation Tests

#### 8.1 Configuration Tests

**`test_invalid_tool_configuration`**
- **Purpose**: Test validation of tool configuration parameters
- **Test Scenario**: Provide various invalid configurations
- **Expected Result**: Tool should validate config and provide clear error messages
- **Priority**: Medium

**`test_missing_event_mesh_config`**
- **Purpose**: Test behavior when event_mesh_config is missing or invalid
- **Test Scenario**: Configure tool without required event_mesh_config
- **Expected Result**: Tool should fail initialization with clear error
- **Priority**: Medium

**`test_invalid_parameter_definitions`**
- **Purpose**: Test validation of parameter definitions in config
- **Test Scenario**: Define parameters with invalid types, missing names, etc.
- **Expected Result**: Configuration validation should catch errors
- **Priority**: Medium

### 9. Performance and Load Tests

#### 9.1 Performance Tests

**`test_high_frequency_requests`**
- **Purpose**: Test tool performance under high request frequency
- **Test Scenario**: Send many requests in rapid succession
- **Expected Result**: Tool should maintain performance and not degrade
- **Priority**: Low

**`test_request_response_latency`**
- **Purpose**: Measure and verify reasonable request-response latency
- **Test Scenario**: Measure time from request to response
- **Expected Result**: Latency should be within acceptable bounds
- **Priority**: Low

**`test_memory_usage_under_load`**
- **Purpose**: Verify tool doesn't have memory leaks under sustained load
- **Test Scenario**: Run many requests over extended period
- **Expected Result**: Memory usage should remain stable
- **Priority**: Low

### 10. Advanced Feature Tests

#### 10.1 Advanced Configuration Tests

**`test_custom_user_properties`**
- **Purpose**: Test custom user properties in requests
- **Test Scenario**: Configure tool to add custom user properties
- **Expected Result**: Custom properties should be included in requests
- **Priority**: Low

**`test_response_topic_insertion`**
- **Purpose**: Test response_topic_insertion_expression feature
- **Test Scenario**: Configure tool to insert reply topic into payload
- **Expected Result**: Reply topic should be correctly inserted
- **Priority**: Low

**`test_custom_reply_topic_configuration`**
- **Purpose**: Test custom reply topic and queue prefixes
- **Test Scenario**: Configure custom prefixes for reply topics/queues
- **Expected Result**: Custom prefixes should be used correctly
- **Priority**: Low

## Test Infrastructure Requirements

### Additional Test Fixtures Needed

**`agent_with_multiple_tools`**
- Agent configured with multiple EventMeshTool instances for isolation testing

**`agent_with_yaml_tool`**
- Agent configured with YAML payload format for format testing

**`agent_with_fire_and_forget_tool`**
- Agent configured with `wait_for_response=false` for async testing

**`slow_responder_service`**
- Responder that introduces configurable delays for timing tests

**`error_responder_service`**
- Responder that can simulate various error conditions

**`load_test_responder`**
- Responder optimized for handling high-volume concurrent requests

### Test Utilities Needed

**`ResponseBuilder`**
- Utility class for building various types of test responses

**`TimingHelper`**
- Utility for measuring request/response timing

**`PayloadValidator`**
- Utility for validating payload structure and content

## Implementation Strategy

### Phase 1: Core Functionality (High Priority)
1. Parameter handling tests
2. Topic template tests
3. Basic request-response tests
4. Timeout and error handling

### Phase 2: Advanced Features (Medium Priority)
1. Concurrency tests
2. Session management tests
3. Payload format tests
4. Configuration validation

### Phase 3: Edge Cases and Performance (Low Priority)
1. Edge case tests
2. Performance tests
3. Advanced feature tests
4. Load testing

---

## Implementation Checklist

### Core Functionality Tests
- [x] 1. `test_parameter_mapping_with_nested_payload_paths`
- [x] 2. `test_parameter_defaults_and_overrides`
- [x] 3. `test_missing_required_parameters`
- [x] 4. `test_parameter_type_validation`
- [x] 5. `test_dynamic_topic_construction`
- [x] 6. `test_topic_template_with_missing_parameter`
- [x] 7. `test_topic_template_with_special_characters`

### Session Management Tests
- [x] 8. `test_session_initialization_and_cleanup`
- [x] 9. `test_session_failure_handling`
- [x] 10. `test_session_isolation`

### Request-Response Pattern Tests
- [x] 11. `test_fire_and_forget_mode`
- [x] 12. `test_synchronous_mode_blocking_behavior`
- [x] 13. `test_request_timeout`
- [x] 14. `test_malformed_response_handling`
- [x] 15. `test_broker_connection_failure`
- [x] 16. `test_response_correlation_failure`

### Concurrency Tests
- [x] 17. `test_concurrent_requests_with_correlation`
- [x] 18. `test_multiple_tool_instances_isolation`
- [ ] 19. `test_high_concurrency_stress`

### Payload Format Tests
- [x] 20. `test_json_payload_format`
- [x] 21. `test_yaml_payload_format`
- [x] 22. `test_text_payload_format`
- [x] 23. `test_payload_encoding_options`

### Edge Cases and Error Conditions
- [x] 24. `test_empty_payload`
- [x] 25. `test_large_payload_handling`
- [x] 26. `test_special_characters_in_parameters`
- [x] 27. `test_null_and_undefined_parameter_values`

### Integration and Real-world Scenarios
- [x] 28. `test_weather_service_simulation`
- [x] 29. `test_error_response_from_service`
- [x] 30. `test_service_unavailable_scenario`
- [x] 31. `test_partial_service_failure`

### Configuration Validation Tests
- [x] 32. `test_invalid_tool_configuration`
- [x] 33. `test_missing_event_mesh_config`
- [x] 34. `test_invalid_parameter_definitions`

### Performance and Load Tests
- [ ] 35. `test_high_frequency_requests`
- [ ] 36. `test_request_response_latency`
- [ ] 37. `test_memory_usage_under_load`

### Advanced Feature Tests
- [x] 38. `test_custom_user_properties`
- [x] 39. `test_response_topic_insertion`
- [x] 40. `test_custom_reply_topic_configuration`

### Test Infrastructure
- [ ] 41. `agent_with_multiple_tools` fixture
- [ ] 42. `agent_with_yaml_tool` fixture
- [ ] 43. `agent_with_fire_and_forget_tool` fixture
- [ ] 44. `slow_responder_service` fixture
- [ ] 45. `error_responder_service` fixture
- [ ] 46. `load_test_responder` fixture
- [ ] 47. `ResponseBuilder` utility class
- [ ] 48. `TimingHelper` utility class
- [ ] 49. `PayloadValidator` utility class

### Documentation and Maintenance
- [ ] 50. Update test documentation
- [ ] 51. Add test execution instructions
- [ ] 52. Create CI/CD integration
- [ ] 53. Performance benchmarking setup
- [ ] 54. Test coverage reporting

**Total Tests Planned: 40**
**Current Tests Implemented: 1**
**Remaining Tests: 39**
