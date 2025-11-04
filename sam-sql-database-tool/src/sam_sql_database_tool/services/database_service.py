"""Service for handling SQL database operations with parallel processing."""

from contextlib import contextmanager
from typing import List, Dict, Any, Generator, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import threading

from sqlalchemy.engine import Engine, Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import inspect, text, select, func, distinct, Table, MetaData

import sqlalchemy as sa
import yaml
import logging
log = logging.getLogger(__name__)


class DatabaseService:
    """A generic service for handling SQL database operations."""

    def __init__(self, connection_string: str, cache_ttl_seconds: int = 3600):
        """Initialize the database service.

        Args:
            connection_string: Database connection string.
            cache_ttl_seconds: Time-to-live for schema cache in seconds (default: 3600 = 1 hour).
        """
        self.connection_string = connection_string
        self.engine: Optional[Engine] = None
        self._schema_cache: Optional[str] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._refresh_in_progress = False
        self._refresh_lock = threading.Lock()
        self._max_enum_cardinality: Optional[int] = None
        self._sample_size: Optional[int] = None

        try:
            self.engine = self._create_engine()
            log.info(
                "Database engine created successfully for dialect: %s",
                self.engine.dialect.name,
            )
        except Exception as e:
            log.exception("Failed to create database engine: %s", e)
            raise

    def _is_cache_valid(self) -> bool:
        """Check if the schema cache is still valid."""
        if self._schema_cache is None or self._cache_timestamp is None:
            return False
        return datetime.now() - self._cache_timestamp < self._cache_ttl

    def clear_cache(self) -> None:
        """Manually clear the schema cache."""
        self._schema_cache = None
        self._cache_timestamp = None
        log.debug("Schema cache cleared")

    def _refresh_schema_background(self, max_enum_cardinality: int, sample_size: int) -> None:
        """Background task to refresh expired schema cache."""
        try:
            log.debug("Background schema refresh started...")
            schema = self._compute_schema(max_enum_cardinality, sample_size)

            with self._refresh_lock:
                self._schema_cache = schema
                self._cache_timestamp = datetime.now()
                self._refresh_in_progress = False

            log.debug("Background schema refresh completed")
        except Exception as e:
            log.exception("Background schema refresh failed: %s", e)
            with self._refresh_lock:
                self._refresh_in_progress = False

    def _create_engine(self) -> Engine:
        """Creates a SQLAlchemy engine with connection pooling for parallel operations."""
        return sa.create_engine(
            self.connection_string,
            pool_size=10,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
        )

    def close(self) -> None:
        """Dispose of the engine and its connection pool."""
        if self.engine:
            try:
                self.engine.dispose()
                log.info("Database engine disposed successfully.")
            except Exception as e:
                log.exception("Error disposing database engine: %s", e)
        else:
            log.warning("No database engine to dispose.")

    @contextmanager
    def get_connection(self) -> Generator[Connection, None, None]:
        """Get a database connection from the pool with automatic transaction management."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized.")

        try:
            with self.engine.begin() as connection:
                yield connection
        except SQLAlchemyError as e:
            log.exception("Database connection error: %s", str(e))
            raise

    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute a SQL query."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized.")
        try:
            with self.get_connection() as conn:
                result = conn.execute(text(query))
                if result.returns_rows:
                    return [dict(row) for row in result.mappings()]
                else:
                    log.info(
                        "Query executed successfully, affected rows: %s",
                        result.rowcount,
                    )
                    return [
                        {
                            "status": "success",
                            "affected_rows": (
                                result.rowcount if result.rowcount is not None else 0
                            ),
                        }
                    ]
        except SQLAlchemyError as e:
            log.exception("Query execution error: %s", str(e))
            raise

    def get_tables(self) -> List[str]:
        """Get all table names in the database."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized.")
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Get detailed column information for a table."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized.")
        inspector = inspect(self.engine)
        return inspector.get_columns(table_name)

    def get_primary_keys(self, table_name: str) -> List[str]:
        """Get primary key columns for a table."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized.")
        inspector = inspect(self.engine)
        pk_constraint = inspector.get_pk_constraint(table_name)
        return pk_constraint["constrained_columns"] if pk_constraint else []

    def get_foreign_keys(self, table_name: str) -> List[Dict[str, Any]]:
        """Get foreign key relationships for a table."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized.")
        inspector = inspect(self.engine)
        return inspector.get_foreign_keys(table_name)

    def get_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        """Get indexes for a table."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized.")
        inspector = inspect(self.engine)
        return inspector.get_indexes(table_name)

    def get_table_sample(self, table_name: str, sample_rows: int = 100) -> List[Dict[str, Any]]:
        """Get sample rows from a table efficiently."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized.")

        try:
            metadata = MetaData()
            table = Table(table_name, metadata, autoload_with=self.engine)
            query = select(table).limit(sample_rows)

            with self.get_connection() as conn:
                result = conn.execute(query)
                return [dict(row._mapping) for row in result]
        except Exception as e:
            log.exception("Error sampling table %s: %s", table_name, e)
            return []

    def _get_complete_enum_values(self, table_name: str, col_name: str, limit: int = 50) -> List[Any]:
        """Get all distinct values for an enum column."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized.")

        try:
            metadata = MetaData()
            table = Table(table_name, metadata, autoload_with=self.engine)
            col = table.c[col_name]

            query = select(distinct(col)).where(col.is_not(None)).order_by(col).limit(limit)

            with self.get_connection() as conn:
                result = conn.execute(query)
                return [row[0] for row in result]
        except Exception as e:
            log.error("Error getting distinct values for %s.%s: %s", table_name, col_name, e)
            return []

    def _get_complete_enum_values_batch(
        self,
        enum_columns: List[Tuple[str, str]]
    ) -> Dict[Tuple[str, str], List[Any]]:
        """Get all distinct values for multiple enum columns in parallel."""
        results = {}

        if not enum_columns:
            return results

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_col = {
                executor.submit(self._get_complete_enum_values, table_name, col_name): (table_name, col_name)
                for table_name, col_name in enum_columns
            }

            for future in as_completed(future_to_col):
                table_name, col_name = future_to_col[future]
                try:
                    values = future.result()
                    results[(table_name, col_name)] = values
                except Exception as e:
                    log.error("Error fetching enum values for %s.%s: %s", table_name, col_name, e)
                    results[(table_name, col_name)] = []

        return results

    def _get_approximate_row_count(self, table_name: str) -> Optional[int]:
        """Get approximate row count for a table."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized.")

        try:
            if self.engine.dialect.name == 'postgresql':
                query = text(
                    "SELECT reltuples::bigint AS estimate "
                    "FROM pg_class "
                    "WHERE relname = :table_name"
                ).bindparams(table_name=table_name)
            else:
                query = text(
                    "SELECT table_rows "
                    "FROM information_schema.tables "
                    "WHERE table_name = :table_name "
                    "AND table_schema = DATABASE()"
                ).bindparams(table_name=table_name)

            with self.get_connection() as conn:
                result = conn.execute(query).first()
                if result:
                    count = result[0]
                    return int(count) if count is not None else None
                return None
        except Exception as e:
            log.debug("Could not get row count for %s: %s", table_name, e)
            return None

    def _looks_like_enum_column(self, column_name: str) -> bool:
        """Check if a column name suggests it might be an enum."""
        enum_patterns = [
            'status', 'state', 'type', 'kind', 'category',
            'level', 'priority', 'role', 'gender', 'country',
            'region', 'phase', 'stage', 'mode', 'flag', 'method',
            'payment', 'fulfillment', 'delivery', 'shipping',
            'visibility', 'access', 'permission', 'scope'
        ]
        name_lower = column_name.lower()
        return any(pattern in name_lower for pattern in enum_patterns)

    def _format_foreign_keys(self, foreign_keys: List[Dict[str, Any]]) -> List[str]:
        """Format foreign keys in a compact, readable format."""
        formatted = []
        for fk in foreign_keys:
            constrained = ', '.join(fk.get('constrained_columns', []))
            referred_table = fk.get('referred_table', 'unknown')
            referred = ', '.join(fk.get('referred_columns', []))
            formatted.append(f"{constrained} → {referred_table}.{referred}")
        return formatted

    def _process_table(
        self,
        table_name: str,
        max_enum_cardinality: int,
        sample_size: int
    ) -> Dict[str, Any]:
        """Process a single table - designed to run in parallel."""
        try:
            log.debug("Processing table: %s", table_name)

            columns = self.get_columns(table_name)
            pks = self.get_primary_keys(table_name)
            fks = self.get_foreign_keys(table_name)
            indexes = self.get_indexes(table_name)

            sample_rows = self.get_table_sample(table_name, sample_rows=sample_size)
            row_count = self._get_approximate_row_count(table_name)

            table_info = {
                'columns': {},
                '_sample_data': sample_rows,
                '_enum_candidates': []
            }

            if pks:
                table_info['primary_keys'] = pks

            if fks:
                table_info['foreign_keys'] = self._format_foreign_keys(fks)

            if row_count:
                table_info['row_count'] = row_count

            indexed_columns = set()
            for idx in indexes:
                indexed_columns.update(idx.get('column_names', []))

            for col in columns:
                col_name = col['name']
                col_type = str(col['type'])

                col_info = {'type': col_type}

                if not col.get('nullable', True):
                    col_info['nullable'] = False

                if col_name in indexed_columns:
                    col_info['indexed'] = True

                if sample_rows:
                    sample_values = [
                        row[col_name] for row in sample_rows
                        if row.get(col_name) is not None
                    ]

                    try:
                        unique_values = list(set(sample_values))
                    except TypeError:
                        continue

                    cardinality = len(unique_values)
                    total_samples = len(sample_values)

                    cardinality_ratio = cardinality / total_samples if total_samples > 0 else 1

                    is_string_type = col_type.upper().startswith(('VARCHAR', 'CHAR', 'TEXT', 'ENUM'))
                    looks_like_enum = self._looks_like_enum_column(col_name)
                    has_low_cardinality = cardinality_ratio < 0.3

                    is_likely_enum = (
                        cardinality > 1 and
                        cardinality <= max_enum_cardinality and
                        is_string_type and
                        (looks_like_enum or has_low_cardinality)
                    )

                    if is_likely_enum:
                        if cardinality > 10:
                            table_info['_enum_candidates'].append(col_name)
                            col_info['_fetch_enum'] = True
                            col_info['_sample_values'] = unique_values
                        else:
                            col_info['enum'] = sorted(str(v) for v in unique_values)
                    elif cardinality > 2 and cardinality <= 5:
                        col_info['examples'] = [str(v) for v in sample_values[:3]]

                table_info['columns'][col_name] = col_info

            return table_info

        except Exception as e:
            log.exception("Error processing table %s: %s", table_name, e)
            return {'columns': {}, '_error': str(e)}

    def _compute_schema(self, max_enum_cardinality: int, sample_size: int) -> str:
        """Compute schema without caching logic."""
        log.info("Starting schema detection...")
        tables = self.get_tables()
        log.debug("Processing %d tables in parallel with 5 workers...", len(tables))
        schema = {}

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_table = {
                executor.submit(self._process_table, table_name, max_enum_cardinality, sample_size): table_name
                for table_name in tables
            }

            for future in as_completed(future_to_table):
                table_name = future_to_table[future]
                try:
                    table_info = future.result()
                    schema[table_name] = table_info
                except Exception as e:
                    log.error("Failed to process table %s: %s", table_name, e)
                    schema[table_name] = {'columns': {}, '_error': str(e)}

        enum_columns_to_fetch = []
        for table_name, table_info in schema.items():
            for col_name in table_info.get('_enum_candidates', []):
                enum_columns_to_fetch.append((table_name, col_name))

        if enum_columns_to_fetch:
            log.debug("Fetching complete enum values for %d columns in parallel...", len(enum_columns_to_fetch))
            enum_values = self._get_complete_enum_values_batch(enum_columns_to_fetch)
        else:
            enum_values = {}

        for table_name, table_info in schema.items():
            for col_name, col_info in table_info['columns'].items():
                if col_info.get('_fetch_enum'):
                    complete_values = enum_values.get((table_name, col_name))
                    if complete_values:
                        col_info['enum'] = sorted(str(v) for v in complete_values)
                    else:
                        sample_vals = col_info.get('_sample_values', [])
                        col_info['enum'] = sorted(str(v) for v in sample_vals)

                    del col_info['_fetch_enum']
                    if '_sample_values' in col_info:
                        del col_info['_sample_values']

            if '_sample_data' in table_info:
                del table_info['_sample_data']
            if '_enum_candidates' in table_info:
                del table_info['_enum_candidates']

        log.info("Schema detection complete for %d tables", len(tables))

        try:
            schema_yaml = yaml.dump(
                schema,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                width=120
            )
        except Exception as e:
            log.error("Failed to dump schema to YAML: %s", e)
            summary_lines = []
            for table_name, table_data in schema.items():
                cols = table_data.get('columns', {})
                col_str = ", ".join([f"{cn}: {ci.get('type', 'UNKNOWN')}" for cn, ci in cols.items()])
                summary_lines.append(f"{table_name}: {col_str}")
            schema_yaml = "\n".join(summary_lines)

        return schema_yaml

    def get_optimized_schema_for_llm(self, max_enum_cardinality: int = 100, sample_size: int = 100) -> str:
        """Get optimized database schema summary for LLM context.

        Args:
            max_enum_cardinality: Maximum distinct values to consider as enum (default: 100)
            sample_size: Number of rows to sample per table (default: 100)

        Returns:
            YAML string with schema information optimized for LLM consumption
        """
        if not self.engine:
            raise RuntimeError("Database engine is not initialized.")

        self._max_enum_cardinality = max_enum_cardinality
        self._sample_size = sample_size

        if self._is_cache_valid():
            log.debug("Using cached schema (age: %s)", datetime.now() - self._cache_timestamp)
            return self._schema_cache

        cache_expired = self._schema_cache is not None

        if cache_expired and not self._refresh_in_progress:
            with self._refresh_lock:
                if not self._refresh_in_progress:
                    self._refresh_in_progress = True
                    log.debug("Cache expired. Starting background refresh, serving stale cache...")
                    refresh_thread = threading.Thread(
                        target=self._refresh_schema_background,
                        args=(max_enum_cardinality, sample_size),
                        daemon=True
                    )
                    refresh_thread.start()

            return self._schema_cache

        schema_yaml = self._compute_schema(max_enum_cardinality, sample_size)

        self._schema_cache = schema_yaml
        self._cache_timestamp = datetime.now()
        log.debug("Schema cached with TTL of %s", self._cache_ttl)

        return schema_yaml
