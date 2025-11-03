# Nuclia RAG Tool User Guide

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Configuration Reference](#configuration-reference)
4. [Template Parameters](#template-parameters)
5. [Prompt Rephrasing](#prompt-rephrasing)
6. [Filter Expressions](#filter-expressions)
7. [Audit Metadata](#audit-metadata)

---

## Overview

The **Nuclia RAG Tool** is a generic, configuration-driven tool for Solace Agent Mesh (SAM) that provides powerful Retrieval-Augmented Generation (RAG) capabilities through Nuclia's knowledge base platform.

### Key Features

- **Generative Answers with Citations**: Generates natural language answers with verifiable, clickable citations to source documents
- **Template-Based Configuration**: Flexible prompt rephrasing and filtering using template parameters
- **Dynamic Filtering**: Apply runtime filters to narrow search scope based on user context
- **Secure Document Access**: Brokered URLs with ephemeral tokens for secure document viewing
- **Artifact-Based Output**: Returns structured markdown artifacts for easy presentation
- **Page-Specific Citations**: Direct links to exact pages in source documents

### What It Does

1. Takes a natural language query from the user
2. Optionally enriches the query with contextual information (e.g., user profile data)
3. Optionally applies filters to narrow the search scope
4. Queries Nuclia's knowledge base for relevant information
5. Generates a comprehensive answer with inline citation markers
6. Creates a formatted markdown artifact with the answer and source list
7. Returns a reference to the artifact for the agent to present to the user

---

## Quick Start

### Minimal Configuration

Here's the simplest possible configuration to get started:

```yaml
tools:
  - tool_type: python
    component_module: sam_nuclia_agent.nuclia_rag_tool
    class_name: NucliaRagTool
    tool_config:
      # Required: Nuclia connection details
      base_url: "https://europe-1.nuclia.cloud/api/v1"
      kb_id: "your-knowledge-box-id"
      token: "${NUCLIA_TOKEN}"
      api_key: "${NUCLIA_API_KEY}"
```

This configuration will:
- Connect to your Nuclia knowledge box
- Accept queries from the LLM
- Return answers with citations
- Use all default settings

### Basic Usage in Agent Instructions

```markdown
When the user asks a question, use the `generate_answer_with_citations` tool:
1. Pass the user's query to the `query` parameter
2. The tool will return a `response_artifact`
3. Present the answer using an artifact embed:
   «artifact_content:{{response_artifact.filename}}:{{response_artifact.version}}»
```

---

## Configuration Reference

### Required Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `base_url` | String | Nuclia API base URL | `"https://europe-1.nuclia.cloud/api/v1"` |
| `kb_id` | String | Knowledge Box unique identifier | `"abc123-def456-ghi789"` |
| `token` | String | Service Account API token | `"${NUCLIA_TOKEN}"` |
| `api_key` | String | Nuclia Account ID | `"${NUCLIA_API_KEY}"` |

### Optional Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `top_k` | Integer | `5` | Maximum paragraphs to retrieve (1-200) |
| `output_filename_base` | String | `"nuclia_answer"` | Base name for output artifacts |
| `artifact_description_query_max_length` | Integer | `150` | Max query length in artifact description |
| `inline_citation_links` | Boolean | `true` | Make citation markers clickable |

### Complete Example

```yaml
tools:
  - tool_type: python
    component_module: sam_nuclia_agent.nuclia_rag_tool
    class_name: NucliaRagTool
    tool_config:
      # Connection
      base_url: "${NUCLIA_BASE_URL}"
      kb_id: "${NUCLIA_KB_ID}"
      token: "${NUCLIA_TOKEN}"
      api_key: "${NUCLIA_API_KEY}"
      
      # Performance
      top_k: 10
      
      # Artifact settings
      output_filename_base: "document_answer"
      artifact_description_query_max_length: 200
      inline_citation_links: true
      
      # Advanced features (covered in later sections)
      template_parameters: []
      prompt_rephrasing: null
      filter_expression_template: null
```

---

## Template Parameters

Template parameters are dynamic values that can be passed to the tool at runtime and used in both prompt rephrasing and filter expressions.

### Defining Template Parameters

```yaml
template_parameters:
  - name: "region"
    description: "The user's region for context"
    type: "string"
    required: false
    nullable: true
    default: ""
  
  - name: "department"
    description: "The user's department"
    type: "string"
    required: false
    nullable: true
    default: null
  
  - name: "priority_level"
    description: "Priority level for the query"
    type: "integer"
    required: false
    nullable: true
    default: 1
```

### Parameter Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `name` | String | Yes | Parameter name (must be valid Python identifier) |
| `description` | String | No | Description for the LLM |
| `type` | String | No | Data type: `string`, `boolean`, `integer`, `number` |
| `required` | Boolean | No | Whether parameter is required |
| `nullable` | Boolean | No | Whether parameter can be null |
| `default` | Any | No | Default value if not provided |

### Using Template Parameters

Once defined, template parameters:
1. Automatically appear in the tool's schema for the LLM
2. Can be used in prompt rephrasing templates with `{parameter_name}`
3. Can be used in filter expression templates with `{parameter_name}`

**Example LLM Tool Call:**
```json
{
  "query": "What is the document policy?",
  "region": "emea",
  "department": "your-department"
}
```

---

## Prompt Rephrasing

Prompt rephrasing allows you to enrich the user's query with contextual information before sending it to Nuclia.

### Basic Prompt Rephrasing

```yaml
prompt_rephrasing:
  template: |
    <context>
    The user is asking about policies for {region}.
    </context>
    
    <query>
    {query}
    </query>
```

**Important:** The template **must** contain the `{query}` placeholder.

### Advanced Prompt Rephrasing

```yaml
template_parameters:
  - name: "policy_type"
    description: "Document category or policy type"
    type: "string"
    default: ""
  - name: "region"
    description: "User region"
    type: "string"
    default: ""

prompt_rephrasing:
  template: |
    <context>
    For the following search, if it applies to a specific policy type,
    ensure that you answer the question using the {policy_type} document.
    For questions that are related to region, the question relates to a user
    in {region}.
    </context>

    <query>
    {query}
    </query>
```

### How It Works

1. The LLM calls the tool with: `{"query": "time off policy", "policy_type": "policy_type_a", "region": "emea"}`
2. The tool substitutes placeholders: `{query}` → `"time off policy"`, `{policy_type}` → `"policy_type_a"`, `{region}` → `"emea"`
3. The enriched prompt is sent to Nuclia for better retrieval

---

## Filter Expressions

Filter expressions allow you to narrow the search scope based on runtime parameters. This is particularly useful for multi-tenant scenarios or when you need to restrict results to specific document types, labels, or metadata.

### Understanding Nuclia Filters

Nuclia supports a rich filtering language based on the `FilterExpression` model. Filters can target:
- **Labels**: Classification labels on documents (e.g., PolicyType, Region, DocumentCategory)
- **Fields**: Specific fields in resources
- **Metadata**: Origin metadata, dates, etc.
- **Keywords**: Specific keywords in documents

### Basic Filter Template

```yaml
filter_expression_template:
  field:
    prop: label
    labelset: "Region"
    label: "{region}"
```

This filter will only search documents tagged with the specified region label.

### Handling Missing Parameters

If a template parameter is missing or empty, **no filtering is applied**. The tool will:
1. Log a warning about missing parameters
2. Proceed with the search without filters
3. Include information in the response about which parameters were missing

**Example Response:**
```json
{
  "status": "success",
  "nuclia_learning_id": "abc123-def456-ghi789",
  "filter_applied": false,
  "missing_filter_parameters": ["region", "policy_type"],
  "message_to_llm": "Answer generated successfully. Note: Filtering was not applied because the following required parameters were missing or empty: region, policy_type"
}
```

### Complex Filter Examples

#### OR Logic: Match Any Condition

```yaml
filter_expression_template:
  field:
    or:
      - prop: label
        labelset: "PolicyType"
        label: "{policy_type}"
      - not:
          prop: label
          labelset: "PolicyType"
```

This matches documents that either:
1. Have the specified policy type label, OR
2. Don't have any policy type label at all

#### AND Logic: Match All Conditions

```yaml
filter_expression_template:
  field:
    and:
      - prop: label
        labelset: "Region"
        label: "{region}"
      - prop: label
        labelset: "DocumentType"
        label: "Policy"
```

This matches documents that have BOTH the region label AND the DocumentType label.

#### Nested Logic

```yaml
filter_expression_template:
  field:
    and:
      - or:
          - prop: label
            labelset: "PolicyType"
            label: "{policy_type}"
          - not:
              prop: label
              labelset: "PolicyType"
      - or:
          - prop: label
            labelset: "Region"
            label: "{region}"
          - not:
              prop: label
              labelset: "Region"
```

This creates a complex filter that handles multiple optional parameters gracefully.

### Filter Properties Reference

Common filter properties you can use:

| Property | Description | Example |
|----------|-------------|---------|
| `label` | Filter by classification labels | `{"prop": "label", "labelset": "PolicyType", "label": "policy_type_a"}` |
| `keyword` | Filter by keywords in text | `{"prop": "keyword", "word": "policy"}` |
| `field` | Filter by specific fields | `{"prop": "field", "type": "text", "name": "title"}` |
| `created` | Filter by creation date | `{"prop": "created", "since": "2024-01-01"}` |
| `modified` | Filter by modification date | `{"prop": "modified", "until": "2024-12-31"}` |

---

## Audit Metadata

Audit metadata allows you to attach contextual information to every Nuclia search request for logging, analytics, and compliance purposes. This metadata is sent to Nuclia and can be used to filter and analyze activity logs.

### Understanding Audit Metadata

- **Purpose**: Track who made requests, from where, and with what context
- **Storage**: Stored by Nuclia with each search request
- **Size Limit**: Maximum 10KB per request
- **Format**: Dictionary of string key-value pairs
- **Source**: All dynamic values must come from `template_parameters`

### Basic Audit Metadata Configuration

```yaml
template_parameters:
  - name: "user_email"
    description: "User's email address for audit logging"
    type: "string"
    default: ""

audit_metadata:
  enabled: true
  fields:
    environment: "production"        # Static value
    user_email: "{user_email}"       # From template_parameters
    query_text: "{query}"            # Always available
```

### How It Works

1. **Define Template Parameters**: Add any parameters you want to include in audit metadata to `template_parameters`
2. **Configure Audit Fields**: Map field names to templates in `audit_metadata.fields`
3. **LLM Provides Values**: The LLM passes parameter values when calling the tool
4. **Template Substitution**: The tool substitutes placeholders with actual values
5. **Sent to Nuclia**: The audit metadata is included in the search request

### Template Syntax

Audit metadata fields support the same template syntax as prompt rephrasing:

- **Static text**: `"production"` - Used as-is
- **Query placeholder**: `"{query}"` - Replaced with the user's query
- **Parameter placeholders**: `"{region}"`, `"{user_email}"` - Replaced with parameter values
- **Combined templates**: `"{user_name} ({user_email})"` - Multiple placeholders in one field

### Complete Example

```yaml
template_parameters:
  # Existing parameters for filtering/rephrasing
  - name: "region"
    description: "User region"
    type: "string"
    default: ""
  
  - name: "policy_type"
    description: "Document category or policy type"
    type: "string"
    default: ""
  
  # Audit-specific parameters
  - name: "user_email"
    description: "User's email address for audit logging"
    type: "string"
    required: false
    default: ""
  
  - name: "session_id"
    description: "Session ID for audit logging"
    type: "string"
    required: false
    default: ""
  
  - name: "user_department"
    description: "User's department for audit logging"
    type: "string"
    required: false
    default: ""

audit_metadata:
  enabled: true
  fields:
    # Static fields
    environment: "production"
    agent_name: "document_agent"
    agent_version: "1.0.0"
    
    # Dynamic fields from parameters
    user_email: "{user_email}"
    user_region: "{region}"
    user_policy_type: "{policy_type}"
    user_department: "{user_department}"
    session_id: "{session_id}"
    
    # Query information
    query_text: "{query}"
    
    # Combined fields
    user_context: "{user_email} from {region}"
```

### Agent Instructions for Audit Metadata

Update your agent instructions to extract and pass audit parameters:

```markdown
When calling the `generate_answer_with_citations` tool, always include:

**Required for filtering and context:**
- `region`: The user's region
- `policy_type`: The determined policy type

**Required for audit logging:**
- `user_email`: Extract from user profile in context
- `session_id`: Extract from session context
- `user_department`: Extract from user profile in context

Example tool call:
```json
{
  "query": "What is the time off policy?",
  "region": "emea",
  "policy_type": "policy_type_a",
  "user_email": "user@example.com",
  "session_id": "sess_abc123",
  "user_department": "your-department"
}
```
```

### Handling Missing Audit Parameters

Unlike filter parameters, missing audit parameters are handled gracefully:

1. **Empty values**: If a parameter is empty or missing, the field is skipped
2. **No errors**: Missing audit parameters never cause the tool to fail
3. **Warnings logged**: The tool logs warnings about undefined parameters
4. **Partial metadata**: The tool sends whatever audit metadata it can build

**Example Log Output:**
```
[NucliaRagTool] Audit metadata field 'session_id' references undefined parameter: 'session_id'. Add it to template_parameters if needed.
```

### Disabling Audit Metadata

To disable audit metadata entirely:

```yaml
audit_metadata:
  enabled: false
```

Or simply omit the `audit_metadata` configuration entirely.

