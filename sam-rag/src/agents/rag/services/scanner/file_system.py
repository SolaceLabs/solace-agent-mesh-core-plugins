from __future__ import annotations

import os
import time
import threading
from solace_ai_connector.common.log import log as logger
from typing import Dict, List, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from solace_agent_mesh.services.file_service.file_service import FileService

from .datasource_base import DataSource
from ..memory.memory_storage import memory_storage

# Try to import database modules, but don't fail if they're not available
try:
    from ..database.connect import get_db, insert_document, update_document, delete_document

    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False


# Concrete implementation for Local File System
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
        self.directories = []
        self.file_changes = []
        self.interval = 10
        self.ingested_documents = ingested_documents
        self.file_service = FileService()

        # Set inherited properties from base class
        self.use_memory_storage = source.get("use_memory_storage", False)
        self.batch = source.get("batch", False)

        self.process_config(source)

    def process_config(self, source: Dict = {}) -> None:
        """
        Process the source configuration to set up directories, file formats, and max file size.

        Args:
            source: A dictionary containing the source configuration.
        """
        self.directories = source.get("directories", [])
        if not self.directories:
            logger.info("No folder paths configured.")
            return

        filters = source.get("filters", {})
        if filters:
            self.formats = filters.get("file_formats", [])
            self.max_file_size = filters.get("max_file_size", None)

        schedule = source.get("schedule", {})
        if schedule:
            self.interval = schedule.get("interval", 10)

    def upload_files(self, documents) -> str:
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

                    # Check if the amfs_url has amfs:// prefix
                    if amfs_url.startswith("amfs://"):
                        metadata = self.file_service.get_metadata(file_url=amfs_url)
                        # Use the file service to download the file
                        self.file_service.download_to_file(
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
        except Exception:
            logger.error("Error uploading files.")
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

                        # Use inherited tracking method
                        metadata = self.extract_file_metadata(
                            file_path, source="filesystem"
                        )
                        self._track_file(
                            file_path, os.path.basename(file_path), "new", metadata
                        )
                        self.pipeline.process_files([file_path])

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

        # Use inherited tracking method
        metadata = self.extract_file_metadata(event.src_path, source="filesystem")
        self._track_file(
            event.src_path, os.path.basename(event.src_path), "new", metadata
        )
        # Add the new document to the existing sources list
        self.ingested_documents.append(event.src_path)
        # Process the file with the pipeline
        self.pipeline.process_files([event.src_path])

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

        # Handle file modification
        try:
            if self.use_memory_storage:
                memory_storage.update_document(path=event.src_path, status="modified")
                logger.info(f"Document updated in memory: {event.src_path}")
            elif DATABASE_AVAILABLE:
                update_document(get_db(), path=event.src_path, status="modified")
                logger.info(f"Document updated in database: {event.src_path}")
            else:
                logger.warning("Neither memory storage nor database is available")
        except Exception as e:
            logger.error(f"Error updating document {event.src_path}: {str(e)}")

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
