#!/usr/bin/env python3
"""
Shared plugin exceptions for synchronization/validation scripts.
"""

from __future__ import annotations

# Plugins that still exist in the repository but should not be auto-managed
# in release/config synchronization files.
DEPRECATED_PLUGINS = {
    "sam-event-mesh-agent",
    "sam-slack",
    "sam-sql-database",
    "sam-webhook-gateway",
}

