"""SQL Database agent component for handling database operations."""

import copy
from typing import Dict, Any, Optional, List

from solace_ai_connector.common.log import log
from solace_agent_mesh.agents.base_agent_component import (
    agent_info,
    BaseAgentComponent,
)

from .services.database_service import (
    DatabaseService,
    MySQLService,
    PostgresService,
    SQLiteService
)
from .actions.search_query import SearchQuery


info = copy.deepcopy(agent_info)
info.update(
    {
        "agent_name": "sql_database",
        "class_name": "SQLDatabaseAgentComponent",
        "description": "SQL Database agent for executing natural language queries against SQL databases",
        "config_parameters": [
            {
                "name": "agent_name",
                "required": True,
                "description": "Name of this SQL database agent instance",
                "type": "string",
            },
            {
                "name": "db_type",
                "required": True,
                "description": "Database type (mysql, postgres, or sqlite)",
                "type": "string",
            },
            {
                "name": "host",
                "required": False,
                "description": "Database host (for MySQL and PostgreSQL)",
                "type": "string",
            },
            {
                "name": "port",
                "required": False,
                "description": "Database port (for MySQL and PostgreSQL)",
                "type": "integer",
            },
            {
                "name": "user",
                "required": False,
                "description": "Database user (for MySQL and PostgreSQL)",
                "type": "string",
            },
            {
                "name": "password",
                "required": False,
                "description": "Database password (for MySQL and PostgreSQL)",
                "type": "string",
            },
            {
                "name": "database",
                "required": True,
                "description": "Database name (or file path for SQLite)",
                "type": "string",
            },
            {
                "name": "query_timeout",
                "required": False,
                "description": "Query timeout in seconds",
                "type": "integer",
                "default": 30,
            },
            {
                "name": "database_purpose",
                "required": True,
                "description": "Purpose of the database",
                "type": "string",
            },
            {
                "name": "data_description",
                "required": False,
                "description": "Detailed description of the data held in the database. Will be auto-detected if not provided.",
                "type": "string",
            },
            {
                "name": "auto_detect_schema",
                "required": False,
                "description": "Automatically create a schema based on the database structure",
                "type": "boolean",
                "default": True,
            },
            {
                "name": "database_schema",
                "required": False,
                "description": "Database schema if auto_detect_schema is False",
                "type": "string",
            },
            {
                "name": "csv_files",
                "required": False,
                "description": "List of CSV files to import as tables on startup",
                "type": "list",
            },
            {
                "name": "csv_directories", 
                "required": False,
                "description": "List of directories to scan for CSV files to import as tables on startup",
                "type": "list",
            }
        ],
    }
)


