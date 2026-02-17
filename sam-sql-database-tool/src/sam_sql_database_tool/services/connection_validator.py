"""Validation utilities for database connection strings."""

import re
import logging

from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError

log = logging.getLogger(__name__)


class ConnectionStringError(ValueError):
    """Raised when connection string validation fails."""
    pass

env_var_pattern = re.compile(r'''
    \$\{            
        [A-Za-z_][A-Za-z0-9_]*  
        \}              
        |
        \$[A-Za-z_][A-Za-z0-9_]*
''', re.VERBOSE)


def validate_connection_string(connection_string: str) -> None:
    """Validate database connection string format and required components.

    Args:
        connection_string: Database connection string to validate.

    Raises:
        ConnectionStringError: If validation fails with a descriptive message.
    """
    if not connection_string or not connection_string.strip():
        log.error("Connection string is empty or whitespace only")
        raise ConnectionStringError(
            "Database connection string is empty. "
            "Please provide a valid connection string."
        )

    env_vars = env_var_pattern.findall(connection_string)
    if env_vars:
        log.error("Connection string contains unresolved environment variables: %s", env_vars)
        raise ConnectionStringError(
            f"Database connection string contains unresolved environment variable(s): {', '.join(env_vars)}. "
            "Ensure the environment variable is set and properly configured."
        )

    try:
        url = make_url(connection_string)
    except ArgumentError as e:
        log.error("Invalid connection string format: %s", e)
        raise ConnectionStringError(
            f"Invalid database connection string format: {e}. "
            "Expected format: dialect+driver://user:password@host:port/database"
        ) from e

    if not url.drivername:
        log.error("Connection string missing database dialect")
        raise ConnectionStringError(
            "Database connection string missing dialect (e.g., postgresql, mysql). "
            "Expected format: dialect+driver://user:password@host:port/database"
        )

    if not url.host:
        log.error("Connection string missing host")
        raise ConnectionStringError(
            "Database connection string missing host. "
            "Expected format: dialect+driver://user:password@host:port/database"
        )

    log.debug(
        "Connection string validated: dialect=%s, host=%s, database=%s",
        url.drivername, url.host, url.database
    )
