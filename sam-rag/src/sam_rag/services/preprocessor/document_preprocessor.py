"""
Document preprocessors for various file formats.
"""

import logging
import os
from typing import Dict, Any, List
from sam_rag.services.preprocessor.preprocessor_base import PreprocessorBase, PreprocessedOutput
from sam_rag.services.preprocessor.raw_text_preprocessor import RawTextPreprocessor
import csv

logger = logging.getLogger(__name__)

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
    default_config = {
            "params": {
                "lowercase": "true",
                "normalize_whitespace": "true",
                "remove_stopwords": "false",
                "remove_punctuation": "false",
                "remove_numbers": "false",
                "remove_non_ascii": "false",
                "remove_urls": "true",
                "remove_emails": "false",
                "remove_html_tags": "false"
            }
    }
    default_preprocessor = config.get("default_preprocessor", default_config)
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

    def preprocess(self, file_path: str) -> PreprocessedOutput:
        """
        Preprocess a text file and extract metadata.

        Args:
            file_path: Path to the text file.

        Returns:
            A dictionary containing preprocessed text content and metadata.
        """
        metadata: Dict[str, Any] = {
            "file_path": file_path,
            "custom_tags": [],  # Initialize custom_tags
        }
        text_content = ""
        file_extension = os.path.splitext(file_path.lower())[1]
        metadata["file_type"] = file_extension.lstrip(".")

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                if metadata["file_type"] == "csv":
                    # For CSV, try to extract headers and then read the full content as text
                    try:
                        reader = csv.reader(file)
                        headers = next(reader, None)
                        if headers:
                            metadata["csv_headers"] = headers
                        file.seek(0)  # Reset file pointer to read the whole content
                        text_content = file.read()
                    except csv.Error as e:
                        logger.warning(
                            f"Could not parse CSV headers for {file_path}: {e}"
                        )
                        file.seek(
                            0
                        )  # Ensure reading from start if header extraction failed
                        text_content = file.read()  # Fallback to reading as plain text
                    except Exception as e:
                        logger.warning(
                            f"Unexpected error during CSV processing for {file_path}: {e}"
                        )
                        file.seek(0)
                        text_content = file.read()
                else:
                    text_content = file.read()

            text_config = filter_config(
                self.config, "text"
            )  # Assuming "text" is the generic config key
            # If specific config for md, json, etc. is needed, filter_config might need adjustment
            # or use file_type as key: filter_config(self.config, metadata["file_type"])
            self.text_preprocessor = RawTextPreprocessor(text_config)
            processed_text = self.text_preprocessor.preprocess(text_content)

            return {"text_content": processed_text, "metadata": metadata}
        except Exception as e:
            logger.error(f"Error preprocessing text file {file_path}: {e}")
            # Return minimal metadata in case of error
            return {"text_content": "", "metadata": metadata}


