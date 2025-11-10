# SAM RAG Configuration Guide

## Introduction

The Solace Agent Mesh RAG (Retrieval Augmented Generation) plugin requires specific configuration to function properly. This document outlines the required and optional configuration parameters for setting up and customizing the SAM RAG plugin.

The configuration is defined in the main A2A ADK Host YAML configuration file, typically under the `apps:` list. The SAM RAG plugin uses a hierarchical configuration structure that allows for fine-grained control over each component of the RAG pipeline.

## Required Configurations

The following configurations are required for the SAM RAG plugin to function properly:

### Shared Configuration

The shared configuration section defines reusable configuration blocks that can be referenced elsewhere in the configuration file using YAML anchors and aliases. Similar to other plugins, the Solace broker and LLM model are configured in this section. 

```yaml
shared_config:
  - broker_connection: &broker_connection
      dev_mode: ${SOLACE_DEV_MODE, false} # Whether to run in development mode
      broker_url: ${SOLACE_BROKER_URL, ws://localhost:8080} # URL of the Solace broker
      broker_username: ${SOLACE_BROKER_USERNAME, default} # Username for the Solace broker
      broker_password: ${SOLACE_BROKER_PASSWORD, default} # Password for the Solace broker
      broker_vpn: ${SOLACE_BROKER_VPN, default} # VPN for the Solace broker
      temporary_queue: ${USE_TEMPORARY_QUEUES, true} # Whether to use temporary queues

  - models:
    general: &general_model
      model: ${LLM_SERVICE_GENERAL_MODEL_NAME} # Use env var for model name
      api_base: ${LLM_SERVICE_ENDPOINT} # Use env var for endpoint URL
      api_key: ${LLM_SERVICE_API_KEY} # Use env var for API key
```

The shared configuration can then be referenced in the application configuration using YAML aliases:

```yaml
apps:
  - name: your-app-name
    app_module: solace_agent_mesh.agent.sac.app
    broker:
      <<: *broker_connection  # References the broker_connection anchor
    app_config:
      namespace: "${NAMESPACE}" # Your A2A topic namespace
      agent_name: "YourAgentName"
      display_name: "Your Agent Display Name"
      supports_streaming: true # RAG agent supports streaming responses
```

### RAG Configuration
RAG includes multiple steps (scanning, preprocessing, splitting, ingesting, and retrieval). Each step should be configured.

#### Preprocessor Configuration

The preprocessor configuration defines how text is extracted and cleaned from various document formats (e.g., PDF, CSV, DOC, ODT, TXT, JSON, HTML, MARKDOWN, XLS). Enable and disable parameters to apply/discard preprocessing steps.

```yaml
preprocessor:
  default_preprocessor:  # Default preprocessor configuration
    type: enhanced
    params:
      lowercase: true
      normalize_whitespace: true
      remove_stopwords: false
      remove_punctuation: false
      remove_numbers: false
      remove_non_ascii: false
      remove_urls: true
      remove_emails: false
      remove_html_tags: false
  preprocessors:  # File-specific preprocessors
    # RAW text file configurations
    text:
      type: text
      params:
        lowercase: true
        normalize_whitespace: true
        remove_stopwords: false
        remove_punctuation: true
        remove_numbers: false
        remove_non_ascii: false
        remove_urls: true
        remove_emails: false
        remove_html_tags: false
    
    # PDF configurations
    pdf: 
      type: document
      params:
        lowercase: true
        normalize_whitespace: true
        remove_stopwords: false
        remove_punctuation: true
        remove_numbers: false
        remove_non_ascii: true
        remove_urls: true
        remove_emails: true
        remove_html_tags: false
    
    # Additional file type configurations for doc, odt, json, html, markdown, csv, xls, etc.
```

#### Splitter Configuration

The splitter configuration defines how documents are broken into smaller chunks for embedding. The SAM RAG plugin provides various text splitting algorithms optimized for different document types.

#### Configuration Structure

The splitter configuration has two main components: The default splitter and splitter for each file format. Each one needs a splitter algorithm.

```yaml
splitter:
  default_splitter:
    # Default splitter configuration used when no specific splitter is found
    type: character # the splitter algorithm type
    params:
      # Parameters specific to this splitter type
  
  splitters:
    # File type-specific splitters
    text:
      type: character
      params:
        # Parameters for text files
    
    json:
      type: recursive_json
      params:
        # Parameters for JSON files
```

