# Dual Profiling Implementation Plan (FINAL)

**Date:** 2026-01-02
**Feature:** Historical profiling with dual snapshots (full + incremental) for comprehensive anomaly detection

---

## Executive Summary

**What:** Add historical profile tracking with two profiling modes:
- **Full profiling:** Random sample of entire dataset (for overall trends)
- **Incremental profiling:** Last 24h data only (for fresh anomalies)

**Why:** Enable LLM to detect anomalies, track trends, and compare data over time

**How:** Background daemon thread + artifact_service storage + three operations (query, list_profiles, get_profile)

**Fast Init:** Tool initializes in ~10 seconds with 300-row sample, then background thread runs comprehensive profiling

---

## Configuration Schema (User-Facing YAML)

```yaml
profiling:
  # Full dataset profiling
  full:
    enabled: true

  # Incremental profiling (last 24h only)
  incremental:
    enabled: true
    timestamp_columns:  # Optional: explicit mapping
      users: "created_at"
      orders: "order_date"
      products: null  # Skip incremental
    # If not specified, uses heuristic detection

  schedule:
    enabled: false  # Master switch for background profiling
    interval_days: 1  # Run every N days

  retention_days: 30  # Max 180
```

**Removed from config:** `sample_size` (unused by adaptive logic), `output_dir` (dead code)

**Internal (hardcoded):** Init uses 300 rows max, background uses adaptive 1K-100K

---

## Phase 1: Cleanup Dead Code (output_dir Removal)

### Files to Modify

**1. `subprocess/analytics_manager.py`**
- Remove `output_dir` parameter from `__init__()`
- Remove `self.output_dir` attribute
- Remove `self.output_dir.mkdir()`
- Remove `str(self.output_dir)` from subprocess args (lines 72, 87, 109)

**2. `subprocess/runtime/run_combined.py`**
- Line 72: `if len(sys.argv) != 3` → `!= 2`
- Line 74: Update usage: `<dsn> <output_dir>` → `<dsn>`
- Remove lines 77-82: `output_dir` parsing and `mkdir()`
- Line 33: `def run_combined(dsn, output_dir)` → `def run_combined(dsn)`
- Line 84: `run_combined(dsn, output_dir)` → `run_combined(dsn)`

**3. `subprocess/runtime/run_discovery.py`**
- Line 315: `!= 3` → `!= 2`
- Line 316: Update usage message
- Remove lines 320-322: `output_dir` parsing and `mkdir()`

**4. `subprocess/runtime/run_profiling.py`**
- Line 510: `!= 3` → `!= 2`
- Line 512: Update usage message
- Remove lines 518-520: `output_dir` parsing and `mkdir()`

**5. `tools.py`**
- Remove line 101: `output_dir = self.tool_config.get(...)`
- Update line 119: Remove `output_dir=output_dir` argument

**6. `config.yaml`**
- Remove line 27: `output_dir: "${OUTPUT_DIR, ./analytics_data}"`

---

## Phase 2: Fast Init with max_rows_override

### 2.1 Modify create_sample_table() to Support Override

**File:** `subprocess/runtime/run_profiling.py` (lines 33-90)

**CRITICAL FIX:** Override must bypass min_rows logic!

