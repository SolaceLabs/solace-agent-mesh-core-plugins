"""
AWS S3 Data Source implementation for the scanner component.

This module provides AWS S3 integration with boto3, batch scanning,
real-time monitoring via S3 events, and file processing capabilities.
"""

import os
import tempfile
import threading
import time
from typing import Dict, List, Any, Optional
from solace_ai_connector.common.log import log as logger

from sam_rag.services.cloud_storage import CloudStorageDataSource

# Try to import AWS S3 dependencies
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    logger.warning("AWS S3 dependencies not available. Install with: pip install boto3")


class S3DataSource(CloudStorageDataSource):
    """
    AWS S3 implementation of CloudStorageDataSource.

    Provides boto3 integration, batch scanning, S3 event notifications,
    and file processing for S3 objects.
    """

    def __init__(self, config: Dict, ingested_documents: List[str], pipeline):
        """
        Initialize the S3DataSource.

        Args:
            config: Configuration dictionary for S3.
            ingested_documents: List of already ingested documents.
            pipeline: The processing pipeline instance.
        """
        if not S3_AVAILABLE:
            raise ImportError(
                "AWS S3 dependencies not available. " "Install with: pip install boto3"
            )

        super().__init__(config, ingested_documents, pipeline)
        self.provider_name = "s3"

        # S3 specific configuration
        self.s3_client = None
        self.bucket_name = ""
        self.prefix = ""
        self.region = "us-east-1"
        self.access_key_id = ""
        self.secret_access_key = ""

        # Initialize the service
        self.process_config(config)

    def process_config(self, source: Dict = {}) -> None:
        """
        Process S3 specific configuration.

        Args:
            source: Configuration dictionary containing S3 settings.
        """
        # Get S3 configuration
        self.bucket_name = source.get("bucket_name", "")
        self.prefix = source.get("prefix", "")
        self.region = source.get("region", "us-east-1")
        self.access_key_id = source.get("access_key_id", "")
        self.secret_access_key = source.get("secret_access_key", "")

        if not self.bucket_name:
            raise ValueError("S3 bucket_name is required")

        # Get folder configurations (S3 prefixes)
        self.folders = source.get("folders", [])
        if not self.folders and self.prefix:
            # Use prefix as default folder
            self.folders = [
                {"prefix": self.prefix, "name": "Default", "recursive": True}
            ]
        elif not self.folders:
            # Default to root
            self.folders = [{"prefix": "", "name": "Root", "recursive": True}]

        # Get real-time monitoring configuration
        real_time_config = source.get("real_time", {})
        self.real_time_enabled = real_time_config.get("enabled", False)
        self.sqs_queue_url = real_time_config.get("sqs_queue_url")
        self.polling_interval = real_time_config.get("polling_interval", 300)

        logger.info(
            f"S3 configuration processed: bucket={self.bucket_name}, "
            f"{len(self.folders)} prefixes, real-time: {self.real_time_enabled}"
        )

    def _authenticate(self) -> bool:
        """
        Authenticate with AWS S3 using boto3.

        Returns:
            True if authentication successful, False otherwise.
        """
        try:
            # Create S3 client
            session = boto3.Session(
                aws_access_key_id=self.access_key_id or None,
                aws_secret_access_key=self.secret_access_key or None,
                region_name=self.region,
            )

            self.s3_client = session.client("s3")

            # Test connection by listing bucket
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info("S3 authentication successful")
            return True

        except NoCredentialsError:
            logger.error("S3 credentials not found")
            return False
        except ClientError as e:
            logger.error(f"S3 authentication failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"S3 authentication failed: {str(e)}")
            return False

    def _list_files(
        self, prefix: str = None, recursive: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List files in S3 bucket.

        Args:
            prefix: The S3 prefix to list files from.
            recursive: Whether to list files recursively.

        Returns:
            A list of file metadata dictionaries.
        """
        if not self.s3_client:
            logger.error("S3 client not initialized")
            return []

        files = []

        try:
            # List objects with pagination
            paginator = self.s3_client.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(
                Bucket=self.bucket_name, Prefix=prefix or ""
            )

            for page in page_iterator:
                objects = page.get("Contents", [])

                for obj in objects:
                    # Skip directories (objects ending with /)
                    if obj["Key"].endswith("/"):
                        continue

                    # Handle recursive flag
                    if not recursive and prefix:
                        # Check if object is in subdirectory
                        relative_key = obj["Key"][len(prefix) :].lstrip("/")
                        if "/" in relative_key:
                            continue

                    # Add file metadata
                    files.append(
                        {
                            "id": obj["Key"],
                            "name": os.path.basename(obj["Key"]),
                            "key": obj["Key"],
                            "size": obj["Size"],
                            "modified_time": obj["LastModified"].isoformat(),
                            "etag": obj["ETag"].strip('"'),
                            "storage_class": obj.get("StorageClass", "STANDARD"),
                        }
                    )

            logger.info(
                f"Listed {len(files)} files from S3 bucket {self.bucket_name} with prefix {prefix or 'root'}"
            )
            return files

        except ClientError as e:
            logger.error(f"Error listing S3 files: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error listing S3 files: {str(e)}")
            return []

    def _download_file(self, file_key: str, file_name: str) -> str:
        """
        Download a file from S3 to a temporary location.

        Args:
            file_key: The S3 key of the file to download.
            file_name: The name of the file.

        Returns:
            The path to the downloaded temporary file.
        """
        if not self.s3_client:
            logger.error("S3 client not initialized")
            return ""

        try:
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{file_name}", dir=self.temp_dir
            )
            temp_file.close()

            # Download file from S3
            self.s3_client.download_file(self.bucket_name, file_key, temp_file.name)

            logger.info(f"Downloaded S3 file to: {temp_file.name}")
            return temp_file.name

        except ClientError as e:
            logger.error(f"Error downloading S3 file {file_name}: {str(e)}")
            return ""
        except Exception as e:
            logger.error(f"Error downloading S3 file {file_name}: {str(e)}")
            return ""

    def _setup_real_time_monitoring(self) -> None:
        """
        Set up real-time monitoring for S3.

        This implementation uses polling as a fallback. In production,
        you would set up S3 Event Notifications with SQS/SNS.
        """
        if self.sqs_queue_url:
            logger.info("S3 SQS event monitoring not yet implemented, using polling")

        # Start polling thread
        self._start_polling()

    def batch_scan(self) -> None:
        """
        Perform batch scanning of all files in configured S3 prefixes.
        """
        logger.info("Starting S3 batch scan")

        if not self._authenticate():
            logger.error("Failed to authenticate with S3")
            return

        for folder_config in self.folders:
            prefix = folder_config.get("prefix", "")
            folder_name = folder_config.get("name", "Unknown")
            recursive = folder_config.get("recursive", True)

            logger.info(f"Scanning S3 prefix: {folder_name} (prefix: {prefix})")

            try:
                files = self._list_files(prefix, recursive)
                for file_info in files:
                    # Override file_id to use S3 key for download
                    file_info["id"] = file_info["key"]
                    self._process_cloud_file(file_info)
            except Exception as e:
                logger.error(f"Error scanning S3 prefix {folder_name}: {str(e)}")

        logger.info("S3 batch scan completed")
