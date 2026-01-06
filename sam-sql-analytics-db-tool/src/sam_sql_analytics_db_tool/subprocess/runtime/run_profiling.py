"""
Database profiling using OpenMetadata metrics directly (no workflows).

Uses OpenMetadata's production-grade profiling metrics as a library.
Database-agnostic - works for PostgreSQL, MySQL, Oracle, Snowflake, MSSQL, SQLite.

Metrics computed:
- Universal: count, null_count, distinct_count, unique_count, ratios
- Numeric: min, max, mean, sum, stddev, median, quartiles, IQR, skewness, histogram
- String: min_length, max_length

Supported databases:
- PostgreSQL, MySQL, Oracle, Snowflake, MSSQL, SQLite
- OpenMetadata metrics automatically handle dialect-specific SQL generation
"""

import json
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, date

from connection_14 import DBFactory14
from sqlalchemy import MetaData, Table, Column, select, text, func, and_, case
from sqlalchemy import inspect as sqla_inspect
from sqlalchemy.engine import Engine
import math

# Feature flag - set to False to disable native TABLESAMPLE and use simple fallback
USE_NATIVE_SAMPLING = True


def create_sample_table(engine: Engine, table: Table, row_count: int, sample_percentage: float = 10.0):
    """
    Create a sampled table using database-native sampling where available.
    Extracted from OpenMetadata sampler patterns (PostgresSampler, MssqlSampler).

    Sampling methods by database:
    - PostgreSQL: TABLESAMPLE BERNOULLI(%) - true random sampling
    - MSSQL: TABLESAMPLE ... PERCENT
    - MySQL: ORDER BY RAND() + LIMIT (no native TABLESAMPLE)
    - SQLite: ORDER BY RANDOM() + LIMIT
    - Others: ORDER BY RANDOM() + LIMIT (universal fallback)

    Args:
        engine: Database engine
        table: SQLAlchemy Table object
        row_count: Total rows in table (for adaptive sizing)
        sample_percentage: Target percentage (default 10%)

    Returns:
        Sampled table (subquery/alias) or original table if disabled/fails
    """
    if not USE_NATIVE_SAMPLING:
        return table  # Feature disabled

    dialect_name = engine.dialect.name

    try:
        # Adaptive sampling: percentage with min/max bounds
        min_rows = 1000
        max_rows = 100000
        target_rows = int(row_count * (sample_percentage / 100))
        actual_rows = max(min_rows, min(target_rows, max_rows))

        # Cap percentage at 100% (for small tables where actual_rows > row_count)
        actual_pct = (actual_rows / row_count * 100) if row_count > 0 else sample_percentage
        actual_pct = min(actual_pct, 100.0)  # CRITICAL: TABLESAMPLE requires 0-100%

        # PostgreSQL - native TABLESAMPLE BERNOULLI
        if dialect_name == 'postgresql':
            return table.tablesample(func.bernoulli(actual_pct))

        # MSSQL - native TABLESAMPLE PERCENT
        elif dialect_name == 'mssql':
            return table.tablesample(text(f"{actual_pct} PERCENT"))

        # MySQL - ORDER BY RAND() + LIMIT (MySQL uses RAND(), others use RANDOM())
        elif dialect_name == 'mysql':
            sample_query = select(table).order_by(func.rand()).limit(actual_rows)
            return sample_query.cte('sample')

        # SQLite and all other databases - ORDER BY RANDOM() + LIMIT
        else:
            sample_query = select(table).order_by(func.random()).limit(actual_rows)
            return sample_query.cte('sample')

    except Exception:
        # If sampling fails, return original table (full scan)
        return table


def get_row_count(engine: Engine, table: Table, table_name: str) -> int:
    """
    Get table row count - uses fast approximate methods where available.

    Approximate methods (instant):
    - PostgreSQL: pg_class.reltuples
    - MySQL: information_schema.table_rows

    Fallback: COUNT(*) for other databases (Oracle, Snowflake, SQLite, MSSQL)
    """
    dialect_name = engine.dialect.name

    try:
        # PostgreSQL - approximate from pg_class (instant, ~95% accurate)
        if dialect_name == 'postgresql':
            query = text("SELECT reltuples::bigint FROM pg_class WHERE relname = :table_name")
            with engine.connect() as conn:
                result = conn.execute(query, {"table_name": table_name}).scalar()
                if result is not None and result > 0:
                    return int(result)

        # MySQL - approximate from information_schema (instant, updated on ANALYZE)
        elif dialect_name == 'mysql':
            query = text("""
                SELECT table_rows
                FROM information_schema.tables
                WHERE table_name = :table_name
                AND table_schema = DATABASE()
            """)
            with engine.connect() as conn:
                result = conn.execute(query, {"table_name": table_name}).scalar()
                if result is not None:
                    return int(result)

    except Exception:
        pass  # Fall through to COUNT(*)

    # Fallback: exact COUNT(*) for databases without fast estimates
    # (Oracle, Snowflake, SQLite, MSSQL, or if approximate failed)
    try:
        with engine.connect() as conn:
            result = conn.execute(select(func.count()).select_from(table)).scalar()
            return int(result) if result is not None else 0
    except Exception:
        return 0  # Last resort fallback