```python
def create_sample_table(
    engine: Engine,
    table: Table,
    row_count: int,
    sample_percentage: float = 10.0,
    max_rows_override: int = None  # NEW: Force specific limit
):
    """Create sampled query with optional max_rows override.

    Override bypasses adaptive logic (for fast init profiling).
    """
    if not USE_NATIVE_SAMPLING:
        return table

    dialect_name = engine.dialect.name

    try:
        # NEW: If override provided, use it directly (bypass min/max bounds)
        if max_rows_override:
            actual_rows = max_rows_override
            actual_pct = (actual_rows / row_count * 100) if row_count > 0 else sample_percentage
            actual_pct = min(actual_pct, 100.0)
        else:
            # Adaptive sampling (existing logic)
            min_rows = 1000
            max_rows = 100000
            target_rows = int(row_count * (sample_percentage / 100))
            actual_rows = max(min_rows, min(target_rows, max_rows))
            actual_pct = (actual_rows / row_count * 100) if row_count > 0 else sample_percentage
            actual_pct = min(actual_pct, 100.0)

        # PostgreSQL - native TABLESAMPLE BERNOULLI
        if dialect_name == 'postgresql':
            return table.tablesample(func.bernoulli(actual_pct))

        # MSSQL - native TABLESAMPLE PERCENT
        elif dialect_name == 'mssql':
            return table.tablesample(text(f"{actual_pct} PERCENT"))

        # MySQL - ORDER BY RAND() + LIMIT
        elif dialect_name == 'mysql':
            sample_query = select(table).order_by(func.rand()).limit(actual_rows)
            return sample_query.cte('sample')

        # SQLite and others - ORDER BY RANDOM() + LIMIT
        else:
            sample_query = select(table).order_by(func.random()).limit(actual_rows)
            return sample_query.cte('sample')

    except Exception:
        return table
```

### 2.2 Thread max_rows_override Through Call Chain

**File:** `subprocess/runtime/run_profiling.py`

Update function signatures:

```python
def profile_table(
    engine, table_name: str, schema: str,
    max_rows_override: int = None  # NEW parameter
) -> dict:
    # ...
    sample_table = create_sample_table(
        engine, table, row_count,
        sample_percentage=10.0,
        max_rows_override=max_rows_override  # Pass through
    )
    # ...

def profile_database(
    dsn: str,
    max_rows_override: int = None  # NEW parameter
) -> dict:
    # ...
    for table_name in tables:
        table_profile = profile_table(
            engine, table_name, schema,
            max_rows_override=max_rows_override  # Pass through
        )
```

**File:** `subprocess/runtime/run_combined.py`

Update function signature:

```python
def run_combined(
    dsn: str,
    max_rows_override: int = None  # NEW parameter
) -> dict:
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_discovery = executor.submit(discover_schema, dsn)
        future_profiling = executor.submit(
            profile_database, dsn, max_rows_override  # Pass through
        )
```

### 2.3 Call from init() with Hardcoded 300

**File:** `tools.py` (update init method)

```python
async def init(self, component, tool_config):
    # ... existing DB/security initialization ...

    # FAST INIT: Run discovery + profiling with 300 row limit
    combined_result = await component.run_in_executor(
        self.subprocess.run_combined,
        connection_string,
        300  # Hardcoded max_rows_override for fast startup
    )

    self._schema_context = combined_result.get("discovery")
    self._profile_context = combined_result.get("profiling")

    log.info("Tool initialized (profiling limited to 300 rows for speed)")

    # ... artifact_service setup and background profiling start ...
```

**Result:** Init completes in ~10 seconds with full metrics on 300 rows per table

---

## Phase 3: Timestamp Column Detection

### 3.1 Create TimestampDetectionService

**File:** `src/sam_sql_analytics_db_tool/services/timestamp_detection.py` (NEW)

