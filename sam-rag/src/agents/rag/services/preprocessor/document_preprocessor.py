"""
Document preprocessors for various file formats.
"""

import os
from typing import Dict, Any
from .preprocessor_base import PreprocessorBase
from .text_preprocessor import TextPreprocessor
from solace_ai_connector.common.log import log as logger


def filter_config(config: Dict[str, Any], key: str) -> Dict[str, Any]:
    """
    Filter the configuration dictionary to get the specific settings for a given key.

    Args:
        config: The original configuration dictionary.
        key: The key to filter by (e.g., 'text', 'pdf', 'html').

    Returns:
        A filtered configuration dictionary with the parameters for the specified file type.
    """
    if not config:
        return {}

    # First try to get file-specific preprocessor config
    preprocessors = config.get("preprocessors", {})
    file_config = preprocessors.get(key, {})

    # Extract the params section if it exists
    if "params" in file_config:
        return file_config.get("params", {})

    # If no specific config found, try to use default preprocessor
    default_preprocessor = config.get("default_preprocessor", {})
    return default_preprocessor.get("params", {})


class TextFilePreprocessor(PreprocessorBase):
    """
    Preprocessor for plain text files.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the text file preprocessor.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)
        self.extensions = [".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".xml"]

    def can_process(self, file_path: str) -> bool:
        """
        Check if this preprocessor can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True if this preprocessor can handle the file, False otherwise.
        """
        ext = os.path.splitext(file_path.lower())[1]
        return ext in self.extensions

    def preprocess(self, file_path: str) -> str:
        """
        Preprocess a text file.

        Args:
            file_path: Path to the text file.

        Returns:
            Preprocessed text content.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                text = file.read()
            text_config = filter_config(self.config, "text")
            self.text_preprocessor = TextPreprocessor(text_config)
            return self.text_preprocessor.preprocess(text)
        except Exception:
            logger.error("Error preprocessing text file.")
            return ""


class PDFPreprocessor(PreprocessorBase):
    """
    Preprocessor for PDF files.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the PDF preprocessor.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)
        # We'll import PyPDF2 only when needed to avoid unnecessary dependencies
        self.pdf_reader = None

    def can_process(self, file_path: str) -> bool:
        """
        Check if this preprocessor can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True if this preprocessor can handle the file, False otherwise.
        """
        return file_path.lower().endswith(".pdf")

    def preprocess(self, file_path: str) -> str:
        """
        Preprocess a PDF file.

        Args:
            file_path: Path to the PDF file.

        Returns:
            Preprocessed text content.
        """
        try:
            # Import PyPDF2 only when needed
            import PyPDF2

            pdf_config = filter_config(self.config, "pdf")
            self.text_preprocessor = TextPreprocessor(pdf_config)

            text = ""
            with open(file_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text() + "\n"

            return self.text_preprocessor.preprocess(text)
        except ImportError:
            logger.error(
                "PyPDF2 is not installed. Please install it using: pip install PyPDF2"
            )
            return ""
        except Exception:
            logger.error("Error preprocessing PDF file.")
            return ""


class DocxPreprocessor(PreprocessorBase):
    """
    Preprocessor for Microsoft Word (DOCX) files.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the DOCX preprocessor.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)

    def can_process(self, file_path: str) -> bool:
        """
        Check if this preprocessor can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True if this preprocessor can handle the file, False otherwise.
        """
        return file_path.lower().endswith((".doc", ".docx"))

    def preprocess(self, file_path: str) -> str:
        """
        Preprocess a DOCX file.

        Args:
            file_path: Path to the DOCX file.

        Returns:
            Preprocessed text content.
        """
        try:
            # Import docx only when needed
            import docx

            doc_config = filter_config(self.config, "doc")
            self.text_preprocessor = TextPreprocessor(doc_config)

            doc = docx.Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])

            return self.text_preprocessor.preprocess(text)
        except ImportError:
            logger.error(
                "python-docx is not installed. Please install it using: pip install python-docx"
            )
            return ""
        except Exception:
            logger.error("Error preprocessing DOCX file.")
            return ""


