# SQL Database Tool Plugin

This plugin for Solace Agent Mesh (SAM) provides a powerful and dynamic tool for executing SQL queries against a database. It allows any agent to be augmented with direct database access.

Unlike the `sam-sql-database` agent, which provides a complete Natural-Language-to-SQL agent, this plugin provides a **tool** that can be added to any existing or new agent. This allows you to create multi-faceted agents that can interact directly with databases for specific, targeted tasks.

## Key Features

- **Dynamic Tool Creation**: Define custom SQL query tools directly in your agent's YAML configuration. Each tool instance is completely independent.
- **Multi-Database Support**: Natively supports PostgreSQL, MySQL, MariaDB, MSSQL, and Oracle.
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
      # max_enum_cardinality: 100
      # schema_sample_size: 100
      # cache_ttl_seconds: 3600

      # --- Connection Pool (optional tuning) ---
      # pool_size: 10
      # max_overflow: 10
      # pool_timeout: 30
      # pool_recycle: 1800      # Set below your DB's idle timeout
      # pool_pre_ping: true

      # --- Engine Settings (optional) ---
      # echo: false             # Log all SQL statements (development only)
      # isolation_level: "READ_COMMITTED"
      # connect_args: {}        # Extra driver kwargs, e.g. {sslmode: "require"}
```

### `tool_config` Details

-   `tool_name`: (Required) The function name the LLM will use to call the tool.
-   `tool_description`: (Optional) A clear description for the LLM explaining what the tool does.
-   `connection_string`: (Required) The full database connection string. It is highly recommended to use a single environment variable for the entire string. Supported formats:
    -   **PostgreSQL**: `postgresql+psycopg2://user:password@host:port/dbname`
    -   **MySQL**: `mysql+pymysql://user:password@host:port/dbname`
    -   **MariaDB**: `mysql+pymysql://user:password@host:port/dbname`
    -   **MSSQL (Microsoft ODBC - Recommended)**: `mssql+pyodbc://user:password@host:port/dbname?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes`
        -   Official Microsoft driver with full feature support (Azure AD auth, Always Encrypted, etc.).
        -   Requires ODBC Driver 17 or 18 installed on the host system.
        -   Driver 18+ enables encryption by default. Control this with the `Encrypt` parameter:
            -   `Encrypt=yes` / `Encrypt=mandatory` — encrypt all traffic (default in Driver 18+).
            -   `Encrypt=no` / `Encrypt=optional` — disable encryption.
            -   `Encrypt=strict` — strict TLS; ignores `TrustServerCertificate` and requires a fully valid certificate chain (Driver 18+ only).
        -   Use `TrustServerCertificate=yes` to bypass certificate validation for self-signed certificates (not applicable when `Encrypt=strict`).
        -   See the [Microsoft docs on ODBC connection string keywords](https://learn.microsoft.com/en-us/sql/relational-databases/native-client/applications/using-connection-string-keywords-with-sql-server-native-client) for the full list of supported parameters.
    -   **MSSQL (FreeTDS)**: `mssql+pyodbc://user:password@host:port/dbname?driver=FreeTDS`
        -   Open-source driver with simpler installation: `sudo apt-get install freetds-dev freetds-bin tdsodbc && sudo odbcinst -i -d -f /usr/share/tdsodbc/odbcinst.ini`
        -   Works well for standard SQL operations.
    -   **Oracle**: `oracle+oracledb://user:password@host:port/?service_name=SERVICE_NAME`
        -   Uses the `oracledb` driver in thin mode (no Oracle Instant Client required).
        -   Replace `SERVICE_NAME` with your Oracle service name (e.g., `XEPDB1`, `ORCL`).
-   `auto_detect_schema`: (Optional, default: `true`) If `true`, the plugin attempts to automatically detect the database schema. If `false`, you must provide `schema_summary_override`.
-   `schema_summary_override`: (Required if `auto_detect_schema` is `false`) A concise natural language summary of the schema, suitable for direct inclusion in an LLM prompt.
-   `max_enum_cardinality`: (Optional, default: `100`) Maximum number of distinct values to consider a column as an enum. Increase for columns like countries (190+), decrease for faster init times.
-   `schema_sample_size`: (Optional, default: `100`) Number of rows to sample per table for schema detection. Increase for better accuracy on sparse data, decrease for faster init times.
-   `cache_ttl_seconds`: (Optional, default: `3600`) Time-to-live for schema cache in seconds. After this duration, the schema will be re-detected on the next query. Set to `0` to disable caching.

#### Connection Pool Settings

-   `pool_size`: (Optional, default: `10`) Number of persistent connections to maintain in the pool. Increase for high-concurrency workloads; decrease to reduce resource usage on low-traffic deployments.
-   `max_overflow`: (Optional, default: `10`) Maximum number of additional temporary connections allowed beyond `pool_size` during traffic spikes. The total connection limit is `pool_size + max_overflow`.
-   `pool_timeout`: (Optional, default: `30`) Seconds to wait for a free connection from the pool before raising a `TimeoutError`. Increase if you frequently hit timeouts under load.
-   `pool_recycle`: (Optional, default: `1800`) Recycle connections after this many seconds to prevent "lost connection" errors. Set this value below your database server's idle connection timeout. Use `-1` to disable recycling.
-   `pool_pre_ping`: (Optional, default: `true`) Test each connection for liveness before use. Keeps the pool healthy after network interruptions. Disable only to reduce per-query latency on very reliable networks.

#### Engine Settings

-   `echo`: (Optional, default: `false`) Log all SQL statements to the Python logger (`sqlalchemy.engine`). Enable for development and troubleshooting only — do not use in production.
-   `isolation_level`: (Optional) Set the transaction isolation level for all connections. Accepted values depend on the database dialect — common values are `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`, and `AUTOCOMMIT`. Omit to use the database's default.
-   `connect_args`: (Optional, default: `{}`) A dictionary of extra keyword arguments passed directly to the database driver's `connect()` call. Use this for driver-specific options such as SSL certificates, connection timeouts, or character set settings. Example for PostgreSQL: `connect_args: {sslmode: "require"}`.

### Tool Parameters

The generated tool accepts a single parameter:

-   `query` (string, required): The SQL query to execute.
