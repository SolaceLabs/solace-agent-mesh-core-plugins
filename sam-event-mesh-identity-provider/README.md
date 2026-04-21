# Event Mesh Identity Provider Plugin

A generic, vendor-agnostic identity and employee service provider for [Solace Agent Mesh](https://solacelabs.github.io/solace-agent-mesh/) that communicates with any backend system via Solace Event Mesh request-response messaging.

## About Solace Agent Mesh

[Solace Agent Mesh](https://solacelabs.github.io/solace-agent-mesh/) is a framework for building AI agent systems that communicate over Solace event brokers. It enables multi-agent collaboration, tool integration, and gateway connectivity for AI-powered applications.

## When to Use This Plugin

Use this plugin when:

- **You have an HR or identity system** (e.g., SAP SuccessFactors, Workday, BambooHR, custom LDAP) that is accessible via a service connected to a Solace event broker.
- **You need identity enrichment** in your gateway — enrich user auth claims with profile data (title, department, manager) from your HR system.
- **You need employee directory access** in your agents — let agents look up employees, search users, fetch org structure, or retrieve profile pictures.
- **You want a single plugin** that serves both identity and employee service roles without writing custom code.

The plugin sends requests to configurable topics on your Solace broker and expects a backend service (your integration layer) to respond. This makes it compatible with **any** backend system — you just need a message-driven integration that responds on the event mesh.

## Key Features

- **Vendor-agnostic**: Works with any backend connected to Solace Event Mesh
- **Configurable field mapping**: Map source fields to canonical schema via YAML (no code changes)
- **Computed fields**: Derive values from multiple source fields (e.g., displayName from first + last name)
- **Field exclusion and renaming**: Fine-grained control over output fields
- **Flexible topic configuration**: Single topic string for all operations, or per-operation dict
- **Built-in caching**: Configurable TTL caching for all operations
- **Dual-purpose**: Use as identity service (gateways) and/or employee service (agents)

## Installation

```bash
sam plugin install sam-event-mesh-identity-provider
```

Or install directly:

```bash
pip install sam-event-mesh-identity-provider
```

## Configuration

### As Identity Service (Gateway)

Add to your gateway configuration to enrich user identity on each request:

```yaml
identity_service:
  type: "event-mesh-identity-provider"

  broker_url: "${IDENTITY_BROKER_URL}"
  broker_vpn: "${IDENTITY_BROKER_VPN}"
  broker_username: "${IDENTITY_BROKER_USERNAME}"
  broker_password: "${IDENTITY_BROKER_PASSWORD}"

  lookup_key: "email"
  cache_ttl_seconds: 3600
  request_expiry_ms: 120000
  response_topic_prefix: "mycompany/identity/response"

  # Single topic for all operations:
  # request_topic: "mycompany/identity/request/v1/{request_id}"

  # Or per-operation topics:
  request_topic:
    user_profile: "mycompany/identity/user-profile/request/v1/{request_id}"
    search_users: "mycompany/identity/search-users/request/v1/{request_id}"

  field_mapping_config:
    field_mapping:
      emp_email: "workEmail"
      title: "jobTitle"
      dept_name: "department"
    computed_fields:
      - target: "displayName"
        source_fields: ["first_name", "last_name"]
        separator: " "
    pass_through_unmapped: true
```

### As People/Employee Service (Agent)

Add to your agent configuration for employee directory access:

```yaml
people_service:
  type: "event-mesh-identity-provider"

  broker_url: "${IDENTITY_BROKER_URL}"
  broker_vpn: "${IDENTITY_BROKER_VPN}"
  broker_username: "${IDENTITY_BROKER_USERNAME}"
  broker_password: "${IDENTITY_BROKER_PASSWORD}"

  lookup_key: "email"
  cache_ttl_seconds: 3600
  response_topic_prefix: "mycompany/identity/response"

  request_topic:
    user_profile: "mycompany/identity/user-profile/request/v1/{request_id}"
    search_users: "mycompany/identity/search-users/request/v1/{request_id}"
    employee_data: "mycompany/identity/employee-data/request/v1/{request_id}"
    employee_profile: "mycompany/identity/employee-profile/request/v1/{request_id}"
    time_off: "mycompany/identity/time-off/request/v1/{request_id}"
    profile_picture: "mycompany/identity/profile-picture/request/v1/{request_id}"

  field_mapping_config:
    field_mapping: {}
    pass_through_unmapped: true
```

## Configuration Reference

| Option | Description | Default |
|--------|-------------|---------|
| `type` | Must be `"event-mesh-identity-provider"` | Required |
| `broker_url` | Solace broker URL | Required |
| `broker_vpn` | Solace message VPN name | Required |
| `broker_username` | Broker authentication username | Required |
| `broker_password` | Broker authentication password | Required |
| `dev_mode` | Enable development mode (no TLS verification) | `false` |
| `lookup_key` | Key in auth_claims used to extract the lookup value | `"email"` |
| `payload_key` | Key name used in the request payload sent to the backend | Value of `lookup_key` |
| `cache_ttl_seconds` | Cache TTL in seconds (0 to disable) | `3600` |
| `request_expiry_ms` | Request timeout in milliseconds | `120000` |
| `response_topic_prefix` | Prefix for the response correlation topic | `"sam/identity-provider/response"` |
| `user_properties_reply_topic_key` | Key in message user properties where the reply topic is stored | `"replyTopic"` |
| `response_topic_insertion_expression` | Expression used by the broker to insert the response topic into the request | `"replyTopic"` |
| `request_topic` | Topic template (string) or per-operation map (dict) | Required |
| `field_mapping_config` | Field transformation configuration | `{}` (passthrough) |

### `request_topic` Formats

**String** — one topic for every operation:
```yaml
request_topic: "mycompany/identity/request/v1/{request_id}"
```

**Dict** — per-operation topics (operations not listed return `None` with a warning):
```yaml
request_topic:
  user_profile: "mycompany/identity/user-profile/request/v1/{request_id}"
  search_users: "mycompany/identity/search-users/request/v1/{request_id}"
  employee_data: "mycompany/identity/employee-data/request/v1/{request_id}"
```

Available operation keys: `user_profile`, `search_users`, `employee_data`, `employee_profile`, `time_off`, `profile_picture`.

## Field Mapping Guide

The field mapping engine transforms source data through a three-phase pipeline:

```
Source Data -> [1. Field Mapping] -> [2. Exclusion] -> [3. Renaming] -> Output
                                  ^
                      [Computed Fields]
```

### Phase 1: field_mapping

Rename source fields to canonical names:

```yaml
field_mapping:
  emp_email: "workEmail"       # "emp_email" in source -> "workEmail" in output
  position: "jobTitle"         # "position" in source -> "jobTitle" in output
```

### Computed Fields

Derive values from multiple source fields:

```yaml
computed_fields:
  # Concatenation (skips empty parts)
  - target: "displayName"
    source_fields: ["firstName", "middleName", "lastName"]
    separator: " "

  # Template-based (with fallback to concatenation if template fails)
  - target: "fullAddress"
    source_fields: ["city", "country"]
    template: "{city}, {country}"
```

### Phase 2: exclusion_list

Remove fields from output:

```yaml
exclusion_list:
  - "mobilePhone"       # Don't expose phone numbers
  - "salaryStructure"   # Don't expose salary data
```

### Phase 3: rename_mapping

Rename fields in the final output:

```yaml
rename_mapping:
  supervisorId: "managerId"    # Rename for downstream consumers
  workEmail: "email"           # Simplify field name
```

### Zero-Configuration

If your backend already returns data using the canonical field names (`id`, `displayName`, `workEmail`, `jobTitle`, `department`, `location`, `supervisorId`, `hireDate`, `mobilePhone`), you don't need any field mapping configuration. Just leave `field_mapping_config` empty or omit it entirely.

## Backend Integration Guide

Your backend service needs to listen on the configured topics and respond. Here's what each operation expects:

### user_profile

**Request payload:**
```json
{"email": "jane@company.com"}
```

**Expected response:** A single employee record (dict).

### search_users

**Request payload:**
```json
{"query": "jan", "limit": 10}
```

**Expected response:** A list of user dicts, or `{"results": [...]}`.

### employee_data

**Request payload:**
```json
{}
```

**Expected response:** A list of all employee dicts, or `{"employees": [...]}`.

### employee_profile

**Request payload:**
```json
{"employee_id": "jane@company.com"}
```

**Expected response:** A single employee record (dict).

### time_off

**Request payload:**
```json
{"employee_id": "jane@company.com", "start_date": "2025-01-01", "end_date": "2025-12-31"}
```

**Expected response:** A list of time-off entry dicts, or `{"entries": [...]}`.
Each entry must contain: `start` (YYYY-MM-DD), `end` (YYYY-MM-DD), `type` (string), `amount` ("full_day" or "half_day").

### profile_picture

**Request payload:**
```json
{"employee_id": "jane@company.com"}
```

**Expected response:** A data URI string (e.g., `"data:image/jpeg;base64,..."`) or `{"data_uri": "..."}`.

## Canonical Employee Schema

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique, stable, lowercase identifier |
| `displayName` | string | Full name for display |
| `workEmail` | string | Primary work email |
| `jobTitle` | string | Official job title |
| `department` | string | Department name |
| `location` | string | Physical/regional location |
| `supervisorId` | string | Manager's unique id |
| `hireDate` | string | ISO 8601 date (YYYY-MM-DD) |
| `mobilePhone` | string | Mobile phone number |

Additional fields from your backend are passed through by default (when `pass_through_unmapped: true`).

## Development

```bash
# Clone the repository
git clone https://github.com/SolaceLabs/solace-agent-mesh-core-plugins.git
cd solace-agent-mesh-core-plugins/sam-event-mesh-identity-provider

# Install in development mode
pip install -e .

# Install test dependencies
pip install pytest pytest-asyncio pytest-mock pytest-cov

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=sam_event_mesh_identity_provider --cov-report=term-missing
```

## License

Apache License 2.0
