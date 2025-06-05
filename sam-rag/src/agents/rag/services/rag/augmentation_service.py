"""
Implementation of an augmentor component for RAG systems.

This module provides functionality to augment retrieved documents by:
1. Retrieving relevant chunks from a vector database
2. Merging chunks from the same source document
3. Using an LLM to clean and improve the content
4. Returning improved content with source information
"""

from typing import Dict, Any, List, Optional
import time
from collections import defaultdict
import litellm
from solace_ai_connector.common.log import log as logger
from solace_agent_mesh.services.file_service.file_service import FileService

from .retriever import Retriever


class AugmentationService:
    """
    Augmention service for RAG systems that enhances retrieved content.
    """

    def __init__(
        self,
        config: Dict[str, Any] = None,
        hybrid_search_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the augmentation service.

        Args:
            config: A dictionary containing configuration parameters.
                - embedding: Configuration for the embedding service.
                - vector_db: Configuration for the vector database.
                - llm: Configuration for the LLM service.
            hybrid_search_config: Optional dictionary containing hybrid search configuration.
        """
        self.config = config or {}
        self._hybrid_search_config = hybrid_search_config or {}
        # Initialize file service
        self.file_service = FileService()

        # Initialize retriever
        self.retriever = Retriever(
            config=self.config, hybrid_search_config=self._hybrid_search_config
        )
        logger.info("Augmention service initialized with retriever")

        # Initialize LiteLLM if provided in config
        self.llm_config = self.config.get("llm", {})
        self.load_balancer_config = self.llm_config.get("load_balancer", [])

        # Flag to indicate if LLM is available
        self.llm_available = len(self.load_balancer_config) > 0

        if self.llm_available:
            try:
                # Configure LiteLLM with the load balancer
                litellm.set_verbose = False
                logger.info("Augmentor initialized with LiteLLM")
            except ImportError:
                logger.warning(
                    "LiteLLM not available. Running without LLM augmentation."
                )
                self.llm_available = False

    def augment(
        self,
        query: str,
        session_id: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve and augment documents relevant to the query.

        Args:
            query: The query text.
            session_id: The session ID for tracking.
            filter: Optional filter to apply to the search.

        Returns:
            A list of dictionaries containing the augmented results, each with:
            - content: The augmented content
            - source: The source document information
            - score: The relevance score
        """
        try:
            # Retrieve relevant chunks
            retrieved_chunks = self.retriever.retrieve(query, filter=filter)

            # Merge chunks by source
            merged_chunks = self._merge_chunks_by_source(retrieved_chunks)

            # Augment merged chunks with LLM
            augmented_chunks = self._augment_chunks_with_llm(query, merged_chunks)

            # Upload files to file service
            files = self._upload_files_to_fileservice(augmented_chunks, session_id)

            # Extract content
            content = self._extract_content(augmented_chunks)

            logger.info(f"Augmented {len(augmented_chunks)} chunks for query")
            return content, files
        except Exception:
            logger.error("Error augmenting documents.")
            raise ValueError("Error augmenting documents") from None

    def _merge_chunks_by_source(
        self, chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge chunks that come from the same source document.

        Args:
            chunks: List of retrieved chunks.

        Returns:
            List of merged chunks.
        """
        # Group chunks by source
        chunks_by_source = defaultdict(list)
        for chunk in chunks:
            # Extract source from metadata
            metadata = chunk.get("metadata", {})
            source = metadata.get("file_path", "unknown")

            # Group by source
            chunks_by_source[source].append(chunk)

        # Merge chunks for each source
        merged_chunks = []
        for source, source_chunks in chunks_by_source.items():
            # Sort chunks by distance (lowest first)
            sorted_chunks = sorted(
                source_chunks, key=lambda x: x.get("distance", 0), reverse=False
            )

            # Combine text from chunks
            combined_text = "\n".join(chunk["text"] for chunk in sorted_chunks)

            # Use metadata from the highest-scoring chunk
            best_metadata = sorted_chunks[0].get("metadata", {}).copy()

            # Create merged chunk
            merged_chunk = {
                "text": combined_text,
                "metadata": best_metadata,
                "source": source,
            }

            merged_chunks.append(merged_chunk)

        return merged_chunks

    def _augment_chunks_with_llm(
        self, query: str, chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to clean and improve the content of merged chunks.

        Args:
            query: The original query.
            chunks: List of merged chunks.

        Returns:
            List of augmented chunks.
        """
        augmented_chunks = []

        for chunk in chunks:
            # Extract information
            text = chunk["text"]
            source = chunk.get("source", "unknown")
            metadata = chunk.get("metadata", {})

            # If LiteLLM is available, use it to improve the content
            if self.llm_available:
                try:
                    # Create prompt for LLM
                    prompt = self._create_augmentation_prompt(query, text)

                    # Get improved content from LLM using LiteLLM
                    response = self._invoke_litellm(prompt)
                    improved_content = response.strip()

                    logger.debug(f"Improved content with LiteLLM for source: {source}")
                except Exception as e:
                    logger.warning(f"Error using LiteLLM to improve content: {str(e)}")
                    improved_content = text  # Fall back to original text
            else:
                improved_content = text  # No LLM available

            # Create augmented chunk
            augmented_chunk = {
                "content": improved_content,
                "source": source,
                "metadata": metadata,
            }

            augmented_chunks.append(augmented_chunk)

        return augmented_chunks

    def _upload_files_to_fileservice(
        self, chunks: List[Dict[str, Any]], session_id: str
    ) -> List[Dict[str, Any]]:
        """
        Upload files to the file service and return the list of files.

        Args:
            chunks: List of chunks to upload.
            session_id: Session ID for file service access control.

        Returns:
            List of files corresponding to chunks.
        """
        files = []

        for chunk in chunks:
            # Extract source from chunk (source is a file path)
            source_path = chunk.get("source", "")
            if not source_path:
                # # Skip chunks without source
                # updated_chunks.append(chunk)
                continue

            try:
                # Upload file to file service using upload_from_file
                file_meta = self.file_service.upload_from_file(
                    source_path, session_id, data_source="Augmentation Service"
                )

                # Add URL to chunk's files data field in the required format
                if "file" not in chunk:
                    chunk["file"] = []

                chunk["file"] = file_meta

                # files.append(chunk)
                files.append(file_meta)

            except Exception as e:
                logger.error(f"Error uploading file to file service: {str(e)}")
                # If upload fails, still include the chunk without file URL
                files.append(chunk)

        return files

    def _invoke_litellm(self, prompt: str) -> str:
        """
        Invoke LiteLLM to generate text.

        Args:
            prompt: The prompt to send to the LLM.

        Returns:
            The generated text response.
        """
        try:
            start_time = time.time()

            # Prepare messages for LiteLLM
            messages = [{"role": "user", "content": prompt}]

            # Use the first model in the load balancer config
            if not self.load_balancer_config:
                raise ValueError("No LLM models configured in load balancer") from None

            model_config = self.load_balancer_config[0]
            litellm_params = model_config.get("litellm_params", {})

            # Call LiteLLM
            response = litellm.completion(
                model=litellm_params.get("model", "openai/gpt-4o"),
                messages=messages,
                api_key=litellm_params.get("api_key"),
                api_base=litellm_params.get("api_base"),
                temperature=litellm_params.get("temperature", 0.01),
                max_tokens=litellm_params.get("max_tokens", 1000),
            )

            end_time = time.time()
            processing_time = round(end_time - start_time, 3)
            logger.debug("LiteLLM processing time: %s seconds", processing_time)

            # Extract the response content
            if response and response.choices and len(response.choices) > 0:
                return response.choices[0].message.content
            else:
                logger.warning("Empty response from LiteLLM")
                return ""

        except Exception:
            logger.error("Error invoking LiteLLM.")
            raise ValueError("Error invoking LiteLLM") from None

    def _create_augmentation_prompt(self, query: str, text: str) -> str:
        """
        Create a prompt for the LLM to improve the content.

        Args:
            query: The original query.
            text: The text to be improved.

        Returns:
            The generated prompt.
        """
        return (
            f"Given the query: '{query}', please clean and improve the following content:\n\n"
            f"{text}\n\n"
            "Make sure to maintain the original meaning while enhancing clarity and coherence."
        )

    def _extract_content(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Extract contents from a list of chunks.

        Args:
            chunks: List of chunks, where each chunk is a dictionary containing 'content' and 'files' fields.

        Returns:
            A dictionary with one key:
            - 'content': A list of all content values from the chunks
        """
        content = ""

        for chunk in chunks:
            # Extract content
            if "content" in chunk:
                content += chunk["content"]

        return content
