"""
Text splitter package for splitting documents into chunks for embedding.
"""

from .splitter_base import SplitterBase
from .text_splitter import (
    CharacterTextSplitter,
    RecursiveCharacterTextSplitter,
    TokenTextSplitter,
)
from .structured_splitter import (
    JSONSplitter,
    RecursiveJSONSplitter,
    HTMLSplitter,
    MarkdownSplitter,
    CSVSplitter,
)
from .splitter_service import SplitterService

__all__ = [
    "SplitterBase",
    "CharacterTextSplitter",
    "RecursiveCharacterTextSplitter",
    "TokenTextSplitter",
    "JSONSplitter",
    "RecursiveJSONSplitter",
    "HTMLSplitter",
    "MarkdownSplitter",
    "CSVSplitter",
    "SplitterService",
]
