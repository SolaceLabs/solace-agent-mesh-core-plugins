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
- [Configuration Guide](docs/configuration.md): Detailed explanation of configuration options

## Installation

### Add the RAG Plugin to Solace Agent Mesh

```sh
solace-agent-mesh plugin add <your-new-component-name> --plugin sam-rag
```
This will create a new component configuration at configs/plugins/<your-new-component-name-kebab-case>.yaml. You need to configure proper values by updating this file. Export at least the following environment variables to work with the default configuration. For more advance settings, please visit the [Configuration Guide](docs/configuration.md).

```
export SOLACE_BROKER_URL=ws://localhost:8008
export SOLACE_BROKER_USERNAME=admin
export SOLACE_BROKER_PASSWORD=admin
export SOLACE_BROKER_VPN=default
export SOLACE_IS_QUEUE_TEMPORARY=true

export OPENAI_MODEL_NAME=<LLM MODEL NAME>
export OPENAI_API_KEY=<LLM KEY>
export OPENAI_API_ENDPOINT=<LLM ENDPOINT>

export QDRANT_URL=<QDRANT CLUSTER URL>
export QDRANT_API_KEY=<QDRANT API KEY>
export QDRANT_COLLECTION=<A NAME FOR QDRANT COLLECTION>
export QDRANT_EMBEDDING_DIMENSION=1024
export DOCUMENTS_PATH=<PATH OF SOURCE DOCUMENTS IN LOCAL DISK>
```

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
Open the SAM UI on the browser.

#### Ingesting documents
(Option1): Store documents in a specific directory and configure the directory path in the ```rag.yaml``` file.
After running SAM, the plugin ingests documents in background automatically.

(Option2): Open the SAM UI on the browser (by default ```http://localhost:5001```), attach files to a query such as "ingest the attached document to RAG".
This query persistently stores the attachments in file system and index them in vector database.

#### Retrieving documents
Use SAM UI on the browser (by default ```http://localhost:5001```) or any other interfaces and send a query such as "search documents about <your query> and return a summary and referenced documents". It retrieves top similar documents and returns a summary of documents align with their original documents.
