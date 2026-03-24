"""
Solace Agent Mesh - Mermaid Plugin

.. deprecated::
    This plugin is deprecated and may be removed in a future release.
    The mermaid diagram generator is now available as a built-in tool in the
    core solace-agent-mesh. Add it to your agent configuration instead:

        tools:
          - tool_type: builtin
            tool_name: "mermaid_diagram_generator"
"""

import warnings

warnings.warn(
    "sam-mermaid is deprecated and may be removed in a future release. "
    "The mermaid diagram generator is now built into the core solace-agent-mesh. "
    "Add it directly to your agent configuration using: "
    "tool_type: builtin, tool_name: mermaid_diagram_generator",
    DeprecationWarning,
    stacklevel=2,
)

from .draw import draw