```python
"""Service for detecting timestamp columns for incremental profiling."""
import logging
from typing import Dict, Optional, List

log = logging.getLogger(__name__)


class TimestampDetectionService:
    """Detect creation timestamp columns for incremental profiling."""

    # Column name patterns indicating creation timestamp
    CREATION_PATTERNS = [
        "created_at", "createdat", "created",
        "inserted_at", "insertedat", "insert_time",
        "timestamp", "record_date", "date_created"
    ]

    # Valid timestamp SQL types
    TIMESTAMP_TYPES = ["DATETIME", "TIMESTAMP", "TIMESTAMPTZ", "DATE"]

    @classmethod
    def detect_timestamp_column(
        cls,
        table_name: str,
        columns: List[Dict],
        configured_column: Optional[str] = None
    ) -> Optional[Dict[str, str]]:
        """Detect timestamp column for table.

        Priority: configured column > heuristic detection

        Args:
            table_name: Table name
            columns: List of column dicts with 'name' and 'type'
            configured_column: User-specified column name (if any)

        Returns:
            {
                "column_name": "created_at",
                "detection_method": "configured" | "heuristic"
            }
            or None if no timestamp column found
        """
        # Priority 1: Use configured column if specified
        if configured_column:
            col_names = {col["name"] for col in columns}
            if configured_column in col_names:
                return {
                    "column_name": configured_column,
                    "detection_method": "configured"
                }
            log.warning(
                "Configured timestamp column '%s' not found in table '%s'",
                configured_column, table_name
            )

        # Priority 2: Heuristic detection
        for col in columns:
            col_name_lower = col["name"].lower()
            col_type_upper = str(col["type"]).upper()

            # Match name pattern AND type
            name_matches = any(
                pattern in col_name_lower
                for pattern in cls.CREATION_PATTERNS
            )
            type_matches = any(
                t in col_type_upper
                for t in cls.TIMESTAMP_TYPES
            )

            if name_matches and type_matches:
                return {
                    "column_name": col["name"],
                    "detection_method": "heuristic"
                }

        # No timestamp column found
        return None
```

### 3.2 Integrate into Discovery

**File:** `subprocess/runtime/run_discovery.py`

Add import at top:
```python
from timestamp_detection import TimestampDetectionService
```

Update `discover_schema()` signature (line 253):
```python
def discover_schema(
    dsn: str,
    timestamp_columns_config: Dict[str, str] = None  # NEW parameter
) -> Dict[str, any]:
```

After processing each table (around line 287), add timestamp detection:

```python
for future in as_completed(future_to_table):
    table_name = future_to_table[future]
    try:
        table_data = future.result()

        # NEW: Detect timestamp column for incremental profiling
        if timestamp_columns_config is not None:
            configured_col = timestamp_columns_config.get(table_name)
            timestamp_info = TimestampDetectionService.detect_timestamp_column(
                table_name=table_name,
                columns=table_data.get("columns", []),
                configured_column=configured_col
            )

            if timestamp_info:
                table_data["_timestamp_column"] = timestamp_info["column_name"]
                table_data["_timestamp_detection_method"] = timestamp_info["detection_method"]
                log.info(
                    "Timestamp column for %s: %s (%s)",
                    table_name,
                    timestamp_info["column_name"],
                    timestamp_info["detection_method"]
                )

        schema_data[table_name] = table_data
```

### 3.3 Update run_combined to Pass Timestamp Config

**File:** `subprocess/runtime/run_combined.py`

Update signature and calls:

```python
def run_combined(
    dsn: str,
    max_rows_override: int = None,
    timestamp_columns_config: dict = None  # NEW parameter
) -> dict:
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_discovery = executor.submit(
            discover_schema, dsn, timestamp_columns_config  # Pass config
        )
        future_profiling = executor.submit(
            profile_database, dsn, max_rows_override
        )
```

Update main():
```python
def main():
    if len(sys.argv) < 2:
        print("Usage: run_combined.py <dsn> [<timestamp_config_json>]", file=sys.stderr)
        sys.exit(1)

    dsn = sys.argv[1]
    timestamp_config = json.loads(sys.argv[2]) if len(sys.argv) > 2 else None

    result = run_combined(dsn, None, timestamp_config)
    print(json.dumps(result, default=json_serialize))
```

### 3.4 Call from tools.py init()

```python
# Extract timestamp config from YAML
timestamp_config = (
    self.tool_config
    .get("profiling", {})
    .get("incremental", {})
    .get("timestamp_columns", {})
)

# Pass to subprocess (serialize as JSON arg)
combined_result = await component.run_in_executor(
    self.subprocess.run_combined,
    connection_string,
    300,  # max_rows_override
    timestamp_config  # NEW parameter
)
```

---

## Phase 4: Dual Profiling Runtime

### 4.1 Add WHERE Filter Support

**File:** `subprocess/runtime/run_profiling.py`

