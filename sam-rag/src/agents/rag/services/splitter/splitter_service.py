"""
Service for splitting documents into chunks for embedding.
"""

from typing import Dict, Any, List

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


class SplitterService:
    """
    Service for splitting documents into chunks for embedding.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the splitter service.

        Args:
            config: A dictionary containing configuration parameters.
                - splitters: A dictionary mapping data types to splitter configurations.
                - default_splitter: The default splitter to use if no specific splitter is found.
        """
        self.config = config or {}
        self.splitters: Dict[str, SplitterBase] = {}
        self.default_splitter = None
        self._register_splitters()

    def _register_splitters(self) -> None:
        """
        Register all available splitters based on the configuration.
        """
        # Get the splitter configurations from the config
        splitter_configs = self.config.get("splitters", {})

        # Register default splitters if not specified in the config
        if not splitter_configs:
            # Default configuration for text splitters
            self.splitters["text"] = RecursiveCharacterTextSplitter()
            self.splitters["txt"] = self.splitters["text"]
            self.splitters["plaintext"] = self.splitters["text"]

            # Default configuration for structured data splitters
            self.splitters["json"] = RecursiveJSONSplitter()
            self.splitters["html"] = HTMLSplitter()
            self.splitters["htm"] = self.splitters["html"]
            self.splitters["markdown"] = MarkdownSplitter()
            self.splitters["md"] = self.splitters["markdown"]
            self.splitters["csv"] = CSVSplitter()

            # Set the default splitter
            self.default_splitter = RecursiveCharacterTextSplitter()
        else:
            # Register splitters based on the configuration
            for data_type, splitter_config in splitter_configs.items():
                splitter_type = splitter_config.get("type", "recursive_character")
                splitter_params = splitter_config.get("params", {})

                # Create the appropriate splitter based on the type
                match splitter_type:
                    case "character":
                        self.splitters[data_type] = CharacterTextSplitter(
                            splitter_params
                        )
                    case "recursive_character":
                        self.splitters[data_type] = RecursiveCharacterTextSplitter(
                            splitter_params
                        )
                    case "token":
                        self.splitters[data_type] = TokenTextSplitter(splitter_params)
                    case "json":
                        self.splitters[data_type] = JSONSplitter(splitter_params)
                    case "recursive_json":
                        self.splitters[data_type] = RecursiveJSONSplitter(
                            splitter_params
                        )
                    case "html":
                        self.splitters[data_type] = HTMLSplitter(splitter_params)
                    case "markdown":
                        self.splitters[data_type] = MarkdownSplitter(splitter_params)
                    case "csv":
                        self.splitters[data_type] = CSVSplitter(splitter_params)

            # Set the default splitter
            default_config = self.config.get("default_splitter", {})
            default_type = default_config.get("type", "recursive_character")
            default_params = default_config.get("params", {})

            match default_type:
                case "character":
                    self.default_splitter = CharacterTextSplitter(default_params)
                case "recursive_character":
                    self.default_splitter = RecursiveCharacterTextSplitter(
                        default_params
                    )
                case "token":
                    self.default_splitter = TokenTextSplitter(default_params)
                case _:
                    self.default_splitter = RecursiveCharacterTextSplitter()

    def get_splitter(self, data_type: str) -> SplitterBase:
        """
        Get the appropriate splitter for the given data type.

        Args:
            data_type: The type of data to split.

        Returns:
            The appropriate splitter for the data type.
        """
        # Convert data type to lowercase for case-insensitive matching
        data_type = data_type.lower()

        # Check if we have a registered splitter for this data type
        if data_type in self.splitters:
            return self.splitters[data_type]

        # If not, try to find a splitter that can handle this data type
        for splitter in self.splitters.values():
            if splitter.can_handle(data_type):
                return splitter

        # If no suitable splitter is found, return the default splitter
        return self.default_splitter

    def split_text(self, text: str, data_type: str) -> List[Any]:
        """
        Split the text into chunks using the appropriate splitter.

        Args:
            text: The text to split.
            data_type: The type of data to split.

        Returns:
            A list of text chunks or dictionaries with 'content' and 'metadata' keys.
        """
        if not text:
            return []

        # Get the appropriate splitter
        splitter = self.get_splitter(data_type)

        # Split the text
        chunks = splitter.split_text(text)

        # Handle both string chunks and dictionary chunks
        return chunks