##### Available Splitter Algorithms

###### Text Splitters

1. **character**
   - **Algorithm: CharacterTextSplitter**
   - **Description**: Splits text based on character count
   - **Best for**: Simple text splitting with consistent formatting
   - **Parameters**:
     - `chunk_size`: Maximum number of characters per chunk (default: 1000)
     - `chunk_overlap`: Number of characters to overlap between chunks (default: 200)
     - `separator`: Character or string to split on (default: " ")
     - `is_separator_regex`: Whether the separator is a regex pattern (default: false)
     - `keep_separator`: Whether to keep the separator in the chunks (default: true)
     - `strip_whitespace`: Whether to strip whitespace from chunk edges (default: true)

2. **recursive_character**
   - **Algorithm: RecursiveCharacterTextSplitter**
   - **Description**: Splits text recursively using multiple separators
   - **Best for**: General-purpose text splitting with varied formatting
   - **Parameters**:
     - `chunk_size`: Maximum number of characters per chunk (default: 1000)
     - `chunk_overlap`: Number of characters to overlap between chunks (default: 200)
     - `separators`: List of separators to try in order (default: ["\n\n", "\n", " ", ""])
     - `is_separator_regex`: Whether the separators are regex patterns (default: false)
     - `keep_separator`: Whether to keep the separator in the chunks (default: true)
     - `strip_whitespace`: Whether to strip whitespace from chunk edges (default: true)

3. **token**:
   - **Algorithm: TokenTextSplitter**
   - **Description**: Splits text based on token count using tiktoken library
   - **Best for**: Precise token-based splitting for LLM context windows
   - **Parameters**:
     - `chunk_size`: Maximum number of tokens per chunk (default: 500)
     - `chunk_overlap`: Number of tokens to overlap between chunks (default: 100)
     - `encoding_name`: Tiktoken encoding name (default: "cl100k_base")

###### Structured Data Splitters

4. **json**
   - **Algorithm: JSONSplitter**
   - **Description**: Basic JSON splitter that formats and splits JSON data
   - **Best for**: Simple JSON documents
   - **Parameters**:
     - `chunk_size`: Maximum number of characters per chunk (default: 1000)
     - `chunk_overlap`: Number of characters to overlap between chunks (default: 200)

5. **recursive_json**
   - **Algorithm: RecursiveJSONSplitter**
   - **Description**: Advanced JSON splitter that traverses the JSON structure recursively
   - **Best for**: Complex nested JSON structures
   - **Parameters**:
     - `chunk_size`: Maximum number of characters per chunk (default: 1000)
     - `chunk_overlap`: Number of characters to overlap between chunks (default: 200)
     - `include_metadata`: Whether to include metadata about JSON structure (default: true)

6. **html**
   - **Algorithm: HTMLSplitter**
   - **Description**: Splits HTML documents based on HTML tags
   - **Best for**: HTML documents with semantic structure
   - **Parameters**:
     - `chunk_size`: Maximum number of characters per chunk (default: 1000)
     - `chunk_overlap`: Number of characters to overlap between chunks (default: 200)
     - `tags_to_extract`: HTML tags to extract as separate chunks (default: ["div", "p", "section", "article"])

7. **markdown**
   - **Algorithm: MarkdownSplitter**
   - **Description**: Splits Markdown documents based on headers
   - **Best for**: Markdown documents with header-based structure
   - **Parameters**:
     - `chunk_size`: Maximum number of characters per chunk (default: 1000)
     - `chunk_overlap`: Number of characters to overlap between chunks (default: 200)
     - `headers_to_split_on`: Headers to split on, in order of hierarchy (default: ["#", "##", "###", "####", "#####", "######"])
     - `strip_headers`: Whether to remove headers from the content (default: false)

8. **csv**
   - **Algorithm: CSVSplitter**
   - **Description**: Splits CSV files by rows
   - **Best for**: Tabular data in CSV format
   - **Parameters**:
     - `chunk_size`: Number of rows per chunk (default: 100)
     - `include_header`: Whether to include the header row in each chunk (default: true)

##### Parameter Selection Guidelines

When configuring splitters, consider these guidelines:

- **Chunk Size**:
  - For text: 1000-4000 characters is typical
  - For tokens: 256-1024 tokens works well for most LLMs
  - For CSV: Depends on row complexity (10-1000 rows)

- **Chunk Overlap**:
  - Usually 10-20% of chunk size
  - Higher overlap improves context preservation between chunks
  - Lower overlap reduces redundancy and storage requirements

