"""
Service for embedding text chunks into vector representations.
"""

from typing import Dict, Any, List, Tuple
import numpy as np

from .embedder_base import EmbedderBase

from .litellm_embedder import LiteLLMEmbedder


class EmbedderService:
    """
    Service for embedding text chunks into vector representations.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the embedder service.

        Args:
            config: A dictionary containing configuration parameters.
                - embedder_type: The type of embedder to use (default: "openai").
                - embedder_params: The parameters to pass to the embedder.
        """
        self.config = config or {}
        self.embedder_type = self.config.get("embedder_type", "openai")
        self.embedder_params = self.config.get("embedder_params", {})
        self.normalize = self.config.get("normalize_embeddings", True)
        self.embedder = self._create_embedder()

    def _create_embedder(self) -> EmbedderBase:
        """
        Create the appropriate embedder based on the configuration.

        Returns:
            The embedder instance.
        """
        # Check if we should use litellm for cloud embedders
        if self.embedder_type in ["openai", "azure_openai", "cohere", "vertex_ai"]:
            # Map embedder_type to litellm model format
            model_prefix = {
                "openai": "openai/",
                "azure_openai": "azure/",
                "cohere": "cohere/",
                "vertex_ai": "vertex_ai/",
            }

            # Create a copy of the embedder params
            params = self.embedder_params.copy()

            # Add the model prefix to the model name if not already present
            model_name = params.get("model", "")
            if model_name and not any(
                model_name.startswith(prefix) for prefix in model_prefix.values()
            ):
                params["model"] = model_prefix[self.embedder_type] + model_name

            return LiteLLMEmbedder(params)

        # Use local embedders
        elif self.embedder_type == "litellm":
            # Direct use of LiteLLM embedder
            return LiteLLMEmbedder(self.embedder_params)
        else:
            raise ValueError(
                f"Unsupported embedder type: {self.embedder_type}"
            ) from None

    def embed_text(self, text: str) -> List[float]:
        """
        Embed a single text string.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding.
        """
        if not text:
            # Return a zero vector of the correct dimension
            dim = self.embedder.get_embedding_dimension()
            return [0.0] * dim

        # Embed the text
        embedding = self.embedder.embed_text(text)

        # Normalize if requested
        if self.normalize:
            embedding = self.embedder.normalize_embedding(embedding)

        return embedding

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple text strings.

        Args:
            texts: The texts to embed.

        Returns:
            A list of embeddings, where each embedding is a list of floats.
        """
        if not texts:
            return []

        # Embed the texts
        embeddings = self.embedder.embed_texts(texts)

        # Normalize if requested
        if self.normalize:
            embeddings = self.embedder.normalize_embeddings(embeddings)

        return embeddings

    def embed_chunks(self, chunks: List[str]) -> List[List[float]]:
        """
        Embed a list of text chunks.

        Args:
            chunks: The text chunks to embed.

        Returns:
            A list of embeddings, where each embedding is a list of floats.
        """
        return self.embed_texts(chunks)

    def embed_file_chunks(
        self, file_chunks: List[Tuple[str, List[str]]]
    ) -> Dict[str, List[List[float]]]:
        """
        Embed chunks from multiple files.

        Args:
            file_chunks: A list of tuples containing (file_path, chunks).

        Returns:
            A dictionary mapping file paths to lists of embeddings.
        """
        result = {}

        for file_path, chunks in file_chunks:
            # Embed the chunks for this file
            embeddings = self.embed_chunks(chunks)

            # Add to the result
            result[file_path] = embeddings

        return result

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of the embeddings produced by this embedder.

        Returns:
            The dimension of the embeddings.
        """
        return self.embedder.get_embedding_dimension()

    def cosine_similarity(
        self, embedding1: List[float], embedding2: List[float]
    ) -> float:
        """
        Calculate the cosine similarity between two embeddings.

        Args:
            embedding1: The first embedding.
            embedding2: The second embedding.

        Returns:
            The cosine similarity between the embeddings.
        """
        return self.embedder.cosine_similarity(embedding1, embedding2)

    def search_similar(
        self,
        query_embedding: List[float],
        embeddings: List[List[float]],
        top_k: int = 5,
    ) -> List[Tuple[int, float]]:
        """
        Search for the most similar embeddings to a query embedding.

        Args:
            query_embedding: The query embedding.
            embeddings: The embeddings to search.
            top_k: The number of results to return.

        Returns:
            A list of tuples containing (index, similarity score).
        """
        if not embeddings:
            return []

        # Calculate similarities
        similarities = [
            self.cosine_similarity(query_embedding, embedding)
            for embedding in embeddings
        ]

        # Sort by similarity (descending)
        sorted_indices = np.argsort(similarities)[::-1]

        # Get the top-k results
        top_k_indices = sorted_indices[:top_k]

        # Return the indices and scores
        return [(int(idx), similarities[idx]) for idx in top_k_indices]
