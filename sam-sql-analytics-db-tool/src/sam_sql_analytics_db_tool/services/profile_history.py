"""Service for managing historical profiles in artifact storage."""
import logging
import json
from typing import Dict, Any, List, Optional

log = logging.getLogger(__name__)


class ProfileHistoryService:
    """Manages historical profile snapshots in artifact storage."""

    def __init__(self, tool_name: str):
        """Initialize profile history service.

        Args:
            tool_name: Tool instance name (for artifact filename scoping)
        """
        self.tool_name = tool_name
        # Use flat storage (no subdirectories) for artifact service compatibility
        self.filename_prefix = f"analytics_profile_{tool_name}_"

    async def save_profile(
        self,
        date: str,
        profile_data: Dict[str, Any],
        artifact_service,
        app_name: str
    ):
        """Save profile snapshot to artifact storage.

        Args:
            date: Date string in YYYY-MM-DD format
            profile_data: Profile context dict to save
            artifact_service: SAM artifact service from component
            app_name: Application name
        """
        from solace_agent_mesh.agent.utils.artifact_helpers import save_artifact_with_metadata
        from datetime import datetime as dt, timezone

        # Flat filename: analytics_profile_analytics_db_2026-01-06.json
        filename = f"{self.filename_prefix}{date}.json"

        await save_artifact_with_metadata(
            artifact_service=artifact_service,
            app_name=app_name,
            user_id="global",  # Database-scoped, not user-specific
            session_id="global",  # Not session-specific
            filename=filename,
            content_bytes=json.dumps(profile_data, default=str).encode(),
            mime_type="application/json",
            metadata_dict={
                "source": "sql_analytics_profiling",
                "date": date,
                "tool_name": self.tool_name
            },
            timestamp=dt.now(timezone.utc)
        )

        log.info("Saved profile for %s to %s", date, filename)

    async def get_profile(
        self,
        date: str,
        artifact_service,
        app_name: str
    ) -> Optional[Dict[str, Any]]:
        """Load profile snapshot for specific date.

        Args:
            date: Date string in YYYY-MM-DD format
            artifact_service: SAM artifact service
            app_name: Application name

        Returns:
            Profile dict or None if not found
        """
        # Flat filename
        filename = f"{self.filename_prefix}{date}.json"

        try:
            artifact = await artifact_service.load_artifact(
                app_name=app_name,
                user_id="global",
                session_id="global",
                filename=filename
            )

            if not artifact:
                log.warning("Profile not found for date %s", date)
                return None

            content = artifact.get_bytes()
            profile = json.loads(content.decode())

            log.info("Loaded profile for %s from %s", date, filename)
            return profile

        except Exception as e:
            log.error("Failed to load profile for %s: %s", date, e, exc_info=True)
            return None

    async def list_profiles(
        self,
        artifact_service,
        app_name: str
    ) -> List[str]:
        """List all available profile dates.

        Args:
            artifact_service: SAM artifact service
            app_name: Application name

        Returns:
            List of date strings (YYYY-MM-DD), sorted newest first
        """
        try:
            # Get all artifact keys (returns flat list of filenames)
            artifact_keys = await artifact_service.list_artifact_keys(
                app_name=app_name,
                user_id="global",
                session_id="global"
            )

            # Filter for our profile files and extract dates
            dates = []
            for filename in artifact_keys:
                # Match flat filenames: analytics_profile_analytics_db_2026-01-06.json
                # Exclude metadata files (.metadata.json)
                if filename.startswith(self.filename_prefix) and filename.endswith(".json") and ".metadata" not in filename:
                    # Extract date from: analytics_profile_analytics_db_2026-01-06.json
                    date_str = filename.replace(self.filename_prefix, "").replace(".json", "")
                    dates.append(date_str)

            # Sort newest first
            sorted_dates = sorted(dates, reverse=True)
            log.info("Found %d historical profiles", len(sorted_dates))
            return sorted_dates

        except Exception as e:
            log.error("Failed to list profiles: %s", e, exc_info=True)
            return []

    async def generate_demo_snapshots(
        self,
        base_profile: Dict[str, Any],
        artifact_service,
        app_name: str,
        num_days: int = 20
    ):
        """Generate demo historical profiles with anomalies for POC.

        ⚠️  DEMO ONLY - Remove this method for production deployment.

        Simulates 20 days with incidents:
        - Day 7: Fraud spike
        - Day 8: ETL failure
        - Day 10: Price corruption
        - Days 12-13: Data loss
        - Days 15-16: System outage
        - Day 18: Inventory crisis

        Args:
            base_profile: Current profile to use as day 0
            artifact_service: SAM artifact service
            app_name: Application name
            num_days: Number of days to generate
        """
        from datetime import datetime, timedelta
        import copy

        log.info("🔧 Generating %d days of DEMO profiles with anomalies...", num_days)

        for days_ago in range(num_days):
            date = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

            # Apply drift simulation
            profile = self._apply_demo_drift(base_profile, days_ago)

            # Save snapshot
            await self.save_profile(date, profile, artifact_service, app_name)

            # Log events
            customers = profile["tables"]["customers"]["table_metrics"]["row_count"]
            orders = profile["tables"]["orders"]["table_metrics"]["row_count"]
            event = self._get_event_label(days_ago)

            log.info("  %s (day -%2d): customers=%6d, orders=%6d%s",
                     date, days_ago, customers, orders, event)

        log.info("✅ Demo generation complete! %d profiles created.", num_days)

    @staticmethod
    def _apply_demo_drift(base_profile: Dict[str, Any], days_ago: int) -> Dict[str, Any]:
        """⚠️  DEMO ONLY - Apply synthetic drift for POC."""
        import copy

        profile = copy.deepcopy(base_profile)

        if days_ago == 0:
            return profile

        # Baseline trends
        growth = (1.005 ** -days_ago)
        price_inflation = (1.003 ** -days_ago)

        # Anomaly flags
        data_loss = days_ago in [12, 13]
        price_corruption = days_ago == 10
        system_outage = days_ago in [15, 16]
        fraud_spike = days_ago == 7
        inventory_crisis = days_ago == 18
        etl_failure = days_ago == 8

        if data_loss:
            growth *= 0.85

        for table_name, table_data in profile.get("tables", {}).items():
            # Row counts
            table_metrics = table_data.get("table_metrics", {})
            if "row_count" in table_metrics and table_metrics["row_count"] > 0:
                original = table_metrics["row_count"]
                if system_outage and table_name in ["orders", "orderlines"]:
                    table_metrics["row_count"] = int(original * (1.005 ** -(days_ago + 1)))
                else:
                    table_metrics["row_count"] = max(1, int(original * growth))

            # Column metrics
            for col_name, metrics in table_data.get("column_metrics", {}).items():
                if not isinstance(metrics, dict):
                    continue

                # Price corruption
                if price_corruption and "price" in col_name.lower():
                    for f in ["min", "max", "mean", "median", "sum"]:
                        if f in metrics and isinstance(metrics[f], (int, float)):
                            metrics[f] *= 0.25

                # Fraud spike
                elif fraud_spike and table_name == "orders" and "totalamount" in col_name:
                    if "max" in metrics:
                        metrics["max"] = 9999.0
                    if "third_quartile" in metrics and metrics["third_quartile"] is not None:
                        metrics["third_quartile"] *= 2.5

                # Inventory crisis
                elif inventory_crisis and table_name == "inventory" and "quan_in_stock" in col_name:
                    for f in ["mean", "median", "max", "sum"]:
                        if f in metrics and isinstance(metrics[f], (int, float)):
                            metrics[f] *= 0.2

                # Normal inflation
                elif any(k in col_name.lower() for k in ["price", "amount", "income"]):
                    for f in ["min", "max", "mean", "median", "sum"]:
                        if f in metrics and isinstance(metrics[f], (int, float)):
                            metrics[f] *= price_inflation

                # ETL failure
                if etl_failure and table_name == "customers" and col_name == "state":
                    metrics["null_ratio"] = 0.85
                    if "null_count" in metrics and "count" in metrics:
                        metrics["null_count"] = metrics["count"] * 0.85

                # Gradual quality degradation
                if "null_ratio" in metrics and metrics["null_ratio"] is not None and metrics["null_ratio"] > 0.1:
                    improvement = 1 - (days_ago * 0.01)
                    metrics["null_ratio"] *= improvement
                    if "null_count" in metrics and "count" in metrics:
                        metrics["null_count"] = int(metrics["count"] * metrics["null_ratio"])

        return profile

    @staticmethod
    def _get_event_label(days_ago: int) -> str:
        """⚠️  DEMO ONLY - Get event label for logging."""
        if days_ago == 0:
            return " [TODAY]"
        elif days_ago in [12, 13]:
            return " [⚠️  DATA LOSS]"
        elif days_ago == 10:
            return " [⚠️  CORRUPTION]"
        elif days_ago in [15, 16]:
            return " [⚠️  OUTAGE]"
        elif days_ago == 7:
            return " [⚠️  FRAUD]"
        elif days_ago == 18:
            return " [⚠️  INV CRISIS]"
        elif days_ago == 8:
            return " [⚠️  ETL FAIL]"
        return ""
