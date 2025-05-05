"""
Text splitters for unstructured text.
"""

from typing import Dict, Any, List
import re

from .splitter_base import SplitterBase

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


class CharacterTextSplitter(SplitterBase):
    """
    Implementation of splitting text that looks at characters.
    Adapted from LangChain's CharacterTextSplitter.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the character text splitter.

        Args:
            config: A dictionary containing configuration parameters.
                - chunk_size: The size of each chunk (default: 1000).
                - chunk_overlap: The overlap between chunks (default: 200).
                - separator: The separator to use for splitting (default: "\n\n").
                - is_separator_regex: Whether the separator is a regex (default: False).
                - keep_separator: Whether to keep the separator in the chunks (default: True).
                - strip_whitespace: Whether to strip whitespace from the chunks (default: True).
        """
        super().__init__(config)
        self.chunk_size = self.config.get("chunk_size", 1000)
        self.chunk_overlap = self.config.get("chunk_overlap", 200)
        self.separator = self.config.get("separator", "\n")
        self.is_separator_regex = self.config.get("is_separator_regex", False)
        self.keep_separator = self.config.get("keep_separator", True)
        self.strip_whitespace = self.config.get("strip_whitespace", True)
        self._length_function = len

    def split_text(self, text: str) -> List[str]:
        """
        Split the text into chunks.

        Args:
            text: The text to split.

        Returns:
            A list of text chunks.
        """
        if not text:
            return []

        # First, get appropriate splits
        if self.is_separator_regex:
            splits = re.split(self.separator, text)
        else:
            splits = text.split(self.separator)

        # Now, clean and filter out empty splits
        cleaned_splits = []
        separator = (
            self.separator
            if not self.is_separator_regex
            else re.search(self.separator, text).group()
            if re.search(self.separator, text)
            else ""
        )

        for i, split in enumerate(splits):
            if self.strip_whitespace:
                split = split.strip()
            if split == "":
                continue
            if i == len(splits) - 1:
                cleaned_splits.append(split)
            elif self.keep_separator:
                cleaned_splits.append(split + separator)
            else:
                cleaned_splits.append(split)

        # If we have no splits, return the original text
        if not cleaned_splits:
            if self.strip_whitespace:
                text = text.strip()
            return [text] if text else []

        # Create chunks with proper overlap
        return self._create_overlapping_chunks(cleaned_splits)

    def _create_overlapping_chunks(self, splits: List[str]) -> List[str]:
        """
        Create chunks from splits with proper overlap.

        Args:
            splits: List of text splits

        Returns:
            List of text chunks with proper overlap
        """
        # If we only have one split and it's smaller than chunk size, return it
        if len(splits) == 1 and self._length_function(splits[0]) <= self.chunk_size:
            return splits

        # Create chunks
        chunks = []
        current_chunk: List[str] = []
        current_chunk_len = 0

        for i, split in enumerate(splits):
            split_len = self._length_function(split)

            # If this split alone exceeds chunk size, we need to handle it separately
            if split_len > self.chunk_size:
                # If we have accumulated content, add it as a chunk
                if current_chunk:
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    current_chunk_len = 0

                # Split this large piece by characters
                for j in range(0, len(split), self.chunk_size - self.chunk_overlap):
                    chunks.append(split[j : j + self.chunk_size])

                continue

            # If adding this split would exceed chunk size, finalize current chunk
            if current_chunk_len + split_len > self.chunk_size and current_chunk:
                chunks.append("".join(current_chunk))

                # Calculate how many splits to keep for overlap
                overlap_splits = []
                overlap_len = 0

                # Work backwards through current_chunk to find splits for overlap
                for j in range(len(current_chunk) - 1, -1, -1):
                    split_to_keep = current_chunk[j]
                    split_to_keep_len = self._length_function(split_to_keep)

                    if overlap_len + split_to_keep_len <= self.chunk_overlap:
                        overlap_splits.insert(0, split_to_keep)
                        overlap_len += split_to_keep_len
                    else:
                        # If this split would exceed overlap size, we're done
                        break

                # Start new chunk with overlap content
                current_chunk = overlap_splits
                current_chunk_len = overlap_len

            # Add the current split to the chunk
            current_chunk.append(split)
            current_chunk_len += split_len

        # Add the final chunk if there's anything left
        if current_chunk:
            chunks.append("".join(current_chunk))

        return chunks

    def can_handle(self, data_type: str) -> bool:
        """
        Check if this splitter can handle the given data type.

        Args:
            data_type: The type of data to split.

        Returns:
            True if this splitter can handle the data type, False otherwise.
        """
        return data_type.lower() in ["text", "txt", "plaintext"]


