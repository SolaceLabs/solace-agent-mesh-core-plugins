"""
Unit tests for the PreprocessorService class.
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock, mock_open

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.agents.rag.services.preprocessor.preprocessor_service import PreprocessorService
from src.agents.rag.services.preprocessor.document_preprocessor import (
    TextFilePreprocessor,
    PDFPreprocessor,
    DocxPreprocessor,
    HTMLPreprocessor,
    ExcelPreprocessor,
    ODTPreprocessor,
    CSVFilePreprocessor,
)


class TestPreprocessorService(unittest.TestCase):
    """Test cases for the PreprocessorService class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "preprocessors": {
                "text": {"params": {"lowercase": True, "normalize_whitespace": True}},
                "pdf": {"params": {"remove_urls": True}},
            },
            "default_preprocessor": {"params": {"normalize_unicode": True}},
        }
        self.preprocessor_service = PreprocessorService(self.config)

    def test_init_default_config(self):
        """Test initialization with default config."""
        preprocessor = PreprocessorService()
        self.assertEqual(preprocessor.config, {})
        self.assertEqual(
            len(preprocessor.preprocessors), 7
        )  # 7 registered preprocessors

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        self.assertEqual(self.preprocessor_service.config, self.config)
        self.assertEqual(len(self.preprocessor_service.preprocessors), 7)

    def test_register_preprocessors(self):
        """Test _register_preprocessors method."""
        # Check that all preprocessors are registered
        preprocessors = self.preprocessor_service.preprocessors
        self.assertEqual(len(preprocessors), 7)

        # Check the order of preprocessors (important for precedence)
        self.assertIsInstance(preprocessors[0], PDFPreprocessor)
        self.assertIsInstance(preprocessors[1], DocxPreprocessor)
        self.assertIsInstance(preprocessors[2], HTMLPreprocessor)
        self.assertIsInstance(preprocessors[3], ExcelPreprocessor)
        self.assertIsInstance(preprocessors[4], ODTPreprocessor)
        self.assertIsInstance(preprocessors[5], CSVFilePreprocessor)
        self.assertIsInstance(preprocessors[6], TextFilePreprocessor)

    def test_get_preprocessor(self):
        """Test _get_preprocessor method."""
        # Test PDF file
        preprocessor = self.preprocessor_service._get_preprocessor("file.pdf")
        self.assertIsInstance(preprocessor, PDFPreprocessor)

        # Test DOCX file
        preprocessor = self.preprocessor_service._get_preprocessor("file.docx")
        self.assertIsInstance(preprocessor, DocxPreprocessor)

        # Test HTML file
        preprocessor = self.preprocessor_service._get_preprocessor("file.html")
        self.assertIsInstance(preprocessor, HTMLPreprocessor)

        # Test Excel file
        preprocessor = self.preprocessor_service._get_preprocessor("file.xlsx")
        self.assertIsInstance(preprocessor, ExcelPreprocessor)

        # Test ODT file
        preprocessor = self.preprocessor_service._get_preprocessor("file.odt")
        self.assertIsInstance(preprocessor, ODTPreprocessor)

        # Test CSV file
        preprocessor = self.preprocessor_service._get_preprocessor("file.csv")
        self.assertIsInstance(preprocessor, CSVFilePreprocessor)

        # Test text file
        preprocessor = self.preprocessor_service._get_preprocessor("file.txt")
        self.assertIsInstance(preprocessor, TextFilePreprocessor)

        # Test unsupported file
        preprocessor = self.preprocessor_service._get_preprocessor("file.unknown")
        self.assertIsNone(preprocessor)

    def test_get_file_extension(self):
        """Test _get_file_extension method."""
        self.assertEqual(
            self.preprocessor_service._get_file_extension("file.pdf"), ".pdf"
        )
        self.assertEqual(
            self.preprocessor_service._get_file_extension("file.PDF"), ".pdf"
        )
        self.assertEqual(
            self.preprocessor_service._get_file_extension("path/to/file.txt"), ".txt"
        )
        self.assertEqual(self.preprocessor_service._get_file_extension("file"), "")

    @patch("os.path.exists", return_value=True)
    def test_preprocess_file(self, mock_exists):
        """Test preprocess_file method."""
        # Mock the preprocessor
        mock_preprocessor = MagicMock()
        mock_preprocessor.preprocess.return_value = "Preprocessed content"

        # Replace _get_preprocessor to return our mock
        with patch.object(
            self.preprocessor_service,
            "_get_preprocessor",
            return_value=mock_preprocessor,
        ):
            result = self.preprocessor_service.preprocess_file("file.txt")
            self.assertEqual(result, "Preprocessed content")
            mock_preprocessor.preprocess.assert_called_once_with("file.txt")

    @patch("os.path.exists", return_value=False)
    @patch("builtins.print")
    def test_preprocess_file_not_found(self, mock_print, mock_exists):
        """Test preprocess_file method with file not found."""
        result = self.preprocessor_service.preprocess_file("nonexistent.txt")
        self.assertIsNone(result)
        mock_print.assert_called_once()

    @patch("os.path.exists", return_value=True)
    @patch("builtins.print")
    def test_preprocess_file_no_preprocessor(self, mock_print, mock_exists):
        """Test preprocess_file method with no suitable preprocessor."""
        # Replace _get_preprocessor to return None
        with patch.object(
            self.preprocessor_service, "_get_preprocessor", return_value=None
        ):
            result = self.preprocessor_service.preprocess_file("file.unknown")
            self.assertIsNone(result)
            mock_print.assert_called_once()

    @patch("os.path.exists", return_value=True)
    @patch("builtins.print")
    def test_preprocess_file_error(self, mock_print, mock_exists):
        """Test preprocess_file method with preprocessing error."""
        # Mock the preprocessor to raise an exception
        mock_preprocessor = MagicMock()
        mock_preprocessor.preprocess.side_effect = Exception("Preprocessing error")

        # Replace _get_preprocessor to return our mock
        with patch.object(
            self.preprocessor_service,
            "_get_preprocessor",
            return_value=mock_preprocessor,
        ):
            result = self.preprocessor_service.preprocess_file("file.txt")
            self.assertIsNone(result)
            mock_print.assert_called_once()

    @patch("os.path.exists", return_value=True)
    def test_preprocess_files(self, mock_exists):
        """Test preprocess_files method."""
        # Mock the preprocessor
        mock_preprocessor = MagicMock()
        mock_preprocessor.preprocess.side_effect = ["Content 1", "Content 2", None]

        # Replace _get_preprocessor to return our mock
        with patch.object(
            self.preprocessor_service,
            "_get_preprocessor",
            return_value=mock_preprocessor,
        ):
            result = self.preprocessor_service.preprocess_files(
                ["file1.txt", "file2.txt", "file3.txt"]
            )
            self.assertEqual(len(result), 3)
            self.assertEqual(result[0], ("file1.txt", "Content 1"))
            self.assertEqual(result[1], ("file2.txt", "Content 2"))
            self.assertEqual(result[2], ("file3.txt", None))

    @patch("os.path.exists", return_value=True)
    def test_preprocess_file_list(self, mock_exists):
        """Test preprocess_file_list method."""
        # Mock the preprocessor
        mock_preprocessor = MagicMock()
        mock_preprocessor.preprocess.side_effect = ["Content 1", "Content 2", None]

        # Replace _get_preprocessor to return our mock
        with patch.object(
            self.preprocessor_service,
            "_get_preprocessor",
            return_value=mock_preprocessor,
        ):
            result = self.preprocessor_service.preprocess_file_list(
                ["file1.txt", "file2.txt", "file3.txt"]
            )
            self.assertEqual(len(result), 2)  # Only 2 files had content
            self.assertEqual(result["file1.txt"], "Content 1")
            self.assertEqual(result["file2.txt"], "Content 2")
            self.assertNotIn("file3.txt", result)

    def test_get_supported_extensions(self):
        """Test get_supported_extensions method."""
        extensions = self.preprocessor_service.get_supported_extensions()
        self.assertIn(".pdf", extensions)
        self.assertIn(".doc", extensions)
        self.assertIn(".docx", extensions)
        self.assertIn(".html", extensions)
        self.assertIn(".htm", extensions)
        self.assertIn(".xls", extensions)
        self.assertIn(".xlsx", extensions)
        self.assertIn(".odt", extensions)
        self.assertIn(".csv", extensions)

        # Check for duplicates
        self.assertEqual(len(extensions), len(set(extensions)))

    def test_get_file_format(self):
        """Test get_file_format method."""
        self.assertEqual(self.preprocessor_service.get_file_format("file.pdf"), "pdf")
        self.assertEqual(self.preprocessor_service.get_file_format("file.PDF"), "pdf")
        self.assertEqual(
            self.preprocessor_service.get_file_format("path/to/file.txt"), "txt"
        )
        self.assertEqual(self.preprocessor_service.get_file_format("file"), "unknown")


if __name__ == "__main__":
    unittest.main()
