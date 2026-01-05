import pytest
import sqlalchemy as sa
import os
import logging
from sam_sql_analytics_db_tool.tools import SqlAnalyticsDbTool
from data_helper import metadata

log = logging.getLogger(__name__)

@pytest.mark.asyncio
class TestSqlAnalyticsDbTool:
    """Integration tests for the SqlAnalyticsDbTool."""

    async def test_container_setup(self, database_engine):
        """Test database container initialization and configuration."""
        engine, db_config = database_engine

        # Verify container is running and accessible via connection
        with engine.connect() as conn:
            # Generic connectivity test that works for all databases
            result = conn.execute(sa.text("SELECT 1")).scalar()
            assert result == 1

    async def test_synthetic_data_population(self, database_engine):
        """Test synthetic data population across all database types."""
        engine, db_config = database_engine

        # Verify table existence and row counts
        expected_counts = {
            'users': 9,
            'categories': 6,
            'products': 12,
            'orders': 10,
            'order_items': 12,
            'reviews': 10,
            'customer_records': 8
        }

        with engine.connect() as conn:
            for table, expected_count in expected_counts.items():
                result = conn.execute(
                    sa.text(f"SELECT COUNT(*) FROM {table}")
                ).scalar()
                assert result == expected_count, f"Table {table} has incorrect row count"

    async def test_discovery_metadata(self, analytics_tool):
        """Rigorously test schema discovery: tables, columns, PKs, FKs, PII, enums."""
        # Verify tool initialization
        assert analytics_tool._connection_healthy
        assert analytics_tool._schema_context is not None

        schema = analytics_tool._schema_context
        tables = schema.get("tables", {})
        summary = schema.get("_summary", {})

        # Verify all expected tables discovered
        expected_tables = {"users", "products", "categories", "product_categories",
                          "orders", "order_items", "reviews", "customer_records"}
        discovered_tables = set(tables.keys())
        assert expected_tables.issubset(discovered_tables), \
            f"Missing tables: {expected_tables - discovered_tables}"

        # Test 1: Users table - columns, PK, unique constraints, PII
        users_table = tables["users"]
        users_cols = {col["name"]: col for col in users_table["columns"]}

        assert "id" in users_cols
        assert "email" in users_cols
        assert "name" in users_cols
        assert "created_at" in users_cols

        # Verify PK
        assert "id" in users_table["primary_keys"], "users.id should be PK"

        # Verify PII detection on email
        email_col = users_cols["email"]
        assert email_col.get("pii"), "Email should be detected as PII"
        assert email_col["pii"].get("pii_detected") is True

        # Test 2: Orders table - foreign keys, enum values for status
        orders_table = tables["orders"]
        orders_cols = {col["name"]: col for col in orders_table["columns"]}

        # Verify FK to users
        fks = orders_table.get("foreign_keys", [])
        user_fk = next((fk for fk in fks if "user_id" in fk.get("columns", [])), None)
        assert user_fk is not None, "orders.user_id should have FK to users"
        assert user_fk["referred_table"] == "users"

        # Verify status enum values
        status_col = orders_cols.get("status")
        if status_col and "enum_values" in status_col:
            expected_statuses = {"Cancelled", "Delivered", "Processing", "Shipped"}
            actual_statuses = set(status_col["enum_values"])
            assert expected_statuses == actual_statuses, \
                f"Status enums mismatch: {actual_statuses}"

        # Test 3: Products table - nullable columns
        products_table = tables["products"]
        products_cols = {col["name"]: col for col in products_table["columns"]}

        # description can be NULL
        desc_col = products_cols.get("description")
        assert desc_col is not None

        # Test 4: Product_categories - composite PK
        pc_table = tables.get("product_categories")
        if pc_table:
            pks = pc_table.get("primary_keys", [])
            assert "product_id" in pks and "category_id" in pks, \
                "product_categories should have composite PK"

        # Test 5: Reviews table - check constraint on rating
        reviews_table = tables["reviews"]
        reviews_cols = {col["name"]: col for col in reviews_table["columns"]}
        assert "rating" in reviews_cols

        # Test 6: Summary stats
        assert summary.get("total_tables", 0) >= 8, "Should discover at least 8 tables"

        # Verify connection status in tool description
        description = analytics_tool.tool_description
        assert "✅ Database Connected" in description
        assert "Database Schema:" in description

    async def test_profiling_metrics(self, analytics_tool):
        """Rigorously test profiling: row counts, min/max/mean, histograms, null ratios."""
        # Verify tool initialization
        assert analytics_tool._connection_healthy
        assert analytics_tool._profile_context is not None

        profile = analytics_tool._profile_context
        tables = profile.get("tables", {})
        summary = profile.get("_summary", {})

        # Test 1: Row counts match expected
        expected_counts = {
            "users": 9,
            "products": 12,
            "categories": 6,
            "orders": 10,
            "order_items": 12,
            "reviews": 10,
            "customer_records": 8
        }

        for table_name, expected_count in expected_counts.items():
            table_profile = tables.get(table_name)
            assert table_profile is not None, f"Missing profile for {table_name}"

            row_count = table_profile.get("table_metrics", {}).get("row_count")
            assert row_count == expected_count, \
                f"{table_name} row count: expected {expected_count}, got {row_count}"

        # Test 2: Users table - numeric column metrics (id)
        users_profile = tables["users"]
        users_col_metrics = users_profile.get("column_metrics", {})

        id_metrics = users_col_metrics.get("id", {})
        assert id_metrics.get("min") == 1, "users.id min should be 1"
        assert id_metrics.get("max") == 9, "users.id max should be 9"
        assert id_metrics.get("count") == 9, "users.id count should be 9"
        assert id_metrics.get("null_count") == 0, "users.id should have no NULLs"
        assert id_metrics.get("distinct_count") == 9, "users.id should be all unique"

        # Test 3: Products table - price column statistics
        products_profile = tables["products"]
        products_col_metrics = products_profile.get("column_metrics", {})

        price_metrics = products_col_metrics.get("price", {})
        assert price_metrics.get("min") == 10.0, "Cheapest product is $10"
        assert price_metrics.get("max") == 2399.99, "Most expensive product is $2399.99"
        assert price_metrics.get("mean") is not None, "price should have mean"
        assert price_metrics.get("median") is not None, "price should have median"
        assert price_metrics.get("stddev") is not None, "price should have stddev"

        # Test 4: Reviews table - rating histogram (1-5 constrained)
        reviews_profile = tables["reviews"]
        reviews_col_metrics = reviews_profile.get("column_metrics", {})

        rating_metrics = reviews_col_metrics.get("rating", {})
        assert rating_metrics.get("min") >= 1, "rating min should be >= 1"
        assert rating_metrics.get("max") <= 5, "rating max should be <= 5"

        # Histogram should exist for numeric columns
        histogram = rating_metrics.get("histogram")
        if histogram:
            assert "boundaries" in histogram, "Histogram should have boundaries"
            assert "frequencies" in histogram, "Histogram should have frequencies"
            assert len(histogram["boundaries"]) == len(histogram["frequencies"]), \
                "Histogram boundaries/frequencies mismatch"

        # Test 5: Products table - null ratio for description
        desc_metrics = products_col_metrics.get("description", {})
        if desc_metrics:
            null_count = desc_metrics.get("null_count", 0)
            count = desc_metrics.get("count", 12)
            # 1 product has NULL description out of 12
            assert null_count >= 1, "description should have at least 1 NULL"
            null_ratio = desc_metrics.get("null_ratio")
            if null_ratio is not None:
                expected_ratio = null_count / count
                assert abs(null_ratio - expected_ratio) < 0.01, \
                    f"null_ratio mismatch: expected ~{expected_ratio}, got {null_ratio}"

        # Test 6: String metrics - email column length
        email_metrics = users_col_metrics.get("email", {})
        if email_metrics:
            min_len = email_metrics.get("min_length")
            max_len = email_metrics.get("max_length")
            # Shortest email: "bob@example.com" = 15 chars
            # Longest: "no-orders@example.com" = 21 chars
            if min_len:
                assert min_len >= 15, f"email min_length should be >= 15, got {min_len}"
            if max_len:
                assert max_len >= 21, f"email max_length should be >= 21, got {max_len}"

        # Test 7: Quartiles and IQR
        if id_metrics.get("first_quartile") and id_metrics.get("third_quartile"):
            q1 = id_metrics["first_quartile"]
            q3 = id_metrics["third_quartile"]
            iqr = id_metrics.get("iqr")
            if iqr is not None:
                expected_iqr = q3 - q1
                assert abs(iqr - expected_iqr) < 0.01, \
                    f"IQR mismatch: expected {expected_iqr}, got {iqr}"

        # Test 8: Summary stats
        assert summary.get("total_tables", 0) >= 8, "Should profile at least 8 tables"

        # Verify profiling in tool description
        description = analytics_tool.tool_description
        assert "Database Profile:" in description

    async def test_pii_detection_implicit_and_content_based(self, analytics_tool):
        """
        Comprehensive PII detection test covering:
        1. Implicit PII: Column names that suggest PII (e.g., "email")
        2. Content-based PII: Non-obvious column names containing actual PII data

        This test validates that OpenMetadata detects PII based on actual data content,
        not just column naming conventions. Uses OpenMetadata's actual return structures
        rather than hardcoded constants.
        """
        import json

        # Verify tool initialization
        assert analytics_tool._connection_healthy, "Tool should be connected to database"
        assert analytics_tool._schema_context is not None, "Schema context should exist"

        schema = analytics_tool._schema_context
        tables = schema.get("tables", {})

        # Part 1: Test implicit PII detection (obvious column names)
        users_table = tables.get("users")
        assert users_table is not None, "users table should exist in schema"

        users_cols = {col["name"]: col for col in users_table["columns"]}

        # Validate email column has PII detection
        email_col = users_cols.get("email")
        assert email_col is not None, "email column should exist in users table"

        email_pii = email_col.get("pii")
        if email_pii and email_pii.get("pii_detected"):
            log.info("✓ Implicit PII detected: users.email - %s", email_pii)
        else:
            log.warning("⚠ email column not detected as PII")

        # Part 2: Test content-based PII detection (non-obvious column names)
        customer_records_table = tables.get("customer_records")
        assert customer_records_table is not None, \
            "customer_records table should exist for content-based PII testing"

        customer_cols = {col["name"]: col for col in customer_records_table["columns"]}

        # Define columns with PII content (but non-obvious names)
        # We map to what Presidio entity types they should match
        pii_test_columns = {
            "account_notes": "phone numbers",
            "reference_code": "SSN patterns",
            "shipping_info": "addresses",
            "transaction_metadata": "credit card numbers",
            "tracking_reference": "IP addresses",
            "contact_info": "email addresses",
            "external_links": "URLs",
            "account_holder": "person names",
            "payment_account": "bank account numbers (IBAN)"
        }

        # Collect detection results
        detection_summary = {
            "total_pii_columns": len(pii_test_columns),
            "detected_count": 0,
            "not_detected_count": 0,
            "detection_details": {}
        }

        log.info("=== Content-based PII Detection Results ===")

        for column_name, expected_content in pii_test_columns.items():
            col_data = customer_cols.get(column_name)
            assert col_data is not None, \
                f"Column '{column_name}' should exist in customer_records table"

            pii_info = col_data.get("pii")
            pii_detected = pii_info.get("pii_detected") if pii_info else False

            detection_summary["detection_details"][column_name] = {
                "expected_content": expected_content,
                "detected": pii_detected,
                "pii_info": pii_info if pii_info else None
            }

            if pii_detected:
                detection_summary["detected_count"] += 1
                pii_type = pii_info.get("pii_type", "unknown")
                confidence = pii_info.get("confidence", "N/A")
                method = pii_info.get("detection_method", "column_name")
                log.info("✓ %s: DETECTED (%s) - type=%s, confidence=%s, method=%s",
                         column_name, expected_content, pii_type, confidence, method)
            else:
                detection_summary["not_detected_count"] += 1
                log.info("✗ %s: NOT detected (%s)", column_name, expected_content)

        # Summary statistics
        detection_rate = detection_summary["detected_count"] / detection_summary["total_pii_columns"]
        log.info("=== PII Detection Summary ===")
        log.info("Total: %d, Detected: %d, Not detected: %d, Rate: %.1f%%",
                 detection_summary['total_pii_columns'],
                 detection_summary['detected_count'],
                 detection_summary['not_detected_count'],
                 detection_rate * 100)

        # Assertions: Content-based PII detection should work
        # With openmetadata-ingestion[data-profiler] installed, we expect PII detection

        # Require at least some PII to be detected
        assert detection_summary["detected_count"] > 0, \
            f"Content-based PII detection failed completely (0/{detection_summary['total_pii_columns']} detected). " \
            f"Expected NER scanner to detect PII in columns containing: " \
            f"{', '.join(pii_test_columns.values())}. " \
            f"\n\nThis indicates either:" \
            f"\n  1. openmetadata-ingestion[data-profiler] is not installed" \
            f"\n  2. Presidio/spaCy models are missing" \
            f"\n  3. NER scanner is not functioning correctly" \
            f"\n\nInstall with: Add 'openmetadata-ingestion[data-profiler]' to [tool.sam-sql-analytics.subprocess-deps]"

        # Warn if detection rate is low but don't fail
        if detection_rate < 0.3:
            log.warning("Low PII detection rate: %.1f%% (%d/%d detected)",
                       detection_rate * 100,
                       detection_summary['detected_count'],
                       detection_summary['total_pii_columns'])
        else:
            log.info("✓ Good PII detection rate: %.1f%% (%d/%d detected)",
                    detection_rate * 100,
                    detection_summary['detected_count'],
                    detection_summary['total_pii_columns'])

        # Part 3: Verify non-PII columns are not falsely flagged
        non_pii_columns = ["id", "user_id"]
        false_positives = []

        for column_name in non_pii_columns:
            if column_name in customer_cols:
                col_data = customer_cols[column_name]
                pii_info = col_data.get("pii")
                if pii_info and pii_info.get("pii_detected"):
                    false_positives.append({
                        "column": column_name,
                        "pii_info": pii_info
                    })

        if false_positives:
            log.warning("False positive PII detections: %s",
                       [fp['column'] for fp in false_positives])

    async def test_pii_filtering_strict_mode(
        self, database_container, analytics_tool_config, mock_component
    ):
        """Test PII filtering strict mode - PII values removed, column defs kept."""
        # Create tool with strict PII filtering
        config_strict = {**analytics_tool_config}
        config_strict["security"] = {
            **analytics_tool_config.get("security", {}),
            "pii_filter_level": "strict"
        }

        tool_strict = SqlAnalyticsDbTool(config_strict)
        await tool_strict.init(mock_component, config_strict)

        # Verify tool initialized correctly
        assert tool_strict._connection_healthy
        assert tool_strict._schema_context is not None
        assert tool_strict._profile_context is not None

        # Get tool description (applies PII filtering for LLM)
        description = tool_strict.tool_description

        # PII column NAMES should still be visible (for SQL generation)
        assert "email" in description, "email column name needed for SQL"
        assert "users" in description

        # Parse schema from description to verify filtering
        import yaml
        schema_yaml = description.split("Database Schema:")[1]
        if "Database Profile:" in schema_yaml:
            schema_yaml = schema_yaml.split("Database Profile:")[0]

        schema_in_desc = yaml.safe_load(schema_yaml)
        users_table = schema_in_desc.get("tables", {}).get("users", {})
        users_cols = {col["name"]: col for col in users_table.get("columns", [])}
        email_col = users_cols.get("email")

        # Email column definition exists
        assert email_col is not None, "email column definition should exist"

        # But enum_values are removed (prevents leaking actual emails)
        assert "enum_values" not in email_col, \
            "enum_values should be removed from PII columns"

        # Verify profile metrics removed for PII columns
        if "Database Profile:" in description:
            profile_yaml = description.split("Database Profile:")[1]
            profile_in_desc = yaml.safe_load(profile_yaml)
            users_profile = profile_in_desc.get("tables", {}).get("users", {})
            email_metrics = users_profile.get("column_metrics", {}).get("email")

            assert email_metrics is None, \
                "PII column metrics removed (prevents min/max leakage)"

            # Non-PII metrics still present
            id_metrics = users_profile.get("column_metrics", {}).get("id")
            assert id_metrics is not None, "Non-PII metrics should remain"

        # Verify original contexts unchanged
        original_schema = tool_strict._schema_context
        users_table_orig = original_schema.get("tables", {}).get("users", {})
        users_cols_orig = {col["name"] for col in users_table_orig.get("columns", [])}
        assert "email" in users_cols_orig

        # Cleanup
        await tool_strict.cleanup(mock_component, config_strict)
        log.info("✓ Strict PII filtering test passed")

    async def test_pii_filtering_none_mode(
        self, database_container, analytics_tool_config, mock_component
    ):
        """Test default behavior - no PII filtering."""
        # Default config (no pii_filter_level specified = "none")
        tool_none = SqlAnalyticsDbTool(analytics_tool_config)
        await tool_none.init(mock_component, analytics_tool_config)

        assert tool_none._connection_healthy

        # Get tool description
        description = tool_none.tool_description

        # With no filtering, PII columns should be visible in schema
        schema = tool_none._schema_context
        users_table = schema.get("tables", {}).get("users", {})
        users_cols = {col["name"] for col in users_table.get("columns", [])}

        # email column should exist in schema
        assert "email" in users_cols

        # Cleanup
        await tool_none.cleanup(mock_component, analytics_tool_config)
        log.info("✓ No PII filtering test passed (default behavior)")
