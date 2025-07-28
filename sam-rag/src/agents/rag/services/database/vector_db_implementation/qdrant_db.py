"""
Qdrant vector database implementation.
"""

import uuid
from typing import Dict, Any, List, Optional
from solace_ai_connector.common.log import log as logger

from ..vector_db_base import VectorDBBase


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
        print(  # Using print for direct visibility
            f"DEBUG QdrantDB.add_documents called. hybrid_search_enabled: {self.hybrid_search_enabled}, sparse_vectors provided: {sparse_vectors is not None}"
        )
        if sparse_vectors:
            print(
                f"DEBUG QdrantDB.add_documents: First few sparse_vectors (if any): {sparse_vectors[:2]}"
            )  # Using print
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
                    payload["text"] = current_doc["text"]

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
