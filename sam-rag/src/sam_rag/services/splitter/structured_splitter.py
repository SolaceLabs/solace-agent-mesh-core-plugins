"""
Splitters for structured data formats like JSON, HTML, Markdown, and CSV.
"""

import json
import re
import csv
import io
from typing import Dict, Any, List

from sam_rag.services.splitter.splitter_base import SplitterBase
from sam_rag.services.splitter.text_splitter import RecursiveCharacterTextSplitter

try:
    from bs4 import BeautifulSoup

    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False

try:
    import markdown

    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False


class JSONSplitter(SplitterBase):
    """
    Split JSON data into chunks.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the JSON splitter.

        Args:
            config: A dictionary containing configuration parameters.
                - chunk_size: The size of each chunk (default: 1000).
                - chunk_overlap: The overlap between chunks (default: 200).
        """
        super().__init__(config)
        self.chunk_size = self.config.get("chunk_size", 1000)
        self.chunk_overlap = self.config.get("chunk_overlap", 200)
        self.text_splitter = RecursiveCharacterTextSplitter(
            {"chunk_size": self.chunk_size, "chunk_overlap": self.chunk_overlap}
        )

    def split_text(self, text: str) -> List[str]:
        """
        Split the JSON text into chunks.

        Args:
            text: The JSON text to split.

        Returns:
            A list of text chunks.
        """
        if not text:
            return []

        try:
            # Parse the JSON
            data = json.loads(text)

            # Convert the JSON to a formatted string
            formatted_json = json.dumps(data, indent=2)

            # Use the text splitter to split the formatted JSON
            return self.text_splitter.split_text(formatted_json)
        except json.JSONDecodeError:
            # If the JSON is invalid, fall back to treating it as plain text
            return self.text_splitter.split_text(text)

    def can_handle(self, data_type: str) -> bool:
        """
        Check if this splitter can handle the given data type.

        Args:
            data_type: The type of data to split.

        Returns:
            True if this splitter can handle the data type, False otherwise.
        """
        return data_type.lower() in ["json"]


