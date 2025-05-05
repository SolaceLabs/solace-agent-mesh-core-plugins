"""
Base class for embedders.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
import numpy as np


class EmbedderBase(ABC):
    """
    Abstract base class for embedders.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the embedder with the given configuration.

        Args:
            config: A dictionary containing configuration parameters.
        """
        self.config = config or {}
        self.embedding_dimension = self.config.get("embedding_dimension", None)
        self.batch_size = self.config.get("batch_size", 1)

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """
        Embed a single text string.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding.
        """
        pass

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

        # Process in batches to avoid memory issues
        embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_embeddings = self._embed_batch(batch)
            embeddings.extend(batch_embeddings)

        return embeddings

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of text strings.

        Args:
            texts: The texts to embed.

        Returns:
            A list of embeddings, where each embedding is a list of floats.
        """
        # Default implementation: embed each text individually
        return [self.embed_text(text) for text in texts]

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of the embeddings produced by this embedder.

        Returns:
            The dimension of the embeddings.
        """
        if self.embedding_dimension is not None:
            return self.embedding_dimension

        # If the dimension is not specified, embed a sample text to determine it
        sample_embedding = self.embed_text("Sample text for dimension detection")
        self.embedding_dimension = len(sample_embedding)
        return self.embedding_dimension

    def normalize_embedding(self, embedding: List[float]) -> List[float]:
        """
        Normalize an embedding to unit length.

        Args:
            embedding: The embedding to normalize.

        Returns:
            The normalized embedding.
        """
        # Convert to numpy array for efficient computation
        embedding_array = np.array(embedding)

        # Calculate the L2 norm (Euclidean norm)
        norm = np.linalg.norm(embedding_array)

        # Normalize the embedding
        if norm > 0:
            normalized_embedding = embedding_array / norm
        else:
            normalized_embedding = embedding_array

        # Convert back to list
        return normalized_embedding.tolist()

    def normalize_embeddings(self, embeddings: List[List[float]]) -> List[List[float]]:
        """
        Normalize multiple embeddings to unit length.

        Args:
            embeddings: The embeddings to normalize.

        Returns:
            The normalized embeddings.
        """
        return [self.normalize_embedding(embedding) for embedding in embeddings]

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
        # Convert to numpy arrays for efficient computation
        embedding1_array = np.array(embedding1)
        embedding2_array = np.array(embedding2)

        # Calculate the dot product
        dot_product = np.dot(embedding1_array, embedding2_array)

        # Calculate the L2 norms
        norm1 = np.linalg.norm(embedding1_array)
        norm2 = np.linalg.norm(embedding2_array)

        # Calculate the cosine similarity
        if norm1 > 0 and norm2 > 0:
            similarity = dot_product / (norm1 * norm2)
        else:
            similarity = 0.0

        return float(similarity)
