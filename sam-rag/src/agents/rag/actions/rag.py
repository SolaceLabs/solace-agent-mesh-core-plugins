"""
Action for retrieving documents from a RAG system.
This action retrieves documents from a vector database and augments the results.
"""

from solace_agent_mesh.common.action import Action
from solace_agent_mesh.common.action_response import ActionResponse
from solace_ai_connector.common.log import log

# To import from a local file, like this file, use a relative path from the rag
# For example, to load this class, use:
#   from rag.actions.ingestion_action import IngestionAction


class RAGAction(Action):

    def __init__(self, **kwargs):
        super().__init__(
            {
                "name": "rag_action",
                "prompt_directive": (
                    "This action retrieves documents from a vector database and returns a list of contents and corresponding source urls."
                ),
                "params": [
                    {
                        "name": "query",
                        "desc": "The query to search for",
                        "type": "string",
                        "default": "",
                        "required": True,
                    },
                ],
                "required_scopes": ["rag:rag_action:write"],
            },
            **kwargs,
        )

    def invoke(self, params, meta={}) -> ActionResponse:
        log.debug("Starting document retrieval process")

        query = params.get("query")
        session_id = meta.get("session_id")
        if not query:
            return ActionResponse(message="Query parameter is required")

        rag = self.get_agent().get_augmentation_handler()
        content, files = rag.augment(query, session_id, filter=None)
        if not content:
            log.info("No results found for the query")
            return ActionResponse(message="No results found for the query")

        return ActionResponse(message=content, files=files)
