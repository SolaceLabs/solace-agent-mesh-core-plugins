"""
Unit tests for the document preprocessor classes.
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock, mock_open

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Mock the solace_ai_connector module
sys.modules["solace_ai_connector"] = MagicMock()
sys.modules["solace_ai_connector.common"] = MagicMock()
sys.modules["solace_ai_connector.common.log"] = MagicMock()
sys.modules["solace_ai_connector.common.log"].log = MagicMock()

from src.agents.rag.services.preprocessor.document_preprocessor import (
    filter_config,
    TextFilePreprocessor,
    PDFPreprocessor,
    DocxPreprocessor,
    HTMLPreprocessor,
    ExcelPreprocessor,
    ODTPreprocessor,
    CSVFilePreprocessor,
)


class TestFilterConfig(unittest.TestCase):
    """Test cases for the filter_config function."""

    def test_filter_config_empty(self):
        """Test filter_config with empty config."""
        result = filter_config({}, "text")
        self.assertEqual(result, {})

    def test_filter_config_none(self):
        """Test filter_config with None config."""
        result = filter_config(None, "text")
        self.assertEqual(result, {})

    def test_filter_config_specific_params(self):
        """Test filter_config with specific preprocessor params."""
        config = {
            "preprocessors": {
                "text": {"params": {"lowercase": True, "normalize_whitespace": True}}
            }
        }
        result = filter_config(config, "text")
        self.assertEqual(result, {"lowercase": True, "normalize_whitespace": True})

    def test_filter_config_default_params(self):
        """Test filter_config with default preprocessor params."""
        config = {
            "default_preprocessor": {
                "params": {"lowercase": True, "normalize_whitespace": True}
            }
        }
        result = filter_config(config, "text")
        self.assertEqual(result, {"lowercase": True, "normalize_whitespace": True})

    def test_filter_config_no_params(self):
        """Test filter_config with no params section."""
        config = {"preprocessors": {"text": {}}}
        result = filter_config(config, "text")
        self.assertEqual(result, {})


class TestTextFilePreprocessor(unittest.TestCase):
    """Test cases for the TextFilePreprocessor class."""

    def setUp(self):
        """Set up test fixtures."""
        self.preprocessor = TextFilePreprocessor()

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.preprocessor.config, {})
        self.assertEqual(
            self.preprocessor.extensions,
            [".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".xml"],
        )

    def test_can_process(self):
        """Test can_process method."""
        # Test supported extensions
        self.assertTrue(self.preprocessor.can_process("file.txt"))
        self.assertTrue(self.preprocessor.can_process("file.md"))
        self.assertTrue(self.preprocessor.can_process("file.csv"))
        self.assertTrue(self.preprocessor.can_process("file.json"))
        self.assertTrue(self.preprocessor.can_process("file.yaml"))
        self.assertTrue(self.preprocessor.can_process("file.yml"))
        self.assertTrue(self.preprocessor.can_process("file.xml"))

        # Test uppercase extensions
        self.assertTrue(self.preprocessor.can_process("file.TXT"))
        self.assertTrue(self.preprocessor.can_process("file.MD"))

        # Test unsupported extensions
        self.assertFalse(self.preprocessor.can_process("file.pdf"))
        self.assertFalse(self.preprocessor.can_process("file.docx"))
        self.assertFalse(self.preprocessor.can_process("file"))

    @patch("builtins.open", new_callable=mock_open, read_data="Hello, world!")
    def test_preprocess(self, mock_file):
        """Test preprocess method."""
        # Create a mock for TextPreprocessor
        mock_instance = MagicMock()
        mock_instance.preprocess.return_value = "Preprocessed text"

        # Create a mock for the TextPreprocessor class
        mock_text_preprocessor = MagicMock(return_value=mock_instance)

        # Patch the TextPreprocessor class
        with patch(
            "src.agents.rag.services.preprocessor.document_preprocessor.TextPreprocessor",
            mock_text_preprocessor,
        ):
            # Call the method
            result = self.preprocessor.preprocess("file.txt")

            # Assertions
            mock_file.assert_called_once_with("file.txt", "r", encoding="utf-8")
            mock_instance.preprocess.assert_called_once_with("Hello, world!")
            self.assertEqual(result, "Preprocessed text")

    @patch("builtins.open", side_effect=Exception("File error"))
    def test_preprocess_error(self, mock_file):
        """Test preprocess method with file error."""
        with patch("builtins.print") as mock_print:
            result = self.preprocessor.preprocess("file.txt")
            mock_print.assert_called_once()
            self.assertEqual(result, "")


class TestPDFPreprocessor(unittest.TestCase):
    """Test cases for the PDFPreprocessor class."""

    def setUp(self):
        """Set up test fixtures."""
        self.preprocessor = PDFPreprocessor()

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.preprocessor.config, {})
        self.assertIsNone(self.preprocessor.pdf_reader)

    def test_can_process(self):
        """Test can_process method."""
        # Test supported extensions
        self.assertTrue(self.preprocessor.can_process("file.pdf"))
        self.assertTrue(self.preprocessor.can_process("file.PDF"))

        # Test unsupported extensions
        self.assertFalse(self.preprocessor.can_process("file.txt"))
        self.assertFalse(self.preprocessor.can_process("file.docx"))

    @patch("builtins.open", new_callable=mock_open)
    def test_preprocess(self, mock_file):
        """Test preprocess method."""
        # Create a mock module for PyPDF2
        mock_pypdf2 = MagicMock()

        # Create a mock for PdfReader
        mock_pdf_reader = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page content"
        mock_pdf_reader.return_value.pages = [mock_page, mock_page]  # Two pages

        # Create a mock for TextPreprocessor
        mock_instance = MagicMock()
        mock_instance.preprocess.return_value = "Preprocessed PDF text"

        # Create a mock for the TextPreprocessor class
        mock_text_preprocessor = MagicMock(return_value=mock_instance)

        # Use patch.dict to mock the import
        with patch.dict("sys.modules", {"PyPDF2": mock_pypdf2}):
            # Set the PdfReader attribute on the mock module
            mock_pypdf2.PdfReader = mock_pdf_reader

            # Patch the TextPreprocessor class
            with patch(
                "src.agents.rag.services.preprocessor.document_preprocessor.TextPreprocessor",
                mock_text_preprocessor,
            ):
                # Call the method
                result = self.preprocessor.preprocess("file.pdf")

        # Assertions
        mock_file.assert_called_once_with("file.pdf", "rb")
        mock_instance.preprocess.assert_called_once_with("Page content\nPage content\n")
        self.assertEqual(result, "Preprocessed PDF text")

    @patch("builtins.print")
    def test_preprocess_import_error(self, mock_print):
        """Test preprocess method with ImportError."""
        with patch("builtins.open", new_callable=mock_open):
            with patch.dict("sys.modules", {"PyPDF2": None}):
                with patch("builtins.__import__", side_effect=ImportError("No PyPDF2")):
                    result = self.preprocessor.preprocess("file.pdf")
                    mock_print.assert_called_once()
                    self.assertEqual(result, "")

    @patch("builtins.print")
    def test_preprocess_general_error(self, mock_print):
        """Test preprocess method with general error."""
        with patch("builtins.open", side_effect=Exception("File error")):
            result = self.preprocessor.preprocess("file.pdf")
            mock_print.assert_called_once()
            self.assertEqual(result, "")


class TestDocxPreprocessor(unittest.TestCase):
    """Test cases for the DocxPreprocessor class."""

    def setUp(self):
        """Set up test fixtures."""
        self.preprocessor = DocxPreprocessor()

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.preprocessor.config, {})

    def test_can_process(self):
        """Test can_process method."""
        # Test supported extensions
        self.assertTrue(self.preprocessor.can_process("file.doc"))
        self.assertTrue(self.preprocessor.can_process("file.docx"))
        self.assertTrue(self.preprocessor.can_process("file.DOC"))
        self.assertTrue(self.preprocessor.can_process("file.DOCX"))

        # Test unsupported extensions
        self.assertFalse(self.preprocessor.can_process("file.txt"))
        self.assertFalse(self.preprocessor.can_process("file.pdf"))

    def test_preprocess(self):
        """Test preprocess method."""
        # Create a mock module for docx
        mock_docx = MagicMock()

        # Create a mock for Document
        mock_document = MagicMock()
        mock_paragraph1 = MagicMock()
        mock_paragraph1.text = "Paragraph 1"
        mock_paragraph2 = MagicMock()
        mock_paragraph2.text = "Paragraph 2"
        mock_document.return_value.paragraphs = [mock_paragraph1, mock_paragraph2]

        # Create a mock for TextPreprocessor
        mock_instance = MagicMock()
        mock_instance.preprocess.return_value = "Preprocessed DOCX text"

        # Create a mock for the TextPreprocessor class
        mock_text_preprocessor = MagicMock(return_value=mock_instance)

        # Use patch.dict to mock the import
        with patch.dict("sys.modules", {"docx": mock_docx}):
            # Set the Document attribute on the mock module
            mock_docx.Document = mock_document

            # Patch the TextPreprocessor class
            with patch(
                "src.agents.rag.services.preprocessor.document_preprocessor.TextPreprocessor",
                mock_text_preprocessor,
            ):
                # Call the method
                result = self.preprocessor.preprocess("file.docx")

        # Assertions
        mock_document.assert_called_once_with("file.docx")
        mock_instance.preprocess.assert_called_once_with("Paragraph 1\nParagraph 2")
        self.assertEqual(result, "Preprocessed DOCX text")

    @patch("builtins.print")
    def test_preprocess_import_error(self, mock_print):
        """Test preprocess method with ImportError."""
        with patch.dict("sys.modules", {"docx": None}):
            with patch(
                "builtins.__import__", side_effect=ImportError("No python-docx")
            ):
                result = self.preprocessor.preprocess("file.docx")
                mock_print.assert_called_once()
                self.assertEqual(result, "")

    @patch("builtins.print")
    def test_preprocess_general_error(self, mock_print):
        """Test preprocess method with general error."""
        # Create a mock module for docx
        mock_docx = MagicMock()

        # Create a mock for Document that raises an exception
        mock_document = MagicMock(side_effect=Exception("DOCX error"))

        # Use patch.dict to mock the import
        with patch.dict("sys.modules", {"docx": mock_docx}):
            # Set the Document attribute on the mock module
            mock_docx.Document = mock_document

            # Call the method
            result = self.preprocessor.preprocess("file.docx")

        # Assertions
        mock_print.assert_called_once()
        self.assertEqual(result, "")


class TestHTMLPreprocessor(unittest.TestCase):
    """Test cases for the HTMLPreprocessor class."""

    def setUp(self):
        """Set up test fixtures."""
        self.preprocessor = HTMLPreprocessor()

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.preprocessor.config, {})

    def test_can_process(self):
        """Test can_process method."""
        # Test supported extensions
        self.assertTrue(self.preprocessor.can_process("file.html"))
        self.assertTrue(self.preprocessor.can_process("file.htm"))
        self.assertTrue(self.preprocessor.can_process("file.HTML"))
        self.assertTrue(self.preprocessor.can_process("file.HTM"))

        # Test unsupported extensions
        self.assertFalse(self.preprocessor.can_process("file.txt"))
        self.assertFalse(self.preprocessor.can_process("file.pdf"))

    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="<html><body>Hello</body></html>",
    )
    def test_preprocess(self, mock_file):
        """Test preprocess method."""
        # Create a mock module for bs4
        mock_bs4 = MagicMock()

        # Create a mock for BeautifulSoup
        mock_bs = MagicMock()
        mock_bs_instance = mock_bs.return_value
        mock_bs_instance.get_text.return_value = "Extracted HTML text"

        # Create a mock for TextPreprocessor
        mock_instance = MagicMock()
        mock_instance.preprocess.return_value = "Preprocessed HTML text"

        # Create a mock for the TextPreprocessor class
        mock_text_preprocessor = MagicMock(return_value=mock_instance)

        # Use patch.dict to mock the import
        with patch.dict("sys.modules", {"bs4": mock_bs4}):
            # Set the BeautifulSoup attribute on the mock module
            mock_bs4.BeautifulSoup = mock_bs

            # Patch the TextPreprocessor class
            with patch(
                "src.agents.rag.services.preprocessor.document_preprocessor.TextPreprocessor",
                mock_text_preprocessor,
            ):
                # Call the method
                result = self.preprocessor.preprocess("file.html")

        # Assertions
        mock_file.assert_called_once_with("file.html", "r", encoding="utf-8")
        mock_bs.assert_called_once()
        mock_instance.preprocess.assert_called_once_with("Extracted HTML text")
        self.assertEqual(result, "Preprocessed HTML text")

    @patch("builtins.print")
    def test_preprocess_import_error(self, mock_print):
        """Test preprocess method with ImportError."""
        with patch("builtins.open", new_callable=mock_open, read_data="<html></html>"):
            with patch.dict("sys.modules", {"bs4": None}):
                with patch(
                    "builtins.__import__", side_effect=ImportError("No BeautifulSoup")
                ):
                    result = self.preprocessor.preprocess("file.html")
                    mock_print.assert_called_once()
                    self.assertEqual(result, "")

    @patch("builtins.print")
    def test_preprocess_general_error(self, mock_print):
        """Test preprocess method with general error."""
        with patch("builtins.open", side_effect=Exception("File error")):
            result = self.preprocessor.preprocess("file.html")
            mock_print.assert_called_once()
            self.assertEqual(result, "")


class TestCSVFilePreprocessor(unittest.TestCase):
    """Test cases for the CSVFilePreprocessor class."""

    def setUp(self):
        """Set up test fixtures."""
        self.preprocessor = CSVFilePreprocessor()

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.preprocessor.config, {})
        self.assertEqual(self.preprocessor.extensions, [".csv"])

    def test_can_process(self):
        """Test can_process method."""
        # Test supported extensions
        self.assertTrue(self.preprocessor.can_process("file.csv"))
        self.assertTrue(self.preprocessor.can_process("file.CSV"))

        # Test unsupported extensions
        self.assertFalse(self.preprocessor.can_process("file.txt"))
        self.assertFalse(self.preprocessor.can_process("file.pdf"))

    @patch("builtins.open", new_callable=mock_open, read_data="a,b,c\n1,2,3")
    def test_preprocess(self, mock_file):
        """Test preprocess method."""
        # Call the method
        result = self.preprocessor.preprocess("file.csv")

        # Assertions
        mock_file.assert_called_once_with("file.csv", "r", encoding="utf-8")
        self.assertEqual(result, "a,b,c\n1,2,3")

    @patch("builtins.print")
    def test_preprocess_error(self, mock_print):
        """Test preprocess method with file error."""
        with patch("builtins.open", side_effect=Exception("File error")):
            result = self.preprocessor.preprocess("file.csv")
            mock_print.assert_called_once()
            self.assertEqual(result, "")


# We'll add minimal tests for the remaining preprocessors to ensure coverage
class TestExcelPreprocessor(unittest.TestCase):
    """Test cases for the ExcelPreprocessor class."""

    def setUp(self):
        """Set up test fixtures."""
        self.preprocessor = ExcelPreprocessor()

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.preprocessor.config, {})

    def test_can_process(self):
        """Test can_process method."""
        # Test supported extensions
        self.assertTrue(self.preprocessor.can_process("file.xls"))
        self.assertTrue(self.preprocessor.can_process("file.xlsx"))
        self.assertTrue(self.preprocessor.can_process("file.XLS"))
        self.assertTrue(self.preprocessor.can_process("file.XLSX"))

        # Test unsupported extensions
        self.assertFalse(self.preprocessor.can_process("file.txt"))
        self.assertFalse(self.preprocessor.can_process("file.pdf"))

    @patch("builtins.print")
    def test_preprocess_import_error(self, mock_print):
        """Test preprocess method with ImportError."""
        with patch.dict("sys.modules", {"pandas": None}):
            with patch("builtins.__import__", side_effect=ImportError("No pandas")):
                result = self.preprocessor.preprocess("file.xlsx")
                mock_print.assert_called_once()
                self.assertEqual(result, "")


class TestODTPreprocessor(unittest.TestCase):
    """Test cases for the ODTPreprocessor class."""

    def setUp(self):
        """Set up test fixtures."""
        self.preprocessor = ODTPreprocessor()

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.preprocessor.config, {})

    def test_can_process(self):
        """Test can_process method."""
        # Test supported extensions
        self.assertTrue(self.preprocessor.can_process("file.odt"))
        self.assertTrue(self.preprocessor.can_process("file.ODT"))

        # Test unsupported extensions
        self.assertFalse(self.preprocessor.can_process("file.txt"))
        self.assertFalse(self.preprocessor.can_process("file.pdf"))

    @patch("builtins.print")
    def test_preprocess_import_error(self, mock_print):
        """Test preprocess method with ImportError."""
        with patch.dict("sys.modules", {"odf": None}):
            with patch("builtins.__import__", side_effect=ImportError("No odfpy")):
                result = self.preprocessor.preprocess("file.odt")
                mock_print.assert_called_once()
                self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
