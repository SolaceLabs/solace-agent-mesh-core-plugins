"""Security services for SQL query validation and PII filtering."""
from sqlglot import parse_one
from typing import Dict, Any
import logging
import copy

log = logging.getLogger(__name__)

class SecurityService:
    """Service for SQL query validation and security."""
    
    # SQL operations that are never allowed
    FORBIDDEN_TOPLEVEL = {
        "insert", "update", "delete", "drop", "alter", 
        "create", "truncate", "merge"
    }
    
    # Additional tokens that should not appear in queries
    FORBIDDEN_TOKENS = {
        "grant", "revoke", "execute", "call"
    }
    
    def __init__(self, blocked_operations: list = None, warning_operations: list = None):
        """Initialize security service.
        
        Args:
            blocked_operations: List of SQL operations to block
            warning_operations: List of SQL operations to warn about
        """
        self.blocked_operations = {op.lower() for op in (blocked_operations or [])}
        self.warning_operations = {op.lower() for op in (warning_operations or [])}
        
        # Add default forbidden operations
        self.blocked_operations.update(self.FORBIDDEN_TOPLEVEL)
        self.blocked_operations.update(self.FORBIDDEN_TOKENS)
        
    def is_read_only_sql(self, sql: str, dialect: str = None) -> bool:
        """Parse SQL and ensure it's a SELECT (read-only), with no DDL/DML tokens.

        Uses AST traversal to avoid false positives from keywords in strings/identifiers.

        Args:
            sql: SQL query to validate
            dialect: SQL dialect to use for parsing

        Returns:
            True if query is read-only, False otherwise
        """
        try:
            # Parse the SQL query
            ast = parse_one(sql, read=dialect)

            # Top-level must be SELECT
            if ast.key.lower() != "select":
                return False

            # AST-based check: traverse nodes for forbidden operations
            # Uses self.blocked_operations (YAML config + hardcoded FORBIDDEN_*)
            # This prevents false positives from keywords in string literals or identifiers
            for node in ast.walk():
                node_type = node.key.lower() if hasattr(node, 'key') else ''
                if node_type in self.blocked_operations:
                    log.warning(
                        "Blocked query contains forbidden operation: %s",
                        node_type
                    )
                    return False

            return True

        except Exception:
            log.warning("Failed to parse SQL for read-only check.", exc_info=True)
            # Fail closed on parse errors
            return False
            
    def validate_query(self, sql: str, dialect: str = None) -> Dict[str, Any]:
        """Validate a SQL query for security compliance.
        
        Args:
            sql: SQL query to validate
            dialect: SQL dialect to use for parsing
            
        Returns:
            Dictionary containing validation results
        """
        try:
            # First check if query is read-only
            if not self.is_read_only_sql(sql, dialect):
                return {
                    "valid": False,
                    "reason": "Only SELECT queries are allowed"
                }
                
            # Check for warning operations
            lowered = f" {sql.lower()} "
            warnings = []
            for op in self.warning_operations:
                if f" {op} " in lowered:
                    warnings.append(f"Query contains '{op}' operation")
                    
            return {
                "valid": True,
                "warnings": warnings if warnings else None
            }
            
        except Exception as e:
            log.error("Query validation failed: %s", e)
            return {
                "valid": False,
                "reason": f"Query validation failed: {str(e)}"
            }
            
    def get_sql_dialect(self, connection_type: str) -> str:
        """Get sqlglot dialect name for database type.

        Args:
            connection_type: Database type from connection string (e.g., 'mysql+pymysql', 'postgresql')

        Returns:
            sqlglot dialect name
        """
        # Strip driver suffix (e.g., mysql+pymysql → mysql)
        base_type = connection_type.lower().split('+')[0]

        # Map connection types to sqlglot dialects
        dialect_map = {
            "postgres": "postgres",
            "postgresql": "postgres",
            "mysql": "mysql",
            "mariadb": "mysql",
            "sqlite": "sqlite",
            "mssql": "tsql",
            "sqlserver": "tsql",
            "oracle": "oracle",
            "snowflake": "snowflake",
        }
        return dialect_map.get(base_type)


