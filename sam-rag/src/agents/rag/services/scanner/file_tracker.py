from __future__ import annotations

from typing import List, Dict, Any
from solace_ai_connector.common.log import log as logger

from .file_system import LocalFileSystemDataSource
from .cloud_storage import CloudStorageDataSource
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
    Class to track file changes from different data sources.
    """

    def __init__(self, config: Dict, pipeline):
        """
        Initialize the FileChangeTracker with the given configuration.

        Args:
            config: A dictionary containing the configuration.
        """
        self.pipeline = pipeline
        self.scanner_config = config.get("scanner", {})
        self.vector_db_config = config.get("vector_db", {})
        self.data_source = None
        self.use_memory_storage = self.scanner_config.get("use_memory_storage", False)
        self.batch = self.scanner_config.get("batch", False)

        # Initialize vector database service to check for existing documents
        self.vector_db = VectorDBService(self.vector_db_config)
        self._create_handlers()

    def _create_handlers(self) -> None:
        # If using database, connect to it
        if not self.use_memory_storage and DATABASE_AVAILABLE:
            db_config = self.scanner_config.get("database", {})
            if not db_config:
                logger.warning(
                    "Database configuration is missing, using memory storage"
                )
                self.use_memory_storage = True
            else:
                connect(db_config)

        # Get data source configuration
        source_config = self.scanner_config.get("source", {})
        if not source_config:
            raise ValueError("Source configuration is missing") from None

        # Set memory storage flag in source config
        source_config["use_memory_storage"] = self.use_memory_storage
        source_config["batch"] = self.batch

        # Get existing source documents from vector database
        ingested_documents = self.get_ingested_documents()

        # Create data source based on type
        source_type = source_config.get("type", "filesystem")
        if source_type == "filesystem":
            self.data_source = LocalFileSystemDataSource(
                source_config, ingested_documents, self.pipeline
            )
        elif source_type == "cloud":
            self.data_source = CloudStorageDataSource(
                source_config, ingested_documents, self.pipeline
            )
        else:
            raise ValueError(f"Invalid data source type: {source_type}") from None

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
                if "metadata" in result and "source" in result["metadata"]:
                    sources.add(result["metadata"]["source"])

            logger.info(f"Found {len(sources)} existing documents in vector database")
            return list(sources)
        except Exception as e:
            logger.warning(
                f"Error getting source documents from vector database: {str(e)}"
            )
            return []

    def scan(self) -> None:
        """
        Detect added, removed, and changed files.

        Returns:
            A dictionary containing the scan results.
        """
        self.data_source.scan()

    def upload_files(self, documents) -> str:
        """
        Upload files to the data source.

        Args:
            documents: A list of documents to upload.

        Returns:
            A string containing the upload results.
        """
        return self.data_source.upload_files(documents)

    def get_tracked_files(self) -> List[Dict[str, Any]]:
        """
        Get all tracked files.

        Returns:
            A list of tracked files with their metadata.
        """
        if self.data_source:
            return self.data_source.get_tracked_files()
        elif self.use_memory_storage:
            return memory_storage.get_all_documents()
        else:
            logger.warning("No data source available")
            return []
