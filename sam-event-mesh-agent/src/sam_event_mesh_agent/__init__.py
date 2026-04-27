"""
Solace Agent Mesh - Event Mesh Agent Plugin

.. deprecated::
    This plugin is deprecated and may be removed in a future release.
    Please migrate to ``sam-event-mesh-tool``, which provides the same functionality
    but can be added to any agent, supports multiple instances with dedicated connections,
    and offers a more robust configuration.
"""

import warnings

warnings.warn(
    "sam-event-mesh-agent is deprecated and may be removed in a future release. "
    "Please migrate to sam-event-mesh-tool, which provides the same functionality "
    "but can be added to any agent, supports multiple instances with dedicated connections, "
    "and offers a more robust configuration. "
    "See the sam-event-mesh-tool README for migration instructions.",
    DeprecationWarning,
    stacklevel=2,
)