class RecursiveJSONSplitter(SplitterBase):
    """
    Split JSON data recursively by traversing the structure, outputting small JSON objects as chunks.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the recursive JSON splitter.

        Args:
            config: A dictionary containing configuration parameters.
                - chunk_size: The size of each chunk (default: 1000).
                - chunk_overlap: The overlap between chunks (default: 200).
                - include_metadata: Whether to include metadata about the JSON structure (default: True).
        """
        super().__init__(config)
        self.chunk_size = self.config.get("chunk_size", 1000)
        self.chunk_overlap = self.config.get("chunk_overlap", 200)
        self.include_metadata = self.config.get("include_metadata", True)
        # text_splitter is only used as fallback
        self.text_splitter = RecursiveCharacterTextSplitter(
            {"chunk_size": self.chunk_size, "chunk_overlap": self.chunk_overlap}
        )

    @staticmethod
    def _json_size(data: dict) -> int:
        """Calculate the size of the serialized JSON object."""
        return len(json.dumps(data))

    @staticmethod
    def _set_nested_dict(d: dict, path: list, value: Any) -> None:
        """Set a value in a nested dictionary based on the given path."""
        for key in path[:-1]:
            d = d.setdefault(key, {})
        d[path[-1]] = value

    def _json_split(
        self,
        data: Any,
        current_path: list = None,
        chunks: list = None,
    ) -> list:
        """Split json into maximum size dictionaries while preserving structure."""
        current_path = current_path or []
        if chunks is None:
            chunks = [{}]
        if isinstance(data, dict):
            for key, value in data.items():
                new_path = current_path + [key]
                value_dict = {key: value}
                value_size = self._json_size(value_dict)
                chunk_size = self._json_size(chunks[-1])
                remaining = self.chunk_size - chunk_size
                # If value is a dict or list, try to split its children into chunks
                if isinstance(value, (dict, list)):
                    sub_chunks = self._json_split(value, [], [{}])
                    for sub_chunk in sub_chunks:
                        sub_chunk_size = self._json_size(sub_chunk)
                        chunk_size = self._json_size(chunks[-1])
                        if sub_chunk_size > self.chunk_size:
                            # If still too big, flatten further
                            deeper_chunks = self._json_split(sub_chunk, [], [{}])
                            for deeper_chunk in deeper_chunks:
                                if self._json_size(deeper_chunk) > self.chunk_size:
                                    chunks.append(deeper_chunk)
                                else:
                                    if (
                                        self._json_size(chunks[-1])
                                        + self._json_size(deeper_chunk)
                                        > self.chunk_size
                                    ):
                                        chunks.append({})
                                    chunks[-1].update(deeper_chunk)
                        else:
                            if chunk_size + sub_chunk_size > self.chunk_size:
                                chunks.append({})
                            chunks[-1].update(sub_chunk)
                else:
                    # For primitives, add to current chunk or start new chunk
                    if value_size > self.chunk_size:
                        # Should not happen for primitives, but handle just in case
                        chunks.append({key: value})
                    elif value_size > remaining:
                        if chunk_size > 0:
                            chunks.append({})
                        self._set_nested_dict(chunks[-1], new_path, value)
                    else:
                        self._set_nested_dict(chunks[-1], new_path, value)
        elif isinstance(data, list):
            for idx, item in enumerate(data):
                new_path = current_path + [str(idx)]
                value_dict = {str(idx): item}
                value_size = self._json_size(value_dict)
                chunk_size = self._json_size(chunks[-1])
                remaining = self.chunk_size - chunk_size
                if isinstance(item, (dict, list)):
                    sub_chunks = self._json_split(item, [], [{}])
                    for sub_chunk in sub_chunks:
                        sub_chunk_size = self._json_size(sub_chunk)
                        chunk_size = self._json_size(chunks[-1])
                        if sub_chunk_size > self.chunk_size:
                            deeper_chunks = self._json_split(sub_chunk, [], [{}])
                            for deeper_chunk in deeper_chunks:
                                if self._json_size(deeper_chunk) > self.chunk_size:
                                    chunks.append(deeper_chunk)
                                else:
                                    if (
                                        self._json_size(chunks[-1])
                                        + self._json_size(deeper_chunk)
                                        > self.chunk_size
                                    ):
                                        chunks.append({})
                                    chunks[-1].update(deeper_chunk)
                        else:
                            if chunk_size + sub_chunk_size > self.chunk_size:
                                chunks.append({})
                            chunks[-1].update(sub_chunk)
                else:
                    if value_size > self.chunk_size:
                        chunks.append({str(idx): item})
                    elif value_size > remaining:
                        if chunk_size > 0:
                            chunks.append({})
                        self._set_nested_dict(chunks[-1], new_path, item)
                    else:
                        self._set_nested_dict(chunks[-1], new_path, item)
        else:
            self._set_nested_dict(chunks[-1], current_path, data)
        return [chunk for chunk in chunks if chunk]  # Remove empty chunks

    def split_text(self, text: str) -> List[str]:
        """
        Split the JSON text into chunks by recursively traversing the structure.

        Args:
            text: The JSON text to split.

        Returns:
            A list of JSON-formatted string chunks.
        """
        if not text:
            return []
        try:
            data = json.loads(text)
            chunks = self._json_split(data)
            # Remove the last chunk if it's empty
            if chunks and not chunks[-1]:
                chunks.pop()
            # Convert to JSON-formatted strings
            return [json.dumps(chunk, ensure_ascii=True) for chunk in chunks]
        except json.JSONDecodeError:
            # If the JSON is invalid, fall back to treating it as plain text
            return self.text_splitter.split_text(text)

    def can_handle(self, data_type: str) -> bool:
        """
        Check if this splitter can handle the given data type.

        Args:
            data_type: The type of data to split.

        Returns:
            True if this splitter can handle the data type, False otherwise.
        """
        return data_type.lower() in ["json"]