class RecursiveCharacterTextSplitter(CharacterTextSplitter):
    """
    Implementation of splitting text that looks at characters recursively.
    Adapted from LangChain's RecursiveCharacterTextSplitter.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the recursive character text splitter.

        Args:
            config: A dictionary containing configuration parameters.
                - chunk_size: The size of each chunk (default: 1000).
                - chunk_overlap: The overlap between chunks (default: 200).
                - separators: The separators to use for splitting (default: ["\n\n", "\n", " ", ""]).
                - is_separator_regex: Whether the separators are regexes (default: False).
                - keep_separator: Whether to keep the separator in the chunks (default: True).
                - strip_whitespace: Whether to strip whitespace from the chunks (default: True).
        """
        super().__init__(config)
        self.separators = self.config.get("separators", ["\n\n", "\n", " ", ""])

        # Ensure we have a final default separator that will catch everything
        if not self.separators or self.separators[-1] != "":
            self.separators.append("")

    def split_text(self, text: str) -> List[str]:
        """
        Split the text into chunks recursively.

        Args:
            text: The text to split.

        Returns:
            A list of text chunks.
        """
        if not text:
            return []

        # Get the appropriate separator to use
        separator = self._get_separator_for_text(text)

        # Now split the text
        if separator:
            if self.is_separator_regex:
                splits = re.split(separator, text)
            else:
                splits = text.split(separator)
        else:
            # If no separator is found, use the default behavior
            return self._split_text_with_size_limit(text)

        # Now process the splits
        final_chunks = []

        # Clean and filter splits
        good_splits = []
        for split in splits:
            if self.strip_whitespace:
                split = split.strip()
            if split:
                good_splits.append(split)

        # Process each split
        for split in good_splits:
            if self._length_function(split) < self.chunk_size:
                final_chunks.append(split)
            else:
                # If the split is too big, recursively split it
                # using the next separator
                other_info = self._get_next_splitter_config()
                if other_info:
                    # Create a new splitter with the next separator
                    sub_splitter = RecursiveCharacterTextSplitter(other_info)
                    sub_chunks = sub_splitter.split_text(split)
                    final_chunks.extend(sub_chunks)
                else:
                    # If there are no more separators, split by character
                    final_chunks.extend(self._split_text_with_size_limit(split))

        # Create chunks with proper overlap
        if len(final_chunks) > 1:
            # Join the chunks first to handle any separators properly
            joined_chunks = []
            for chunk in final_chunks:
                joined_chunks.append(chunk)

            # Then create overlapping chunks
            return self._create_overlapping_chunks(joined_chunks)

        return final_chunks

    def _get_separator_for_text(self, text: str) -> str:
        """
        Get the first separator that appears in the text.

        Args:
            text: The text to check.

        Returns:
            The first separator that appears in the text, or None if none are found.
        """
        for separator in self.separators:
            if separator == "":
                # Special case: empty separator always matches
                return separator

            if self.is_separator_regex:
                if re.search(separator, text):
                    return separator
            else:
                if separator in text:
                    return separator

        return self.separators[-1]  # Default to the last separator (usually "")

    def _get_next_splitter_config(self) -> Dict[str, Any]:
        """
        Get the configuration for the next splitter in the recursive chain.

        Returns:
            A dictionary containing the configuration for the next splitter,
            or None if there are no more separators.
        """
        if len(self.separators) <= 1:
            return None

        # Create a new config with the next separator
        next_config = self.config.copy() if self.config else {}
        next_config["separators"] = self.separators[1:]

        return next_config

    def _split_text_with_size_limit(self, text: str) -> List[str]:
        """
        Split text by characters to ensure chunks are below the chunk size.

        Args:
            text: The text to split.

        Returns:
            A list of text chunks.
        """
        # If the text is already small enough, return it as is
        if self._length_function(text) <= self.chunk_size:
            return [text]

        # Otherwise, split it by characters
        result = []
        for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
            chunk = text[i : i + self.chunk_size]
            if chunk:
                result.append(chunk)

        return result

    def can_handle(self, data_type: str) -> bool:
        """
        Check if this splitter can handle the given data type.

        Args:
            data_type: The type of data to split.

        Returns:
            True if this splitter can handle the data type, False otherwise.
        """
        return data_type.lower() in ["text", "txt", "plaintext"]


class TokenTextSplitter(SplitterBase):
    """
    Split text by tokens using tiktoken.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the token text splitter.

        Args:
            config: A dictionary containing configuration parameters.
                - chunk_size: The size of each chunk in tokens (default: 500).
                - chunk_overlap: The overlap between chunks in tokens (default: 100).
                - encoding_name: The name of the tiktoken encoding to use (default: "cl100k_base").
        """
        super().__init__(config)
        self.chunk_size = self.config.get("chunk_size", 500)
        self.chunk_overlap = self.config.get("chunk_overlap", 100)
        self.encoding_name = self.config.get("encoding_name", "cl100k_base")

        if not TIKTOKEN_AVAILABLE:
            raise ImportError(
                "The tiktoken package is required for TokenTextSplitter. "
                "Please install it with `pip install tiktoken`."
            )

        self.tokenizer = tiktoken.get_encoding(self.encoding_name)

    def split_text(self, text: str) -> List[str]:
        """
        Split the text into chunks by tokens.

        Args:
            text: The text to split.

        Returns:
            A list of text chunks.
        """
        if not text:
            return []

        # Tokenize the text
        tokens = self.tokenizer.encode(text)

        # If the text is small enough, return it as is
        if len(tokens) <= self.chunk_size:
            return [text]

        # Split the tokens into chunks with proper overlap
        chunks = []
        for i in range(0, len(tokens), self.chunk_size - self.chunk_overlap):
            # Get the tokens for this chunk
            chunk_tokens = tokens[i : i + self.chunk_size]
            # Decode the tokens back to text
            chunk_text = self.tokenizer.decode(chunk_tokens)
            chunks.append(chunk_text)

        return chunks

    def can_handle(self, data_type: str) -> bool:
        """
        Check if this splitter can handle the given data type.

        Args:
            data_type: The type of data to split.

        Returns:
            True if this splitter can handle the data type, False otherwise.
        """
        return data_type.lower() in ["text", "txt", "plaintext"]
