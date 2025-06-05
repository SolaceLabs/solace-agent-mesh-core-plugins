"""
Additional vector database implementations.

This module contains implementations for various vector databases:
- Pinecone
- Weaviate
- Qdrant
- Redis
- Elasticsearch
- pgvector (PostgreSQL)
- Vespa
- Vald
- Zilliz
"""

import os
import uuid
import json
import numpy as np
from typing import Dict, Any, List, Optional
from solace_ai_connector.common.log import log as logger

from .vector_db_base import VectorDBBase


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
                    else current_doc["text"]  # Fixed: was "document"
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


class QdrantDB(VectorDBBase):
    """
    Vector database using Qdrant.
    """

    def __init__(
        self,
        config: Dict[str, Any] = None,
        hybrid_search_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the Qdrant vector database.

        Args:
            config: A dictionary containing configuration parameters.
                - url: The Qdrant URL (default: "http://localhost:6333").
                - api_key: The Qdrant API key (optional).
                - collection_name: The name of the collection to use (default: "documents").
                - embedding_dimension: The dimension of the embeddings (default: 768).
            hybrid_search_config: Optional dictionary containing hybrid search configuration.
        """
        super().__init__(config=config, hybrid_search_config=hybrid_search_config)
        self.url = self.config.get("url", "http://localhost:6333")
        self.api_key = self.config.get("api_key")
        self.collection_name = self.config.get("collection_name", "documents")
        self.embedding_dimension = self.config.get(
            "embedding_dimension", 768
        )  # For the default dense vector

        # Hybrid search specific params for Qdrant
        self.hybrid_search_params = self.config.get("hybrid_search_params", {})
        self.sparse_vector_name = self.hybrid_search_params.get(
            "sparse_vector_name",
            "sparse_db",  # Default sparse vector name to match config
        )

        self.client = None
        self._setup_client()

    def _setup_client(self) -> None:
        """
        Set up the Qdrant client.
        """
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models

            # Create the client
            self.client = QdrantClient(url=self.url, api_key=self.api_key)

            # Check if the collection exists
            collections = self.client.get_collections().collections
            logger.info(
                f"Existing collections: {[collection.name for collection in collections]}"
            )
            collection_names = [collection.name for collection in collections]

            if self.collection_name not in collection_names:
                logger.info(
                    f"Collection '{self.collection_name}' not found. Creating..."
                )
                # Define base vector parameters for the default dense vector
                dense_vector_config = models.VectorParams(
                    size=self.embedding_dimension,
                    distance=models.Distance.COSINE,
                )

                if self.hybrid_search_enabled:
                    logger.info(
                        f"Hybrid search enabled. Configuring collection with dense and sparse ('{self.sparse_vector_name}') vectors."
                    )
                    sparse_vector_config = models.SparseVectorParams(
                        index=models.SparseIndexParams(
                            on_disk=False  # Recommended for mutable sparse vectors
                        )
                    )
                    self.client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config={
                            "": dense_vector_config
                        },  # Dense vector must be in a dict by name
                        sparse_vectors_config={
                            self.sparse_vector_name: sparse_vector_config
                        },
                    )
                    logger.info(
                        f"Collection '{self.collection_name}' created successfully with dense and sparse vector configurations."
                    )
                else:
                    logger.info(
                        f"Hybrid search disabled. Configuring collection with only dense vectors."
                    )
                    self.client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=dense_vector_config,  # Single dense vector config
                    )
                    logger.info(
                        f"Collection '{self.collection_name}' created successfully with dense vector configuration."
                    )
            else:
                logger.info(f"Collection '{self.collection_name}' already exists.")
                # TODO: Potentially update existing collection if hybrid search settings changed
                # For now, we assume the collection is compatible or re-created if not.
        except ImportError:
            raise ImportError(
                "The qdrant-client package is required for QdrantDB. "
                "Please install it with `pip install qdrant-client`."
            ) from None

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],  # These are dense embeddings
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

        if (
            sparse_vectors is None
        ):  # Ensure sparse_vectors list matches length if not provided
            sparse_vectors = [None] * len(documents)

        if len(documents) != len(sparse_vectors):
            logger.warning(
                f"Mismatch between number of documents ({len(documents)}) and sparse_vectors ({len(sparse_vectors)}). Sparse vectors will not be added for missing entries."
            )
            # Adjust sparse_vectors to match documents length, filling with None
            adjusted_sparse_vectors = [None] * len(documents)
            for i in range(min(len(documents), len(sparse_vectors))):
                adjusted_sparse_vectors[i] = sparse_vectors[i]
            sparse_vectors = adjusted_sparse_vectors

        from qdrant_client.http import models

        # Prepare the points to upsert
        points = []
        logger.debug(
            f"QdrantDB: Preparing to upsert {len(documents)} points to collection '{self.collection_name}'."
        )
        for i in range(len(documents)):
            # Prepare the payload
            payload = {"text": documents[i]}

            # Add metadata to payload
            if metadatas and i < len(metadatas):
                for key, value in metadatas[i].items():
                    payload[key] = value

            current_vector_data: Dict[str, Any] = {
                "": embeddings[i]  # Use empty string for default/unnamed dense vector
            }

            if (
                self.hybrid_search_enabled
                and sparse_vectors
                and i < len(sparse_vectors)
                and sparse_vectors[i] is not None
            ):
                current_sparse_vector = sparse_vectors[i]
                if current_sparse_vector:  # Ensure it's not None and not empty
                    current_vector_data[self.sparse_vector_name] = models.SparseVector(
                        indices=list(current_sparse_vector.keys()),
                        values=list(current_sparse_vector.values()),
                    )

            points.append(
                models.PointStruct(
                    id=ids[i],
                    vector=current_vector_data
                    if self.hybrid_search_enabled
                    else embeddings[i],
                    payload=payload,
                )
            )

        print(
            f"QdrantDB: Upserting {len(points)} points to collection '{self.collection_name}'."
        )

        logger.debug(f"QdrantDB: upserting {len(points)} points'.")

        # Upsert the points
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,  # Ensure operation is completed
        )

        return ids

    def search(
        self,
        query_embedding: List[float],  # This is the dense query vector
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
        from qdrant_client.http import models

        # Prepare the filter
        qdrant_filter = None
        if filter:
            conditions = []
            for key, value in filter.items():
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value),
                    )
                )
            qdrant_filter = models.Filter(must=conditions)

        query_input: Any  # Can be List[float] or List[models.Query]

        print("request_hybrid:", request_hybrid)
        print("hybrid_search_enabled:", self.hybrid_search_enabled)
        print(
            "query_sparse_vector:",
            query_sparse_vector is not None and len(query_sparse_vector) > 0,
        )
        if request_hybrid and self.hybrid_search_enabled and query_sparse_vector:
            logger.info(
                f"Performing hybrid search with sparse vector on Qdrant collection '{self.collection_name}'."
            )
            # Construct a list of query objects for hybrid search
            query_input = [
                models.NamedVectorQuery(
                    name="",
                    vector=query_embedding,  # Use empty string for default/unnamed dense vector
                ),
                models.NamedSparseVectorQuery(
                    name=self.sparse_vector_name,
                    vector=models.SparseVector(
                        indices=list(query_sparse_vector.keys()),
                        values=list(query_sparse_vector.values()),
                    ),
                ),
            ]
            logger.debug(f"Hybrid search query input: {query_input}")
        else:
            logger.info(
                f"Performing dense-only search on Qdrant collection '{self.collection_name}'."
            )
            # For dense-only, query_input is just the dense vector
            # The client.query_points API can accept a single vector directly for the default dense vector
            query_input = query_embedding

        # Use query_points API
        search_results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_input,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
            with_vectors=False,
        )

        # Format the results
        formatted_results = []
        for scored_point in search_results.points:
            text = scored_point.payload.get("text", "") if scored_point.payload else ""
            metadata = (
                {k: v for k, v in scored_point.payload.items() if k != "text"}
                if scored_point.payload
                else {}
            )

            score = scored_point.score

            formatted_results.append(
                {
                    "id": scored_point.id,
                    "text": text,
                    "metadata": metadata,
                    "score": score,
                    "version": scored_point.version,
                }
            )
        return formatted_results

    def delete(self, ids: List[str]) -> None:
        """
        Delete documents from the vector database.

        Args:
            ids: The IDs of the documents to delete.
        """
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=ids,
        )

    def get(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get documents from the vector database.

        Args:
            ids: The IDs of the documents to get.

        Returns:
            A list of dictionaries containing the documents.
        """
        # Get the points
        results = self.client.retrieve(
            collection_name=self.collection_name,
            ids=ids,
            with_vectors=True,
        )

        # Format the results
        formatted_results = []
        for result in results:
            # Extract the document text
            document = result.payload.get("text", "")

            # Extract the metadata
            metadata = {k: v for k, v in result.payload.items() if k != "text"}

            formatted_results.append(
                {
                    "id": result.id,
                    "text": document,
                    "metadata": metadata,
                    "embedding": result.vector,
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
        from qdrant_client.http import models

        # If sparse_vectors is not provided, initialize with None for each ID
        if sparse_vectors is None:
            sparse_vectors = [None] * len(ids)

        # Ensure sparse_vectors list matches length of ids
        if len(ids) != len(sparse_vectors):
            logger.warning(
                f"Mismatch between number of IDs ({len(ids)}) and sparse_vectors ({len(sparse_vectors)}). Adjusting sparse_vectors."
            )
            adjusted_sparse_vectors = [None] * len(ids)
            for i in range(min(len(ids), len(sparse_vectors))):
                adjusted_sparse_vectors[i] = sparse_vectors[i]
            sparse_vectors = adjusted_sparse_vectors

        for i, doc_id in enumerate(ids):
            # Update the payload if needed
            if (documents and i < len(documents)) or (metadatas and i < len(metadatas)):
                # Get the current document
                current_docs = self.get([doc_id])
                if not current_docs:
                    continue

                current_doc = current_docs[0]

                # Prepare the payload
                payload = {}

                # Update the document content if provided
                if documents and i < len(documents):
                    payload["text"] = documents[i]
                else:
                    payload["text"] = current_doc["text"]  # Fixed: was "document"

                # Update the metadata if provided
                current_metadata = current_doc["metadata"]
                if metadatas and i < len(metadatas):
                    current_metadata.update(metadatas[i])

                # Add metadata to payload
                for key, value in current_metadata.items():
                    payload[key] = value

                # Update the payload
                self.client.set_payload(
                    collection_name=self.collection_name,
                    payload=payload,
                    points=[doc_id],
                )

            # Update the vectors if provided
            if (embeddings and i < len(embeddings)) or (
                sparse_vectors
                and i < len(sparse_vectors)
                and sparse_vectors[i] is not None
            ):
                # Handle dense vector update
                if embeddings and i < len(embeddings):
                    if self.hybrid_search_enabled:
                        # For hybrid search, we need to use named vectors
                        vector_data = {"": embeddings[i]}  # Default dense vector

                        # Add sparse vector if provided
                        if (
                            sparse_vectors
                            and i < len(sparse_vectors)
                            and sparse_vectors[i]
                        ):
                            current_sparse = sparse_vectors[i]
                            vector_data[self.sparse_vector_name] = models.SparseVector(
                                indices=list(current_sparse.keys()),
                                values=list(current_sparse.values()),
                            )

                        # Update with named vectors
                        self.client.update_vectors(
                            collection_name=self.collection_name,
                            points=[
                                models.PointVectors(
                                    id=doc_id,
                                    vector=vector_data,
                                )
                            ],
                        )
                    else:
                        # For dense-only search, use simple vector update
                        self.client.update_vectors(
                            collection_name=self.collection_name,
                            points=[
                                models.PointVectors(
                                    id=doc_id,
                                    vector=embeddings[i],
                                )
                            ],
                        )
                # Handle sparse-only vector update when dense is not provided
                elif (
                    self.hybrid_search_enabled
                    and sparse_vectors
                    and i < len(sparse_vectors)
                    and sparse_vectors[i]
                ):
                    # Get current dense vector first
                    current_docs = self.get([doc_id])
                    if not current_docs or "embedding" not in current_docs[0]:
                        logger.warning(
                            f"Cannot update sparse vector for ID {doc_id} without existing dense vector"
                        )
                        continue

                    # Create vector data with existing dense and new sparse
                    current_dense = current_docs[0]["embedding"]
                    current_sparse = sparse_vectors[i]

                    vector_data = {"": current_dense}  # Default dense vector
                    vector_data[self.sparse_vector_name] = models.SparseVector(
                        indices=list(current_sparse.keys()),
                        values=list(current_sparse.values()),
                    )

                    # Update with named vectors
                    self.client.update_vectors(
                        collection_name=self.collection_name,
                        points=[
                            models.PointVectors(
                                id=doc_id,
                                vector=vector_data,
                            )
                        ],
                    )

    def count(self) -> int:
        """
        Get the number of documents in the vector database.

        Returns:
            The number of documents.
        """
        collection_info = self.client.get_collection(self.collection_name)
        return collection_info.vectors_count

    def clear(self) -> None:
        """
        Clear all documents from the vector database.
        """
        self.client.delete_collection(self.collection_name)
        self._setup_client()


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
        """
        super().__init__(config=config, hybrid_search_config=hybrid_search_config)
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
                    TextField("source"),
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
    ) -> List[str]:
        """
        Add documents to the vector database.

        Args:
            documents: The documents to add.
            embeddings: The embeddings of the documents.
            metadatas: Optional metadata for each document.
            ids: Optional IDs for each document.

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

        import numpy as np

        # Add the documents
        pipeline = self.client.pipeline()
        for i in range(len(documents)):
            # Convert embedding to bytes
            embedding_bytes = np.array(embeddings[i], dtype=np.float32).tobytes()

            # Prepare the hash fields
            hash_fields = {
                "text": documents[i],
                "embedding": embedding_bytes,
            }

            # Add metadata fields
            for key, value in metadatas[i].items():
                hash_fields[key] = value

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
    ) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query embedding.

        Args:
            query_embedding: The query embedding.
            top_k: The number of results to return.
            filter: Optional filter to apply to the search.

        Returns:
            A list of dictionaries containing the search results.
        """
        import numpy as np

        # Prepare the query
        query = f"*=>[KNN {top_k} @embedding $embedding AS distance]"

        # Add filter if provided
        if filter:
            filter_conditions = []
            for key, value in filter.items():
                filter_conditions.append(f"@{key}:{{{value}}}")

            if filter_conditions:
                filter_str = " ".join(filter_conditions)
                query = f"{filter_str}=>[KNN {top_k} @embedding $embedding AS distance]"

        # Convert embedding to bytes
        embedding_bytes = np.array(query_embedding, dtype=np.float32).tobytes()

        # Execute the search
        results = self.client.ft(self.index_name).search(
            query,
            {"embedding": embedding_bytes},
        )

        # Format the results
        formatted_results = []
        for result in results.docs:
            # Extract the document ID
            doc_id = result.id.replace(self.prefix, "")

            # Extract the document text
            document = result.text

            # Extract the metadata
            metadata = {
                k: v
                for k, v in result.__dict__.items()
                if k not in ["id", "text", "embedding", "distance"]
            }

            # Extract the distance
            distance = float(result.distance)

            formatted_results.append(
                {
                    "id": doc_id,
                    "text": document,
                    "metadata": metadata,
                    "distance": distance,
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
        import numpy as np

        formatted_results = []
        for doc_id in ids:
            key = f"{self.prefix}{doc_id}"
            result = self.client.hgetall(key)

            if result:
                # Extract the document text
                document = result.get("text", "")

                # Extract the metadata
                metadata = {
                    k: v for k, v in result.items() if k not in ["text", "embedding"]
                }

                # Extract the embedding
                embedding_bytes = result.get("embedding", b"")
                embedding = (
                    np.frombuffer(embedding_bytes, dtype=np.float32).tolist()
                    if embedding_bytes
                    else []
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
        # Redis doesn't directly support sparse vectors, so we ignore the sparse_vectors parameter
        if sparse_vectors:
            logger.warning(
                "RedisDB: 'sparse_vectors' parameter was provided but will be ignored as RedisDB currently only supports dense vectors through this interface."
            )

        import numpy as np

        pipeline = self.client.pipeline()
        for i, doc_id in enumerate(ids):
            key = f"{self.prefix}{doc_id}"

            # Get the current document
            current = self.client.hgetall(key)
            if not current:
                continue

            # Prepare the updates
            updates = {}

            # Update the document content if provided
            if documents and i < len(documents):
                updates["text"] = documents[i]

            # Update the embedding if provided
            if embeddings and i < len(embeddings):
                embedding_bytes = np.array(embeddings[i], dtype=np.float32).tobytes()
                updates["embedding"] = embedding_bytes

            # Update the metadata if provided
            if metadatas and i < len(metadatas):
                for key, value in metadatas[i].items():
                    updates[key] = value

            # Update the hash
            if updates:
                pipeline.hset(key, mapping=updates)

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
        return info["num_docs"]

    def clear(self) -> None:
        """
        Clear all documents from the vector database.
        """
        # Get all keys with the prefix
        keys = self.client.keys(f"{self.prefix}*")

        # Delete all keys
        if keys:
            self.client.delete(*keys)


class PgVectorDB(VectorDBBase):
    """
    Vector database using PostgreSQL with pgvector extension.
    """

    def __init__(
        self,
        config: Dict[str, Any] = None,
        hybrid_search_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the PostgreSQL vector database.

        Args:
            config: A dictionary containing configuration parameters.
                - connection_string: The PostgreSQL connection string (required).
                - table_name: The name of the table to use (default: "documents").
                - embedding_dimension: The dimension of the embeddings (default: 768).
            hybrid_search_config: Optional dictionary containing hybrid search configuration.
        """
        super().__init__(config=config, hybrid_search_config=hybrid_search_config)

        self.host = self.config.get("host", "localhost")
        self.port = self.config.get("port", 5432)
        self.database = self.config.get("database", "vectordb")
        self.user = self.config.get("user", "postgres")
        self.password = self.config.get("password")

        self.table_name = self.config.get("table_name", "documents")
        self.embedding_dimension = self.config.get("embedding_dimension", 768)
        self.conn = None
        self._setup_client()

    def _setup_client(self) -> None:
        """
        Set up the PostgreSQL client.
        """
        try:
            import psycopg2

            # First connect to the default postgres database to check if our database exists
            default_conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database="postgres",  # Connect to default database first
                user=self.user,
                password=self.password,
            )
            default_conn.autocommit = True  # Set autocommit mode for database creation

            with default_conn.cursor() as cursor:
                # Check if the database exists
                cursor.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s", (self.database,)
                )
                database_exists = cursor.fetchone() is not None

                # Create the database if it doesn't exist
                if not database_exists:
                    cursor.execute(f"CREATE DATABASE {self.database}")
                    logger.info("Created database.")

            # Close the connection to the default database
            default_conn.close()

            # Now connect to the target database
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
            )

            # Create the pgvector extension if it doesn't exist
            with self.conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                # Create the table if it doesn't exist
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        id TEXT PRIMARY KEY,
                        text TEXT NOT NULL,
                        embedding vector({self.embedding_dimension}) NOT NULL,
                        metadata JSONB
                    );
                """
                )

                # Create an index for vector similarity search
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.table_name}_embedding_idx
                    ON {self.table_name}
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100);
                """
                )

                self.conn.commit()
        except ImportError:
            raise ImportError(
                "The psycopg2 package is required for PgVectorDB. "
                "Please install it with `pip install psycopg2-binary`."
            )
        except ConnectionError:
            raise ConnectionError("Failed to connect to PostgreSQL database") from None
        except Exception:
            raise ValueError(
                "An error occurred while setting up the PostgreSQL client"
            ) from None

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        sparse_vectors: Optional[
            List[Optional[Dict[int, float]]]
        ] = None,  # Added to match base
    ) -> List[str]:
        """
        Add documents to the vector database. PgVectorDB only supports dense vectors.

        Args:
            documents: The documents to add.
            embeddings: The embeddings of the documents.
            metadatas: Optional metadata for each document.
            ids: Optional IDs for each document.

        Returns:
            The IDs of the added documents.
        """
        if sparse_vectors:
            logger.warning(
                "PgVectorDB: 'sparse_vectors' parameter was provided but will be ignored as PgVectorDB currently only supports dense vectors through this interface."
            )

        if not documents or not embeddings:
            return []

        # Generate IDs if not provided
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(len(documents))]

        # Create default metadata if not provided
        if metadatas is None:
            metadatas = [{"source": "unknown"} for _ in range(len(documents))]

        import json

        # Add the documents
        with self.conn.cursor() as cursor:
            for i in range(len(documents)):
                # Convert metadata to JSON
                metadata_json = json.dumps(metadatas[i])

                # Insert the document
                cursor.execute(
                    f"""
                    INSERT INTO {self.table_name} (id, text, embedding, metadata)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET text = EXCLUDED.text,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata;
                    """,
                    (ids[i], documents[i], embeddings[i], metadata_json),
                )

            self.conn.commit()

        return ids

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
        query_sparse_vector: Optional[Dict[int, float]] = None,  # Added to match base
        request_hybrid: bool = False,  # Added to match base
    ) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query embedding. PgVectorDB only supports dense search.

        Args:
            query_embedding: The query embedding.
            top_k: The number of results to return.
            filter: Optional filter to apply to the search.

        Returns:
            A list of dictionaries containing the search results.
        """
        if request_hybrid or query_sparse_vector:
            logger.warning(
                "PgVectorDB: 'request_hybrid' was true or 'query_sparse_vector' was provided, "
                "but PgVectorDB currently only supports dense search through this interface. Proceeding with dense search."
            )

        # Prepare the query
        query = f"""
            SELECT id, text, metadata, 1 - (embedding <=> %s::vector({self.embedding_dimension})) as similarity
            FROM {self.table_name}
        """

        # Add filter if provided
        params = [query_embedding]
        if filter:
            filter_conditions = []
            for key, value in filter.items():
                filter_conditions.append(f"metadata->>'%s' = %s")
                params.extend([key, value])

            if filter_conditions:
                filter_str = " AND ".join(filter_conditions)
                query += f" WHERE {filter_str}"

        # Add order by and limit
        query += f" ORDER BY similarity DESC LIMIT {top_k}"

        # Execute the search
        with self.conn.cursor() as cursor:
            cursor.execute(query, params)
            results = cursor.fetchall()

        # Format the results
        formatted_results = []
        for result in results:
            doc_id, text, metadata, similarity = result

            # Parse the metadata if it's a string, otherwise use as is
            if isinstance(metadata, str):
                metadata = json.loads(metadata) if metadata else {}
            else:
                # Ensure metadata is a dictionary
                metadata = metadata if metadata else {}

            formatted_results.append(
                {
                    "id": doc_id,
                    "text": text,
                    "metadata": metadata,
                    "distance": 1 - similarity,
                }
            )

        return formatted_results

    def delete(self, ids: List[str]) -> None:
        """
        Delete documents from the vector database.

        Args:
            ids: The IDs of the documents to delete.
        """
        # Delete the documents
        with self.conn.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {self.table_name} WHERE id = ANY(%s)",
                (ids,),
            )

            self.conn.commit()

    def get(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get documents from the vector database.

        Args:
            ids: The IDs of the documents to get.

        Returns:
            A list of dictionaries containing the documents.
        """
        # Get the documents
        with self.conn.cursor() as cursor:
            cursor.execute(
                f"SELECT id, text, embedding, metadata FROM {self.table_name} WHERE id = ANY(%s)",
                (ids,),
            )
            results = cursor.fetchall()

        # Format the results
        formatted_results = []
        for result in results:
            doc_id, text, embedding, metadata_json = result

            # Parse the metadata
            metadata = json.loads(metadata_json) if metadata_json else {}

            formatted_results.append(
                {
                    "id": doc_id,
                    "text": text,
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
        # PgVectorDB doesn't support sparse vectors, so we ignore the sparse_vectors parameter
        if sparse_vectors:
            logger.warning(
                "PgVectorDB: 'sparse_vectors' parameter was provided but will be ignored as PgVectorDB currently only supports dense vectors through this interface."
            )

        # Get the current documents
        current_docs = self.get(ids)

        # Update the documents
        with self.conn.cursor() as cursor:
            for i, doc_id in enumerate(ids):
                if i < len(current_docs):
                    current_doc = current_docs[i]

                    # Update the document content if provided
                    text = (
                        documents[i]
                        if documents and i < len(documents)
                        else current_doc["text"]  # Fixed: was "document"
                    )

                    # Update the embedding if provided
                    embedding = (
                        embeddings[i]
                        if embeddings and i < len(embeddings)
                        else current_doc["embedding"]
                    )

                    # Update the metadata if provided
                    metadata = current_doc["metadata"]
                    if metadatas and i < len(metadatas):
                        metadata.update(metadatas[i])

                    # Convert metadata to JSON
                    metadata_json = json.dumps(metadata)

                    # Update the document
                    cursor.execute(
                        f"""
                        UPDATE {self.table_name}
                        SET text = %s, embedding = %s, metadata = %s
                        WHERE id = %s
                        """,
                        (text, embedding, metadata_json, doc_id),
                    )

            self.conn.commit()

    def count(self) -> int:
        """
        Get the number of documents in the vector database.

        Returns:
            The number of documents.
        """
        # Count the documents
        with self.conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            result = cursor.fetchone()

        return result[0] if result else 0

    def clear(self) -> None:
        """
        Clear all documents from the vector database.
        """
        # Delete all documents
        with self.conn.cursor() as cursor:
            cursor.execute(f"DELETE FROM {self.table_name}")
            self.conn.commit()


class ChromaDB(VectorDBBase):
    """
    Vector database using ChromaDB.
    """

    def __init__(
        self,
        config: Dict[str, Any] = None,
        hybrid_search_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the ChromaDB vector database.

        Args:
            config: A dictionary containing configuration parameters.
                - persist_directory: The directory to persist the database to (default: "./chroma_db").
                - collection_name: The name of the collection to use (default: "documents").
                - embedding_dimension: The dimension of the embeddings (default: 768).
            hybrid_search_config: Optional dictionary containing hybrid search configuration.
        """
        super().__init__(config=config, hybrid_search_config=hybrid_search_config)
        self.persist_directory = self.config.get("persist_directory", "./chroma_db")
        self.collection_name = self.config.get("collection_name", "documents")
        self.embedding_dimension = self.config.get("embedding_dimension", 768)
        self.client = None
        self.collection = None
        self._setup_client()

    def _setup_client(self) -> None:
        """
        Set up the ChromaDB client.
        """
        try:
            import chromadb
            from chromadb.config import Settings

            # Create the client
            self.client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(anonymized_telemetry=False),
            )

            # Get or create the collection
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={
                    "hnsw:space": "cosine",
                    "embedding_dimension": self.embedding_dimension,  # Custom metadata
                },
                embedding_function=None,  # We provide our own embeddings
            )
        except ImportError:
            raise ImportError(
                "The chromadb package is required for ChromaDB. "
                "Please install it with `pip install chromadb`."
            ) from None

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        sparse_vectors: Optional[
            List[Optional[Dict[int, float]]]
        ] = None,  # Added to match base
    ) -> List[str]:
        """
        Add documents to the vector database. ChromaDB only supports dense vectors through this interface.

        Args:
            documents: The documents to add.
            embeddings: The embeddings of the documents.
            metadatas: Optional metadata for each document.
            ids: Optional IDs for each document.

        Returns:
            The IDs of the added documents.
        """
        if sparse_vectors:
            logger.warning(
                "ChromaDB: 'sparse_vectors' parameter was provided but will be ignored as ChromaDB currently only supports dense vectors through this interface."
            )

        if not documents or not embeddings:
            return []

        # Generate IDs if not provided
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(len(documents))]

        # Create default metadata if not provided
        if metadatas is None:
            metadatas = [{"source": "unknown"} for _ in range(len(documents))]

        # Add the documents to the collection
        self.collection.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )

        return ids

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
        query_sparse_vector: Optional[Dict[int, float]] = None,  # Added to match base
        request_hybrid: bool = False,  # Added to match base
    ) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query embedding. ChromaDB only supports dense search.

        Args:
            query_embedding: The query embedding.
            top_k: The number of results to return.
            filter: Optional filter to apply to the search.

        Returns:
            A list of dictionaries containing the search results.
        """
        if request_hybrid or query_sparse_vector:
            logger.warning(
                "ChromaDB: 'request_hybrid' was true or 'query_sparse_vector' was provided, "
                "but ChromaDB currently only supports dense search through this interface. Proceeding with dense search."
            )

        # Search the collection
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter,
        )

        # Format the results
        formatted_results = []
        for i in range(len(results["ids"][0])):
            formatted_results.append(
                {
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                }
            )

        return formatted_results

    def delete(self, ids: List[str]) -> None:
        """
        Delete documents from the vector database.

        Args:
            ids: The IDs of the documents to delete.
        """
        self.collection.delete(ids=ids)

    def get(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get documents from the vector database.

        Args:
            ids: The IDs of the documents to get.

        Returns:
            A list of dictionaries containing the documents.
        """
        # Get the documents
        results = self.collection.get(ids=ids)

        # Format the results
        formatted_results = []
        for i in range(len(results["ids"])):
            formatted_results.append(
                {
                    "id": results["ids"][i],
                    "text": results["documents"][i],
                    "metadata": results["metadatas"][i],
                    "embedding": results["embeddings"][i],
                }
            )

        return formatted_results

    def update(
        self,
        ids: List[str],
        documents: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Update documents in the vector database.

        Args:
            ids: The IDs of the documents to update.
            documents: Optional new document contents.
            embeddings: Optional new embeddings.
            metadatas: Optional new metadata.
        """
        self.collection.update(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def count(self) -> int:
        """
        Get the number of documents in the vector database.

        Returns:
            The number of documents.
        """
        return self.collection.count()

    def clear(self) -> None:
        """
        Clear all documents from the vector database.
        """
        self.collection.delete(where={})


# Marker for beginning of RedisDB implementation - ensure imports are at top of file if not already.
# Assuming standard imports like uuid, List, Dict, Any, Optional, logger are already present.
# We will need specific imports for redisvl.

try:
    from redisvl.index import SearchIndex
    from redisvl.schema import IndexSchema, TextField, VectorField
    from redisvl.query import VectorQuery, FilterQuery
    from redisvl.query.filter import Tag
    # For hybrid, redisvl might use a different query structure or require manual query combination.
    # Let's assume FilterQuery for FT and VectorQuery for vector part, then combine results client-side if needed,
    # or use a combined query string if supported directly by redisvl for hybrid.
    # For now, we'll focus on schema and basic methods.
    import redis
except ImportError:
    logger.warning(
        "redis or redisvl packages not found. RedisDB will not be available. "
        "Please install them with `pip install redis redisvl`."
    )

    # Define a placeholder class if redisvl is not installed to avoid runtime errors on load
    class RedisDB(VectorDBBase):

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            raise NotImplementedError(
                "RedisDB requires 'redis' and 'redisvl' packages to be installed."
            )

        def add_documents(self, *args, **kwargs):
            raise NotImplementedError()

        def search(self, *args, **kwargs):
            raise NotImplementedError()

        def delete(self, *args, **kwargs):
            raise NotImplementedError()

        def get(self, *args, **kwargs):
            raise NotImplementedError()

        def update(self, *args, **kwargs):
            raise NotImplementedError()

        def count(self, *args, **kwargs):
            raise NotImplementedError()

        def clear(self, *args, **kwargs):
            raise NotImplementedError()


if "SearchIndex" in globals():  # Proceed only if redisvl was imported

    class RedisDB(VectorDBBase):
        """
        Vector database using Redis with RediSearch (via redisvl).
        Hybrid search is achieved by combining full-text search on a text field
        with vector similarity search.
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
                    - url: Redis URL (e.g., "redis://localhost:6379").
                    - index_name: Name of the RediSearch index.
                    - embedding_dimension: Dimension of the embeddings.
                    - text_field_name: Name for the text content field (for FT search).
                    - vector_field_name: Name for the vector field.
                    - (Optional) hybrid_search_params:
                        - text_score_weight: Weight for text search score in client-side fusion (0.0-1.0).
                        - vector_score_weight: Weight for vector search score in client-side fusion (0.0-1.0).
                hybrid_search_config: Global hybrid search configuration.
            """
            super().__init__(config=config, hybrid_search_config=hybrid_search_config)

            self.redis_url = self.config.get("url")
            if not self.redis_url:
                raise ValueError("Redis URL ('url') is required for RedisDB.")

            self.index_name = self.config.get("index_name", "rag-redis-index")
            self.embedding_dimension = self.config.get("embedding_dimension")
            if not self.embedding_dimension:
                raise ValueError(
                    "Embedding dimension ('embedding_dimension') is required for RedisDB."
                )

            self.text_field_name = self.config.get("text_field_name", "content")
            self.vector_field_name = self.config.get("vector_field_name", "embedding")

            self.hybrid_params = self.config.get("hybrid_search_params", {})
            self.text_score_weight = self.hybrid_params.get("text_score_weight", 0.5)
            self.vector_score_weight = self.hybrid_params.get(
                "vector_score_weight", 0.5
            )

            self.client = None
            self.index = None
            self._setup_client_and_index()

        def _get_redis_connection(self):
            """Helper to get a Redis connection from URL."""
            return redis.from_url(self.redis_url)

        def _setup_client_and_index(self) -> None:
            """
            Set up the Redis client and ensure the RediSearch index exists with the correct schema.
            """
            try:
                # Create a SearchIndex instance (which connects to Redis)
                self.index = SearchIndex.from_existing(
                    name=self.index_name, url=self.redis_url
                )
                logger.info(
                    f"Successfully connected to existing Redis index '{self.index_name}'."
                )
                # TODO: Validate existing schema if necessary, though redisvl might handle some aspects.
                # For simplicity, we assume if it exists, it's compatible or will be recreated if issues arise.
            except (
                Exception
            ) as e:  # Broad exception as redisvl might raise various things if index doesn't exist
                logger.info(
                    f"Redis index '{self.index_name}' not found or connection error: {e}. Attempting to create."
                )

                schema_dict = {
                    "index": {
                        "name": self.index_name,
                        "prefix": f"doc:{self.index_name}",  # Standard prefix for keys
                    },
                    "fields": [
                        {"name": self.text_field_name, "type": "text"},
                        {
                            "name": self.vector_field_name,
                            "type": "vector",
                            "attrs": {
                                "dims": self.embedding_dimension,
                                "algorithm": "flat",  # or "hnsw"
                                "distance_metric": "cosine",
                                "datatype": "float32",
                            },
                        },
                        # Add other metadata fields here if they need to be indexed for filtering
                        # e.g., {"name": "source", "type": "tag"}
                    ],
                }
                schema = IndexSchema.from_dict(schema_dict)

                try:
                    # Get a direct redis connection for index creation if SearchIndex.create() isn't available/suitable
                    # In newer redisvl, SearchIndex can create directly.
                    self.index = SearchIndex(schema=schema, redis_url=self.redis_url)
                    self.index.create(
                        overwrite=True
                    )  # Overwrite if it exists but was problematic
                    logger.info(
                        f"Redis index '{self.index_name}' created successfully with schema."
                    )
                except Exception as creation_error:
                    logger.error(
                        f"Failed to create Redis index '{self.index_name}': {creation_error}"
                    )
                    raise ValueError(
                        f"Failed to create Redis index '{self.index_name}'"
                    ) from creation_error

            # Store the underlying redis client from the index for other operations if needed
            if self.index and hasattr(self.index, "client") and self.index.client:
                self.client = self.index.client
            elif (
                self.index
                and hasattr(self.index, "_redis_conn")
                and self.index._redis_conn
            ):  # Older redisvl
                self.client = self.index._redis_conn
            else:
                self.client = self._get_redis_connection()  # Fallback

        # --- VectorDBBase methods to implement ---

        def add_documents(
            self,
            documents: List[str],
            embeddings: List[List[float]],  # Dense embeddings
            metadatas: Optional[List[Dict[str, Any]]] = None,
            ids: Optional[List[str]] = None,
            sparse_vectors: Optional[
                List[Optional[Dict[int, float]]]
            ] = None,  # Ignored for Redis
        ) -> List[str]:
            if sparse_vectors:
                logger.warning(
                    "RedisDB: 'sparse_vectors' are provided but will be ignored. "
                    "Redis hybrid search uses full-text search on stored text content."
                )

            if not documents or not embeddings:
                return []

            if ids is None:
                ids = [str(uuid.uuid4()) for _ in range(len(documents))]
            if metadatas is None:
                metadatas = [{} for _ in range(len(documents))]

            data_to_load = []
            for i, doc_text in enumerate(documents):
                record = {
                    "id": ids[i],  # redisvl uses 'id' by default for the key suffix
                    self.text_field_name: doc_text,
                    self.vector_field_name: np.array(
                        embeddings[i], dtype=np.float32
                    ).tobytes(),
                }
                # Add other metadata, ensuring they are compatible types for redisvl (str, int, float)
                # For simplicity, only adding text and vector now. Metadata needs careful handling.
                current_meta = metadatas[i]
                for k, v in current_meta.items():
                    if isinstance(
                        v, (str, int, float, bool)
                    ):  # redisvl schema fields for tags/text need simple types
                        record[k] = v
                    else:
                        record[k] = json.dumps(
                            v
                        )  # Store complex metadata as JSON string if not a dedicated schema field

                data_to_load.append(record)

            if data_to_load:
                # Assuming self.index is a redisvl.index.SearchIndex instance
                # Keys will be like "doc:index_name:id_value"
                keys = [f"{self.index.prefix}:{item['id']}" for item in data_to_load]
                self.index.load(data_to_load, keys=keys)
                logger.info(
                    f"RedisDB: Added {len(data_to_load)} documents to index '{self.index_name}'."
                )
            return ids

        def search(
            self,
            query_embedding: List[float],  # Dense query vector
            top_k: int = 5,
            filter: Optional[Dict[str, Any]] = None,  # Standard metadata filter
            query_sparse_vector: Optional[Dict[int, float]] = None,  # Ignored for Redis
            request_hybrid: bool = False,
            # For Redis, the original text query is needed for FT part of hybrid.
            # This is a workaround: expecting it in the filter.
        ) -> List[Dict[str, Any]]:
            if query_sparse_vector:
                logger.warning(
                    "RedisDB: 'query_sparse_vector' is provided but will be ignored. "
                    "Redis hybrid search uses full-text search on the original query text."
                )

            redis_filter_expression = None
            original_text_query_for_ft = None

            if filter:
                # Basic filter conversion for redisvl Tag queries (exact match on tags)
                # More complex filters would need more sophisticated parsing.
                # Example: filter = {"source": "website"} -> Tag("source") == "website"
                # For now, let's assume filter keys match tag fields in schema.
                conditions = []
                temp_filter = filter.copy()  # Avoid modifying original filter dict

                if "_text_query_for_redis_ft" in temp_filter:
                    original_text_query_for_ft = temp_filter.pop(
                        "_text_query_for_redis_ft"
                    )

                for key, value in temp_filter.items():
                    if isinstance(value, str):  # Assuming string values for tag filters
                        conditions.append(Tag(key) == value)
                if conditions:
                    # For multiple conditions, redisvl uses & or |
                    # Assuming AND for now if multiple filter conditions
                    current_filter_obj = conditions[0]
                    for i in range(1, len(conditions)):
                        current_filter_obj &= conditions[i]
                    redis_filter_expression = current_filter_obj

            results = []
            if (
                request_hybrid
                and self.hybrid_search_enabled
                and original_text_query_for_ft
            ):
                logger.info(
                    f"RedisDB: Performing hybrid search in index '{self.index_name}'."
                )
                # This is a simplified hybrid query. redisvl might offer more direct hybrid query objects.
                # Option 1: Two separate queries, then client-side merge & re-rank (complex).
                # Option 2: Construct a single RediSearch query string if redisvl allows raw queries.
                # FT <-> VEC @weight (syntax varies)
                # redisvl's FilterQuery is for FT, VectorQuery for KNN.
                # A common pattern is `(@text_field_name:$ft_query) =>[KNN $top_k @vector_field_name $vector_blob AS vector_score]`,
                # which performs FT then reranks top results with KNN.

                # Let's try to form a hybrid query string for RediSearch
                # This requires knowing the exact syntax and might be client version dependent.
                # Example: "(@content_field:word1 word2) (@vector_field:[VECTOR_RANGE $radius $vector_blob])"
                # Or more commonly: perform a vector search and then re-score or filter with FT, or vice-versa.
                # For simplicity, let's use redisvl's VectorQuery with a text filter if possible,
                # or acknowledge this part needs more advanced redisvl usage.

                # A basic hybrid approach with redisvl:
                # 1. Perform a vector query with a filter.
                # 2. The text query part needs to be incorporated.
                # If redisvl's VectorQuery can take a raw FT query string as part of its filter, that's one way.
                # query = VectorQuery(
                # vector=np.array(query_embedding, dtype=np.float32),
                # vector_field_name=self.vector_field_name,
                # num_results=top_k,
                # distance_threshold=None, # Optional
                # filter_expression= ??? # Here we'd need to combine metadata filter AND FT filter
                # )
                # This is tricky because redisvl's FilterExpression is for metadata, not arbitrary FT.

                # Let's assume a simple FT query for now, and then a vector query, and then a manual merge.
                # This is NOT ideal and not true server-side hybrid fusion.
                # For a true hybrid query, one might need to use raw RediSearch commands or a more specific
                # hybrid query object if redisvl provides one.

                # Fallback: If true hybrid query construction is too complex for this step,
                # log that it's doing dense search with FT filter.
                # Or, do a vector search and then if results are too few, broaden with FT.

                # Simplest "hybrid-like" with redisvl: Vector search + FT filter
                # This means the FT part acts as a strict filter, not a weighted component.
                ft_filter_part = Tag(self.text_field_name).matches(
                    original_text_query_for_ft
                )
                combined_filter = ft_filter_part
                if redis_filter_expression:
                    combined_filter &= redis_filter_expression

                vec_query = VectorQuery(
                    vector=np.array(query_embedding, dtype=np.float32),
                    vector_field_name=self.vector_field_name,
                    num_results=top_k,
                    filter_expression=combined_filter,
                )
                raw_results = self.index.query(vec_query)
                logger.info(
                    f"RedisDB: Executed hybrid-like (vector + FT filter) query. Found {len(raw_results)} results."
                )

            else:  # Dense only
                logger.info(
                    f"RedisDB: Performing dense-only search in index '{self.index_name}'."
                )
                vec_query = VectorQuery(
                    vector=np.array(query_embedding, dtype=np.float32),
                    vector_field_name=self.vector_field_name,
                    num_results=top_k,
                    filter_expression=redis_filter_expression,  # Only metadata filter
                )
                raw_results = self.index.query(vec_query)
                logger.info(
                    f"RedisDB: Executed dense-only query. Found {len(raw_results)} results."
                )

            # Format results (common for both paths)
            # redisvl results are typically List[Dict] where each dict is a document.
            for res_doc in raw_results:
                # The vector score might be under a specific key like 'vector_distance' or similar
                # depending on redisvl version and query type. Default is 'vector_distance'.
                score = 1 - float(
                    res_doc.get("vector_distance", 1.0)
                )  # Convert distance to similarity

                # Reconstruct metadata, excluding known fields like id, text_field, vector_field, score field
                metadata = {
                    k: v
                    for k, v in res_doc.items()
                    if k
                    not in [
                        "id",
                        self.text_field_name,
                        self.vector_field_name,
                        "vector_distance",
                        res_doc.get("_score_field_name", "vector_distance"),
                    ]
                }

                # Try to parse JSON string metadata back to dict if it was stored that way
                for k_meta, v_meta in metadata.items():
                    if isinstance(v_meta, str):
                        try:
                            metadata[k_meta] = json.loads(v_meta)
                        except json.JSONDecodeError:
                            pass  # Keep as string if not valid JSON

                results.append(
                    {
                        "id": res_doc["id"].split(":")[-1],  # Get original ID part
                        "text": res_doc.get(self.text_field_name, ""),
                        "metadata": metadata,
                        "score": score,
                    }
                )
            return results

        def delete(self, ids: List[str]) -> None:
            if not ids:
                return
            # redisvl SearchIndex.delete expects full keys
            full_keys = [f"{self.index.prefix}:{id_val}" for id_val in ids]
            self.index.client.delete(*full_keys)  # Use underlying client's delete
            logger.info(
                f"RedisDB: Deleted {len(ids)} documents from index '{self.index_name}'."
            )

        def get(self, ids: List[str]) -> List[Dict[str, Any]]:
            if not ids:
                return []
            full_keys = [f"{self.index.prefix}:{id_val}" for id_val in ids]
            # Fetching raw documents by key. redisvl SearchIndex might not have a direct 'get_documents' by list of IDs.
            # Use underlying client.
            raw_docs = self.index.client.mget(
                full_keys
            )  # This gets raw Redis hash objects

            formatted_results = []
            for i, raw_doc_bytes in enumerate(raw_docs):
                if raw_doc_bytes:  # MGET returns None for non-existent keys
                    # Assuming documents are stored as Hashes by redisvl's load method
                    # Need to decode bytes to str for field names and some values
                    doc_fields = {
                        k.decode("utf-8"): v.decode("utf-8")
                        for k, v in raw_doc_bytes.items()
                    }

                    text = doc_fields.get(self.text_field_name, "")
                    # Vector is stored as bytes, needs to be converted back to list of floats
                    embedding_bytes = raw_doc_bytes.get(
                        self.vector_field_name.encode("utf-8")
                    )  # Key is bytes
                    embedding = None
                    if embedding_bytes:
                        embedding = np.frombuffer(
                            embedding_bytes, dtype=np.float32
                        ).tolist()

                    metadata = {
                        k: v
                        for k, v in doc_fields.items()
                        if k not in ["id", self.text_field_name, self.vector_field_name]
                    }
                    for k_meta, v_meta in metadata.items():  # Try to parse JSON strings
                        if isinstance(v_meta, str):
                            try:
                                metadata[k_meta] = json.loads(v_meta)
                            except:
                                pass

                    formatted_results.append(
                        {
                            "id": ids[i],  # Use original requested ID
                            "text": text,
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
        ) -> None:
            # Simplest update: delete then add. True partial updates are more complex.
            logger.warning(
                "RedisDB: Update operation is implemented as delete then add. This is not a partial update."
            )
            if not ids:
                return

            # Prepare data for re-adding
            docs_to_readd = []
            embeds_to_readd = []
            metas_to_readd = []
            ids_to_readd = []

            # Fetch existing data for fields not being updated
            # This is inefficient for many updates. A true upsert or partial update mechanism in redisvl would be better.
            # For now, we require all fields to be provided for simplicity if we don't fetch.
            # Let's assume if a field is None, it's not updated, but this requires careful construction of add_documents call.

            # To keep it simple for this pass: if updating, assume all relevant fields for the ID are provided or it's a full replace.
            # We'll just call add_documents which handles ID generation if needed, but here IDs are fixed.

            # For a true update, one would fetch, modify, then re-store.
            # For now, just use add_documents which will overwrite if IDs are the same.
            # This assumes `add_documents` can handle overwriting based on ID.
            # redisvl's `load` with same keys will overwrite.

            if documents is None:
                documents = [None] * len(ids)
            if embeddings is None:
                embeddings = [None] * len(ids)
            if metadatas is None:
                metadatas = [None] * len(ids)

            valid_docs_for_add = []
            valid_embeds_for_add = []
            valid_metas_for_add = []
            valid_ids_for_add = []

            # This is effectively an upsert.
            # We need to ensure that if a document/embedding/metadata is not provided for an ID,
            # it's not accidentally wiped if `add_documents` expects full data.
            # The current `add_documents` expects dense embeddings.
            # This update is tricky without a proper partial update mechanism or fetching existing.

            # Let's simplify: update will only work if all components (doc, embed, meta) for an ID are provided.
            # Or, it's a full replacement.
            # The `add_documents` method already handles this by creating new records.
            # So, we can just call it. It will overwrite based on the key (doc:index_name:id).

            # We need to filter out None entries for documents and embeddings for the items being updated.
            # This is still not a true partial update.

            # Let's make `update` a simple call to `add_documents` for the provided IDs.
            # The caller is responsible for providing the complete new state for those IDs.

            # Filter out entries where essential data for add_documents might be missing
            # For simplicity, if embeddings[i] is None, we can't re-add.
            final_ids = []
            final_docs = []
            final_embeds = []
            final_metas = []

            for i, doc_id in enumerate(ids):
                if (
                    embeddings[i] is not None and documents[i] is not None
                ):  # Must have dense embedding and text
                    final_ids.append(doc_id)
                    final_docs.append(documents[i])
                    final_embeds.append(embeddings[i])
                    final_metas.append(metadatas[i] if metadatas[i] is not None else {})
                else:
                    logger.warning(
                        f"RedisDB: Skipping update for ID {doc_id} due to missing document text or dense embedding."
                    )

            if final_ids:
                self.add_documents(
                    documents=final_docs,
                    embeddings=final_embeds,
                    metadatas=final_metas,
                    ids=final_ids,
                )
                logger.info(
                    f"RedisDB: Updated {len(final_ids)} documents by re-adding."
                )
            else:
                logger.info(
                    "RedisDB: No documents were updated as essential data was missing."
                )

        def count(self) -> int:
            # Get index info
            try:
                info = self.index.info()
                return int(info.get("num_docs", 0))
            except Exception as e:
                logger.error(
                    f"RedisDB: Error getting count for index '{self.index_name}': {e}"
                )
                return 0

        def clear(self) -> None:
            # Deletes all documents from the index.
            # redisvl SearchIndex doesn't have a direct clear_all_docs method.
            # One way is to delete the index and recreate it.
            try:
                self.index.delete(drop=True)  # Deletes the index itself
                logger.info(f"RedisDB: Index '{self.index_name}' deleted.")
                self._setup_client_and_index()  # Recreate it
                logger.info(
                    f"RedisDB: Index '{self.index_name}' cleared and recreated."
                )
            except Exception as e:
                logger.error(f"RedisDB: Error clearing index '{self.index_name}': {e}")
                # As a fallback, could try to scan and delete all keys with the prefix, but that's risky and slow.
                # For now, if drop fails, we log error.


# End of RedisDB implementation
# Ensure this new class is registered in VectorDBService.get_db_instance if dynamic loading is used.
# (This part is outside this file, in vector_db_service.py)
