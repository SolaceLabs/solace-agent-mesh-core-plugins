"""
Enhanced preprocessor for handling various document formats and preprocessing steps.
"""

import os
from typing import Dict, Any, List, Tuple, Optional
from .preprocessor_base import PreprocessorBase
from .text_preprocessor import TextPreprocessor
from .document_preprocessor import (
    TextFilePreprocessor,
    PDFPreprocessor,
    DocxPreprocessor,
    HTMLPreprocessor,
    ExcelPreprocessor,
    ODTPreprocessor,
)


class EnhancedPreprocessorService:
    """
    Enhanced service for preprocessing documents of various formats.
    This service extends the base PreprocessorService with additional capabilities.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the enhanced preprocessor service.

        Args:
            config: Configuration dictionary.
                - lowercase: Whether to convert text to lowercase (default: True).
                - normalize_unicode: Whether to normalize Unicode characters (default: True).
                - normalize_whitespace: Whether to normalize whitespace (default: True).
                - remove_punctuation: Whether to remove punctuation (default: True).
                - remove_special_chars: Whether to remove special characters (default: True).
                - remove_urls: Whether to remove URLs (default: True).
                - remove_html_tags: Whether to remove HTML tags (default: True).
                - remove_numbers: Whether to remove numbers (default: False).
                - remove_non_ascii: Whether to remove non-ASCII characters (default: False).
        """
        self.config = config or {}
        self.preprocessors: List[PreprocessorBase] = []
        self.text_preprocessor = TextPreprocessor(self.config)
        self._register_preprocessors()

    def _register_preprocessors(self) -> None:
        """
        Register all available preprocessors.
        """
        # Register preprocessors in order of preference
        self.preprocessors = [
            PDFPreprocessor(self.config),
            DocxPreprocessor(self.config),
            HTMLPreprocessor(self.config),
            ExcelPreprocessor(self.config),
            ODTPreprocessor(self.config),
            # TextFilePreprocessor should be last as it handles many generic formats
            TextFilePreprocessor(self.config),
        ]

    def _get_preprocessor(self, file_path: str) -> Optional[PreprocessorBase]:
        """
        Get the appropriate preprocessor for the given file.

        Args:
            file_path: Path to the file.

        Returns:
            The appropriate preprocessor, or None if no suitable preprocessor is found.
        """
        for preprocessor in self.preprocessors:
            if preprocessor.can_process(file_path):
                return preprocessor
        return None

    def _get_file_extension(self, file_path: str) -> str:
        """
        Get the file extension from a file path.

        Args:
            file_path: Path to the file.

        Returns:
            The file extension (lowercase, with leading dot).
        """
        _, ext = os.path.splitext(file_path.lower())
        return ext

    def preprocess_file(self, file_path: str) -> Optional[str]:
        """
        Preprocess a single file.

        Args:
            file_path: Path to the file.

        Returns:
            Preprocessed text content, or None if the file cannot be processed.
        """
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return None

        preprocessor = self._get_preprocessor(file_path)
        if preprocessor:
            try:
                return preprocessor.preprocess(file_path)
            except Exception as e:
                print(f"Error preprocessing file {file_path}: {str(e)}")
                return None
        else:
            print(f"No suitable preprocessor found for file: {file_path}")
            return None

    def preprocess_files(
        self, file_paths: List[str]
    ) -> List[Tuple[str, Optional[str]]]:
        """
        Preprocess multiple files.

        Args:
            file_paths: List of file paths.

        Returns:
            List of tuples containing (file_path, preprocessed_text).
            If a file cannot be processed, the preprocessed_text will be None.
        """
        results = []
        for file_path in file_paths:
            preprocessed_text = self.preprocess_file(file_path)
            results.append((file_path, preprocessed_text))
        return results

    def preprocess_file_list(self, file_paths: List[str]) -> Dict[str, str]:
        """
        Preprocess a list of files and return a dictionary mapping file paths to preprocessed text.

        Args:
            file_paths: List of file paths.

        Returns:
            Dictionary mapping file paths to preprocessed text.
            Files that could not be processed will not be included in the dictionary.
        """
        results = {}
        for file_path, text in self.preprocess_files(file_paths):
            if text:
                results[file_path] = text
        return results

    def get_supported_extensions(self) -> List[str]:
        """
        Get a list of all supported file extensions.

        Returns:
            List of supported file extensions.
        """
        extensions = []
        for preprocessor in self.preprocessors:
            if hasattr(preprocessor, "extensions"):
                extensions.extend(preprocessor.extensions)
            elif isinstance(preprocessor, PDFPreprocessor):
                extensions.append(".pdf")
            elif isinstance(preprocessor, DocxPreprocessor):
                extensions.extend([".doc", ".docx"])
            elif isinstance(preprocessor, HTMLPreprocessor):
                extensions.extend([".html", ".htm"])
            elif isinstance(preprocessor, ExcelPreprocessor):
                extensions.extend([".xls", ".xlsx"])
            elif isinstance(preprocessor, ODTPreprocessor):
                extensions.append(".odt")
        return list(set(extensions))  # Remove duplicates

    def get_file_format(self, file_path: str) -> str:
        """
        Get the file format from a file path.

        Args:
            file_path: Path to the file.

        Returns:
            The file format (e.g., "pdf", "docx", "txt").
        """
        ext = self._get_file_extension(file_path)
        if ext:
            return ext[1:]  # Remove the leading dot
        return "unknown"

    def clean_text(self, text: str) -> str:
        """
        Clean and normalize text using the text preprocessor.

        Args:
            text: The text to clean.

        Returns:
            Cleaned and normalized text.
        """
        return self.text_preprocessor.preprocess(text)
