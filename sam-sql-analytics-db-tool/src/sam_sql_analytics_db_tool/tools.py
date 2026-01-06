from google.genai import types as adk_types
from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool
from typing import Dict, Any, Optional
import logging
import os
import yaml

from urllib.parse import urlparse
from .services.connection import DBFactory
from .subprocess.analytics_manager import AnalyticsSubprocessManager
from .services.security import SecurityService, PIIFilterService

log = logging.getLogger(__name__)

class SqlAnalyticsDbTool(DynamicTool):
    """SQL Analytics tool with OpenMetadata integration."""
    
    def __init__(self, tool_config):
        """Initialize the tool with configuration."""
        super().__init__(tool_config)
        self.db_factory = None
        # Subprocess manager
        self.subprocess = None

        # security service
        self.security_service = None

        # context data
        self._schema_context = None
        self._profile_context = None
 
        self._connection_healthy = False
        self._connection_error = None
        
    @property
    def parameters_schema(self):
        """Define the parameters schema - only SQL queries allowed."""
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "query": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Read-only SQL query to execute."
                )
            },
            required=["query"]
        )
    
    @property
    def tool_name(self) -> str:
        """Return the function name that the LLM will call."""
        return self.tool_config.get("tool_name", "unnamed_sql_database_tool")
        
    @property
    def tool_description(self):
        """Include schema and profile data in tool description (with PII filtering)."""
        context = []
        if not self._connection_healthy:
            status_message = f"\n\n❌ WARNING: Database is currently UNAVAILABLE.\n"
            if self._connection_error:
                status_message += f"Connection Error: {self._connection_error}\n"
            status_message += "Queries will fail until connectivity is restored."
            return f"{self.tool_config.get('tool_description', '')}{status_message}"
        else:
            context.append("✅ Database Connected")

        # Apply PII filtering before including in LLM context
        pii_filter_level = self.tool_config.get("security", {}).get("pii_filter_level", "none")
        schema_for_llm = self._schema_context
        profile_for_llm = self._profile_context

        if pii_filter_level != "none" and (self._schema_context or self._profile_context):
            # Filter contexts (handles None inputs gracefully)
            schema_for_llm, profile_for_llm = PIIFilterService.filter_for_llm(
                schema=self._schema_context or {},
                profile=self._profile_context or {},
                level=pii_filter_level
            )
            # Restore None if original was None
            if not self._schema_context:
                schema_for_llm = None
            if not self._profile_context:
                profile_for_llm = None

        # Include both schema and profile data in context
        if schema_for_llm:
            context.append("\nDatabase Schema:")
            context.append(yaml.dump(schema_for_llm, default_flow_style=False))

        if profile_for_llm:
            context.append("\nDatabase Profile:")
            context.append(yaml.dump(profile_for_llm, default_flow_style=False))

        return "\n".join([self.tool_config.get("tool_description", "")] + context)
        
    async def init(self, component, tool_config: Dict):
        """Initialize services and run discovery/profiling."""
        try:
            # Get configuration
            connection_string = self.tool_config["connection_string"]
            pool_config = self.tool_config.get("pool", {})
            timeouts = self.tool_config.get("timeouts", {})
            security_config = self.tool_config.get("security", {})
            profiling_config = self.tool_config.get("profiling", {})
            
            # Initialize services
            self.db_factory = DBFactory(
                connection_string=connection_string,
                pool_config=pool_config,
                timeouts=timeouts
            )
            
            self.security_service = SecurityService(
                blocked_operations=security_config.get("blocked_operations"),
                warning_operations=security_config.get("warning_operations")
            )
            log.info("Initialized DBFactory and SecurityService")
            self.subprocess = AnalyticsSubprocessManager()

            # Run combined discovery + profiling in parallel (single subprocess)
            log.info("Running subprocess combined discovery + profiling...")
            combined_result = self.subprocess.run_combined(connection_string)

            # Unpack results
            self._schema_context = combined_result.get("discovery")
            self._profile_context = combined_result.get("profiling")

            log.info("Done subprocess combined discovery + profiling!")

            self._connection_healthy = True
            log.info("Discovery and profiling completed")

        except Exception as e:
            self._connection_healthy = False
            self._connection_error = str(e)
            log.error("Failed to initialize SQL analytics tool: %s", e)
            
    async def cleanup(self, component, tool_config: Dict):
        """Clean up resources."""
        if self.db_factory:
            self.db_factory.close()
            
    async def _run_async_impl(self, args: Dict[str, Any], **kwargs):
        """Execute validated SQL query."""
        if not self._connection_healthy:
            return {
                "error": f"Database connection is not available: {self._connection_error}"
            }
            
        query = args.get("query")
        if not query:
            return {"error": "No SQL query provided"}
            
        # Validate query
        validation = self.security_service.validate_query(
            query,
            self.security_service.get_sql_dialect(
                urlparse(self.tool_config["connection_string"]).scheme
            )
        )
        
        if not validation["valid"]:
            return {"error": validation["reason"]}
            
        if validation.get("warnings"):
            log.warning("Query warnings: %s", validation["warnings"])
            
        try:
            # Execute query with row limit enforcement
            results = self.db_factory.run_select(query)

            # Filter PII from query results based on security configuration
            pii_filter_level = self.tool_config.get("security", {}).get("pii_filter_level", "none")
            if pii_filter_level != "none" and self._schema_context:
                results = PIIFilterService.filter_pii_from_results(
                    results=results,
                    schema_context=self._schema_context,
                    filter_level=pii_filter_level
                )

            return {"result": results}

        except Exception as e:
            log.error("Query execution failed: %s", e)
            return {"error": str(e)}
