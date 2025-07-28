"""
PostgreSQL with pgvector extension vector database implementation.
"""

import uuid
import json
from typing import Dict, Any, List, Optional
from solace_ai_connector.common.log import log as logger

from ..vector_db_base import VectorDBBase


class PgVectorDB(VectorDBBase):
    """
    Vector database using PostgreSQL with pgvector extension.
    """

    def __init__(
        self,
        config: Dict[str, Any] = None,
        hybrid_search_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the PostgreSQL vector database.

        Args:
            config: A dictionary containing configuration parameters.
                - host: The PostgreSQL host (default: "localhost").
                - port: The PostgreSQL port (default: 5432).
                - database: The database name (default: "vectordb").
                - user: The PostgreSQL user (default: "postgres").
                - password: The PostgreSQL password (optional).
                - table_name: The name of the table to use (default: "documents").
                - embedding_dimension: The dimension of the embeddings (default: 768).
            hybrid_search_config: Optional dictionary containing hybrid search configuration.
                                  Note: This PgVectorDB implementation does not support hybrid search.
        """
        super().__init__(config=config, hybrid_search_config=hybrid_search_config)
        if self.hybrid_search_enabled:
            logger.warning(
                "PgVectorDB: Hybrid search was enabled in config, but this implementation "
                "does not support hybrid search. It will operate in dense-only mode."
            )
            self.hybrid_search_enabled = False

        self.host = self.config.get("host", "localhost")
        self.port = self.config.get("port", 5432)
        self.database = self.config.get("database", "vectordb")
        self.user = self.config.get("user", "postgres")
        self.password = self.config.get("password")

        self.table_name = self.config.get("table_name", "documents")
        self.embedding_dimension = self.config.get("embedding_dimension", 768)
        self.conn = None
        self._setup_client()

    def _setup_client(self) -> None:
        """
        Set up the PostgreSQL client.
        """
        try:
            import psycopg2
            from psycopg2.extras import execute_values  # For efficient batch inserts if needed later

            # First connect to the default postgres database to check if our database exists
            default_conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database="postgres",  # Connect to default database first
                user=self.user,
                password=self.password,
            )
            default_conn.autocommit = True  # Set autocommit mode for database creation

            with default_conn.cursor() as cursor:
                # Check if the database exists
                cursor.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s", (self.database,)
                )
                database_exists = cursor.fetchone() is not None

                # Create the database if it doesn't exist
                if not database_exists:
                    cursor.execute(
                        f"CREATE DATABASE {self.database}"
                    )  # Safe due to prior checks
                    logger.info(f"Created database '{self.database}'.")

            # Close the connection to the default database
            default_conn.close()

            # Now connect to the target database
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
            )

            # Create the pgvector extension if it doesn't exist
            with self.conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                # Create the table if it doesn't exist
                # Ensure table_name is sanitized or use placeholders if it could be dynamic from untrusted source
                # For now, assuming table_name from config is safe.
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        id TEXT PRIMARY KEY,
                        text TEXT NOT NULL,
                        embedding vector({self.embedding_dimension}) NOT NULL,
                        metadata JSONB
                    );
                """
                )

                # Create an index for vector similarity search
                # Index name needs to be unique, incorporate table_name
                index_name = f"{self.table_name}_embedding_idx"
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON {self.table_name}
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100);
                """
                )  # Consider HNSW for better performance on larger datasets: USING hnsw (embedding vector_cosine_ops)

                self.conn.commit()
        except ImportError:
            raise ImportError(
                "The psycopg2 package is required for PgVectorDB. "
                "Please install it with `pip install psycopg2-binary`."
            ) from None
        except psycopg2.Error as e:  # Catch psycopg2 specific errors
            logger.error(f"PostgreSQL connection or setup error: {e}")
            raise ConnectionError(
                f"Failed to connect to or set up PostgreSQL database: {e}"
            ) from e
        except Exception as e:  # Catch other potential errors
            logger.error(f"An unexpected error occurred during PgVectorDB setup: {e}")
            raise ValueError(
                f"An error occurred while setting up the PostgreSQL client: {e}"
            ) from e

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        sparse_vectors: Optional[List[Optional[Dict[int, float]]]] = None,
    ) -> List[str]:
        """
        Add documents to the vector database. PgVectorDB only supports dense vectors.

        Args:
            documents: The documents to add.
            embeddings: The embeddings of the documents.
            metadatas: Optional metadata for each document.
            ids: Optional IDs for each document.
            sparse_vectors: Ignored by this implementation.

        Returns:
            The IDs of the added documents.
        """
        if sparse_vectors:
            logger.warning(
                "PgVectorDB: 'sparse_vectors' parameter was provided but will be ignored as PgVectorDB currently only supports dense vectors through this interface."
            )

        if not documents or not embeddings:
            return []

        # Generate IDs if not provided
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(len(documents))]

        # Create default metadata if not provided
        if metadatas is None:
            metadatas = [{"source": "unknown"} for _ in range(len(documents))]

        # Add the documents
        with self.conn.cursor() as cursor:
            for i in range(len(documents)):
                # Convert metadata to JSON string
                metadata_json = json.dumps(
                    metadatas[i] if metadatas and i < len(metadatas) else {}
                )

                # Insert the document
                cursor.execute(
                    f"""
                    INSERT INTO {self.table_name} (id, text, embedding, metadata)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET text = EXCLUDED.text,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata;
                    """,
                    (ids[i], documents[i], embeddings[i], metadata_json),
                )

            self.conn.commit()

        return ids

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
        query_sparse_vector: Optional[Dict[int, float]] = None,
        request_hybrid: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query embedding. PgVectorDB only supports dense search.

        Args:
            query_embedding: The query embedding.
            top_k: The number of results to return.
            filter: Optional filter to apply to the search. Example: {"source": "website"}
            query_sparse_vector: Ignored.
            request_hybrid: Ignored.

        Returns:
            A list of dictionaries containing the search results.
        """
        if request_hybrid or query_sparse_vector:
            logger.warning(
                "PgVectorDB: 'request_hybrid' was true or 'query_sparse_vector' was provided, "
                "but PgVectorDB currently only supports dense search through this interface. Proceeding with dense search."
            )

        # Prepare the query
        # Using <=> for cosine distance (0=exact match, 1=orthogonal, 2=opposite)
        # Similarity = 1 - distance for cosine
        query_sql = f"""
            SELECT id, text, metadata, 1 - (embedding <=> %s::vector({self.embedding_dimension})) as similarity
            FROM {self.table_name}
        """

        params: list = [query_embedding]  # Type hint for params

        # Add filter if provided
        # This is a basic filter for JSONB metadata. More complex queries might be needed for nested fields or arrays.
        if filter:
            filter_conditions = []
            for key, value in filter.items():
                # For JSONB, use @> for containment if value is an object/array, or ->> for text field match
                # Assuming simple key-value string matches for now
                filter_conditions.append(f"metadata->>%s = %s")
                params.extend(
                    [key, str(value)]
                )  # Ensure value is string for ->> comparison

            if filter_conditions:
                filter_str = " AND ".join(filter_conditions)
                query_sql += f" WHERE {filter_str}"

        # Add order by and limit
        query_sql += f" ORDER BY similarity DESC LIMIT %s"
        params.append(top_k)

        # Execute the search
        with self.conn.cursor() as cursor:
            cursor.execute(query_sql, tuple(params))  # Pass params as a tuple
            results = cursor.fetchall()

        # Format the results
        formatted_results = []
        for result_row in results:  # Use a more descriptive variable name
            doc_id, text, metadata_db, similarity_score = result_row  # Unpack directly

            # metadata_db is already a dict if JSONB, no need to json.loads unless it was stored as text
            # psycopg2 typically converts JSONB to dict automatically.

            formatted_results.append(
                {
                    "id": doc_id,
                    "text": text,
                    "metadata": metadata_db
                    if metadata_db
                    else {},  # Ensure it's a dict
                    "distance": 1 - similarity_score,  # distance = 1 - similarity
                }
            )

        return formatted_results

    def delete(self, ids: List[str]) -> None:
        """
        Delete documents from the vector database.

        Args:
            ids: The IDs of the documents to delete.
        """
        if not ids:
            return
        # Delete the documents
        with self.conn.cursor() as cursor:
            # Using ANY for a list of IDs
            cursor.execute(
                f"DELETE FROM {self.table_name} WHERE id = ANY(%s::text[])",  # Cast to text array
                (ids,),
            )
            self.conn.commit()

    def get(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get documents from the vector database.

        Args:
            ids: The IDs of the documents to get.

        Returns:
            A list of dictionaries containing the documents.
        """
        if not ids:
            return []
        # Get the documents
        with self.conn.cursor() as cursor:
            cursor.execute(
                f"SELECT id, text, embedding, metadata FROM {self.table_name} WHERE id = ANY(%s::text[])",
                (ids,),
            )
            results = cursor.fetchall()

        # Format the results
        formatted_results = []
        for result_row in results:
            doc_id, text, embedding_val, metadata_db = result_row

            formatted_results.append(
                {
                    "id": doc_id,
                    "text": text,
                    "metadata": metadata_db if metadata_db else {},
                    "embedding": list(embedding_val)
                    if embedding_val
                    else [],  # pgvector returns np.array like, convert to list
                }
            )
        return formatted_results

    def update(
        self,
        ids: List[str],
        documents: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        sparse_vectors: Optional[List[Optional[Dict[int, float]]]] = None,
    ) -> None:
        """
        Update documents in the vector database.
        This performs an UPSERT. If document/embedding/metadata is not provided for an ID,
        the existing value for that field will be retained if using COALESCE,
        or overwritten if using EXCLUDED (as in add_documents).
        For simplicity, this update will overwrite fields if new values are provided,
        similar to the ON CONFLICT clause in add_documents.

        Args:
            ids: The IDs of the documents to update.
            documents: Optional new document contents.
            embeddings: Optional new embeddings.
            metadatas: Optional new metadata.
            sparse_vectors: Ignored.
        """
        if sparse_vectors:
            logger.warning(
                "PgVectorDB: 'sparse_vectors' parameter was provided but will be ignored."
            )

        if not ids:
            return

        # Prepare data for update
        # We'll build a list of tuples for execute_values for efficiency if we were doing many updates
        # For now, iterating and executing one by one for clarity, similar to add_documents.
        # A more optimized version might fetch existing, merge, then update.
        # Or use complex SQL UPDATE FROM VALUES.

        with self.conn.cursor() as cursor:
            for i, doc_id in enumerate(ids):
                # Build SET clause dynamically
                set_clauses = []
                params_update: list = []

                current_doc_data = None  # To fetch existing if only partial update is desired for some fields

                if documents and i < len(documents) and documents[i] is not None:
                    set_clauses.append("text = %s")
                    params_update.append(documents[i])
                elif (
                    documents
                    and i < len(documents)
                    and documents[i] is None
                    and (embeddings is None or embeddings[i] is None)
                    and (metadatas is None or metadatas[i] is None)
                ):
                    # If only text is explicitly set to None, and nothing else is being updated for this ID, skip text update
                    pass

                if embeddings and i < len(embeddings) and embeddings[i] is not None:
                    set_clauses.append("embedding = %s")
                    # pgvector expects list or np.array for vector type
                    params_update.append(list(embeddings[i]))
                elif (
                    embeddings
                    and i < len(embeddings)
                    and embeddings[i] is None
                    and (documents is None or documents[i] is None)
                    and (metadatas is None or metadatas[i] is None)
                ):
                    pass

                if metadatas and i < len(metadatas) and metadatas[i] is not None:
                    set_clauses.append("metadata = %s")
                    params_update.append(json.dumps(metadatas[i]))
                elif (
                    metadatas
                    and i < len(metadatas)
                    and metadatas[i] is None
                    and (documents is None or documents[i] is None)
                    and (embeddings is None or embeddings[i] is None)
                ):
                    pass

                if not set_clauses:
                    logger.debug(
                        f"No update data provided for ID {doc_id}, skipping update."
                    )
                    continue

                params_update.append(doc_id)  # For WHERE id = %s

                update_sql = f"UPDATE {self.table_name} SET {', '.join(set_clauses)} WHERE id = %s"

                cursor.execute(update_sql, tuple(params_update))
            self.conn.commit()

    def count(self) -> int:
        """
        Get the number of documents in the vector database.

        Returns:
            The number of documents.
        """
        with self.conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            result = cursor.fetchone()
        return result[0] if result and result[0] is not None else 0

    def clear(self) -> None:
        """
        Clear all documents from the vector database.
        """
        with self.conn.cursor() as cursor:
            cursor.execute(f"DELETE FROM {self.table_name}")
            self.conn.commit()

    def __del__(self):
        """
        Close the database connection when the object is deleted.
        """
        if self.conn:
            self.conn.close()
            logger.info("PostgreSQL connection closed.")
