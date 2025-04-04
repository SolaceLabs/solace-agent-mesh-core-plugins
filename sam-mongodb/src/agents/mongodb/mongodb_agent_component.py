"""MongoDB Agent Component for handling database operations."""

import copy
from typing import Dict, Any, List, Tuple

from solace_ai_connector.common.log import log  # Added log import
from solace_agent_mesh.agents.base_agent_component import (
    agent_info,
    BaseAgentComponent,
)
from solace_ai_connector.components.general.db.mongo.mongo_handler import MongoHandler
from .actions.search_query import SearchQuery


info = copy.deepcopy(agent_info)
info.update(
    {
        "agent_name": None,  # Template variable replaced at agent creation
        "class_name": "MongoDBAgentComponent",
        "description": "Provides natural language query access to a MongoDB database.",  # Base description
        "config_parameters": [
            {
                "name": "agent_name",
                "required": True,
                "description": "Name of this MongoDB agent instance (used for topics, queues, etc.)",
                "type": "string",
            },
            {
                "name": "always_open",  # Keep this for backward compatibility if needed, but not templated
                "required": False,
                "description": "Whether this agent should always be open",
                "type": "boolean",
                "default": False,
            },
            {
                "name": "database_host",
                "required": True,
                "description": "MongoDB host. Set via <AGENT_NAME>_MONGO_HOST env var.",
                "type": "string",
            },
            {
                "name": "database_port",
                "required": True,
                "description": "MongoDB port. Set via <AGENT_NAME>_MONGO_PORT env var.",
                "type": "integer",
            },
            {
                "name": "database_user",
                "required": False,
                "description": "MongoDB user. Set via <AGENT_NAME>_MONGO_USER env var.",
                "type": "string",
            },
            {
                "name": "database_password",
                "required": False,
                "description": "MongoDB password. Set via <AGENT_NAME>_MONGO_PASSWORD env var.",
                "type": "string",
            },
            {
                "name": "database_name",
                "required": True,
                "description": "Database name. Set via <AGENT_NAME>_MONGO_DB env var.",
                "type": "string",
            },
            {
                "name": "database_collection",
                "required": False,
                "description": "Collection name. If not provided, agent accesses all collections. Set via <AGENT_NAME>_MONGO_COLLECTION env var.",
                "type": "string",
            },
            {
                "name": "database_purpose",
                "required": True,
                "description": "Purpose of the database. Set via <AGENT_NAME>_DB_PURPOSE env var.",
                "type": "string",
            },
            {
                "name": "data_description",
                "required": True,
                "description": "Detailed description of the data. Set via <AGENT_NAME>_DB_DESCRIPTION env var.",
                "type": "string",
            },
            {
                "name": "auto_detect_schema",
                "required": False,
                "description": "Automatically detect schema. Set via <AGENT_NAME>_AUTO_DETECT_SCHEMA env var.",
                "type": "boolean",
                "default": True,  # Changed default to True
            },
            {
                "name": "database_schema",  # Keep for manual override if needed
                "required": False,
                "description": "Manually defined database schema if auto_detect_schema is False.",
                "type": "string",
            },
            {
                "name": "max_inline_results",
                "required": False,
                "description": "Maximum number of results to return inline before using a file",
                "type": "integer",
                "default": 10,
            },
        ],
    }
)


