# Solace Agent Mesh SQL Database

A plugin that provides SQL database query capabilities with natural language processing. Supports MySQL, PostgreSQL, and SQLite databases.

NOTE: While the search action implies that it will not modify the database, it is very important that the credentials to the database for this action are read-only. This is because the natural language processing may not always generate the correct SQL query and could potentially modify the database.

## Features

- Natural language to SQL query conversion
- Support for multiple database types (MySQL, PostgreSQL, SQLite)
- Automatic schema detection with detailed metadata
- Multiple response formats (YAML, JSON, CSV, Markdown)
- Configurable query timeout
- Connection pooling and automatic reconnection
- CSV file import for database initialization

## Add a SQL Database Agent to SAM

Add the plugin to your SAM instance:

```sh
solace-agent-mesh plugin add sam_sql_database --pip -u git+https://github.com/SolaceLabs/solace-agent-mesh-core-plugins#subdirectory=sam-sql-database
```

To instantiate the agent, you can use:

```sh
solace-agent-mesh add agent <new_agent_name> --copy-from sam_sql_database:sql_database
```

For example:

```sh
solace-agent-mesh add agent my_database --copy-from sam_sql_database:sql_database
```

This will create a new config file in the `configs/agents` directory with agent name you provided. You can view that configuration file to see the environment variables that need to be set (listed below).

## Environment Variables

The following environment variables are required for Solace connection:
- **SOLACE_BROKER_URL**
- **SOLACE_BROKER_USERNAME**
- **SOLACE_BROKER_PASSWORD**
- **SOLACE_BROKER_VPN**
- **SOLACE_AGENT_MESH_NAMESPACE**

For database connection:
- **<AGENT_NAME>_DB_TYPE** - One of: mysql, postgres, sqlite
- **<AGENT_NAME>_DB_HOST** - Database host (for MySQL/PostgreSQL)
- **<AGENT_NAME>_DB_PORT** - Database port (for MySQL/PostgreSQL)
- **<AGENT_NAME>_DB_USER** - Database user (for MySQL/PostgreSQL)
- **<AGENT_NAME>_DB_PASSWORD** - Database password (for MySQL/PostgreSQL)
- **<AGENT_NAME>_DB_NAME** - Database name or file path (for SQLite)
- **<AGENT_NAME>_QUERY_TIMEOUT** - Query timeout in seconds (optional, default 30)
- **<AGENT_NAME>_DB_PURPOSE** - Description of the database purpose
- **<AGENT_NAME>_DB_DESCRIPTION** - Detailed description of the data
- **<AGENT_NAME>_AUTO_DETECT_SCHEMA** - Whether to automatically detect schema (optional, default true)
- **<AGENT_NAME>_DB_SCHEMA** - Database schema text (required if auto_detect_schema is false)
- **<AGENT_NAME>_SCHEMA_SUMMARY** - Natural language summary of the schema (required if auto_detect_schema is false)
- **<AGENT_NAME>_QUERY_EXAMPLES** - List of example natural language to SQL query mappings (optional)
- **<AGENT_NAME>_RESPONSE_GUIDELINES** - Guidelines to be attached to action responses (optional)

## Actions

### search_query
Execute natural language queries against the SQL database. The query is converted to SQL and results are returned in the specified format.

Parameters:
- **query** (required): Natural language description of the search query
- **response_format** (optional): Format of response (yaml, markdown, json, csv)
- **inline_result** (optional): Whether to return result inline or as file

If `response_guidelines` is configured, these guidelines will be included in the action response message.

## Multiple Database Support

You can add multiple SQL database agents to your SAM instance by:

1. Creating multiple copies of the config file
2. Giving each a unique name
3. Configuring different database connections
4. Using different agent names

This allows you to interact with multiple databases through natural language queries.

## Schema Detection

The agent can handle database schemas in two ways:

1. **Automatic Schema Detection** (default):
   - Automatically detects and analyzes the database schema
   - Generates a natural language summary of the schema
   - Includes table structures, column types, and relationships

2. **Manual Schema Configuration**:
   - Set `AUTO_DETECT_SCHEMA=false` to disable automatic detection
   - Provide `DB_SCHEMA` with the database structure description
   - Provide `SCHEMA_SUMMARY` with a natural language summary
   - Useful when you want to control exactly how the schema is presented to the agent

The schema information helps the LLM generate more accurate SQL queries from natural language.

## Query Examples

The SQL Database agent supports providing example queries to improve natural language to SQL conversion accuracy. This is particularly useful for:
- Teaching the agent about domain-specific terminology
- Demonstrating preferred query patterns
- Improving accuracy for complex queries
- Handling edge cases specific to your database

### How to Configure Query Examples

You can add query examples in your agent's YAML configuration file:

```yaml
  # Other configuration...
  - component_name: action_request_processor
    # Other configuration...
    component_config:
      # Other configuration...
      query_examples:
        - natural_language: "Show me all employees in the Engineering department"
          sql_query: "SELECT * FROM employees WHERE department = 'Engineering'"
        - natural_language: "What are the top 5 highest paid employees?"
          sql_query: "SELECT name, salary FROM employees ORDER BY salary DESC LIMIT 5"
        - natural_language: "How many orders were placed last month?"
          sql_query: "SELECT COUNT(*) FROM orders WHERE order_date >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)"
```
### Example Format and Usage


Each query example must include:
1. `natural_language`: The natural language question or request
2. `sql_query`: The corresponding SQL query that correctly answers the question

The agent will use these examples to better understand how to translate natural language queries into SQL for your specific database schema and domain.

## CSV File Import

The SQL Database agent supports importing CSV files to initialize or populate your database tables. This is particularly useful for:
- Setting up test databases
- Importing data from external sources
- Quickly populating tables with sample data

### How to Import CSV Files

You can directly edit your agent's YAML configuration file:

```yaml
  # Other configuration...
  - component_name: action_request_processor
    # Other configuration...
    component_config:
      # Other configuration...
      csv_files:
        - /path/to/file1.csv
        - /path/to/file2.csv
      csv_directories:
        - /path/to/csv/directory
```

### CSV File Format Requirements

For successful import:

1. The CSV file name (without extension) will be used as the table name
2. The first row must contain column headers that match your desired table column names
3. Data types will be inferred from the content
4. For best results, ensure data is clean and consistent

Example CSV file (`employees.csv`):
```
id,name,department,salary
1,John Doe,Engineering,75000
2,Jane Smith,Marketing,65000
3,Bob Johnson,Finance,80000
```

This will create or populate a table named `employees` with the columns `id`, `name`, `department`, and `salary`.

### Import Process

The CSV import happens automatically when the agent starts up. The process:

1. Reads each CSV file
2. Creates tables if they don't exist
3. Inserts data only for newly created tables
4. Handles data type conversion

If a table already exists, the agent will skip importing data for that table. This prevents accidental data modification of existing tables.
