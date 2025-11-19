"""
In-memory storage implementation for the scanner module.

This module provides an in-memory storage option for the scanner module,
allowing it to store file information in memory instead of a database.
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class MemoryStorage:
    """
    A singleton class for in-memory storage of file information.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryStorage, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the memory storage."""
        self.files = {}  # Dict to store file information: {path: {metadata}}
        self.changes = []  # List to store file changes: [{path, status, timestamp}]
        self.last_scan_time = None

    def insert_document(self, path: str, file: str, **kwargs) -> None:
        """
        Insert a document into the memory storage.

        Args:
            path: The path to the document.
            file: The filename of the document.
            **kwargs: Additional metadata for the document.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        self.files[path] = {
            "path": path,
            "file": file,
            "status": "new",
            "timestamp": timestamp,
            **kwargs,
        }
        self.changes.append({"path": path, "status": "new", "timestamp": timestamp})
        logger.info("Document inserted in memory.")

    def update_document(self, path: str, status: str, **kwargs) -> None:
        """
        Update a document in the memory storage.

        Args:
            path: The path to the document.
            status: The new status of the document.
            **kwargs: Additional metadata to update.
        """
        if path in self.files:
            timestamp = datetime.now(timezone.utc).isoformat()
            self.files[path].update(
                {"status": status, "timestamp": timestamp, **kwargs}
            )
            self.changes.append(
                {"path": path, "status": status, "timestamp": timestamp}
            )
            logger.info("Document updated in memory.")
        else:
            logger.warning("Document not found in memory.")

    def delete_document(self, path: str) -> None:
        """
        Delete a document from the memory storage.

        Args:
            path: The path to the document.
        """
        if path in self.files:
            timestamp = datetime.now(timezone.utc).isoformat()
            del self.files[path]
            self.changes.append(
                {"path": path, "status": "deleted", "timestamp": timestamp}
            )
            logger.info("Document deleted from memory.")
        else:
            logger.warning("Document not found in memory.")

    def get_document(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Get a document from the memory storage.

        Args:
            path: The path to the document.

        Returns:
            The document metadata or None if not found.
        """
        return self.files.get(path)

    def get_all_documents(self) -> List[Dict[str, Any]]:
        """
        Get all documents from the memory storage.

        Returns:
            A list of document metadata for files with status 'modified' or 'new'.
        """
        return [
            file
            for file in self.files.values()
            if file.get("status") in ["modified", "new"]
        ]

    def get_changes_since(
        self, timestamp: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get changes since the given timestamp.

        Args:
            timestamp: The timestamp to get changes since. If None, returns all changes.

        Returns:
            A list of changes.
        """
        if timestamp is None:
            return self.changes

        return [change for change in self.changes if change["timestamp"] > timestamp]

    def clear(self) -> None:
        """Clear the memory storage."""
        self.files = {}
        self.changes = []
        self.last_scan_time = None
        logger.info("Memory storage cleared")

    def set_last_scan_time(self) -> None:
        """Set the last scan time to now."""
        self.last_scan_time = datetime.now(timezone.utc).isoformat()

    def get_last_scan_time(self) -> Optional[str]:
        """Get the last scan time."""
        return self.last_scan_time


# Create a singleton instance
memory_storage = MemoryStorage()