class PDFPreprocessor(PreprocessorBase):
    """
    High-quality PDF preprocessor using pdfplumber (primary) and pypdf (fallback).

    This implementation provides superior text extraction with proper spacing,
    layout preservation, and table handling compared to basic PyPDF2.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the enhanced PDF preprocessor.

        Args:
            config: Configuration dictionary with PDF-specific settings.
        """
        super().__init__(config)
        self.extraction_method = None
        self.quality_threshold = 0.7  # Minimum quality score to accept extraction

    def can_process(self, file_path: str) -> bool:
        """
        Check if this preprocessor can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True if this preprocessor can handle the file, False otherwise.
        """
        return file_path.lower().endswith(".pdf")

    def preprocess(self, file_path: str) -> PreprocessedOutput:
        """
        Preprocess a PDF file using intelligent multi-method extraction.

        Args:
            file_path: Path to the PDF file.

        Returns:
            A dictionary containing high-quality preprocessed text content and metadata.
        """
        logger.info(f"Starting PDF preprocessing for: {file_path}")

        metadata: Dict[str, Any] = {
            "file_path": file_path,
            "file_type": "pdf",
            "custom_tags": [],
            "keywords": [],
            "extraction_method": None,
            "extraction_quality": 0.0,
            "has_tables": False,
            "page_count": 0,
        }

        # Try extraction methods in order of quality
        extraction_result = self._extract_with_intelligence(file_path, metadata)

        if not extraction_result["text_content"]:
            logger.warning(f"No text could be extracted from PDF: {file_path}")
            return {"text_content": "", "metadata": metadata}

        # Apply text preprocessing
        try:
            pdf_config = filter_config(self.config, "pdf")
            text_preprocessor = RawTextPreprocessor(pdf_config)
            processed_text = text_preprocessor.preprocess(
                extraction_result["text_content"]
            )

            logger.info(
                f"Successfully processed PDF {file_path} using {metadata['extraction_method']} "
                f"(quality: {metadata['extraction_quality']:.2f})"
            )

            return {"text_content": processed_text, "metadata": metadata}

        except Exception as e:
            logger.error(f"Error in text preprocessing for {file_path}: {str(e)}")
            return {
                "text_content": extraction_result["text_content"],
                "metadata": metadata,
            }

    def _extract_with_intelligence(
        self, file_path: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Intelligently extract text using the best available method.

        Args:
            file_path: Path to the PDF file.
            metadata: Metadata dictionary to update.

        Returns:
            Dictionary with extracted text content and quality metrics.
        """
        # Method 1: Try pdfplumber (best quality)
        result = self._extract_with_pdfplumber(file_path, metadata)
        if result["quality"] >= self.quality_threshold:
            metadata["extraction_method"] = "pdfplumber"
            metadata["extraction_quality"] = result["quality"]
            return result

        logger.info(
            f"pdfplumber quality too low ({result['quality']:.2f}), trying pypdf fallback"
        )

        # Method 2: Try pypdf (fallback)
        result = self._extract_with_pypdf(file_path, metadata)
        metadata["extraction_method"] = "pypdf"
        metadata["extraction_quality"] = result["quality"]

        return result

    def _extract_with_pdfplumber(
        self, file_path: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract text using pdfplumber with advanced layout analysis.

        Args:
            file_path: Path to the PDF file.
            metadata: Metadata dictionary to update.

        Returns:
            Dictionary with extracted text and quality score.
        """
        try:
            import pdfplumber
            from datetime import datetime

            logger.debug(f"Attempting pdfplumber extraction for: {file_path}")

            text_content = ""
            tables_found = 0

            with pdfplumber.open(file_path) as pdf:
                metadata["page_count"] = len(pdf.pages)

                # Extract metadata from PDF info
                self._extract_metadata_pdfplumber(pdf, metadata)

                # Process each page with advanced extraction
                for page_num, page in enumerate(pdf.pages):
                    logger.debug(f"Processing page {page_num + 1}/{len(pdf.pages)}")

                    # Extract tables first (they often have better structure)
                    tables = page.extract_tables()
                    if tables:
                        tables_found += len(tables)
                        for table in tables:
                            table_text = self._format_table(table)
                            if table_text:
                                text_content += f"\n[TABLE]\n{table_text}\n[/TABLE]\n"

                    # Extract regular text with layout preservation
                    page_text = page.extract_text(
                        x_tolerance=2,  # Horizontal tolerance for character grouping
                        y_tolerance=2,  # Vertical tolerance for line grouping
                        layout=True,  # Preserve layout structure
                        x_density=7.25,  # Character density for word separation
                        y_density=13,  # Line density for paragraph separation
                    )

                    if page_text:
                        # Clean and enhance the extracted text
                        cleaned_text = self._enhance_text_spacing(page_text)
                        text_content += cleaned_text + "\n\n"

            metadata["has_tables"] = tables_found > 0
            if tables_found > 0:
                logger.info(f"Extracted {tables_found} tables from PDF")

            # Calculate quality score
            quality = self._calculate_text_quality(text_content)

            logger.debug(f"pdfplumber extraction completed. Quality: {quality:.2f}")
            return {"text_content": text_content.strip(), "quality": quality}

        except ImportError:
            logger.warning(
                "pdfplumber not available. Install with: pip install pdfplumber"
            )
            return {"text_content": "", "quality": 0.0}
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed for {file_path}: {str(e)}")
            return {"text_content": "", "quality": 0.0}

    def _extract_with_pypdf(
        self, file_path: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract text using pypdf as fallback method.

        Args:
            file_path: Path to the PDF file.
            metadata: Metadata dictionary to update.

        Returns:
            Dictionary with extracted text and quality score.
        """
        try:
            import pypdf
            from datetime import datetime

            logger.debug(f"Attempting pypdf extraction for: {file_path}")

            text_content = ""

            with open(file_path, "rb") as file:
                pdf_reader = pypdf.PdfReader(file)
                metadata["page_count"] = len(pdf_reader.pages)

                # Extract metadata
                self._extract_metadata_pypdf(pdf_reader, metadata)

                # Extract text from all pages
                for page_num, page in enumerate(pdf_reader.pages):
                    logger.debug(
                        f"Processing page {page_num + 1}/{len(pdf_reader.pages)}"
                    )

                    page_text = page.extract_text()
                    if page_text:
                        # Enhance spacing for pypdf extraction
                        enhanced_text = self._enhance_text_spacing(page_text)
                        text_content += enhanced_text + "\n\n"

            # Calculate quality score
            quality = self._calculate_text_quality(text_content)

            logger.debug(f"pypdf extraction completed. Quality: {quality:.2f}")
            return {"text_content": text_content.strip(), "quality": quality}

        except ImportError:
            logger.error("pypdf not available. Install with: pip install pypdf")
            return {"text_content": "", "quality": 0.0}
        except Exception as e:
            logger.error(f"pypdf extraction failed for {file_path}: {str(e)}")
            return {"text_content": "", "quality": 0.0}

    def _extract_metadata_pdfplumber(self, pdf, metadata: Dict[str, Any]) -> None:
        """Extract metadata using pdfplumber."""
        try:
            if hasattr(pdf, "metadata") and pdf.metadata:
                info = pdf.metadata
                if info.get("Title"):
                    metadata["title"] = str(info["Title"])
                if info.get("Author"):
                    metadata["author"] = str(info["Author"])
                if info.get("Subject"):
                    metadata["subject"] = str(info["Subject"])
                if info.get("Keywords"):
                    keywords_str = str(info["Keywords"])
                    metadata["keywords"] = [
                        k.strip() for k in keywords_str.split(",") if k.strip()
                    ]
                if info.get("CreationDate"):
                    try:
                        metadata["creation_date"] = info["CreationDate"].strftime(
                            "%Y-%m-%d"
                        )
                    except (AttributeError, ValueError):
                        metadata["creation_date"] = str(info["CreationDate"])
        except Exception as e:
            logger.debug(f"Could not extract metadata with pdfplumber: {str(e)}")

    def _extract_metadata_pypdf(self, pdf_reader, metadata: Dict[str, Any]) -> None:
        """Extract metadata using pypdf."""
        try:
            if pdf_reader.metadata:
                info = pdf_reader.metadata
                if info.get("/Title"):
                    metadata["title"] = str(info["/Title"])
                if info.get("/Author"):
                    metadata["author"] = str(info["/Author"])
                if info.get("/Subject"):
                    metadata["subject"] = str(info["/Subject"])
                if info.get("/Keywords"):
                    keywords_str = str(info["/Keywords"])
                    metadata["keywords"] = [
                        k.strip() for k in keywords_str.split(",") if k.strip()
                    ]
                if info.get("/CreationDate"):
                    creation_date = str(info["/CreationDate"])
                    if creation_date.startswith("D:"):
                        import re

                        match = re.match(r"D:(\d{8,14})", creation_date)
                        if match:
                            date_digits = match.group(1)
                            try:
                                from datetime import datetime

                                if len(date_digits) >= 14:
                                    parsed_date = datetime.strptime(
                                        date_digits[:14], "%Y%m%d%H%M%S"
                                    )
                                else:
                                    parsed_date = datetime.strptime(
                                        date_digits[:8], "%Y%m%d"
                                    )
                                metadata["creation_date"] = parsed_date.strftime(
                                    "%Y-%m-%d"
                                )
                            except ValueError:
                                metadata["creation_date"] = creation_date
                    else:
                        metadata["creation_date"] = creation_date
        except Exception as e:
            logger.debug(f"Could not extract metadata with pypdf: {str(e)}")

    def _format_table(self, table: List[List[str]]) -> str:
        """
        Format extracted table data into readable text.

        Args:
            table: List of rows, each row is a list of cell values.

        Returns:
            Formatted table as string.
        """
        if not table:
            return ""

        try:
            # Filter out None values and convert to strings
            clean_table = []
            for row in table:
                clean_row = [str(cell) if cell is not None else "" for cell in row]
                clean_table.append(clean_row)

            # Calculate column widths
            if not clean_table:
                return ""

            col_widths = [0] * len(clean_table[0])
            for row in clean_table:
                for i, cell in enumerate(row):
                    if i < len(col_widths):
                        col_widths[i] = max(col_widths[i], len(cell))

            # Format table
            formatted_rows = []
            for row in clean_table:
                formatted_cells = []
                for i, cell in enumerate(row):
                    if i < len(col_widths):
                        formatted_cells.append(cell.ljust(col_widths[i]))
                formatted_rows.append(" | ".join(formatted_cells))

            return "\n".join(formatted_rows)

        except Exception as e:
            logger.debug(f"Error formatting table: {str(e)}")
            return str(table)

    def _enhance_text_spacing(self, text: str) -> str:
        """
        Enhance text spacing and formatting.

        Args:
            text: Raw extracted text.

        Returns:
            Text with improved spacing and formatting.
        """
        if not text:
            return ""

        import re

        # Fix common spacing issues
        # Add space between letters that are stuck together (common in PDF extraction)
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)

        # Fix missing spaces after punctuation
        text = re.sub(r"([.!?])([A-Z])", r"\1 \2", text)

        # Fix missing spaces after numbers
        text = re.sub(r"(\d)([A-Za-z])", r"\1 \2", text)

        # Normalize multiple spaces to single space
        text = re.sub(r" +", " ", text)

        # Normalize line breaks - preserve paragraph structure
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)  # Multiple line breaks to double
        text = re.sub(r"\n +", "\n", text)  # Remove spaces at start of lines

        # Clean up common PDF artifacts
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]", "", text)

        return text.strip()

    def _calculate_text_quality(self, text: str) -> float:
        """
        Calculate quality score for extracted text.

        Args:
            text: Extracted text content.

        Returns:
            Quality score between 0.0 and 1.0.
        """
        if not text or len(text) < 10:
            return 0.0

        import re

        # Calculate various quality metrics
        total_chars = len(text)

        # Count letters, numbers, and spaces
        letters = len(re.findall(r"[a-zA-Z]", text))
        numbers = len(re.findall(r"\d", text))
        spaces = len(re.findall(r"\s", text))

        # Count words (sequences of letters/numbers)
        words = len(re.findall(r"\b\w+\b", text))

        # Quality indicators
        letter_ratio = letters / total_chars if total_chars > 0 else 0
        space_ratio = spaces / total_chars if total_chars > 0 else 0
        word_density = words / (total_chars / 100) if total_chars > 0 else 0

        # Penalize for too many special characters (indicates poor extraction)
        special_chars = total_chars - letters - numbers - spaces
        special_ratio = special_chars / total_chars if total_chars > 0 else 0

        # Calculate composite quality score
        quality = (
            letter_ratio * 0.4  # Good letter content
            + min(space_ratio * 5, 0.3)  # Reasonable spacing (cap at 0.3)
            + min(word_density * 0.1, 0.2)  # Good word density
            + max(0, 0.1 - special_ratio)  # Penalize excessive special chars
        )

        # Bonus for reasonable text length
        if 100 <= total_chars <= 10000:
            quality += 0.1

        return min(quality, 1.0)


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

    def preprocess(self, file_path: str) -> PreprocessedOutput:
        """
        Preprocess a DOCX file and extract metadata.

        Args:
            file_path: Path to the DOCX file.

        Returns:
            A dictionary containing preprocessed text content and metadata.
        """
        file_extension = os.path.splitext(file_path.lower())[1].lstrip(".")
        metadata: Dict[str, Any] = {
            "file_path": file_path,
            "file_type": file_extension,
            "custom_tags": [],
            "keywords": [],
        }
        text_content = ""

        try:
            # Import docx only when needed
            import docx
            from datetime import datetime  # Ensure datetime is imported if not already at top level

            doc_config = filter_config(
                self.config, "doc"
            )  # Assuming "doc" covers .docx as well
            self.text_preprocessor = RawTextPreprocessor(doc_config)

            doc = docx.Document(file_path)

            # Extract core properties
            core_props = doc.core_properties
            if core_props:
                if core_props.title:
                    metadata["title"] = core_props.title
                if core_props.author:
                    metadata["author"] = core_props.author
                if core_props.keywords:  # This is often a string, not a list
                    kw_str = core_props.keywords
                    if kw_str:
                        metadata["keywords"] = [
                            k.strip() for k in kw_str.split(",") if k.strip()
                        ]
                if core_props.created:  # This is a datetime object
                    try:
                        metadata["creation_date"] = core_props.created.strftime(
                            "%Y-%m-%d"
                        )
                    except (
                        AttributeError
                    ):  # If 'created' is not a datetime object for some reason
                        logger.warning(
                            f"Could not format 'created' date for {file_path}: {core_props.created}"
                        )
                        metadata["creation_date"] = str(core_props.created)
                # python-docx does not directly provide a total page count easily.
                # metadata["page_count"] = ... # Omitted

            text_content = "\n".join([paragraph.text for paragraph in doc.paragraphs])

            processed_text = self.text_preprocessor.preprocess(text_content)
            return {"text_content": processed_text, "metadata": metadata}

        except ImportError:
            logger.error(
                "python-docx is not installed. Please install it using: pip install python-docx"
            )
            return {"text_content": "", "metadata": metadata}
        except Exception as e:
            logger.error(f"Error preprocessing DOCX file {file_path}: {e}")
            return {"text_content": "", "metadata": metadata}


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

    def preprocess(self, file_path: str) -> PreprocessedOutput:
        """
        Preprocess an HTML file and extract metadata.

        Args:
            file_path: Path to the HTML file.

        Returns:
            A dictionary containing preprocessed text content and metadata.
        """
        file_extension = os.path.splitext(file_path.lower())[1].lstrip(".")
        metadata: Dict[str, Any] = {
            "file_path": file_path,
            "file_type": file_extension,
            "custom_tags": [],
            "keywords": [],
        }
        text_content = ""

        try:
            # Import BeautifulSoup only when needed
            from bs4 import BeautifulSoup

            html_config = filter_config(self.config, "html")
            self.text_preprocessor = RawTextPreprocessor(html_config)

            with open(file_path, "r", encoding="utf-8") as file:
                soup = BeautifulSoup(file.read(), "html.parser")

                # Extract html_title_tag
                if soup.title and soup.title.string:
                    metadata["html_title_tag"] = soup.title.string.strip()

                # Attempt to extract other metadata from meta tags
                meta_author = soup.find(
                    "meta", attrs={"name": lambda x: x and x.lower() == "author"}
                )
                if meta_author and meta_author.get("content"):
                    metadata["author"] = meta_author["content"].strip()

                meta_keywords = soup.find(
                    "meta", attrs={"name": lambda x: x and x.lower() == "keywords"}
                )
                if meta_keywords and meta_keywords.get("content"):
                    kw_str = meta_keywords["content"].strip()
                    if kw_str:
                        metadata["keywords"] = [
                            k.strip() for k in kw_str.split(",") if k.strip()
                        ]

                # Common meta tags for date: 'date', 'dcterms.created', 'article.published_time'
                date_meta_names = [
                    "date",
                    "creation_date",
                    "dcterms.created",
                    "article:published_time",
                    "og:article:published_time",
                ]
                for name in date_meta_names:
                    meta_date = soup.find(
                        "meta", attrs={"name": lambda x: x and x.lower() == name}
                    )
                    if not meta_date:  # Try property attribute for OpenGraph tags
                        meta_date = soup.find(
                            "meta",
                            attrs={"property": lambda x: x and x.lower() == name},
                        )
                    if meta_date and meta_date.get("content"):
                        # Basic parsing, assuming YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
                        date_str = meta_date["content"].strip()
                        if date_str:
                            metadata["creation_date"] = date_str.split("T")[
                                0
                            ]  # Take only date part
                            break  # Found a date

                # Extract text from HTML
                text_content = soup.get_text(separator=" ", strip=True)

            processed_text = self.text_preprocessor.preprocess(text_content)
            return {"text_content": processed_text, "metadata": metadata}

        except ImportError:
            logger.error(
                "BeautifulSoup is not installed. Please install it using: pip install beautifulsoup4"
            )
            return {"text_content": "", "metadata": metadata}
        except Exception as e:
            logger.error(f"Error preprocessing HTML file {file_path}: {e}")
            return {"text_content": "", "metadata": metadata}


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

    def preprocess(self, file_path: str) -> PreprocessedOutput:
        """
        Preprocess an Excel file and extract metadata.

        Args:
            file_path: Path to the Excel file.

        Returns:
            A dictionary containing preprocessed text content and metadata.
        """
        file_extension = os.path.splitext(file_path.lower())[1].lstrip(".")
        metadata: Dict[str, Any] = {
            "file_path": file_path,
            "file_type": file_extension,
            "custom_tags": [],
            # title, author, keywords, creation_date are not typically standard in Excel files
            # in a way that pandas can easily extract without custom logic or conventions.
        }
        text_content = ""

        try:
            # Import pandas only when needed
            import pandas as pd

            xls_config = filter_config(self.config, "xls")  # or "excel"
            self.text_preprocessor = RawTextPreprocessor(xls_config)

            # Read all sheets
            excel_file = pd.ExcelFile(file_path)
            sheet_names = excel_file.sheet_names
            if sheet_names:  # Add sheet names to metadata if they exist
                metadata["sheet_names"] = sheet_names

            for sheet_name in sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                # Convert dataframe to string
                text_content += f"Sheet: {sheet_name}\n"
                # Optionally, add first row as headers for each sheet if relevant
                # if not df.empty:
                #     metadata[f"sheet_{sheet_name}_headers"] = list(df.columns)
                text_content += df.to_string(index=False) + "\n\n"

            processed_text = self.text_preprocessor.preprocess(text_content)
            return {"text_content": processed_text, "metadata": metadata}

        except ImportError:
            logger.error(
                "pandas is not installed. Please install it using: pip install pandas"
            )
            return {"text_content": "", "metadata": metadata}
        except Exception as e:
            logger.error(f"Error preprocessing Excel file {file_path}: {e}")
            return {"text_content": "", "metadata": metadata}


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

    def preprocess(self, file_path: str) -> PreprocessedOutput:
        """
        Preprocess an ODT file and extract metadata.

        Args:
            file_path: Path to the ODT file.

        Returns:
            A dictionary containing preprocessed text content and metadata.
        """
        metadata: Dict[str, Any] = {
            "file_path": file_path,
            "file_type": "odt",
            "custom_tags": [],
            "keywords": [],
        }
        text_content = ""

        try:
            # Import odfpy only when needed
            from odf import text, teletype
            from odf.opendocument import load
            from odf.meta import Meta  # For metadata extraction
            from datetime import datetime  # For date parsing

            odt_config = filter_config(self.config, "odt")
            self.text_preprocessor = RawTextPreprocessor(odt_config)

            textdoc = load(file_path)

            # Extract metadata
            meta = textdoc.getElementsByType(Meta)
            if meta:
                meta_obj = meta[0]  # Assuming one meta element
                if meta_obj.getTitle():
                    metadata["title"] = meta_obj.getTitle()
                if meta_obj.getCreator():  # Author
                    metadata["author"] = meta_obj.getCreator()
                if meta_obj.getCreationDate():  # Returns datetime object
                    try:
                        metadata["creation_date"] = meta_obj.getCreationDate().strftime(
                            "%Y-%m-%d"
                        )
                    except AttributeError:
                        logger.warning(
                            f"Could not format creation date for ODT {file_path}: {meta_obj.getCreationDate()}"
                        )
                        metadata["creation_date"] = str(meta_obj.getCreationDate())

                # Keywords in ODF are stored as multiple <meta:keyword> elements
                keywords_elements = meta_obj.getElementsByType(text.Keyword)
                if keywords_elements:
                    keywords_list = [
                        teletype.extractText(kw)
                        for kw in keywords_elements
                        if teletype.extractText(kw)
                    ]
                    if keywords_list:
                        metadata["keywords"] = keywords_list

            allparas = textdoc.getElementsByType(text.P)
            text_content = "\n".join([teletype.extractText(para) for para in allparas])

            processed_text = self.text_preprocessor.preprocess(text_content)
            return {"text_content": processed_text, "metadata": metadata}

        except ImportError:
            logger.error(
                "odfpy is not installed. Please install it using: pip install odfpy"
            )
            return {"text_content": "", "metadata": metadata}
        except Exception as e:
            logger.error(f"Error preprocessing ODT file {file_path}: {e}")
            return {"text_content": "", "metadata": metadata}


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

    def preprocess(self, file_path: str) -> PreprocessedOutput:
        """
        Preprocess a CSV file and extract metadata.

        Args:
            file_path: Path to the CSV file.

        Returns:
            A dictionary containing preprocessed text content and metadata.
        """
        metadata: Dict[str, Any] = {
            "file_path": file_path,
            "file_type": "csv",
            "custom_tags": [],
        }
        text_content = ""

        try:
            # Ensure csv module is imported if not already at the top
            # import csv

            with open(file_path, "r", encoding="utf-8", newline="") as file:
                # Extract headers
                try:
                    reader = csv.reader(file)
                    headers = next(reader, None)
                    if headers:
                        metadata["csv_headers"] = headers
                    file.seek(0)  # Reset file pointer to read the whole content
                    text_content = file.read()
                except csv.Error as e:
                    logger.warning(f"Could not parse CSV headers for {file_path}: {e}")
                    file.seek(0)
                    text_content = file.read()  # Fallback to reading as plain text
                except (
                    Exception
                ) as e:  # Catch other potential errors during header reading
                    logger.warning(
                        f"Unexpected error reading CSV headers for {file_path}: {e}"
                    )
                    file.seek(0)
                    text_content = file.read()

            # CSV content is typically not further preprocessed by RawTextPreprocessor in the same way
            # unless specific cleaning (like removing extra spaces in data) is desired.
            # For now, we return the raw text content.
            # If RawTextPreprocessor is needed:
            # csv_config = filter_config(self.config, "csv") # or "text"
            # self.text_preprocessor = RawTextPreprocessor(csv_config)
            # processed_text = self.text_preprocessor.preprocess(text_content)
            # return {"text_content": processed_text, "metadata": metadata}

            return {"text_content": text_content, "metadata": metadata}

        except Exception as e:
            logger.error(f"Error preprocessing CSV file {file_path}: {e}")
            return {"text_content": "", "metadata": metadata}
