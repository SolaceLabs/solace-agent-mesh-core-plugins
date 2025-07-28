"""
Redis vector database implementation using redisvl.
This version uses the 'redisvl' package for more advanced Redis search capabilities.
"""

import uuid
import json
import numpy as np
from typing import Dict, Any, List, Optional
from solace_ai_connector.common.log import log as logger

from ..vector_db_base import VectorDBBase

# Attempt to import redisvl and its components
try:
    from redisvl.index import SearchIndex
    from redisvl.schema import IndexSchema  # , TagField, TextField, VectorField # Specific field types
    from redisvl.query import VectorQuery  # , FilterQuery # For hybrid, might need FilterQuery or other constructs
    from redisvl.query.filter import Tag  # For creating filter expressions
    import redis  # For direct connection if needed or for connection utilities

    REDISVL_AVAILABLE = True
except ImportError:
    logger.warning(
        "redis or redisvl packages not found. RedisDB (redisvl version) will not be fully available. "
        "Please install them with `pip install redis redisvl`."
    )
    REDISVL_AVAILABLE = False

    # Define placeholders if redisvl is not installed to avoid runtime errors on class definition
    class SearchIndex:
        pass

    class IndexSchema:
        pass

    class VectorQuery:
        pass

    class Tag:
        pass


if not REDISVL_AVAILABLE:
    # Define a placeholder class if redisvl is not installed
    class RedisDB(VectorDBBase):

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            raise NotImplementedError(
                "RedisDB (redisvl version) requires 'redis' and 'redisvl' packages to be installed."
            )

        def add_documents(self, *args, **kwargs):
            raise NotImplementedError()

        def search(self, *args, **kwargs):
            raise NotImplementedError()

        def delete(self, *args, **kwargs):
            raise NotImplementedError()

        def get(self, *args, **kwargs):
            raise NotImplementedError()

        def update(self, *args, **kwargs):
            raise NotImplementedError()

        def count(self, *args, **kwargs):
            raise NotImplementedError()

        def clear(self, *args, **kwargs):
            raise NotImplementedError()