class SQLDatabaseAgentComponent(BaseAgentComponent):
    """Component for handling SQL database operations."""

    info = info
    actions = [SearchQuery]

    def __init__(self, module_info: Dict[str, Any] = None, **kwargs):
        """Initialize the SQL Database agent component.

        Args:
            module_info: Optional module configuration.
            **kwargs: Additional keyword arguments.

        Raises:
            ValueError: If required database configuration is missing.
        """
        module_info = module_info or info
        super().__init__(module_info, **kwargs)

        self.agent_name = self.get_config("agent_name")
        self.db_type = self.get_config("db_type")
        self.database_purpose = self.get_config("database_purpose")
        self.data_description = self.get_config("data_description")
        self.auto_detect_schema = self.get_config("auto_detect_schema", True)
        self.query_timeout = self.get_config("query_timeout", 30)

        self.action_list.fix_scopes("<agent_name>", self.agent_name)
        module_info["agent_name"] = self.agent_name

        # Initialize database handler
        self.db_handler = self._create_db_handler()

        # Import any configured CSV files
        csv_files = self.get_config("csv_files", [])
        csv_directories = self.get_config("csv_directories", [])
        if csv_files or csv_directories:
            try:
                self.db_handler.import_csv_files(csv_files, csv_directories)
            except Exception as e:
                log.error("Error importing CSV files: %s", str(e))

        # Get schema information
        if self.auto_detect_schema:
            self.detailed_schema = self._detect_schema()
        else:
            self.detailed_schema = self.get_config("database_schema")
            
        # Generate schema summary for action description
        self.schema_summary = self._get_schema_summary()
        
        # Update the search_query action with schema information
        for action in self.action_list.actions:
            if action.name == "search_query":
                # Access the action's configuration dictionary instead of the prompt_directive attribute
                current_directive = action._prompt_directive
                schema_info = f"\n\nDatabase Schema:\n{self.schema_summary}"
                # Update the prompt_directive in the action's configuration
                action._prompt_directive = current_directive + schema_info
                break

    def _create_db_handler(self) -> DatabaseService:
        """Create appropriate database handler based on configuration.
        
        Returns:
            Database service instance
            
        Raises:
            ValueError: If database configuration is invalid
        """
        connection_params = {
            "database": self.get_config("database"),
        }

        if self.db_type in ("mysql", "postgres"):
            # Add connection parameters needed for MySQL/PostgreSQL
            connection_params.update({
                "host": self.get_config("host"),
                "port": self.get_config("port"),
                "user": self.get_config("user"),
                "password": self.get_config("password"),
            })

        if self.db_type == "mysql":
            return MySQLService(connection_params, query_timeout=self.query_timeout)
        elif self.db_type == "postgres":
            return PostgresService(connection_params, query_timeout=self.query_timeout)
        elif self.db_type in ("sqlite", "sqlite3"):
            return SQLiteService(connection_params, query_timeout=self.query_timeout)
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")

    def _detect_schema(self) -> Dict[str, Any]:
        """Detect database schema including tables, columns, relationships and sample data.
        
        Returns:
            Dictionary containing detailed schema information
        """
        schema = {}
        tables = self.db_handler.get_tables()
        
        for table in tables:
            table_info = {
                "columns": {},
                "primary_keys": self.db_handler.get_primary_keys(table),
                "foreign_keys": self.db_handler.get_foreign_keys(table),
                "indexes": self.db_handler.get_indexes(table)
            }
            
            # Get detailed column information
            columns = self.db_handler.get_columns(table)
            for col in columns:
                col_name = col["name"]
                table_info["columns"][col_name] = {
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                }
                
                # Get sample values and statistics for the column
                try:
                    unique_values = self.db_handler.get_unique_values(table, col_name)
                    if unique_values:
                        table_info["columns"][col_name]["sample_values"] = unique_values

                    stats = self.db_handler.get_column_stats(table, col_name)
                    if stats:
                        table_info["columns"][col_name]["statistics"] = stats
                except Exception:
                    # Skip sample data if there's an error
                    pass

            schema[table] = table_info

        return schema

    def _get_schema_summary(self) -> str:
        """Gets a terse formatted summary of the database schema.

        Returns:
            A string containing a one-line summary of each table and its columns.
        """
        if not self.detailed_schema:
            return "Schema information not available."
            
        summary_lines = []
        
        for table_name, table_info in self.detailed_schema.items():
            # Get all column names
            columns = list(table_info["columns"].keys())
            summary_lines.append(f"{table_name}: {', '.join(columns)}")
            
        return "\n".join(summary_lines)

    def get_db_handler(self) -> DatabaseService:
        """Get the database handler instance."""
        return self.db_handler

    def get_agent_summary(self):
        """Get a summary of the agent's capabilities."""
        description = f"This agent provides read-only access to a {self.db_type} database.\n\n"

        if self.database_purpose:
            description += f"Purpose:\n{self.database_purpose}\n\n"

        if self.data_description:
            description += f"Data Description:\n{self.data_description}\n"
        else:
            # Just mention the tables without the full schema
            tables = list(self.detailed_schema.keys()) if self.detailed_schema else []
            if tables:
                description += f"Contains {len(tables)} tables: {', '.join(tables)}\n"
            else:
                description += "No tables found in database.\n"

        return {
            "agent_name": self.agent_name,
            "description": description,
            "always_open": self.info.get("always_open", False),
            "actions": self.get_actions_summary(),
        }
