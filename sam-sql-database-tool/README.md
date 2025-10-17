# SQL Database Tool Plugin

This plugin for Solace Agent Mesh (SAM) provides a powerful and dynamic tool for executing SQL queries against a database. It allows any agent to be augmented with direct database access.

Unlike the `sam-sql-database` agent, which provides a complete Natural-Language-to-SQL agent, this plugin provides a **tool** that can be added to any existing or new agent. This allows you to create multi-faceted agents that can interact directly with databases for specific, targeted tasks.

## Key Features

- **Dynamic Tool Creation**: Define custom SQL query tools directly in your agent's YAML configuration. Each tool instance is completely independent.
- **Multi-Database Support**: Natively supports PostgreSQL, MySQL, and MariaDB.
- **Dedicated Connections**: Each tool instance creates its own dedicated database connection, allowing for fine-grained configuration.
- **Flexible Schema Handling**:
    -   Automatic schema detection and summarization for LLM prompting.
    -   Manual override for providing a detailed schema and a natural language summary.

## Installation

To add this tool to a new or existing agent, you must first install it and then manually add the tool configuration to your agent's YAML file:

```bash
sam plugin install sam-sql-database-tool
```

This creates a new component configuration at `configs/plugins/<your-component-name-kebab-case>.yaml`.

## Configuration

To use the tool, add one or more `tool_type: python` blocks to the `tools` list in your agent's `app_config`. Each block will create a new, independent tool instance.

### Example Tool Configuration

Here is an example of configuring a tool to query a customer database.

```yaml
# In your agent's app_config:
tools:
  - tool_type: python
    component_module: "sam_sql_database_tool.tools"
    class_name: "SqlDatabaseTool"
    tool_config:
      # --- Tool Definition for LLM ---
      tool_name: "QueryCustomerDatabase"
      tool_description: "Executes a SQL query against the customer database."

      # --- Database Connection Configuration ---
      connection_string: "${CUSTOMER_DB_CONNECTION_STRING}"

      # --- Schema Handling ---
      auto_detect_schema: true
      # schema_summary_override: "A table named 'customers' with columns 'id' and 'name'."
```

### `tool_config` Details

-   `tool_name`: (Required) The function name the LLM will use to call the tool.
-   `tool_description`: (Optional) A clear description for the LLM explaining what the tool does.
-   `connection_string`: (Required) The full database connection string (e.g., `postgresql+psycopg2://user:password@host:port/dbname` for PostgreSQL, or `mysql+pymysql://user:password@host:port/dbname` for MySQL/MariaDB). It is highly recommended to use a single environment variable for the entire string.
-   `auto_detect_schema`: (Optional, default: `true`) If `true`, the plugin attempts to automatically detect the database schema. If `false`, you must provide `schema_summary_override`.
-   `schema_summary_override`: (Required if `auto_detect_schema` is `false`) A concise natural language summary of the schema, suitable for direct inclusion in an LLM prompt.
-   `max_enum_cardinality`: (Optional, default: `100`) Maximum number of distinct values to consider a column as an enum. Increase for columns like countries (190+), decrease for faster init times.
-   `schema_sample_size`: (Optional, default: `100`) Number of rows to sample per table for schema detection. Increase for better accuracy on sparse data, decrease for faster init times.
-   `cache_ttl_seconds`: (Optional, default: `3600`) Time-to-live for schema cache in seconds. After this duration, the schema will be re-detected on the next query. Set to `0` to disable caching.

### Tool Parameters

The generated tool accepts a single parameter:

-   `query` (string, required): The SQL query to execute.