Update `profile_table()` to accept WHERE clause:

```python
def profile_table(
    engine,
    table_name: str,
    schema: str,
    max_rows_override: int = None,
    where_clause: str = None  # NEW: For incremental profiling
) -> dict:
    # ... existing setup ...

    # Create sampled table
    sample_table = create_sample_table(
        engine, table, row_count,
        sample_percentage=10.0,
        max_rows_override=max_rows_override
    )

    # NEW: Apply WHERE filter if provided
    if where_clause:
        from sqlalchemy import text
        sample_table = sample_table.where(text(where_clause))
        profile_data["_where_clause"] = where_clause
        log.info("Profiling %s with filter: %s", table_name, where_clause)

    # ... rest of profiling logic unchanged ...
```

Update `profile_database()` to accept per-table WHERE filters:

```python
def profile_database(
    dsn: str,
    max_rows_override: int = None,
    where_filters: Dict[str, str] = None  # NEW: {table_name: WHERE clause}
) -> dict:
    # ...
    for table_name in tables:
        where_clause = where_filters.get(table_name) if where_filters else None
        table_profile = profile_table(
            engine, table_name, schema,
            max_rows_override=max_rows_override,
            where_clause=where_clause  # NEW parameter
        )
```

### 4.2 Create Dual Profiling Script

**File:** `subprocess/runtime/run_dual_profiling.py` (NEW)

```python
"""Run full + incremental profiling in parallel."""
import json
import sys
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from datetime import datetime, date

from run_profiling import profile_database

log = logging.getLogger(__name__)


def json_serialize(obj):
    """Convert non-JSON-serializable types."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    raise TypeError(f"Type {type(obj)} not serializable")


def run_dual_profiling(
    dsn: str,
    schema_with_timestamps: dict,
    max_rows_override: int = None
) -> dict:
    """Run both full and incremental profiling in parallel.

    Args:
        dsn: Database connection string
        schema_with_timestamps: Schema dict with _timestamp_column metadata
        max_rows_override: Optional row limit (None = use adaptive 1K-100K)

    Returns:
        {
            "full": {tables: {...}},
            "incremental": {tables: {...}},
            "timestamp_columns": {"users": "created_at", ...}
        }
    """
    results = {}

    with ThreadPoolExecutor(max_workers=2) as executor:
        # Submit full profiling (no WHERE filters)
        future_full = executor.submit(
            profile_database,
            dsn,
            max_rows_override,
            where_filters=None
        )

        # Build WHERE clauses for incremental profiling
        where_filters = {}
        for table_name, table_data in schema_with_timestamps.get("tables", {}).items():
            timestamp_col = table_data.get("_timestamp_column")
            if timestamp_col:
                # Database-agnostic interval syntax
                where_filters[table_name] = (
                    f"{timestamp_col} > NOW() - INTERVAL '24 hours'"
                )

        # Submit incremental profiling
        future_incr = executor.submit(
            profile_database,
            dsn,
            max_rows_override,
            where_filters=where_filters
        )

        # Collect results
        results["full"] = future_full.result()
        results["incremental"] = future_incr.result()

        # Include timestamp column mapping for transparency
        results["timestamp_columns"] = {
            table: data.get("_timestamp_column")
            for table, data in schema_with_timestamps.get("tables", {}).items()
            if data.get("_timestamp_column")
        }

    return results


def main():
    if len(sys.argv) != 3:
        print("Usage: run_dual_profiling.py <dsn> <schema_json>", file=sys.stderr)
        sys.exit(1)

    dsn = sys.argv[1]
    schema_json = sys.argv[2]  # JSON string of schema with timestamp metadata

    schema = json.loads(schema_json)
    result = run_dual_profiling(dsn, schema, max_rows_override=None)

    # Output JSON to stdout
    print(json.dumps(result, default=json_serialize))


if __name__ == "__main__":
    main()
```

### 4.3 Add to AnalyticsSubprocessManager

**File:** `subprocess/analytics_manager.py`

