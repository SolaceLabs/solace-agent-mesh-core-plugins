# Solace Agent Mesh MongoDB Plugin

A plugin that provides a MongoDB agent capable of performing complex queries based on natural language.

## Features

- Natural language to MongoDB aggregation pipeline conversion using an LLM.
- Query execution against MongoDB databases.
- Automatic schema detection (optional) with sample data for better LLM context.
- Configurable response formats (YAML, JSON, CSV, Markdown).
- Handles query retries on LLM or database errors.

## Add a MongoDB Agent to SAM

1.  **Add the Plugin:**
    If you haven't already, add the plugin to your SAM instance:
    ```sh
    solace-agent-mesh plugin add sam_mongodb --pip -u git+https://github.com/SolaceLabs/solace-agent-mesh-core-plugins#subdirectory=sam-mongodb
    ```

2.  **Instantiate the Agent:**
    You have two options:

    *   **Option A: Editing `solace-agent-mesh.yaml` (For a single instance):**
        If you only need one MongoDB agent, you can directly load it in your main `solace-agent-mesh.yaml`:
        ```yaml
        # solace-agent-mesh.yaml
        ...
        plugins:
          ...
          - name: sam_mongodb
            load_unspecified_files: false
            includes_gateway_interface: false
            load:
              agents:
                - mongodb # Loads configs/agents/mongodb.yaml by default
              gateways: []
              overwrites: []
          ...
        ```
        **Note:** If using this method, the environment variable prefix will be `MONGODB` (see below). You might need to manually edit `configs/agents/mongodb.yaml` for settings not controlled by environment variables (like `database_purpose`, `data_description`).

    *   **Option B: Using `add agent` (Recommended for multiple instances):**
        Use the `solace-agent-mesh add agent` command. Replace `<new_agent_name>` with a descriptive name (e.g., `customer_db`, `product_catalog`).
        ```sh
        solace-agent-mesh add agent <new_agent_name> --copy-from sam_mongodb:mongodb
        ```
        This creates `<new_agent_name>.yaml` in `configs/agents/` with template variables automatically replaced. You will need to set environment variables specific to this agent instance.

## Environment Variables

The following environment variables are required for **Solace connection** (used by all agents):
- **SOLACE_BROKER_URL**
- **SOLACE_BROKER_USERNAME**
- **SOLACE_BROKER_PASSWORD**
- **SOLACE_BROKER_VPN**
- **SOLACE_AGENT_MESH_NAMESPACE**

For **each MongoDB agent instance**, you need to set the following environment variables. Replace `<AGENT_NAME>` with the uppercase version of the agent's name:
  - If you used **Option A** (editing `solace-agent-mesh.yaml`), the default agent name is `mongodb`, so use `MONGODB`.
  - If you used **Option B** (`add agent`), use the uppercase version of the `<new_agent_name>` you provided (e.g., `CUSTOMER_DB`, `PRODUCT_CATALOG`).

- **`<AGENT_NAME>_MONGO_HOST`** (Required): MongoDB host address.
- **`<AGENT_NAME>_MONGO_PORT`** (Required): MongoDB port number.
- **`<AGENT_NAME>_MONGO_DB`** (Required): The name of the MongoDB database to connect to.
- **`<AGENT_NAME>_DB_PURPOSE`** (Required): A clear description of the purpose of this database. Used to help the LLM understand context.
- **`<AGENT_NAME>_DB_DESCRIPTION`** (Required): A detailed description of the data stored in the database/collections, including document structures, field meanings, and relationships. Crucial for accurate query generation.
- **`<AGENT_NAME>_MONGO_USER`** (Optional): MongoDB username for authentication.
- **`<AGENT_NAME>_MONGO_PASSWORD`** (Optional): MongoDB password for authentication.
- **`<AGENT_NAME>_MONGO_COLLECTION`** (Optional): Specific collection to target. If omitted, the agent can query across all collections (schema detection will scan all).
- **`<AGENT_NAME>_AUTO_DETECT_SCHEMA`** (Optional): Set to `true` (default) or `false`. If true, the agent attempts to detect collection schemas on startup.
- **`<AGENT_NAME>_MAX_INLINE_RESULTS`** (Optional): Maximum number of results to include directly in the response message before switching to an attached file. Defaults to `10`.

**Example Environment Variables:**

For the default agent loaded via `solace-agent-mesh.yaml` (Option A):
```bash
export MONGODB_MONGO_HOST="localhost"
export MONGODB_MONGO_PORT="27017"
export MONGODB_MONGO_DB="mydatabase"
export MONGODB_DB_PURPOSE="Stores user profiles and activity data."
export MONGODB_DB_DESCRIPTION="Contains 'users' collection (fields: _id, name, email, age, signup_date) and 'activity' collection (fields: _id, user_id, action, timestamp)."
# Optional auth:
# export MONGODB_MONGO_USER="myuser"
# export MONGODB_MONGO_PASSWORD="mypassword"
```

For an agent named `product_catalog` created via `add agent` (Option B):
```bash
export PRODUCT_CATALOG_MONGO_HOST="mongo.example.com"
export PRODUCT_CATALOG_MONGO_PORT="27017"
export PRODUCT_CATALOG_MONGO_DB="catalog"
export PRODUCT_CATALOG_MONGO_COLLECTION="products" # Target specific collection
export PRODUCT_CATALOG_DB_PURPOSE="Contains detailed information about products offered."
export PRODUCT_CATALOG_DB_DESCRIPTION="The 'products' collection has fields like: product_id, name, description, price, category, stock_level, attributes (nested object)."
export PRODUCT_CATALOG_AUTO_DETECT_SCHEMA="true"
```

## Actions

### search_query
Executes a natural language query against the configured MongoDB database. The agent uses an LLM to convert the natural language into a MongoDB aggregation pipeline, executes it, and returns the results.

Parameters:
- **query** (required): Natural language description of the search query.
- **response_format** (optional): Format for the results (yaml, markdown, json, csv). Defaults to `yaml`.
- **inline_result** (optional): If `true` (default) and results are small enough (`max_inline_results`), return results directly in the response. Otherwise, results are returned as an attached file.
