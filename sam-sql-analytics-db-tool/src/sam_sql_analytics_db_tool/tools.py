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
        """Define the parameters schema for query execution and historical profiling."""
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "operation": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    enum=["query", "get_profile", "list_profiles"],
                    description=(
                        "Operation type:\n"
                        "- 'query': Execute SQL query (default)\n"
                        "- 'get_profile': Load historical profile for specific date\n"
                        "- 'list_profiles': List all available profile dates"
                    )
                ),
                "query": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Read-only SQL query to execute (when operation='query')."
                ),
                "date": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Date in YYYY-MM-DD format (when operation='get_profile')."
                )
            },
            required=[]  # operation defaults to "query", then query is required
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

        # Add directive for LLM to use context before querying
        if self._schema_context and self._profile_context:
            context.append("\n" + "="*80)
            context.append("⚠️  CRITICAL INSTRUCTION ⚠️")
            context.append("="*80)
            context.append("ALWAYS prefer the DATABASE SCHEMA and DATABASE PROFILE sections below over executing SQL queries.")
            context.append("These sections contain:")
            context.append("  • Complete table definitions (columns, types, constraints, relationships)")
            context.append("  • Pre-computed statistics (row counts, min/max/mean/median/stddev/quartiles)")
            context.append("  • Data distributions (histograms)")
            context.append("\nExecute SQL queries ONLY when:")
            context.append("  • You need actual data values (not just counts or statistics)")
            context.append("  • The question requires filtering (WHERE), joins, or aggregations beyond simple counts")
            context.append("="*80 + "\n")

        # Add historical profiling info if available
        if self._artifact_service:
            context.append("\n📅 Historical Profiling:")
            context.append("  Drift detection enabled - use operations to compare profiles over time:")
            context.append("  • list_profiles - Get available snapshot dates")
            context.append("  • get_profile(date='YYYY-MM-DD') - Load historical profile for comparison")
            context.append("")

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

        # Include both schema and profile data in context with visual markers
        if schema_for_llm:
            context.append("\n" + "="*80)
            context.append("📋 DATABASE SCHEMA")
            context.append("="*80)
            context.append(yaml.dump(schema_for_llm, default_flow_style=False))
            context.append("="*80 + "\n")

        if profile_for_llm:
            context.append("\n" + "="*80)
            context.append("📊 DATABASE PROFILE (Pre-computed Statistics)")
            context.append("="*80)
            context.append(yaml.dump(profile_for_llm, default_flow_style=False))
            context.append("="*80)

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

            # Initialize historical profiling if artifact service available
            self._artifact_service = None
            self._app_name = None

            if hasattr(component, "artifact_service") and component.artifact_service:
                from .services.profile_history import ProfileHistoryService

                self._artifact_service = component.artifact_service
                self._app_name = getattr(component, "app_name", "sam-app")
                self.profile_history = ProfileHistoryService(self.tool_name)

                # ⚠️  DEMO POC: Auto-generate synthetic profiles if none exist (DELETE THIS LINE FOR PRODUCTION)
                await self._init_demo_profiles_if_empty()

                log.info("Historical profiling enabled (artifact service available)")
            else:
                log.warning("Historical profiling disabled (artifact service unavailable)")

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
        """Route to appropriate handler based on operation type."""
        operation = args.get("operation", "query")  # Default to query for backward compatibility

        if operation == "query":
            return await self._handle_query(args, kwargs)
        elif operation == "get_profile":
            return await self._handle_get_profile(args, kwargs)
        elif operation == "list_profiles":
            return await self._handle_list_profiles(args, kwargs)
        else:
            return {"error": f"Invalid operation: {operation}"}

    async def _handle_query(self, args: Dict[str, Any], kwargs: Dict[str, Any]):
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
            max_rows = self.tool_config.get("security", {}).get("max_result_rows", 1000)
            results = self.db_factory.run_select(query, limit=max_rows)

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

    async def _handle_get_profile(self, args: Dict[str, Any], kwargs: Dict[str, Any]):
        """Load historical profile snapshot for drift analysis."""
        if not hasattr(self, 'profile_history') or not self._artifact_service:
            return {
                "error": "Historical profiling not available (artifact service unavailable)"
            }

        date = args.get("date")
        if not date:
            return {"error": "Missing 'date' parameter for get_profile operation"}

        # Validate date format
        from datetime import datetime
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return {"error": f"Invalid date format: {date}. Use YYYY-MM-DD"}

        # Load profile from artifact storage
        profile = await self.profile_history.get_profile(
            date=date,
            artifact_service=self._artifact_service,
            app_name=self._app_name
        )

        if not profile:
            return {
                "error": f"Profile not found for date {date}. Use list_profiles operation to see available dates."
            }

        return {
            "date": date,
            "profile": profile
        }

    async def _handle_list_profiles(self, args: Dict[str, Any], kwargs: Dict[str, Any]):
        """List all available historical profile dates."""
        if not hasattr(self, 'profile_history') or not self._artifact_service:
            return {
                "error": "Historical profiling not available (artifact service unavailable)"
            }

        dates = await self.profile_history.list_profiles(
            artifact_service=self._artifact_service,
            app_name=self._app_name
        )

        return {
            "available_dates": dates,
            "count": len(dates)
        }

    async def _init_demo_profiles_if_empty(self):
        """⚠️  DEMO POC ONLY - Delete this entire method for production.

        Auto-generates 20 days of synthetic profiles with anomalies if none exist.
        """
        existing = await self.profile_history.list_profiles(self._artifact_service, self._app_name)
        if len(existing) == 0:
            log.info("🔧 POC: Generating 20 days of demo profiles with anomalies...")
            await self.profile_history.generate_demo_snapshots(
                self._profile_context, self._artifact_service, self._app_name, num_days=20
            )