```python
def run_dual_profiling(
    self,
    dsn: str,
    schema_with_timestamps: dict,
    max_rows_override: int = None
):
    """Run both full and incremental profiling."""
    venv = self.initialize_env(dsn)
    python_path = venv / "bin" / "python"
    script = venv / "runtime" / "run_dual_profiling.py"

    cmd = [
        str(python_path),
        str(script),
        dsn,
        json.dumps(schema_with_timestamps)  # Pass schema as JSON
    ]

    return self._execute_subprocess_json(cmd)
```

---

## Phase 5: Update Tool Schema & Operations

### 5.1 Update parameters_schema with profile_type

**File:** `tools.py`

```python
@property
def parameters_schema(self):
    return adk_types.Schema(
        type=adk_types.Type.OBJECT,
        properties={
            "operation": adk_types.Schema(
                type=adk_types.Type.STRING,
                enum=["query", "list_profiles", "get_profile"],
                description=(
                    "Operation: query (SQL), list_profiles (dates), "
                    "get_profile (load profile)"
                )
            ),
            "query": adk_types.Schema(
                type=adk_types.Type.STRING,
                description="SQL SELECT query (when operation='query')"
            ),
            "date": adk_types.Schema(
                type=adk_types.Type.STRING,
                description="Date YYYY-MM-DD (when operation='get_profile')"
            ),
            "profile_type": adk_types.Schema(
                type=adk_types.Type.STRING,
                enum=["full", "incremental", "both"],
                description=(
                    "Profile type:\n"
                    "- 'full': Full dataset snapshots (overall trends)\n"
                    "- 'incremental': Last 24h data snapshots (fresh anomalies)\n"
                    "- 'both': Return both types (default)"
                )
            ),
        },
        required=["operation"]
    )
```

### 5.2 Update _run_async_impl Routing

```python
async def _run_async_impl(self, args, tool_context, **kwargs):
    """Route to handler based on operation."""
    operation = args.get("operation")

    if operation == "query":
        if not args.get("query"):
            return {"error": "Missing 'query' parameter"}
        return await self._handle_query(args, tool_context)

    elif operation == "list_profiles":
        return await self._handle_list_profiles(args, tool_context)

    elif operation == "get_profile":
        if not args.get("date"):
            return {"error": "Missing 'date' parameter"}
        return await self._handle_get_profile(args, tool_context)

    else:
        return {"error": f"Invalid operation: {operation}"}
```

### 5.3 Extract _handle_query()

Extract current query execution logic into separate method.

### 5.4 Add _handle_list_profiles()

```python
async def _handle_list_profiles(self, args, tool_context):
    """List available profile dates with type filtering."""
    if not self._artifact_service:
        return {"error": "artifact_service unavailable"}

    profile_type = args.get("profile_type", "both")
    result = {}

    if profile_type in ["full", "both"]:
        result["full_dates"] = await self.profile_history.list_profiles(
            "full", self._artifact_service, self._app_name
        )

    if profile_type in ["incremental", "both"]:
        result["incremental_dates"] = await self.profile_history.list_profiles(
            "incremental", self._artifact_service, self._app_name
        )

    return result
```

### 5.5 Add _handle_get_profile()

```python
async def _handle_get_profile(self, args, tool_context):
    """Load historical profile with type selection."""
    if not self._artifact_service:
        return {"error": "artifact_service unavailable"}

    date = args.get("date")
    profile_type = args.get("profile_type", "both")

    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {"error": f"Invalid date format: {date}"}

    result = {"date": date}

    if profile_type in ["full", "both"]:
        result["full"] = await self.profile_history.get_profile(
            date, "full", self._artifact_service, self._app_name
        )

    if profile_type in ["incremental", "both"]:
        result["incremental"] = await self.profile_history.get_profile(
            date, "incremental", self._artifact_service, self._app_name
        )

    return result
```

---

## Phase 6: ProfileHistoryService (Dual Type Support)

**File:** `src/sam_sql_analytics_db_tool/services/profile_history.py` (NEW)

