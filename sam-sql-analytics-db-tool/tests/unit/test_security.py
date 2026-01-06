import pytest
from sam_sql_analytics_db_tool.services.security import SecurityService

def test_is_read_only_sql():
    security = SecurityService()
    
    # Test valid SELECT queries
    assert security.is_read_only_sql("SELECT * FROM users", "postgres")
    assert security.is_read_only_sql("SELECT id, name FROM users WHERE age > 18", "mysql")
    
    # Test invalid queries
    assert not security.is_read_only_sql("INSERT INTO users (name) VALUES ('test')", "sqlite")
    assert not security.is_read_only_sql("UPDATE users SET name = 'test'", "mssql")
    assert not security.is_read_only_sql("DELETE FROM users", "oracle")
    
def test_validate_query():
    security = SecurityService(
        warning_operations=["WITH"]
    )
    
    # Test valid query
    result = security.validate_query("SELECT * FROM users", "postgres")
    assert result["valid"]
    assert not result.get("warnings")
    
    # Test query with warnings
    result = security.validate_query("WITH temp AS (SELECT 1) SELECT * FROM temp", "postgres")
    assert result["valid"]
    assert result["warnings"]
    assert "WITH".lower() in result["warnings"][0]
    
    # Test invalid query
    result = security.validate_query("DROP TABLE users", "mysql")
    assert not result["valid"]
    
def test_get_sql_dialect():
    security = SecurityService()

    assert security.get_sql_dialect("postgres") == "postgres"
    assert security.get_sql_dialect("mysql") == "mysql"
    assert security.get_sql_dialect("oracle") == "oracle"
    assert security.get_sql_dialect("unknown") == None

def test_is_read_only_with_keywords_in_identifiers():
    """Test that keywords in table/column names don't cause false positives."""
    security = SecurityService()

    # Table names containing keywords (should be ALLOWED)
    assert security.is_read_only_sql(
        "SELECT * FROM deleted_users",
        "postgres"
    ), "Table named 'deleted_users' should be allowed"

    assert security.is_read_only_sql(
        "SELECT update_time FROM events",
        "postgres"
    ), "Column named 'update_time' should be allowed"

    assert security.is_read_only_sql(
        "SELECT * FROM insert_log WHERE created_at > NOW()",
        "postgres"
    ), "Table named 'insert_log' should be allowed"

def test_is_read_only_with_keywords_in_strings():
    """Test that keywords in string literals don't cause false positives."""
    security = SecurityService()

    # String literals containing keywords (should be ALLOWED)
    assert security.is_read_only_sql(
        "SELECT * FROM users WHERE status = 'delete pending'",
        "postgres"
    ), "String literal 'delete pending' should be allowed"

    assert security.is_read_only_sql(
        "SELECT * FROM logs WHERE message LIKE '%update failed%'",
        "postgres"
    ), "String literal containing 'update' should be allowed"

def test_is_read_only_blocks_actual_operations():
    """Test that actual forbidden operations are blocked."""
    security = SecurityService()

    # These should be BLOCKED
    assert not security.is_read_only_sql(
        "DELETE FROM deleted_users WHERE id = 1",
        "postgres"
    ), "Actual DELETE should be blocked even if table contains 'delete'"

    assert not security.is_read_only_sql(
        "UPDATE update_log SET status = 'done'",
        "postgres"
    ), "Actual UPDATE should be blocked even if table contains 'update'"

    assert not security.is_read_only_sql(
        "INSERT INTO insert_log (message) VALUES ('test')",
        "postgres"
    ), "Actual INSERT should be blocked"

def test_filter_pii_from_results_strict():
    """Test PII filtering with strict mode."""
    from sam_sql_analytics_db_tool.services.security import PIIFilterService

    # Mock schema context with PII metadata
    schema_context = {
        "tables": {
            "users": {
                "columns": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "email", "type": "VARCHAR", "pii": {"pii_detected": True, "pii_type": "NonSensitive"}},
                    {"name": "name", "type": "VARCHAR", "pii": {"pii_detected": True, "pii_type": "Sensitive"}},
                    {"name": "created_at", "type": "TIMESTAMP"}
                ]
            }
        }
    }

    # Mock query results
    results = [
        {"id": 1, "email": "alice@example.com", "name": "Alice", "created_at": "2024-01-01"},
        {"id": 2, "email": "bob@example.com", "name": "Bob", "created_at": "2024-01-02"}
    ]

    # Filter with strict mode
    filtered = PIIFilterService.filter_pii_from_results(results, schema_context, "strict")

    # Verify PII columns are masked
    assert filtered[0]["email"] == "***REDACTED***", "email should be masked"
    assert filtered[0]["name"] == "***REDACTED***", "name should be masked"
    assert filtered[1]["email"] == "***REDACTED***", "email should be masked"
    assert filtered[1]["name"] == "***REDACTED***", "name should be masked"

    # Verify non-PII columns remain
    assert filtered[0]["id"] == 1, "id should remain visible"
    assert filtered[0]["created_at"] == "2024-01-01", "created_at should remain visible"
    assert filtered[1]["id"] == 2, "id should remain visible"

def test_filter_pii_from_results_moderate():
    """Test PII filtering with moderate mode (only Sensitive PII)."""
    from sam_sql_analytics_db_tool.services.security import PIIFilterService

    schema_context = {
        "tables": {
            "users": {
                "columns": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "email", "type": "VARCHAR", "pii": {"pii_detected": True, "pii_type": "NonSensitive"}},
                    {"name": "ssn", "type": "VARCHAR", "pii": {"pii_detected": True, "pii_type": "Sensitive"}},
                ]
            }
        }
    }

    results = [{"id": 1, "email": "alice@example.com", "ssn": "123-45-6789"}]

    # Filter with moderate mode
    filtered = PIIFilterService.filter_pii_from_results(results, schema_context, "moderate")

    # Only Sensitive PII should be masked
    assert filtered[0]["ssn"] == "***REDACTED***", "Sensitive PII (ssn) should be masked"
    assert filtered[0]["email"] == "alice@example.com", "NonSensitive PII (email) should remain"
    assert filtered[0]["id"] == 1, "Non-PII should remain"

def test_filter_pii_from_results_none():
    """Test PII filtering with none mode (no filtering)."""
    from sam_sql_analytics_db_tool.services.security import PIIFilterService

    schema_context = {
        "tables": {
            "users": {
                "columns": [
                    {"name": "email", "type": "VARCHAR", "pii": {"pii_detected": True, "pii_type": "NonSensitive"}},
                ]
            }
        }
    }

    results = [{"email": "alice@example.com"}]

    # Filter with none mode
    filtered = PIIFilterService.filter_pii_from_results(results, schema_context, "none")

    # No filtering should occur
    assert filtered[0]["email"] == "alice@example.com", "No filtering with 'none' level"

def test_filter_pii_from_results_empty():
    """Test PII filtering with empty results."""
    from sam_sql_analytics_db_tool.services.security import PIIFilterService

    schema_context = {"tables": {}}

    # Empty results
    filtered = PIIFilterService.filter_pii_from_results([], schema_context, "strict")
    assert filtered == [], "Empty results should remain empty"

    # None results
    filtered = PIIFilterService.filter_pii_from_results(None, schema_context, "strict")
    assert filtered is None, "None results should remain None"
