# Augmentation Component

The Augmentation component is responsible for enhancing retrieved documents with LLM-generated content to provide more coherent and informative responses.

## Overview

The Augmentation component takes retrieved documents from the vector database and enhances them using a Language Model (LLM). It merges chunks from the same source, uses an LLM to clean and improve the content, and returns the enhanced content with source information. This process is known as Retrieval-Augmented Generation (RAG).

## Key Classes

### AugmentationService

The `AugmentationService` class is the main class of the augmentation component. It:

- Initializes the retriever for finding relevant documents
- Configures LiteLLM for accessing language models
- Provides methods for augmenting retrieved content

```python
class AugmentationService:
    def __init__(self, config: Dict[str, Any] = None):
        # Initialize with configuration
        
    def augment(self, query: str, session_id: str, filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        # Retrieve and augment documents relevant to the query
        
    def _merge_chunks_by_source(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Merge chunks that come from the same source document
        
    def _augment_chunks_with_llm(self, query: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Use LLM to clean and improve the content of merged chunks
        
    def _upload_files_to_fileservice(self, chunks: List[Dict[str, Any]], session_id: str) -> List[Dict[str, Any]]:
        # Upload files to the file service and return the list of files
        
    def _invoke_litellm(self, prompt: str) -> str:
        # Invoke LiteLLM to generate text
        
    def _create_augmentation_prompt(self, query: str, text: str) -> str:
        # Create a prompt for the LLM to improve the content
        
    def _extract_content(self, chunks: List[Dict[str, Any]]) -> str:
        # Extract contents from a list of chunks
```

## Configuration

The Augmentation component is configured through the `llm` section of the `configs/agents/rag.yaml` file:

```yaml
llm:
  load_balancer:
    - model_name: "gpt-4o" # model alias
      litellm_params:
            model: openai/${OPENAI_MODEL_NAME}
            api_key: ${OPENAI_API_KEY}
            api_base: ${OPENAI_API_ENDPOINT}
            temperature: 0.01
            # add any other parameters here
    - model_name: "claude-3-5-sonnet" # model alias
      litellm_params:
            model: anthropic/${ANTHROPIC_MODEL_NAME}
            api_key: ${ANTHROPIC_API_KEY}
            api_base: ${ANTHROPIC_API_ENDPOINT}
            # add any other parameters here
```

It also uses the `retrieval` configuration for controlling the number of chunks to retrieve.

### Key Configuration Parameters

- `load_balancer`: List of LLM configurations for load balancing
- `model_name`: Alias for the model
- `litellm_params`: Parameters for LiteLLM

### Common LiteLLM Parameters

- `model`: The model to use (provider/model_name format)
- `api_key`: API key for authentication
- `api_base`: Base URL for the API
- `temperature`: Temperature for generation (lower values are more deterministic)
- `max_tokens`: Maximum number of tokens to generate

## Augmentation Process

The augmentation process works as follows:

1. The `AugmentationService` receives a query, session ID, and optional filter
2. It retrieves relevant chunks from the vector database using the retriever
3. It merges chunks from the same source document
4. It uses an LLM to clean and improve the content of the merged chunks
5. It uploads the source files to the file service
6. It extracts the content from the augmented chunks
7. It returns the augmented content and file information

```python
def augment(self, query: str, session_id: str, filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    try:
        # Retrieve relevant chunks
        retrieved_chunks = self.retriever.retrieve(query, filter=filter)

        # Merge chunks by source
        merged_chunks = self._merge_chunks_by_source(retrieved_chunks)

        # Augment merged chunks with LLM
        augmented_chunks = self._augment_chunks_with_llm(query, merged_chunks)

        # Upload files to file service
        files = self._upload_files_to_fileservice(augmented_chunks, session_id)

        # Extract content
        content = self._extract_content(augmented_chunks)

        logger.info(f"Augmented {len(augmented_chunks)} chunks for query")
        return content, files
    except Exception:
        logger.error("Error augmenting documents.")
        raise ValueError("Error augmenting documents") from None
```

## Chunk Merging

The `_merge_chunks_by_source` method merges chunks that come from the same source document:

```python
def _merge_chunks_by_source(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Group chunks by source
    chunks_by_source = defaultdict(list)
    for chunk in chunks:
        # Extract source from metadata
        metadata = chunk.get("metadata", {})
        source = metadata.get("source", "unknown")

        # Group by source
        chunks_by_source[source].append(chunk)

    # Merge chunks for each source
    merged_chunks = []
    for source, source_chunks in chunks_by_source.items():
        # Sort chunks by distance (lowest first)
        sorted_chunks = sorted(
            source_chunks, key=lambda x: x.get("distance", 0), reverse=False
        )

        # Combine text from chunks
        combined_text = "\n".join(chunk["text"] for chunk in sorted_chunks)

        # Use metadata from the highest-scoring chunk
        best_metadata = sorted_chunks[0].get("metadata", {}).copy()

        # Create merged chunk
        merged_chunk = {
            "text": combined_text,
            "metadata": best_metadata,
            "source": source,
        }

        merged_chunks.append(merged_chunk)

    return merged_chunks
```

