"""The ingestion agent component for the rag"""

import logging
import os
import sys
import threading
from typing import Dict, List, Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(SCRIPT_DIR))

# Adding imports for file tracking and ingestion functionality
from sam_rag.services.ingestor.ingestion_service import IngestionService
from sam_rag.services.scanner.file_tracker import FileChangeTracker

# Add new imports for the RAG pipeline
from sam_rag.services.preprocessor.preprocessor_service import PreprocessorService
from sam_rag.services.splitter.splitter_service import SplitterService
from sam_rag.services.embedder.embedder_service import EmbedderService
from sam_rag.services.rag.augmentation_service import AugmentationService

log = logging.getLogger(__name__)

class Pipeline:

    def __init__(self, config, **kwargs):
        """Initialize the rag agent component.

        Args:
            config: The component configuration.
            **kwargs: Additional keyword arguments.

        Raises:
            ValueError: If required database configuration is missing.
        """

        self.component_config = config
        self._hybrid_search_config = self.component_config.get("hybrid_search", {})
        # Store host_component explicitly for access by data sources
        self.host_component = config.get("host_component")

        # Initialize handlers
        self.ingestion_handler = None
        self.file_tracker = None
        self.preprocessing_handler = None
        self.embedding_handler = None
        self.splitting_handler = None
        self.augmentation_handler = None
        self.use_memory_storage = False
        self.batch_mode = False
        # Create handlers
        self._create_handlers()

        # Run the ingestion pipeline in a separate thread
        self.ingestion_thread = threading.Thread(target=self._run)
        self.ingestion_thread.daemon = (
            True  # Set as daemon so it exits when main thread exits
        )
        self.ingestion_thread.start()
        log.info(f"Started ingestion pipeline on background")

    def _run(self):
        """Ingest documents into the vector database."""
        log.info("=== PIPELINE: Starting _run method ===")
        log.info("PIPELINE: Starting document ingestion process")
        log.info(f"PIPELINE: File tracker state: {self.file_tracker is not None}")

        if self.batch_mode:
            log.info("PIPELINE: Batch mode is enabled, proceeding with scan...")
            # Scan for file changes
            self._scan_files()

            # Get new/modified/deleted files
            files = self._get_tracked_files()
            log.info(f"PIPELINE: Found {len(files) if files else 0} files to process")

        else:
            log.error("PIPELINE: No file tracker is initialized.")

        log.info("=== PIPELINE: Finished _run method ===")

    def process_files(
        self, file_paths: List[str], metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Process files through a complete RAG pipeline: preprocess, chunk, embed, and ingest.

        Args:
            file_paths: List of file paths to process.
            metadata: Optional metadata to merge with file metadata for cloud storage files.

        Returns:
            A dictionary containing the processing results.
        """
        log.info(f"Processing {len(file_paths)} files through the RAG pipeline")

        # Step 1: Preprocess files
        preprocessed_docs = []
        preprocessed_metadata = []

        for i, file_path in enumerate(file_paths):
            try:
                # Handle both cloud URIs and local files
                if self._is_cloud_uri(file_path):
                    # Cloud file - should already be downloaded to temp location by cloud provider
                    log.debug(f"Processing cloud file: {file_path}")
                else:
                    # Local file - verify it exists
                    if not os.path.exists(file_path):
                        log.warning(f"Local file not found: {file_path}")
                        continue

                # Get the document type
                doc_type = self._get_file_type(file_path)

                # Process the file with the appropriate preprocessor config
                # The preprocessor service will select the right preprocessor based on file type
                preprocess_output = self.preprocessing_handler.preprocess_file(
                    file_path
                )
                text = preprocess_output.get("text_content", None)
                file_metadata = preprocess_output.get("metadata", {})

                # Merge provided metadata with file metadata (provided metadata takes precedence)
                if metadata:
                    merged_metadata = file_metadata.copy()
                    merged_metadata.update(metadata)
                    # Ensure the file_path is preserved from the provided metadata if it exists
                    if "file_path" in metadata:
                        merged_metadata["file_path"] = metadata["file_path"]
                        # Use the cloud URI as the source for consistency
                        source_path = metadata["file_path"]
                    else:
                        source_path = file_path
                    
                    # Ensure artifact_url is preserved if it exists in the provided metadata
                    if "artifact_url" in metadata:
                        merged_metadata["artifact_url"] = metadata["artifact_url"]
                        log.info(f"Preserved artifact URL in metadata: {metadata['artifact_url']}")
                else:
                    merged_metadata = file_metadata
                    source_path = file_path

                if text:
                    preprocessed_docs.append(text)
                    preprocessed_metadata.append(
                        {
                            "source": source_path,
                            "metadata": merged_metadata,
                        }
                    )
                    log.info("Successfully preprocessed a file.")
                else:
                    log.warning("Failed to preprocess a file.")
            except Exception as e:
                log.error(f"Error preprocessing file {file_path}.", trace=e)

        if not preprocessed_docs:
            log.warning("No documents were successfully preprocessed")
            return {
                "success": False,
                "message": "No documents were successfully preprocessed",
                "document_ids": [],
            }

        # Refit the sparse model if hybrid search is enabled, using all preprocessed document texts
        if (
            self.embedding_handler
            and hasattr(self.embedding_handler, "hybrid_search_enabled")
            and self.embedding_handler.hybrid_search_enabled
        ):
            log.info(
                "Pipeline: Hybrid search is enabled. Refitting sparse model with actual corpus documents."
            )
            log.debug(
                f"[HYBRID_SEARCH_DEBUG] Refitting sparse model with {len(preprocessed_docs)} actual corpus documents"
            )
            # Use the new refit method that combines sample corpus with actual documents
            if hasattr(self.embedding_handler, "refit_sparse_model_with_corpus"):
                self.embedding_handler.refit_sparse_model_with_corpus(preprocessed_docs)
            else:
                # Fallback to original method for backward compatibility
                self.embedding_handler.fit_sparse_model(preprocessed_docs)
        else:
            log.info(
                "Pipeline: Hybrid search is disabled or embedding_handler is not configured for it. Skipping sparse model fitting."
            )

        # Step 2: Split documents into chunks
        chunks = []
        chunks_metadata = []

        for i, (doc, data) in enumerate(zip(preprocessed_docs, preprocessed_metadata)):
            try:
                # Get the metadata
                meta = data.get("metadata", {})
                # Get the document type
                doc_type = meta.get("file_type", "text")

                # Split the document
                doc_chunks = self.splitting_handler.split_text(doc, doc_type)

                # Add chunks and metadata
                chunks.extend(doc_chunks)
                chunks_metadata.extend([meta.copy() for _ in range(len(doc_chunks))])

                log.info(f"Split a document into {len(doc_chunks)} chunks")
            except Exception:
                log.error("Error splitting a document")

        if not chunks:
            log.warning("No chunks were created from the documents")
            return {
                "success": False,
                "message": "No chunks were created from the documents",
                "document_ids": [],
            }

        # Step 3: Embed chunks
        try:
            embeddings = self.embedding_handler.embed_texts(chunks)
            log.info(f"Created {len(embeddings)} embeddings")
        except Exception as e:
            log.error("Error embedding chunks.", trace=e)
            return {
                "success": False,
                "message": "Error embedding chunks.",
                "document_ids": [],
            }

        # Step 4: Ingest embeddings into vector database
        try:
            # Use the ingestion handler to store the embeddings
            result = self.ingestion_handler.ingest_embeddings(
                texts=chunks, embeddings=embeddings, metadata=chunks_metadata
            )
            log.info(f"Ingestion result: {result['message']}")
            return result
        except Exception as e:
            log.error(f"Error ingesting embeddings.", trace=e)
            return {
                "success": False,
                "message": "Error ingesting embeddings.",
                "document_ids": [],
            }

    def _is_cloud_uri(self, path: str) -> bool:
        """
        Check if path is a cloud URI for any provider.

        Args:
            path: The file path to check.

        Returns:
            True if the path is a cloud URI, False otherwise.
        """
        cloud_prefixes = [
            "google_drive://",
            "gdrive://",
            "onedrive://",
            "od://",
            "s3://",
            "aws://",
            "gcs://",
            "gs://",
            "azure://",
            "az://",
            "dropbox://",
            "db://",
        ]
        return any(path.startswith(prefix) for prefix in cloud_prefixes)

    def _get_file_type(self, file_path: str) -> str:
        """
        Get the file type from a file path.

        Args:
            file_path: Path to the file.

        Returns:
            The file type (e.g., "pdf", "text", "html").
        """
        _, ext = os.path.splitext(file_path.lower())
        return ext[1:] if ext else "text"  # Remove the leading dot

    def _get_tracked_files(self) -> List[Dict[str, Any]]:
        """
        Get all tracked files from the file tracker.

        Returns:
            A list of tracked files with their metadata.
        """
        if self.file_tracker:
            try:
                files = []
                tracked_files = self.file_tracker.get_tracked_files()
                for i, file in enumerate(tracked_files):
                    file_path = file.get("path", None)  # Get the file path
                    if not file_path:
                        log.warning(f"Invalid file path: {file}")
                        continue

                    # Handle both cloud URIs and local files
                    if self._is_cloud_uri(file_path):
                        # Cloud files don't need local existence check
                        log.debug(f"Cloud file detected: {file_path}")
                    else:
                        # Local files need existence check
                        if not os.path.exists(file_path):
                            log.warning(f"Local file not found: {file_path}")
                            continue

                    file_status = file.get("status", None)  # Get the file status
                    if file_status not in {"modified", "new"}:
                        continue

                    files.append(file_path)
                return files
            except Exception as e:
                log.error("Error getting tracked files.", trace=e)
                return []

    def _scan_files(self) -> Dict[str, List[str]]:
        """
        Scan for file changes using the file tracker.

        Returns:
            A dictionary containing the scan results.
        """
        if self.file_tracker:
            return self.file_tracker.scan()
        else:
            log.warning("Scanner module not available or file tracker not initialized")
            return {"added": [], "removed": [], "changed": []}

    def _create_handlers(self):
        """Create handlers for the agent."""
        log.info("=== PIPELINE: Starting _create_handlers ===")

        # Initialize the ingestion handler
        self.ingestion_handler = IngestionService(
            config=self.component_config,
            hybrid_search_config=self._hybrid_search_config,
        )
        log.info("PIPELINE: Ingestion handler initialized")

        # Initialize the file tracker
        scanner_config = self.component_config.get("scanner", {})
        log.info(f"PIPELINE: Scanner config found: {bool(scanner_config)}")
        log.info(
            f"PIPELINE: Scanner config keys: {list(scanner_config.keys()) if scanner_config else 'None'}"
        )

        if scanner_config:
            # Check if batch mode is enabled
            self.batch_mode = scanner_config.get("batch", False)
            log.info(f"PIPELINE: Batch mode: {self.batch_mode}")

            has_valid_source = False
            if self.batch_mode:
                # Support both new 'sources' array format and legacy 'source' format
                sources_config = scanner_config.get("sources", [])

                log.info(f"PIPELINE: Final sources_config length: {len(sources_config)}")

                # Check if any source has valid configuration
                for i, source in enumerate(sources_config):
                    source_type = source.get("type", "filesystem")
                    log.info(f"PIPELINE: Checking source {i} of type '{source_type}'")

                    if source_type == "filesystem" and "directories" in source:
                        directories = source.get("directories", [])
                        log.info(
                            f"PIPELINE: Filesystem source has {len(directories)} directories"
                        )
                        if directories:
                            has_valid_source = True
                            log.info("PIPELINE: Valid filesystem source found")
                            # Continue processing other sources instead of breaking
                    elif source_type in ["google_drive", "onedrive", "s3", "cloud"]:
                        # Cloud sources don't need directories
                        log.info(f"PIPELINE: Cloud source '{source_type}' found")
                        has_valid_source = True
                        # Continue processing other sources instead of breaking
                    else:
                        log.info(
                            f"PIPELINE: Unknown source type '{source_type}' - skipping"
                        )

                log.info(f"PIPELINE: Has valid source: {has_valid_source}")

            # If batch mode is disabled, we can proceed without valid sources
            if has_valid_source or not self.batch_mode:
                try:
                    log.info("PIPELINE: Attempting to create FileChangeTracker...")
                    self.file_tracker = FileChangeTracker(self.component_config, self)
                    self.use_memory_storage = scanner_config.get(
                        "use_memory_storage", False
                    )
                    
                    if has_valid_source:
                        log.info(
                            f"PIPELINE: File tracker initialized successfully with {len(sources_config)} source(s) using "
                            + (
                                "memory storage"
                                if self.use_memory_storage
                                else "database storage"
                            )
                        )
                    else:
                        log.info(
                            f"PIPELINE: File tracker initialized without sources (batch mode disabled) using "
                            + (
                                "memory storage"
                                if self.use_memory_storage
                                else "database storage"
                            )
                        )
                except Exception as e:
                    log.error("PIPELINE: Failed to initialize file tracker.", trace=e)
                    import traceback

                    log.error(f"PIPELINE: Traceback: {traceback.format_exc()}")
                    self.file_tracker = None
            else:
                log.error("PIPELINE: No valid sources configured for file tracking and batch mode is enabled.")
                raise ValueError(
                    "No valid sources configured for file tracking and batch mode is enabled. "
                    "Please check your scanner configuration."
                )
        else:
            log.error("PIPELINE: No scanner configuration provided.")
            raise ValueError(
                "No scanner configuration provided. Please check your component configuration."
            )

        log.info(f"PIPELINE: File tracker final state: {self.file_tracker is not None}")
        log.info("=== PIPELINE: Finished _create_handlers ===")

        # Initialize the preprocessing handler
        preprocessor_config = self.component_config.get("preprocessor", {})
        default_preprocessor = preprocessor_config.get("default_preprocessor", {})
        file_specific_preprocessors = preprocessor_config.get("preprocessors", {})

        # Log the extracted configuration for debugging
        log.debug(f"Using default preprocessor config: {default_preprocessor}")
        log.debug(
            f"Using file-specific preprocessor configs: {file_specific_preprocessors}"
        )

        # Initialize pipeline components with configuration from params
        self.preprocessing_handler = PreprocessorService(
            {
                "default_preprocessor": default_preprocessor,
                "preprocessors": file_specific_preprocessors,
            }
        )

        # Initialize the splitter handlers
        splitter_config = self.component_config.get("splitter", {})
        self.splitting_handler = SplitterService(splitter_config)

        # Initialize the embedding handler
        embedder_config = self.component_config.get("embedding", {})
        self.embedding_handler = EmbedderService(
            config=embedder_config, hybrid_search_config=self._hybrid_search_config
        )

        # Initialize the augmentation handler
        # Pass host_component from config to AugmentationService
        self.augmentation_handler = AugmentationService(
            config=self.component_config,
            hybrid_search_config=self._hybrid_search_config,
        )

    def get_agent_summary(self):
        """Get a summary of the agent's capabilities."""
        return {
            "agent_name": self.agent_name,
            "description": f"This agent ingests documents and retrieves relevant information.\n",
            "detailed_description": (
                "This agent ingests various types of documents in a vector database and retrieves relevant information.\n\n"
            ),
            "always_open": self.info.get("always_open", False),
            "actions": self.get_actions_summary(),
        }

    def get_ingestion_handler(self):
        """Get the ingestion handler."""
        return self.ingestion_handler

    def get_file_tracker(self):
        """Get the file tracker."""
        return self.file_tracker

    def get_preprocessor_handler(self):
        """Get the preprocessor handler."""
        return self.preprocessing_handler

    def get_embedding_handler(self):
        """Get the embedding handler."""
        return self.embedding_handler

    def get_splitting_handler(self):
        """Get the splitting handler."""
        return self.splitting_handler

    def get_augmentation_handler(self):
        """Get the augmentation handler."""
        return self.augmentation_handler
        
    def cleanup(self):
        """Clean up resources used by the pipeline."""
        log.info("=== PIPELINE: Starting cleanup ===")
        
        # Clean up file tracker resources
        if self.file_tracker:
            log.info("PIPELINE: Cleaning up file tracker resources")
            # No specific cleanup method for file tracker currently
            
        # Clean up vector database connections
        if self.ingestion_handler:
            log.info("PIPELINE: Cleaning up ingestion handler resources")
            if hasattr(self.ingestion_handler, "cleanup"):
                self.ingestion_handler.cleanup()
                
        # Clean up embedding handler resources
        if self.embedding_handler:
            log.info("PIPELINE: Cleaning up embedding handler resources")
            if hasattr(self.embedding_handler, "cleanup"):
                self.embedding_handler.cleanup()
                
        log.info("=== PIPELINE: Cleanup completed ===")
