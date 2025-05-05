# Preprocessor Component

The Preprocessor component is responsible for extracting and cleaning text from various document formats.

## Overview

The Preprocessor component handles the extraction of text from different file formats (PDF, DOCX, HTML, etc.) and applies various cleaning operations to normalize the text for further processing. It provides a unified interface for preprocessing different document types with customizable preprocessing parameters.

## Key Classes

### PreprocessorService

The `PreprocessorService` class is the main entry point for the preprocessor component. It:

- Manages a collection of specialized preprocessors for different file formats
- Selects the appropriate preprocessor based on file extension
- Provides methods for preprocessing individual files or batches of files

```python
class PreprocessorService:
    def __init__(self, config: Dict[str, Any] = None):
        # Initialize with configuration
        
    def preprocess_file(self, file_path: str) -> Optional[str]:
        # Preprocess a single file
        
    def preprocess_files(self, file_paths: List[str]) -> List[Tuple[str, Optional[str]]]:
        # Preprocess multiple files
        
    def preprocess_file_list(self, file_paths: List[str]) -> Dict[str, str]:
        # Preprocess a list of files and return a dictionary
```

### PreprocessorBase

The `PreprocessorBase` class is the base class for all preprocessors. It:

- Defines the interface for preprocessors
- Provides common preprocessing functionality
- Handles configuration of preprocessing parameters

```python
class PreprocessorBase:
    def __init__(self, config: Dict[str, Any] = None):
        # Initialize with configuration
        
    def preprocess(self, file_path: str) -> str:
        # Preprocess a file and return the cleaned text
        
    def can_process(self, file_path: str) -> bool:
        # Check if this preprocessor can process the given file
```

### Specialized Preprocessors

The preprocessor component includes several specialized preprocessors for different file formats:

- `TextFilePreprocessor`: Handles plain text files
- `PDFPreprocessor`: Extracts and cleans text from PDF files
- `DocxPreprocessor`: Extracts and cleans text from DOCX files
- `HTMLPreprocessor`: Extracts and cleans text from HTML files
- `ExcelPreprocessor`: Extracts and cleans text from Excel files
- `ODTPreprocessor`: Extracts and cleans text from ODT files
- `CSVFilePreprocessor`: Extracts and cleans text from CSV files

Each specialized preprocessor implements the `PreprocessorBase` interface and provides format-specific text extraction and cleaning.

## Configuration

The Preprocessor component is configured through the `preprocessor` section of the `configs/agents/rag.yaml` file:

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
        lowercase: true
        normalize_whitespace: true
        remove_stopwords: false
        remove_punctuation: true
    
    # Document file configurations
    pdf:
      type: document
      params:
        lowercase: true
        normalize_whitespace: true
        remove_non_ascii: true
    
    # Additional file type configurations
    # ...
```

### Key Configuration Parameters

- `default_preprocessor`: Default settings applied to all document types
- `preprocessors`: Type-specific settings that override the defaults for specific file types

### Preprocessor Types

- `enhanced`: General-purpose text preprocessor with advanced options
- `text`: Specialized for plain text files
- `document`: Specialized for document files (PDF, DOCX, etc.)
- `structured`: Specialized for structured data files (JSON, etc.)
- `html`: Specialized for HTML files
- `markdown`: Specialized for Markdown files

### Preprocessing Parameters

- `lowercase`: Convert text to lowercase
- `normalize_whitespace`: Replace multiple whitespace characters with a single space
- `remove_stopwords`: Remove common words like "the", "and", etc.
- `remove_punctuation`: Remove punctuation marks
- `remove_numbers`: Remove numeric characters
- `remove_non_ascii`: Remove non-ASCII characters
- `remove_urls`: Remove URLs
- `remove_emails`: Remove email addresses
- `remove_html_tags`: Remove HTML tags

## Preprocessing Process

The preprocessing process works as follows:

1. The `PreprocessorService` receives a file path to preprocess
2. It determines the appropriate preprocessor based on the file extension
3. The selected preprocessor:
   - Extracts text from the file using format-specific methods
   - Applies the configured cleaning operations
   - Returns the cleaned text
4. The `PreprocessorService` returns the cleaned text to the caller

## Text Extraction

Each specialized preprocessor uses different libraries and techniques to extract text from its supported file formats:

- `TextFilePreprocessor`: Uses standard file I/O to read text files
- `PDFPreprocessor`: Uses libraries like PyPDF2 or pdfminer to extract text from PDF files
- `DocxPreprocessor`: Uses python-docx to extract text from DOCX files
- `HTMLPreprocessor`: Uses BeautifulSoup to extract text from HTML files
- `ExcelPreprocessor`: Uses pandas or openpyxl to extract text from Excel files
- `ODTPreprocessor`: Uses odfpy to extract text from ODT files
- `CSVFilePreprocessor`: Uses pandas to extract text from CSV files

## Text Cleaning

After text extraction, each preprocessor applies the configured cleaning operations to normalize the text:

1. Convert to lowercase (if `lowercase` is `true`)
2. Normalize whitespace (if `normalize_whitespace` is `true`)
3. Remove stopwords (if `remove_stopwords` is `true`)
4. Remove punctuation (if `remove_punctuation` is `true`)
5. Remove numbers (if `remove_numbers` is `true`)
6. Remove non-ASCII characters (if `remove_non_ascii` is `true`)
7. Remove URLs (if `remove_urls` is `true`)
8. Remove email addresses (if `remove_emails` is `true`)
9. Remove HTML tags (if `remove_html_tags` is `true`)

## Integration with Pipeline

The Preprocessor component integrates with the Pipeline component through the `preprocessing_handler` field of the `Pipeline` class. When the pipeline processes a file, it calls the `preprocess_file` method of the `PreprocessorService` to extract and clean the text before passing it to the Splitter component.

## Next Steps

- [Splitter Component](splitter.md)
- [Embedder Component](embedder.md)
- [Vector Database Component](vector_db.md)
- [Retriever Component](retriever.md)
- [Augmentation Component](augmentation.md)
- [Scanner Component](scanner.md)
