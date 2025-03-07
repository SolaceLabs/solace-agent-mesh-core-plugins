"""
Base class for document preprocessors.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class PreprocessorBase(ABC):
    """
    Abstract base class for document preprocessors.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the preprocessor with the given configuration.

        Args:
            config: A dictionary containing configuration parameters.
        """
        self.config = config or {}

    @abstractmethod
    def preprocess(self, file_path: str) -> str:
        """
        Preprocess a document from the given file path.

        Args:
            file_path: Path to the document file.

        Returns:
            Preprocessed text content.
        """
        pass

    @abstractmethod
    def can_process(self, file_path: str) -> bool:
        """
        Check if this preprocessor can handle the given file type.

        Args:
            file_path: Path to the document file.

        Returns:
            True if this preprocessor can handle the file, False otherwise.
        """
        pass
