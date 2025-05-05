# Solace Agent Mesh RAG Tutorial

This tutorial provides step-by-step instructions for setting up, configuring, and using the Solace Agent Mesh RAG system.

## Prerequisites

Before you begin, ensure you have:

1. Solace Agent Mesh installed
2. Access to a Solace broker
3. Access to a vector database (Qdrant, Chroma, Pinecone, or PostgreSQL with pgvector)
4. API keys for embedding and LLM services (OpenAI, Anthropic, etc.)

## Installation

### 1. Add the RAG Plugin to Solace Agent Mesh

```sh
solace-agent-mesh plugin add sam_rag --pip -u git+https://github.com/SolaceLabs/solace-agent-mesh-core-plugins#subdirectory=sam-rag
```

### 2. Instantiate the RAG Agent

```sh
solace-agent-mesh add agent rag --copy-from sam_rag
```

You can repeat this step to connect to multiple collections/databases.

### 3. Rebuild Solace Agent Mesh

```sh
solace-agent-mesh build
```

## Basic Configuration

### 1. Set Environment Variables

Create a `.env` file or set environment variables for sensitive information:

```sh
# Solace Broker
export SOLACE_DEV_MODE=true
export SOLACE_BROKER_URL="tcp://localhost:55555"
export SOLACE_BROKER_USERNAME="admin"
export SOLACE_BROKER_PASSWORD="admin"
export SOLACE_BROKER_VPN="default"
export USE_TEMPORARY_QUEUES=true
export SOLACE_AGENT_MESH_NAMESPACE="my-namespace/"

# OpenAI
export OPENAI_EMBEDDING_MODEL="text-embedding-ada-002"
export OPENAI_API_KEY="your-openai-api-key"
export OPENAI_API_ENDPOINT="https://api.openai.com/v1"
export OPENAI_MODEL_NAME="gpt-4o"

# Anthropic (optional)
export ANTHROPIC_MODEL_NAME="claude-3-5-sonnet"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export ANTHROPIC_API_ENDPOINT="https://api.anthropic.com"

# Qdrant
export QDRANT_URL="http://localhost:6333"
export QDRANT_API_KEY="your-qdrant-api-key"
export QDRANT_COLLECTION="documents"
export QDRANT_EMBEDDING_DIMENSION=1536
```

### 2. Configure Document Sources

Edit the `configs/agents/rag.yaml` file to specify the directories to monitor:

```yaml
scanner:
  batch: true
  use_memory_storage: true
  source:
    type: filesystem
    directories:
      - "/path/to/your/documents"
    filters:
      file_formats:
        - ".txt"
        - ".pdf"
        - ".docx"
        - ".md"
      max_file_size: 10240
  schedule:
    interval: 60
```

### 3. Configure Vector Database

Choose and configure your preferred vector database in the `configs/agents/rag.yaml` file:

#### Qdrant Example

```yaml
vector_db:
  db_type: "qdrant"
  db_params:
    url: ${QDRANT_URL}
    api_key: ${QDRANT_API_KEY}
    collection_name: ${QDRANT_COLLECTION}
    embedding_dimension: ${QDRANT_EMBEDDING_DIMENSION}
```

#### Chroma Example

```yaml
vector_db:
  db_type: "chroma"
  db_params:
    host: ${CHROMA_HOST}
    port: ${CHROMA_PORT}
    collection_name: ${CHROMA_COLLECTION}
    persist_directory: ${CHROMA_PERSIST_DIR}
    embedding_function: ${CHROMA_EMBEDDING_FUNCTION}
    embedding_dimension: ${CHROMA_EMBEDDING_DIMENSION}
```

#### Pinecone Example

```yaml
vector_db:
  db_type: "pinecone"
  db_params:
    api_key: ${PINECONE_API_KEY}
    index_name: ${PINECONE_INDEX}
    namespace: ${PINECONE_NAMESPACE}
    embedding_dimension: ${PINECONE_DIMENSIONS}
    metric: ${PINECONE_METRIC}
    cloud: ${PINECONE_CLOUD}
    region: ${PINECONE_REGION}
```

#### PostgreSQL with pgvector Example

```yaml
vector_db:
  db_type: "pgvector"
  db_params:
    host: ${PGVECTOR_HOST}
    port: ${PGVECTOR_PORT}
    database: ${PGVECTOR_DATABASE}
    user: ${PGVECTOR_USER}
    password: ${PGVECTOR_PASSWORD}
    table_name: ${PGVECTOR_TABLE}
    embedding_dimension: ${PGVECTOR_DIMENSION}
```

### 4. Configure Embedding Service

Configure the embedding service in the `configs/agents/rag.yaml` file:

```yaml
embedding:
  embedder_type: "openai"
  embedder_params:
    model: ${OPENAI_EMBEDDING_MODEL}
    api_key: ${OPENAI_API_KEY}
    api_base: ${OPENAI_API_ENDPOINT}
    batch_size: 32
  normalize_embeddings: True
```

