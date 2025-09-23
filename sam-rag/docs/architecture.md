# SAM RAG Architecture

## Overview

The Solace Agent Mesh RAG (Retrieval Augmented Generation) plugin provides a complete RAG pipeline that enhances LLM capabilities with document retrieval. This document outlines the architecture of the SAM RAG plugin, explaining how the different components work together to provide a seamless RAG experience.

## High-Level Architecture

The SAM RAG plugin follows a modular architecture with the following main components:

1. **Scanner**: Monitors and ingests documents from various sources
2. **Preprocessor**: Cleans and normalizes text from various document formats
3. **Splitter**: Breaks documents into smaller chunks for embedding
4. **Embedder**: Converts text chunks into vector embeddings
5. **Vector Database**: Stores embeddings for efficient retrieval
6. **Retriever**: Finds relevant document chunks based on query similarity
7. **Augmentation Handler**: Enhances retrieved content using LLMs
8. **Pipeline**: Orchestrates the flow of data through the components
9. **Tools**: Provides interfaces for document ingestion and search

## Component Interactions

The following diagram illustrates how the components interact with each other:

```
                                 ┌─────────────┐
                                 │   Scanner   │
                                 └──────┬──────┘
                                        │
                                        ▼
┌─────────────┐                 ┌─────────────┐
│    Tools    │◄───────────────►│   Pipeline  │
└─────────────┘                 └──────┬──────┘
                                       │
                                       ▼
                                ┌─────────────┐
                                │Preprocessor │
                                └──────┬──────┘
                                       │
                                       ▼
                                ┌─────────────┐
                                │  Splitter   │
                                └──────┬──────┘
                                       │
                                       ▼
                                ┌─────────────┐
                                │  Embedder   │
                                └──────┬──────┘
                                       │
                                       ▼
                                ┌─────────────┐
                                │ Vector DB   │
                                └──────┬──────┘
                                       │
                                       ▼
                                ┌─────────────┐
                                │  Retriever  │
                                └──────┬──────┘
                                       │
                                       ▼
                                ┌─────────────┐
                                │Augmentation │
                                │  Handler    │
                                └─────────────┘
```

## Component Details

### 1. Scanner

The Scanner component monitors and ingests documents from various sources, including:
- Local filesystem
- Google Drive
- OneDrive
- AWS S3

It tracks changes to documents (new, modified, deleted) and triggers the ingestion process when changes are detected. The Scanner can be configured to run in batch mode (process all existing files on startup) and/or in real-time mode (monitor for changes).

### 2. Preprocessor

The Preprocessor component cleans and normalizes text from various document formats. It handles different file types (PDF, CSV, DOC, ODT, TXT, JSON, HTML, MARKDOWN, XLS) and applies preprocessing steps such as:
- Lowercasing
- Normalizing whitespace
- Removing stopwords
- Removing punctuation
- Removing numbers
- Removing non-ASCII characters
- Removing URLs
- Removing emails
- Removing HTML tags

### 3. Splitter

The Splitter component breaks documents into smaller chunks for embedding. It provides various text splitting algorithms optimized for different document types:
- Character-based splitting
- Recursive character-based splitting
- Token-based splitting
- JSON splitting
- HTML splitting
- Markdown splitting
- CSV splitting

### 4. Embedder

The Embedder component converts text chunks into vector embeddings using various embedding models:
- OpenAI embeddings
- Hugging Face embeddings
- Custom embeddings

### 5. Vector Database

The Vector Database component stores embeddings for efficient retrieval. It supports various vector database options:
- Qdrant
- Chroma
- Pinecone
- Redis
- PostgreSQL with pgvector

### 6. Retriever

The Retriever component finds relevant document chunks based on query similarity. It supports various retrieval methods:
- Dense retrieval (vector similarity)
- Hybrid retrieval (dense + sparse)

### 7. Augmentation Handler

The Augmentation Handler component enhances retrieved content using LLMs. It formats the retrieved chunks and sends them to the LLM for augmentation.

### 8. Pipeline

The Pipeline component orchestrates the flow of data through the components. It manages the lifecycle of the components and ensures that data flows correctly from one component to the next.

### 9. Tools

The Tools component provides interfaces for document ingestion and search. It exposes the following tools:
- `ingest_document`: Ingests a document into the RAG system
- `search_documents`: Searches for documents relevant to a query

## Lifecycle Management

The SAM RAG plugin provides lifecycle functions for initializing and cleaning up the RAG agent:

1. **initialize_rag_agent**: Initializes the RAG agent with the provided configuration
2. **cleanup_rag_agent_resources**: Cleans up resources used by the RAG agent

## Integration with ADK Framework

The SAM RAG plugin integrates with the ADK framework through:
- Tool registration
- Lifecycle function registration
- Artifact service integration
- Host component integration

## Data Flow

### Document Ingestion Flow

1. User uploads a document or the scanner detects a new/modified document
2. The document is preprocessed to extract and clean the text
3. The text is split into smaller chunks
4. The chunks are embedded into vector representations
5. The embeddings are stored in the vector database along with metadata

### Document Retrieval Flow

1. User submits a query
2. The query is embedded into a vector representation
3. The vector database is searched for similar vectors
4. The most relevant chunks are retrieved
5. The chunks are formatted and sent to the LLM for augmentation
6. The augmented response is returned to the user

## Configuration

The SAM RAG plugin is highly configurable, allowing users to customize each component of the RAG pipeline. See the [Configuration Guide](configuration.md) for detailed information about configuration options.

## Tools and Lifecycle Functions

For detailed information about the tools and lifecycle functions provided by the SAM RAG plugin, see the [Tools and Lifecycle Functions Guide](tools_and_lifecycle.md).