- **Separators**:
  - Choose natural boundaries in your text (paragraphs, sentences)
  - For code, consider language-specific separators (function boundaries, class definitions)

##### Example Configuration

Here's a comprehensive example that configures all splitter types with detailed parameters:

```yaml
splitter:
  # Default splitter used when no specific splitter is found for a file type
  default_splitter:
    type: recursive_character
    params:
      chunk_size: 2048          # Maximum characters per chunk
      chunk_overlap: 400        # Character overlap between chunks
      separators: ["\n\n", "\n", " ", ""]  # Try paragraph breaks, then line breaks, etc.
      is_separator_regex: false # Treat separators as literal strings, not regex
      keep_separator: true      # Keep the separator in the output chunks
      strip_whitespace: true    # Remove leading/trailing whitespace from chunks
  
  # File type-specific splitters
  splitters:
    # Plain text files - Character splitter
    text:
      type: character
      params:
        chunk_size: 2048        # Characters per chunk
        chunk_overlap: 400      # Character overlap
        separator: " "          # Split on spaces
        is_separator_regex: false
        keep_separator: true
        strip_whitespace: true
    
    # Text files with line-based structure
    txt:
      type: character
      params:
        chunk_size: 2048
        chunk_overlap: 400
        separator: "\n"         # Split on newlines
        is_separator_regex: false
        keep_separator: true
        strip_whitespace: true
    
    # Large documents where token count matters
    pdf:
      type: token
      params:
        chunk_size: 500         # Tokens per chunk (for LLM context windows)
        chunk_overlap: 100      # Token overlap
        encoding_name: "cl100k_base"  # OpenAI's encoding
    
    # JSON data - Basic splitter
    json:
      type: json
      params:
        chunk_size: 1000
        chunk_overlap: 200
    
    # JSON data - Advanced recursive splitter
    json_complex:
      type: recursive_json
      params:
        chunk_size: 200         # Characters per JSON chunk
        chunk_overlap: 50       # Character overlap
        include_metadata: true  # Include path information in JSON structure
    
    # HTML documents
    html:
      type: html
      params:
        chunk_size: 2048
        chunk_overlap: 400
        tags_to_extract: ["p", "h1", "h2", "h3", "li", "div", "section", "article"]
                              # Extract content from these HTML tags
    
    # Markdown documents
    markdown:
      type: markdown
      params:
        chunk_size: 2048
        chunk_overlap: 400
        headers_to_split_on: ["#", "##", "###", "####", "#####", "######"]
                              # Split on headers of different levels
        strip_headers: false   # Keep headers in the content
    
    # CSV data
    csv:
      type: csv
      params:
        chunk_size: 100        # 100 rows per chunk
        include_header: true   # Include header row in each chunk
```

#### LLM Configuration

The LLM configuration defines the language models used for augmentation. Multiple models can be configured for load balancing.

```yaml
llm:
  load_balancer:
    - model_name: "gpt-4o"  # model alias
      litellm_params:
        model: openai/${OPENAI_MODEL_NAME}
        api_key: ${OPENAI_API_KEY}
        api_base: ${OPENAI_API_ENDPOINT}
        temperature: 0.01
    - model_name: "claude-3-5-sonnet"  # model alias
      litellm_params:
        model: anthropic/${ANTHROPIC_MODEL_NAME}
        api_key: ${ANTHROPIC_API_KEY}
        api_base: ${ANTHROPIC_API_ENDPOINT}
    # Additional models can be added here
```

#### Retrieval Configuration

The retrieval configuration defines how relevant documents are retrieved.

```yaml
retrieval:
  top_k: 7  # Number of documents to retrieve (default: 5)
```

#### Embedding Configuration

The embedding configuration defines how text is converted into vector embeddings.

```yaml
embedding:
  embedder_type: "openai"  # Required: Type of embedder to use
  embedder_params:         # Parameters for the embedder
    model: "${OPENAI_EMBEDDING_MODEL}"
    api_key: "${OPENAI_API_KEY}"
    api_base: "${OPENAI_API_ENDPOINT}"
    batch_size: 32
    additional_kwargs: {}
  normalize_embeddings: true  # Whether to normalize embeddings (default: true)
  hybrid_search:              # Optional: Configuration for hybrid search
    sparse_model_config:      # Configuration for sparse vector model
      type: "tfidf"          # Type of sparse model (e.g., "tfidf")
      params: {}             # Model-specific parameters
```