class HTMLSplitter(SplitterBase):
    """
    Split HTML data into chunks.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the HTML splitter.

        Args:
            config: A dictionary containing configuration parameters.
                - chunk_size: The size of each chunk (default: 1000).
                - chunk_overlap: The overlap between chunks (default: 200).
                - tags_to_extract: The HTML tags to extract (default: ["div", "p", "section", "article"]).
        """
        super().__init__(config)
        self.chunk_size = self.config.get("chunk_size", 1000)
        self.chunk_overlap = self.config.get("chunk_overlap", 200)
        self.tags_to_extract = self.config.get(
            "tags_to_extract", ["div", "p", "section", "article"]
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            {"chunk_size": self.chunk_size, "chunk_overlap": self.chunk_overlap}
        )

        if not BEAUTIFULSOUP_AVAILABLE:
            raise ImportError(
                "The beautifulsoup4 package is required for HTMLSplitter. "
                "Please install it with `pip install beautifulsoup4`."
            ) from None

    def split_text(self, text: str) -> List[str]:
        """
        Split the HTML text into chunks.

        Args:
            text: The HTML text to split.

        Returns:
            A list of text chunks.
        """
        if not text:
            return []

        try:
            # Parse the HTML
            soup = BeautifulSoup(text, "html.parser")

            # Extract chunks from the HTML structure
            chunks = []

            # Find all elements of the specified tags
            for tag in self.tags_to_extract:
                elements = soup.find_all(tag)
                for element in elements:
                    # Extract text from the element
                    element_text = element.get_text(separator=" ", strip=True)
                    if element_text:
                        chunks.append(element_text)

            # If no chunks were extracted or they're too small, fall back to the text splitter
            if not chunks or all(len(chunk) < self.chunk_size / 2 for chunk in chunks):
                # Extract all text from the HTML
                all_text = soup.get_text(separator=" ", strip=True)
                return self.text_splitter.split_text(all_text)

            # Merge small chunks if necessary
            merged_chunks = []
            current_chunk = ""

            for chunk in chunks:
                if len(current_chunk) + len(chunk) <= self.chunk_size:
                    current_chunk += " " + chunk if current_chunk else chunk
                else:
                    if current_chunk:
                        merged_chunks.append(current_chunk)
                    current_chunk = chunk

            if current_chunk:
                merged_chunks.append(current_chunk)

            return merged_chunks
        except Exception:
            # If the HTML parsing fails, fall back to treating it as plain text
            return self.text_splitter.split_text(text)

    def can_handle(self, data_type: str) -> bool:
        """
        Check if this splitter can handle the given data type.

        Args:
            data_type: The type of data to split.

        Returns:
            True if this splitter can handle the data type, False otherwise.
        """
        return data_type.lower() in ["html", "htm"]


