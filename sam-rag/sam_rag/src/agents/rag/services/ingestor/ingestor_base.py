"""
Base class for document ingestors.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, Tuple


class IngestorBase(ABC):
    """
    Abstract base class for document ingestors.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the ingestor with the given configuration.

        Args:
            config: A dictionary containing configuration parameters.
        """
        self.config = config or {}

    @abstractmethod
    def ingest_documents(
        self,
        file_paths: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest documents from file paths.

        Args:
            file_paths: List of file paths to ingest.
            metadata: Optional metadata for each document.

        Returns:
            A dictionary containing the ingestion results.
        """
        pass

    @abstractmethod
    def ingest_texts(
        self,
        texts: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest texts directly.

        Args:
            texts: List of texts to ingest.
            metadata: Optional metadata for each text.
            ids: Optional IDs for each text.

        Returns:
            A dictionary containing the ingestion results.
        """
        pass

    @abstractmethod
    def delete_documents(self, ids: List[str]) -> None:
        """
        Delete documents from the vector database.

        Args:
            ids: The IDs of the documents to delete.
        """
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query.

        Args:
            query: The query text.
            top_k: The number of results to return.
            filter: Optional filter to apply to the search.

        Returns:
            A list of dictionaries containing the search results.
        """
        pass
