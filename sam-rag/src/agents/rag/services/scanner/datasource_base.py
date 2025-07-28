from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from solace_ai_connector.common.log import log as logger


# Abstract base class for data sources
class DataSource(ABC):
    """
    Abstract base class for data sources.
    """

    def __init__(self, config: Dict):
        """
        Initialize the DataSource with the given configuration.

        Args:
            config: A dictionary containing the configuration.
        """
        self.config = config
        self.formats = []
        self.max_file_size = None
        self.use_memory_storage = False
        self.batch = False
        self.ingested_documents = []
        self.pipeline = None

    @abstractmethod
    def process_config(self, source: Dict = {}) -> None:
        """
        Process the source configuration.

        Args:
            source: A dictionary containing the source configuration.
        """
        pass

    @abstractmethod
    def scan(self) -> None:
        """
        Monitor changes in the data source.

        This method should be implemented by concrete data source classes.
        """
        pass

    @abstractmethod
    def upload_files(self, documents) -> None:
        """
        Upload files to the data source.

        Args:
            documents: A list of documents to upload.
        """
        pass

    def get_tracked_files(self) -> List[Dict[str, Any]]:
        """
        Get all tracked files.

        Returns:
            A list of tracked files with their metadata.
        """
        return []

    def is_valid_file_format(
        self, file_name: str, mime_type: Optional[str] = None
    ) -> bool:
        """
        Check if the file format is valid based on configured filters.

        Args:
            file_name: The name of the file.
            mime_type: Optional MIME type of the file.

        Returns:
            True if the file format is valid, False otherwise.
        """
        if not self.formats:
            return True

        # Check file extension
        return any(file_name.lower().endswith(fmt.lower()) for fmt in self.formats)

    def is_valid_file_size(self, file_size: int) -> bool:
        """
        Check if the file size is within the configured limit.

        Args:
            file_size: The size of the file in bytes.

        Returns:
            True if the file size is valid, False otherwise.
        """
        if self.max_file_size is None:
            return True

        # Convert max_file_size from KB to bytes
        max_size_bytes = self.max_file_size * 1024
        return file_size <= max_size_bytes

    def is_cloud_uri(self, path: str) -> bool:
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

    def extract_file_metadata(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """
        Extract metadata from a file.

        Args:
            file_path: The path to the file.
            **kwargs: Additional metadata.

        Returns:
            A dictionary containing file metadata.
        """
        import os
        from datetime import datetime

        metadata = {
            "file_path": file_path,
            "file_name": os.path.basename(file_path)
            if "/" in file_path or "\\" in file_path
            else file_path,
            "source_type": self.__class__.__name__.lower().replace("datasource", ""),
            "ingested_at": datetime.now().isoformat(),
        }

        # Add any additional metadata
        metadata.update(kwargs)

        return metadata

    @abstractmethod
    def batch_scan(self) -> None:
        """
        Perform batch scanning of all files in the data source.

        This method should be implemented by concrete data source classes.
        """
        pass

    def _track_file(
        self,
        file_path: str,
        file_name: str,
        status: str,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """
        Track a file in the appropriate storage backend.

        Args:
            file_path: The path to the file.
            file_name: The name of the file.
            status: The status of the file (new, modified, deleted).
            metadata: Additional metadata for the file.
        """
        try:
            if self.use_memory_storage:
                from ..memory.memory_storage import memory_storage

                memory_storage.insert_document(
                    path=file_path, file=file_name, status=status, **(metadata or {})
                )
                logger.info(f"File tracked in memory: {file_path}")
            else:
                # Try to use database storage
                try:
                    from ..database.connect import get_db, insert_document

                    insert_document(
                        get_db(),
                        status=status,
                        path=file_path,
                        file=file_name,
                    )
                    logger.info(f"File tracked in database: {file_path}")
                except ImportError:
                    logger.warning(
                        "Database not available, falling back to memory storage"
                    )
                    from ..memory.memory_storage import memory_storage

                    memory_storage.insert_document(
                        path=file_path,
                        file=file_name,
                        status=status,
                        **(metadata or {}),
                    )
        except Exception as e:
            logger.error(f"Error tracking file {file_path}: {str(e)}")
