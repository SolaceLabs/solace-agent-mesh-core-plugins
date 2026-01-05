# src/sam_sql_analytics_db_tool/subprocess/runtime/run_discovery.py
"""
Database schema discovery using SQLAlchemy Inspector + OpenMetadata PII detection.
Simple, database-agnostic approach without OpenMetadata workflows/server dependencies.

Features:
- Schema structure (tables, columns, types, constraints)
- Primary/foreign key relationships
- Index information
- PII detection on column names (OpenMetadata ColumnNameScanner)
- Enum values for low-cardinality string columns (≤50 distinct values)

Supported databases:
- PostgreSQL, MySQL, Oracle, Snowflake, MSSQL, SQLite
- Any database with SQLAlchemy support
"""

import json
import sys
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Tuple, List, Optional

from connection_14 import DBFactory14
from sqlalchemy import inspect as sqla_inspect
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# Thread-safe module-level NER scanner instance
# spaCy models are thread-safe for inference (shared across parallel threads)
# Initialize once at module load to prevent parallel download race condition
_NER_SCANNER = None

try:
    from metadata.pii.scanners.ner_scanner import NERScanner

    # Create scanner instance (triggers spaCy model download once, not 5x in parallel)
    _NER_SCANNER = NERScanner()
    log.info("NER scanner initialized at module load")
except (ImportError, ModuleNotFoundError):
    log.debug("NER scanner not available")
except Exception as e:
    log.warning("NER scanner initialization failed: %s", e)


def detect_pii_column_name(column_name: str) -> Dict[str, any]:
    """Detect PII in column names using OpenMetadata's ColumnNameScanner."""
    try:
        from metadata.pii.scanners.column_name_scanner import ColumnNameScanner

        scanner = ColumnNameScanner()
        result = scanner.scan(column_name)

        if result:
            # Extract tag name from FQN (e.g., "PII.Sensitive" -> "Sensitive")
            tag_name = result.tag_fqn.root.split('.')[-1] if hasattr(result.tag_fqn, 'root') else str(result.tag_fqn).split('.')[-1]
            return {
                "pii_detected": True,
                "pii_type": tag_name,
                "confidence": result.confidence
            }
    except (ImportError, ModuleNotFoundError) as e:
        # Expected: OpenMetadata PII scanners not installed
        log.debug(f"ColumnNameScanner not available: {e}")
    except AttributeError as e:
        # Possible API change in OpenMetadata
        log.warning(f"PII column name detection failed for '{column_name}' (possible API change): {e}")
    except Exception as e:
        # Unexpected error - log it for debugging
        log.error(f"Unexpected error in PII column name detection for '{column_name}': {type(e).__name__}: {e}")

    return {"pii_detected": False}


def get_column_sample(engine: Engine, table_name: str, column_name: str, limit: int = 100) -> Optional[List[any]]:
    """
    Extract randomized sample values from a column.
    Uses ORDER BY RANDOM() for database-agnostic randomization.
    """
    try:
        from sqlalchemy import MetaData, Table, select, func

        metadata = MetaData()
        table = Table(table_name, metadata, autoload_with=engine)
        col = table.c[column_name]

        # Randomize using func.random() - maps to RANDOM() (Postgres/SQLite), RAND() (MySQL), etc.
        query = select(col).where(col.is_not(None)).order_by(func.random()).limit(limit)

        with engine.connect() as conn:
            result = conn.execute(query)
            return [row[0] for row in result if row[0] is not None]
    except Exception:
        # Fallback to non-random if ORDER BY RANDOM() not supported
        try:
            query_fallback = select(col).where(col.is_not(None)).limit(limit)
            with engine.connect() as conn:
                result = conn.execute(query_fallback)
                return [row[0] for row in result if row[0] is not None]
        except Exception:
            return None


def detect_pii_from_data(column_name: str, sample_data: List[any]) -> Dict[str, any]:
    """
    Detect PII by analyzing actual column data using NER scanner.
    Uses NLP to identify emails, SSNs, names, etc. in actual values.
    """
    if not sample_data:
        log.debug(f"No sample data for '{column_name}', skipping PII detection")
        return {"pii_detected": False}

    if _NER_SCANNER is None:
        return {"pii_detected": False}

    try:
        # Convert sample data to strings
        sample_strings = [str(val) for val in sample_data[:100] if val]

        if not sample_strings:
            log.debug(f"No non-null strings in sample data for '{column_name}'")
            return {"pii_detected": False}

        log.info(f"Running NER scanner on '{column_name}' with {len(sample_strings)} samples")
        log.debug(f"Sample preview for '{column_name}': {sample_strings[:3]}")

        # Use module-level scanner instance (thread-safe for concurrent inference)
        result = _NER_SCANNER.scan(sample_strings)

        log.info(f"NER scan result for '{column_name}': {result}")

        if result:
            # Extract detected PII type
            tag_name = result.tag_fqn.root.split('.')[-1] if hasattr(result.tag_fqn, 'root') else str(result.tag_fqn).split('.')[-1]
            log.info(f"✓ PII detected in '{column_name}': type={tag_name}, confidence={result.confidence}")
            return {
                "pii_detected": True,
                "pii_type": tag_name,
                "confidence": result.confidence,
                "detection_method": "data_analysis"
            }
        else:
            log.info(f"✗ No PII detected in '{column_name}' via NER scanner (result=None)")

    except (ImportError, ModuleNotFoundError) as e:
        # Expected: NER scanner or NLP models not installed
        log.warning(f"NERScanner import failed for '{column_name}': {e}")
    except AttributeError as e:
        # Possible API change in OpenMetadata or malformed result
        log.warning(f"PII data detection failed for '{column_name}' (possible API change): {e}")
    except Exception as e:
        # Unexpected error during NER scanning - log it for debugging
        log.error(f"Unexpected error in PII data detection for '{column_name}': {type(e).__name__}: {e}", exc_info=True)

    return {"pii_detected": False}