**Required Parameters:**
- `embedder_type`: The type of embedder to use (e.g., "openai", "huggingface", etc.)

**Optional Parameters:**
- `embedder_params`: Parameters specific to the chosen embedder
- `normalize_embeddings`: Whether to normalize embeddings (default: true)
- `hybrid_search`: Configuration for hybrid search (dense + sparse retrieval)

#### Vector Database Configuration

The vector database configuration defines where and how vector embeddings are stored and retrieved. Several vector database options are supported. You need to set only one database.

##### Qdrant

```yaml
vector_db:
  db_type: "qdrant"  # Required: Type of vector database
  db_params:         # Parameters for the vector database
    url: "${QDRANT_URL}"
    api_key: "${QDRANT_API_KEY}"
    collection_name: "${QDRANT_COLLECTION}"
    embedding_dimension: ${QDRANT_EMBEDDING_DIMENSION}
    hybrid_search_params:     # Optional: Qdrant-specific hybrid search parameters
      sparse_vector_name: "sparse_db"  # Name for the sparse vector in Qdrant
```

##### Chroma

```yaml
vector_db:
  db_type: "chroma"
  db_params:
    host: "${CHROMA_HOST}"
    port: "${CHROMA_PORT}"
    collection_name: "${CHROMA_COLLECTION}"
    persist_directory: "${CHROMA_PERSIST_DIR, './chroma_db'}"
    embedding_function: "${CHROMA_EMBEDDING_FUNCTION}"
    embedding_dimension: ${CHROMA_EMBEDDING_DIMENSION}
```

##### Pinecone

```yaml
vector_db:
  db_type: "pinecone"
  db_params:
    api_key: "${PINECONE_API_KEY}"
    index_name: "${PINECONE_INDEX}"
    namespace: "${PINECONE_NAMESPACE}"
    embedding_dimension: ${PINECONE_DIMENSIONS}
    metric: "${PINECONE_METRIC}"
    cloud: "${PINECONE_CLOUD}"
    region: "${PINECONE_REGION}"
    hybrid_search_params:
      alpha: 0.5  # 0.0 for pure sparse, 1.0 for pure dense
```

##### Redis

```yaml
vector_db:
  db_type: "redis"
  db_params:
    url: "${REDIS_URL}"  # e.g., redis://localhost:6379
    index_name: "${REDIS_INDEX_NAME}"
    embedding_dimension: ${REDIS_EMBEDDING_DIMENSION}
    text_field_name: "content"
    vector_field_name: "embedding"
    hybrid_search_params:
      text_score_weight: 0.3
      vector_score_weight: 0.7
```

##### PostgreSQL with pgvector

```yaml
vector_db:
  db_type: "pgvector"
  db_params:
    host: "${PGVECTOR_HOST, 'localhost'}"
    port: "${PGVECTOR_PORT, 5432}"
    database: "${PGVECTOR_DATABASE, 'vectordb'}"
    user: "${PGVECTOR_USER, 'postgres'}"
    password: "${PGVECTOR_PASSWORD}"
    table_name: "${PGVECTOR_TABLE, 'document_embeddings'}"
    embedding_dimension: ${PGVECTOR_DIMENSION, 1024}
```

You should set the following environment variables for each database.
- **OpenAI:**
  - `OPENAI_EMBEDDING_MODEL`: Name of the OpenAI embedding model
  - `OPENAI_API_KEY`: API key for OpenAI
  - `OPENAI_API_ENDPOINT`: Endpoint URL for OpenAI
  - `OPENAI_MODEL_NAME`: Name of the OpenAI model

- **Anthropic:**
  - `ANTHROPIC_MODEL_NAME`: Name of the Anthropic model
  - `ANTHROPIC_API_KEY`: API key for Anthropic
  - `ANTHROPIC_API_ENDPOINT`: Endpoint URL for Anthropic

- **Qdrant:**
  - `QDRANT_URL`: URL of the Qdrant vector database
  - `QDRANT_API_KEY`: API key for Qdrant
  - `QDRANT_COLLECTION`: Name of the Qdrant collection
  - `QDRANT_EMBEDDING_DIMENSION`: Dimension of the embeddings