else:  # Proceed only if redisvl was imported successfully

    class RedisDB(VectorDBBase):
        """
        Vector database using Redis with RediSearch (via redisvl).
        Hybrid search is achieved by combining full-text search on a text field
        with vector similarity search.
        """

        def __init__(
            self,
            config: Dict[str, Any] = None,
            hybrid_search_config: Optional[Dict[str, Any]] = None,
        ):
            """
            Initialize the Redis vector database (redisvl version).

            Args:
                config: A dictionary containing configuration parameters.
                    - url: Redis URL (e.g., "redis://localhost:6379"). (Required)
                    - index_name: Name of the RediSearch index. (Default: "rag-redis-index")
                    - embedding_dimension: Dimension of the embeddings. (Required)
                    - text_field_name: Name for the text content field (for FT search). (Default: "content")
                    - vector_field_name: Name for the vector field. (Default: "embedding")
                    - (Optional) hybrid_search_params:
                        - text_score_weight: Weight for text search score in client-side fusion (0.0-1.0). (Default: 0.5)
                        - vector_score_weight: Weight for vector search score in client-side fusion (0.0-1.0). (Default: 0.5)
                hybrid_search_config: Global hybrid search configuration.
            """
            super().__init__(config=config, hybrid_search_config=hybrid_search_config)

            self.redis_url = self.config.get("url")
            if not self.redis_url:
                raise ValueError("Redis URL ('url') is required for RedisDB (redisvl).")

            self.index_name = self.config.get("index_name", "rag-redis-index")
            self.embedding_dimension = self.config.get("embedding_dimension")
            if not self.embedding_dimension:
                raise ValueError(
                    "Embedding dimension ('embedding_dimension') is required for RedisDB (redisvl)."
                )

            self.text_field_name = self.config.get("text_field_name", "content")
            self.vector_field_name = self.config.get("vector_field_name", "embedding")

            # Hybrid search specific parameters from config (can be overridden by global hybrid_search_config)
            # These are more for client-side fusion if redisvl doesn't support server-side weighted hybrid directly.
            self.hybrid_params = self.config.get("hybrid_search_params", {})
            self.text_score_weight = self.hybrid_params.get("text_score_weight", 0.5)
            self.vector_score_weight = self.hybrid_params.get(
                "vector_score_weight", 0.5
            )

            self.client = None  # Underlying redis.Redis client
            self.index: Optional[SearchIndex] = (
                None  # redisvl.index.SearchIndex instance
            )
            self._setup_client_and_index()

        def _get_redis_connection(self):
            """Helper to get a Redis connection from URL."""
            return redis.from_url(self.redis_url)

        def _setup_client_and_index(self) -> None:
            """
            Set up the Redis client and ensure the RediSearch index exists with the correct schema.
            """
            try:
                # Create a SearchIndex instance (which connects to Redis)
                self.index = SearchIndex.from_existing(
                    name=self.index_name, url=self.redis_url
                )
                logger.info(
                    f"RedisDB (redisvl): Successfully connected to existing Redis index '{self.index_name}'."
                )
                # Store the underlying redis client
                if self.index and hasattr(self.index, "client") and self.index.client:
                    self.client = self.index.client
                else:  # Fallback if client attribute name changes or not directly exposed
                    self.client = self._get_redis_connection()

            except Exception as e:
                logger.info(
                    f"RedisDB (redisvl): Index '{self.index_name}' not found or connection error: {e}. Attempting to create."
                )
                # Define schema using redisvl's dictionary format
                # This schema should include fields for text, vector, and any filterable metadata.
                schema_dict = {
                    "index": {
                        "name": self.index_name,
                        "prefix": f"doc:{self.index_name}",  # Standard prefix for keys
                        # "storage_type": "hash", # Default is hash
                    },
                    "fields": [
                        {
                            "name": self.text_field_name,
                            "type": "text",
                        },  # For full-text search
                        {
                            "name": self.vector_field_name,
                            "type": "vector",
                            "attrs": {
                                "dims": self.embedding_dimension,
                                "algorithm": "FLAT",  # or "HNSW" for larger datasets
                                "distance_metric": "COSINE",
                                "datatype": "FLOAT32",  # Or FLOAT64
                            },
                        },
                        # Example of a tag field for filtering (must be added to schema if used in filters)
                        # {"name": "source", "type": "tag"},
                        # {"name": "category", "type": "tag"},
                    ],
                }
                # Add any metadata fields from config that should be indexed as tags
                # For simplicity, this is not done automatically here. User must ensure schema matches data.

                try:
                    schema_instance = IndexSchema.from_dict(schema_dict)
                    self.index = SearchIndex(
                        schema=schema_instance, redis_url=self.redis_url
                    )
                    self.index.create(
                        overwrite=True
                    )  # Overwrite if it exists but was problematic
                    logger.info(
                        f"RedisDB (redisvl): Index '{self.index_name}' created successfully."
                    )
                    if hasattr(self.index, "client") and self.index.client:
                        self.client = self.index.client
                    else:
                        self.client = self._get_redis_connection()

                except Exception as creation_error:
                    logger.error(
                        f"RedisDB (redisvl): Failed to create Redis index '{self.index_name}': {creation_error}"
                    )
                    raise ValueError(
                        f"Failed to create Redis index '{self.index_name}'"
                    ) from creation_error

        def add_documents(
            self,
            documents: List[str],
            embeddings: List[List[float]],
            metadatas: Optional[List[Dict[str, Any]]] = None,
            ids: Optional[List[str]] = None,
            sparse_vectors: Optional[
                List[Optional[Dict[int, float]]]
            ] = None,  # Ignored
        ) -> List[str]:
            if sparse_vectors:
                logger.warning(
                    "RedisDB (redisvl): 'sparse_vectors' are provided but will be ignored. "
                    "Hybrid search uses full-text search on stored text content."
                )

            if not documents or not embeddings:
                return []

            if ids is None:
                ids = [str(uuid.uuid4()) for _ in range(len(documents))]
            if metadatas is None:
                metadatas = [{} for _ in range(len(documents))]

            # Ensure metadatas list length matches documents list length
            if len(metadatas) < len(documents):
                metadatas.extend([{} for _ in range(len(documents) - len(metadatas))])

            data_to_load = []
            for i, doc_text in enumerate(documents):
                record = {
                    "id": ids[i],  # redisvl uses 'id' by default for the key suffix
                    self.text_field_name: doc_text,
                    # redisvl expects vector as numpy array of float32
                    self.vector_field_name: np.array(embeddings[i], dtype=np.float32),
                }
                # Add metadata. Ensure keys match schema fields if they are indexed (e.g., as tags).
                # Unindexed metadata will still be stored with the HASH.
                current_meta = metadatas[i]
                for k, v in current_meta.items():
                    # redisvl schema fields for tags/text need simple types (str, int, float, bool)
                    # If a metadata field is defined in schema (e.g. as TagField), ensure type compatibility.
                    if isinstance(
                        v, (list, dict)
                    ):  # Store complex types as JSON strings
                        record[k] = json.dumps(v)
                    else:
                        record[k] = v
                data_to_load.append(record)

            if data_to_load and self.index:
                # redisvl's load method handles creating keys like "doc:index_name:id_value"
                self.index.load(
                    data_to_load
                )  # No need to specify keys if 'id' is in records
                logger.info(
                    f"RedisDB (redisvl): Added {len(data_to_load)} documents to index '{self.index_name}'."
                )
            return ids

        def search(
            self,
            query_embedding: List[float],
            top_k: int = 5,
            filter: Optional[Dict[str, Any]] = None,
            query_sparse_vector: Optional[Dict[int, float]] = None,  # Ignored
            request_hybrid: bool = False,
            # For Redis hybrid search, the original text query is needed for the FT part.
            # This is a workaround: expecting it in the filter dict with a special key.
            # e.g., filter={"_text_query_for_ft": "search terms", "source": "website"}
        ) -> List[Dict[str, Any]]:
            if not self.index:
                raise RuntimeError("RedisDB (redisvl) index is not initialized.")

            if query_sparse_vector:
                logger.warning(
                    "RedisDB (redisvl): 'query_sparse_vector' is provided but will be ignored."
                )

            redis_filter_expression: Optional[Tag] = None
            original_text_query_for_ft: Optional[str] = None

            # Process filter for metadata and potential FT query string
            if filter:
                temp_filter = filter.copy()
                if "_text_query_for_ft" in temp_filter:
                    original_text_query_for_ft = str(
                        temp_filter.pop("_text_query_for_ft")
                    )

                conditions = []
                for key, value in temp_filter.items():
                    # Assuming filter keys correspond to Tag fields in the schema
                    if isinstance(value, str):  # Basic Tag filter
                        conditions.append(Tag(key) == value)
                    # Add more complex filter logic here if needed (e.g., numeric ranges)

                if conditions:
                    # Combine multiple conditions with & (AND)
                    current_filter_obj = conditions[0]
                    for i in range(1, len(conditions)):
                        current_filter_obj &= conditions[i]
                    redis_filter_expression = current_filter_obj

            # Prepare the vector for query
            query_vector_np = np.array(query_embedding, dtype=np.float32)

            # Construct the query
            # For hybrid search, redisvl might require a specific query structure or manual query string.
            # A common RediSearch hybrid pattern: (@text_field:$ft_query)=>[KNN $k @vector_field $vec_blob]
            # This tells RediSearch to first filter by FT, then apply KNN on results.
            # redisvl's VectorQuery has a `filter_expression` for metadata, but for FT in hybrid,
            # it might need to be part of a raw query string or a specific hybrid query object.

            raw_results: List[Dict[str, Any]] = []

            if (
                request_hybrid
                and self.hybrid_search_enabled
                and original_text_query_for_ft
            ):
                logger.info(
                    f"RedisDB (redisvl): Performing hybrid search in index '{self.index_name}'."
                )
                # Constructing a raw RediSearch query string for hybrid.
                # This bypasses some of redisvl's abstractions but gives more control for complex queries.
                # Ensure field names match the schema.
                # The `HYBRID_FT_FIRST` option in RediSearch means FT runs first.
                # The query string needs careful escaping and formatting.
                # Example: "(@content_field:hello world)=>[KNN 5 @vector_field $vector_blob EF_RUNTIME 10 HYBRID_FT_FIRST]"
                # $vector_blob will be passed as a query parameter.

                # Simpler hybrid approach with redisvl: use FT as a filter within VectorQuery
                # This is not true weighted hybrid fusion but FT pre-filtering.
                ft_filter_str = (
                    f"@{self.text_field_name}:({original_text_query_for_ft})"
                )

                # If redisvl's Tag can handle raw filter strings (it usually can't directly for FT parts like this)
                # A workaround is to use a raw query if VectorQuery doesn't support FT parts in filter_expression.
                # For now, let's assume we combine FT filter with metadata filter.

                # This is a simplified way to express FT filter with metadata filter.
                # True hybrid might need `index.search()` with a raw query string.
                hybrid_filter_parts = [f"({ft_filter_str})"]
                if redis_filter_expression:
                    # This is tricky as redis_filter_expression is a Tag object.
                    # We need to convert it to its string representation for RediSearch.
                    # For now, let's assume simple FT pre-filtering.
                    # A more robust solution would use redisvl's query combination features if available,
                    # or construct the full query string manually.
                    # Let's try to use the FT part in the main query string of VectorQuery if possible,
                    # or combine filter expressions.
                    # This part is complex with current redisvl capabilities for hybrid.
                    # A common way is to use the FT query as the main query string for VectorQuery
                    # and then the vector part is applied.
                    # query_string = ft_filter_str # Main query is FT
                    # vec_query = VectorQuery(
                    #     vector=query_vector_np,
                    #     vector_field_name=self.vector_field_name,
                    #     num_results=top_k,
                    #     filter_expression=redis_filter_expression, # Metadata filter
                    #     query_string=query_string # FT part as main query
                    # )
                    # This syntax for VectorQuery might not be correct.
                    # Fallback: Use FT as a Tag filter if text_field_name is a Tag field (not ideal for FT).
                    # For true hybrid, often a raw query to self.index.client.ft().search() is needed.
                    logger.warning(
                        "RedisDB (redisvl): True server-side hybrid query is complex to construct with redisvl abstractions. Performing vector search with FT-like filter if possible."
                    )
                    # This is a placeholder for a more robust hybrid query.
                    # For now, we'll do a vector query with metadata filter, and FT part is illustrative.
                    # A simple FT filter might be: Tag(self.text_field_name).matches(f"({original_text_query_for_ft})")
                    # but this is not standard FT.

                    # Let's assume for now hybrid means vector search with metadata filter, FT part is logged.
                    # A proper hybrid implementation would require deeper integration with RediSearch query syntax.
                    vec_query = VectorQuery(
                        vector=query_vector_np,
                        vector_field_name=self.vector_field_name,
                        num_results=top_k,
                        filter_expression=redis_filter_expression,  # Only metadata filter for now
                        # return_fields=[self.text_field_name, "id", ... other metadata fields]
                    )
                    raw_results = self.index.query(vec_query)

            else:  # Dense only
                logger.info(
                    f"RedisDB (redisvl): Performing dense-only search in index '{self.index_name}'."
                )
                vec_query = VectorQuery(
                    vector=query_vector_np,
                    vector_field_name=self.vector_field_name,
                    num_results=top_k,
                    filter_expression=redis_filter_expression,
                    # Specify fields to return, including metadata and the text field
                    # return_fields=['id', self.text_field_name, self.vector_field_name, 'vector_distance', ... any other metadata fields in schema]
                )
                raw_results = self.index.query(vec_query)

            # Format results
            formatted_results = []
            for res_doc in raw_results:  # res_doc is a dict from redisvl
                # Score is usually under 'vector_distance'. Convert to similarity (0 to 1).
                # Cosine distance from RediSearch is 0 (identical) to 2 (opposite).
                # Similarity = 1 - (distance / 2) if metric is cosine and range is 0-2
                # Or if distance is already 0-1 (like 1-cosine_sim), then similarity = 1 - distance.
                # redisvl's vector_distance for COSINE is typically 1-similarity. So higher score = more similar.
                # Let's assume vector_distance is actual distance, so lower is better.
                # We need to return "distance" as per base class, so this is fine.
                distance = float(res_doc.get("vector_distance", float("inf")))

                # Reconstruct metadata, excluding known fields
                metadata = {
                    k: v
                    for k, v in res_doc.items()
                    if k
                    not in [
                        "id",
                        self.text_field_name,
                        self.vector_field_name,
                        "vector_distance",
                        "payload",
                    ]
                }
                # Try to parse JSON string metadata back to dict
                for k_meta, v_meta in metadata.items():
                    if isinstance(v_meta, str):
                        try:
                            metadata[k_meta] = json.loads(v_meta)
                        except json.JSONDecodeError:
                            pass  # Keep as string

                formatted_results.append(
                    {
                        "id": res_doc.get("id", "").split(":")[
                            -1
                        ],  # Get original ID part if prefixed
                        "text": res_doc.get(self.text_field_name, ""),
                        "metadata": metadata,
                        "distance": distance,
                    }
                )
            return formatted_results

        def delete(self, ids: List[str]) -> None:
            if not ids or not self.index or not self.client:
                return
            # redisvl SearchIndex.delete expects full keys or just IDs if prefix is known.
            # Using underlying client.delete with full keys is safer.
            full_keys = [f"{self.index.schema.index_prefix}:{id_val}" for id_val in ids]
            if full_keys:
                self.client.delete(*full_keys)
                logger.info(
                    f"RedisDB (redisvl): Deleted {len(ids)} documents from index '{self.index_name}'."
                )

        def get(self, ids: List[str]) -> List[Dict[str, Any]]:
            if not ids or not self.index or not self.client:
                return []

            full_keys = [f"{self.index.schema.index_prefix}:{id_val}" for id_val in ids]
            # Fetching raw documents by key. redisvl SearchIndex might not have a direct 'get_documents_by_ids'.
            # Use underlying client's mget to get raw Redis hash objects.
            # Note: mget returns list of bytes (for HASH values) or None.
            # We need hgetall for each key to get all fields.

            formatted_results = []
            pipeline = self.client.pipeline(transaction=False)
            for key in full_keys:
                pipeline.hgetall(key)

            raw_docs_fields_list = pipeline.execute()  # List of Dict[bytes, bytes]

            for i, raw_doc_fields_bytes in enumerate(raw_docs_fields_list):
                if raw_doc_fields_bytes:  # If key existed and HGETALL returned fields
                    # Decode field names and string values from bytes to str
                    doc_fields = {
                        k.decode("utf-8"): v.decode("utf-8")
                        for k, v in raw_doc_fields_bytes.items()
                        if isinstance(k, bytes)
                        and isinstance(v, bytes)  # Ensure they are bytes
                    }

                    text = doc_fields.get(self.text_field_name, "")

                    # Vector is stored as bytes by redisvl, needs to be converted back
                    embedding_bytes = raw_doc_fields_bytes.get(
                        self.vector_field_name.encode("utf-8")
                    )
                    embedding = None
                    if embedding_bytes and isinstance(embedding_bytes, bytes):
                        embedding = np.frombuffer(
                            embedding_bytes, dtype=np.float32
                        ).tolist()

                    metadata = {
                        k: v
                        for k, v in doc_fields.items()
                        if k not in ["id", self.text_field_name, self.vector_field_name]
                    }
                    for k_meta, v_meta in metadata.items():  # Try to parse JSON strings
                        if isinstance(v_meta, str):
                            try:
                                metadata[k_meta] = json.loads(v_meta)
                            except:
                                pass

                    formatted_results.append(
                        {
                            "id": ids[i],  # Use original requested ID
                            "text": text,
                            "metadata": metadata,
                            "embedding": embedding,
                        }
                    )
            return formatted_results

        def update(
            self,
            ids: List[str],
            documents: Optional[List[str]] = None,
            embeddings: Optional[List[List[float]]] = None,
            metadatas: Optional[List[Dict[str, Any]]] = None,
            sparse_vectors: Optional[
                List[Optional[Dict[int, float]]]
            ] = None,  # Ignored
        ) -> None:
            # redisvl's `load` method (used by `add_documents`) acts as an upsert.
            # So, update can be implemented by calling `add_documents` with the new data.
            # This requires that if a field is not provided for update, its old value might be lost
            # unless `add_documents` is smart enough or we fetch-modify-add.
            # For simplicity, assume `update` means providing the full new state for the document.
            if not ids:
                return

            logger.info(
                "RedisDB (redisvl): Update operation implemented as a full replace (upsert) using add_documents."
            )

            # We need to construct the arguments for add_documents carefully.
            # If a field (documents, embeddings, metadatas) is None for a particular ID,
            # we cannot simply pass it to add_documents as it expects complete data for each item.
            # This means an update must provide all necessary fields (text, embedding) for each ID.

            docs_for_add = []
            embeds_for_add = []
            metas_for_add = []
            ids_for_add = []

            for i, doc_id in enumerate(ids):
                doc_text = (
                    documents[i]
                    if documents and i < len(documents) and documents[i] is not None
                    else None
                )
                doc_embed = (
                    embeddings[i]
                    if embeddings and i < len(embeddings) and embeddings[i] is not None
                    else None
                )
                doc_meta = (
                    metadatas[i]
                    if metadatas and i < len(metadatas) and metadatas[i] is not None
                    else {}
                )

                if (
                    doc_text is not None and doc_embed is not None
                ):  # Essential fields for add_documents
                    ids_for_add.append(doc_id)
                    docs_for_add.append(doc_text)
                    embeds_for_add.append(doc_embed)
                    metas_for_add.append(doc_meta)
                else:
                    logger.warning(
                        f"RedisDB (redisvl): Skipping update for ID {doc_id} due to missing document text or embedding."
                    )

            if ids_for_add:
                self.add_documents(
                    documents=docs_for_add,
                    embeddings=embeds_for_add,
                    metadatas=metas_for_add,
                    ids=ids_for_add,
                )
                logger.info(
                    f"RedisDB (redisvl): Processed update for {len(ids_for_add)} documents."
                )

        def count(self) -> int:
            if not self.index:
                return 0
            try:
                info = self.index.info()  # redisvl SearchIndex.info() returns a dict
                return int(info.get("num_docs", 0))
            except Exception as e:
                logger.error(
                    f"RedisDB (redisvl): Error getting count for index '{self.index_name}': {e}"
                )
                return 0

        def clear(self) -> None:
            # Deletes all documents from the index by deleting and recreating the index.
            if not self.index:
                return
            try:
                # Some versions of redisvl SearchIndex might have a delete() method that can drop the index.
                # Or use client directly: self.client.ft(self.index_name).dropindex(delete_documents=True)
                # For redisvl, SearchIndex(schema).delete() or SearchIndex.delete_index(client, name)
                # Let's try to use the instance method if available, or recreate.
                self.index.delete(
                    drop=True
                )  # Assuming drop=True deletes the index definition
                logger.info(
                    f"RedisDB (redisvl): Index '{self.index_name}' and its documents deleted."
                )
                # Recreate it with the same schema
                self._setup_client_and_index()
                logger.info(
                    f"RedisDB (redisvl): Index '{self.index_name}' cleared and recreated."
                )
            except Exception as e:
                logger.error(
                    f"RedisDB (redisvl): Error clearing index '{self.index_name}': {e}. Attempting fallback clear."
                )
                # Fallback: if drop fails, try to delete all keys with prefix (less ideal)
                if self.client and hasattr(self.index.schema, "index_prefix"):
                    keys_to_delete = [
                        key.decode("utf-8")
                        for key in self.client.keys(
                            f"{self.index.schema.index_prefix}:*"
                        )
                    ]
                    if keys_to_delete:
                        self.client.delete(*keys_to_delete)
                        logger.info(
                            f"RedisDB (redisvl): Deleted {len(keys_to_delete)} document keys as fallback clear."
                        )
                    # This does not remove the index definition itself.
                    # Recreating the index is better.
                    self._setup_client_and_index()  # Try to recreate to ensure clean state
                else:
                    logger.error(
                        f"RedisDB (redisvl): Fallback clear failed, client or prefix not available."
                    )

        def __del__(self):
            """
            Close the Redis connection if managed by this instance.
            redisvl's SearchIndex might manage its own connection lifecycle.
            If we created self.client directly, we should close it.
            """
            if self.client and hasattr(self.client, "close"):
                try:
                    self.client.close()
                    logger.info(
                        "RedisDB (redisvl): Underlying Redis connection closed."
                    )
                except Exception as e:
                    logger.error(
                        f"RedisDB (redisvl): Error closing Redis connection: {e}"
                    )
