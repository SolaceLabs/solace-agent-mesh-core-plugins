"""The ingestion agent component for the rag"""

import os
import copy
import sys
import threading
from typing import Dict, List, Any
from solace_ai_connector.common.log import log

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(SCRIPT_DIR))

from solace_agent_mesh.agents.base_agent_component import (
    agent_info,
    BaseAgentComponent,
)

# Ingestion action import
from .actions.rag import RAGAction
from .actions.ingest import IngestionAction

# Add new imports for the RAG pipeline
from .services.pipeline.pipeline import Pipeline

info = copy.deepcopy(agent_info)
info.update(
    {
        "agent_name": "rag",
        "class_name": "RAGAgentComponent",
        "description": "This agent scans documents of resources, ingests documents in a vector database, and "
        "provides relevant information when a user explicitly requests it.",
        "config_parameters": [
            {
                "name": "scanner",
                "desc": "Configuration for the document scanner.",
                "type": "object",
                "properties": {
                    "batch": {
                        "type": "boolean",
                        "desc": "Whether to process documents in batch mode",
                    },
                    "use_memory_storage": {
                        "type": "boolean",
                        "desc": "Whether to use in-memory storage",
                    },
                    "source": {
                        "type": "object",
                        "desc": "Document source configuration",
                        "properties": {
                            "type": {
                                "type": "string",
                                "desc": "Source type (e.g., filesystem)",
                            },
                            "directories": {
                                "type": "array",
                                "desc": "Directories to scan",
                                "items": {"type": "string"},
                            },
                            "filters": {
                                "type": "object",
                                "desc": "File filtering options",
                                "properties": {
                                    "file_formats": {
                                        "type": "array",
                                        "desc": "Supported file formats",
                                        "items": {"type": "string"},
                                    },
                                    "max_file_size": {
                                        "type": "number",
                                        "desc": "Maximum file size in KB",
                                    },
                                },
                            },
                        },
                    },
                    "database": {
                        "type": "object",
                        "desc": "Database configuration for metadata",
                        "properties": {
                            "type": {
                                "type": "string",
                                "desc": "Database type (e.g., postgresql)",
                            },
                            "dbname": {"type": "string", "desc": "Database name"},
                            "host": {"type": "string", "desc": "Database host"},
                            "port": {"type": "number", "desc": "Database port"},
                            "user": {"type": "string", "desc": "Database username"},
                            "password": {"type": "string", "desc": "Database password"},
                        },
                    },
                    "schedule": {
                        "type": "object",
                        "desc": "Scanning schedule configuration",
                        "properties": {
                            "interval": {
                                "type": "number",
                                "desc": "Scan interval in seconds",
                            }
                        },
                    },
                },
            },
            {
                "name": "preprocessor",
                "desc": "Configuration for document preprocessing.",
                "type": "object",
                "properties": {
                    "default_preprocessor": {
                        "type": "object",
                        "desc": "Default preprocessing settings",
                        "properties": {
                            "type": {"type": "string", "desc": "Preprocessor type"},
                            "params": {
                                "type": "object",
                                "desc": "Preprocessing parameters",
                                "properties": {
                                    "remove_stopwords": {
                                        "type": "boolean",
                                        "desc": "Whether to remove stopwords",
                                    },
                                    "remove_punctuation": {
                                        "type": "boolean",
                                        "desc": "Whether to remove punctuation",
                                    },
                                    "lowercase": {
                                        "type": "boolean",
                                        "desc": "Whether to convert text to lowercase",
                                    },
                                    "normalize_whitespace": {
                                        "type": "boolean",
                                        "desc": "Whether to normalize whitespace",
                                    },
                                    "remove_urls": {
                                        "type": "boolean",
                                        "desc": "Whether to remove URLs",
                                    },
                                    "remove_emails": {
                                        "type": "boolean",
                                        "desc": "Whether to remove email addresses",
                                    },
                                },
                            },
                        },
                    },
                    "preprocessors": {
                        "type": "object",
                        "desc": "File-specific preprocessors",
                        "properties": {
                            "text": {
                                "type": "object",
                                "desc": "Text file preprocessor",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "desc": "Preprocessor type",
                                    },
                                    "params": {
                                        "type": "object",
                                        "desc": "Preprocessor parameters",
                                    },
                                },
                            },
                            "pdf": {
                                "type": "object",
                                "desc": "PDF file preprocessor",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "desc": "Preprocessor type",
                                    },
                                    "params": {
                                        "type": "object",
                                        "desc": "Preprocessor parameters",
                                    },
                                },
                            },
                            "docx": {
                                "type": "object",
                                "desc": "DOCX file preprocessor",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "desc": "Preprocessor type",
                                    },
                                    "params": {
                                        "type": "object",
                                        "desc": "Preprocessor parameters",
                                    },
                                },
                            },
                            "odt": {
                                "type": "object",
                                "desc": "ODT file preprocessor",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "desc": "Preprocessor type",
                                    },
                                    "params": {
                                        "type": "object",
                                        "desc": "Preprocessor parameters",
                                    },
                                },
                            },
                            "json": {
                                "type": "object",
                                "desc": "JSON file preprocessor",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "desc": "Preprocessor type",
                                    },
                                    "params": {
                                        "type": "object",
                                        "desc": "Preprocessor parameters",
                                    },
                                },
                            },
                            "html": {
                                "type": "object",
                                "desc": "HTML file preprocessor",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "desc": "Preprocessor type",
                                    },
                                    "params": {
                                        "type": "object",
                                        "desc": "Preprocessor parameters",
                                    },
                                },
                            },
                            "markdown": {
                                "type": "object",
                                "desc": "Markdown file preprocessor",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "desc": "Preprocessor type",
                                    },
                                    "params": {
                                        "type": "object",
                                        "desc": "Preprocessor parameters",
                                    },
                                },
                            },
                            "csv": {
                                "type": "object",
                                "desc": "CSV file preprocessor",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "desc": "Preprocessor type",
                                    },
                                    "params": {
                                        "type": "object",
                                        "desc": "Preprocessor parameters",
                                    },
                                },
                            },
                            "xls": {
                                "type": "object",
                                "desc": "Excel file preprocessor",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "desc": "Preprocessor type",
                                    },
                                    "params": {
                                        "type": "object",
                                        "desc": "Preprocessor parameters",
                                    },
                                },
                            },
                        },
                    },
                },
            },
            {
                "name": "splitter",
                "desc": "Configuration for text splitting.",
                "type": "object",
                "properties": {
                    "default_splitter": {
                        "type": "object",
                        "desc": "Default text splitter settings",
                        "properties": {
                            "type": {"type": "string", "desc": "Splitter type"},
                            "params": {
                                "type": "object",
                                "desc": "Splitter parameters",
                                "properties": {
                                    "chunk_size": {
                                        "type": "number",
                                        "desc": "Size of each chunk",
                                    },
                                    "chunk_overlap": {
                                        "type": "number",
                                        "desc": "Overlap between chunks",
                                    },
                                    "separator": {
                                        "type": "string",
                                        "desc": "Text separator",
                                    },
                                },
                            },
                        },
                    },
                    "splitters": {
                        "type": "object",
                        "desc": "File-specific text splitters",
                        "properties": {
                            "text": {
                                "type": "object",
                                "desc": "Text file splitter",
                                "properties": {
                                    "type": {"type": "string", "desc": "Splitter type"},
                                    "params": {
                                        "type": "object",
                                        "desc": "Splitter parameters",
                                    },
                                },
                            },
                            "txt": {
                                "type": "object",
                                "desc": "TXT file splitter",
                                "properties": {
                                    "type": {"type": "string", "desc": "Splitter type"},
                                    "params": {
                                        "type": "object",
                                        "desc": "Splitter parameters",
                                    },
                                },
                            },
                            "json": {
                                "type": "object",
                                "desc": "JSON file splitter",
                                "properties": {
                                    "type": {"type": "string", "desc": "Splitter type"},
                                    "params": {
                                        "type": "object",
                                        "desc": "Splitter parameters",
                                    },
                                },
                            },
                            "html": {
                                "type": "object",
                                "desc": "HTML file splitter",
                                "properties": {
                                    "type": {"type": "string", "desc": "Splitter type"},
                                    "params": {
                                        "type": "object",
                                        "desc": "Splitter parameters",
                                    },
                                },
                            },
                            "markdown": {
                                "type": "object",
                                "desc": "Markdown file splitter",
                                "properties": {
                                    "type": {"type": "string", "desc": "Splitter type"},
                                    "params": {
                                        "type": "object",
                                        "desc": "Splitter parameters",
                                    },
                                },
                            },
                            "csv": {
                                "type": "object",
                                "desc": "CSV file splitter",
                                "properties": {
                                    "type": {"type": "string", "desc": "Splitter type"},
                                    "params": {
                                        "type": "object",
                                        "desc": "Splitter parameters",
                                    },
                                },
                            },
                        },
                    },
                },
            },
            {
                "name": "embedding",
                "desc": "Configuration for embedding generation.",
                "type": "object",
                "properties": {
                    "embedder_type": {
                        "type": "string",
                        "desc": "Type of embedder to use",
                    },
                    "embedder_params": {
                        "type": "object",
                        "desc": "Parameters for the embedder",
                        "properties": {
                            "model": {"type": "string", "desc": "Embedding model name"},
                            "api_key": {
                                "type": "string",
                                "desc": "API key for embedding service",
                            },
                            "base_url": {
                                "type": "string",
                                "desc": "Base URL for embedding service",
                            },
                            "batch_size": {
                                "type": "number",
                                "desc": "Batch size for embedding generation",
                            },
                            "dimensions": {
                                "type": "number",
                                "desc": "Dimensions of the embedding vector",
                            },
                            "device": {
                                "type": "string",
                                "desc": "Device to use for local embeddings",
                            },
                        },
                    },
                    "normalize_embeddings": {
                        "type": "boolean",
                        "desc": "Whether to normalize embeddings",
                    },
                },
            },
            {
                "name": "vector_db",
                "desc": "Configuration for vector database.",
                "type": "object",
                "properties": {
                    "db_type": {
                        "type": "string",
                        "desc": "Type of vector database",
                    },
                    "db_params": {
                        "type": "object",
                        "desc": "Parameters for the vector database",
                        "properties": {
                            "url": {
                                "type": "string",
                                "desc": "URL for the vector database",
                            },
                            "api_key": {
                                "type": "string",
                                "desc": "API key for the vector database",
                            },
                            "collection_name": {
                                "type": "string",
                                "desc": "Collection name in the vector database",
                            },
                            "embedding_dimension": {
                                "type": "number",
                                "desc": "Dimension of the embedding vectors",
                            },
                        },
                    },
                },
            },
        ],
    }
)


