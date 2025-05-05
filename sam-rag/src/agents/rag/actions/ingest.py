"""
Action for ingesting documents into the RAG system.
This action gets documents and ingests them into a vector database.
"""

import ujson as json

from solace_agent_mesh.common.action import Action
from solace_agent_mesh.common.action_response import ActionResponse
from solace_ai_connector.common.log import log

# To import from a local file, like this file, use a relative path from the rag
# For example, to load this class, use:
#   from rag.actions.ingestion_action import IngestionAction


class IngestionAction(Action):

    def __init__(self, **kwargs):
        super().__init__(
            {
                "name": "ingestion_action",
                "prompt_directive": (
                    "This action ingests documents into a vector database."
                ),
                "params": [
                    {
                        "name": "documents",
                        "desc": "The list of attached documents, which contain amfs_url, name and mime_type per document",
                        "type": "list",
                        "default": [],
                        "required": True,
                        "properties": {
                            "name": {
                                "type": "string",
                                "desc": "The name of the document",
                            },
                            "amfs_url": {
                                "type": "string",
                                "desc": "The amfs url of the document",
                            },
                            "mime_type": {
                                "type": "string",
                                "desc": "The type of the document",
                            },
                        },
                    },
                ],
                "required_scopes": ["rag:ingestion_action:write"],
            },
            **kwargs,
        )

    def invoke(self, params, meta={}) -> ActionResponse:
        log.debug("Starting document ingestion process")
        documents = params.get("documents")
        json_documents = json.loads(documents)

        # Verify the documents parameter
        verified_documents = []
        if json_documents and isinstance(json_documents, list):
            for document in json_documents:
                if (
                    "name" in document
                    and "amfs_url" in document
                    and "mime_type" in document
                ):
                    verified_documents.append(document)

        log.debug("Verified documents")

        tracker = self.get_agent().get_file_tracker()
        results = tracker.upload_files(verified_documents)
        if not results:
            log.warning("Failed to upload files")
            return ActionResponse(message="Could not upload files")
        log.debug(f"Ingestion results: {results}")

        return ActionResponse(message=results)
