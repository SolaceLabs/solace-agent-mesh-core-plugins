# Vector Database Component

The Vector Database component is responsible for storing and retrieving vector embeddings for similarity search.

## Overview

The Vector Database component provides a unified interface for interacting with various vector database backends. It handles the storage of embeddings and their associated metadata, as well as similarity search operations. The component supports multiple vector database providers, including Qdrant, Chroma, Pinecone, and PostgreSQL with pgvector.

## Key Classes

### VectorDBService

The `VectorDBService` class is the main entry point for the vector database component. It:

- Creates and manages the appropriate vector database implementation based on configuration
- Provides methods for adding, updating, and deleting documents
- Handles similarity search operations

```python
class VectorDBService:
    def __init__(self, config: Dict[str, Any] = None):
        # Initialize with configuration
        
    def add_documents(self, documents: List[str], embeddings: List[List[float]], metadatas: List[Dict[str, Any]] = None, ids: List[str] = None) -> List[str]:
        # Add documents to the vector database
        
    def search(self, query_embedding: List[float], top_k: int = 5, filter: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        # Search for similar documents
        
    def delete(self, ids: List[str]) -> None:
        # Delete documents from the vector database
        
    def update(self, ids: List[str], documents: List[str], embeddings: List[List[float]], metadatas: List[Dict[str, Any]] = None) -> None:
        # Update documents in the vector database
```

### VectorDBBase

The `VectorDBBase` class is the base class for all vector database implementations. It:

- Defines the interface for vector database operations
- Provides common functionality for vector database operations
- Handles error handling and logging

```python
class VectorDBBase:
    def __init__(self, config: Dict[str, Any] = None):
        # Initialize with configuration
        
    def add_documents(self, documents: List[str], embeddings: List[List[float]], metadatas: List[Dict[str, Any]] = None, ids: List[str] = None) -> List[str]:
        # Add documents to the vector database
        
    def search(self, query_embedding: List[float], top_k: int = 5, filter: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        # Search for similar documents
        
    def delete(self, ids: List[str]) -> None:
        # Delete documents from the vector database
        
    def update(self, ids: List[str], documents: List[str], embeddings: List[List[float]], metadatas: List[Dict[str, Any]] = None) -> None:
        # Update documents in the vector database
```

### Vector Database Implementations

The vector database component includes several implementations for different vector database backends:

- `QdrantVectorDB`: Implementation for Qdrant
- `ChromaVectorDB`: Implementation for Chroma
- `PineconeVectorDB`: Implementation for Pinecone
- `PGVectorDB`: Implementation for PostgreSQL with pgvector

Each implementation extends the `VectorDBBase` class and provides backend-specific functionality.

## Configuration

The Vector Database component is configured through the `vector_db` section of the `configs/agents/rag.yaml` file:

```yaml
vector_db:
  # Qdrant configuration
  db_type: "qdrant"
  db_params:
    url: ${QDRANT_URL}
    api_key: ${QDRANT_API_KEY}
    collection_name: ${QDRANT_COLLECTION}
    embedding_dimension: ${QDRANT_EMBEDDING_DIMENSION}
```

### Key Configuration Parameters

- `db_type`: The type of vector database to use
- `db_params`: Parameters specific to the chosen vector database

### Supported Vector Database Types

- `qdrant`: Qdrant vector database
- `chroma`: Chroma vector database
- `pinecone`: Pinecone vector database
- `pgvector`: PostgreSQL with pgvector extension

### Common Vector Database Parameters

- `url`: URL of the vector database
- `api_key`: API key for authentication
- `collection_name`: Name of the collection to use
- `embedding_dimension`: Dimension of the embedding vectors

## Vector Database Operations

### Adding Documents

The `add_documents` method adds documents to the vector database:

```python
def add_documents(self, documents: List[str], embeddings: List[List[float]], metadatas: List[Dict[str, Any]] = None, ids: List[str] = None) -> List[str]:
    # Add documents to the vector database
```

Parameters:
- `documents`: List of document texts
- `embeddings`: List of embedding vectors
- `metadatas`: Optional list of metadata dictionaries
- `ids`: Optional list of document IDs

Returns:
- List of document IDs (either the provided IDs or generated ones)

### Searching for Similar Documents

The `search` method searches for documents similar to a query embedding:

```python
def search(self, query_embedding: List[float], top_k: int = 5, filter: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    # Search for similar documents
```