class HTMLPreprocessor(PreprocessorBase):
    """
    Preprocessor for HTML files.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the HTML preprocessor.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)

    def can_process(self, file_path: str) -> bool:
        """
        Check if this preprocessor can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True if this preprocessor can handle the file, False otherwise.
        """
        return file_path.lower().endswith((".html", ".htm"))

    def preprocess(self, file_path: str) -> str:
        """
        Preprocess an HTML file.

        Args:
            file_path: Path to the HTML file.

        Returns:
            Preprocessed text content.
        """
        try:
            # Import BeautifulSoup only when needed
            from bs4 import BeautifulSoup

            html_config = filter_config(self.config, "html")
            self.text_preprocessor = TextPreprocessor(html_config)

            with open(file_path, "r", encoding="utf-8") as file:
                soup = BeautifulSoup(file.read(), "html.parser")
                # Extract text from HTML
                text = soup.get_text(separator=" ", strip=True)

            return self.text_preprocessor.preprocess(text)
        except ImportError:
            logger.error(
                "BeautifulSoup is not installed. Please install it using: pip install beautifulsoup4"
            )
            return ""
        except Exception:
            logger.error("Error preprocessing HTML file.")
            return ""


class ExcelPreprocessor(PreprocessorBase):
    """
    Preprocessor for Excel files.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the Excel preprocessor.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)

    def can_process(self, file_path: str) -> bool:
        """
        Check if this preprocessor can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True if this preprocessor can handle the file, False otherwise.
        """
        return file_path.lower().endswith((".xls", ".xlsx"))

    def preprocess(self, file_path: str) -> str:
        """
        Preprocess an Excel file.

        Args:
            file_path: Path to the Excel file.

        Returns:
            Preprocessed text content.
        """
        try:
            # Import pandas only when needed
            import pandas as pd

            xls_config = filter_config(self.config, "xls")
            self.text_preprocessor = TextPreprocessor(xls_config)

            # Read all sheets
            excel_file = pd.ExcelFile(file_path)
            text = ""

            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                # Convert dataframe to string
                text += f"Sheet: {sheet_name}\n"
                text += df.to_string(index=False) + "\n\n"

            return self.text_preprocessor.preprocess(text)
        except ImportError:
            logger.error(
                "pandas is not installed. Please install it using: pip install pandas"
            )
            return ""
        except Exception:
            logger.error("Error preprocessing Excel file.")
            return ""


class ODTPreprocessor(PreprocessorBase):
    """
    Preprocessor for OpenDocument Text (ODT) files.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the ODT preprocessor.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)

    def can_process(self, file_path: str) -> bool:
        """
        Check if this preprocessor can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True if this preprocessor can handle the file, False otherwise.
        """
        return file_path.lower().endswith(".odt")

    def preprocess(self, file_path: str) -> str:
        """
        Preprocess an ODT file.

        Args:
            file_path: Path to the ODT file.

        Returns:
            Preprocessed text content.
        """
        try:
            # Import odfpy only when needed
            from odf import text, teletype
            from odf.opendocument import load

            odt_config = filter_config(self.config, "odt")
            self.text_preprocessor = TextPreprocessor(odt_config)

            textdoc = load(file_path)
            allparas = textdoc.getElementsByType(text.P)
            content = "\n".join([teletype.extractText(para) for para in allparas])

            return self.text_preprocessor.preprocess(content)
        except ImportError:
            logger.error(
                "odfpy is not installed. Please install it using: pip install odfpy"
            )
            return ""
        except Exception:
            logger.error("Error preprocessing ODT file.")
            return ""


class CSVFilePreprocessor(PreprocessorBase):
    """
    Preprocessor for plain text files.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the text file preprocessor.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)
        self.extensions = [".csv"]

    def can_process(self, file_path: str) -> bool:
        """
        Check if this preprocessor can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True if this preprocessor can handle the file, False otherwise.
        """
        ext = os.path.splitext(file_path.lower())[1]
        return ext in self.extensions

    def preprocess(self, file_path: str) -> str:
        """
        Preprocess a text file.

        Args:
            file_path: Path to the text file.

        Returns:
            Return text content.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read()
            return content
        except Exception:
            logger.error("Error preprocessing text file.")
            return ""