def compute_histogram_bins(res_min: float, res_max: float, res_iqr: float, res_row_count: float):
    """
    Compute histogram bins using OpenMetadata's Freedman-Diaconis rule.
    Extracted from metadata.profiler.metrics.hybrid.histogram.Histogram

    Returns: (num_bins, bin_width)
    """
    max_bin_count = 15  # Cap at 15 bins for LLM context (OpenMetadata uses 100)

    if res_iqr is not None and res_iqr > 0:
        # Freedman-Diaconis rule: bin_width = 2 * IQR * n^(-1/3)
        bin_width = 2 * res_iqr * (res_row_count ** (-1 / 3))
        num_bins = math.ceil((res_max - res_min) / bin_width)
    else:
        # Sturge's rule fallback when IQR is None or 0
        num_bins = int(math.ceil(math.log2(res_row_count) + 1))
        bin_width = (res_max - res_min) / num_bins if num_bins > 0 else 1

    # Cap at max_bin_count
    if num_bins > max_bin_count:
        num_bins = max_bin_count
        bin_width = (res_max - res_min) / num_bins

    return num_bins, bin_width


def format_bin_label(lower: float, upper: float = None) -> str:
    """Format histogram bin labels (e.g., '10 to 20', '90 and up')"""
    lower_str = f"{lower:.2f}" if isinstance(lower, float) else str(lower)
    if upper is None:
        return f"{lower_str} and up"
    upper_str = f"{upper:.2f}" if isinstance(upper, float) else str(upper)
    return f"{lower_str} to {upper_str}"


def compute_histogram(engine: Engine, sample_table, col: Column,
                      min_val: float, max_val: float,
                      iqr_val: float, row_count: int) -> dict:
    """
    Compute histogram for a numeric column using pure SQL (no session needed).
    Builds CASE statements for binning similar to OpenMetadata's Histogram.fn()

    Args:
        engine: Database engine
        sample_table: Sampled table to query
        col: Column to profile
        min_val, max_val: Column min/max from previous metrics
        iqr_val: Inter-quartile range from previous metrics
        row_count: Approximate table row count

    Returns:
        {"boundaries": [...], "frequencies": [...]} or None if failed
    """
    try:
        # Compute bins using OpenMetadata's algorithm
        num_bins, bin_width = compute_histogram_bins(min_val, max_val, iqr_val, row_count)

        if num_bins == 0 or min_val == max_val:
            return None  # Single value or empty

        # Build CASE statements for each bin
        case_stmts = []
        bin_labels = []

        starting_bound = min_val
        for bin_num in range(num_bins):
            ending_bound = starting_bound + bin_width

            if bin_num < num_bins - 1:
                # Normal bin: lower <= col < upper
                condition = and_(col >= starting_bound, col < ending_bound)
                label = format_bin_label(starting_bound, ending_bound)
            else:
                # Last bin: col >= lower (no upper limit)
                condition = col >= starting_bound
                label = format_bin_label(starting_bound)

            case_stmts.append(func.count(case([(condition, col)])))
            bin_labels.append(label)
            starting_bound = ending_bound

        # Execute histogram query
        with engine.connect() as conn:
            result_row = conn.execute(
                select(*case_stmts).select_from(sample_table)
            ).first()

            if result_row:
                return {
                    "boundaries": bin_labels,
                    "frequencies": list(result_row)
                }

        return None

    except Exception:
        return None  # Histogram is optional, fail gracefully


