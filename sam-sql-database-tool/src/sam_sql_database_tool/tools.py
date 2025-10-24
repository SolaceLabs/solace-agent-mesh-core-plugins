from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, model_validator, SecretStr
from google.genai import types as adk_types
from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool
from solace_agent_mesh.agent.sac.component import SamAgentComponent
from .services.database_service import DatabaseService

import logging
log = logging.getLogger(__name__)

class DatabaseConfig(BaseModel):
    tool_name: str = Field(
        description="The name of the tool as it will be invoked by the LLM."
    )
    tool_description: Optional[str] = Field(
        default="", description="A description of what the tool does."
    )
    connection_string: SecretStr = Field(
        description="The full database connection string (e.g., 'postgresql+psycopg2://user:password@host:port/dbname')."
    )
    auto_detect_schema: bool = Field(
        default=True,
        description="If true, automatically detect schema. If false, overrides must be provided.",
    )
    schema_summary_override: Optional[str] = Field(
        default=None,
        description="Natural language summary of the schema if auto_detect_schema is false.",
    )
    max_enum_cardinality: int = Field(
        default=100,
        description="Maximum number of distinct values to consider a column as an enum (default: 100).",
    )
    schema_sample_size: int = Field(
        default=100,
        description="Number of rows to sample per table for schema detection (default: 100).",
    )
    cache_ttl_seconds: int = Field(
        default=3600,
        description="Time-to-live for schema cache in seconds (default: 3600 = 1 hour).",
    )

    @model_validator(mode='after')
    def check_required_fields(self) -> 'DatabaseConfig':
        if self.auto_detect_schema is False:
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
        self._schema_context: Optional[str] = None
        self._connection_healthy: bool = False
        self._connection_error: Optional[str] = None
        self.description = self.tool_description

    @property
    def tool_name(self) -> str:
        """Return the function name that the LLM will call."""
        return self.tool_config.get("tool_name", "unnamed_sql_database_tool")

    @property
    def tool_description(self) -> str:
        """Return the description of what this tool does, including schema context."""
        base_description = self.tool_config.get("tool_description", "")

        if not self._connection_healthy:
            status_message = f"\n\n❌ WARNING: This database is currently UNAVAILABLE.\n"
            if self._connection_error:
                status_message += f"Connection Error: {self._connection_error}\n"
            status_message += "Queries to this database will fail until connectivity is restored."
            return f"{base_description}{status_message}"

        if self._schema_context:
            return f"{base_description}\n\n✅ Database Connected\n\nDatabase Schema:\n{self._schema_context}"

        return base_description

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

        connection_string = self.tool_config.connection_string.get_secret_value()
        cache_ttl = self.tool_config.cache_ttl_seconds

        try:
            self.db_service = DatabaseService(
                connection_string=connection_string,
                cache_ttl_seconds=cache_ttl
            )
        except Exception as e:
            self._connection_healthy = False
            self._connection_error = f"Failed to create database engine: {type(e).__name__}: {str(e)}"
            log.error(
                "%s Failed to initialize DatabaseService: %s. Tool will be marked as unavailable.",
                log_identifier,
                e
            )
            log.warning(
                "%s Tool '%s' initialized in DEGRADED mode. It will not accept queries until database connectivity is restored.",
                log_identifier,
                self.tool_name
            )
            return

        try:
            if self.tool_config.auto_detect_schema:
                log.info("%s Auto-detecting database schema...", log_identifier)
                self._schema_context = self.db_service.get_optimized_schema_for_llm(
                    max_enum_cardinality=self.tool_config.max_enum_cardinality,
                    sample_size=self.tool_config.schema_sample_size
                )
                log.info("%s Schema cached in memory (%d chars)", log_identifier, len(self._schema_context))
            else:
                log.info("%s Using provided schema overrides.", log_identifier)
                if not self.tool_config.schema_summary_override:
                    raise ValueError(
                        "schema_summary_override is required when auto_detect_schema is false."
                    )
                self._schema_context = self.tool_config.schema_summary_override
                log.info("%s Schema overrides applied.", log_identifier)

            if not self._schema_context:
                log.warning(
                    "%s Schema context is empty. This may impact LLM performance.",
                    log_identifier,
                )

            self._connection_healthy = True
            self._connection_error = None
            log.info("%s Connection for '%s' established successfully.", log_identifier, self.tool_name)

        except Exception as e:
            self._connection_healthy = False
            self._connection_error = f"Schema detection failed: {type(e).__name__}: {str(e)}"
            log.error(
                "%s Error during schema handling: %s. Tool will be marked as unavailable.",
                log_identifier,
                e
            )
            log.warning(
                "%s Tool '%s' initialized in DEGRADED mode. It will not accept queries until database connectivity is restored.",
                log_identifier,
                self.tool_name
            )

    async def cleanup(self, component: SamAgentComponent, tool_config: Dict):
        log_identifier = f"[{self.tool_name}:cleanup]"
        log.info("%s Closing connection...", log_identifier)
        if self.db_service:
            self.db_service.close()
        log.info("%s Connection for '%s' closed.", log_identifier, self.tool_name)

    async def _run_async_impl(self, args: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        log_identifier = f"[{self.tool_name}:run]"
        query = args.get("query")

        if not self._connection_healthy:
            error_msg = f"Database '{self.tool_name}' is currently unavailable."
            if self._connection_error:
                error_msg += f"\nReason: {self._connection_error}"
            error_msg += "\nPlease check the database connectivity and try again later."
            log.warning("%s Query rejected - connection unhealthy: %s", log_identifier, self._connection_error)
            return {"error": error_msg}

        if not self.db_service:
            return {"error": f"The database connection for '{self.tool_name}' is not available."}

        log.info("%s Executing query on '%s': %s", log_identifier, self.tool_name, query)
        try:
            results = self.db_service.execute_query(query)
            return {"result": results}
        except Exception as e:
            log.error("%s Error executing query: %s", log_identifier, e)
            return {"error": str(e)}
