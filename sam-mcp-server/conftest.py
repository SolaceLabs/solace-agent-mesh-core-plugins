"""
Configuration file for pytest.
This file adjusts the Python path to allow imports relative to the sam-mcp-server directory.
"""

import os
import sys
from pathlib import Path

# Add the sam-mcp-server directory to the Python path
sam_mcp_server_dir = Path(__file__).parent
sys.path.insert(0, str(sam_mcp_server_dir))
