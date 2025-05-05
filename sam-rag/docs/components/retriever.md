# Retriever Component

The Retriever component is responsible for searching the vector database for documents relevant to a query.

## Overview

The Retriever component takes a query, converts it to an embedding, and searches the vector database for similar documents. It provides a unified interface for retrieving relevant documents regardless of the underlying vector database implementation.

## Key Classes

### Retriever

The `Retriever` class is the main class of the retriever component. It:

- Embeds queries using the embedding service
- Searches the vector database for similar documents
- Handles filtering and ranking of search results

```python
class Retriever:
    def __init__(self, config: Dict[str, Any] = None):
        # Initialize with configuration
        
    def retrieve(self, query: str, filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        # Retrieve documents similar to the query
        
    def get_query_embedding(self, query: str) -> List[float]:
        # Get the embedding for a query
```

## Configuration

The Retriever component is configured through the `retrieval` section of the `configs/agents/rag.yaml` file:

```yaml
retrieval:
  top_k: 7                   # Number of chunks to retrieve
```

It also uses the `embedding` and `vector_db` configurations for embedding generation and vector database access.

### Key Configuration Parameters

- `top_k`: Number of chunks to retrieve for each query

## Retrieval Process

The retrieval process works as follows:

1. The `Retriever` receives a query and an optional filter
2. It converts the query to an embedding using the embedding service
3. It searches the vector database for documents similar to the query embedding
4. It returns the search results, which include:
   - The document text
   - The document metadata
   - The similarity score

```python
def retrieve(self, query: str, filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    try:
        # Get query embedding
        query_embedding = self.get_query_embedding(query)

        # Search the vector database
        results = self.vector_db.search(
            query_embedding=query_embedding,
            top_k=self.top_k,
            filter=filter,
        )

        logger.info(f"Found {len(results)} results for query")
        return results
    except Exception:
        logger.error("Error retrieving documents.")
        raise ValueError(
            "Error retrieving documents. Please check the query and try again."
        ) from None
```

## Query Embedding

The `get_query_embedding` method converts a query to an embedding using the embedding service:

```python
def get_query_embedding(self, query: str) -> List[float]:
    try:
        # Get query embedding
        embeddings = self.embedding_service.embed_texts([query])
        if not embeddings or len(embeddings) == 0:
            raise ValueError("Failed to generate embedding for query") from None

        return embeddings[0]
    except Exception:
        logger.error("Error generating query embedding.")
        raise ValueError(
            "Error generating query embedding. Please check the query and try again."
        ) from None
```

## Search Results

The search results are a list of dictionaries, where each dictionary contains:

- `text`: The document text
- `metadata`: The document metadata
- `distance`: The distance/similarity score
- `id`: The document ID

## Filtering

The `retrieve` method supports filtering of search results through the `filter` parameter. The filter is a dictionary that specifies conditions that the document metadata must satisfy. The exact format of the filter depends on the underlying vector database implementation.

For example, a filter might look like:

```python
filter = {
    "source": "document1.pdf",
    "page": {"$gte": 10, "$lte": 20}
}
```

This would retrieve only documents from "document1.pdf" with a page number between 10 and 20.

## Integration with Augmentation

The Retriever component is used by the Augmentation component to retrieve relevant documents for a query. The Augmentation component then enhances the retrieved documents using an LLM to provide a more coherent and informative response.

## Integration with Pipeline

The Retriever component integrates with the Pipeline component through the `retriever` field of the `AugmentationService` class. When the augmentation service processes a query, it calls the `retrieve` method of the `Retriever` to find relevant documents before enhancing them with the LLM.

## Next Steps

- [Augmentation Component](augmentation.md)
- [Scanner Component](scanner.md)
- [Preprocessor Component](preprocessor.md)
- [Splitter Component](splitter.md)
- [Embedder Component](embedder.md)
- [Vector Database Component](vector_db.md)