class MarkdownSplitter(SplitterBase):
    """
    Split Markdown data into chunks based on headers.
    Inspired by LangChain's MarkdownHeaderTextSplitter.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the Markdown splitter.

        Args:
            config: A dictionary containing configuration parameters.
                - chunk_size: The size of each chunk (default: 1000).
                - chunk_overlap: The overlap between chunks (default: 200).
                - headers_to_split_on: List of headers to split on, ordered by hierarchy level
                  (default: ["#", "##", "###", "####", "#####", "######"]).
                - return_each_line: Whether to return each line with its header metadata (default: False).
        """
        super().__init__(config)
        self.chunk_size = self.config.get("chunk_size", 1000)
        self.chunk_overlap = self.config.get("chunk_overlap", 200)
        self.headers_to_split_on = self.config.get(
            "headers_to_split_on", ["#", "##", "###", "####", "#####", "######"]
        )
        self.strip_headers = self.config.get("strip_headers", False)
        self.text_splitter = RecursiveCharacterTextSplitter(
            {"chunk_size": self.chunk_size, "chunk_overlap": self.chunk_overlap}
        )

        # Create a pattern to match any of the headers, allowing for indentation
        self.header_pattern = re.compile(
            r"^\s*("
            + "|".join(map(re.escape, self.headers_to_split_on))
            + r")\s+(.+)$",
            re.MULTILINE,
        )

    def split_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Split the Markdown text into chunks based on headers.

        Args:
            text: The Markdown text to split.

        Returns:
            A list of dictionaries with 'content' and 'metadata' keys.
        """
        if not text:
            return []

        # Extract all headers and their positions
        headers_with_positions = []
        for match in self.header_pattern.finditer(text):
            header_level = match.group(1)
            header_text = match.group(2).strip()
            position = match.start()
            headers_with_positions.append((header_level, header_text, position))

        # If no headers found, use the text splitter
        if not headers_with_positions:
            chunks = self.text_splitter.split_text(text)
            return [{"content": chunk, "metadata": {}} for chunk in chunks]

        # Sort headers by position
        headers_with_positions.sort(key=lambda x: x[2])

        # Split text by headers
        documents = []
        for i, (header_level, header_text, position) in enumerate(
            headers_with_positions
        ):
            # Get the content until the next header or the end of the text
            if i < len(headers_with_positions) - 1:
                next_position = headers_with_positions[i + 1][2]
                content = text[position:next_position]
            else:
                content = text[position:]

            # Remove the header from the content if strip_headers is True
            if self.strip_headers:
                content = content.split("\n", 1)[1] if "\n" in content else ""

            # Add the document if content is not empty
            if content.strip():
                # Create metadata dictionary with header hierarchy
                metadata = {}
                current_level_idx = self.headers_to_split_on.index(header_level)

                # Map header levels to user-friendly names
                header_name_map = {
                    "#": "Header 1",
                    "##": "Header 2",
                    "###": "Header 3",
                    "####": "Header 4",
                    "#####": "Header 5",
                    "######": "Header 6",
                }

                # Add the current header to metadata
                current_header_name = header_name_map.get(
                    header_level, f"Header {current_level_idx + 1}"
                )
                metadata[current_header_name] = header_text

                # Look back to find parent headers
                for j in range(i - 1, -1, -1):
                    prev_level = headers_with_positions[j][0]
                    prev_level_idx = self.headers_to_split_on.index(prev_level)
                    prev_header_name = header_name_map.get(
                        prev_level, f"Header {prev_level_idx + 1}"
                    )

                    # If this is a parent header level (lower index means higher level)
                    if prev_level_idx < current_level_idx:
                        if prev_header_name not in metadata:
                            metadata[prev_header_name] = headers_with_positions[j][1]

                # Create document with content and metadata
                document = {"content": content.strip(), "metadata": metadata}
                documents.append(document)

        # If documents are too large, split them further
        final_documents = []
        for doc in documents:
            if len(doc["content"]) > self.chunk_size:
                chunks = self.text_splitter.split_text(doc["content"])
                for chunk in chunks:
                    final_documents.append(
                        {"content": chunk, "metadata": doc["metadata"].copy()}
                    )
            else:
                final_documents.append(doc)

        return final_documents

    def can_handle(self, data_type: str) -> bool:
        """
        Check if this splitter can handle the given data type.

        Args:
            data_type: The type of data to split.

        Returns:
            True if this splitter can handle the data type, False otherwise.
        """
        return data_type.lower() in ["markdown", "md"]


class CSVSplitter(SplitterBase):
    """
    Split CSV data into chunks.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the CSV splitter.

        Args:
            config: A dictionary containing configuration parameters.
                - chunk_size: The size of each chunk in rows (default: 100).
                - include_header: Whether to include the header in each chunk (default: True).
        """
        super().__init__(config)
        self.chunk_size = self.config.get("chunk_size", 100)
        self.include_header = self.config.get("include_header", True)

    def split_text(self, text: str) -> List[str]:
        """
        Split the CSV text into chunks.

        Args:
            text: The CSV text to split.

        Returns:
            A list of text chunks.
        """
        if not text:
            return []

        try:
            # Parse the CSV
            csv_reader = csv.reader(io.StringIO(text))
            rows = list(csv_reader)

            if not rows:
                return []

            # Get the header
            header = rows[0]

            # Split the rows into chunks
            chunks = []
            for i in range(1, len(rows), self.chunk_size):
                chunk_rows = rows[i : i + self.chunk_size]

                if self.include_header and i > 1:
                    # Include the header in each chunk
                    chunk_rows = [header] + chunk_rows

                # Convert the chunk back to CSV
                output = io.StringIO()
                csv_writer = csv.writer(output)
                csv_writer.writerows(chunk_rows)
                chunks.append(output.getvalue())

            return chunks
        except Exception:
            # If the CSV parsing fails, fall back to treating it as plain text
            text_splitter = RecursiveCharacterTextSplitter(
                {
                    "chunk_size": self.chunk_size * 100,  # Rough estimate
                    "chunk_overlap": 20,
                }
            )
            return text_splitter.split_text(text)

    def can_handle(self, data_type: str) -> bool:
        """
        Check if this splitter can handle the given data type.

        Args:
            data_type: The type of data to split.

        Returns:
            True if this splitter can handle the data type, False otherwise.
        """
        return data_type.lower() in ["csv"]
