"""
Base class for vector databases.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class VectorDBBase(ABC):
    """
    Abstract base class for vector databases.
    """

    def __init__(
        self,
        config: Dict[str, Any] = None,
        hybrid_search_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the vector database with the given configuration.

        Args:
            config: A dictionary containing configuration parameters for the specific database.
            hybrid_search_config: Optional dictionary containing hybrid search configuration.
        """
        self.config = config or {}
        self.hybrid_search_config = hybrid_search_config or {}
        self.hybrid_search_enabled = self.hybrid_search_config.get("enabled", False)

    @abstractmethod
    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
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
        pass

    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
        query_sparse_vector: Optional[Dict[int, float]] = None,
        request_hybrid: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query embedding.

        Args:
            query_embedding: The dense query embedding.
            top_k: The number of results to return.
            filter: Optional filter to apply to the search.
            query_sparse_vector: Optional sparse vector for the query.
            request_hybrid: Flag to request hybrid search if available and enabled.

        Returns:
            A list of dictionaries containing the search results.
        """
        pass

    @abstractmethod
    def delete(self, ids: List[str]) -> None:
        """
        Delete documents from the vector database.

        Args:
            ids: The IDs of the documents to delete.
        """
        pass

    @abstractmethod
    def get(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get documents from the vector database.

        Args:
            ids: The IDs of the documents to get.

        Returns:
            A list of dictionaries containing the documents.
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def count(self) -> int:
        """
        Get the number of documents in the vector database.

        Returns:
            The number of documents.
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """
        Clear all documents from the vector database.
        """
        pass
