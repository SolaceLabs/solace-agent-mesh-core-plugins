"""
Google Drive Data Source implementation for the scanner component.

This module provides Google Drive integration with OAuth2 authentication,
batch scanning, real-time monitoring, and file processing capabilities.
"""

import os
import tempfile
import threading
import time
from typing import Dict, List, Any, Optional
from solace_ai_connector.common.log import log as logger

from ..cloud_storage import CloudStorageDataSource

# Try to import Google Drive dependencies
try:
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
    from googleapiclient.http import MediaIoBaseDownload
    from googleapiclient.errors import HttpError

    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False
    logger.warning(
        "Google Drive dependencies not available. Install with: pip install google-api-python-client google-oauth2"
    )


class GoogleDriveDataSource(CloudStorageDataSource):
    """
    Google Drive implementation of CloudStorageDataSource.

    Provides OAuth2 authentication, batch scanning, real-time monitoring,
    and file processing for Google Drive documents.
    """

    # Google Drive API scopes
    SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

    # Google Workspace format mappings for export
    GOOGLE_FORMATS = {
        "application/vnd.google-apps.document": {
            "export_mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "extension": ".docx",
        },
        "application/vnd.google-apps.spreadsheet": {
            "export_mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "extension": ".xlsx",
        },
        "application/vnd.google-apps.presentation": {
            "export_mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "extension": ".pptx",
        },
    }

    def __init__(self, config: Dict, ingested_documents: List[str], pipeline):
        """
        Initialize the GoogleDriveDataSource.

        Args:
            config: Configuration dictionary for Google Drive.
            ingested_documents: List of already ingested documents.
            pipeline: The processing pipeline instance.
        """
        if not GOOGLE_DRIVE_AVAILABLE:
            raise ImportError(
                "Google Drive dependencies not available. "
                "Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )

        super().__init__(config, ingested_documents, pipeline)
        self.provider_name = "google_drive"

        # Google Drive specific configuration
        self.service = None
        self.service_account_key_path = ""
        self.include_google_formats = False
        self.change_token = None

        # Initialize the service
        self.process_config(config)

    def process_config(self, source: Dict = {}) -> None:
        """
        Process Google Drive specific configuration.

        Args:
            source: Configuration dictionary containing Google Drive settings.
        """
        # Get service account key path
        self.service_account_key_path = source.get("service_account_key_path", "")
        if not self.service_account_key_path:
            raise ValueError("Google Drive service_account_key_path is required")

        # Get folder configurations
        self.folders = source.get("folders", [])
        if not self.folders:
            logger.warning("No Google Drive folders configured")

        # Get filter configurations
        filters = source.get("filters", {})
        self.include_google_formats = filters.get("include_google_formats", False)

        # Get real-time monitoring configuration
        real_time_config = source.get("real_time", {})
        self.real_time_enabled = real_time_config.get("enabled", False)
        self.webhook_url = real_time_config.get("webhook_url")
        self.polling_interval = real_time_config.get("polling_interval", 300)

        logger.info(
            f"Google Drive configuration processed: {len(self.folders)} folders, "
            f"real-time: {self.real_time_enabled}, include_google_formats: {self.include_google_formats}"
        )

    def _authenticate(self) -> bool:
        """
        Authenticate with Google Drive API using Service Account.

        Returns:
            True if authentication successful, False otherwise.
        """
        try:
            # Check if service account key file exists
            if not os.path.exists(self.service_account_key_path):
                logger.error(
                    f"Google Drive service account key file not found: {self.service_account_key_path}"
                )
                return False

            # Load service account credentials
            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_key_path, scopes=self.SCOPES
            )

            # Build the service
            self.service = build("drive", "v3", credentials=credentials)
            logger.info(
                "Google Drive service initialized successfully with Service Account"
            )
            return True

        except Exception as e:
            logger.error(
                f"Google Drive Service Account authentication failed: {str(e)}"
            )
            return False

    def _validate_folder_access(
        self, folder_id: str, folder_type: str = "personal"
    ) -> bool:
        """
        Validate that the folder exists and is accessible.

        Args:
            folder_id: The ID of the folder to validate.
            folder_type: Type of folder ('personal' or 'shared_drive').

        Returns:
            True if folder is accessible, False otherwise.
        """
        if not self.service:
            logger.error("Google Drive service not initialized")
            return False

        try:
            # Build parameters for folder access check
            get_params = {"fileId": folder_id, "fields": "id, name, mimeType, parents"}

            # Handle shared drives
            if folder_type == "shared_drive":
                get_params["supportsAllDrives"] = True

            # Try to get folder metadata
            folder_metadata = self.service.files().get(**get_params).execute()

            # Check if it's actually a folder
            if folder_metadata.get("mimeType") != "application/vnd.google-apps.folder":
                logger.error(f"ID {folder_id} is not a folder")
                return False

            logger.debug(
                f"Successfully validated folder access: {folder_metadata.get('name')} ({folder_id})"
            )
            return True

        except HttpError as e:
            if e.resp.status == 403:
                logger.error(f"Permission denied accessing folder {folder_id}")
            elif e.resp.status == 404:
                logger.error(f"Folder {folder_id} not found")
            else:
                logger.error(
                    f"HTTP error validating folder {folder_id}: {e.resp.status}"
                )
            return False
        except Exception as e:
            logger.error(f"Error validating folder access {folder_id}: {str(e)}")
            return False

    def _get_drive_id_for_folder(self, folder_id: str) -> Optional[str]:
        """
        Get the drive ID for a folder in a shared drive.

        Args:
            folder_id: The ID of the folder.

        Returns:
            The drive ID if found, None otherwise.
        """
        if not self.service:
            return None

        try:
            folder_metadata = (
                self.service.files()
                .get(
                    fileId=folder_id, fields="driveId, parents", supportsAllDrives=True
                )
                .execute()
            )

            drive_id = folder_metadata.get("driveId")
            if drive_id:
                logger.debug(f"Found drive ID {drive_id} for folder {folder_id}")
                return drive_id

            # If no direct drive ID, try to get it from parents
            parents = folder_metadata.get("parents", [])
            if parents:
                return self._get_drive_id_for_folder(parents[0])

            return None

        except Exception as e:
            logger.debug(f"Could not get drive ID for folder {folder_id}: {str(e)}")
            return None

    def _list_files(
        self,
        folder_id: str = None,
        recursive: bool = True,
        folder_type: str = "personal",
    ) -> List[Dict[str, Any]]:
        """
        List files in Google Drive.

        Args:
            folder_id: The ID of the folder to list files from.
            recursive: Whether to list files recursively.
            folder_type: Type of folder ('personal' or 'shared_drive').

        Returns:
            A list of file metadata dictionaries.
        """
        if not self.service:
            logger.error("Google Drive service not initialized")
            return []

        # Validate folder exists and is accessible
        if folder_id and not self._validate_folder_access(folder_id, folder_type):
            logger.error(f"Cannot access Google Drive folder {folder_id}")
            return []

        files = []

        try:
            # Build query for files in folder
            if folder_id:
                query = f"'{folder_id}' in parents and trashed=false"
            else:
                query = "trashed=false"

            # Add shared drive support
            list_params = {
                "q": query,
                "fields": "nextPageToken, files(id, name, mimeType, size, modifiedTime, parents, webViewLink, driveId)",
                "pageSize": 100,  # Optimize batch size
            }

            # Handle shared drives
            if folder_type == "shared_drive":
                list_params["includeItemsFromAllDrives"] = True
                list_params["supportsAllDrives"] = True
                if folder_id:
                    # For shared drives, we need to get the drive ID
                    drive_id = self._get_drive_id_for_folder(folder_id)
                    if drive_id:
                        list_params["driveId"] = drive_id

            logger.debug(f"Querying Google Drive with params: {list_params}")

            # Get files with pagination
            page_token = None
            total_items_processed = 0

            while True:
                if page_token:
                    list_params["pageToken"] = page_token

                results = self.service.files().list(**list_params).execute()

                items = results.get("files", [])
                total_items_processed += len(items)

                logger.debug(
                    f"Found {len(items)} items in current page for folder {folder_id or 'root'}"
                )

                for item in items:
                    # Handle folders recursively
                    if (
                        item["mimeType"] == "application/vnd.google-apps.folder"
                        and recursive
                    ):
                        logger.debug(
                            f"Processing subfolder: {item['name']} ({item['id']})"
                        )
                        subfolder_files = self._list_files(
                            item["id"], recursive, folder_type
                        )
                        files.extend(subfolder_files)
                    else:
                        # Add file metadata
                        file_metadata = {
                            "id": item["id"],
                            "name": item["name"],
                            "mime_type": item["mimeType"],
                            "size": int(item.get("size", 0)) if item.get("size") else 0,
                            "modified_time": item.get("modifiedTime"),
                            "parents": item.get("parents", []),
                            "web_view_link": item.get("webViewLink"),
                            "drive_id": item.get("driveId"),
                        }
                        files.append(file_metadata)
                        logger.debug(f"Added file: {item['name']} ({item['id']})")

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            logger.info(
                f"Successfully listed {len(files)} files from Google Drive folder {folder_id or 'root'} "
                f"(processed {total_items_processed} total items, type: {folder_type})"
            )
            return files

        except HttpError as e:
            error_details = e.error_details if hasattr(e, "error_details") else str(e)
            logger.error(
                f"Google Drive API error listing files in folder {folder_id}: "
                f"Status: {e.resp.status}, Details: {error_details}"
            )
            # Log specific permission errors
            if e.resp.status == 403:
                logger.error(
                    f"Permission denied accessing folder {folder_id}. "
                    f"Ensure the service account has access to this folder."
                )
            elif e.resp.status == 404:
                logger.error(f"Folder {folder_id} not found or not accessible.")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing Google Drive files: {str(e)}")
            logger.debug(f"Error details: {type(e).__name__}: {str(e)}")
            return []

    def _download_file(self, file_id: str, file_name: str) -> str:
        """
        Download a file from Google Drive to a temporary location.

        Args:
            file_id: The ID of the file to download.
            file_name: The name of the file.

        Returns:
            The path to the downloaded temporary file.
        """
        if not self.service:
            logger.error("Google Drive service not initialized")
            return ""

        try:
            # Get file metadata to determine MIME type
            file_metadata = self.service.files().get(fileId=file_id).execute()
            mime_type = file_metadata.get("mimeType")

            # Handle Google Workspace formats
            if mime_type in self.GOOGLE_FORMATS and self.include_google_formats:
                export_info = self.GOOGLE_FORMATS[mime_type]
                request = self.service.files().export_media(
                    fileId=file_id, mimeType=export_info["export_mime"]
                )
                # Update file name with correct extension
                name_without_ext = os.path.splitext(file_name)[0]
                file_name = f"{name_without_ext}{export_info['extension']}"
            else:
                # Regular file download
                request = self.service.files().get_media(fileId=file_id)

            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{file_name}", dir=self.temp_dir
            )

            # Download file
            downloader = MediaIoBaseDownload(temp_file, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(f"Download progress: {int(status.progress() * 100)}%")

            temp_file.close()
            logger.info(f"Downloaded Google Drive file to: {temp_file.name}")
            return temp_file.name

        except HttpError as e:
            logger.error(
                f"Google Drive API error downloading file {file_name}: {str(e)}"
            )
            return ""
        except Exception as e:
            logger.error(f"Error downloading Google Drive file {file_name}: {str(e)}")
            return ""

    def _setup_real_time_monitoring(self) -> None:
        """
        Set up real-time monitoring for Google Drive.

        This implementation uses polling as a fallback. In production,
        you would set up Google Drive Push Notifications (webhooks).
        """
        if self.webhook_url:
            logger.info(
                "Google Drive webhook monitoring not yet implemented, using polling"
            )

        # Start polling thread
        self._start_polling()

    def batch_scan(self) -> None:
        """
        Perform batch scanning of all files in configured Google Drive folders.
        """
        logger.info("=== GOOGLE_DRIVE: Starting batch scan ===")
        logger.info(f"Google Drive batch mode: {self.batch}")
        logger.info(f"Google Drive folders configured: {len(self.folders)}")

        if not self._authenticate():
            logger.error("Failed to authenticate with Google Drive")
            return

        logger.info("Google Drive authentication successful")

        for i, folder_config in enumerate(self.folders):
            folder_id = folder_config.get("folder_id")
            folder_name = folder_config.get("name", "Unknown")
            recursive = folder_config.get("recursive", True)
            folder_type = folder_config.get("type", "personal")

            logger.info(
                f"Scanning Google Drive folder {i+1}/{len(self.folders)}: {folder_name} (ID: {folder_id}, type: {folder_type})"
            )

            try:
                files = self._list_files(folder_id, recursive, folder_type)
                logger.info(
                    f"Found {len(files)} files in Google Drive folder {folder_name}"
                )

                for j, file_info in enumerate(files):
                    logger.debug(
                        f"Processing Google Drive file {j+1}/{len(files)}: {file_info.get('name')}"
                    )
                    self._process_cloud_file(file_info)

                logger.info(
                    f"Completed processing {len(files)} files from folder {folder_name}"
                )
            except Exception as e:
                logger.error(
                    f"Error scanning Google Drive folder {folder_name}: {str(e)}"
                )
                import traceback

                logger.error(f"Traceback: {traceback.format_exc()}")

        logger.info("=== GOOGLE_DRIVE: Batch scan completed ===")

    def _process_cloud_file(self, file_info: Dict[str, Any]) -> None:
        """
        Process a Google Drive file with proper duplicate checking.

        Args:
            file_info: Dictionary containing file information.
        """
        file_id = file_info.get("id")
        file_name = file_info.get("name")
        file_size = file_info.get("size", 0)
        mime_type = file_info.get("mime_type")
        modified_time = file_info.get("modified_time")

        # Create standardized Google Drive URI for consistent identification
        google_drive_uri = f"google_drive://{file_id}"

        # Also create a display path for logging
        display_path = f"google_drive://{file_id}/{file_name}"

        # Check if already ingested using multiple strategies for robustness
        if self._is_file_already_ingested(
            file_id, file_name, google_drive_uri, modified_time
        ):
            logger.info(f"Google Drive file already ingested: {file_name} ({file_id})")
            return

        # Validate file
        if not self._is_valid_cloud_file(file_name, mime_type, file_size):
            logger.debug(f"Invalid Google Drive file: {file_name}")
            return

        # Track the file with enhanced metadata
        metadata = self._create_enhanced_metadata(file_info, google_drive_uri)
        self._track_file(google_drive_uri, file_name, "new", metadata)

        # Download and process
        try:
            temp_file_path = self._download_file(file_id, file_name)
            if temp_file_path:
                # Process the downloaded file with enhanced metadata
                # Pass the metadata to the pipeline for proper Google Drive URI storage
                self.pipeline.process_files([temp_file_path], metadata=metadata)

                # Cleanup temporary file
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(
                        f"Failed to cleanup temp file {temp_file_path}: {str(e)}"
                    )
        except Exception as e:
            logger.error(f"Error processing Google Drive file {file_name}: {str(e)}")

    def _is_file_already_ingested(
        self,
        file_id: str,
        file_name: str,
        google_drive_uri: str,
        modified_time: Optional[str],
    ) -> bool:
        """
        Check if a Google Drive file has already been ingested using multiple strategies.

        Args:
            file_id: The Google Drive file ID.
            file_name: The name of the file.
            google_drive_uri: The standardized Google Drive URI.
            modified_time: The file's last modified time.

        Returns:
            True if the file has already been ingested, False otherwise.
        """
        # Strategy 1: Check using standardized Google Drive URI
        if google_drive_uri in self.ingested_documents:
            logger.debug(f"Found duplicate using Google Drive URI: {google_drive_uri}")
            return True

        # Strategy 2: Check using file ID patterns
        file_id_patterns = [
            f"google_drive://{file_id}",
            f"gdrive://{file_id}",
            f"google_drive://{file_id}/{file_name}",
            f"gdrive://{file_id}/{file_name}",
        ]

        for pattern in file_id_patterns:
            if pattern in self.ingested_documents:
                logger.debug(f"Found duplicate using pattern: {pattern}")
                return True

        # Strategy 3: Check for file name patterns (less reliable but useful fallback)
        # This helps catch cases where the same file might have been ingested differently
        name_patterns = [file_name, f"google_drive_{file_name}", f"gdrive_{file_name}"]

        for pattern in name_patterns:
            if any(pattern in doc for doc in self.ingested_documents):
                logger.debug(f"Found potential duplicate using name pattern: {pattern}")
                # This is less certain, so we log it but don't immediately return
                # In the future, we could add more sophisticated checking here
                pass

        return False

    def _create_enhanced_metadata(
        self, file_info: Dict[str, Any], google_drive_uri: str
    ) -> Dict[str, Any]:
        """
        Create enhanced metadata for Google Drive files.

        Args:
            file_info: Dictionary containing file information.
            google_drive_uri: The standardized Google Drive URI.

        Returns:
            A dictionary containing enhanced metadata.
        """
        # Start with base metadata
        metadata = self.extract_file_metadata(google_drive_uri, **file_info)

        # Add Google Drive specific metadata
        metadata.update(
            {
                "source": "google_drive",
                "provider": "google_drive",
                "google_drive_id": file_info.get("id"),
                "google_drive_uri": google_drive_uri,
                "original_name": file_info.get("name"),
                "mime_type": file_info.get("mime_type"),
                "size": file_info.get("size", 0),
                "modified_time": file_info.get("modified_time"),
                "web_view_link": file_info.get("web_view_link"),
                "drive_id": file_info.get("drive_id"),
                "parents": file_info.get("parents", []),
            }
        )

        return metadata