```python
"""Service for managing historical profiles in artifact storage."""
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from solace_agent_mesh.agent.utils.artifact_helpers import save_artifact_with_metadata

log = logging.getLogger(__name__)


class ProfileHistoryService:
    """Manages historical profiles (tool-instance scoped, dual type)."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        self.base_path = f"analytics_profiles/{tool_name}"

    async def save_profile(
        self,
        date: str,
        profile_data: Dict,
        profile_type: str,  # "full" or "incremental"
        artifact_service,
        app_name: str
    ):
        """Save profile to artifacts/{profile_type}/profile_YYYY-MM-DD.json"""
        filename = f"{self.base_path}/{profile_type}/profile_{date}.json"

        await save_artifact_with_metadata(
            artifact_service=artifact_service,
            app_name=app_name,
            user_id="global",  # Database-scoped
            session_id="global",  # Not session-specific
            filename=filename,
            content_bytes=json.dumps(profile_data).encode(),
            mime_type="application/json",
            metadata_dict={
                "source": "sql_analytics_profiling",
                "profile_type": profile_type,
                "date": date,
                "tool_name": self.tool_name
            }
        )

        log.info("Saved %s profile for %s", profile_type, date)

    async def list_profiles(
        self,
        profile_type: str,  # "full" or "incremental"
        artifact_service,
        app_name: str
    ) -> List[str]:
        """List available dates for profile type."""
        prefix = f"{self.base_path}/{profile_type}"

        try:
            artifacts = await artifact_service.list_artifacts(
                app_name=app_name,
                user_id="global",
                session_id="global",
                prefix=prefix
            )

            dates = []
            for artifact in artifacts:
                filename = artifact.get("filename", "")
                if "profile_" in filename and filename.endswith(".json"):
                    date_str = filename.split("profile_")[1].replace(".json", "")
                    dates.append(date_str)

            return sorted(dates, reverse=True)

        except Exception as e:
            log.error("Failed to list %s profiles: %s", profile_type, e)
            return []

    async def get_profile(
        self,
        date: str,
        profile_type: str,
        artifact_service,
        app_name: str
    ) -> Optional[Dict]:
        """Load profile for specific date and type."""
        filename = f"{self.base_path}/{profile_type}/profile_{date}.json"

        try:
            artifact = await artifact_service.load_artifact(
                app_name=app_name,
                user_id="global",
                session_id="global",
                filename=filename
            )

            if not artifact:
                return None

            content = artifact.get_bytes()
            return json.loads(content.decode())

        except Exception as e:
            log.error("Failed to load %s profile for %s: %s", profile_type, date, e)
            return None

    async def prune_old_profiles(
        self,
        retention_days: int,
        artifact_service,
        app_name: str
    ):
        """Prune both full and incremental profiles older than retention."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        for profile_type in ["full", "incremental"]:
            try:
                dates = await self.list_profiles(
                    profile_type, artifact_service, app_name
                )
                old_dates = [d for d in dates if d < cutoff_str]

                for date in old_dates:
                    filename = f"{self.base_path}/{profile_type}/profile_{date}.json"
                    await artifact_service.delete_artifact(
                        app_name=app_name,
                        user_id="global",
                        session_id="global",
                        filename=filename
                    )

                if old_dates:
                    log.info(
                        "Pruned %d old %s profiles",
                        len(old_dates), profile_type
                    )

            except Exception as e:
                log.error("Failed to prune %s profiles: %s", profile_type, e)
```

---

## Phase 7: Background Job with Dual Profiling

### 7.1 Store artifact_service in init()

**File:** `tools.py` (add to init after combined_result)

```python
# Store artifact_service for background thread
self._artifact_service = None
self._app_name = None

if hasattr(component, "artifact_service") and component.artifact_service:
    self._artifact_service = component.artifact_service
    self._app_name = getattr(component, "app_name", "sam-app")
    log.info("artifact_service available")

    # Initialize profile history service
    self.profile_history = ProfileHistoryService(self.tool_name)

    # Start background profiling if enabled
    schedule_config = profiling_config.get("schedule", {})
    if schedule_config.get("enabled"):
        self._start_background_profiling(component, schedule_config)
else:
    log.warning("artifact_service unavailable - profiling disabled")
```

