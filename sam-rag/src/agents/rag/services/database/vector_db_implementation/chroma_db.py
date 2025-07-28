"""
ChromaDB vector database implementation.
"""

import os
import uuid
from typing import Dict, Any, List, Optional
from solace_ai_connector.common.log import log as logger

from ..vector_db_base import VectorDBBase


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
                                  Note: This ChromaDB implementation does not support hybrid search.
        """
        super().__init__(config=config, hybrid_search_config=hybrid_search_config)
        if self.hybrid_search_enabled:
            logger.warning(
                "ChromaDB: Hybrid search was enabled in config, but this implementation "
                "does not support hybrid search. It will operate in dense-only mode."
            )
            self.hybrid_search_enabled = False

        self.persist_directory = self.config.get("persist_directory", "./chroma_db")
        self.collection_name = self.config.get("collection_name", "documents")
        self.embedding_dimension = self.config.get(
            "embedding_dimension", 768
        )  # Used for metadata
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
            # Ensure the persist_directory exists
            if not os.path.exists(self.persist_directory):
                os.makedirs(self.persist_directory, exist_ok=True)
                logger.info(
                    f"Created persist_directory for ChromaDB at {self.persist_directory}"
                )

            self.client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(
                    anonymized_telemetry=False
                ),  # Consider making telemetry configurable
            )

            # Get or create the collection
            # ChromaDB uses 'hnsw:space' for distance metric in collection metadata.
            # Common values: "l2" (Euclidean), "ip" (inner product), "cosine"
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={
                    "hnsw:space": "cosine",  # Defaulting to cosine similarity
                    "embedding_dimension": str(
                        self.embedding_dimension
                    ),  # Store as string if needed by Chroma
                },
                embedding_function=None,  # We provide our own embeddings
            )
        except ImportError:
            raise ImportError(
                "The chromadb package is required for ChromaDB. "
                "Please install it with `pip install chromadb`."
            ) from None
        except Exception as e:
            logger.error(f"Error setting up ChromaDB client: {e}")
            raise ConnectionError(f"Failed to set up ChromaDB client: {e}") from e

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        sparse_vectors: Optional[List[Optional[Dict[int, float]]]] = None,
    ) -> List[str]:
        """
        Add documents to the vector database. ChromaDB only supports dense vectors through this interface.

        Args:
            documents: The documents to add.
            embeddings: The embeddings of the documents.
            metadatas: Optional metadata for each document.
            ids: Optional IDs for each document.
            sparse_vectors: Ignored.

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

        # Ensure metadatas list length matches documents list length
        if len(metadatas) < len(documents):
            metadatas.extend(
                [{"source": "unknown"}] * (len(documents) - len(metadatas))
            )

        # Add the documents to the collection
        # ChromaDB expects embeddings to be a list of lists, which is already the case.
        # Documents should be a list of strings.
        # Metadatas should be a list of dictionaries.
        # IDs should be a list of strings.
        self.collection.add(
            documents=documents,  # List of strings
            embeddings=embeddings,  # List of lists of floats
            metadatas=metadatas,  # List of dicts
            ids=ids,  # List of strings
        )

        return ids

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,  # ChromaDB calls this 'where'
        query_sparse_vector: Optional[Dict[int, float]] = None,
        request_hybrid: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query embedding. ChromaDB only supports dense search.

        Args:
            query_embedding: The query embedding.
            top_k: The number of results to return.
            filter: Optional filter to apply to the search (Chroma's 'where' clause).
                    Example: {"source": "website"} or {"type": {"$eq": "report"}}
            query_sparse_vector: Ignored.
            request_hybrid: Ignored.

        Returns:
            A list of dictionaries containing the search results.
        """
        if request_hybrid or query_sparse_vector:
            logger.warning(
                "ChromaDB: 'request_hybrid' was true or 'query_sparse_vector' was provided, "
                "but ChromaDB currently only supports dense search through this interface. Proceeding with dense search."
            )

        # Search the collection
        # query_embeddings should be a list of embeddings, so [query_embedding]
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter,  # Pass the filter as 'where'
            include=["metadatas", "documents", "distances"],  # Specify what to include
        )

        # Format the results
        # ChromaDB query results are structured as dictionaries with keys like 'ids', 'documents', 'metadatas', 'distances'.
        # Each of these is a list of lists (one inner list per query embedding, though we only send one).
        formatted_results = []
        if results and results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                formatted_results.append(
                    {
                        "id": results["ids"][0][i],
                        "text": results["documents"][0][i]
                        if results["documents"] and results["documents"][0]
                        else "",
                        "metadata": results["metadatas"][0][i]
                        if results["metadatas"] and results["metadatas"][0]
                        else {},
                        "distance": results["distances"][0][i]
                        if results["distances"] and results["distances"][0]
                        else float("inf"),
                    }
                )
        return formatted_results

    def delete(self, ids: List[str]) -> None:
        """
        Delete documents from the vector database.

        Args:
            ids: The IDs of the documents to delete.
        """
        if not ids:
            return
        self.collection.delete(ids=ids)

    def get(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get documents from the vector database.

        Args:
            ids: The IDs of the documents to get.

        Returns:
            A list of dictionaries containing the documents.
        """
        if not ids:
            return []
        # Get the documents
        # ChromaDB get() returns a dict with 'ids', 'embeddings', 'metadatas', 'documents'
        results = self.collection.get(
            ids=ids,
            include=["metadatas", "documents", "embeddings"],  # Specify what to include
        )

        # Format the results
        formatted_results = []
        if results and results["ids"]:
            for i in range(len(results["ids"])):
                formatted_results.append(
                    {
                        "id": results["ids"][i],
                        "text": results["documents"][i] if results["documents"] else "",
                        "metadata": results["metadatas"][i]
                        if results["metadatas"]
                        else {},
                        "embedding": results["embeddings"][i]
                        if results["embeddings"]
                        else [],
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
        ChromaDB's update method replaces the specified fields for the given IDs.
        If a field (documents, embeddings, metadatas) is None, it's not updated for those IDs.

        Args:
            ids: The IDs of the documents to update.
            documents: Optional new document contents (list of strings).
            embeddings: Optional new embeddings (list of lists of floats).
            metadatas: Optional new metadata (list of dicts).
            sparse_vectors: Ignored.
        """
        if sparse_vectors:
            logger.warning(
                "ChromaDB: 'sparse_vectors' parameter was provided but will be ignored."
            )

        if not ids:
            return

        # ChromaDB's update method requires lists for documents, embeddings, metadatas
        # that correspond to the list of IDs. If a parameter is None, it means no update for that aspect.
        # However, if a list is provided, it must match the length of `ids`.
        # This logic needs to be handled carefully if we want to allow partial updates (e.g., update only metadata for some IDs).
        # For now, assume if a list is provided, it's complete for the given IDs.

        # The `collection.update` method expects that if a list (e.g., `documents`) is provided,
        # it has the same length as `ids`.
        # If you want to update only specific items, you might need to fetch, modify, then `upsert` or `add` again.
        # Or, construct the lists carefully.

        # Let's stick to the direct `update` call. If `documents` is not None, it must be a list of len(ids).
        # Same for embeddings and metadatas.

        self.collection.update(
            ids=ids,
            documents=documents
            if documents
            else None,  # Pass None if not updating documents
            embeddings=embeddings
            if embeddings
            else None,  # Pass None if not updating embeddings
            metadatas=metadatas
            if metadatas
            else None,  # Pass None if not updating metadatas
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
        This involves deleting the collection and recreating it, as ChromaDB
        doesn't have a simple "delete all items" for a PersistentClient collection
        without deleting the collection itself.
        Alternatively, one could query all IDs and delete them, but that's less efficient.
        """
        logger.info(
            f"Clearing ChromaDB collection '{self.collection_name}' by deleting and recreating."
        )
        try:
            self.client.delete_collection(name=self.collection_name)
        except Exception as e:
            # Catch specific exception if collection doesn't exist, e.g. ValueError from Chroma
            logger.warning(
                f"Could not delete collection '{self.collection_name}' (it might not exist): {e}"
            )

        # Recreate the collection
        self._setup_client()  # This will call get_or_create_collection
