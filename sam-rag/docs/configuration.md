# Solace Agent Mesh RAG Configuration Guide

This document provides a comprehensive guide to configuring the Solace Agent Mesh RAG system through the `configs/agents/rag.yaml` file.

## Configuration Overview

The RAG agent is configured through the `configs/agents/rag.yaml` file, which contains settings for:

- Broker connection
- Document scanning
- Text preprocessing
- Document splitting
- Embedding generation
- Vector database storage
- LLM augmentation
- Retrieval parameters

## Configuration File Structure

The configuration file has the following high-level structure:

```yaml
log:
  # Logging configuration
  
shared_config:
  # Shared configuration for broker connection

flows:
  - name: rag_action_request_processor
    components:
      # Input component
      - component_name: broker_input
        # ...
      
      # RAG agent component
      - component_name: action_request_processor
        component_config:
          # Scanner configuration
          # Preprocessor configuration
          # Splitter configuration
          # Embedding configuration
          # Vector database configuration
          # LLM configuration
          # Retrieval configuration
      
      # Output component
      - component_name: broker_output
        # ...
```

## Detailed Configuration Sections

### Logging Configuration

```yaml
log:
  stdout_log_level: INFO
  log_file_level: INFO
  log_file: solace_ai_connector.log
```

- `stdout_log_level`: Log level for console output
- `log_file_level`: Log level for file output
- `log_file`: Log file name

### Broker Connection

```yaml
shared_config:
  - broker_config: &broker_connection
      dev_mode: ${SOLACE_DEV_MODE}
      broker_url: ${SOLACE_BROKER_URL}
      broker_username: ${SOLACE_BROKER_USERNAME}
      broker_password: ${SOLACE_BROKER_PASSWORD}
      broker_vpn: ${SOLACE_BROKER_VPN}
      temporary_queue: ${USE_TEMPORARY_QUEUES}
```

- `dev_mode`: Enable development mode
- `broker_url`: URL of the Solace broker
- `broker_username`: Username for broker authentication
- `broker_password`: Password for broker authentication
- `broker_vpn`: Solace message VPN
- `temporary_queue`: Whether to use temporary queues

### Scanner Configuration

```yaml
scanner:
  batch: true                # Process documents in batch mode
  use_memory_storage: true   # Use in-memory storage for tracking files
  source:
    type: filesystem         # Source type (filesystem or cloud)
    directories:
      - "DIRECTORY PATH"     # Path to directory containing documents
    filters:
      file_formats:          # Supported file formats
        - ".txt"
        - ".pdf"
        - ".docx"
        # ... other formats
      max_file_size: 10240   # Maximum file size in KB (10MB)
  database:                  # Database for storing metadata
    type: postgresql
    dbname: ${DB_NAME}
    host: ${DB_HOST}
    port: ${DB_PORT}
    user: ${DB_USER}
    Password: ${DB_PASSWORD}
  schedule:
    interval: 60             # Scanning interval in seconds
```

#### Key Scanner Parameters

- `batch`: When `true`, processes all existing documents in the specified directories during startup
- `use_memory_storage`: When `true`, stores file tracking information in memory; when `false`, uses the configured database
- `source.type`: The type of document source (`filesystem` or `cloud`)
- `source.directories`: List of directories to monitor for documents
- `source.filters.file_formats`: List of supported file extensions
- `source.filters.max_file_size`: Maximum file size in KB
- `database`: (Deprecated) Configuration for the metadata database (used when `use_memory_storage` is `false`)
- `schedule.interval`: How often to scan for changes (in seconds)

### Preprocessor Configuration

```yaml
preprocessor:
  default_preprocessor:      # Default settings for all document types
    type: enhanced
    params:
      lowercase: true              # Convert text to lowercase
      normalize_whitespace: true   # Normalize whitespace characters
      remove_stopwords: false      # Remove common stopwords
      remove_punctuation: false    # Remove punctuation
      remove_numbers: false        # Remove numeric characters
      remove_non_ascii: false      # Remove non-ASCII characters
      remove_urls: true            # Remove URLs
      remove_emails: false         # Remove email addresses
      remove_html_tags: false      # Remove HTML tags
  
  preprocessors:             # Type-specific preprocessor settings
    # Text file configurations
    text:
      type: text
      params:
        # Text-specific preprocessing parameters
    
    # Document file configurations
    pdf:
      type: document
      params:
        # PDF-specific preprocessing parameters
    
    # Additional file type configurations
    # ...
```

