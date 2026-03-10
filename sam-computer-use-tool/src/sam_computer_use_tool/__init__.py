"""
sam-computer-use-tool: Browser automation plugin for Solace Agent Mesh.

Provides Playwright-based browser control with artifact storage for screenshots.
"""

from .tools import ComputerUseTool
from .config import ComputerUseToolConfig

__all__ = ["ComputerUseTool", "ComputerUseToolConfig"]
