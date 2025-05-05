"""
Implementation of document ingestion service focused only on vector database operations.

This module provides a simplified ingestion service that only handles the storage of 
pre-processed, pre-embedded content into a vector database. The preprocessing,
splitting, and embedding steps are handled by the RAG pipeline.
"""

from typing import Dict, Any, List, Optional
from solace_ai_connector.common.log import log as logger

from ..database.vector_db_service import VectorDBService
from .ingestion_base import IngestionBase


class IngestionService(IngestionBase):
    """
    Ingest documents into a vector database.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the document ingestion service.

        Args:
            config: A dictionary containing configuration parameters.
                - vector_db: Configuration for the vector database.
        """
        super().__init__(config)

        # Initialize only the vector database component
        self.vector_db = VectorDBService(self.config.get("vector_db", {}))
        logger.info("Document ingestion service initialized with vector database")

    def ingest_documents(
        self,
        file_paths: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        This method is maintained for compatibility with the IngestionBase interface,
        but it's not implemented in this simplified version.
        The RAG pipeline should handle document processing and use ingest_embeddings instead.
        """
        logger.warning("ingest_documents is not implemented in this version")
        return {
            "success": False,
            "message": "ingest_documents is not implemented. Use the RAG pipeline instead.",
            "document_ids": [],
        }

    def ingest_texts(
        self,
        texts: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest pre-processed texts with their embeddings.

        This method is maintained for compatibility with existing code that uses
        the ingestion service directly. In the new workflow, you should use
        ingest_embeddings instead.

        Args:
            texts: List of pre-processed text chunks.
            metadata: Optional metadata for each text chunk.
            ids: Optional IDs for each text chunk.

        Returns:
            A dictionary containing the ingestion results.
        """
        logger.warning(
            "Using ingest_texts without embeddings. This will fail if called directly."
        )
        return {
            "success": False,
            "message": "ingest_texts without embeddings is not supported. Use ingest_embeddings instead.",
            "document_ids": [],
        }

    def ingest_embeddings(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        metadata: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest pre-processed and pre-embedded texts into the vector database.

        Args:
            texts: List of pre-processed text chunks.
            embeddings: List of embeddings corresponding to the text chunks.
            metadata: Optional metadata for each text chunk.
            ids: Optional IDs for each text chunk.

        Returns:
            A dictionary containing the ingestion results.
        """
        logger.info(f"Ingesting {len(texts)} pre-processed and pre-embedded texts")

        # Create default metadata if not provided
        if metadata is None:
            metadata = [{"source": "direct_text"} for _ in range(len(texts))]

        # Verify that texts and embeddings have the same length
        if len(texts) != len(embeddings):
            error_msg = f"Number of texts ({len(texts)}) does not match number of embeddings ({len(embeddings)})"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "document_ids": [],
            }

        # Store embeddings in vector database
        try:
            document_ids = self.vector_db.add_documents(
                documents=texts,
                embeddings=embeddings,
                metadatas=metadata,
                ids=ids,
            )
            logger.info(f"Added {len(document_ids)} documents to vector database")

            return {
                "success": True,
                "message": f"Successfully ingested {len(document_ids)} points into vector database",
                "document_ids": document_ids,
            }
        except Exception:
            error_msg = "Error storing embeddings in vector database."
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "document_ids": [],
            }

    def delete_documents(self, ids: List[str]) -> None:
        """
        Delete documents from the vector database.

        Args:
            ids: The IDs of the documents to delete.
        """
        try:
            self.vector_db.delete(ids)
            logger.info(f"Deleted {len(ids)} documents from vector database")
        except Exception:
            logger.error("Error deleting documents from vector database.")
            raise ValueError("Error deleting documents from vector database") from None
