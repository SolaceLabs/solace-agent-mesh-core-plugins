"""
Configuration file for pytest.
This file adjusts the Python path to allow imports relative to the sam-mcp-server directory.
"""

import os
import sys
from pathlib import Path
import unittest.mock as mock

# Add the sam-mcp-server directory to the Python path
sam_mcp_server_dir = Path(__file__).parent
sys.path.insert(0, str(sam_mcp_server_dir))

# Mock the mcp module if it's not available
try:
    import mcp
except ImportError:
    # Create a mock module for mcp
    mcp_mock = mock.MagicMock()
    sys.modules['mcp'] = mcp_mock
    sys.modules['mcp.server'] = mock.MagicMock()
    sys.modules['mcp.server.options'] = mock.MagicMock()
    sys.modules['mcp.server.stdio'] = mock.MagicMock()
    sys.modules['mcp.server.sse'] = mock.MagicMock()
    sys.modules['mcp.types'] = mock.MagicMock()
    sys.modules['mcp.shared'] = mock.MagicMock()
    sys.modules['mcp.shared.session'] = mock.MagicMock()
