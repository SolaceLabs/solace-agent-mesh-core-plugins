"""
Redis (legacy) vector database implementation.
This version uses the 'redis' package directly.
"""

import uuid
import numpy as np
from typing import Dict, Any, List, Optional
from solace_ai_connector.common.log import log as logger

from ..vector_db_base import VectorDBBase


class RedisDB(VectorDBBase):
    """
    Vector database using Redis with vector search.
    """

    def __init__(
        self,
        config: Dict[str, Any] = None,
        hybrid_search_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the Redis vector database.

        Args:
            config: A dictionary containing configuration parameters.
                - host: The Redis host (default: "localhost").
                - port: The Redis port (default: 6379).
                - password: The Redis password (optional).
                - index_name: The name of the index to use (default: "documents").
                - prefix: The prefix to use for keys (default: "doc:").
                - embedding_dimension: The dimension of the embeddings (default: 768).
            hybrid_search_config: Optional dictionary containing hybrid search configuration.
                                  Note: This legacy RedisDB implementation does not support hybrid search.
        """
        super().__init__(config=config, hybrid_search_config=hybrid_search_config)
        if self.hybrid_search_enabled:
            logger.warning(
                "RedisDB (legacy): Hybrid search was enabled in config, but this implementation "
                "does not support hybrid search. It will operate in dense-only mode."
            )
            # Force disable hybrid search for this specific implementation
            self.hybrid_search_enabled = False

        self.host = self.config.get("host", "localhost")
        self.port = self.config.get("port", 6379)
        self.password = self.config.get("password")
        self.index_name = self.config.get("index_name", "documents")
        self.prefix = self.config.get("prefix", "doc:")
        self.embedding_dimension = self.config.get("embedding_dimension", 768)
        self.client = None
        self._setup_client()

    def _setup_client(self) -> None:
        """
        Set up the Redis client.
        """
        try:
            import redis
            from redis.commands.search.field import TextField, VectorField
            from redis.commands.search.indexDefinition import IndexDefinition, IndexType

            # Create the client
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                decode_responses=True,
            )

            # Check if the index exists
            try:
                self.client.ft(self.index_name).info()
            except:
                # Create the index
                schema = (
                    TextField("text"),
                    TextField("source"),  # Assuming 'source' is a common metadata field
                    VectorField(
                        "embedding",
                        "FLAT",
                        {
                            "TYPE": "FLOAT32",
                            "DIM": self.embedding_dimension,
                            "DISTANCE_METRIC": "COSINE",
                        },
                    ),
                )

                self.client.ft(self.index_name).create_index(
                    schema,
                    definition=IndexDefinition(
                        prefix=[self.prefix], index_type=IndexType.HASH
                    ),
                )
        except ImportError:
            raise ImportError(
                "The redis package is required for RedisDB. "
                "Please install it with `pip install redis`."
            ) from None

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        sparse_vectors: Optional[List[Optional[Dict[int, float]]]] = None,  # Ignored
    ) -> List[str]:
        """
        Add documents to the vector database.

        Args:
            documents: The documents to add.
            embeddings: The embeddings of the documents.
            metadatas: Optional metadata for each document.
            ids: Optional IDs for each document.
            sparse_vectors: Ignored by this implementation.

        Returns:
            The IDs of the added documents.
        """
        if sparse_vectors:
            logger.warning(
                "RedisDB (legacy): 'sparse_vectors' parameter was provided but will be ignored."
            )
        if not documents or not embeddings:
            return []

        # Generate IDs if not provided
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(len(documents))]

        # Create default metadata if not provided
        if metadatas is None:
            metadatas = [{"source": "unknown"} for _ in range(len(documents))]

        # Add the documents
        pipeline = self.client.pipeline()
        for i in range(len(documents)):
            # Convert embedding to bytes
            embedding_bytes = np.array(embeddings[i], dtype=np.float32).tobytes()

            # Prepare the hash fields
            hash_fields: Dict[str, Any] = {  # Ensure type for hash_fields
                "text": documents[i],
                "embedding": embedding_bytes,
            }

            # Add metadata fields
            if metadatas and i < len(metadatas):
                for key, value in metadatas[i].items():
                    # Ensure metadata values are strings for Redis HSET
                    hash_fields[key] = (
                        str(value)
                        if not isinstance(value, (bytes, str, int, float))
                        else value
                    )

            # Add the hash
            key = f"{self.prefix}{ids[i]}"
            pipeline.hset(key, mapping=hash_fields)

        # Execute the pipeline
        pipeline.execute()

        return ids

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
        query_sparse_vector: Optional[Dict[int, float]] = None,  # Ignored
        request_hybrid: bool = False,  # Ignored
    ) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query embedding.

        Args:
            query_embedding: The query embedding.
            top_k: The number of results to return.
            filter: Optional filter to apply to the search.
            query_sparse_vector: Ignored by this implementation.
            request_hybrid: Ignored by this implementation.

        Returns:
            A list of dictionaries containing the search results.
        """
        if query_sparse_vector or request_hybrid:
            logger.warning(
                "RedisDB (legacy): 'query_sparse_vector' or 'request_hybrid' was provided but will be ignored."
            )

        # Prepare the query
        # Base query for vector similarity
        query_str = f"*=>[KNN {top_k} @embedding $embedding AS distance]"

        # Add filter if provided
        # Note: Redis search query syntax for filters can be complex.
        # This is a simplified filter for exact matches on text fields.
        # Example: @field:value
        # For tag fields: @field:{tag}
        # Ensure your schema matches the filter keys and types.
        filter_parts = []
        if filter:
            for key, value in filter.items():
                # Escape special characters for Redis query syntax if necessary
                # For simplicity, assuming value is a simple string or number
                # If value contains spaces or special chars, it might need quoting or escaping
                escaped_value = (
                    str(value).replace("-", "\\-").replace(" ", "\\ ")
                )  # Basic escaping
                filter_parts.append(f"@{key}:{escaped_value}")

        if filter_parts:
            filter_query_str = " ".join(filter_parts)
            # Combine filter with KNN query
            query_str = (
                f"({filter_query_str})=>[KNN {top_k} @embedding $embedding AS distance]"
            )
        else:
            # Default query if no filter
            query_str = f"*=>[KNN {top_k} @embedding $embedding AS distance]"

        # Convert embedding to bytes
        embedding_bytes = np.array(query_embedding, dtype=np.float32).tobytes()

        # Execute the search
        from redis.commands.search.query import Query  # Ensure Query is imported

        redis_query = (
            Query(query_str)
            .return_fields(
                "id", "text", "distance", *[k for k in (filter or {}).keys()]
            )
            .sort_by("distance")
            .dialect(2)
        )

        results = self.client.ft(self.index_name).search(
            redis_query,  # Use the Query object
            {"embedding": embedding_bytes},
        )

        # Format the results
        formatted_results = []
        for result_doc in results.docs:  # Iterate through result_doc objects
            # Extract the document ID
            doc_id = result_doc.id.replace(self.prefix, "")

            # Extract the document text
            text_content = result_doc.text if hasattr(result_doc, "text") else ""

            # Extract the metadata
            metadata = {}
            # Known fields to exclude from metadata
            excluded_fields = [
                "id",
                "text",
                "embedding",
                "distance",
                "payload",
            ]  # payload is often used by redis-py
            for attr, value in result_doc.__dict__.items():
                if attr not in excluded_fields and not attr.startswith("_"):
                    metadata[attr] = value

            # Extract the distance
            distance = (
                float(result_doc.distance) if hasattr(result_doc, "distance") else 1.0
            )  # Default if not found

            formatted_results.append(
                {
                    "id": doc_id,
                    "text": text_content,
                    "metadata": metadata,
                    "distance": distance,  # Cosine distance from Redis is 1-similarity
                }
            )

        return formatted_results

    def delete(self, ids: List[str]) -> None:
        """
        Delete documents from the vector database.

        Args:
            ids: The IDs of the documents to delete.
        """
        pipeline = self.client.pipeline()
        for doc_id in ids:
            key = f"{self.prefix}{doc_id}"
            pipeline.delete(key)

        pipeline.execute()

    def get(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get documents from the vector database.

        Args:
            ids: The IDs of the documents to get.

        Returns:
            A list of dictionaries containing the documents.
        """
        formatted_results = []
        for doc_id in ids:
            key = f"{self.prefix}{doc_id}"
            result = self.client.hgetall(
                key
            )  # hgetall returns Dict[str, str] with decode_responses=True

            if result:
                # Extract the document text
                document = result.get("text", "")

                # Extract the metadata
                metadata = {
                    k: v for k, v in result.items() if k not in ["text", "embedding"]
                }

                # Extract the embedding
                embedding_bytes_str = result.get(
                    "embedding", ""
                )  # This will be a string if decode_responses=True
                embedding = []
                if embedding_bytes_str:
                    # Need to convert string back to bytes before np.frombuffer
                    embedding_bytes = embedding_bytes_str.encode(
                        "latin-1"
                    )  # Assuming it was stored as raw bytes then decoded
                    try:
                        embedding = np.frombuffer(
                            embedding_bytes, dtype=np.float32
                        ).tolist()
                    except ValueError as e:
                        logger.error(
                            f"Error decoding embedding for {doc_id}: {e}. Embedding string: {embedding_bytes_str[:50]}..."
                        )

                formatted_results.append(
                    {
                        "id": doc_id,
                        "text": document,
                        "metadata": metadata,
                        "embedding": embedding,
                    }
                )

        return formatted_results

    def update(
        self,
        ids: List[str],
        documents: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        sparse_vectors: Optional[List[Optional[Dict[int, float]]]] = None,  # Ignored
    ) -> None:
        """
        Update documents in the vector database.

        Args:
            ids: The IDs of the documents to update.
            documents: Optional new document contents.
            embeddings: Optional new embeddings.
            metadatas: Optional new metadata.
            sparse_vectors: Ignored by this implementation.
        """
        if sparse_vectors:
            logger.warning(
                "RedisDB (legacy): 'sparse_vectors' parameter was provided but will be ignored."
            )

        pipeline = self.client.pipeline()
        for i, doc_id in enumerate(ids):
            key = f"{self.prefix}{doc_id}"

            # Check if document exists, HGETALL returns empty dict if key doesn't exist
            # current = self.client.hgetall(key) # Not strictly needed if we just overwrite
            # if not current:
            #     logger.warning(f"Document with ID {doc_id} not found for update.")
            #     continue

            # Prepare the updates
            updates: Dict[str, Any] = {}

            # Update the document content if provided
            if documents and i < len(documents) and documents[i] is not None:
                updates["text"] = documents[i]

            # Update the embedding if provided
            if embeddings and i < len(embeddings) and embeddings[i] is not None:
                embedding_bytes = np.array(embeddings[i], dtype=np.float32).tobytes()
                updates["embedding"] = embedding_bytes

            # Update the metadata if provided
            if metadatas and i < len(metadatas) and metadatas[i] is not None:
                for meta_key, meta_value in metadatas[i].items():
                    updates[meta_key] = (
                        str(meta_value)
                        if not isinstance(meta_value, (bytes, str, int, float))
                        else meta_value
                    )

            # Update the hash if there are any updates
            if updates:
                pipeline.hset(key, mapping=updates)
            else:
                logger.debug(f"No updates provided for ID {doc_id}.")

        # Execute the pipeline
        pipeline.execute()

    def count(self) -> int:
        """
        Get the number of documents in the vector database.

        Returns:
            The number of documents.
        """
        # Get the index info
        info = self.client.ft(self.index_name).info()

        # Extract the number of documents
        return int(info["num_docs"])  # num_docs is usually a string from client

    def clear(self) -> None:
        """
        Clear all documents from the vector database.
        """
        # Get all keys with the prefix
        keys = self.client.keys(f"{self.prefix}*")

        # Delete all keys
        if keys:
            self.client.delete(*keys)
