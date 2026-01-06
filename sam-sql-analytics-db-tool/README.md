# SQL Analytics DB Tool

A SQL analytics tool with OpenMetadata integration for schema discovery and profiling.

## Features

- **Schema Discovery**: Automatically discovers and maps database schemas using OpenMetadata
- **Data Profiling**: Generates statistical profiles of database tables and columns using OpenMetadata
- **PII Detection & Filtering**: Automatic detection of PII using OpenMetadata's NER scanner, with configurable filtering for LLM contexts
- **Security**: Enforces read-only access with SQL query validation
- **Connection Management**: Supports multiple database types with connection pooling
- **Query Execution**: Executes validated SQL queries with row limits and timeouts

## Supported Databases

**Fully Supported (Tested):**
- PostgreSQL
- MySQL/MariaDB

**Experimental (Implementation exists, not fully tested):**
- SQLite
- Microsoft SQL Server
- Oracle
- Snowflake

> Note: Experimental databases have connection and configuration scaffolding but lack integration test coverage. Use with caution in production environments.

## Configuration

Example configuration in `config.yaml`:

```yaml
tool_config:
  tool_name: "analytics_db"
  tool_description: "SQL analytics tool with OpenMetadata integration"
  connection_string: "${DB_CONNECTION_STRING}"
  output_dir: "${OUTPUT_DIR, ./analytics_data}"
  
  # Database connection pool settings
  pool:
    pool_size: 5
    max_overflow: 5
    pool_timeout: 30
    pool_recycle: 1800
    pool_pre_ping: true
  
  # Query timeouts
  timeouts:
    connect_timeout: 10
    statement_timeout_ms: 30000
  
  # Security settings
  security:
    blocked_operations: ["ALTER", "DROP", "TRUNCATE", "DELETE", "UPDATE", "GRANT", "REVOKE"]
    warning_operations: ["INSERT", "CREATE"]
    pii_filter_level: "none"  # Options: "strict", "moderate", "none" (default)
```

### Connection String Format

Connection strings follow standard URL format:

```
dialect://username:password@hostname:port/database
```

**Tested Examples:**
- PostgreSQL: `postgres://user:pass@localhost:5432/mydb`
- MySQL: `mysql://user:pass@localhost:3306/mydb`

**Experimental (Untested):**
- SQLite: `sqlite:///path/to/db.sqlite`
- MSSQL: `mssql://user:pass@localhost:1433/mydb?driver=ODBC+Driver+18+for+SQL+Server`
- Oracle: `oracle://user:pass@localhost:1521/service_name`
- Snowflake: `snowflake://user:pass@account/database/schema?warehouse=compute_wh`

## Usage

The tool provides a single endpoint for executing SQL queries:

```python
result = await tool.run({
    "query": "SELECT * FROM users LIMIT 100"
})
```

The tool automatically:
1. Validates the query for security
2. Enforces row limits
3. Returns results as a list of dictionaries

## LLM Capabilities with Context Enrichment

With schema discovery and profiling context, the LLM can answer:

**Data Discovery:**
- "What tables are in this database?"
- "Show me the schema for the users table"
- "Which tables have foreign keys to users?"
- "What indexes exist on the products table?"

**Data Quality:**
- "Which columns have NULL values?"
- "What's the null ratio for email column?"
- "Which tables have the highest null ratios?"
- "Are there columns with 100% distinct values?"

**Distribution & Statistics:**
- "What's the price range of products?"
- "Show me the distribution of ratings"
- "What's the median order amount?"
- "Show me quartiles for product prices"

**Privacy & PII:**
- "Which columns contain PII?"
- "Show me all Sensitive PII columns"
- "Does customer_records have any PII?"

**Data Volume:**
- "How many rows are in each table?"
- "Which table has the most rows?"

**Query Generation:**
- "Write a query to find users who signed up this month"
- "Get all orders with customer names" (uses FK relationships)
- "Find products with price > average"

**Anomaly Detection (Current Profile):**
- "Are there unusual patterns in the data?" (uses stddev/IQR)
- "Are there any price outliers?" (uses quartiles)
- "Are there columns with suspiciously high null ratios?"

### Schema Discovery

On initialization, the tool:
1. Discovers database schema using OpenMetadata
2. Generates schema documentation
3. Makes schema available in tool description

### Data Profiling

The tool performs data profiling to provide:
1. Column statistics (min, max, mean, etc.)
2. Value distributions
3. Data quality metrics

### PII Detection and Filtering

The tool automatically detects Personally Identifiable Information (PII) using OpenMetadata's machine learning-based scanners:

**Detection Methods:**
1. **Column Name Scanner**: Detects PII based on column naming patterns (e.g., "email", "ssn", "phone")
2. **NER Scanner**: Analyzes actual data content using Microsoft Presidio and spaCy NLP models to detect PII regardless of column names

**Detected PII Types:**
- Phone numbers
- SSNs
- Email addresses
- Physical addresses
- Credit card numbers
- IP addresses
- URLs
- Person names
- Bank account numbers (IBAN)

**PII Filtering Levels:**

Configure `pii_filter_level` in security settings to control PII visibility in LLM contexts:

- **`strict`**: Remove ALL PII values from LLM context
  - Column names/types/constraints remain visible (for SQL generation)
  - Removes: enum_values, min/max/histogram (actual PII data)
  - Use when LLM should never see actual PII values

- **`moderate`**: Remove only Sensitive PII values
  - Filters high-risk PII (SSN, credit cards)
  - Keeps NonSensitive PII visible
  - Use for balanced privacy protection

- **`none`** (default): No filtering
  - All detected PII remains visible in LLM context
  - Use when PII exposure to LLM is acceptable

**What Gets Filtered:**

When `pii_filter_level` is set to `"strict"` or `"moderate"`, PII is filtered from:

1. **LLM Context (tool description):**
   - Schema: `enum_values` removed from PII columns
   - Profile: ALL `column_metrics` removed for PII columns
   - Preserved: Column names, types, PKs, FKs, indexes (schema structure intact)

2. **Query Results (user/UI):**
   - PII column values masked as `"***REDACTED***"`
   - Column names and structure preserved
   - Non-PII columns remain visible with actual values

**Important Notes:**
- PII filtering applies to both LLM context AND query results returned to user
- Original schema context remains unfiltered internally
- LLM can still generate queries using PII column names (sees column definitions)
- Profile metrics removed to prevent min/max/histogram value leakage

**Example Configuration:**
```yaml
security:
  pii_filter_level: "strict"  # Mask ALL PII in LLM context + query results
```

**Example Query Result (strict mode):**
```json
{
  "result": [
    {
      "id": 1,
      "name": "***REDACTED***",
      "email": "***REDACTED***",
      "created_at": "2024-01-15T10:30:00"
    }
  ]
}
```

## Security

The tool enforces:
1. Read-only access (SELECT queries only)
2. Row limits on all queries
3. Query timeouts
4. Blocked operations list
5. Warning operations list

## Development

### Prerequisites

- Python 3.10+
- OpenMetadata
- SQLAlchemy
- Database drivers for supported databases

### Installation

```bash
pip install -e .
```

### Testing

```bash
pytest tests/
