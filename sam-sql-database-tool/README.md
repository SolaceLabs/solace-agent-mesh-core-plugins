# SQL Database Tool Plugin

This plugin for Solace Agent Mesh (SAM) provides a powerful and dynamic tool for executing SQL queries against a database. It allows any agent to be augmented with direct database access.

Unlike the `sam-sql-database` agent, which provides a complete Natural-Language-to-SQL agent, this plugin provides a **tool** that can be added to any existing or new agent. This allows you to create multi-faceted agents that can interact directly with databases for specific, targeted tasks.

## Key Features

- **Dynamic Tool Creation**: Define custom SQL query tools directly in your agent's YAML configuration. Each tool instance is completely independent.
- **Multi-Database Support**: Works with MySQL, PostgreSQL, and SQLite.
- **Dedicated Connections**: Each tool instance creates its own dedicated database connection, allowing for fine-grained configuration.
- **Flexible Schema Handling**:
    -   Automatic schema detection and summarization for LLM prompting.
    -   Manual override for providing a detailed schema and a natural language summary.

## Installation

To add this tool to a new or existing agent, you must first install it and then manually add the tool configuration to your agent's YAML file:

```bash
sam plugin add <your-component-name> --plugin sam-sql-database-tool
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
      db_type: "postgresql"
      db_host: "${DB_HOST}"
      db_port: ${DB_PORT}
      db_user: "${DB_USER}"
      db_password: "${DB_PASSWORD}"
      db_name: "customer_db"

      # --- Schema Handling ---
      auto_detect_schema: true
      # database_schema_override: |
      #   CREATE TABLE customers (id INT, name VARCHAR(255));
      # schema_summary_override: "A table named 'customers' with columns 'id' and 'name'."
```

### `tool_config` Details

-   `tool_name`: (Required) The function name the LLM will use to call the tool.
-   `tool_description`: (Optional) A clear description for the LLM explaining what the tool does.
-   `db_type`: (Required) The type of the database. Must be one of `"postgresql"`, `"mysql"`, or `"sqlite"`.
-   `db_host`, `db_port`, `db_user`, `db_password`: (Required for PostgreSQL/MySQL) Connection details for your database. It's highly recommended to use environment variables (e.g., `${DB_HOST}`) for sensitive information.
-   `db_name`: (Required) The name of the database (for PostgreSQL/MySQL) or the file path to the database file (for SQLite).
-   `auto_detect_schema`: (Optional, default: `true`) If `true`, the plugin attempts to automatically detect the database schema. If `false`, you must provide `database_schema_override` and `schema_summary_override`.
-   `database_schema_override`: (Required if `auto_detect_schema` is `false`) A YAML or plain text string describing the detailed database schema (e.g., DDL statements).
-   `schema_summary_override`: (Required if `auto_detect_schema` is `false`) A concise natural language summary of the schema, suitable for direct inclusion in an LLM prompt.

### Tool Parameters

The generated tool accepts a single parameter:

-   `query` (string, required): The SQL query to execute.
