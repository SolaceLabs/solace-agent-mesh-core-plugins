import pytest
from unittest.mock import Mock, patch
from sam_sql_analytics_db_tool.tools import SqlAnalyticsDbTool

@pytest.fixture
def tool_config():
    """Basic tool configuration for testing."""
    return {
        "tool_name": "analytics_db",
        "tool_description": "Test analytics tool",
        "connection_string": "sqlite:///test.db",
        "pool": {
            "pool_size": 1,
            "max_overflow": 1
        },
        "timeouts": {
            "connect_timeout": 5,
            "statement_timeout_ms": 10000
        },
        "security": {
            "blocked_operations": ["DROP", "DELETE"],
            "warning_operations": ["WITH"]
        },
        "profiling": {
            "sample_size": 100,
            "adaptive_sampling": True
        }
    }

@pytest.fixture
def mock_component():
    """Mock component for testing."""
    component = Mock()
    component.run_in_executor = Mock()
    return component

def test_tool_initialization(tool_config):
    """Test tool initialization without services."""
    tool = SqlAnalyticsDbTool(tool_config)
    assert tool.tool_config == tool_config
    assert not tool._connection_healthy
    assert tool._schema_context is None
    assert tool._profile_context is None

@patch('sam_sql_analytics_db_tool.tools.DBFactory')
@patch('sam_sql_analytics_db_tool.tools.SecurityService')
async def test_tool_init_success(mock_security, mock_db, tool_config, mock_component):
    """Test successful tool initialization with services."""
    # Mock successful combined discovery + profiling
    mock_component.run_in_executor.return_value = async_return({
        "discovery": {"tables": ["users", "orders"]},
        "profiling": {"profiles": {"users": {"row_count": 100}}}
    })

    tool = SqlAnalyticsDbTool(tool_config)
    await tool.init(mock_component, tool_config)

    assert tool._connection_healthy
    assert tool._schema_context == {"tables": ["users", "orders"]}
    assert tool._profile_context == {"profiles": {"users": {"row_count": 100}}}

@patch('sam_sql_analytics_db_tool.tools.DBFactory')
@patch('sam_sql_analytics_db_tool.tools.SecurityService')
async def test_tool_init_failure(mock_security, mock_db, tool_config, mock_component):
    """Test tool initialization failure handling."""
    mock_component.run_in_executor.side_effect = Exception("Connection failed")
    
    tool = SqlAnalyticsDbTool(tool_config)
    await tool.init(mock_component, tool_config)
    
    assert not tool._connection_healthy
    assert tool._connection_error is not None
    assert "Connection failed" in tool._connection_error

async def async_return(result):
    return result

@patch('sam_sql_analytics_db_tool.tools.DBFactory')
@patch('sam_sql_analytics_db_tool.tools.SecurityService')
async def test_query_execution(mock_security, mock_db, tool_config, mock_component):
    """Test SQL query execution."""
    # Set up successful initialization
    mock_component.run_in_executor.side_effect = [
        async_return({"tables": ["users"]}),
        async_return({"profiles": {}})
    ]
    
    # Mock security validation
    mock_security_instance = Mock()
    mock_security_instance.validate_query.return_value = {"valid": True}
    mock_security.return_value = mock_security_instance
    
    # Mock database query results
    mock_db_instance = Mock()
    mock_db_instance.run_select.return_value = [
        {"id": 1, "name": "test"}
    ]
    mock_db.return_value = mock_db_instance
    
    # Initialize and run query
    tool = SqlAnalyticsDbTool(tool_config)
    await tool.init(mock_component, tool_config)
    
    result = await tool._run_async_impl({"query": "SELECT * FROM users"})
    
    assert "result" in result
    assert result["result"] == [{"id": 1, "name": "test"}]
    mock_security_instance.validate_query.assert_called_once()
    mock_db_instance.run_select.assert_called_once()

@patch('sam_sql_analytics_db_tool.tools.DBFactory')
@patch('sam_sql_analytics_db_tool.tools.SecurityService')
async def test_invalid_query_rejection(mock_security, mock_db, tool_config, mock_component):
    """Test rejection of invalid queries."""
    # Set up successful initialization
    mock_component.run_in_executor.side_effect = [
        async_return({"tables": ["users"]}),
        async_return({"profiles": {}})
    ]
    
    # Mock security validation failure
    mock_security_instance = Mock()
    mock_security_instance.validate_query.return_value = {
        "valid": False,
        "reason": "Invalid query"
    }
    mock_security.return_value = mock_security_instance
    
    # Initialize and attempt invalid query
    tool = SqlAnalyticsDbTool(tool_config)
    await tool.init(mock_component, tool_config)
    
    result = await tool._run_async_impl({"query": "DROP TABLE users"})
    
    assert "error" in result
    assert "Invalid query" in result["error"]
    mock_security_instance.validate_query.assert_called_once()
    mock_db_instance = mock_db.return_value
    mock_db_instance.run_select.assert_not_called()
