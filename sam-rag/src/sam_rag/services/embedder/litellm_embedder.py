"""
LiteLLM-based embedder that supports multiple embedding providers.
"""

from typing import Dict, Any, List, Optional

from sam_rag.services.embedder.embedder_base import EmbedderBase


class LiteLLMEmbedder(EmbedderBase):
    """
    Embedder using the LiteLLM library to support multiple embedding providers.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the LiteLLM embedder.

        Args:
            config: A dictionary containing configuration parameters.
                - model: The model to use (e.g., "openai/text-embedding-ada-002", "azure/text-embedding-ada-002").
                - api_key: The API key for the provider.
                - api_base: The base URL for the API (optional).
                - api_version: The API version (optional, for Azure).
                - dimensions: The dimensions of the embeddings (optional).
                - batch_size: The batch size to use (default: 32).
                - additional_kwargs: Additional keyword arguments to pass to the embedding API.
        """
        super().__init__(config)
        self.model = self.config.get("model")
        if not self.model:
            raise ValueError("Model name is required for LiteLLMEmbedder") from None

        self.api_key = self.config.get("api_key")
        self.api_base = self.config.get("api_base")
        self.api_version = self.config.get("api_version")
        self.dimensions = self.config.get("dimensions")
        self.additional_kwargs = self.config.get("additional_kwargs", {})
        self.normalize = self.config.get("normalize_embeddings", True)

        # Import litellm here to avoid importing it if not needed
        try:
            import litellm

            self.litellm = litellm
        except ImportError:
            raise ImportError(
                "The litellm package is required for LiteLLMEmbedder. "
                "Please install it with `pip install litellm`."
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
            dim = self.get_embedding_dimension()
            return [0.0] * dim

        # Prepare the kwargs for the embedding API
        kwargs = self._prepare_kwargs()

        # Get the embedding from the API
        response = self.litellm.embedding(model=self.model, input=[text], **kwargs)

        # Extract the embedding
        embedding = response["data"][0]["embedding"]

        return embedding

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of text strings.

        Args:
            texts: The texts to embed.

        Returns:
            A list of embeddings, where each embedding is a list of floats.
        """
        if not texts:
            return []

        # Filter out empty texts
        non_empty_indices = [i for i, text in enumerate(texts) if text]
        non_empty_texts = [texts[i] for i in non_empty_indices]

        if not non_empty_texts:
            # Return zero vectors of the correct dimension
            dim = self.get_embedding_dimension()
            return [[0.0] * dim for _ in texts]

        # Prepare the kwargs for the embedding API
        kwargs = self._prepare_kwargs()

        # Get the embeddings from the API
        response = self.litellm.embedding(
            model=self.model, input=non_empty_texts, **kwargs
        )

        # Extract the embeddings
        embeddings = [data["embedding"] for data in response["data"]]

        # Reinsert zero vectors for empty texts
        result = []
        non_empty_idx = 0
        for i in range(len(texts)):
            if i in non_empty_indices:
                result.append(embeddings[non_empty_idx])
                non_empty_idx += 1
            else:
                # Add a zero vector of the correct dimension
                dim = (
                    len(embeddings[0]) if embeddings else self.get_embedding_dimension()
                )
                result.append([0.0] * dim)

        return result

    def _prepare_kwargs(self) -> Dict[str, Any]:
        """
        Prepare the keyword arguments for the embedding API.

        Returns:
            A dictionary of keyword arguments.
        """
        kwargs = {}

        # Add API key if provided
        if self.api_key:
            kwargs["api_key"] = self.api_key

        # Add API base URL if provided
        if self.api_base:
            kwargs["api_base"] = self.api_base

        # Add API version if provided (for Azure)
        if self.api_version:
            kwargs["api_version"] = self.api_version

        # Add dimensions if provided
        if self.dimensions:
            kwargs["dimensions"] = self.dimensions

        # Add any additional kwargs
        kwargs.update(self.additional_kwargs)

        return kwargs