- **Chroma:**
  - `CHROMA_HOST`: Host for Chroma DB
  - `CHROMA_PORT`: Port for Chroma DB
  - `CHROMA_COLLECTION`: Collection name for Chroma DB
  - `CHROMA_PERSIST_DIR`: Persistence directory for Chroma DB
  - `CHROMA_EMBEDDING_FUNCTION`: Embedding function for Chroma DB

- **Pinecone:**
  - `PINECONE_API_KEY`: API key for Pinecone
  - `PINECONE_INDEX`: Index name for Pinecone
  - `PINECONE_NAMESPACE`: Namespace for Pinecone
  - `PINECONE_DIMENSIONS`: Dimensions for Pinecone embeddings
  - `PINECONE_METRIC`: Metric for Pinecone (e.g., "cosine")
  - `PINECONE_CLOUD`: Cloud provider for Pinecone
  - `PINECONE_REGION`: Region for Pinecone

- **Redis:**
  - `REDIS_URL`: URL for Redis
  - `REDIS_INDEX_NAME`: Index name for Redis
  - `REDIS_EMBEDDING_DIMENSION`: Dimension of embeddings for Redis

- **PostgreSQL with pgvector:**
  - `PGVECTOR_HOST`: Host for PostgreSQL
  - `PGVECTOR_PORT`: Port for PostgreSQL
  - `PGVECTOR_DATABASE`: Database name for PostgreSQL
  - `PGVECTOR_USER`: User for PostgreSQL
  - `PGVECTOR_PASSWORD`: Password for PostgreSQL
  - `PGVECTOR_TABLE`: Table name for PostgreSQL
  - `PGVECTOR_DIMENSION`: Dimension of embeddings for PostgreSQL

**Optional Parameters:**
- Database-specific optional parameters (varies by database type)
- `hybrid_search_params`: Parameters for hybrid search (if enabled)

### Optional Configurations

The following configurations are optional and have default values:

#### Hybrid Search Configuration

The hybrid search configuration enables combining dense vector search with sparse retrieval methods.

```yaml
hybrid_search:
  enabled: ${HYBRID_SEARCH_ENABLED}  # Global toggle for hybrid search
```

Set this environment variable to enable/disable the hybrid search.
- **Hybrid Search:**
  - `HYBRID_SEARCH_ENABLED`: Whether to enable hybrid search

#### Scanner Configuration

The scanner configuration defines how documents are discovered and monitored. The SAM RAG plugin supports multiple document sources, including local filesystem and cloud storage providers.

##### Basic Scanner Configuration

```yaml
scanner:
  batch: true  # Process existing files on startup (default: true)
  use_memory_storage: true  # Use in-memory storage (default: true)
  source:  # Single source configuration
    type: filesystem
    directories:
      - "DIRECTORY_PATH"  # Path to documents directory
    filters:
      file_formats:
        - ".txt"
        - ".pdf"
        - ".docx"
        - ".doc"
        - ".md"
        - ".html"
        - ".csv"
        - ".json"
        - ".odt"
        - ".xlsx"
        - ".xls"
      max_file_size: 10240  # in KB (10MB)
  database:  # DEPRECATED: Optional for persistent metadata storage
    type: postgresql
    dbname: ${DB_NAME}  # deprecated
    host: ${DB_HOST}    # deprecated
    port: ${DB_PORT}    # deprecated
    user: ${DB_USER}    # deprecated
    password: ${DB_PASSWORD}  # deprecated
  schedule:
    interval: 60  # seconds (default: 60)
```

Set these environment variables for the database. This feature has been deprecated and will be removed. It is enabled when ```use_memory_storage``` is false.
- **Database (for scanner metadata):** **(DEPRECATED)**
  - `DB_NAME`: Database name (deprecated)
  - `DB_HOST`: Database host (deprecated)
  - `DB_PORT`: Database port (deprecated)
  - `DB_USER`: Database user (deprecated)
  - `DB_PASSWORD`: Database password (deprecated)


##### Multi-Cloud Scanner Configuration

The scanner can be configured to ingest documents from filesystem or cloud sources simultaneously. If any source is configured, the scanner fetches documents from the source and ingest into vector database.