#### Key Preprocessor Parameters

- `default_preprocessor`: Default settings applied to all document types
- `preprocessors`: Type-specific settings that override the defaults for specific file types

#### Preprocessor Types

- `enhanced`: General-purpose text preprocessor with advanced options
- `text`: Specialized for plain text files
- `document`: Specialized for document files (PDF, DOCX, etc.)
- `structured`: Specialized for structured data files (JSON, etc.)
- `html`: Specialized for HTML files
- `markdown`: Specialized for Markdown files

#### Preprocessing Parameters

- `lowercase`: Convert text to lowercase
- `normalize_whitespace`: Replace multiple whitespace characters with a single space
- `remove_stopwords`: Remove common words like "the", "and", etc.
- `remove_punctuation`: Remove punctuation marks
- `remove_numbers`: Remove numeric characters
- `remove_non_ascii`: Remove non-ASCII characters
- `remove_urls`: Remove URLs
- `remove_emails`: Remove email addresses
- `remove_html_tags`: Remove HTML tags

### Splitter Configuration

```yaml
splitter:
  default_splitter:          # Default settings for all document types
    type: character
    params:
      chunk_size: 4096       # Size of each chunk
      chunk_overlap: 800     # Overlap between chunks
      separator: " "         # Text separator
  
  splitters:                 # Type-specific splitter settings
    # Text file configurations
    text:
      type: character
      params:
        chunk_size: 4096
        chunk_overlap: 800
        separator: " "
        is_separator_regex: false
        keep_separator: true
        strip_whitespace: true
    
    # Additional file type configurations
    # ...
```

#### Key Splitter Parameters

- `default_splitter`: Default settings applied to all document types
- `splitters`: Type-specific settings that override the defaults for specific file types

#### Splitter Types

- `character`: Splits text by character count
- `recursive_character`: Recursively splits text by different separators
- `token`: Splits text by token count
- `recursive_json`: Recursively splits JSON documents
- `html`: Specialized for HTML documents
- `markdown`: Specialized for Markdown documents
- `csv`: Specialized for CSV files

#### Splitting Parameters

- `chunk_size`: Maximum size of each chunk (in characters or tokens)
- `chunk_overlap`: Number of characters or tokens to overlap between chunks
- `separator`: Character or string to use as separator
- `is_separator_regex`: Whether the separator is a regular expression
- `keep_separator`: Whether to keep the separator in the output
- `strip_whitespace`: Whether to strip whitespace from the beginning and end of chunks

### Embedding Configuration

```yaml
embedding:
  embedder_type: "openai"    # Type of embedding model
  embedder_params:
    model: ${OPENAI_EMBEDDING_MODEL}
    api_key: ${OPENAI_API_KEY}
    api_base: ${OPENAI_API_ENDPOINT}
    batch_size: 32
    additional_kwargs: {}
  normalize_embeddings: True # Whether to normalize embedding vectors
```

#### Key Embedding Parameters

- `embedder_type`: The type of embedding model to use
- `embedder_params`: Parameters specific to the chosen embedding model
- `normalize_embeddings`: Whether to normalize embedding vectors (recommended for cosine similarity)

#### Supported Embedder Types

- `openai`: OpenAI embedding models
- `azure_openai`: Azure OpenAI embedding models
- `cohere`: Cohere embedding models
- `vertex_ai`: Google Vertex AI embedding models
- `litellm`: LiteLLM embedding models (supports multiple providers)

### Vector Database Configuration

```yaml
vector_db:
  # Qdrant configuration
  db_type: "qdrant"
  db_params:
    url: ${QDRANT_URL}
    api_key: ${QDRANT_API_KEY}
    collection_name: ${QDRANT_COLLECTION}
    embedding_dimension: ${QDRANT_EMBEDDING_DIMENSION}
```

#### Key Vector Database Parameters

- `db_type`: The type of vector database to use
- `db_params`: Parameters specific to the chosen vector database

#### Supported Vector Database Types

