"""
Slack Gateway for A2A Agent Host.

DEPRECATED: This plugin is deprecated and will be removed in a future version.
Please migrate to sam-slack-gateway-adapter which uses the new gateway adapter framework.
See: https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/tree/main/sam-slack-gateway-adapter
"""

import warnings

warnings.warn(
    "sam-slack is deprecated. Please migrate to sam-slack-gateway-adapter "
    "which uses the new gateway adapter framework. "
    "See the sam-slack-gateway-adapter README for migration instructions.",
    DeprecationWarning,
    stacklevel=2,
)
