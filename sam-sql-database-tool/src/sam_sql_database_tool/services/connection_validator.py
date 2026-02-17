"""Validation utilities for database connection strings."""

import re
import logging
from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError

log = logging.getLogger(__name__)


env_var_pattern = re.compile(r'''
    \$\{
        [A-Za-z_][A-Za-z0-9_]*
    \}
    |
    \$\{\}
    |
    \$[A-Za-z_][A-Za-z0-9_]*
''', re.VERBOSE)


def validate_connection_string(connection_string: str) -> str:
    """Validate database connection string format and required components.

    Args:
        connection_string: Database connection string to validate.

    Returns:
        The validated connection string.

    Raises:
        ValueError: If validation fails with a descriptive message.
    """
    if not connection_string or not connection_string.strip():
        raise ValueError(
            "Database connection string is empty. "
            "Please provide a valid connection string."
        )

    env_vars = env_var_pattern.findall(connection_string)
    if env_vars:
        raise ValueError(
            f"Database connection string contains unresolved environment variable(s): {', '.join(env_vars)}. "
            "Ensure the environment variable is set and properly configured."
        )

    try:
        url = make_url(connection_string)
    except (ArgumentError) as e:
        raise ValueError(
            f"Invalid database connection string format: {e}. "
            "Expected format: dialect+driver://user:password@host:port/database"
        ) from e
    except ValueError as e:
        message = str(e)
        if "invalid literal for int() with base 10" in message:
            message = "Invalid port number in connection string"
        raise ValueError(f"Failed to parse database connection string: {message}") from e

    if not url.drivername:
        raise ValueError(
            "Database connection string missing dialect (e.g., postgresql, mysql). "
            "Expected format: dialect+driver://user:password@host:port/database"
        )

    if not url.host:
        raise ValueError(
            "Database connection string missing host. "
            "Expected format: dialect+driver://user:password@host:port/database"
        )

    log.debug(
        "Connection string validated: dialect=%s, host=%s, database=%s",
        url.drivername, url.host, url.database
    )
    return connection_string


class ValidatedConnectionString(str):
    """A string type that validates database connection strings via Pydantic."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls._validate,
            core_schema.str_schema(),
        )

    @classmethod
    def _validate(cls, value: str) -> str:
        validate_connection_string(value)
        return value
