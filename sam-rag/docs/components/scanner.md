# Scanner Component

The Scanner component is responsible for monitoring document sources, detecting changes, and triggering the document ingestion process.

## Overview

The Scanner component monitors specified directories or cloud storage locations for new, modified, or deleted documents. When changes are detected, it updates the file tracking database and triggers the document ingestion pipeline.

## Key Classes

### FileChangeTracker

The `FileChangeTracker` class is the main entry point for the scanner component. It:

- Initializes the appropriate data source (filesystem or cloud storage)
- Manages file tracking information
- Coordinates the scanning process
- Provides methods for retrieving tracked files

```python
class FileChangeTracker:
    def __init__(self, config: Dict, pipeline):
        # Initialize with configuration and pipeline reference
        
    def scan(self) -> None:
        # Scan for file changes
        
    def upload_files(self, documents) -> str:
        # Upload files to the data source
        
    def get_tracked_files(self) -> List[Dict[str, Any]]:
        # Get all tracked files
```

### LocalFileSystemDataSource

The `LocalFileSystemDataSource` class monitors local file system directories for changes. It:

- Scans directories for new, modified, or deleted files
- Validates files against configured filters
- Updates the file tracking database
- Triggers the document ingestion pipeline

```python
class LocalFileSystemDataSource(DataSource):
    def __init__(self, source: Dict, ingested_documents: List[str], pipeline) -> None:
        # Initialize with source configuration, ingested documents, and pipeline reference
        
    def batch_scan(self) -> None:
        # Scan all existing files in configured directories
        
    def scan(self) -> None:
        # Monitor directories for file system changes
        
    def on_created(self, event):
        # Handle file creation events
        
    def on_deleted(self, event):
        # Handle file deletion events
        
    def on_modified(self, event):
        # Handle file modification events
```

### CloudStorageDataSource

The `CloudStorageDataSource` class monitors cloud storage locations for changes. It:

- Scans cloud storage for new, modified, or deleted files
- Validates files against configured filters
- Updates the file tracking database
- Triggers the document ingestion pipeline

## Configuration

The Scanner component is configured through the `scanner` section of the `configs/agents/rag.yaml` file:

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
    dbname: rag_metadata
    host: localhost
    port: 5432
    user: admin
    password: admin
  schedule:
    interval: 60             # Scanning interval in seconds
```

### Key Configuration Parameters

- `batch`: When `true`, processes all existing documents in the specified directories during startup
- `use_memory_storage`: When `true`, stores file tracking information in memory; when `false`, uses the configured database
- `source.type`: The type of document source (`filesystem` or `cloud`)
- `source.directories`: List of directories to monitor for documents
- `source.filters.file_formats`: List of supported file extensions
- `source.filters.max_file_size`: Maximum file size in KB
- `database`: Configuration for the metadata database (used when `use_memory_storage` is `false`)
- `schedule.interval`: How often to scan for changes (in seconds)

## File Tracking

The Scanner component tracks files using either in-memory storage or a database:

### In-Memory Storage

When `use_memory_storage` is `true`, file tracking information is stored in memory using the `memory_storage` module. This is suitable for development and testing, but not for production use as the tracking information is lost when the application restarts.

### Database Storage

When `use_memory_storage` is `false`, file tracking information is stored in a database. The database is configured through the `database` section of the scanner configuration. This is suitable for production use as the tracking information persists across application restarts.

## File Validation

The Scanner component validates files against the configured filters:

- File extension must be in the `file_formats` list
- File size must be less than or equal to `max_file_size`

## Scanning Process

The scanning process works as follows:

1. If `batch` is `true`, scan all existing files in the configured directories
2. Set up file system watchers to monitor for changes
3. When a change is detected:
   - For new files: Add to the tracking database and trigger ingestion
   - For modified files: Update the tracking database and trigger ingestion
   - For deleted files: Remove from the tracking database

## Integration with Pipeline

The Scanner component integrates with the Pipeline component through the `pipeline` parameter passed to the `FileChangeTracker` constructor. When changes are detected, the Scanner component calls the `process_files` method of the Pipeline component to trigger the document ingestion process.

## Next Steps

- [Preprocessor Component](preprocessor.md)
- [Splitter Component](splitter.md)
- [Embedder Component](embedder.md)
- [Vector Database Component](vector_db.md)
- [Retriever Component](retriever.md)
- [Augmentation Component](augmentation.md)
