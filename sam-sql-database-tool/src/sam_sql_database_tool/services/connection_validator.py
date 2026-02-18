"""Validation utilities for database connection strings."""

import re
import logging
from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError

log = logging.getLogger(__name__)

EXPECTED_URL_FORMAT = "dialect+driver://user:password@host:port/database?param=value"

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

    try:
        url = make_url(connection_string)
    except ArgumentError as e:
        raise ValueError(
            f"Invalid database connection string format: {e}. "
            f"Expected URL format: {EXPECTED_URL_FORMAT}"
        ) from e
    except ValueError as e:
        message = str(e)
        if "invalid literal for int() with base 10" in message:
            message = "Invalid port number in connection string"
        raise ValueError(f"Failed to parse database connection string: {message}") from e

    if not url.drivername:
        raise ValueError(
            "Database connection string missing dialect (e.g., postgresql, mysql). "
            f"Expected URL format: {EXPECTED_URL_FORMAT}"
        )

    if not url.host:
        raise ValueError(
            "Database connection string missing host. "
            f"Expected URL format: {EXPECTED_URL_FORMAT}"
        )

    log.debug(
        "Connection string validated: dialect=%s, host=%s, database=%s",
        url.drivername, url.host, url.database
    )
    return connection_string