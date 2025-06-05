"""
OneDrive Data Source implementation for the scanner component.

This module provides OneDrive integration with Microsoft Graph API authentication,
batch scanning, real-time monitoring, and file processing capabilities.
"""

import os
import tempfile
import threading
import time
from typing import Dict, List, Any, Optional
from solace_ai_connector.common.log import log as logger

from ..cloud_storage import CloudStorageDataSource

# Try to import OneDrive/Microsoft Graph dependencies
try:
    import msal
    import requests

    ONEDRIVE_AVAILABLE = True
except ImportError:
    ONEDRIVE_AVAILABLE = False
    logger.warning(
        "OneDrive dependencies not available. Install with: pip install msal requests"
    )


class OneDriveDataSource(CloudStorageDataSource):
    """
    OneDrive implementation of CloudStorageDataSource.

    Provides Microsoft Graph API authentication, batch scanning, real-time monitoring,
    and file processing for OneDrive documents (personal and business).
    """

    # Microsoft Graph API scopes for different authentication flows
    INTERACTIVE_SCOPES = [
        "https://graph.microsoft.com/Files.Read.All",
        "https://graph.microsoft.com/Sites.Read.All",
    ]
    CLIENT_CREDENTIAL_SCOPES = ["https://graph.microsoft.com/.default"]

    # Microsoft Graph API endpoints
    GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"

    # Office format mappings for download
    OFFICE_FORMATS = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
        "application/vnd.ms-excel": ".xls",
        "application/msword": ".doc",
        "application/vnd.ms-powerpoint": ".ppt",
    }

    def __init__(self, config: Dict, ingested_documents: List[str], pipeline):
        """
        Initialize the OneDriveDataSource.

        Args:
            config: Configuration dictionary for OneDrive.
            ingested_documents: List of already ingested documents.
            pipeline: The processing pipeline instance.
        """
        if not ONEDRIVE_AVAILABLE:
            raise ImportError(
                "OneDrive dependencies not available. "
                "Install with: pip install msal requests"
            )

        super().__init__(config, ingested_documents, pipeline)
        self.provider_name = "onedrive"

        # OneDrive specific configuration
        self.app = None
        self.access_token = None
        self.client_id = ""
        self.client_secret = ""
        self.tenant_id = ""
        self.authority = ""
        self.account_type = "personal"  # personal or business

        # Initialize the service
        self.process_config(config)

    def process_config(self, source: Dict = {}) -> None:
        """
        Process OneDrive specific configuration.

        Args:
            source: Configuration dictionary containing OneDrive settings.
        """
        # Get authentication configuration
        self.client_id = source.get("client_id", "")
        self.client_secret = source.get("client_secret", "")
        self.tenant_id = source.get("tenant_id", "")
        self.account_type = source.get("account_type", "personal")

        if not self.client_id:
            raise ValueError("OneDrive client_id is required")

        # Set authority based on account type
        if self.account_type == "business" and self.tenant_id:
            self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        else:
            self.authority = "https://login.microsoftonline.com/common"

        # Get folder configurations
        self.folders = source.get("folders", [])
        if not self.folders:
            # Default to root folder
            self.folders = [{"path": "/", "name": "Root", "recursive": True}]

        # Get real-time monitoring configuration
        real_time_config = source.get("real_time", {})
        self.real_time_enabled = real_time_config.get("enabled", False)
        self.webhook_url = real_time_config.get("webhook_url")
        self.polling_interval = real_time_config.get("polling_interval", 300)

        logger.info(
            f"OneDrive configuration processed: {len(self.folders)} folders, "
            f"account_type: {self.account_type}, real-time: {self.real_time_enabled}"
        )

    def _authenticate(self) -> bool:
        """
        Authenticate with Microsoft Graph API using MSAL.

        Returns:
            True if authentication successful, False otherwise.
        """
        try:
            logger.info(
                f"Authenticating with OneDrive - Account type: {self.account_type}, Authority: {self.authority}"
            )

            # Create MSAL application
            if self.client_secret:
                # Confidential client (business apps)
                logger.info(
                    "Using confidential client authentication flow (with client secret)"
                )
                self.app = msal.ConfidentialClientApplication(
                    client_id=self.client_id,
                    client_credential=self.client_secret,
                    authority=self.authority,
                )
            else:
                # Public client (personal apps)
                logger.info("Using public client authentication flow (interactive)")
                self.app = msal.PublicClientApplication(
                    client_id=self.client_id, authority=self.authority
                )

            # Try to get token from cache
            accounts = self.app.get_accounts()
            logger.debug(f"Found {len(accounts)} cached accounts")

            if accounts:
                # Try silent authentication first
                logger.info("Attempting silent authentication with cached account")
                result = self.app.acquire_token_silent(
                    self.INTERACTIVE_SCOPES, account=accounts[0]
                )
                if result and "access_token" in result:
                    self.access_token = result["access_token"]
                    logger.info("OneDrive authentication successful (cached token)")
                    return True

            # Interactive authentication
            if self.client_secret:
                # Client credentials flow for business apps
                logger.info("Attempting client credentials flow authentication")
                result = self.app.acquire_token_for_client(
                    scopes=self.CLIENT_CREDENTIAL_SCOPES
                )
            else:
                # Interactive flow for personal apps
                logger.info("Attempting interactive authentication flow")
                result = self.app.acquire_token_interactive(
                    scopes=self.INTERACTIVE_SCOPES
                )

            if result and "access_token" in result:
                self.access_token = result["access_token"]
                # Log partial token for debugging (first 10 chars only for security)
                token_preview = (
                    self.access_token[:10] + "..." if self.access_token else "None"
                )
                logger.info(
                    f"OneDrive authentication successful - Token preview: {token_preview}"
                )
                return True
            else:
                error = result.get("error", "Unknown error")
                error_desc = result.get("error_description", "No description")
                logger.error(f"OneDrive authentication failed: {error} - {error_desc}")
                logger.error(f"Full authentication result: {result}")
                return False

        except Exception as e:
            logger.error(f"OneDrive authentication failed with exception: {str(e)}")
            import traceback

            logger.error(
                f"Authentication exception traceback: {traceback.format_exc()}"
            )
            return False

    def _make_graph_request(
        self, endpoint: str, method: str = "GET", params: Dict = None
    ) -> Dict:
        """
        Make a request to Microsoft Graph API.

        Args:
            endpoint: The API endpoint (relative to graph API base).
            method: HTTP method (GET, POST, etc.).
            params: Query parameters.

        Returns:
            Response data as dictionary.
        """
        if not self.access_token:
            logger.error("No access token available for Graph API request")
            return {}

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        url = f"{self.GRAPH_API_ENDPOINT}/{endpoint.lstrip('/')}"

        logger.info(f"Making Graph API request: {method} {url}")
        if params:
            logger.debug(f"Request parameters: {params}")

        try:
            response = requests.request(method, url, headers=headers, params=params)
            logger.debug(f"Graph API response status: {response.status_code}")

            # Log response headers for debugging
            logger.debug(f"Response headers: {dict(response.headers)}")

            try:
                response.raise_for_status()
                response_data = response.json()
                # Log a sample of the response data (first few items if it's a collection)
                if "value" in response_data and isinstance(
                    response_data["value"], list
                ):
                    sample_size = min(2, len(response_data["value"]))
                    logger.debug(
                        f"Response contains {len(response_data['value'])} items. Sample: {response_data['value'][:sample_size]}"
                    )
                return response_data
            except ValueError:
                # Not a JSON response
                logger.error(f"Non-JSON response received: {response.text[:200]}...")
                return {}

        except requests.exceptions.RequestException as e:
            logger.error(f"Graph API request failed: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response status code: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text[:500]}")
            return {}

    def _list_files(
        self, folder_path: str = None, recursive: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List files in OneDrive.

        Args:
            folder_path: The path of the folder to list files from.
            recursive: Whether to list files recursively.

        Returns:
            A list of file metadata dictionaries.
        """
        if not self.access_token:
            logger.error("OneDrive not authenticated")
            return []

        files = []

        try:
            # Build endpoint for folder
            if folder_path and folder_path != "/":
                # Encode folder path for URL
                encoded_path = folder_path.replace(" ", "%20")
                # Log the original and encoded paths
                logger.info(
                    f"Listing files from folder path: '{folder_path}' (encoded: '{encoded_path}')"
                )
                endpoint = f"me/drive/root:{encoded_path}:/children"
                logger.info(f"Using endpoint for specific folder: {endpoint}")
            else:
                logger.info("Listing files from root folder")
                endpoint = "me/drive/root/children"
                logger.info(f"Using endpoint for root folder: {endpoint}")

            # Get files with pagination
            page_count = 0
            while endpoint:
                page_count += 1
                logger.info(
                    f"Fetching page {page_count} of files using endpoint: {endpoint}"
                )

                response = self._make_graph_request(endpoint)
                items = response.get("value", [])

                logger.info(f"Retrieved {len(items)} items from OneDrive")

                # Log folder structure for debugging
                folders = [item["name"] for item in items if item.get("folder")]
                if folders:
                    logger.info(
                        f"Folders found at '{folder_path or 'root'}': {folders}"
                    )

                for item in items:
                    if item.get("folder"):
                        # Handle folders recursively
                        if recursive:
                            folder_path_for_recursion = (
                                item.get("parentReference", {}).get("path", "")
                                + "/"
                                + item["name"]
                            )
                            logger.debug(
                                f"Recursively listing files in subfolder: {folder_path_for_recursion}"
                            )
                            folder_files = self._list_files(
                                folder_path_for_recursion,
                                recursive,
                            )
                            files.extend(folder_files)
                    else:
                        # Add file metadata
                        file_info = {
                            "id": item["id"],
                            "name": item["name"],
                            "mime_type": item.get("file", {}).get(
                                "mimeType", "application/octet-stream"
                            ),
                            "size": item.get("size", 0),
                            "modified_time": item.get("lastModifiedDateTime"),
                            "download_url": item.get("@microsoft.graph.downloadUrl"),
                            "web_url": item.get("webUrl"),
                            "path": item.get("parentReference", {}).get("path", "")
                            + "/"
                            + item["name"],
                        }
                        logger.debug(
                            f"Found file: {file_info['name']} (path: {file_info['path']})"
                        )
                        files.append(file_info)

                # Handle pagination
                endpoint = response.get("@odata.nextLink")
                if endpoint:
                    # Extract relative endpoint from full URL
                    endpoint = endpoint.replace(self.GRAPH_API_ENDPOINT + "/", "")
                    logger.debug(
                        f"Pagination: Next link found, continuing to next page"
                    )

            logger.info(
                f"Listed {len(files)} files from OneDrive folder {folder_path or 'root'}"
            )
            return files

        except Exception as e:
            logger.error(f"Error listing OneDrive files: {str(e)}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def _download_file(self, file_id: str, file_name: str) -> str:
        """
        Download a file from OneDrive to a temporary location.

        Args:
            file_id: The ID of the file to download.
            file_name: The name of the file.

        Returns:
            The path to the downloaded temporary file.
        """
        if not self.access_token:
            logger.error("OneDrive not authenticated")
            return ""

        try:
            # Get download URL
            endpoint = f"me/drive/items/{file_id}"
            response = self._make_graph_request(endpoint)
            download_url = response.get("@microsoft.graph.downloadUrl")

            if not download_url:
                logger.error(f"No download URL available for OneDrive file {file_name}")
                return ""

            # Download file content
            file_response = requests.get(download_url)
            file_response.raise_for_status()

            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{file_name}", dir=self.temp_dir
            )

            # Write content to temporary file
            temp_file.write(file_response.content)
            temp_file.close()

            logger.info(f"Downloaded OneDrive file to: {temp_file.name}")
            return temp_file.name

        except Exception as e:
            logger.error(f"Error downloading OneDrive file {file_name}: {str(e)}")
            return ""

    def _setup_real_time_monitoring(self) -> None:
        """
        Set up real-time monitoring for OneDrive.

        This implementation uses polling as a fallback. In production,
        you would set up Microsoft Graph webhooks (subscriptions).
        """
        if self.webhook_url:
            logger.info(
                "OneDrive webhook monitoring not yet implemented, using polling"
            )

        # Start polling thread
        self._start_polling()

    def _list_root_folders(self) -> List[Dict[str, Any]]:
        """
        List all folders at the root level of OneDrive.
        This is useful for debugging to see what folders actually exist.

        Returns:
            A list of folder metadata dictionaries.
        """
        if not self.access_token:
            logger.error("OneDrive not authenticated for listing root folders")
            return []

        try:
            logger.info("Listing all root folders in OneDrive")
            endpoint = "me/drive/root/children"
            response = self._make_graph_request(endpoint)

            folders = []
            for item in response.get("value", []):
                if item.get("folder"):
                    folder_info = {
                        "id": item["id"],
                        "name": item["name"],
                        "path": "/"
                        + item["name"],  # Add leading slash for consistency with config
                        "folder_type": "folder",
                        "child_count": item.get("folder", {}).get("childCount", 0),
                    }
                    folders.append(folder_info)

            logger.info(
                f"Found {len(folders)} folders at root level: {[f['name'] for f in folders]}"
            )
            return folders

        except Exception as e:
            logger.error(f"Error listing OneDrive root folders: {str(e)}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def batch_scan(self) -> None:
        """
        Perform batch scanning of all files in configured OneDrive folders.
        """
        logger.info("Starting OneDrive batch scan")

        if not self._authenticate():
            logger.error("Failed to authenticate with OneDrive")
            return

        # First, list all root folders to help with debugging
        logger.info("Checking available root folders in OneDrive")
        root_folders = self._list_root_folders()
        logger.info(f"Available root folders: {[f['name'] for f in root_folders]}")

        # Check if configured folders exist
        configured_paths = [folder_config.get("path") for folder_config in self.folders]
        logger.info(f"Configured folder paths: {configured_paths}")

        # Try to access root directly to verify basic access
        logger.info("Verifying basic OneDrive access by listing root folder")
        root_items = self._list_files("/", recursive=False)
        logger.info(f"Root access successful, found {len(root_items)} items")

        for folder_config in self.folders:
            folder_path = folder_config.get("path", "/")
            folder_name = folder_config.get("name", "Unknown")
            recursive = folder_config.get("recursive", True)

            logger.info(
                f"Scanning OneDrive folder: {folder_name} (path: {folder_path})"
            )

            # Check if this is a path with a leading slash that might cause issues
            if folder_path.startswith("/") and folder_path != "/":
                logger.warning(
                    f"Folder path '{folder_path}' starts with a leading slash, "
                    f"which may cause issues with the Graph API. "
                    f"Consider removing the leading slash."
                )
                # Try with and without leading slash
                try_paths = [folder_path, folder_path.lstrip("/")]
            else:
                try_paths = [folder_path]

            success = False
            for path in try_paths:
                try:
                    logger.info(f"Attempting to list files with path: '{path}'")
                    files = self._list_files(path, recursive)
                    if files:
                        logger.info(
                            f"Successfully listed {len(files)} files from path '{path}'"
                        )
                        for file_info in files:
                            self._process_cloud_file(file_info)
                        success = True
                        break
                    else:
                        logger.warning(f"No files found in path '{path}'")
                except Exception as e:
                    logger.error(f"Error scanning OneDrive folder '{path}': {str(e)}")

            if not success:
                logger.error(
                    f"Failed to access folder {folder_name} with all attempted paths"
                )

        logger.info("OneDrive batch scan completed")
