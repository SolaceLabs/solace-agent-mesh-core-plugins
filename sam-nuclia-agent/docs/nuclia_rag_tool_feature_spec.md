# Feature Specification: Generic Nuclia RAG Tool

## 1. Overview

This document specifies the design and functionality of the Generic Nuclia RAG (Retrieval-Augmented Generation) Tool for the Solace Agent Mesh (SAM).

The tool's primary purpose is to provide a reusable, configuration-driven interface for SAM agents to connect to Nuclia's advanced RAG capabilities. It takes a natural language query, orchestrates a generative search against a specified Nuclia Knowledge Box, processes the response to include verifiable citations, and packages the result into a structured artifact.

This approach simplifies the agent's role to high-level orchestration, promoting efficiency, security, and a rich, trustworthy user experience.

## 2. Goals & Requirements

-   **Trust and Verifiability**: The user must be able to see exactly where the information in the generated answer comes from. The tool must inject clickable, footnote-style citation markers into the answer and provide secure links that point to the exact page of the source document.
-   **Security**: Access to source documents must be brokered through a secure mechanism. The tool must generate URLs that point to the SAM Gateway, not directly to Nuclia, preventing the exposure of long-lived credentials or backend system details to the client.
-   **Efficiency and Reusability**: The tool must be generic and not tied to a specific use case (e.g., your-department). It must handle all complex data processing (query rephrasing, response parsing, citation injection) and return a simple, actionable result to the LLM, minimizing token usage and simplifying the agent's logic.
-   **Configurability**: The tool's behavior, especially prompt generation and connection details, must be fully controllable via the agent's YAML configuration without requiring changes to the tool's Python code.

## 3. Core Workflow

The tool executes the following steps upon invocation:

1.  **Configuration Validation**: On initialization, the tool validates that essential Nuclia connection details (`base_url`, `kb_id`, `token`, `api_key`) are present in the `tool_config`.
2.  **Prompt Rephrasing**: It uses the `prompt_rephrasing` configuration object to dynamically build a context-rich prompt. It extracts specified data from the `tool_context` and injects it into a prompt template. If this configuration is omitted, the original user query is used directly.
3.  **Querying Nuclia**: It authenticates with the Nuclia SDK and calls the `search.ask()` method with `citations=True` to receive a generative answer.
4.  **Response Formatting**: It processes the `AskAnswer` object returned by the Nuclia SDK.
    -   It decodes the `answer` bytes to a UTF-8 string.
    -   It parses the `citations` dictionary to create a unique, numbered citation for each distinct source paragraph.
    -   It generates a secure, page-specific URL for each citation (e.g., `/gateway/download/...#page=5`).
    -   It injects clickable footnote markers (e.g., `[[1]](url)`) into the answer text at the correct character positions.
    -   It creates a separate, pre-formatted markdown list of all citations, including the page number for clarity.
5.  **Artifact Creation**: It combines the answer and citations into a single markdown string and saves it as one artifact (`<base_name>.md`).
6.  **Tool Output**: It returns a dictionary to the LLM containing the `status` and details for the single created artifact (`response_artifact`), empowering the agent to use an embed for the final response.

## 4. Design Decisions

-   **Generic Tool (`nuclia_rag_tool.py`)**: Decoupling the Nuclia logic from specific agent use cases promotes code reuse and simplifies maintenance. Any agent can use this tool by providing its own configuration.
-   **Artifact-based Output**: Instead of returning a large, unstructured block of text to the LLM, the tool returns a reference to a structured artifact. This is more efficient (fewer tokens), simplifies the LLM's task to orchestration, and preserves the rich structure of the answer and citations. The agent can then use `artifact_content` embeds to display the information.
-   **Brokered, Page-Specific URLs**: This is a security-first approach. It abstracts the Nuclia backend from the end-user and prevents the exposure of long-lived tokens. Adding the page number fragment (`#page=N`) significantly improves the user experience by directing them to the precise location of the source information.

