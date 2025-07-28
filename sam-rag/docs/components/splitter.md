# Splitter Component

The Splitter component is responsible for breaking documents into smaller chunks for embedding and retrieval.

## Overview

The Splitter component takes preprocessed text and splits it into smaller chunks that are suitable for embedding and retrieval. It provides different splitting strategies for different types of content, such as plain text, JSON, HTML, Markdown, and CSV.

## Key Classes

### SplitterService

The `SplitterService` class is the main entry point for the splitter component. It:

- Manages a collection of specialized splitters for different content types
- Selects the appropriate splitter based on content type
- Provides methods for splitting text into chunks

```python
class SplitterService:
    def __init__(self, config: Dict[str, Any] = None):
        # Initialize with configuration
        
    def get_splitter(self, data_type: str) -> SplitterBase:
        # Get the appropriate splitter for the given data type
        
    def split_text(self, text: str, data_type: str) -> List[Any]:
        # Split the text into chunks using the appropriate splitter
```

### SplitterBase

The `SplitterBase` class is the base class for all splitters. It:

- Defines the interface for splitters
- Provides common splitting functionality
- Handles configuration of splitting parameters

```python
class SplitterBase:
    def __init__(self, config: Dict[str, Any] = None):
        # Initialize with configuration
        
    def split_text(self, text: str) -> List[str]:
        # Split the text into chunks and return the chunks
        
    def can_handle(self, data_type: str) -> bool:
        # Check if this splitter can handle the given data type
```

### Text Splitters

The splitter component includes several specialized text splitters:

- `CharacterTextSplitter`: Splits text by character count
- `RecursiveCharacterTextSplitter`: Recursively splits text by different separators
- `TokenTextSplitter`: Splits text by token count

### Structured Data Splitters

The splitter component also includes specialized splitters for structured data:

- `JSONSplitter`: Splits JSON documents
- `RecursiveJSONSplitter`: Recursively splits JSON documents
- `HTMLSplitter`: Splits HTML documents
- `MarkdownSplitter`: Splits Markdown documents
- `CSVSplitter`: Splits CSV files

## Configuration

The Splitter component is configured through the `splitter` section of the `configs/agents/rag.yaml` file:

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
    
    txt:
      type: character
      params:
        chunk_size: 200
        chunk_overlap: 40
        separator: "\n"
    
    # Structured data configurations
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
    
    markdown:
      type: markdown
      params:
        chunk_size: 4096
        chunk_overlap: 800
        headers_to_split_on: ["#", "##", "###", "####", "#####", "######"]
        strip_headers: false
    
    csv:
      type: csv
      params:
        chunk_size: 4096
        include_header: false
```

### Key Configuration Parameters

- `default_splitter`: Default settings applied to all document types
- `splitters`: Type-specific settings that override the defaults for specific file types

### Splitter Types

- `character`: Splits text by character count
- `recursive_character`: Recursively splits text by different separators
- `token`: Splits text by token count
- `recursive_json`: Recursively splits JSON documents
- `html`: Specialized for HTML documents
- `markdown`: Specialized for Markdown documents
- `csv`: Specialized for CSV files

### Splitting Parameters

- `chunk_size`: Maximum size of each chunk (in characters or tokens)
- `chunk_overlap`: Number of characters or tokens to overlap between chunks
- `separator`: Character or string to use as separator
- `is_separator_regex`: Whether the separator is a regular expression
- `keep_separator`: Whether to keep the separator in the output
- `strip_whitespace`: Whether to strip whitespace from the beginning and end of chunks

## Splitting Process

The splitting process works as follows:

1. The `SplitterService` receives text to split and a content type
2. It determines the appropriate splitter based on the content type
3. The selected splitter:
   - Splits the text into chunks based on its splitting strategy
   - Applies the configured parameters (chunk size, overlap, etc.)
   - Returns the chunks
4. The `SplitterService` returns the chunks to the caller

## Splitting Strategies

### Character Text Splitting

The `CharacterTextSplitter` splits text by character count:

1. Split the text by the specified separator
2. Combine the splits into chunks of the specified size
3. Ensure that chunks overlap by the specified amount

### Recursive Character Text Splitting

The `RecursiveCharacterTextSplitter` recursively splits text by different separators:

1. Try to split the text by the first separator
2. If the resulting chunks are too large, try the next separator
3. Continue until the chunks are small enough or there are no more separators
4. Ensure that chunks overlap by the specified amount

### Token Text Splitting

The `TokenTextSplitter` splits text by token count:

1. Tokenize the text using a tokenizer
2. Combine the tokens into chunks of the specified size
3. Ensure that chunks overlap by the specified amount

### Structured Data Splitting

Specialized splitters for structured data use different strategies:

- `JSONSplitter`: Splits JSON documents by keys
- `RecursiveJSONSplitter`: Recursively splits JSON documents by keys and values
- `HTMLSplitter`: Splits HTML documents by tags
- `MarkdownSplitter`: Splits Markdown documents by headers
- `CSVSplitter`: Splits CSV files by rows

## Integration with Pipeline

The Splitter component integrates with the Pipeline component through the `splitting_handler` field of the `Pipeline` class. When the pipeline processes a file, it calls the `split_text` method of the `SplitterService` to split the preprocessed text into chunks before passing them to the Embedder component.

## Next Steps

- [Embedder Component](embedder.md)
- [Vector Database Component](vector_db.md)
- [Retriever Component](retriever.md)
- [Augmentation Component](augmentation.md)
- [Scanner Component](scanner.md)
- [Preprocessor Component](preprocessor.md)
