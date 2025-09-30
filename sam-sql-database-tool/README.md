# Solace Agent Mesh - Reusable SQL Database Tool

This plugin provides a reusable `DynamicTool` for connecting to SQL databases within the Solace Agent Mesh. It follows the recommended pattern of defining each database connection as a separate, explicit tool in the agent's configuration YAML.

## Features

- **Lifecycle Management**: The tool manages its own database connection lifecycle using the `init` and `cleanup` methods.
- **Configuration Validation**: Uses a Pydantic model to validate the tool's configuration.
- **Reusable**: A single `DynamicTool` Python class is reused for all database connections.
- **Multi-Database Support:** Works with MySQL, PostgreSQL, and SQLite.

## Installation

```bash
sam plugin add <your-component-name> --plugin sam-sql-database-tool
```

This creates a new component configuration at `configs/plugins/<your-component-name-kebab-case>.yaml`.

## Configuration

The SQL Database Tool is configured within the `tools` list of your agent's YAML configuration file.

**Key Configuration Sections:**

### Tool Configuration (`tools`)

To use the `SqlQueryTool`, you will add a separate `tool_type: python` block to your agent's `tools` list for each database you want to connect to. Each block requires a `tool_config` section that defines the connection parameters.

```yaml
# Within app_config:
tools:
  - tool_type: python
    component_module: "sam_sql_database_tool.tools"
    class_name: "SqlDatabaseTool"
    tool_config:
      # --- Connection Parameters ---
      name: "my_db" # A unique name for this tool instance
      db_type: "postgresql"
      db_host: "${DB_HOST}"
      db_port: ${DB_PORT}
      db_user: "${DB_USER}"
      db_password: "${DB_PASSWORD}"
      db_name: "${DB_NAME}"
```

*   **`name`**: (Required) A unique name for this tool instance. This will be used to generate the tool name (e.g., `query_my_db`).
*   **`db_type`**: (Required) Specify `"postgresql"`, `"mysql"`, or `"sqlite"`.
*   **`db_host`**, **`db_port`**, **`db_user`**, **`db_password`**: (Required for PostgreSQL/MySQL) Connection details for your database. It's highly recommended to use environment variables (e.g., `${DB_HOST}`) for sensitive information.
*   **`db_name`**: (Required) The name of the database (for PostgreSQL/MySQL) or the file path to the database file (for SQLite).

## Usage

Once the agent is configured with the SQL Database Tool:

1.  The agent starts, and the `init` method of the `SqlDatabaseTool` class connects to the database.
2.  A user sends a natural language query to the agent.
3.  The ADK agent, using its instruction, converts the natural language query into an SQL query string.
4.  The ADK agent invokes the dynamically named tool (e.g., `query_my_db`) with the generated SQL.
5.  The tool's `_run_async_impl` method executes the SQL query against the database and returns the results.
6.  When the agent shuts down, the `cleanup` method of the `SqlDatabaseTool` class closes the database connection.