class RAGAgentComponent(BaseAgentComponent):
    info = info
    # ingest action
    actions = [RAGAction, IngestionAction]

    def __init__(self, module_info: Dict[str, Any] = None, **kwargs):
        """Initialize the rag agent component.

        Args:
            module_info: Optional module configuration.
            **kwargs: Additional keyword arguments.

        Raises:
            ValueError: If required database configuration is missing.
        """
        module_info = module_info or info

        super().__init__(module_info, **kwargs)

        self.agent_name = self.get_config("agent_name")

        self.action_list.fix_scopes("<agent_name>", self.agent_name)

        module_info["agent_name"] = self.agent_name
        self.component_config = self.get_config("component_config")

        self.pipeline = Pipeline(config=self.component_config)

    def get_agent_summary(self):
        """Get a summary of the agent's capabilities."""
        return {
            "agent_name": self.agent_name,
            "description": f"This agent ingests documents and retrieves relevant information.\n",
            "detailed_description": (
                "This agent ingests various types of documents in a vector database and retrieves relevant information.\n\n"
            ),
            "always_open": self.info.get("always_open", False),
            "actions": self.get_actions_summary(),
        }

    def get_augmentation_handler(self):
        """Get the augmentation handler."""
        return self.pipeline.get_augmentation_handler()

    def get_file_tracker(self):
        """Get the file tracker."""
        return self.pipeline.get_file_tracker()
