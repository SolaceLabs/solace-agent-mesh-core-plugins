"""
Service for vector database operations.
"""
import logging
from typing import Dict, Any, List, Optional

from sam_rag.services.database.vector_db_base import VectorDBBase
from sam_rag.services.database.vector_db_implementation import (  # Corrected import path
    PineconeDB,
    QdrantDB,
    RedisLegacyDB,
    RedisVLDB,
    PgVectorDB,
    ChromaDB,
)

logger = logging.getLogger(__name__)

class VectorDBService:
    """
    Service for vector database operations.
    """

    def __init__(
        self,
        config: Dict[str, Any] = None,
        hybrid_search_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the vector database service.

        Args:
            config: A dictionary containing configuration parameters for the vector database.
                - db_type: The type of vector database to use (default: "chroma").
                - db_params: The parameters to pass to the vector database.
            hybrid_search_config: Optional dictionary containing hybrid search configuration.
                - enabled: Boolean flag to enable/disable hybrid search.
        """
        self.config = config or {}
        self.db_type = self.config.get("db_type", "chroma")
        self.db_params = self.config.get("db_params", {})

        self.hybrid_search_config = hybrid_search_config or {}
        self.hybrid_search_enabled = self.hybrid_search_config.get("enabled", False)

        self.db = self._create_db()

    def _create_db(self) -> VectorDBBase:
        """
        Create the appropriate vector database based on the configuration.

        Returns:
            The vector database instance.
        """
        # Pass hybrid_search_config to individual DB implementations
        if self.db_type == "chroma":
            return ChromaDB(
                config=self.db_params, hybrid_search_config=self.hybrid_search_config
            )
        elif self.db_type == "pinecone":
            return PineconeDB(
                config=self.db_params, hybrid_search_config=self.hybrid_search_config
            )
        elif self.db_type == "qdrant":
            return QdrantDB(
                config=self.db_params, hybrid_search_config=self.hybrid_search_config
            )
        elif self.db_type == "redis_legacy":  # Updated
            return RedisLegacyDB(  # Updated
                config=self.db_params, hybrid_search_config=self.hybrid_search_config
            )
        elif self.db_type == "redis_vl":  # Added
            return RedisVLDB(  # Added
                config=self.db_params, hybrid_search_config=self.hybrid_search_config
            )
        elif self.db_type == "pgvector":
            return PgVectorDB(
                config=self.db_params, hybrid_search_config=self.hybrid_search_config
            )
        else:
            # Default to ChromaDB
            return ChromaDB(
                config=self.db_params, hybrid_search_config=self.hybrid_search_config
            )

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
            embeddings: The embeddings of the documents.
            metadatas: Optional metadata for each document.
            ids: Optional IDs for each document.

        Returns:
            The IDs of the added documents.
        """
        return self.db.add_documents(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
            sparse_vectors=sparse_vectors,
        )

    def search(
        self,
        query_embedding: List[float],  # This is the dense query vector
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
        query_sparse_vector: Optional[Dict[int, float]] = None,
        request_hybrid: bool = False,
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

        logger.debug(
            f"[HYBRID_SEARCH_DEBUG] VectorDBService.search called with db_type: {self.db_type}, request_hybrid: {request_hybrid}, has_sparse_vector: {query_sparse_vector is not None and len(query_sparse_vector) > 0 if query_sparse_vector else False}"
        )

        results = self.db.search(
            query_embedding=query_embedding,
            top_k=top_k,
            filter=filter,
            query_sparse_vector=query_sparse_vector,
            request_hybrid=request_hybrid,
        )

        logger.debug(
            f"[HYBRID_SEARCH_DEBUG] VectorDBService.search returned {len(results)} results"
        )
        return results

    def delete(self, ids: List[str]) -> None:
        """
        Delete documents from the vector database.

        Args:
            ids: The IDs of the documents to delete.
        """
        self.db.delete(ids)

    def get(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get documents from the vector database.

        Args:
            ids: The IDs of the documents to get.

        Returns:
            A list of dictionaries containing the documents.
        """
        return self.db.get(ids)

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
        self.db.update(ids, documents, embeddings, metadatas)

    def count(self) -> int:
        """
        Get the number of documents in the vector database.

        Returns:
            The number of documents.
        """
        return self.db.count()

    def clear(self) -> None:
        """
        Clear all documents from the vector database.
        """
        self.db.clear()

    def add_file_embeddings(
        self,
        file_embeddings: Dict[str, List[List[float]]],
        file_chunks: Dict[str, List[str]],
        metadatas: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, List[str]]:
        """
        Add file embeddings to the vector database.

        Args:
            file_embeddings: A dictionary mapping file paths to lists of embeddings.
            file_chunks: A dictionary mapping file paths to lists of text chunks.
            metadatas: Optional dictionary mapping file paths to lists of metadata.

        Returns:
            A dictionary mapping file paths to lists of document IDs.
        """
        result = {}

        for file_path, embeddings in file_embeddings.items():
            # Get the chunks for this file
            chunks = file_chunks.get(file_path, [])

            # Get the metadata for this file
            file_metadatas = None
            if metadatas and file_path in metadatas:
                file_metadatas = metadatas[file_path]
            else:
                # Create default metadata
                file_metadatas = [{"source": file_path} for _ in range(len(chunks))]

            # Add the documents to the vector database
            ids = self.add_documents(chunks, embeddings, file_metadatas)

            # Add to the result
            result[file_path] = ids

        return result

    def search_similar_chunks(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for chunks similar to the query embedding.

        Args:
            query_embedding: The query embedding.
            top_k: The number of results to return.
            filter: Optional filter to apply to the search.

        Returns:
            A list of dictionaries containing the search results.
        """
        return self.search(query_embedding, top_k, filter)
