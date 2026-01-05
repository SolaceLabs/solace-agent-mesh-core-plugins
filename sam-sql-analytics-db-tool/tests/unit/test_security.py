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