- `qdrant`: Qdrant vector database
- `chroma`: Chroma vector database
- `pinecone`: Pinecone vector database
- `pgvector`: PostgreSQL with pgvector extension

#### Common Vector Database Parameters

- `url`: URL of the vector database
- `api_key`: API key for authentication
- `collection_name`: Name of the collection to use
- `embedding_dimension`: Dimension of the embedding vectors

### LLM Configuration

```yaml
llm:
  load_balancer:
    - model_name: "gpt-4o" # model alias
      litellm_params:
            model: openai/${OPENAI_MODEL_NAME}
            api_key: ${OPENAI_API_KEY}
            api_base: ${OPENAI_API_ENDPOINT}
            temperature: 0.01
            # add any other parameters here
    - model_name: "claude-3-5-sonnet" # model alias
      litellm_params:
            model: anthropic/${ANTHROPIC_MODEL_NAME}
            api_key: ${ANTHROPIC_API_KEY}
            api_base: ${ANTHROPIC_API_ENDPOINT}
            # add any other parameters here
```

#### Key LLM Parameters

- `load_balancer`: List of LLM configurations for load balancing
- `model_name`: Alias for the model
- `litellm_params`: Parameters for LiteLLM

#### Common LiteLLM Parameters

- `model`: The model to use (provider/model_name format)
- `api_key`: API key for authentication
- `api_base`: Base URL for the API
- `temperature`: Temperature for generation (lower values are more deterministic)
- `max_tokens`: Maximum number of tokens to generate

### Retrieval Configuration

```yaml
retrieval:
  top_k: 7                   # Number of chunks to retrieve
```

#### Key Retrieval Parameters

- `top_k`: Number of chunks to retrieve for each query

## Environment Variables

The configuration file uses environment variables for sensitive information and deployment-specific settings. These variables should be set in the environment or in a `.env` file:

- `SOLACE_DEV_MODE`: Enable development mode
- `SOLACE_BROKER_URL`: URL of the Solace broker
- `SOLACE_BROKER_USERNAME`: Username for broker authentication
- `SOLACE_BROKER_PASSWORD`: Password for broker authentication
- `SOLACE_BROKER_VPN`: Solace message VPN
- `USE_TEMPORARY_QUEUES`: Whether to use temporary queues
- `SOLACE_AGENT_MESH_NAMESPACE`: Namespace for Solace Agent Mesh topics
- `OPENAI_EMBEDDING_MODEL`: OpenAI embedding model name
- `OPENAI_API_KEY`: OpenAI API key
- `OPENAI_API_ENDPOINT`: OpenAI API endpoint
- `OPENAI_MODEL_NAME`: OpenAI model name
- `ANTHROPIC_MODEL_NAME`: Anthropic model name
- `ANTHROPIC_API_KEY`: Anthropic API key
- `ANTHROPIC_API_ENDPOINT`: Anthropic API endpoint
- `QDRANT_URL`: Qdrant URL
- `QDRANT_API_KEY`: Qdrant API key
- `QDRANT_COLLECTION`: Qdrant collection name
- `QDRANT_EMBEDDING_DIMENSION`: Dimension of embedding vectors

## Configuration Examples

### Minimal Configuration

```yaml
scanner:
  batch: true
  use_memory_storage: true
  source:
    type: filesystem
    directories:
      - "/path/to/documents"
    filters:
      file_formats:
        - ".txt"
        - ".pdf"
      max_file_size: 10240
  schedule:
    interval: 60

preprocessor:
  default_preprocessor:
    type: enhanced
    params:
      lowercase: true
      normalize_whitespace: true

splitter:
  default_splitter:
    type: character
    params:
      chunk_size: 1000
      chunk_overlap: 200

embedding:
  embedder_type: "openai"
  embedder_params:
    model: "text-embedding-ada-002"
    api_key: "your-api-key"
  normalize_embeddings: true

vector_db:
  db_type: "qdrant"
  db_params:
    url: "http://localhost:6333"
    collection_name: "documents"
    embedding_dimension: 1536

retrieval:
  top_k: 5
```

### Advanced Configuration

See the full `configs/agents/rag.yaml` file for an advanced configuration example.

## Next Steps

- [Architecture Overview](architecture.md)
- [Tutorial](tutorial.md)
