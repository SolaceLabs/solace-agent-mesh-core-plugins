from abc import ABC, abstractmethod
from typing import List, Dict, Any


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