def process_table(engine: Engine, inspector, table_name: str) -> Dict[str, any]:
    """
    Process a single table - designed to run in parallel.
    Extracts all metadata including enum values.
    Returns both data and warnings about non-critical failures.
    """
    warnings = []

    try:
        # Get column information
        columns = inspector.get_columns(table_name)

        # Get primary keys
        pk_constraint = inspector.get_pk_constraint(table_name)
        primary_keys = pk_constraint.get('constrained_columns', []) if pk_constraint else []

        # Get foreign keys
        foreign_keys = []
        for fk in inspector.get_foreign_keys(table_name):
            foreign_keys.append({
                'columns': fk.get('constrained_columns', []),
                'referred_table': fk.get('referred_table'),
                'referred_columns': fk.get('referred_columns', []),
            })

        # Get indexes
        indexes = []
        try:
            for idx in inspector.get_indexes(table_name):
                indexes.append({
                    'name': idx.get('name'),
                    'columns': idx.get('column_names', []),
                    'unique': idx.get('unique', False),
                })
        except Exception:
            pass  # Some databases may not support index introspection

        # Build column metadata with PII detection and enum values
        column_metadata = []
        for col in columns:
            col_meta = {
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
            }

            # Add default if present
            if col.get("default") is not None:
                col_meta["default"] = str(col["default"])

            # PII detection: start with column name
            pii_info = detect_pii_column_name(col["name"])
            if pii_info["pii_detected"]:
                col_meta["pii"] = pii_info

            # Extract sample data for string columns (for enum/PII detection)
            col_type_str = str(col["type"]).lower()
            is_string = any(t in col_type_str for t in ['char', 'text', 'string', 'varchar', 'enum'])

            if is_string:
                try:
                    sample_data = get_column_sample(engine, table_name, col["name"], limit=100)

                    # If name-based PII detection didn't find anything, try data-based
                    if not col_meta.get("pii") and sample_data:
                        pii_info_data = detect_pii_from_data(col["name"], sample_data)
                        if pii_info_data["pii_detected"]:
                            col_meta["pii"] = pii_info_data

                    # Extract enum values from sample if low cardinality
                    if sample_data:
                        try:
                            unique_values = list(set(str(v) for v in sample_data))
                            if len(unique_values) <= 50:
                                col_meta["enum_values"] = sorted(unique_values)
                        except Exception as e:
                            warnings.append(f"Enum extraction failed for {table_name}.{col['name']}: {str(e)}")

                except Exception as e:
                    warnings.append(f"Sample data extraction failed for {table_name}.{col['name']}: {str(e)}")

            column_metadata.append(col_meta)

        result = {
            "columns": column_metadata,
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys,
            "indexes": indexes,
        }

        # Add warnings if any occurred
        if warnings:
            result["_warnings"] = warnings

        return result

    except Exception as e:
        return {"columns": [], "_error": str(e), "_fatal": True}


def discover_schema(dsn: str) -> Dict[str, any]:
    """
    Discover database schema using SQLAlchemy Inspector.
    Database-agnostic, works for all supported databases.
    Processes tables in parallel (5 workers) for performance.

    Returns:
        dict with:
        - tables: {table_name: {columns, pks, fks, indexes, _warnings?}}
        - _summary: {total_tables, tables_with_warnings, tables_with_errors}
    """

    db = DBFactory14(dsn)
    inspector = sqla_inspect(db.engine)

    tables = inspector.get_table_names()
    schema_data = {}
    summary = {
        "total_tables": len(tables),
        "tables_with_warnings": 0,
        "tables_with_errors": 0,
        "total_warnings": 0
    }

    # Process all tables in parallel
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_table = {
            executor.submit(process_table, db.engine, inspector, table_name): table_name
            for table_name in tables
        }

        for future in as_completed(future_to_table):
            table_name = future_to_table[future]
            try:
                table_data = future.result()
                schema_data[table_name] = table_data

                # Track issues for summary
                if table_data.get("_warnings"):
                    summary["tables_with_warnings"] += 1
                    summary["total_warnings"] += len(table_data["_warnings"])
                if table_data.get("_error"):
                    summary["tables_with_errors"] += 1

            except Exception as e:
                schema_data[table_name] = {"columns": [], "_error": str(e), "_fatal": True}
                summary["tables_with_errors"] += 1

    return {
        "tables": schema_data,
        "_summary": summary
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: run_discovery.py <dsn>", file=sys.stderr)
        sys.exit(1)

    dsn = sys.argv[1]

    # Discover schema using SQLAlchemy Inspector
    schema_data = discover_schema(dsn)

    # Output as JSON to stdout (do not log after this point!)
    print(json.dumps(schema_data))


if __name__ == "__main__":
    main()