```yaml
scanner:
  batch: true # set true to enable batch processing
  use_memory_storage: true # set true to temporarily store links to files in memory rather than database
  
  # Multiple cloud sources configuration
  sources:
    # Local file system source
    - type: filesystem
      directories:
        - "${DOCUMENTS_PATH}"  # e.g. "/path/to/local/documents"
      filters:
        file_formats:
          - ".txt"
          - ".pdf"
          - ".docx"
          # Additional formats...
        max_file_size: 10240  # in KB (10MB)
      schedule:
        interval: 60  # seconds
    
    # Google Drive source
    - type: google_drive
      provider: google_drive
      # OAuth2 Authentication (Default)
      credentials_path: "${GOOGLE_DRIVE_CREDENTIALS_PATH}"
      
      # OR Service Account Authentication
      # auth_type: "service_account"  # Use Service Account instead of OAuth2
      # service_account_key_path: "${GOOGLE_SERVICE_ACCOUNT_KEY_PATH}" # e.g. "/path/to/service-account-key.json"
      
      folders:
        - folder_id: "${GOOGLE_DRIVE_FOLDER_ID_1}"
          name: "Documents"
          recursive: true
          type: "personal"
        - folder_id: "${GOOGLE_DRIVE_FOLDER_ID_2}"
          name: "Shared Drive"
          recursive: true
          type: "shared_drive"
      filters:
        file_formats:
          - ".txt"
          - ".pdf"
          - ".docx"
          # Additional formats...
        max_file_size: 10240  # in KB (10MB)
        include_google_formats: true  # Include Google Docs, Sheets, Slides
      real_time:
        enabled: true
        webhook_url: "${GOOGLE_DRIVE_WEBHOOK_URL}"
        polling_interval: 300  # 5 minutes
    
    # OneDrive source
    - type: onedrive
      provider: onedrive
      client_id: "${ONEDRIVE_CLIENT_ID}"
      client_secret: "${ONEDRIVE_CLIENT_SECRET}"
      tenant_id: "${ONEDRIVE_TENANT_ID}"
      account_type: "business"  # or "personal"
      folders:
        - path: "/Documents"
          name: "Documents"
          recursive: true
        - path: "/Shared Documents"
          name: "Shared Documents"
          recursive: true
      filters:
        file_formats:
          - ".txt"
          - ".pdf"
          - ".docx"
          # Additional formats...
        max_file_size: 10240  # in KB (10MB)
      real_time:
        enabled: true
        webhook_url: "${ONEDRIVE_WEBHOOK_URL}"
        polling_interval: 300  # 5 minutes
    
    # AWS S3 source
    - type: s3
      provider: s3
      bucket_name: "${S3_BUCKET_NAME}"
      region: "${S3_REGION}"
      access_key_id: "${AWS_ACCESS_KEY_ID}"
      secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
      folders:
        - prefix: "documents/"
          name: "Documents"
          recursive: true
        - prefix: "reports/"
          name: "Reports"
          recursive: true
      filters:
        file_formats:
          - ".txt"
          - ".pdf"
          - ".docx"
          # Additional formats...
        max_file_size: 10240  # in KB (10MB)
      real_time:
        enabled: true
        sqs_queue_url: "${S3_SQS_QUEUE_URL}"
        polling_interval: 300  # 5 minutes
```

Set the following environment variables for the aforementioned sources:
- **Filesystem Sources:**
  - `DOCUMENTS_PATH`: Path to local documents directory for batch scanning documents.
  
  - **Google Drive:**
    - `GOOGLE_DRIVE_CREDENTIALS_PATH`: Path to Google Drive credentials file (for OAuth2)
    - `GOOGLE_SERVICE_ACCOUNT_KEY_PATH`: Path to service account key file (for service account auth)
    - `GOOGLE_DRIVE_FOLDER_ID_1`, `GOOGLE_DRIVE_FOLDER_ID_2`: IDs of Google Drive folders to monitor
    - `GOOGLE_DRIVE_WEBHOOK_URL`: Webhook URL for real-time updates
  
  - **OneDrive:**
    - `ONEDRIVE_CLIENT_ID`: Client ID for OneDrive API
    - `ONEDRIVE_CLIENT_SECRET`: Client secret for OneDrive API
    - `ONEDRIVE_TENANT_ID`: Tenant ID for OneDrive (for business accounts)
    - `ONEDRIVE_WEBHOOK_URL`: Webhook URL for real-time updates
  
  - **AWS S3:**
    - `S3_BUCKET_NAME`: Name of the S3 bucket
    - `S3_REGION`: AWS region for the S3 bucket
    - `AWS_ACCESS_KEY_ID`: AWS access key ID
    - `AWS_SECRET_ACCESS_KEY`: AWS secret access key
    - `S3_SQS_QUEUE_URL`: URL for SQS queue for real-time updates