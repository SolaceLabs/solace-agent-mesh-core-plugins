from typing import Dict, Any, Optional
from google.genai import types as adk_types
from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool
from solace_agent_mesh.agent.sac.component import SamAgentComponent
from .config import DatabaseConfig
from .services.database_service import (
    DatabaseService,
    MySQLService,
    PostgresService,
    SQLiteService,
)

class SqlDatabaseTool(DynamicTool):
    config_model = DatabaseConfig

    def __init__(self, tool_config: DatabaseConfig):
        super().__init__(tool_config)
        self.db_service: Optional[DatabaseService] = None

    @property
    def tool_name(self) -> str:
        """Return the function name that the LLM will call."""
        return self.tool_config.get("tool_name", "unnamed_sql_database_tool")

    @property
    def tool_description(self) -> str:
        """Return the description of what this tool does."""
        return self.tool_config.get("tool_description", "")

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "query": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="The SQL query to execute."
                ),
            },
            required=["query"],
        )

    async def init(self, component: SamAgentComponent, tool_config: Dict):
        print(f"INFO: Initializing connection for '{self.tool_name}'...")
        connection_params = {
            "host": self.tool_config.db_host,
            "port": self.tool_config.db_port,
            "user": self.tool_config.db_user,
            "password": (
                self.tool_config.db_password.get_secret_value()
                if self.tool_config.db_password
                else None
            ),
            "database": self.tool_config.db_name,
        }

        if self.tool_config.db_type == "postgresql":
            self.db_service = PostgresService(connection_params)
        elif self.tool_config.db_type == "mysql":
            self.db_service = MySQLService(connection_params)
        elif self.tool_config.db_type == "sqlite":
            sqlite_params = {"database": self.tool_config.db_name}
            self.db_service = SQLiteService(sqlite_params)
        else:
            raise ValueError(f"Unsupported database type: {self.tool_config.db_type}")
        
        print(f"INFO: Connection for '{self.tool_name}' established.")

    async def cleanup(self, component: SamAgentComponent, tool_config: Dict):
        print(f"INFO: Closing connection for '{self.tool_name}'...")
        if self.db_service:
            self.db_service.close()
        print(f"INFO: Connection for '{self.tool_name}' closed.")

    async def _run_async_impl(self, args: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        query = args.get("query")
        if not self.db_service:
            return {"error": f"The database connection for '{self.tool_name}' is not available."}
        
        print(f"INFO: Executing query on '{self.tool_name}': {query}")
        try:
            results = self.db_service.execute_query(query)
            return {"result": results}
        except Exception as e:
            return {"error": str(e)}