## 5. Tool Configuration (`tool_config`)

The tool is controlled via the `tool_config` section in the agent's YAML definition.

| Parameter                               | Type                 | Required | Default                      | Description                                                                                             |
| --------------------------------------- | -------------------- | -------- | ---------------------------- | ------------------------------------------------------------------------------------------------------- |
| `base_url`                              | String               | Yes      | -                            | The base URL for the Nuclia API (e.g., `https://europe-1.nuclia.cloud/api/v1`).                         |
| `kb_id`                                 | String               | Yes      | -                            | The unique ID of the Nuclia Knowledge Box to query.                                                     |
| `token`                                 | String               | Yes      | -                            | The long-lived Nuclia Service Account API key. Should be loaded from an environment variable.           |
| `api_key`                               | String               | Yes      | -                            | The Nuclia Account ID. Should be loaded from an environment variable.                                   |
| `top_k`                                 | Integer              | No       | `5`                          | The maximum number of context paragraphs to retrieve from Nuclia to generate the answer.                |
| `output_filename_base`                  | String               | No       | `"nuclia_answer"`            | Base name for output artifacts. The tool will append '.md' extension.                                   |
| `artifact_description_query_max_length` | Integer              | No       | `150`                        | The maximum character length of the original query to include in the created artifact's description.    |
| `inline_citation_links`                 | Boolean              | No       | `true`                       | If true, citation markers in the answer text (e.g., `[1]`) will be rendered as clickable markdown links. |
| `template_parameters`                   | List of Objects      | No       | `[]`                         | List of dynamic parameters for prompt rephrasing, filtering, and audit metadata.                        |
| `prompt_rephrasing`                     | Object               | No       | `null`                       | An object to control dynamic prompt generation. If omitted, the original query is used directly.        |
| `filter_expression_template`            | Object               | No       | `null`                       | Template for Nuclia filter expressions using template parameters.                                       |
| `audit_metadata`                        | Object               | No       | `null`                       | Configuration for audit metadata to include in Nuclia search requests.                                  |

### `prompt_rephrasing` Object Structure

-   **`template`** (String, Required): The prompt template. Must contain `{query}` placeholder. Can contain other placeholders matching `template_parameters` names.

### `audit_metadata` Object Structure

-   **`enabled`** (Boolean, Optional, Default: `true`): Whether to include audit metadata in requests.
-   **`fields`** (Dictionary, Required): Dictionary of audit metadata fields. Keys are field names, values are templates that can contain:
    -   Static text: `"production"`
    -   `{query}`: The user's query
    -   Any `template_parameters`: `{your-country}`, `{user@example.com}`, etc.

## 6. Tool Output Specification

The tool returns a dictionary to the LLM with details of the single created artifact. The agent can use an `artifact_content` embed to access the combined content.

**Tool Return Dictionary Structure:**
```json
{
  "status": "success",
  "nuclia_learning_id": "abc123-def456-ghi789",
  "message_to_llm": "...",
  "response_artifact": {
    "filename": "nuclia_answer.md",
    "version": 1,
    "mime_type": "text/markdown"
  }
}
```

**Response Fields:**
- `status`: Execution status ("success", "error", "no_answer_found")
- `nuclia_learning_id`: Unique identifier from Nuclia for this search request, used for tracking and correlation
- `message_to_llm`: Contextual message for the LLM about the result
- `response_artifact`: Details of the created markdown artifact
- `filter_applied`: (Optional) Boolean indicating if filtering was applied
- `applied_filter`: (Optional) The actual filter expression that was used
- `missing_filter_parameters`: (Optional) List of parameters that were missing

**`response_artifact` Content:**
A single markdown file containing the generated answer text, with footnote markers, followed by a formatted list of sources. For example:
```markdown
This is the generative answer to the user's question, with a citation marker here [[1](https://.../secure_url_1#page=5)].
