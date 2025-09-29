# SAM RAG Tools and Lifecycle Functions

## Overview

The SAM RAG plugin provides tools for document ingestion and retrieval, as well as lifecycle functions for initializing and cleaning up the RAG agent. This document provides detailed information about these components.

## Tools Implementation

The SAM RAG plugin provides two main tools for interacting with the RAG system:

### 1. `ingest_document` Tool

The `ingest_document` tool allows you to ingest a document into the RAG system. The document is processed through the RAG pipeline, which includes preprocessing, splitting, embedding, and storing in the vector database.

#### Parameters

- `input_file`: The filename (and optional version) of the input artifact from the artifact service. The file can be a PDF, TXT, or other supported format.
- `tool_context`: The context provided by the ADK framework.
- `tool_config`: Optional tool configuration.

#### Return Value

A dictionary containing the status of the ingestion operation:

```json
{
  "status": "success",
  "message": "Document 'example.pdf' successfully ingested through RAG pipeline.",
  "document_ids": ["doc_id_1", "doc_id_2"],
  "artifact_url": "artifact://app_name/user_id/session_id/example.pdf?version=1"
}
```

#### Error Handling

The tool handles various error scenarios:
- Missing tool context
- Missing host component
- Missing file tracker
- File not found
- Invalid file format
- Pipeline processing errors

#### Example Usage

```python
result = await ingest_document(
    input_file="example.pdf:1",
    tool_context=context
)
```

### 2. `search_documents` Tool

The `search_documents` tool allows you to search for documents relevant to a query and retrieve the relevant content and references to documents.

#### Parameters

- `query`: The search query.
- `filter_criteria`: Optional criteria to filter search results.
- `include_original_documents`: Whether to include original documents as artifacts in the response.
- `include_references`: Whether to include document references in the response.
- `tool_context`: The context provided by the ADK framework.
- `tool_config`: Optional tool configuration.

#### Return Value

A dictionary containing the search results, augmented response, and document references:

```json
{
  "status": "success",
  "augmented_response": "The augmented response based on the retrieved documents.",
  "message": "Successfully retrieved and augmented relevant documents.",
  "chunks": [
    {
      "text": "The text content of the chunk.",
      "score": 0.95,
      "metadata": {
        "file_name": "example.pdf",
        "source": "upload_file",
        "artifact_url": "artifact://app_name/user_id/session_id/example.pdf?version=1"
      },
      "artifact_url": "artifact://app_name/user_id/session_id/example.pdf?version=1"
    }
  ]
}
```

#### Error Handling

The tool handles various error scenarios:
- Missing tool context
- Missing host component
- Missing augmentation handler
- No relevant documents found
- Artifact retrieval errors

#### Example Usage

```python
result = await search_documents(
    query="What is the capital of France?",
    filter_criteria={"source": "upload_file"},
    include_original_documents=True,
    include_references=True,
    tool_context=context
)
```

## Lifecycle Functions

The SAM RAG plugin provides lifecycle functions for initializing and cleaning up the RAG agent.

### 1. `initialize_rag_agent` Function

The `initialize_rag_agent` function initializes the RAG agent with the provided configuration. It sets up the scanner, preprocessor, splitter, embedder, and vector DB services.

#### Parameters

- `host_component`: The host component that will host the RAG agent.
- `init_config`: The configuration for the RAG agent, of type `RagAgentConfig`.

#### Configuration Classes

The RAG agent configuration is defined using Pydantic models:

- `RagAgentConfig`: The main configuration class for the RAG agent.
  - `scanner`: Configuration for the scanner component.
  - `preprocessor`: Configuration for the preprocessor component.
  - `splitter`: Configuration for the splitter component.
  - `embedding`: Configuration for the embedding component.
  - `vector_db`: Configuration for the vector database component.
  - `llm`: Configuration for the LLM component.
  - `retrieval`: Configuration for the retrieval component.

#### Initialization Process

1. The function creates a pipeline with the provided configuration.
2. It stores the pipeline, file tracker, and augmentation handler in the host component's agent-specific state.
3. It sets the system instruction for the LLM.

#### Error Handling

If an error occurs during initialization, the function logs the error and raises a `RuntimeError`.

### 2. `cleanup_rag_agent_resources` Function

The `cleanup_rag_agent_resources` function cleans up resources used by the RAG agent.

#### Parameters

- `host_component`: The host component that hosts the RAG agent.

#### Cleanup Process

1. The function retrieves the pipeline from the host component's agent-specific state.
2. If the pipeline exists, it calls the pipeline's `cleanup` method to clean up resources.

#### Error Handling

If an error occurs during cleanup, the function logs the error but does not prevent further cleanup.

## Integration with ADK Framework

The SAM RAG plugin integrates with the ADK framework through the following mechanisms:

1. **Tool Registration**: The tools are registered with the ADK framework in the configuration file:

```yaml
tools:
  - tool_type: python
    component_module: "sam_rag.tools"
    function_name: "ingest_document"
  
  - tool_type: python
    component_module: "sam_rag.tools"
    function_name: "search_documents"
```

2. **Lifecycle Function Registration**: The lifecycle functions are registered with the ADK framework in the configuration file:

```yaml
agent_init_function:
  module: "sam_rag.lifecycle"
  name: "initialize_rag_agent"
  config:
    # RAG configuration...

agent_cleanup_function:
  module: "sam_rag.lifecycle"
  name: "cleanup_rag_agent_resources"
```

3. **Artifact Service Integration**: The tools and lifecycle functions integrate with the ADK framework's artifact service to store and retrieve documents.

4. **Host Component Integration**: The lifecycle functions integrate with the host component to store and retrieve agent-specific state.
