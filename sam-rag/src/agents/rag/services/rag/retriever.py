"""
Implementation of a retriever component for RAG systems.

This module provides functionality to retrieve relevant documents from a vector database
based on a query. It handles the embedding of the query and the retrieval of similar
documents from the vector database.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
from solace_ai_connector.common.log import log as logger

from ..database.vector_db_service import VectorDBService
from ..embedder.embedder_service import EmbedderService


class Retriever:
    """
    Retriever component for RAG systems that handles query embedding and document retrieval.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the retriever.

        Args:
            config: A dictionary containing configuration parameters.
                - embedding: Configuration for the embedding service.
                - vector_db: Configuration for the vector database.
        """
        self.config = config or {}

        # Initialize embedding service
        self.embedding_service = EmbedderService(self.config.get("embedding", {}))
        logger.info("Retriever initialized with embedding service")

        # Initialize vector database service
        self.vector_db = VectorDBService(self.config.get("vector_db", {}))
        logger.info("Retriever initialized with vector database service")

        # Set retrieval parameters
        self.retrieval_config = self.config.get("retrieval", {})
        self.top_k = 5  # Default value
        if self.retrieval_config:
            self.top_k = self.retrieval_config.get("top_k", 5)
        logger.info("Retriever initialized with top-k parameter")

    def retrieve(
        self,
        query: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve documents similar to the query.

        Args:
            query: The query text.
            filter: Optional filter to apply to the search.

        Returns:
            A list of dictionaries containing the search results, each with:
            - text: The document text
            - metadata: The document metadata
            - score: The similarity score
        """
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

    def get_query_embedding(self, query: str) -> List[float]:
        """
        Get the embedding for a query.

        Args:
            query: The query text.

        Returns:
            The embedding vector for the query.
        """
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