### 7.2 Background Profiling Thread

```python
def _start_background_profiling(self, component, schedule_config):
    """Start daemon thread for scheduled dual profiling."""
    import threading
    import asyncio

    self._stop_profiling = threading.Event()
    self._component_ref = component

    def profiling_loop():
        # Convert interval_days to seconds
        interval_days = schedule_config.get("interval_days", 1)
        interval_seconds = interval_days * 86400

        profiling_config = self.tool_config.get("profiling", {})
        retention_days = profiling_config.get("retention_days", 30)

        log.info(
            "Profiling loop starting (interval=%d days, retention=%d days)",
            interval_days, retention_days
        )

        while not self._stop_profiling.wait(interval_seconds):
            try:
                log.info("Running scheduled dual profiling...")

                # Run dual profiling subprocess
                dual_result = self.subprocess.run_dual_profiling(
                    self.tool_config["connection_string"],
                    self._schema_context,  # Has timestamp column metadata
                    max_rows_override=None  # Use adaptive 1K-100K
                )

                date = datetime.utcnow().strftime("%Y-%m-%d")

                # Save full profile (if enabled)
                if profiling_config.get("full", {}).get("enabled", True):
                    asyncio.run(self.profile_history.save_profile(
                        date, dual_result["full"], "full",
                        self._artifact_service, self._app_name
                    ))

                # Save incremental profile (if enabled)
                if profiling_config.get("incremental", {}).get("enabled", True):
                    asyncio.run(self.profile_history.save_profile(
                        date, dual_result["incremental"], "incremental",
                        self._artifact_service, self._app_name
                    ))

                # Prune old profiles (both types)
                asyncio.run(self.profile_history.prune_old_profiles(
                    retention_days, self._artifact_service, self._app_name
                ))

                log.info("Dual profiling completed for %s", date)

            except Exception as e:
                log.error("Dual profiling failed: %s", e, exc_info=True)

    thread = threading.Thread(target=profiling_loop, daemon=True)
    thread.start()
    log.info("Background profiling thread started")

async def cleanup(self, component, tool_config):
    """Stop background thread and cleanup."""
    if hasattr(self, "_stop_profiling"):
        log.info("Stopping background profiling...")
        self._stop_profiling.set()

    if self.db_factory:
        self.db_factory.close()
```

**Add imports:**
```python
import threading
import asyncio
from datetime import datetime
```

---

## Phase 8: Transparency in tool_description

**File:** `tools.py` (update tool_description property)

Add after "✅ Database Connected" (line 65):

```python
# Show detected timestamp columns for transparency
schedule = self.tool_config.get("profiling", {}).get("schedule", {})
if schedule.get("enabled") and self._artifact_service:
    profiling_config = self.tool_config.get("profiling", {})

    context.append("\n📊 Historical profiling enabled")

    # Show which profile types are enabled
    full_enabled = profiling_config.get("full", {}).get("enabled", True)
    incr_enabled = profiling_config.get("incremental", {}).get("enabled", True)

    if full_enabled:
        context.append("  - Full snapshots: Enabled (random 10% sample)")
    if incr_enabled:
        context.append("  - Incremental snapshots: Enabled (last 24h data)")
        context.append("\n  Timestamp columns detected:")

        for table_name, table_data in self._schema_context.get("tables", {}).items():
            timestamp_col = table_data.get("_timestamp_column")
            method = table_data.get("_timestamp_detection_method")

            if timestamp_col:
                context.append(f"    - {table_name}.{timestamp_col} ({method})")
            else:
                context.append(f"    - {table_name}: skipped (no timestamp)")

    retention = profiling_config.get("retention_days", 30)
    context.append(f"\n  Retention: {retention} days")
```

