"""
Base class for text splitters.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union, TypeVar

# Define a type variable for chunk types
ChunkType = TypeVar("ChunkType", str, Dict[str, Any])


class SplitterBase(ABC):
    """
    Abstract base class for text splitters.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the splitter with the given configuration.

        Args:
            config: A dictionary containing configuration parameters.
        """
        self.config = config or {}

    @abstractmethod
    def split_text(self, text: str) -> List[Union[str, Dict[str, Any]]]:
        """
        Split the text into chunks.

        Args:
            text: The text to split.

        Returns:
            A list of text chunks or dictionaries with 'content' and 'metadata' keys.
        """
        pass

    @abstractmethod
    def can_handle(self, data_type: str) -> bool:
        """
        Check if this splitter can handle the given data type.

        Args:
            data_type: The type of data to split (e.g., "text", "json", "html").

        Returns:
            True if this splitter can handle the data type, False otherwise.
        """
        pass