Parameters:
- `query_embedding`: The query embedding vector
- `top_k`: Number of results to return
- `filter`: Optional filter to apply to the search

Returns:
- List of dictionaries containing:
  - `text`: The document text
  - `metadata`: The document metadata
  - `distance`: The distance/similarity score
  - `id`: The document ID

### Deleting Documents

The `delete` method deletes documents from the vector database:

```python
def delete(self, ids: List[str]) -> None:
    # Delete documents from the vector database
```

Parameters:
- `ids`: List of document IDs to delete

### Updating Documents

The `update` method updates documents in the vector database:

```python
def update(self, ids: List[str], documents: List[str], embeddings: List[List[float]], metadatas: List[Dict[str, Any]] = None) -> None:
    # Update documents in the vector database
```

Parameters:
- `ids`: List of document IDs to update
- `documents`: List of updated document texts
- `embeddings`: List of updated embedding vectors
- `metadatas`: Optional list of updated metadata dictionaries

## Vector Database Implementations

### Qdrant

Qdrant is a vector database designed for production-ready similarity search. The `QdrantVectorDB` implementation:

- Connects to a Qdrant server using the provided URL and API key
- Creates a collection if it doesn't exist
- Adds, updates, and deletes points in the collection
- Performs similarity search using the provided query embedding

Configuration:

```yaml
vector_db:
  db_type: "qdrant"
  db_params:
    url: ${QDRANT_URL}
    api_key: ${QDRANT_API_KEY}
    collection_name: ${QDRANT_COLLECTION}
    embedding_dimension: ${QDRANT_EMBEDDING_DIMENSION}
```

### Chroma

Chroma is an open-source embedding database designed for AI applications. The `ChromaVectorDB` implementation:

- Connects to a Chroma server using the provided host and port
- Creates a collection if it doesn't exist
- Adds, updates, and deletes documents in the collection
- Performs similarity search using the provided query embedding

Configuration:

```yaml
vector_db:
  db_type: "chroma"
  db_params:
    host: ${CHROMA_HOST}
    port: ${CHROMA_PORT}
    collection_name: ${CHROMA_COLLECTION}
    persist_directory: ${CHROMA_PERSIST_DIR}
    embedding_function: ${CHROMA_EMBEDDING_FUNCTION}
    embedding_dimension: ${CHROMA_EMBEDDING_DIMENSION}
```

### Pinecone

Pinecone is a managed vector database service. The `PineconeVectorDB` implementation:

- Connects to Pinecone using the provided API key
- Creates an index if it doesn't exist
- Adds, updates, and deletes vectors in the index
- Performs similarity search using the provided query embedding

Configuration:

```yaml
vector_db:
  db_type: "pinecone"
  db_params:
    api_key: ${PINECONE_API_KEY}
    index_name: ${PINECONE_INDEX}
    namespace: ${PINECONE_NAMESPACE}
    embedding_dimension: ${PINECONE_DIMENSIONS}
    metric: ${PINECONE_METRIC}
    cloud: ${PINECONE_CLOUD}
    region: ${PINECONE_REGION}
```

### PostgreSQL with pgvector

PostgreSQL with the pgvector extension provides vector similarity search capabilities. The `PGVectorDB` implementation:

- Connects to a PostgreSQL database using the provided connection parameters
- Creates a table with a vector column if it doesn't exist
- Adds, updates, and deletes rows in the table
- Performs similarity search using the provided query embedding

Configuration:

```yaml
vector_db:
  db_type: "pgvector"
  db_params:
    host: ${PGVECTOR_HOST}
    port: ${PGVECTOR_PORT}
    database: ${PGVECTOR_DATABASE}
    user: ${PGVECTOR_USER}
    password: ${PGVECTOR_PASSWORD}
    table_name: ${PGVECTOR_TABLE}
    embedding_dimension: ${PGVECTOR_DIMENSION}
```

## Integration with Pipeline

The Vector Database component integrates with the Pipeline component through the `ingestion_handler` field of the `Pipeline` class. When the pipeline processes a file, it calls the `ingest_embeddings` method of the `IngestionService`, which in turn calls the `add_documents` method of the `VectorDBService` to store the embeddings in the vector database.

## Next Steps

- [Retriever Component](retriever.md)
- [Augmentation Component](augmentation.md)
- [Scanner Component](scanner.md)
- [Preprocessor Component](preprocessor.md)
- [Splitter Component](splitter.md)
- [Embedder Component](embedder.md)