---

## Artifact Storage Structure

```
artifact://app/global/analytics_profiles/
└── {TOOL_NAME}/              ← e.g., "analytics_db"
    ├── full/
    │   ├── profile_2026-01-02.json
    │   └── profile_2026-01-01.json
    └── incremental/
        ├── profile_2026-01-02.json  (last 24h data)
        └── profile_2026-01-01.json  (that day's data)
```

---

## Implementation Checklist

**Phase 1: Cleanup**
- [ ] Remove output_dir from analytics_manager.py
- [ ] Remove output_dir from run_combined.py
- [ ] Remove output_dir from run_discovery.py
- [ ] Remove output_dir from run_profiling.py
- [ ] Remove output_dir from tools.py init()
- [ ] Remove output_dir from config.yaml

**Phase 2: Fast Init**
- [ ] Add max_rows_override to create_sample_table() (with bypass logic)
- [ ] Thread max_rows_override through profile_table()
- [ ] Thread max_rows_override through profile_database()
- [ ] Thread max_rows_override through run_combined()
- [ ] Call from init() with hardcoded 300

**Phase 3: Timestamp Detection**
- [ ] Create TimestampDetectionService class
- [ ] Integrate into run_discovery.py
- [ ] Update run_combined() to pass timestamp config
- [ ] Pass timestamp config from tools.py init()

**Phase 4: Dual Profiling**
- [ ] Add where_clause parameter to profile_table()
- [ ] Add where_filters parameter to profile_database()
- [ ] Create run_dual_profiling.py script
- [ ] Add run_dual_profiling() to AnalyticsSubprocessManager

**Phase 5: Schema & Operations**
- [ ] Update parameters_schema with operation + profile_type
- [ ] Update _run_async_impl with routing logic
- [ ] Extract _handle_query()
- [ ] Implement _handle_list_profiles()
- [ ] Implement _handle_get_profile()

**Phase 6: Profile History Service**
- [ ] Create ProfileHistoryService class
- [ ] Implement save_profile() with profile_type
- [ ] Implement list_profiles() with artifact scanning
- [ ] Implement get_profile() with profile_type
- [ ] Implement prune_old_profiles() for both types

**Phase 7: Background Job**
- [ ] Store artifact_service in init()
- [ ] Implement _start_background_profiling()
- [ ] Implement profiling_loop() with dual profiling
- [ ] Update cleanup() to stop thread
- [ ] Add imports (threading, asyncio, datetime)

**Phase 8: Transparency**
- [ ] Update tool_description to show timestamp columns
- [ ] Show full/incremental enabled status
- [ ] Keep config.yaml simple (remove sample_size)

**Phase 9: Testing**
- [ ] Unit tests for TimestampDetectionService
- [ ] Unit tests for ProfileHistoryService
- [ ] Integration tests for operation routing
- [ ] Integration tests for dual profiling
- [ ] Update existing tests to use operation="query"
- [ ] Test background thread start/stop
- [ ] Test pruning logic

**Phase 10: Documentation**
- [ ] Update README with dual profiling section
- [ ] Update config.yaml with schedule/retention examples
- [ ] Document timestamp detection strategy

---

## Key Design Decisions (FINAL)

- **Dual profiling:** Full (trends) + incremental (anomalies) run in parallel
- **Fast init:** Hardcoded 300 rows (not in YAML) for 10-second startup
- **Background:** Adaptive 1K-100K or 10% (hardcoded bounds)
- **Timestamp detection:** Config-first, heuristic fallback
- **Transparency:** tool_description shows detected timestamp columns
- **Interval:** `interval_days` (user-friendly), converted to seconds internally
- **Artifact scope:** Tool-instance (global/global) - database-specific, not user/session
- **No index file:** Scan artifacts directory directly (simpler)
- **Config stays clean:** Only user-customizable options in YAML
- **profile_type parameter:** "full", "incremental", or "both"
- **max_rows_override fix:** Bypasses min_rows when set (critical for 300-row init)