class MongoDBAgentComponent(BaseAgentComponent):
    """Component for handling MongoDB database operations."""

    actions = [SearchQuery]

    def __init__(self, module_info: Dict[str, Any] = None, **kwargs):
        """Initialize the MongoDB agent component.

        Args:
            module_info: Optional module configuration.
            **kwargs: Additional keyword arguments.

        Raises:
            ValueError: If required database configuration is missing.
        """
        module_info = module_info or info
        super().__init__(module_info, **kwargs)

        # Get core config values
        self.agent_name = self.get_config("agent_name")
        self.database_purpose = self.get_config("database_purpose")
        self.data_description = self.get_config("data_description")
        self.database_collection = self.get_config(
            "database_collection"
        )  # Can be "" if not set
        self.auto_detect_schema = self.get_config(
            "auto_detect_schema", True
        )  # Default true

        # Update component info with specific instance details
        module_info["agent_name"] = self.agent_name
        module_info[
            "description"
        ] = (  # Update description with instance name and purpose
            f"Provides natural language query access to the '{self.agent_name}' MongoDB database. "
            f"Purpose: {self.database_purpose}"
        )
        self.info = module_info  # Ensure self.info uses the updated module_info

        # Update action scopes
        self.action_list.fix_scopes("<agent_name>", self.agent_name)

        # Initialize MongoDB handler
        self.db_handler = MongoHandler(
            self.get_config("database_host"),
            self.get_config("database_port"),
            self.get_config("database_user"),
            self.get_config("database_password"),
            self.get_config("database_collection"),
            self.get_config("database_name"),
        )

        # Schema detection / loading
        self.detailed_schema = None
        self.summary_schema = None
        if self.auto_detect_schema:
            try:
                self.detailed_schema, self.summary_schema = self._detect_schema()
            except Exception as e:
                # Raise error as the agent cannot function without a schema
                error_msg = (
                    f"Failed to auto-detect schema for agent {self.agent_name}: {e}"
                )
                log.error(error_msg)
                raise ValueError(error_msg) from e
        else:
            # Try to load manual schema if provided
            manual_schema = self.get_config("database_schema")
            if manual_schema:
                # Assume manual schema is in the summary format for simplicity
                # A more robust implementation might parse a detailed manual schema
                self.detailed_schema = {"manual_schema": manual_schema}
                self.summary_schema = {"manual_schema": manual_schema}
            else:
                # Raise error as auto-detect is off and no manual schema was provided
                error_msg = f"Auto-detect schema is off for agent {self.agent_name}, but no manual schema provided via 'database_schema' config."
                log.error(error_msg)
                raise ValueError(error_msg)

    def _detect_schema(self) -> Tuple[Dict[str, Dict[str, List[str]]], Dict[str, str]]:
        """Detect the database schema and include sample data. Returns detailed and summary schemas.

        Returns:
            A tuple containing:
            - A dictionary where keys are collection names and values are dictionaries
              containing field names and sample data.
            - A dictionary where keys are collection names and values are comma-separated
              lists of field names.
        """
        detailed_schema = {}
        summary_schema = {}

        if self.database_collection:
            collections = [self.database_collection]
        else:
            collections = self.db_handler.get_collections()

        for collection in collections:
            fields = self.db_handler.get_fields(collection)
            sample_data = self._get_sample_data(collection, fields)
            detailed_schema[collection] = sample_data
            summary_schema[collection] = ", ".join(fields)

        return detailed_schema, summary_schema

    def _get_sample_data(self, collection: str, fields: List[str]) -> Dict[str, str]:
        """Get sample data for a collection.

        Args:
            collection: Name of the collection.
            fields: List of field names.

        Returns:
            A dictionary where keys are field names and values are strings of sample data.
        """
        sample_data = {}
        for field in fields:
            unique_values, all = self.db_handler.get_sample_values(collection, field)
            truncated_values = [
                value if len(value) <= 40 else value[:37] + "..."
                for value in unique_values
            ]
            if all:
                sample_data[field] = (
                    f"(all unique values: {', '.join(truncated_values)})"
                )
            else:
                sample_data[field] = f"(examples: {', '.join(truncated_values)})"

        return sample_data

    def get_db_handler(self):
        """Get the database handler instance."""
        return self.db_handler

    def get_agent_summary(self):
        """Get a summary of the agent's capabilities."""
        summary = {
            "agent_name": self.agent_name,
            "description": self.info.get(
                "description", "Provides read-only access to a MongoDB database."
            ),  # Use dynamic description
            "detailed_description": (
                f"Agent Name: {self.agent_name}\n"
                f"Purpose: {self.database_purpose}\n\n"
                f"Data Description:\n{self.data_description}\n\n"
                f"Schema Summary:\n{self.summary_schema}\n"  # Use the potentially detected/loaded schema
            ),
            "always_open": self.info.get("always_open", False),
            "actions": self.get_actions_summary(),
        }
        return summary
