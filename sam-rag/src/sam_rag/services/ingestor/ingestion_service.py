"""
Implementation of document ingestion service focused only on vector database operations.

This module provides a simplified ingestion service that only handles the storage of 
pre-processed, pre-embedded content into a vector database. The preprocessing,
splitting, and embedding steps are handled by the RAG pipeline.
"""

import logging
from typing import Dict, Any, List, Optional

from sam_rag.services.database.vector_db_service import VectorDBService
from sam_rag.services.ingestor.ingestion_base import IngestionBase

logger = logging.getLogger(__name__)

class IngestionService(IngestionBase):
    """
    Ingest documents into a vector database.
    """

    def __init__(
        self,
        config: Dict[str, Any] = None,
        hybrid_search_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the document ingestion service.

        Args:
            config: A dictionary containing configuration parameters.
                - vector_db: Configuration for the vector database.
            hybrid_search_config: Optional dictionary containing hybrid search configuration.
        """
        super().__init__(config)
        _hybrid_search_config = hybrid_search_config or {}

        # Initialize only the vector database component
        self.vector_db = VectorDBService(
            config=self.config.get("vector_db", {}),
            hybrid_search_config=_hybrid_search_config,
        )
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
        embeddings: List[Dict[str, Any]],  # Updated type hint
        metadata: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest pre-processed and pre-embedded texts into the vector database.

        Args:
            texts: List of pre-processed text chunks.
            embeddings: List of dictionaries, each containing "dense_vector"
                        and optionally "sparse_vector".
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
            error_msg = f"Number of texts ({len(texts)}) does not match number of embedding structures ({len(embeddings)})"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "document_ids": [],
            }

        dense_vectors: List[List[float]] = []
        sparse_vectors: List[Optional[Dict[int, float]]] = []

        for emb_data in embeddings:
            dense_vectors.append(emb_data["dense_vector"])
            sparse_vectors.append(emb_data.get("sparse_vector"))

        # Store embeddings in vector database
        try:
            logger.debug(
                f"[HYBRID_SEARCH_DEBUG] Storing {len(texts)} documents with dense_vectors: {len(dense_vectors)}, sparse_vectors: {len([sv for sv in sparse_vectors if sv])}"
            )

            document_ids = self.vector_db.add_documents(
                documents=texts,
                embeddings=dense_vectors,  # Pass extracted dense vectors
                metadatas=metadata,
                ids=ids,
                sparse_vectors=sparse_vectors,  # Pass extracted sparse vectors
            )
            logger.info(f"Added {len(document_ids)} documents to vector database")
            logger.debug(
                f"[HYBRID_SEARCH_DEBUG] Successfully stored document IDs: {document_ids[:5]}{'...' if len(document_ids) > 5 else ''}"
            )

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
