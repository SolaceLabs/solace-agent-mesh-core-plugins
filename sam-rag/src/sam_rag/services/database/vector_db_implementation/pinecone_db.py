"""
Pinecone vector database implementation.
"""

import logging
import uuid
from typing import Dict, Any, List, Optional

from sam_rag.services.database.vector_db_base import VectorDBBase

logger = logging.getLogger(__name__)

class PineconeDB(VectorDBBase):
    """
    Vector database using Pinecone.
    """

    def __init__(
        self,
        config: Dict[str, Any] = None,
        hybrid_search_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the Pinecone vector database.

        Args:
            config: A dictionary containing configuration parameters.
                - api_key: The Pinecone API key (required).
                - index_name: The name of the index to use (required).
                - namespace: The namespace to use (default: "default").
                - embedding_dimension: The dimension of the embeddings (default: 768).
                - cloud: The cloud provider to use (default: "aws").
                - region: The region to use (default: "us-east-1").
            hybrid_search_config: Optional dictionary containing hybrid search configuration.
        """
        super().__init__(config=config, hybrid_search_config=hybrid_search_config)
        self.api_key = self.config.get("api_key")
        if not self.api_key:
            raise ValueError("Pinecone API key is required") from None

        self.index_name = self.config.get("index_name")
        if not self.index_name:
            raise ValueError("Pinecone index name is required") from None

        self.namespace = self.config.get("namespace", "default")
        self.embedding_dimension = self.config.get("embedding_dimension", 768)
        self.cloud = self.config.get("cloud", "aws")
        self.region = self.config.get("region", "us-east-1")

        # Hybrid search specific params for Pinecone
        self.hybrid_search_params = self.config.get("hybrid_search_params", {})
        self.hybrid_alpha = self.hybrid_search_params.get(
            "alpha", 0.5
        )  # Store alpha, though not used in client.query directly

        self.index = None
        self._setup_client()

    def _setup_client(self) -> None:
        """
        Set up the Pinecone client.
        """
        try:
            from pinecone import Pinecone, ServerlessSpec

            # Initialize Pinecone with the new API
            pc = Pinecone(api_key=self.api_key)

            # Check if the index exists
            if self.index_name not in pc.list_indexes().names():
                # Create the index
                # Determine the metric based on whether hybrid search is enabled
                metric_type = "dotproduct" if self.hybrid_search_enabled else "cosine"
                if self.hybrid_search_enabled:
                    logger.info(
                        f"PineconeDB: Hybrid search enabled. Creating index '{self.index_name}' with metric '{metric_type}'."
                    )
                else:
                    logger.info(
                        f"PineconeDB: Creating index '{self.index_name}' with metric '{metric_type}'."
                    )

                pc.create_index(
                    name=self.index_name,
                    dimension=self.embedding_dimension,
                    metric=metric_type,  # Use dotproduct for hybrid, cosine otherwise
                    spec=ServerlessSpec(cloud=self.cloud, region=self.region),
                    # For serverless, explicit sparse_values config at creation might not be needed.
                    # Pinecone infers from data or it's a general capability of the index type.
                    # If a specific 'sparse_values=True' or similar param is available for create_index
                    # in the used client version, it could be added here.
                )

            # Connect to the index
            self.index = pc.Index(self.index_name)
        except ImportError:
            raise ImportError(
                "The pinecone-client package is required for PineconeDB. "
                "Please install it with `pip install pinecone-client`."
            ) from None

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],  # Dense embeddings
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        sparse_vectors: Optional[List[Optional[Dict[int, float]]]] = None,
    ) -> List[str]:
        """
        Add documents to the vector database.

        Args:
            documents: The documents to add.
            embeddings: The dense embeddings of the documents.
            metadatas: Optional metadata for each document.
            ids: Optional IDs for each document.
            sparse_vectors: Optional sparse vector representations for each document.

        Returns:
            The IDs of the added documents.
        """
        if not documents or not embeddings:
            return []

        # Generate IDs if not provided
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(len(documents))]

        # Create default metadata if not provided
        if metadatas is None:
            metadatas = [{"source": "unknown"} for _ in range(len(documents))]

        if sparse_vectors is None:
            sparse_vectors = [None] * len(documents)

        if len(documents) != len(sparse_vectors):
            logger.warning(
                f"PineconeDB: Mismatch between number of documents ({len(documents)}) and sparse_vectors ({len(sparse_vectors)}). Adjusting sparse_vectors."
            )
            adjusted_sparse_vectors = [None] * len(documents)
            for i in range(min(len(documents), len(sparse_vectors))):
                adjusted_sparse_vectors[i] = sparse_vectors[i]
            sparse_vectors = adjusted_sparse_vectors

        vectors_to_upsert = []
        for i in range(len(documents)):
            current_metadata = (
                metadatas[i].copy() if metadatas and i < len(metadatas) else {}
            )
            current_metadata["text"] = documents[i]

            vector_data: Dict[str, Any] = {
                "id": ids[i],
                "values": embeddings[i],
                "metadata": current_metadata,
            }

            if (
                self.hybrid_search_enabled
                and sparse_vectors
                and i < len(sparse_vectors)
                and sparse_vectors[i] is not None
            ):
                current_sparse = sparse_vectors[i]
                if current_sparse:  # Ensure it's not None and not empty
                    vector_data["sparse_values"] = {
                        "indices": list(current_sparse.keys()),
                        "values": list(current_sparse.values()),
                    }

            vectors_to_upsert.append(vector_data)

        # Upsert the vectors in batches
        batch_size = 100  # Pinecone's recommended batch size
        for i in range(0, len(vectors_to_upsert), batch_size):
            batch = vectors_to_upsert[i : i + batch_size]
            self.index.upsert(vectors=batch, namespace=self.namespace)
            logger.debug(
                f"PineconeDB: Upserted batch of {len(batch)} vectors to namespace '{self.namespace}'."
            )

        return ids

    def search(
        self,
        query_embedding: List[float],  # Dense query vector
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
        query_sparse_vector: Optional[Dict[int, float]] = None,
        request_hybrid: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query embedding, optionally using hybrid search.

        Args:
            query_embedding: The dense query embedding.
            top_k: The number of results to return.
            filter: Optional filter to apply to the search.
            query_sparse_vector: Optional sparse vector for the query.
            request_hybrid: Flag to request hybrid search if available and enabled.

        Returns:
            A list of dictionaries containing the search results.
        """
        query_params = {
            "vector": query_embedding,
            "top_k": top_k,
            "include_metadata": True,
            "namespace": self.namespace,
            "filter": filter,
        }

        if request_hybrid and self.hybrid_search_enabled and query_sparse_vector:
            logger.info(
                f"PineconeDB: Performing hybrid search with sparse vector in namespace '{self.namespace}'."
            )
            query_params["sparse_vector"] = {
                "indices": list(query_sparse_vector.keys()),
                "values": list(query_sparse_vector.values()),
            }
            # Pinecone's server-side hybrid search typically uses an alpha defined at the index level
            # or automatically balances. The `alpha` in client.query is for multiple dense vectors.
            # If a specific alpha is needed for query-time weighting between the dense `vector` and `sparse_vector`
            # for this type of query, the Pinecone documentation for the specific client version should be consulted.
            # For now, we assume providing both is sufficient for the server to perform hybrid search.
        else:
            logger.info(
                f"PineconeDB: Performing dense-only search in namespace '{self.namespace}'."
            )

        results = self.index.query(**query_params)

        # Format the results
        formatted_results = []
        for match in results.matches:
            formatted_results.append(
                {
                    "id": match.id,
                    "text": match.metadata.get("text", ""),
                    "metadata": {
                        k: v for k, v in match.metadata.items() if k != "text"
                    },
                    "distance": match.score,
                }
            )

        return formatted_results

    def delete(self, ids: List[str]) -> None:
        """
        Delete documents from the vector database.

        Args:
            ids: The IDs of the documents to delete.
        """
        self.index.delete(ids=ids, namespace=self.namespace)

    def get(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get documents from the vector database.

        Args:
            ids: The IDs of the documents to get.

        Returns:
            A list of dictionaries containing the documents.
        """
        # Fetch the vectors
        results = self.index.fetch(ids=ids, namespace=self.namespace)

        # Format the results
        formatted_results = []
        for id, vector in results.vectors.items():
            formatted_results.append(
                {
                    "id": id,
                    "text": vector.metadata.get("text", ""),
                    "metadata": {
                        k: v for k, v in vector.metadata.items() if k != "text"
                    },
                    "embedding": vector.values,
                }
            )

        return formatted_results

    def update(
        self,
        ids: List[str],
        documents: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        sparse_vectors: Optional[List[Optional[Dict[int, float]]]] = None,
    ) -> None:
        """
        Update documents in the vector database.

        Args:
            ids: The IDs of the documents to update.
            documents: Optional new document contents.
            embeddings: Optional new embeddings.
            metadatas: Optional new metadata.
            sparse_vectors: Optional sparse vector representations for each document.
        """
        # Get the current documents
        current_docs = self.get(ids)

        # If sparse_vectors is not provided, initialize with None for each ID
        if sparse_vectors is None:
            sparse_vectors = [None] * len(ids)

        # Ensure sparse_vectors list matches length of ids
        if len(ids) != len(sparse_vectors):
            logger.warning(
                f"PineconeDB: Mismatch between number of IDs ({len(ids)}) and sparse_vectors ({len(sparse_vectors)}). Adjusting sparse_vectors."
            )
            adjusted_sparse_vectors = [None] * len(ids)
            for i in range(min(len(ids), len(sparse_vectors))):
                adjusted_sparse_vectors[i] = sparse_vectors[i]
            sparse_vectors = adjusted_sparse_vectors

        # Prepare the vectors to upsert
        vectors_to_upsert = []
        for i, doc_id in enumerate(ids):
            if i < len(current_docs):
                current_doc = current_docs[i]

                # Update the document content if provided
                doc_content = (
                    documents[i]
                    if documents and i < len(documents)
                    else current_doc["text"]
                )

                # Update the embedding if provided
                embedding = (
                    embeddings[i]
                    if embeddings and i < len(embeddings)
                    else current_doc["embedding"]
                )

                # Update the metadata if provided
                metadata = current_doc["metadata"].copy()
                if metadatas and i < len(metadatas):
                    metadata.update(metadatas[i])

                # Add document text to metadata
                metadata["text"] = doc_content

                # Create vector data structure
                vector_data = {
                    "id": doc_id,
                    "values": embedding,
                    "metadata": metadata,
                }

                # Add sparse vector if provided and hybrid search is enabled
                if (
                    self.hybrid_search_enabled
                    and sparse_vectors
                    and i < len(sparse_vectors)
                    and sparse_vectors[i] is not None
                ):
                    current_sparse = sparse_vectors[i]
                    if current_sparse:  # Ensure it's not None and not empty
                        vector_data["sparse_values"] = {
                            "indices": list(current_sparse.keys()),
                            "values": list(current_sparse.values()),
                        }

                vectors_to_upsert.append(vector_data)

        # Upsert the vectors in batches
        batch_size = 100
        for i in range(0, len(vectors_to_upsert), batch_size):
            batch = vectors_to_upsert[i : i + batch_size]
            self.index.upsert(vectors=batch, namespace=self.namespace)

    def count(self) -> int:
        """
        Get the number of documents in the vector database.

        Returns:
            The number of documents.
        """
        stats = self.index.describe_index_stats()
        return stats.namespaces.get(self.namespace, {}).get("vector_count", 0)

    def clear(self) -> None:
        """
        Clear all documents from the vector database.
        """
        self.index.delete(delete_all=True, namespace=self.namespace)
