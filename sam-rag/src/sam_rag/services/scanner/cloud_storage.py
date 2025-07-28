import os
import tempfile
import threading
import time
from abc import abstractmethod
from typing import Dict, List, Any, Optional
from solace_ai_connector.common.log import log as logger

from sam_rag.services.scanner.datasource_base import DataSource
from sam_rag.services.memory.memory_storage import memory_storage

# Try to import database modules, but don't fail if they're not available
try:
    from sam_rag.services.database.connect import get_db, insert_document, update_document, delete_document

    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False


# Abstract base class for Cloud Storage implementations
class CloudStorageDataSource(DataSource):
    """
    Abstract base class for cloud storage data sources.

    This class provides common functionality for all cloud storage providers
    while allowing specific implementations for different cloud services.
    """

    def __init__(self, config: Dict, ingested_documents: List[str], pipeline):
        """
        Initialize the CloudStorageDataSource with the given configuration.

        Args:
            config: A dictionary containing the configuration.
            ingested_documents: A list of documents that have been ingested.
            pipeline: The processing pipeline to use for the documents.
        """
        super().__init__(config)
        self.use_memory_storage = config.get("use_memory_storage", False)
        self.batch = config.get("batch", False)
        self.ingested_documents = ingested_documents
        self.pipeline = pipeline

        # Cloud-specific configuration
        self.provider_name = ""
        self.credentials = {}
        self.folders = []
        self.real_time_enabled = False
        self.polling_interval = 300  # 5 minutes default
        self.temp_dir = tempfile.gettempdir()

        # Processing configuration
        filters = config.get("filters", {})
        self.formats = filters.get("file_formats", [])
        self.max_file_size = filters.get("max_file_size", None)

        # Get artifact service from pipeline's host component
        host_component = getattr(pipeline, "host_component", None)
        artifact_service = getattr(host_component, "artifact_service", None)
        app_name = getattr(host_component, "agent_name", "sam_rag")
        self.artifact_path = None
        
        # Get artifact path from config
        if host_component and hasattr(host_component, "app_config"):
            artifact_config = host_component.app_config.get("artifact_service", {})
            self.artifact_path = artifact_config.get("base_path", "/tmp/a2a_rag_agent_artifacts")
            logger.info(f"Using artifact path from config: {self.artifact_path}")
        
        if artifact_service:
            # Create adapter with artifact service
            from ..artifact_adapter import ArtifactStorageAdapter
            self.file_service = ArtifactStorageAdapter(artifact_service, app_name)
            logger.info("Using ArtifactStorageAdapter for cloud file operations")
        else:
            # Fallback to empty object with methods that raise exceptions
            logger.warning("No artifact service available. Cloud file operations will fail.")
            self.file_service = type('DummyFileService', (), {
                'download_to_file': lambda *args, **kwargs: logger.error("No artifact service available"),
                'get_metadata': lambda *args, **kwargs: logger.error("No artifact service available"),
                'upload_from_file': lambda *args, **kwargs: logger.error("No artifact service available")
            })()

        # Initialize the cloud provider
        self.process_config(config)

    @abstractmethod
    def process_config(self, source: Dict = {}) -> None:
        """
        Process the cloud provider specific configuration.

        Args:
            source: A dictionary containing the source configuration.
        """
        pass

    @abstractmethod
    def _authenticate(self) -> bool:
        """
        Authenticate with the cloud provider.

        Returns:
            True if authentication successful, False otherwise.
        """
        pass

    @abstractmethod
    def _list_files(
        self, folder_id: str = None, recursive: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List files in the cloud storage.

        Args:
            folder_id: The ID of the folder to list files from.
            recursive: Whether to list files recursively.

        Returns:
            A list of file metadata dictionaries.
        """
        pass

    @abstractmethod
    def _download_file(self, file_id: str, file_name: str) -> str:
        """
        Download a file from cloud storage to a temporary location.

        Args:
            file_id: The ID of the file to download.
            file_name: The name of the file.

        Returns:
            The path to the downloaded temporary file.
        """
        pass

    @abstractmethod
    def _setup_real_time_monitoring(self) -> None:
        """
        Set up real-time monitoring for the cloud storage.

        This could involve webhooks, push notifications, or polling.
        """
        pass

    def batch_scan(self) -> None:
        """
        Perform batch scanning of all files in configured cloud folders.
        """
        logger.info(f"Starting {self.provider_name} batch scan")

        if not self._authenticate():
            logger.error(f"Failed to authenticate with {self.provider_name}")
            return

        for folder_config in self.folders:
            folder_id = folder_config.get("folder_id") or folder_config.get("path")
            folder_name = folder_config.get("name", "Unknown")
            recursive = folder_config.get("recursive", True)

            logger.info(f"Scanning {self.provider_name} folder: {folder_name}")

            try:
                files = self._list_files(folder_id, recursive)
                for file_info in files:
                    self._process_cloud_file(file_info)
            except Exception as e:
                logger.error(
                    f"Error scanning {self.provider_name} folder {folder_name}: {str(e)}"
                )

    def scan(self) -> None:
        """
        Monitor the cloud storage for changes.
        """
        logger.info(f"=== {self.provider_name.upper()}: Starting scan ===")
        logger.info(f"{self.provider_name} batch mode: {self.batch}")
        logger.info(f"{self.provider_name} real-time enabled: {self.real_time_enabled}")

        # Perform batch scan if enabled
        if self.batch:
            logger.info(f"{self.provider_name}: Starting batch scan")
            self.batch_scan()
        else:
            logger.info(
                f"{self.provider_name}: Batch mode disabled, skipping batch scan"
            )

        # Set up real-time monitoring if enabled
        if self.real_time_enabled:
            logger.info(f"{self.provider_name}: Setting up real-time monitoring")
            self._setup_real_time_monitoring()
        else:
            logger.info(
                f"{self.provider_name}: Real-time monitoring disabled, starting polling"
            )
            # Fallback to periodic polling
            self._start_polling()

        logger.info(f"=== {self.provider_name.upper()}: Scan method completed ===")

    def _start_polling(self) -> None:
        """
        Start periodic polling for changes.
        """

        def poll_for_changes():
            while True:
                try:
                    logger.debug(f"Polling {self.provider_name} for changes")
                    # This is a simple implementation - could be optimized with change tokens
                    for folder_config in self.folders:
                        folder_id = folder_config.get("folder_id") or folder_config.get(
                            "path"
                        )
                        files = self._list_files(
                            folder_id, folder_config.get("recursive", True)
                        )
                        for file_info in files:
                            self._process_cloud_file(file_info)
                except Exception as e:
                    logger.error(f"Error during {self.provider_name} polling: {str(e)}")

                time.sleep(self.polling_interval)

        # Start polling in a daemon thread
        polling_thread = threading.Thread(target=poll_for_changes)
        polling_thread.daemon = True
        polling_thread.start()
        logger.info(
            f"Started {self.provider_name} polling with {self.polling_interval}s interval"
        )

    def _process_cloud_file(self, file_info: Dict[str, Any]) -> None:
        """
        Process a cloud file.

        Args:
            file_info: Dictionary containing file information.
        """
        file_id = file_info.get("id")
        file_name = file_info.get("name")
        file_size = file_info.get("size", 0)
        mime_type = file_info.get("mime_type")

        # Create unique path for cloud files
        file_path = f"{self.provider_name}://{file_id}/{file_name}"

        # Check if already ingested
        if file_path in self.ingested_documents:
            logger.debug(f"{self.provider_name} file already ingested: {file_name}")
            return

        # Validate file
        if not self._is_valid_cloud_file(file_name, mime_type, file_size):
            logger.debug(f"Invalid {self.provider_name} file: {file_name}")
            return

        # Download and process
        try:
            temp_file_path = self._download_file(file_id, file_name)
            if temp_file_path:
                # Store the file as an artifact
                artifact_url = self.store_as_artifact_sync(temp_file_path)
                
                if artifact_url:
                    logger.info(f"Stored cloud file as artifact: {artifact_url}")
                    
                    # Create metadata with artifact URL
                    metadata = self.extract_file_metadata(
                        file_path=file_path, 
                        artifact_url=artifact_url,
                        **file_info
                    )
                    
                    # Track the file with artifact URL
                    self._track_file(file_path, file_name, "new", metadata)
                    
                    # Process the downloaded file with metadata
                    self.pipeline.process_files([temp_file_path], metadata=metadata)
                else:
                    logger.warning(f"Failed to store cloud file as artifact: {file_name}")

                # Cleanup temporary file
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(
                        f"Failed to cleanup temp file {temp_file_path}.", trace=e
                    )
        except Exception as e:
            logger.error(
                f"Error processing {self.provider_name} file {file_name}: {str(e)}"
            )

    def _is_valid_cloud_file(
        self, file_name: str, mime_type: Optional[str], file_size: int
    ) -> bool:
        """
        Check if a cloud file is valid based on configured filters.

        Args:
            file_name: The name of the file.
            mime_type: The MIME type of the file.
            file_size: The size of the file in bytes.

        Returns:
            True if the file is valid, False otherwise.
        """
        # Check file format
        if not self.is_valid_file_format(file_name, mime_type):
            return False

        # Check file size
        if not self.is_valid_file_size(file_size):
            return False

        return True

    def upload_files(self, documents) -> str:
        """
        Upload files to the cloud storage.

        Args:
            documents: A list of documents to upload.

        Returns:
            A string indicating the result of the upload operation.
        """
        # This is a placeholder implementation
        # Specific cloud providers should implement their own upload logic
        logger.warning(f"Upload not implemented for {self.provider_name}")
        return f"Upload not implemented for {self.provider_name}"

    def get_tracked_files(self) -> List[Dict[str, Any]]:
        """
        Get all tracked files from cloud storage.

        Returns:
            A list of tracked files with their metadata.
        """
        if self.use_memory_storage:
            return [
                doc
                for doc in memory_storage.get_all_documents()
                if doc.get("source_type", "").startswith(self.provider_name.lower())
            ]
        elif DATABASE_AVAILABLE:
            # This would need to be implemented based on your database structure
            logger.warning("Database retrieval not implemented for cloud storage")
            return []
        else:
            logger.warning("Neither memory storage nor database is available")
            return []
