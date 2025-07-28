"""
File system data source implementation for the SAM RAG plugin.
Monitors local file system for document changes and processes them.
"""

import os
import time
import threading
from typing import Dict, List, Any, Optional

# Import SAC logger if available, otherwise use standard logging
try:
    from solace_ai_connector.common.log import log as logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import base data source class
from .datasource_base import DataSource

# Import memory storage for in-memory document tracking
from ..memory.memory_storage import memory_storage

# Import artifact adapter
from ..artifact_adapter import ArtifactStorageAdapter

# ADK Imports
from google.adk.artifacts import BaseArtifactService # Added import

# Try to import database modules, but don't fail if they're not available
try:
    from ..database.connect import get_db, insert_document, update_document, delete_document
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False


class LocalFileSystemDataSource(DataSource):
    """
    A data source implementation for monitoring local file system changes.
    """

    def __init__(self, source: Dict, ingested_documents: List[str], pipeline) -> None:
        """
        Initialize the LocalFileSystemDataSource with the given source configuration.

        Args:
            source: A dictionary containing the source configuration.
            ingested_documents: A list of documents that have already been ingested.
            pipeline: An pipeline object for processing files.
        """
        super().__init__(source)
        self.pipeline = pipeline
        self.source_config = source # Store source for later use
        self.directories = []
        self.file_changes = []
        self.interval = 10
        self.ingested_documents = ingested_documents
        
        host_component = getattr(pipeline, "host_component", None)
        app_name = getattr(host_component, "agent_name", "sam_rag") # Used by ArtifactStorageAdapter

        logger.info(f"LocalFileSystemDataSource - Initializing. Host component: {host_component}")

        artifact_service: Optional[BaseArtifactService] = None

        if host_component and hasattr(host_component, "artifact_service"):
            artifact_service = host_component.artifact_service
            if artifact_service:
                logger.info(f"LocalFileSystemDataSource: Successfully retrieved artifact_service (type: {type(artifact_service)}) from host_component.")
            else:
                logger.warning("LocalFileSystemDataSource: host_component.artifact_service is None. File operations may fail.")
        else:
            logger.warning("LocalFileSystemDataSource: host_component or host_component.artifact_service not found. File operations may fail.")
        
        # Determine artifact_path (seems to be a local path hint, not directly the service's base_path)
        # This logic is kept as it might be used for other purposes by the class.
        self.artifact_path = None
        if host_component and hasattr(host_component, "app_config"):
            artifact_config_from_host = host_component.app_config.get("artifact_service", {})
            self.artifact_path = artifact_config_from_host.get("base_path", "/tmp/a2a_rag_agent_artifacts")
            logger.info(f"LocalFileSystemDataSource: Using artifact base_path hint from host_component.app_config: {self.artifact_path}")
        elif hasattr(pipeline, "component_config"):
            artifact_config_from_pipeline = pipeline.component_config.get("artifact_service", {})
            self.artifact_path = artifact_config_from_pipeline.get("base_path", "/tmp/a2a_rag_agent_artifacts")
            logger.info(f"LocalFileSystemDataSource: Using artifact base_path hint from pipeline.component_config: {self.artifact_path}")
        else:
            artifact_config_from_source = self.source_config.get("artifact_config", {})
            self.artifact_path = artifact_config_from_source.get("base_path", "/tmp/a2a_rag_agent_artifacts")
            logger.info(f"LocalFileSystemDataSource: Using artifact base_path hint from source_config or default: {self.artifact_path}")

        if artifact_service:
            self.file_service = ArtifactStorageAdapter(artifact_service, app_name)
            logger.info(f"LocalFileSystemDataSource: Initialized ArtifactStorageAdapter with artifact_service from host_component.")
        else:
            logger.warning("LocalFileSystemDataSource: No artifact service available from host_component. File operations will fail. Using DummyFileService.")
            self.file_service = type('DummyFileService', (), {
                'download_to_file': lambda *args, **kwargs: logger.error("DummyFileService: No artifact service. download_to_file failed."),
                'get_metadata': lambda *args, **kwargs: logger.error("DummyFileService: No artifact service. get_metadata failed."),
                'upload_from_file': lambda *args, **kwargs: logger.error("DummyFileService: No artifact service. upload_from_file failed.")
            })()

        # Set inherited properties from base class
        self.use_memory_storage = self.source_config.get("use_memory_storage", False)
        self.batch = self.source_config.get("batch", False)

        self.process_config(self.source_config)

    def process_config(self, source_cfg: Dict = {}) -> None:
        """
        Process the source configuration to set up directories, file formats, and max file size.

        Args:
            source_cfg: A dictionary containing the source configuration.
        """
        self.directories = source_cfg.get("directories", [])
        if not self.directories:
            logger.info("No folder paths configured.")
            return

        filters = source_cfg.get("filters", {})
        if filters:
            self.formats = filters.get("file_formats", [])
            self.max_file_size = filters.get("max_file_size", None)

        schedule = source_cfg.get("schedule", {})
        if schedule:
            self.interval = schedule.get("interval", 10)

    async def upload_files(self, documents) -> str:
        """
        Upload a file in the destination directory.
        Args:
            documents: The documents to upload.
        """
        try:
            if self.directories:
                destination_directory = self.directories[0]
                # Save the file to the destination directory
                if not os.path.exists(destination_directory):
                    os.makedirs(destination_directory)

                for document in documents:
                    amfs_url = document.get("amfs_url")
                    file_name = document.get("name")
                    mime_type = document.get("mime_type")

                    # Check if the URL has amfs:// or artifact:// prefix
                    if amfs_url.startswith("amfs://") or amfs_url.startswith("artifact://"):
                        # Get metadata using the adapter
                        metadata = await self.file_service.get_metadata(file_url=amfs_url)
                        # Use the adapter to download the file
                        await self.file_service.download_to_file(
                            file_url=amfs_url,
                            destination_path=os.path.join(
                                destination_directory, file_name
                            ),
                            session_id=metadata.get("session_id"),
                        )
                        logger.info("File uploaded.")

                return "Files uploaded successfully"
            else:
                logger.warning("No destination directory configured.")
                return "Failed to upload documents. No destination directory configured"
        except Exception as e:
            logger.error(f"Error uploading files: {e}")
            return "Failed to upload documents"

    def batch_scan(self) -> None:
        """
        Scan all existing files in configured directories that match the format filters.
        """
        logger.info(f"Starting batch scan of directories: {self.directories}")

        if not self.directories:
            logger.warning("No directories configured for batch scan.")
            return

        for directory in self.directories:
            if not os.path.exists(directory):
                logger.warning(f"Directory does not exist: {directory}")
                continue

            for root, _, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)

                    if self.is_valid_file(file_path):
                        # Check if the document already exists in the vector database
                        if file_path in self.ingested_documents:
                            logger.info(
                                "Batch: Document already exists in vector database."
                            )
                            continue

                        # Store the file as an artifact
                        artifact_url = self.store_as_artifact_sync(file_path)
                        
                        if artifact_url:
                            logger.info(f"Stored file as artifact: {artifact_url}")
                            
                            # Use inherited tracking method with artifact URL
                            metadata = self.extract_file_metadata(
                                file_path=file_path, 
                                artifact_url=artifact_url,
                                source="filesystem"
                            )
                            
                            self._track_file(
                                file_path, os.path.basename(file_path), "new", metadata
                            )
                            
                            # Process the file with the pipeline
                            self.pipeline.process_files([file_path], metadata=metadata)
                        else:
                            logger.warning(f"Failed to store file as artifact: {file_path}")

    def scan(self) -> None:
        """
        Monitor the configured directories for file system changes.
        If batch mode is enabled, first scan all existing files.
        """
        logger.info("=== FILESYSTEM: Starting scan ===")
        logger.info(f"Filesystem batch mode: {self.batch}")
        logger.info(f"Filesystem directories: {self.directories}")

        # If batch mode is enabled, first scan existing files
        if self.batch:
            logger.info("Filesystem: Starting batch scan")
            self.batch_scan()
            logger.info("Filesystem: Batch scan completed")
        else:
            logger.info("Filesystem: Batch mode disabled, skipping batch scan")

        # Set up file system monitoring (non-blocking)
        logger.info("Filesystem: Setting up file system monitoring")
        event_handler = FileSystemEventHandler()
        event_handler.on_created = self.on_created
        event_handler.on_deleted = self.on_deleted
        event_handler.on_modified = self.on_modified

        observer = Observer()
        for directory in self.directories:
            if os.path.exists(directory):
                observer.schedule(event_handler, directory, recursive=True)
                logger.info(f"Filesystem: Monitoring directory: {directory}")
            else:
                logger.warning(f"Filesystem: Directory does not exist: {directory}")

        observer.start()
        logger.info("Filesystem: File system observer started")

        # Start periodic monitoring in background (non-blocking)
        def run_periodically():
            while True:
                time.sleep(self.interval)

        thread = threading.Thread(target=run_periodically)
        thread.daemon = True  # Make thread a daemon so it exits when main thread exits
        thread.start()
        logger.info(
            f"Filesystem: Started periodic monitoring with {self.interval}s interval"
        )

        # Don't block here - let the scan method return so other data sources can be processed
        logger.info("=== FILESYSTEM: Scan method completed (non-blocking) ===")

    def on_created(self, event):
        """
        Handle the event when a file is created.

        Args:
            event: The file system event.
        """
        if not self.is_valid_file(event.src_path):
            logger.warning(f"Invalid file: {event.src_path}")
            return

        # Check if the document already exists in the vector database
        if event.src_path in self.ingested_documents:
            logger.info(
                f"Document already exists in vector database. Re-ingest {event.src_path}"
            )

        # Store the file as an artifact
        artifact_url = self.store_as_artifact_sync(event.src_path)
        
        if artifact_url:
            logger.info(f"Stored file as artifact: {artifact_url}")
            
            # Use inherited tracking method with artifact URL
            metadata = self.extract_file_metadata(
                file_path=event.src_path, 
                artifact_url=artifact_url,
                source="filesystem"
            )
            
            self._track_file(
                event.src_path, os.path.basename(event.src_path), "new", metadata
            )
            
            # Add the new document to the existing sources list
            self.ingested_documents.append(event.src_path)
            
            # Process the file with the pipeline
            self.pipeline.process_files([event.src_path], metadata=metadata)
        else:
            logger.warning(f"Failed to store file as artifact: {event.src_path}")

    def on_deleted(self, event):
        """
        Handle the event when a file is deleted.

        Args:
            event: The file system event.
        """

        # Handle file deletion
        try:
            if self.use_memory_storage:
                memory_storage.delete_document(path=event.src_path)
                logger.info(f"Document deleted from memory: {event.src_path}")
            elif DATABASE_AVAILABLE:
                delete_document(get_db(), path=event.src_path)
                logger.info(f"Document deleted from database: {event.src_path}")
            else:
                logger.warning("Neither memory storage nor database is available")
        except Exception as e:
            logger.error(f"Error deleting document {event.src_path}: {str(e)}")

    def on_modified(self, event):
        """
        Handle the event when a file is modified.

        Args:
            event: The file system event.
        """
        if not self.is_valid_file(event.src_path):
            return

        # Check if the document already exists in the vector database
        # For modified files, we still want to update them even if they exist
        # But we'll log that they exist for tracking purposes
        if event.src_path in self.ingested_documents:
            logger.info(
                f"Modified document exists in vector database: {event.src_path}"
            )

        # Store the file as an artifact
        artifact_url = self.store_as_artifact_sync(event.src_path)
        
        if artifact_url:
            logger.info(f"Stored modified file as artifact: {artifact_url}")
            
            # Handle file modification
            try:
                # Create metadata with artifact URL
                metadata = self.extract_file_metadata(
                    file_path=event.src_path, 
                    artifact_url=artifact_url,
                    source="filesystem"
                )
                
                if self.use_memory_storage:
                    memory_storage.update_document(
                        path=event.src_path, 
                        status="modified",
                        artifact_url=artifact_url
                    )
                    logger.info(f"Document updated in memory: {event.src_path}")
                elif DATABASE_AVAILABLE:
                    update_document(
                        get_db(), 
                        path=event.src_path, 
                        status="modified",
                        artifact_url=artifact_url
                    )
                    logger.info(f"Document updated in database: {event.src_path}")
                else:
                    logger.warning("Neither memory storage nor database is available")
                    
                # Process the modified file with the pipeline
                self.pipeline.process_files([event.src_path], metadata=metadata)
            except Exception as e:
                logger.error(f"Error updating document {event.src_path}: {str(e)}")
        else:
            logger.warning(f"Failed to store modified file as artifact: {event.src_path}")

    def is_valid_file(self, path: str) -> bool:
        """
        Check if the file is valid based on the configured formats and size.

        Args:
            path: The file path to validate.

        Returns:
            True if the file is valid, False otherwise.
        """
        if os.path.isdir(path):
            return False
        if path.endswith(".DS_Store"):
            return False
        if self.formats and not any(path.endswith(fmt) for fmt in self.formats):
            return False
        if (
            self.max_file_size is not None
            and os.path.getsize(path) > self.max_file_size * 1024
        ):
            return False
        return True

    # Using the store_as_artifact_sync method from the base class
    # This method is already implemented in DataSource

    def get_tracked_files(self) -> List[Dict[str, Any]]:
        """
        Get all tracked files.

        Returns:
            A list of tracked files with their metadata.
        """
        if self.use_memory_storage:
            return memory_storage.get_all_documents()
        elif DATABASE_AVAILABLE:
            # This would need to be implemented based on your database structure
            # For now, we'll just return an empty list
            logger.warning("Database retrieval not implemented")
            return []
        else:
            logger.warning("Neither memory storage nor database is available")
            return []
