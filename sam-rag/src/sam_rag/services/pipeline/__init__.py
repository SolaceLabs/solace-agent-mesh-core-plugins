"""
Pipeline package for the SAM RAG plugin.

This package contains the Pipeline class that orchestrates the RAG workflow,
coordinating between various components like scanners, preprocessors, splitters,
embedders, and vector databases.
"""

from .pipeline import Pipeline

__all__ = ["Pipeline"]