### 5. Configure LLM for Augmentation

Configure the LLM service for augmentation in the `configs/agents/rag.yaml` file:

```yaml
llm:
  load_balancer:
    - model_name: "gpt-4o"
      litellm_params:
        model: openai/${OPENAI_MODEL_NAME}
        api_key: ${OPENAI_API_KEY}
        api_base: ${OPENAI_API_ENDPOINT}
        temperature: 0.01
    - model_name: "claude-3-5-sonnet"
      litellm_params:
        model: anthropic/${ANTHROPIC_MODEL_NAME}
        api_key: ${ANTHROPIC_API_KEY}
        api_base: ${ANTHROPIC_API_ENDPOINT}
```

## Running the RAG System

### 1. Start Solace Agent Mesh

```sh
solace-agent-mesh run
```

### 2. Monitor Document Ingestion

When the RAG agent starts, it will:

1. Scan the configured directories for documents
2. Process existing documents if `batch` is set to `true`
3. Monitor for new, modified, or deleted documents
4. Ingest documents into the vector database

You can monitor the ingestion process in the logs:

```sh
tail -f solace_ai_connector.log
```

### 3. Query the RAG System

You can query the RAG system through the Solace broker by sending a message to the appropriate topic:

```
${SOLACE_AGENT_MESH_NAMESPACE}solace-agent-mesh/v1/actionRequest/[session_id]/rag/rag_action
```

With a payload like:

```json
{
  "query": "What is Solace Agent Mesh RAG?"
}
```

The response will be published to:

```
${SOLACE_AGENT_MESH_NAMESPACE}solace-agent-mesh/v1/actionResponse/[session_id]/rag/rag_action
```

## Advanced Configuration

### Customizing Preprocessors

You can customize preprocessors for different file types in the `configs/agents/rag.yaml` file:

```yaml
preprocessor:
  default_preprocessor:
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
  
  preprocessors:
    text:
      type: text
      params:
        lowercase: true
        normalize_whitespace: true
        remove_stopwords: false
        remove_punctuation: true
    
    pdf:
      type: document
      params:
        lowercase: true
        normalize_whitespace: true
        remove_non_ascii: true
```

### Customizing Splitters

You can customize splitters for different file types in the `configs/agents/rag.yaml` file:

```yaml
splitter:
  default_splitter:
    type: character
    params:
      chunk_size: 4096
      chunk_overlap: 800
      separator: " "
  
  splitters:
    text:
      type: character
      params:
        chunk_size: 4096
        chunk_overlap: 800
        separator: " "
    
    json:
      type: recursive_json
      params:
        chunk_size: 100
        chunk_overlap: 10
    
    html:
      type: html
      params:
        chunk_size: 4096
        chunk_overlap: 800
        tags_to_extract: ["p", "h1", "h2", "h3", "li"]
```

### Using Cloud Storage

You can configure the RAG system to monitor cloud storage instead of local directories:

```yaml
scanner:
  batch: true
  use_memory_storage: true
  source:
    type: cloud
    cloud_provider: "aws"
    bucket: "my-document-bucket"
    prefix: "documents/"
    credentials:
      access_key: ${AWS_ACCESS_KEY}
      secret_key: ${AWS_SECRET_KEY}
    filters:
      file_formats:
        - ".txt"
        - ".pdf"
      max_file_size: 10240
  schedule:
    interval: 300
```

### Using a Database for File Tracking

You can configure the RAG system to use a database for file tracking instead of in-memory storage:

```yaml
scanner:
  batch: true
  use_memory_storage: false
  source:
    type: filesystem
    directories:
      - "/path/to/your/documents"
  database:
    type: postgresql
    dbname: rag_metadata
    host: localhost
    port: 5432
    user: admin
    password: admin
  schedule:
    interval: 60
```

## Troubleshooting

### Common Issues

#### Documents Not Being Ingested

1. Check that the directories are correctly configured
2. Verify that the file formats are supported
3. Check that the file sizes are within the configured limit
4. Check the logs for errors

#### Vector Database Connection Issues

1. Verify that the vector database is running
2. Check that the connection parameters are correct
3. Ensure that the collection exists
4. Check the logs for connection errors

#### Embedding Service Issues

1. Verify that the API key is correct
2. Check that the model name is valid
3. Ensure that the API endpoint is accessible
4. Check the logs for API errors

#### LLM Service Issues

1. Verify that the API key is correct
2. Check that the model name is valid
3. Ensure that the API endpoint is accessible
4. Check the logs for API errors

### Checking Logs

```sh
tail -f solace_ai_connector.log
```

## Next Steps

- [Architecture Overview](architecture.md)
- [Configuration Guide](configuration.md)
- [Component Documentation](components/)
