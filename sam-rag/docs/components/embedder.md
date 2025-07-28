# Embedder Component

The Embedder component is responsible for converting text chunks into vector embeddings for storage and retrieval.

## Overview

The Embedder component takes text chunks and converts them into vector embeddings using various embedding models. These embeddings are numerical representations of the text that capture semantic meaning, allowing for similarity-based retrieval. The component supports multiple embedding providers and models, with a focus on using LiteLLM as a unified interface.

## Key Classes

### EmbedderService

The `EmbedderService` class is the main entry point for the embedder component. It:

- Creates and manages the appropriate embedder based on configuration
- Provides methods for embedding text chunks
- Handles normalization of embeddings
- Provides utility methods for similarity calculations

```python
class EmbedderService:
    def __init__(self, config: Dict[str, Any] = None):
        # Initialize with configuration
        
    def embed_text(self, text: str) -> List[float]:
        # Embed a single text string
        
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # Embed multiple text strings
        
    def embed_chunks(self, chunks: List[str]) -> List[List[float]]:
        # Embed a list of text chunks
        
    def embed_file_chunks(self, file_chunks: List[Tuple[str, List[str]]]) -> Dict[str, List[List[float]]]:
        # Embed chunks from multiple files
        
    def get_embedding_dimension(self) -> int:
        # Get the dimension of the embeddings
        
    def cosine_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        # Calculate the cosine similarity between two embeddings
        
    def search_similar(self, query_embedding: List[float], embeddings: List[List[float]], top_k: int = 5) -> List[Tuple[int, float]]:
        # Search for the most similar embeddings to a query embedding
```

### EmbedderBase

The `EmbedderBase` class is the base class for all embedders. It:

- Defines the interface for embedders
- Provides common embedding functionality
- Handles normalization of embeddings

```python
class EmbedderBase:
    def __init__(self, config: Dict[str, Any] = None):
        # Initialize with configuration
        
    def embed_text(self, text: str) -> List[float]:
        # Embed a single text string
        
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # Embed multiple text strings
        
    def normalize_embedding(self, embedding: List[float]) -> List[float]:
        # Normalize a single embedding
        
    def normalize_embeddings(self, embeddings: List[List[float]]) -> List[List[float]]:
        # Normalize multiple embeddings
        
    def get_embedding_dimension(self) -> int:
        # Get the dimension of the embeddings
        
    def cosine_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        # Calculate the cosine similarity between two embeddings
```

### LiteLLMEmbedder

The `LiteLLMEmbedder` class is a concrete implementation of the `EmbedderBase` interface that uses LiteLLM to generate embeddings. It:

- Supports multiple embedding providers through LiteLLM
- Handles batching of embedding requests
- Provides error handling and fallbacks

```python
class LiteLLMEmbedder(EmbedderBase):
    def __init__(self, config: Dict[str, Any] = None):
        # Initialize with configuration
        
    def embed_text(self, text: str) -> List[float]:
        # Embed a single text string using LiteLLM
        
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # Embed multiple text strings using LiteLLM
        
    def get_embedding_dimension(self) -> int:
        # Get the dimension of the embeddings
```

## Configuration

The Embedder component is configured through the `embedding` section of the `configs/agents/rag.yaml` file:

```yaml
embedding:
  embedder_type: "openai"    # Type of embedding model
  embedder_params:
    model: ${OPENAI_EMBEDDING_MODEL}
    api_key: ${OPENAI_API_KEY}
    api_base: ${OPENAI_API_ENDPOINT}
    batch_size: 32
    additional_kwargs: {}
  normalize_embeddings: True # Whether to normalize embedding vectors
```

### Key Configuration Parameters

- `embedder_type`: The type of embedding model to use
- `embedder_params`: Parameters specific to the chosen embedding model
- `normalize_embeddings`: Whether to normalize embedding vectors (recommended for cosine similarity)

### Supported Embedder Types

- `openai`: OpenAI embedding models
- `azure_openai`: Azure OpenAI embedding models
- `cohere`: Cohere embedding models
- `vertex_ai`: Google Vertex AI embedding models
- `litellm`: LiteLLM embedding models (supports multiple providers)

### Common Embedder Parameters

- `model`: The name of the embedding model
- `api_key`: API key for authentication
- `api_base`: Base URL for the API
- `batch_size`: Number of texts to embed in a single API call
- `additional_kwargs`: Additional parameters to pass to the embedding API

## Embedding Process

The embedding process works as follows:

1. The `EmbedderService` receives text chunks to embed
2. It calls the appropriate embedder's `embed_texts` method
3. The embedder:
   - Batches the texts based on the configured batch size
   - Calls the embedding API for each batch
   - Combines the results
   - Returns the embeddings
4. If `normalize_embeddings` is `true`, the embeddings are normalized
5. The `EmbedderService` returns the embeddings to the caller

## Embedding Models

The Embedder component supports various embedding models through LiteLLM:

### OpenAI Embedding Models

- `text-embedding-ada-002`: 1536-dimensional embeddings
- `text-embedding-3-small`: 1536-dimensional embeddings
- `text-embedding-3-large`: 3072-dimensional embeddings

### Azure OpenAI Embedding Models

- Azure versions of OpenAI embedding models

### Cohere Embedding Models

- `embed-english-v3.0`: 1024-dimensional embeddings
- `embed-multilingual-v3.0`: 1024-dimensional embeddings

### Google Vertex AI Embedding Models

- `textembedding-gecko`: 768-dimensional embeddings
- `textembedding-gecko-multilingual`: 768-dimensional embeddings

## Embedding Normalization

Embedding normalization is the process of scaling the embedding vectors to have a unit L2 norm (length of 1). This is important for cosine similarity calculations, as it ensures that the similarity is based solely on the direction of the vectors, not their magnitude.

When `normalize_embeddings` is `true`, the embeddings are normalized using the following formula:

```
normalized_embedding = embedding / ||embedding||
```

where `||embedding||` is the L2 norm (Euclidean length) of the embedding vector.

## Similarity Calculations

The Embedder component provides methods for calculating the similarity between embeddings:

### Cosine Similarity

Cosine similarity measures the cosine of the angle between two vectors. It ranges from -1 (completely opposite) to 1 (exactly the same), with 0 indicating orthogonality (no correlation).

```
cosine_similarity(a, b) = (a · b) / (||a|| * ||b||)
```

where `a · b` is the dot product of the vectors, and `||a||` and `||b||` are their L2 norms.

If the embeddings are normalized, the cosine similarity simplifies to the dot product:

```
cosine_similarity(a, b) = a · b
```

### Similarity Search

The `search_similar` method finds the most similar embeddings to a query embedding:

1. Calculate the cosine similarity between the query embedding and each embedding in the collection
2. Sort the embeddings by similarity (highest first)
3. Return the top-k results as tuples of (index, similarity)

## Integration with Pipeline

The Embedder component integrates with the Pipeline component through the `embedding_handler` field of the `Pipeline` class. When the pipeline processes a file, it calls the `embed_texts` method of the `EmbedderService` to convert the text chunks into embeddings before passing them to the Vector Database component.

## Next Steps

- [Vector Database Component](vector_db.md)
- [Retriever Component](retriever.md)
- [Augmentation Component](augmentation.md)
- [Scanner Component](scanner.md)
- [Preprocessor Component](preprocessor.md)
- [Splitter Component](splitter.md)
