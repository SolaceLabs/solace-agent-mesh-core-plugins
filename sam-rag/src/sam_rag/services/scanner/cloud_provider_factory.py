"""
Cloud Provider Factory for creating different cloud storage data sources.

This module provides a factory pattern for instantiating different cloud storage
providers in a consistent and extensible manner.
"""

from typing import Dict, List, Any, Type
from solace_ai_connector.common.log import log as logger

from sam_rag.services.scanner.datasource_base import DataSource


class CloudProviderFactory:
    """
    Factory class for creating cloud storage data sources.

    This factory provides a centralized way to create different cloud storage
    data sources while maintaining consistency and extensibility.
    """

    # Registry of available cloud providers
    _providers = {}

    @classmethod
    def register_provider(
        cls, provider_type: str, provider_class: Type[DataSource]
    ) -> None:
        """
        Register a new cloud provider.

        Args:
            provider_type: The type identifier for the provider (e.g., 'google_drive').
            provider_class: The class that implements the provider.
        """
        cls._providers[provider_type] = provider_class
        logger.info(f"Registered cloud provider: {provider_type}")

    @classmethod
    def get_available_providers(cls) -> List[str]:
        """
        Get a list of available cloud providers.

        Returns:
            A list of provider type identifiers.
        """
        return list(cls._providers.keys())

    @classmethod
    def create_provider(
        cls, provider_type: str, config: Dict, ingested_documents: List[str], pipeline
    ) -> DataSource:
        """
        Create a cloud storage data source instance.

        Args:
            provider_type: The type of provider to create.
            config: Configuration dictionary for the provider.
            ingested_documents: List of already ingested documents.
            pipeline: The processing pipeline instance.

        Returns:
            An instance of the requested cloud storage data source.

        Raises:
            ValueError: If the provider type is not supported.
            ImportError: If the provider dependencies are not available.
        """
        if provider_type not in cls._providers:
            available = ", ".join(cls.get_available_providers())
            raise ValueError(
                f"Unsupported cloud provider: {provider_type}. "
                f"Available providers: {available}"
            )

        provider_class = cls._providers[provider_type]

        try:
            logger.info(f"Creating cloud provider instance: {provider_type}")
            return provider_class(config, ingested_documents, pipeline)
        except ImportError as e:
            logger.error(
                f"Failed to create {provider_type} provider: missing dependencies"
            )
            raise ImportError(
                f"Missing dependencies for {provider_type} provider. "
                f"Please install the required packages. Error: {str(e)}"
            ) from e
        except Exception as e:
            logger.error(f"Failed to create {provider_type} provider: {str(e)}")
            raise

    @classmethod
    def is_provider_available(cls, provider_type: str) -> bool:
        """
        Check if a provider is available and its dependencies are installed.

        Args:
            provider_type: The type of provider to check.

        Returns:
            True if the provider is available, False otherwise.
        """
        if provider_type not in cls._providers:
            return False

        provider_class = cls._providers[provider_type]

        try:
            # Try to check if the provider's dependencies are available
            # This is a basic check - each provider should implement more specific checks
            return hasattr(provider_class, "__init__")
        except Exception:
            return False


# Auto-register available providers
def _register_available_providers():
    """
    Automatically register available cloud providers.

    This function attempts to import and register cloud providers that are available.
    If a provider's dependencies are not installed, it will be skipped.
    """

    # Try to register Google Drive provider
    try:
        from .providers.google_drive import GoogleDriveDataSource

        CloudProviderFactory.register_provider("google_drive", GoogleDriveDataSource)
    except ImportError:
        logger.debug("Google Drive provider not available - missing dependencies")

    # Try to register OneDrive provider
    try:
        from .providers.onedrive import OneDriveDataSource

        CloudProviderFactory.register_provider("onedrive", OneDriveDataSource)
    except ImportError:
        logger.debug("OneDrive provider not available - missing dependencies")

    # Try to register AWS S3 provider
    try:
        from .providers.s3 import S3DataSource

        CloudProviderFactory.register_provider("s3", S3DataSource)
    except ImportError:
        logger.debug("AWS S3 provider not available - missing dependencies")

    # Try to register Google Cloud Storage provider
    try:
        from .providers.gcs import GCSDataSource

        CloudProviderFactory.register_provider("gcs", GCSDataSource)
    except ImportError:
        logger.debug(
            "Google Cloud Storage provider not available - missing dependencies"
        )


# Register providers when module is imported
_register_available_providers()
