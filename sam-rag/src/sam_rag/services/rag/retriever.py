"""
Implementation of a retriever component for RAG systems.

This module provides functionality to retrieve relevant documents from a vector database
based on a query. It handles the embedding of the query and the retrieval of similar
documents from the vector database.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

from sam_rag.services.database.vector_db_service import VectorDBService
from sam_rag.services.embedder.embedder_service import EmbedderService

logger = logging.getLogger(__name__)

class Retriever:
    """
    Retriever component for RAG systems that handles query embedding and document retrieval.
    """

    def __init__(
        self,
        config: Dict[str, Any] = None,
        hybrid_search_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the retriever.

        Args:
            config: A dictionary containing configuration parameters.
                - embedding: Configuration for the embedding service.
                - vector_db: Configuration for the vector database.
                - retrieval: Configuration for retrieval parameters like top_k.
            hybrid_search_config: Optional dictionary containing hybrid search configuration.
        """
        self.config = config or {}
        _hybrid_search_config = hybrid_search_config or {}
        self.hybrid_search_enabled = _hybrid_search_config.get("enabled", False)

        # Initialize embedding service
        self.embedding_service = EmbedderService(
            config=self.config.get("embedding", {}),
            hybrid_search_config=_hybrid_search_config,
        )
        logger.info("Retriever initialized with embedding service")

        # Initialize vector database service
        self.vector_db = VectorDBService(
            config=self.config.get("vector_db", {}),
            hybrid_search_config=_hybrid_search_config,
        )
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
        logger.debug(
            f"[HYBRID_SEARCH_DEBUG] retrieve called with query length: {len(query)}, hybrid_search_enabled: {self.hybrid_search_enabled}, top_k: {self.top_k}"
        )

        try:
            # Get query embedding (dense and potentially sparse)
            query_embedding_data = self.get_query_embedding(query)
            dense_query_embedding = query_embedding_data["dense_vector"]
            sparse_query_vector = query_embedding_data.get("sparse_vector")

            logger.debug(
                f"[HYBRID_SEARCH_DEBUG] Query embeddings - dense_dim: {len(dense_query_embedding) if dense_query_embedding else 0}, sparse_terms: {len(sparse_query_vector) if sparse_query_vector else 0}"
            )

            request_hybrid_search = self.hybrid_search_enabled

            # Search the vector database
            results = self.vector_db.search(
                query_embedding=dense_query_embedding,
                top_k=self.top_k,
                filter=filter,
                query_sparse_vector=sparse_query_vector,
                request_hybrid=request_hybrid_search,
            )

            logger.info(f"Found {len(results)} results for query")
            logger.debug(
                f"[HYBRID_SEARCH_DEBUG] Search results sample: {[{'score': r.get('score', r.get('distance', 'N/A')), 'text_preview': r.get('text', '')[:50]} for r in results[:3]]}"
            )
            return results
        except Exception:
            logger.error("Error retrieving documents.")
            raise ValueError(
                "Error retrieving documents. Please check the query and try again."
            ) from None

    def get_query_embedding(self, query: str) -> Dict[str, Any]:
        """
        Get the embedding data (dense and potentially sparse) for a query.

        Args:
            query: The query text.

        Returns:
            A dictionary containing "dense_vector" and "sparse_vector" (if applicable).
        """
        try:
            # Get query embedding data
            embedding_data = self.embedding_service.embed_text(query)
            if not embedding_data or not embedding_data.get("dense_vector"):
                raise ValueError("Failed to generate embedding for query") from None

            return embedding_data
        except Exception:
            logger.error("Error generating query embedding.")
            raise ValueError(
                "Error generating query embedding. Please check the query and try again."
            ) from None
