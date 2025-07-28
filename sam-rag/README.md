# Solace Agent Mesh RAG

A document-ingesting agent that monitors specified directories, keeping stored documents up to date in a vector database for Retrieval-Augmented Generation (RAG) queries.

## Overview

The Solace Agent Mesh RAG system provides a complete RAG pipeline that includes:

1. **Document Scanning**: Monitors directories for new, modified, or deleted documents
2. **Document Preprocessing**: Cleans and normalizes text from various document formats
3. **Text Splitting**: Breaks documents into smaller chunks for embedding
4. **Embedding Generation**: Converts text chunks into vector embeddings
5. **Vector Storage**: Stores embeddings in a vector database for efficient retrieval
6. **Retrieval**: Finds relevant document chunks based on query similarity
7. **Augmentation**: Enhances retrieved content using LLMs

## Documentation

Comprehensive documentation is available in the `docs` directory:

- [Architecture Overview](docs/architecture.md): High-level system architecture and component interactions
- [Configuration Guide](docs/configuration.md): Detailed explanation of configuration options
- [Tutorial](docs/tutorial.md): Step-by-step guide for setting up and using the system

### Component Documentation

- [Scanner](docs/components/scanner.md): Monitors document sources for changes
- [Preprocessor](docs/components/preprocessor.md): Extracts and cleans text from documents
- [Splitter](docs/components/splitter.md): Breaks documents into chunks for embedding
- [Embedder](docs/components/embedder.md): Converts text chunks to vector embeddings
- [Vector Database](docs/components/vector_db.md): Stores and retrieves vector embeddings
- [Retriever](docs/components/retriever.md): Searches for relevant documents
- [Augmentation](docs/components/augmentation.md): Enhances retrieved content using LLMs

## Installation

### Add the RAG Plugin to Solace Agent Mesh

```sh
solace-agent-mesh plugin add sam_rag --pip -u git+https://github.com/SolaceLabs/solace-agent-mesh-core-plugins#subdirectory=sam-rag
```

### Instantiate the RAG Agent

```sh
solace-agent-mesh add agent rag --copy-from sam_rag
```

### Rebuild Solace Agent Mesh

```sh
solace-agent-mesh build
```

## Configuration

The RAG agent is configured through the `configs/agents/rag.yaml` file. See the [Configuration Guide](docs/configuration.md) for detailed information.

### Key Configuration Sections

- **Scanner Configuration**: Document source and monitoring settings
- **Preprocessor Configuration**: Text extraction and cleaning settings
- **Splitter Configuration**: Document chunking settings
- **Embedding Configuration**: Vector embedding settings
- **Vector Database Configuration**: Storage and retrieval settings
- **LLM Configuration**: Language model settings for augmentation
- **Retrieval Configuration**: Search parameters

## Usage

### Running the RAG System

```sh
solace-agent-mesh run
```

### Querying the RAG System
(Option1): Open the SAM UI on the browser. By default, it is accessible on ```http://localhost:5001```
(Option2): Send a message to the appropriate topic:

```
${SOLACE_AGENT_MESH_NAMESPACE}solace-agent-mesh/v1/actionRequest/[session_id]/rag/rag_action
```

With a payload like:

```json
{
  "query": "Search documents about RAG agents?"
}
```

#### Ingesting documents
(Option1): Store documents in a specific directory and configure the directory path in the ```rag.yaml``` file.
After running SAM, the plugin ingests documents in background automatically.

(Option2): Open the SAM UI on the browser (by default ```http://localhost:5001```), attach files to a query such as "ingest the attached document to RAG".
This query persistently stores the attachments in file system and index them in vector database.

#### Retrieving documents
Use SAM UI on the browser (by default ```http://localhost:5001```) or any other interfaces and send a query such as "search documents about <your query> and return a summary and referenced documents". It retrieves top similar documents and returns a summary of documents align with their original documents.
