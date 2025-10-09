"""
Text preprocessing utilities for cleaning and normalizing text.
"""

import logging
import re
import unicodedata
from typing import Dict, Any

log = logging.getLogger(__name__)

class RawTextPreprocessor:
    """
    Utility class for text preprocessing operations.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the text preprocessor with the given configuration.

        Args:
            config: A dictionary containing configuration parameters.
                - lowercase: Whether to convert text to lowercase.
                - normalize_unicode: Whether to normalize Unicode characters.
                - normalize_whitespace: Whether to normalize whitespace.
                - remove_punctuation: Whether to remove punctuation.
                - remove_urls: Whether to remove URLs.
                - remove_html_tags: Whether to remove HTML tags.
                - remove_numbers: Whether to remove numbers.
                - remove_non_ascii: Whether to remove non-ASCII characters.
                - remove_emails: Whether to remove email addresses.
        """
        self.config = config or {}

        # Default configuration
        self.lowercase = self.config.get("lowercase", False)
        self.normalize_unicode = self.config.get("normalize_unicode", False)
        self.normalize_whitespace = self.config.get("normalize_whitespace", False)
        self.remove_punctuation = self.config.get("remove_punctuation", False)
        self.remove_urls = self.config.get("remove_urls", False)
        self.remove_html_tags = self.config.get("remove_html_tags", False)
        self.remove_numbers = self.config.get("remove_numbers", False)
        self.remove_non_ascii = self.config.get("remove_non_ascii", False)
        self.remove_emails = self.config.get("remove_emails", False)

    def preprocess(self, text: str) -> str:
        """
        Apply preprocessing steps to clean and normalize text.

        Args:
            text: The input text to preprocess.

        Returns:
            Preprocessed text.
        """
        if not text:
            return ""

        # Unicode normalization
        if self.normalize_unicode:
            log.debug("Normalizing unicode characters: %s", text)
            text = self._normalize_unicode(text)

        # Lowercase conversion
        if self.lowercase:
            log.debug("Converting text to lowercase: %s", text)
            text = text.lower()

        # Remove URLs
        if self.remove_urls:
            log.debug("Removing URLs from text: %s", text)
            text = self._remove_urls(text)

        # Remove Emails
        if self._remove_emails:
            log.debug("Removing Emails from text: %s", text)
            text = self._remove_emails(text)

        # Remove HTML tags
        if self.remove_html_tags:
            log.debug("Removing HTML tags from text: %s", text)
            text = self._remove_html_tags(text)

        # Remove punctuation
        if self.remove_punctuation:
            log.debug("Removing punctuation from text: %s", text)
            text = self._remove_punctuation(text)

        # Remove numbers
        if self.remove_numbers:
            log.debug("Removing numbers from text: %s", text)
            text = self._remove_numbers(text)

        # Remove non-ASCII characters
        if self.remove_non_ascii:
            log.debug("Removing non-ASCII characters from text: %s", text)
            text = self._remove_non_ascii(text)

        # Normalize whitespace
        if self.normalize_whitespace:
            log.debug("Normalizing whitespace in text: %s", text)
            text = self._normalize_whitespace(text)

        return text

    def _normalize_unicode(self, text: str) -> str:
        """
        Normalize Unicode characters to their canonical form.

        Args:
            text: The input text.

        Returns:
            Text with normalized Unicode characters.
        """
        return unicodedata.normalize("NFKC", text)

    def _remove_urls(self, text: str) -> str:
        """
        Remove URLs from text.

        Args:
            text: The input text.

        Returns:
            Text with URLs removed.
        """
        url_pattern = r"https?://\S+|www\.\S+"
        return re.sub(url_pattern, " ", text)

    def _remove_emails(self, text: str) -> str:
        """
        Remove email addresses from text.

        Args:
            text: The input text.

        Returns:
            Text with email addresses removed.
        """
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        return re.sub(email_pattern, " ", text)

    def _remove_html_tags(self, text: str) -> str:
        """
        Remove HTML tags from text.

        Args:
            text: The input text.

        Returns:
            Text with HTML tags removed.
        """
        html_pattern = r"<.*?>"
        return re.sub(html_pattern, " ", text)

    def _remove_punctuation(self, text: str) -> str:
        """
        Remove punctuation from text, except for specified characters.

        Preserves:
        - Standard punctuation: ., ,, ;, :, !, ?, ', ", -
        - Brackets and parentheses: (), [], {}, <>
        - Mathematical symbols: +, *, /, =, %
        - Currency symbols: $, €, £, ¥

        Args:
            text: The input text.

        Returns:
            Text with unwanted punctuation removed.
        """
        # Define punctuation to keep
        preserved_punct = r".,;:!?\'\"\-\(\)\[\]\{\}<>\+\*/=\%\$€£¥"
        punctuation_pattern = f"[^\\w\\s{preserved_punct}]"
        return re.sub(punctuation_pattern, " ", text)

    def _remove_numbers(self, text: str) -> str:
        """
        Remove numbers from text.

        Args:
            text: The input text.

        Returns:
            Text with numbers removed.
        """
        return re.sub(r"\d+", " ", text)

    def _remove_non_ascii(self, text: str) -> str:
        """
        Remove non-ASCII characters from text.

        Args:
            text: The input text.

        Returns:
            Text with non-ASCII characters removed.
        """
        return re.sub(r"[^\x00-\x7F]+", " ", text)

    def _normalize_whitespace(self, text: str) -> str:
        """
        Normalize whitespace in text.

        Args:
            text: The input text.

        Returns:
            Text with normalized whitespace.
        """
        # Replace multiple whitespace characters with a single space
        text = re.sub(r"\s+", " ", text)
        # Trim leading and trailing whitespace
        return text.strip()
