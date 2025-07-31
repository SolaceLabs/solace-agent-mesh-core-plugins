"""
Database package for the SAM RAG plugin.

This package contains classes and utilities for interacting with vector databases,
including base classes and specific implementations for different vector database providers.
"""

from .vector_db_base import VectorDBBase
from .vector_db_service import VectorDBService

__all__ = ["VectorDBBase", "VectorDBService"]
