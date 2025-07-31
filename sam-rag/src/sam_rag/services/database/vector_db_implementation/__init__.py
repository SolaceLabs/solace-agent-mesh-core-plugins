"""
Vector DB Implementations Package.

This package contains specific implementations for various vector databases.
"""

from sam_rag.services.database.vector_db_implementation.pinecone_db import PineconeDB
from sam_rag.services.database.vector_db_implementation.qdrant_db import QdrantDB
from sam_rag.services.database.vector_db_implementation.redis_legacy_db import RedisDB as RedisLegacyDB  # Alias to avoid name clash
from sam_rag.services.database.vector_db_implementation.pgvector_db import PgVectorDB
from sam_rag.services.database.vector_db_implementation.chroma_db import ChromaDB
from sam_rag.services.database.vector_db_implementation.redis_vl_db import RedisDB as RedisVLDB  # Alias for the redisvl version

# You can define an __all__ list if you want to specify what gets imported
# when a client does 'from . import *'
__all__ = [
    "PineconeDB",
    "QdrantDB",
    "RedisLegacyDB",  # Use the alias
    "PgVectorDB",
    "ChromaDB",
    "RedisVLDB",  # Use the alias
]

# Optional: A dictionary mapping names to classes for easier dynamic loading
IMPLEMENTATIONS = {
    "pinecone": PineconeDB,
    "qdrant": QdrantDB,
    "redis_legacy": RedisLegacyDB,
    "pgvector": PgVectorDB,
    "chroma": ChromaDB,
    "redis_vl": RedisVLDB,
}
