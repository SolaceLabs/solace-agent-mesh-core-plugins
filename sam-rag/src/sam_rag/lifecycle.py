"""Lifecycle functions for the SAM RAG plugin."""

import logging
from typing import Any, Dict

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

log = logging.getLogger(__name__)

class RagScannerConfig(BaseModel):
    """Configuration for the RAG scanner component."""
    batch: bool = Field(default=True, description="Process existing files on startup")
    use_memory_storage: bool = Field(default=True, description="Use in-memory storage")
    sources: List[Dict[str, Any]] = Field(default=[], description="Multiple sources configuration")
    schedule: Dict[str, Any] = Field(default={"interval": 60}, description="Scanning schedule")

class RagPreprocessorConfig(BaseModel):
    """Configuration for the RAG preprocessor component."""
    default_preprocessor: Dict[str, Any] = Field(default={}, description="Default preprocessor configuration")
    preprocessors: Dict[str, Dict[str, Any]] = Field(default={}, description="File-specific preprocessors")

class RagSplitterConfig(BaseModel):
    """Configuration for the RAG splitter component."""
    default_splitter: Dict[str, Any] = Field(default={}, description="Default splitter configuration")
    splitters: Dict[str, Dict[str, Any]] = Field(default={}, description="File-specific splitters")

class RagEmbeddingConfig(BaseModel):
    """Configuration for the RAG embedding component."""
    embedder_type: str = Field(description="Type of embedder to use")
    embedder_params: Dict[str, Any] = Field(default={}, description="Parameters for the embedder")
    normalize_embeddings: bool = Field(default=True, description="Whether to normalize embeddings")

class RagVectorDBConfig(BaseModel):
    """Configuration for the RAG vector database component."""
    db_type: str = Field(description="Type of vector database")
    db_params: Dict[str, Any] = Field(default={}, description="Parameters for the vector database")

class RagLLMConfig(BaseModel):
    """Configuration for the RAG LLM component."""
    load_balancer: List[Dict[str, Any]] = Field(default=[], description="LLM load balancer configuration")

class RagRetrievalConfig(BaseModel):
    """Configuration for the RAG retrieval component."""
    top_k: int = Field(default=5, description="Number of documents to retrieve")

class RagAgentConfig(BaseModel):
    """Configuration for the RAG agent."""
    scanner: RagScannerConfig = Field(default_factory=RagScannerConfig, description="Scanner configuration")
    preprocessor: RagPreprocessorConfig = Field(default_factory=RagPreprocessorConfig, description="Preprocessor configuration")
    splitter: RagSplitterConfig = Field(default_factory=RagSplitterConfig, description="Splitter configuration")
    embedding: RagEmbeddingConfig = Field(description="Embedding configuration")
    vector_db: RagVectorDBConfig = Field(description="Vector database configuration")
    llm: RagLLMConfig = Field(default_factory=RagLLMConfig, description="LLM configuration")
    retrieval: RagRetrievalConfig = Field(default_factory=RagRetrievalConfig, description="Retrieval configuration")

def initialize_rag_agent(host_component: Any, init_config: RagAgentConfig):
    """
    Initialize the RAG agent with the provided configuration.
    This function sets up the scanner, preprocessor, splitter, embedder, and vector DB services.
    
    Args:
        host_component: The host component that will host the RAG agent.
        init_config: The configuration for the RAG agent.
    """
    log_identifier = f"[{host_component.agent_name}:init_rag_agent]"
    log.info("%s Starting RAG Agent initialization...", log_identifier)
    
    try:
        # Import RAG services
        from .services.pipeline.pipeline import Pipeline
        
        # Add host_component to config for artifact service access
        config_dict = init_config.dict()
        config_dict["host_component"] = host_component
        
        # Log host_component details for debugging
        log.info(f"{log_identifier} host_component type: {type(host_component)}")
        
        # The A2A ADK Host is responsible for initializing and providing the artifact_service
        # on the host_component if it's configured in the host's main YAML.
        # This plugin should not attempt to create it.
        if hasattr(host_component, "artifact_service") and host_component.artifact_service is not None:
            log.info(f"{log_identifier} ArtifactService is available on host_component: {host_component.artifact_service}")
        else:
            log.warning(f"{log_identifier} ArtifactService is NOT available on host_component. "
                        "If RAG background processes require artifact storage, "
                        "ensure artifact_service is configured in the A2A ADK Host's main YAML "
                        "and provided to this agent's host_component by the framework.")

        # Create pipeline with configuration
        # The pipeline and its sub-services will access host_component.artifact_service if needed.
        pipeline = Pipeline(config=config_dict)
        
        # Store pipeline in agent_specific_state
        host_component.set_agent_specific_state("rag_pipeline", pipeline)
        
        # Store file tracker for direct access
        file_tracker = pipeline.get_file_tracker()
        host_component.set_agent_specific_state("file_tracker", file_tracker)
        
        # Store augmentation handler for direct access
        augmentation_handler = pipeline.get_augmentation_handler()
        host_component.set_agent_specific_state("augmentation_handler", augmentation_handler)
        
        # Set system instruction for the LLM
        system_instruction = """
        You are a RAG (Retrieval Augmented Generation) agent that can:
        1. Ingest documents from various sources (file system, cloud storage)
        2. Process and index documents for efficient retrieval
        3. Search for relevant information based on user queries
        4. Provide augmented responses using retrieved information
        
        You have access to tools for document ingestion and retrieval.
        """
        host_component.set_agent_system_instruction_string(system_instruction)
        
        log.info("%s RAG Agent initialization completed successfully.", log_identifier)
        
    except Exception as e:
        log.exception("%s Failed to initialize RAG Agent: %s", log_identifier, e)
        raise RuntimeError(f"RAG Agent initialization failed: {e}") from e

def cleanup_rag_agent_resources(host_component: Any):
    """
    Clean up resources used by the RAG agent.
    
    Args:
        host_component: The host component that hosts the RAG agent.
    """
    log_identifier = f"[{host_component.agent_name}:cleanup_rag_agent]"
    log.info("%s Cleaning up RAG Agent resources...", log_identifier)
    
    try:
        # Get pipeline from agent_specific_state
        pipeline = host_component.get_agent_specific_state("rag_pipeline")
        if pipeline:
            # Clean up pipeline resources
            pipeline.cleanup()
            log.info("%s Pipeline resources cleaned up successfully.", log_identifier)
        else:
            log.info("%s No pipeline found in agent_specific_state.", log_identifier)
            
        log.info("%s RAG Agent resource cleanup finished.", log_identifier)
        
    except Exception as e:
        log.error("%s Error during RAG Agent cleanup: %s", log_identifier, e, exc_info=True)
        # Log error but don't prevent further cleanup
