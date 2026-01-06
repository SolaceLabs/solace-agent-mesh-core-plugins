# src/sam_sql_analytics_db_tool/subprocess/runtime/run_combined.py
"""
Combined discovery + profiling in a single Python runtime.
Optimizes first-run performance by running both operations in parallel.

Usage: python run_combined.py <dsn>
"""

import json
import sys
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from datetime import datetime, date

# Import discovery and profiling functions
from run_discovery import discover_schema
from run_profiling import profile_database


def json_serialize(obj):
    """Convert non-JSON-serializable types to JSON-compatible types."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    raise TypeError(f"Type {type(obj)} not serializable")


def run_combined(dsn: str) -> dict:
    """
    Run both discovery and profiling in parallel.

    Args:
        dsn: Database connection string

    Returns:
        Combined result: {"discovery": {...}, "profiling": {...}}
    """
    results = {}

    # Run both operations in parallel (2 workers: 1 for discovery, 1 for profiling)
    with ThreadPoolExecutor(max_workers=2) as executor:
        # Submit both tasks (no sample_size needed - using percentage-based sampling)
        future_discovery = executor.submit(discover_schema, dsn)
        future_profiling = executor.submit(profile_database, dsn)

        # Collect results as they complete
        futures = {
            future_discovery: "discovery",
            future_profiling: "profiling"
        }

        for future in as_completed(futures):
            operation_name = futures[future]
            try:
                results[operation_name] = future.result()
            except Exception as e:
                # If one operation fails, still return partial results
                results[operation_name] = {
                    "_error": str(e),
                    "_fatal": True
                }

    return results


def main():
    if len(sys.argv) != 2:
        print("Usage: run_combined.py <dsn>", file=sys.stderr)
        sys.exit(1)

    dsn = sys.argv[1]

    # Run combined discovery + profiling in parallel
    result = run_combined(dsn)

    # Output JSON to stdout (last line - pip messages may appear above)
    print(json.dumps(result, default=json_serialize))


if __name__ == "__main__":
    main()
