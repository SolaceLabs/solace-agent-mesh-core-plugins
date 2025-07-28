from __future__ import annotations

from typing import List, Dict, Any, Union
from solace_ai_connector.common.log import log as logger

from .file_system import LocalFileSystemDataSource
from .cloud_storage import CloudStorageDataSource
from .cloud_provider_factory import CloudProviderFactory
from ..memory.memory_storage import memory_storage
from ..database.vector_db_service import VectorDBService


# Try to import database modules, but don't fail if they're not available
try:
    from ..database.connect import connect

    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False


# Class to track file changes
class FileChangeTracker:
    """
    Class to track file changes from multiple data sources.

    Supports both single and multiple data source configurations for
    backward compatibility and enhanced functionality.
    """

    def __init__(self, config: Dict, pipeline):
        """
        Initialize the FileChangeTracker with the given configuration.

        Args:
            config: A dictionary containing the configuration.
            pipeline: The processing pipeline instance.
        """
        logger.info("=== FILE_TRACKER: Starting initialization ===")
        self.pipeline = pipeline
        self.scanner_config = config.get("scanner", {})
        self.vector_db_config = config.get("vector_db", {})
        self.data_sources = []  # Support multiple data sources
        self.use_memory_storage = self.scanner_config.get("use_memory_storage", False)
        self.batch = self.scanner_config.get("batch", False)

        logger.info(
            f"FILE_TRACKER: Scanner config keys: {list(self.scanner_config.keys())}"
        )
        logger.info(f"FILE_TRACKER: use_memory_storage: {self.use_memory_storage}")
        logger.info(f"FILE_TRACKER: batch: {self.batch}")

        # Initialize vector database service to check for existing documents
        logger.info("FILE_TRACKER: Initializing vector database service...")
        self.vector_db = VectorDBService(self.vector_db_config)
        logger.info("FILE_TRACKER: Vector database service initialized")

        logger.info("FILE_TRACKER: Calling _create_handlers...")
        self._create_handlers()
        logger.info("=== FILE_TRACKER: Initialization complete ===")

    def _create_handlers(self) -> None:
        """Create handlers for multiple data sources."""
        logger.info("=== FILE_TRACKER: Starting _create_handlers ===")

        # If using database, connect to it
        if not self.use_memory_storage and DATABASE_AVAILABLE:
            db_config = self.scanner_config.get("database", {})
            logger.info(f"FILE_TRACKER: Database config found: {bool(db_config)}")
            if not db_config:
                logger.warning(
                    "FILE_TRACKER: Database configuration is missing, using memory storage"
                )
                self.use_memory_storage = True
            else:
                logger.info("FILE_TRACKER: Connecting to database...")
                connect(db_config)
                logger.info("FILE_TRACKER: Database connected")

        # Support multiple sources (new format) or single source (backward compatibility)
        sources_config = self.scanner_config.get("sources", [])
        logger.info(
            f"FILE_TRACKER: Found 'sources' config: {len(sources_config)} sources"
        )

        if not sources_config:
            # Fallback to single source for backward compatibility
            source_config = self.scanner_config.get("source", {})
            logger.info(
                f"FILE_TRACKER: Fallback to 'source' config: {bool(source_config)}"
            )
            if source_config:
                sources_config = [source_config]
                logger.info("FILE_TRACKER: Converted single source to sources array")
            else:
                logger.error("FILE_TRACKER: No source configuration found")
                raise ValueError("No source configuration found") from None

        logger.info(
            f"FILE_TRACKER: Final sources_config: {len(sources_config)} sources"
        )
        for i, source in enumerate(sources_config):
            logger.info(
                f"FILE_TRACKER: Source {i}: type='{source.get('type', 'unknown')}', keys={list(source.keys())}"
            )

        # Get existing source documents from vector database
        logger.info("FILE_TRACKER: Getting ingested documents from vector database...")
        ingested_documents = self.get_ingested_documents()
        logger.info(f"FILE_TRACKER: Found {len(ingested_documents)} ingested documents")

        # Create data sources
        logger.info("FILE_TRACKER: Creating data sources...")
        for i, source_config in enumerate(sources_config):
            logger.info(f"FILE_TRACKER: Processing source {i}...")

            # Set common flags in source config
            source_config["use_memory_storage"] = self.use_memory_storage
            source_config["batch"] = self.batch
            logger.info(
                f"FILE_TRACKER: Set flags - use_memory_storage: {self.use_memory_storage}, batch: {self.batch}"
            )

            logger.info(
                f"FILE_TRACKER: Creating data source for type: {source_config.get('type', 'unknown')}"
            )
            data_source = self._create_data_source(source_config, ingested_documents)
            if data_source:
                self.data_sources.append(data_source)
                logger.info(f"FILE_TRACKER: Successfully created data source {i}")
            else:
                logger.warning(f"FILE_TRACKER: Failed to create data source {i}")

        logger.info(
            f"FILE_TRACKER: Total data sources created: {len(self.data_sources)}"
        )

        if not self.data_sources:
            logger.error("FILE_TRACKER: No valid data sources could be created")
            raise ValueError("No valid data sources could be created") from None

        logger.info(
            f"FILE_TRACKER: Initialized {len(self.data_sources)} data source(s)"
        )
        logger.info("=== FILE_TRACKER: Finished _create_handlers ===")

    def _create_data_source(
        self, source_config: Dict, ingested_documents: List[str]
    ) -> Union[LocalFileSystemDataSource, CloudStorageDataSource, None]:
        """
        Create a data source based on configuration.

        Args:
            source_config: Configuration for the data source.
            ingested_documents: List of already ingested documents.

        Returns:
            A data source instance or None if creation failed.
        """
        source_type = source_config.get("type", "filesystem")
        logger.info(
            f"FILE_TRACKER: _create_data_source called with type: {source_type}"
        )
        logger.info(f"FILE_TRACKER: Source config keys: {list(source_config.keys())}")

        try:
            if source_type == "filesystem":
                logger.info("FILE_TRACKER: Creating LocalFileSystemDataSource...")
                return LocalFileSystemDataSource(
                    source_config, ingested_documents, self.pipeline
                )
            elif source_type == "cloud":
                # Legacy cloud storage (generic)
                logger.info("FILE_TRACKER: Creating CloudStorageDataSource...")
                return CloudStorageDataSource(
                    source_config, ingested_documents, self.pipeline
                )
            else:
                # Try to create using cloud provider factory
                provider_type = source_config.get("provider", source_type)
                logger.info(
                    f"FILE_TRACKER: Trying cloud provider factory for type: {provider_type}"
                )
                logger.info(
                    f"FILE_TRACKER: Available providers: {CloudProviderFactory.get_available_providers()}"
                )

                if CloudProviderFactory.is_provider_available(provider_type):
                    logger.info(
                        f"FILE_TRACKER: Provider {provider_type} is available, creating..."
                    )
                    return CloudProviderFactory.create_provider(
                        provider_type, source_config, ingested_documents, self.pipeline
                    )
                else:
                    logger.error(
                        f"FILE_TRACKER: Unsupported data source type: {source_type}, provider: {provider_type}"
                    )
                    logger.error(
                        f"FILE_TRACKER: Available providers: {CloudProviderFactory.get_available_providers()}"
                    )
                    return None

        except Exception as e:
            logger.error(
                f"FILE_TRACKER: Failed to create data source of type {source_type}: {str(e)}"
            )
            import traceback

            logger.error(f"FILE_TRACKER: Traceback: {traceback.format_exc()}")
            return None

    def get_ingested_documents(self) -> List[str]:
        """
        Get a list of source document paths from the vector database.

        Returns:
            A list of document paths that are already in the vector database.
        """
        try:
            # Use a dummy embedding to search for all documents
            # We'll use a large number to get all documents
            # The actual similarity doesn't matter since we just want to extract metadata
            dimension = self.vector_db_config.get("db_params").get(
                "embedding_dimension", 768
            )
            dummy_embedding = [0.0] * dimension
            results = self.vector_db.search(
                query_embedding=dummy_embedding, top_k=10000
            )

            # Extract source paths from metadata
            sources = set()
            for result in results:
                if "metadata" in result and "file_path" in result["metadata"]:
                    sources.add(result["metadata"]["file_path"])

            logger.info(f"Found {len(sources)} existing documents in vector database")
            return list(sources)
        except Exception as e:
            logger.warning(
                f"Error getting source documents from vector database: {str(e)}"
            )
            return []

    def scan(self) -> None:
        """
        Detect added, removed, and changed files across all data sources.
        """
        logger.info(f"Starting scan across {len(self.data_sources)} data source(s)")

        # Log details about each data source before scanning
        for i, data_source in enumerate(self.data_sources):
            logger.info(
                f"Data source {i}: {type(data_source).__name__} - Provider: {getattr(data_source, 'provider_name', 'N/A')}"
            )

        for i, data_source in enumerate(self.data_sources):
            try:
                logger.info(
                    f"Scanning data source {i+1}/{len(self.data_sources)}: {type(data_source).__name__}"
                )
                logger.info(
                    f"Data source batch mode: {getattr(data_source, 'batch', 'N/A')}"
                )
                logger.info(f"About to call scan() on data source {i+1}")
                data_source.scan()
                logger.info(f"Successfully completed scanning data source {i+1}")
            except Exception as e:
                logger.error(f"Error scanning data source {i+1}: {str(e)}")
                import traceback

                logger.error(f"Traceback: {traceback.format_exc()}")
                # Continue with next data source even if this one fails
                logger.info(f"Continuing to next data source despite error in {i+1}")
            finally:
                logger.info(f"Finished processing data source {i+1}, moving to next")

        logger.info("Completed scanning all data sources")

    def upload_files(self, documents) -> str:
        """
        Upload files to the first available data source that supports uploads.

        Args:
            documents: A list of documents to upload.

        Returns:
            A string containing the upload results.
        """
        if not self.data_sources:
            return "No data sources available for upload"

        # Try to upload to the first data source
        # In the future, this could be enhanced to support target-specific uploads
        try:
            return self.data_sources[0].upload_files(documents)
        except Exception as e:
            logger.error(f"Error uploading files: {str(e)}")
            return f"Upload failed: {str(e)}"

    def get_tracked_files(self) -> List[Dict[str, Any]]:
        """
        Get all tracked files from all data sources.

        Returns:
            A list of tracked files with their metadata.
        """
        all_files = []

        if self.data_sources:
            for data_source in self.data_sources:
                try:
                    files = data_source.get_tracked_files()
                    all_files.extend(files)
                except Exception as e:
                    logger.error(
                        f"Error getting tracked files from {type(data_source).__name__}: {str(e)}"
                    )
        elif self.use_memory_storage:
            all_files = memory_storage.get_all_documents()
        else:
            logger.warning("No data sources available")

        return all_files

    def get_data_sources_info(self) -> List[Dict[str, Any]]:
        """
        Get information about all configured data sources.

        Returns:
            A list of dictionaries containing data source information.
        """
        info = []
        for i, data_source in enumerate(self.data_sources):
            info.append(
                {
                    "index": i,
                    "type": type(data_source).__name__,
                    "provider": getattr(data_source, "provider_name", "unknown"),
                    "config": {
                        "use_memory_storage": data_source.use_memory_storage,
                        "batch": data_source.batch,
                        "formats": data_source.formats,
                        "max_file_size": data_source.max_file_size,
                    },
                }
            )
        return info

    # Backward compatibility - maintain single data source interface
    @property
    def data_source(self):
        """
        Get the first data source for backward compatibility.

        Returns:
            The first data source or None if no data sources exist.
        """
        return self.data_sources[0] if self.data_sources else None