## LLM Augmentation

The `_augment_chunks_with_llm` method uses an LLM to clean and improve the content of the merged chunks:

```python
def _augment_chunks_with_llm(self, query: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    augmented_chunks = []

    for chunk in chunks:
        # Extract information
        text = chunk["text"]
        source = chunk.get("source", "unknown")
        metadata = chunk.get("metadata", {})

        # If LiteLLM is available, use it to improve the content
        if self.llm_available:
            try:
                # Create prompt for LLM
                prompt = self._create_augmentation_prompt(query, text)

                # Get improved content from LLM using LiteLLM
                response = self._invoke_litellm(prompt)
                improved_content = response.strip()

                logger.debug(f"Improved content with LiteLLM for source: {source}")
            except Exception as e:
                logger.warning(f"Error using LiteLLM to improve content: {str(e)}")
                improved_content = text  # Fall back to original text
        else:
            improved_content = text  # No LLM available

        # Create augmented chunk
        augmented_chunk = {
            "content": improved_content,
            "source": source,
            "metadata": metadata,
        }

        augmented_chunks.append(augmented_chunk)

    return augmented_chunks
```

## File Service Integration

The `_upload_files_to_fileservice` method uploads the source files to the file service:

```python
def _upload_files_to_fileservice(self, chunks: List[Dict[str, Any]], session_id: str) -> List[Dict[str, Any]]:
    files = []

    for chunk in chunks:
        # Extract source from chunk (source is a file path)
        source_path = chunk.get("source", "")
        if not source_path:
            continue

        try:
            # Upload file to file service using upload_from_file
            file_meta = self.file_service.upload_from_file(
                source_path, session_id, data_source="Augmentation Service"
            )

            # Add URL to chunk's files data field in the required format
            if "file" not in chunk:
                chunk["file"] = []

            chunk["file"] = file_meta

            files.append(file_meta)

        except Exception as e:
            logger.error(f"Error uploading file to file service: {str(e)}")
            # If upload fails, still include the chunk without file URL
            files.append(chunk)

    return files
```

## LiteLLM Integration

The `_invoke_litellm` method invokes LiteLLM to generate text:

```python
def _invoke_litellm(self, prompt: str) -> str:
    try:
        start_time = time.time()

        # Prepare messages for LiteLLM
        messages = [{"role": "user", "content": prompt}]

        # Use the first model in the load balancer config
        if not self.load_balancer_config:
            raise ValueError("No LLM models configured in load balancer") from None

        model_config = self.load_balancer_config[0]
        litellm_params = model_config.get("litellm_params", {})

        # Call LiteLLM
        response = litellm.completion(
            model=litellm_params.get("model", "openai/gpt-4o"),
            messages=messages,
            api_key=litellm_params.get("api_key"),
            api_base=litellm_params.get("api_base"),
            temperature=litellm_params.get("temperature", 0.01),
            max_tokens=litellm_params.get("max_tokens", 1000),
        )

        end_time = time.time()
        processing_time = round(end_time - start_time, 3)
        logger.debug("LiteLLM processing time: %s seconds", processing_time)

        # Extract the response content
        if response and response.choices and len(response.choices) > 0:
            return response.choices[0].message.content
        else:
            logger.warning("Empty response from LiteLLM")
            return ""

    except Exception:
        logger.error("Error invoking LiteLLM.")
        raise ValueError("Error invoking LiteLLM") from None
```

## Augmentation Prompt

The `_create_augmentation_prompt` method creates a prompt for the LLM to improve the content:

```python
def _create_augmentation_prompt(self, query: str, text: str) -> str:
    return (
        f"Given the query: '{query}', please clean and improve the following content:\n\n"
        f"{text}\n\n"
        "Make sure to maintain the original meaning while enhancing clarity and coherence."
    )
```

## Integration with Pipeline

The Augmentation component integrates with the Pipeline component through the `augmentation_handler` field of the `Pipeline` class. When the RAG action is invoked, it calls the `augment` method of the `AugmentationService` to retrieve and enhance relevant documents.

## Next Steps

- [Scanner Component](scanner.md)
- [Preprocessor Component](preprocessor.md)
- [Splitter Component](splitter.md)
- [Embedder Component](embedder.md)
- [Vector Database Component](vector_db.md)
- [Retriever Component](retriever.md)