class PIIFilterService:
    """Service for filtering PII from contexts before sending to LLM."""

    @staticmethod
    def _identify_pii_columns(
        schema_context: Dict[str, Any],
        filter_level: str
    ) -> set[str]:
        """Identify PII column names based on filter level.

        Args:
            schema_context: Schema context with PII detection metadata
            filter_level: "strict" (all PII), "moderate" (sensitive only), or "none"

        Returns:
            Set of column names that should be filtered
        """
        if filter_level == "none" or not schema_context:
            return set()

        pii_columns = set()
        for table_name, table_data in schema_context.get("tables", {}).items():
            for col in table_data.get("columns", []):
                pii_info = col.get("pii")
                if pii_info and pii_info.get("pii_detected"):
                    # Apply filtering based on level
                    if filter_level == "strict":
                        # Filter all PII
                        pii_columns.add(col["name"])
                    elif filter_level == "moderate":
                        # Filter only Sensitive PII
                        pii_type = pii_info.get("pii_type", "")
                        if pii_type == "Sensitive":
                            pii_columns.add(col["name"])

        return pii_columns

    @staticmethod
    def filter_for_llm(
        schema: Dict[str, Any],
        profile: Dict[str, Any],
        level: str
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Filter PII columns from schema and profile contexts.

        This prevents PII from reaching the LLM in tool descriptions.
        Works for PostgreSQL, MySQL, Oracle, Snowflake, MSSQL, SQLite.

        Args:
            schema: Schema context dict with structure:
                {
                    "tables": {
                        "users": {
                            "columns": [
                                {
                                    "name": "email",
                                    "type": "VARCHAR(255)",
                                    "nullable": False,
                                    "pii": {
                                        "pii_detected": True,
                                        "pii_type": "Sensitive",
                                        "confidence": 1.0
                                    }
                                },
                                {"name": "id", "type": "INTEGER", ...}
                            ],
                            "primary_key": ["id"],
                            "foreign_keys": [...],
                            "indexes": [...]
                        }
                    },
                    "_summary": {"total_tables": 5, "total_columns": 42}
                }

            profile: Profile context dict with structure:
                {
                    "tables": {
                        "users": {
                            "table_metrics": {"row_count": 1000, ...},
                            "column_metrics": {
                                "email": {
                                    "type": "VARCHAR(255)",
                                    "count": 1000,
                                    "null_count": 0,
                                    "distinct_count": 1000,
                                    "min": "aaron@company.com",  # <- Leaks PII!
                                    "max": "zoe@company.com"     # <- Leaks PII!
                                },
                                "id": {"count": 1000, "min": 1, "max": 1000, ...}
                            }
                        }
                    },
                    "_summary": {"total_tables": 5}
                }

            level: Protection level - "strict", "moderate", or "none"
                - "strict": Remove ALL PII values (keep column defs)
                - "moderate": Remove Sensitive PII values only
                - "none": No filtering (default)

        Returns:
            Tuple of (filtered_schema, filtered_profile) with:
            - Schema: enum_values removed from PII columns
            - Profile: column_metrics removed for PII columns
            - Preserved: Column names, types, PKs, FKs, indexes

        Example:
            >>> schema, profile = PIIFilterService.filter_for_llm(
            ...     schema, profile, "strict"
            ... )
            >>> # email column kept, but enum_values and metrics removed
        """
        # Always copy for safety
        filtered_schema = copy.deepcopy(schema)
        filtered_profile = copy.deepcopy(profile)

        pii_columns_filtered = 0

        if level != "none":
            log.debug("PII filtering level: %s", level)

            # Identify PII columns using shared helper (needs dict structure)
            pii_columns_global = PIIFilterService._identify_pii_columns(filtered_schema, level)

            # Filter schema: remove enum_values from PII columns (keep column definitions)
            for table_name, table_data in filtered_schema.get("tables", {}).items():
                for col in table_data.get("columns", []):
                    if col["name"] in pii_columns_global:
                        # Remove enum_values (actual PII data) but keep column definition
                        if "enum_values" in col:
                            del col["enum_values"]
                            log.debug(
                                "Removed enum_values from PII column %s.%s",
                                table_name, col["name"]
                            )
                        pii_columns_filtered += 1

            # Filter profile: remove ALL column_metrics for PII columns
            # Profile metrics leak PII via min/max/histogram/distinct values
            for table_name, table_profile in filtered_profile.get("tables", {}).items():
                # Use the same PII columns set identified earlier
                pii_columns = pii_columns_global

                # Remove metrics for PII columns only
                column_metrics = table_profile.get("column_metrics", {})
                filtered_metrics = {
                    col_name: metrics
                    for col_name, metrics in column_metrics.items()
                    if col_name not in pii_columns
                }
                table_profile["column_metrics"] = filtered_metrics

            # Update summary stats
            if pii_columns_filtered > 0:
                filtered_schema.setdefault("_summary", {})[
                    "pii_columns_filtered"
                ] = pii_columns_filtered
                log.info(
                    "PII filter (%s): Filtered %d columns (values removed)",
                    level,
                    pii_columns_filtered
                )

        # Always trim redundant fields (LAST STEP, after all PII filtering)
        PIIFilterService._trim_for_llm_context(filtered_schema, filtered_profile)

        return filtered_schema, filtered_profile

    @staticmethod
    def _trim_for_llm_context(schema: Dict[str, Any], profile: Dict[str, Any]):
        """Remove redundant/verbose fields to reduce context size.

        Modifies schema and profile in-place.
        """
        # Trim schema PII metadata (keep only pii_type, remove verbose fields)
        for table_data in schema.get("tables", {}).values():
            for col in table_data.get("columns", []):
                pii_info = col.get("pii")
                if pii_info and isinstance(pii_info, dict):
                    # Simplify PII info: keep only type
                    pii_type = pii_info.get("pii_type")
                    if pii_type:
                        col["pii"] = pii_type  # "Sensitive" or "NonSensitive"
                    else:
                        del col["pii"]

        # Trim profile metrics (remove derivable/rarely-used fields)
        for table_profile in profile.get("tables", {}).values():
            # Remove table-level redundant fields
            table_metrics = table_profile.get("table_metrics", {})
            if "sampling_enabled" in table_metrics:
                del table_metrics["sampling_enabled"]

            # Trim column metrics
            for col_name, metrics in table_profile.get("column_metrics", {}).items():
                if not isinstance(metrics, dict):
                    continue

                # Remove derivable fields
                if "iqr" in metrics:
                    del metrics["iqr"]  # Derivable: Q3 - Q1
                if "duplicate_count" in metrics:
                    del metrics["duplicate_count"]  # Derivable: count - distinct_count

                # Remove rarely-used advanced fields
                if "non_parametric_skew" in metrics:
                    del metrics["non_parametric_skew"]

                # Remove type from metrics (already in schema)
                if "type" in metrics:
                    del metrics["type"]

    @staticmethod
    def filter_pii_from_results(
        results: list[Dict[str, Any]],
        schema_context: Dict[str, Any],
        filter_level: str
    ) -> list[Dict[str, Any]]:
        """Filter PII columns from query results based on filter level.

        Args:
            results: List of row dicts from query execution
            schema_context: Schema context with PII detection metadata
            filter_level: "strict" (all PII), "moderate" (sensitive only), or "none"

        Returns:
            Filtered results with PII values masked as "***REDACTED***"
        """
        if not results or filter_level == "none" or not schema_context:
            return results

        # Identify PII columns using shared helper
        pii_columns = PIIFilterService._identify_pii_columns(schema_context, filter_level)

        if not pii_columns:
            return results

        # Mask PII values in results
        filtered_results = []
        for row in results:
            filtered_row = {}
            for col_name, value in row.items():
                if col_name in pii_columns:
                    filtered_row[col_name] = "***REDACTED***"
                else:
                    filtered_row[col_name] = value
            filtered_results.append(filtered_row)

        log.info(
            "Filtered %d PII columns from query results (level=%s): %s",
            len(pii_columns), filter_level, sorted(pii_columns)
        )

        return filtered_results