def json_serialize(obj):
    """Convert non-JSON-serializable types to JSON-compatible types."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    raise TypeError(f"Type {type(obj)} not serializable")


def profile_table(engine, table_name: str, schema: str) -> dict:
    """
    Profile a single table using OpenMetadata metrics.
    Returns both metrics and warnings about metric computation failures.
    """
    warnings = []

    # Import OpenMetadata static metrics (have .fn() returning SQL)
    from metadata.profiler.metrics.static.min import Min
    from metadata.profiler.metrics.static.max import Max
    from metadata.profiler.metrics.static.mean import Mean
    from metadata.profiler.metrics.static.sum import Sum
    from metadata.profiler.metrics.static.null_count import NullCount
    from metadata.profiler.metrics.static.distinct_count import DistinctCount
    from metadata.profiler.metrics.static.stddev import StdDev
    from metadata.profiler.metrics.static.max_length import MaxLength
    from metadata.profiler.metrics.static.min_length import MinLength
    from metadata.profiler.metrics.static.count import Count

    # Import composed metrics (compute in Python from previous results)
    from metadata.profiler.metrics.composed.null_ratio import NullRatio
    from metadata.profiler.metrics.composed.distinct_ratio import DistinctRatio
    from metadata.profiler.metrics.composed.duplicate_count import DuplicateCount

    # Import window metrics (percentiles)
    from metadata.profiler.metrics.window.median import Median
    from metadata.profiler.metrics.window.first_quartile import FirstQuartile
    from metadata.profiler.metrics.window.third_quartile import ThirdQuartile
    from metadata.profiler.metrics.composed.iqr import InterQuartileRange

    # Import advanced metrics
    from metadata.profiler.metrics.composed.non_parametric_skew import NonParametricSkew

    inspector = sqla_inspect(engine)

    # Get column metadata
    column_info = inspector.get_columns(table_name, schema=schema)

    # Create SQLAlchemy Table object for querying
    metadata = MetaData()
    table_columns = []
    for col in column_info:
        table_columns.append(Column(col['name'], col['type']))

    table = Table(table_name, metadata, *table_columns, schema=schema)

    profile_data = {
        "table_name": table_name,
        "schema": schema,
        "table_metrics": {},
        "column_metrics": {},
    }

    # Get row count (fast approximate for Postgres/MySQL, COUNT(*) fallback for others)
    row_count = get_row_count(engine, table, table_name)
    profile_data["table_metrics"]["row_count"] = row_count

    # Create sampled table for column metrics (avoids full table scans)
    sample_table = create_sample_table(engine, table, row_count, sample_percentage=10.0)
    profile_data["table_metrics"]["sampling_enabled"] = (sample_table != table)

    # Compute column-level metrics on SAMPLE
    for col_info in column_info:
        col_name = col_info['name']
        # Use column from sample_table (not original table)
        col = sample_table.c[col_name]
        col_type_str = str(col_info['type']).lower()

        col_metrics = {
            "type": str(col_info['type']),
            "nullable": col_info.get('nullable', True),
        }

        # Determine column type category
        is_numeric = any(t in col_type_str for t in ['int', 'float', 'numeric', 'decimal', 'double'])
        is_string = any(t in col_type_str for t in ['char', 'text', 'string', 'varchar'])

        # Build metrics list - ONLY SQL metrics that have .fn() returning SQL expressions
        # ComposedMetrics and QueryMetrics are computed separately
        sql_metrics = [
            # Universal metrics (StaticMetric - have .fn())
            ("count", Count(col=col)),
            ("null_count", NullCount(col=col)),
            ("distinct_count", DistinctCount(col=col)),
            # NOTE: unique_count is QueryMetric (requires session) - skip for now
        ]

        if is_numeric:
            # Numeric statistics (StaticMetric)
            sql_metrics.extend([
                ("min", Min(col=col)),
                ("max", Max(col=col)),
                ("mean", Mean(col=col)),
                ("sum", Sum(col=col)),
                ("stddev", StdDev(col=col)),
            ])

            # Percentiles and quartiles (WindowMetric)
            sql_metrics.extend([
                ("median", Median(col=col)),
                ("first_quartile", FirstQuartile(col=col)),
                ("third_quartile", ThirdQuartile(col=col)),
            ])

        if is_string:
            # String metrics (StaticMetric)
            sql_metrics.extend([
                ("min_length", MinLength(col=col)),
                ("max_length", MaxLength(col=col)),
            ])

        # Batch execute SQL metrics in a single query (OpenMetadata pattern)
        with engine.connect() as conn:
            try:
                # Build list of SQL expressions from SQL metrics only
                sql_exprs = []
                metric_names = []
                for metric_name, metric in sql_metrics:
                    try:
                        sql_expr = metric.fn()
                        if sql_expr is not None:
                            sql_exprs.append(sql_expr)
                            metric_names.append(metric_name)
                    except Exception as e:
                        # Skip metrics that fail to build SQL expression
                        warnings.append(f"Metric '{metric_name}' failed to build SQL for {table_name}.{col_name}: {str(e)}")

                # Execute all SQL metrics in a single SELECT statement
                if sql_exprs:
                    result_row = conn.execute(
                        select(*sql_exprs).select_from(sample_table)
                    ).first()

                    # Map results back to metric names
                    if result_row:
                        for idx, metric_name in enumerate(metric_names):
                            col_metrics[metric_name] = result_row[idx]

            except Exception as e:
                # If batch execution fails entirely, log and continue
                warnings.append(f"Batch metric execution failed for {table_name}.{col_name}: {str(e)}")

        # Compute composed metrics (Python-based, use results from SQL metrics)
        # These metrics expect OpenMetadata key names (e.g., "valuesCount" not "count")
        try:
            # Build result dict with OpenMetadata naming for composed metrics
            om_results = {
                Count.name(): col_metrics.get("count"),
                NullCount.name(): col_metrics.get("null_count"),
                DistinctCount.name(): col_metrics.get("distinct_count"),
            }

            # Add numeric metrics for IQR/skew computation
            if is_numeric:
                om_results[Mean.name()] = col_metrics.get("mean")
                om_results[StdDev.name()] = col_metrics.get("stddev")
                om_results[Median.name()] = col_metrics.get("median")
                om_results[FirstQuartile.name()] = col_metrics.get("first_quartile")
                om_results[ThirdQuartile.name()] = col_metrics.get("third_quartile")

            # Null ratio = null_count / (count + null_count)
            null_ratio = NullRatio(col=col)
            col_metrics["null_ratio"] = null_ratio.fn(om_results)

            # Distinct ratio = distinct_count / count
            distinct_ratio = DistinctRatio(col=col)
            col_metrics["distinct_ratio"] = distinct_ratio.fn(om_results)

            # Duplicate count = count - distinct_count
            duplicate_count = DuplicateCount(col=col)
            col_metrics["duplicate_count"] = duplicate_count.fn(om_results)

            # IQR and non-parametric skew (numeric only)
            if is_numeric and col_metrics.get("first_quartile") and col_metrics.get("third_quartile"):
                iqr = InterQuartileRange(col=col)
                col_metrics["iqr"] = iqr.fn(om_results)

                non_param_skew = NonParametricSkew(col=col)
                col_metrics["non_parametric_skew"] = non_param_skew.fn(om_results)

        except Exception as e:
            warnings.append(f"Composed metrics computation failed for {table_name}.{col_name}: {str(e)}")

        # Compute histogram separately for numeric columns (needs min/max/iqr from batched results)
        if is_numeric and col_metrics.get("min") is not None and col_metrics.get("max") is not None:
            try:
                histogram_result = compute_histogram(
                    engine=engine,
                    sample_table=sample_table,
                    col=col,
                    min_val=float(col_metrics["min"]),
                    max_val=float(col_metrics["max"]),
                    iqr_val=float(col_metrics.get("iqr")) if col_metrics.get("iqr") is not None else None,
                    row_count=profile_data["table_metrics"].get("row_count", 1000)
                )
                if histogram_result:
                    col_metrics["histogram"] = histogram_result
            except Exception as e:
                warnings.append(f"Histogram computation failed for {table_name}.{col_name}: {str(e)}")

        profile_data["column_metrics"][col_name] = col_metrics

    # Add warnings if any occurred
    if warnings:
        profile_data["_warnings"] = warnings

    return profile_data


def profile_database(dsn: str) -> dict:
    """
    Profile all tables in database using OpenMetadata metrics.

    Returns:
        dict with:
        - tables: {table_name: {table_metrics, column_metrics, _warnings?}}
        - _summary: {total_tables, tables_with_warnings, tables_with_errors, total_warnings}
    """

    db = DBFactory14(dsn)
    inspector = sqla_inspect(db.engine)

    profile_results = {}
    summary = {
        "total_tables": 0,
        "tables_with_warnings": 0,
        "tables_with_errors": 0,
        "total_warnings": 0
    }

    # Get all tables
    for table_name in inspector.get_table_names():
        summary["total_tables"] += 1
        schema = inspector.default_schema_name

        try:
            table_profile = profile_table(db.engine, table_name, schema)
            profile_results[table_name] = table_profile

            # Track issues
            if table_profile.get("_warnings"):
                summary["tables_with_warnings"] += 1
                summary["total_warnings"] += len(table_profile["_warnings"])

        except Exception as e:
            profile_results[table_name] = {
                "_error": str(e),
                "_fatal": True,
                "table_name": table_name,
                "schema": schema,
            }
            summary["tables_with_errors"] += 1

    return {
        "tables": profile_results,
        "_summary": summary
    }


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: run_profiling.py <dsn>",
            file=sys.stderr
        )
        sys.exit(1)

    dsn = sys.argv[1]

    # Profile database using OpenMetadata metrics directly
    profile_data = profile_database(dsn)

    # Output as JSON (with custom serialization for Decimal, datetime, etc.)
    print(json.dumps(profile_data, default=json_serialize))


if __name__ == "__main__":
    main()
