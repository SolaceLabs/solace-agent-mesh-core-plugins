from typing import Dict, Any, Literal, Optional
from pydantic import BaseModel, Field, model_validator, SecretStr
from google.genai import types as adk_types
from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool
from solace_agent_mesh.agent.sac.component import SamAgentComponent
from .services.database_service import (
    DatabaseService,
    MySQLService,
    PostgresService,
    SQLiteService,
)

import yaml
import logging
log = logging.getLogger(__name__)

class DatabaseConfig(BaseModel):
    tool_name: str = Field(
        description="The name of the tool as it will be invoked by the LLM."
    )
    tool_description: Optional[str] = Field(
        default="", description="A description of what the tool does."
    )
    db_type: Literal["postgresql", "mysql", "sqlite"] = Field(
        description="Type of the database."
    )
    db_host: Optional[str] = Field(
        default=None, description="Database host (required for PostgreSQL/MySQL)."
    )
    db_port: Optional[int] = Field(
        default=None, description="Database port (required for PostgreSQL/MySQL)."
    )
    db_user: Optional[str] = Field(
        default=None, description="Database user (required for PostgreSQL/MySQL)."
    )
    db_password: Optional[SecretStr] = Field(
        default=None, description="Database password (required for PostgreSQL/MySQL)."
    )
    db_name: str = Field(
        description="Database name (for PostgreSQL/MySQL) or file path (for SQLite)."
    )
    auto_detect_schema: bool = Field(
        default=True,
        description="If true, automatically detect schema. If false, overrides must be provided.",
    )
    database_schema_override: Optional[str] = Field(
        default=None,
        description="YAML/text string of the detailed database schema if auto_detect_schema is false.",
    )
    schema_summary_override: Optional[str] = Field(
        default=None,
        description="Natural language summary of the schema if auto_detect_schema is false.",
    )

    @model_validator(mode='after')
    def check_required_fields(self) -> 'DatabaseConfig':
        if self.db_type in ["postgresql", "mysql"]:
            if not all([self.db_host, self.db_port, self.db_user, self.db_password]):
                raise ValueError(
                    f"For db_type '{self.db_type}', db_host, db_port, db_user, and db_password are required."
                )
        
        if self.auto_detect_schema is False:
            if self.database_schema_override is None:
                raise ValueError(
                    "'database_schema_override' is required when 'auto_detect_schema' is false"
                )
            if self.schema_summary_override is None:
                raise ValueError(
                    "'schema_summary_override' is required when 'auto_detect_schema' is false"
                )
        return self
    
    def get(self, key: str, default: Any = None) -> Any:
        """Allows dictionary-like access to the model's attributes."""
        return getattr(self, key, default)

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
        log_identifier = f"[{self.tool_name}:init]"
        log.info("%s Initializing connection...", log_identifier)
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
        
        schema_summary_for_llm: str = ""
        detailed_schema_yaml: str = ""

        try:
            if self.tool_config.auto_detect_schema:
                log.info("%s Auto-detecting database schema...", log_identifier)
                schema_summary_for_llm = self.db_service.get_schema_summary_for_llm()
                detailed_schema_dict = self.db_service.get_detailed_schema_representation()
                detailed_schema_yaml = yaml.dump(
                    detailed_schema_dict, sort_keys=False, allow_unicode=True
                )
                log.info("%s Schema auto-detection complete.", log_identifier)
            else:
                log.info("%s Using provided schema overrides.", log_identifier)
                if (
                    not self.tool_config.schema_summary_override
                    or not self.tool_config.database_schema_override
                ):
                    raise ValueError(
                        "schema_summary_override and database_schema_override are required when auto_detect_schema is false."
                    )
                schema_summary_for_llm = self.tool_config.schema_summary_override
                detailed_schema_yaml = self.tool_config.database_schema_override
                log.info("%s Schema overrides applied.", log_identifier)

            if not schema_summary_for_llm:
                log.warning(
                    "%s Schema summary for LLM is empty. This may impact LLM performance.",
                    log_identifier,
                )

        except Exception as e:
            log.exception("%s Error during schema handling: %s", log_identifier, e)
            raise RuntimeError(f"Schema handling failed: {e}") from e

        log.info("%s Connection for '%s' established.", log_identifier, self.tool_name)

    async def cleanup(self, component: SamAgentComponent, tool_config: Dict):
        log_identifier = f"[{self.tool_name}:cleanup]"
        log.info("%s Closing connection...", log_identifier)
        if self.db_service:
            self.db_service.close()
        log.info("%s Connection for '%s' closed.", log_identifier, self.tool_name)

    async def _run_async_impl(self, args: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        log_identifier = f"[{self.tool_name}:run]"
        query = args.get("query")
        if not self.db_service:
            return {"error": f"The database connection for '{self.tool_name}' is not available."}

        log.info("%s Executing query on '%s': %s", log_identifier, self.tool_name, query)
        try:
            results = self.db_service.execute_query(query)
            return {"result": results}
        except Exception as e:
            log.error("%s Error executing query: %s", log_identifier, e)
            return {"error": str(e)}
