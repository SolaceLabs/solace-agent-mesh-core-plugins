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

# Adding imports for file tracking and ingestion functionality
from .services.ingestor.ingestion_service import IngestionService
from .services.scanner.file_tracker import FileChangeTracker

# Add new imports for the RAG pipeline
from .services.preprocessor.preprocessor_service import PreprocessorService
from .services.splitter.splitter_service import SplitterService
from .services.embedder.embedder_service import EmbedderService
from .services.rag.augmentation_service import AugmentationService

info = copy.deepcopy(agent_info)
info.update(
    {
        "agent_name": "rag",
        "class_name": "RAGAgentComponent",
        "description": "The agent scans documents of resources, ingests documents in a vector database, and "
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
    actions = [RAGAction]

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

        # Initialize handlers
        self.ingestion_handler = None
        self.file_tracker = None
        self.preprocessing_handler = None
        self.embedding_handler = None
        self.splitting_handler = None
        self.augmentation_handler = None
        self.use_memory_storage = False
        # Create handlers
        self._create_handlers()

        # Run the ingestion process in a separate thread
        self.ingestion_thread = threading.Thread(target=self._ingest)
        self.ingestion_thread.daemon = (
            True  # Set as daemon so it exits when main thread exits
        )
        self.ingestion_thread.start()
        log.info(f"Started ingestion process on background thread")

    def _ingest(self):
        """Ingest documents into the vector database."""
        log.info("Starting document ingestion process")
        if self.file_tracker:
            # Real-time scanner: Scan for file changes
            self._scan_files()

            # Batch scanner: Get files
            files = self._get_tracked_files()

            if files:
                # Process files through the complete pipeline
                result = self._process_files(files, self.component_config)
                log.info(f"Processing result: {result}")
            else:
                log.info("No files found to process.")
        else:
            log.error("No file tracker is initialized.")

    def _process_files(self, file_paths: List[str], params=None) -> Dict[str, Any]:
        """
        Process files through a complete RAG pipeline: preprocess, chunk, embed, and ingest.

        Args:
            file_paths: List of file paths to process.
            params: Configuration parameters.

        Returns:
            A dictionary containing the processing results.
        """
        log.info(f"Processing {len(file_paths)} files through the RAG pipeline")

        # Step 1: Preprocess files
        preprocessed_docs = []
        preprocessed_metadata = []

        for i, file_path in enumerate(file_paths):
            try:
                # Verify the file exists
                if not os.path.exists(file_path):
                    log.warning(f"File not found: {file_path}")
                    continue

                # Get the document type
                doc_type = self._get_file_type(file_path)

                # Process the file with the appropriate preprocessor config
                # The preprocessor service will select the right preprocessor based on file type
                text = self.preprocessing_handler.preprocess_file(file_path)

                if text:
                    preprocessed_docs.append(text)
                    preprocessed_metadata.append(
                        {
                            "source": file_path,
                            "document_type": doc_type,
                            "file_name": os.path.basename(file_path),
                            "index": i,
                        }
                    )
                    log.info(
                        f"Successfully preprocessed file: {file_path} ({doc_type})"
                    )
                else:
                    log.warning(f"Failed to preprocess file: {file_path}")
            except Exception as e:
                log.error(f"Error preprocessing file {file_path}: {str(e)}")

        if not preprocessed_docs:
            log.warning("No documents were successfully preprocessed")
            return {
                "success": False,
                "message": "No documents were successfully preprocessed",
                "document_ids": [],
            }

        # Step 2: Split documents into chunks
        chunks = []
        chunks_metadata = []

        for i, (doc, meta) in enumerate(zip(preprocessed_docs, preprocessed_metadata)):
            try:
                # Get the document type
                doc_type = meta.get("document_type", "text")

                # Split the document
                doc_chunks = self.splitting_handler.split_text(doc, doc_type)

                # Add chunks and metadata
                chunks.extend(doc_chunks)
                chunks_metadata.extend([meta.copy() for _ in range(len(doc_chunks))])

                log.info(f"Split document {i} into {len(doc_chunks)} chunks")
            except Exception as e:
                log.error(f"Error splitting document {i}: {str(e)}")

        if not chunks:
            log.warning("No chunks were created from the documents")
            return {
                "success": False,
                "message": "No chunks were created from the documents",
                "document_ids": [],
            }

        # Step 3: Embed chunks
        try:
            embeddings = self.embedding_handler.embed_texts(chunks)
            log.info(f"Created {len(embeddings)} embeddings")
        except Exception as e:
            log.error(f"Error embedding chunks: {str(e)}")
            return {
                "success": False,
                "message": f"Error embedding chunks: {str(e)}",
                "document_ids": [],
            }

        # Step 4: Ingest embeddings into vector database
        try:
            # Use the ingestion handler to store the embeddings
            result = self.ingestion_handler.ingest_embeddings(
                texts=chunks, embeddings=embeddings, metadata=chunks_metadata
            )
            log.info(f"Ingestion result: {result['message']}")
            return result
        except Exception as e:
            log.error(f"Error ingesting embeddings: {str(e)}")
            return {
                "success": False,
                "message": f"Error ingesting embeddings: {str(e)}",
                "document_ids": [],
            }

        # Step 5: Add metadata to the memory storage
        # if self.use_memory_storage:
        #     try:
        #         for meta_data in chunks_metadata:
        #             self.file_tracker.add_file(
        #                 path=meta_data["source"],
        #                 file=meta_data["file_name"],
        #                 status="new",
        #                 timestamp=time.time(),
        #             )
        #         log.info("Metadata added to memory storage")
        #     except Exception as e:
        #         log.error(f"Error adding metadata to memory storage: {str(e)}")

    def _get_file_type(self, file_path: str) -> str:
        """
        Get the file type from a file path.

        Args:
            file_path: Path to the file.

        Returns:
            The file type (e.g., "pdf", "text", "html").
        """
        _, ext = os.path.splitext(file_path.lower())
        return ext[1:] if ext else "text"  # Remove the leading dot

    def _get_tracked_files(self) -> List[Dict[str, Any]]:
        """
        Get all tracked files from the file tracker.

        Returns:
            A list of tracked files with their metadata.
        """
        if self.file_tracker:
            try:
                files = []
                tracked_files = self.file_tracker.get_tracked_files()
                for i, file in enumerate(tracked_files):
                    file_path = file.get("path", None)  # Get the file path
                    if not file_path:
                        log.warning(f"Invalid file path: {file}")
                        continue

                    # Verify the file exists
                    if not os.path.exists(file_path):
                        log.warning(f"File not found: {file_path}")
                        continue

                    file_status = file.get("status", None)  # Get the file status
                    if file_status not in {"modified", "new"}:
                        continue

                    files.append(file_path)
                return files
            except Exception as e:
                log.error(f"Error getting tracked files: {str(e)}")
                return []

    def _scan_files(self) -> Dict[str, List[str]]:
        """
        Scan for file changes using the file tracker.

        Returns:
            A dictionary containing the scan results.
        """
        if self.file_tracker:
            return self.file_tracker.scan()
        else:
            log.warning("Scanner module not available or file tracker not initialized")
            return {"added": [], "removed": [], "changed": []}

    def _create_handlers(self):
        """Create handlers for the agent."""
        # Initialize the ingestion handler
        self.ingestion_handler = IngestionService(self.component_config)

        # Initialize the file tracker
        scanner_config = self.get_config("scanner", {})
        if scanner_config:
            source_config = scanner_config.get("source", {})

            # Get directories from scanner configuration
            if (
                source_config.get("type") == "filesystem"
                and "directories" in source_config
            ):
                directories = source_config.get("directories", [])

                if directories:
                    self.file_tracker = FileChangeTracker(self.component_config)
                    self.use_memory_storage = scanner_config["use_memory_storage"]
                    log.info(
                        "File tracker initialized with memory storage"
                        if self.use_memory_storage
                        else "File tracker initialized with database"
                    )
                else:
                    log.info("No directories provided for ingestion.")
            else:
                log.info("No directories provided in scanner configuration.")

        # Initialize the preprocessing handler
        preprocessor_config = self.get_config("preprocessor", {})
        default_preprocessor = preprocessor_config.get("default_preprocessor", {})
        file_specific_preprocessors = preprocessor_config.get("preprocessors", {})

        # Log the extracted configuration for debugging
        log.debug(f"Using default preprocessor config: {default_preprocessor}")
        log.debug(
            f"Using file-specific preprocessor configs: {file_specific_preprocessors}"
        )

        # Initialize pipeline components with configuration from params
        self.preprocessing_handler = PreprocessorService(
            {
                "default_preprocessor": default_preprocessor,
                "preprocessors": file_specific_preprocessors,
            }
        )

        # Initialize the splitter handlers
        splitter_config = self.get_config("splitter", {})
        self.splitting_handler = SplitterService(splitter_config)

        # Initialize the embedding handler
        embedder_config = self.get_config("embedding", {})
        self.embedding_handler = EmbedderService(embedder_config)

        # Initialize the augmentation handler
        self.augmentation_handler = AugmentationService(self.component_config)

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

    def get_ingestion_handler(self):
        """Get the ingestion handler."""
        return self.ingestion_handler

    def get_file_tracker(self):
        """Get the file tracker."""
        return self.file_tracker

    def get_preprocessor_handler(self):
        """Get the preprocessor handler."""
        return self.preprocessing_handler

    def get_embedding_handler(self):
        """Get the embedding handler."""
        return self.embedding_handler

    def get_splitting_handler(self):
        """Get the splitting handler."""
        return self.splitting_handler

    def get_augmentation_handler(self):
        """Get the augmentation handler."""
        return self.augmentation_handler
