# SAM Nuclia Tool Plugin

A plugin for connecting to RAG and retrieving relevant documents from [Nuclia](https://nuclia.com).

This is a plugin for Solace Agent Mesh (SAM).

## Features

- **Generative Answers with Citations**: Generates natural language answers with verifiable, clickable citations to source documents
- **Template-Based Configuration**: Flexible prompt rephrasing and filtering using template parameters
- **Dynamic Filtering**: Apply runtime filters to narrow search scope based on user context
- **Secure Document Access**: Brokered URLs with ephemeral tokens for secure document viewing
- **REMi Event Publishing**: Publish evaluation events to Solace event mesh for RAG quality monitoring
- **Audit Metadata**: Track search requests with contextual information for logging and analytics
- **Page-Specific Citations**: Direct links to exact pages in source documents

## Installation

To install the Nuclia Agent plugin, run the following command:

```bash
sam plugin install sam-nuclia-tool
```

This will create a new component configuration at `configs/plugins/<your-new-component-name-kebab-case>.yaml`.

## Documentation

For detailed configuration and usage instructions, see the [Nuclia RAG Tool User Guide](docs/nuclia_rag_tool_user_guide.md).