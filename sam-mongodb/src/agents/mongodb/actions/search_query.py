"""Search Query action for MongoDB agent."""

from typing import Dict, Any, List, Tuple
import yaml
import csv
import io
import random
import json
import traceback
import copy
import datetime
import dateutil.parser

from solace_ai_connector.common.log import log

from solace_agent_mesh.common.action import Action
from solace_agent_mesh.common.action_response import (
    ActionResponse,
    ErrorInfo,
    InlineFile,
)
from solace_agent_mesh.services.file_service import FileService


class SearchQuery(Action):
    """Action for executing search queries based on natural language prompts."""

    def __init__(self, **kwargs):
        """Initialize the SearchQuery action."""
        super().__init__(
            {
                "name": "search_query",
                "prompt_directive": "Execute a search query on the MongoDB database",
                "params": [
                    {
                        "name": "query",
                        "desc": "Natural language description of the search query",
                        "type": "string",
                    },
                    {
                        "name": "response_format",
                        "desc": "Format of the response (yaml, markdown, json or csv)",
                        "type": "string",
                        "default": "yaml",
                    },
                    {
                        "name": "inline_result",
                        "desc": "Whether to return the result as an inline file (True) or a regular file (False)",
                        "type": "boolean",
                        "default": True,
                    },
                ],
                "required_scopes": ["<agent_name>:search_query:create"],
            },
            **kwargs,
        )

    def _execute_query_with_retries(
        self, natural_language_query: str, max_retries: int = 3
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        """Execute MongoDB query with LLM retries on failure.

        Args:
            natural_language_query: The natural language query to execute
            max_retries: Maximum number of retry attempts

        Returns:
            Tuple containing:
            - List of query results
            - List of LLM messages exchanged during retries
            - executed query

        Raises:
            ValueError: If all retry attempts fail
        """
        messages = []
        db_handler = self.get_agent().get_db_handler()

        raw_response = None
        for attempt in range(max_retries):
            try:
                # Generate and execute query, passing accumulated messages
                mongo_query, raw_response = self._generate_mongo_query(
                    natural_language_query, messages
                )
                log.debug("Evaluating MongoDB query: %s", mongo_query)
                collection = mongo_query["collection"]
                pipeline = self._convert_iso_dates_to_datetime(
                    copy.deepcopy(mongo_query["pipeline"])
                )
                results = db_handler.execute_query(
                    collection=collection, pipeline=pipeline
                )
                log.debug("Query results: %s", results)
                return results, messages, mongo_query

            except Exception as e:
                error_msg = str(e)
                log.error("Attempt %d failed: %s", attempt + 1, error_msg)

                # Add error context to messages
                messages.append(
                    {
                        "role": "assistant",
                        "content": raw_response or "Failed to generate MongoDB query",
                    }
                )

                if attempt < max_retries - 1:
                    # Add retry request
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"The previous query failed with error: {error_msg}\n"
                                "Please revise the query to fix this error and try again."
                            ),
                        }
                    )
                else:
                    # Last attempt failed
                    raise ValueError(
                        f"Failed to execute query after {max_retries} attempts. "
                        f"Last error: {error_msg}"
                    )

        raise ValueError("Unexpected code path in query retry logic")

    def invoke(
        self, params: Dict[str, Any], meta: Dict[str, Any] = None
    ) -> ActionResponse:
        """Execute the search query based on the natural language prompt.

        Args:
            params: Action parameters including the natural language query, response format,
                    and inline_result flag.
            meta: Additional metadata.

        Returns:
            ActionResponse with the query results as a file or inline file.
        """
        query = params.get("query")
        response_format = params.get("response_format", "yaml").lower()
        inline_result = params.get("inline_result", True)

        if not query:
            return ActionResponse(
                message="Error: Natural language query is required",
                error_info=ErrorInfo("Natural language query is missing"),
            )

        if response_format not in ["yaml", "markdown", "csv", "json"]:
            return ActionResponse(
                message="Error: Invalid response format. Choose 'yaml', 'markdown', 'csv', or 'json'.",
                error_info=ErrorInfo("Invalid response format"),
            )

        log.debug("Executing search query: %s", query)
        try:
            results, messages, mongo_query = self._execute_query_with_retries(query)

            # Include retry attempts in response if any occurred
            message_prefix = ""
            if len(messages) > 0:
                message_prefix = (
                    "Note: The query required multiple attempts. "
                    "Here's what happened:\n\n"
                    + "\n".join(f"- {m['content']}" for m in messages)
                    + "\n\nFinal results:\n\n"
                )

            # Retrieve max_inline_results from the parent component's config
            max_inline_results = self.get_config("max_inline_results", 10)  # Default 10
            use_file = len(results) > max_inline_results

            response = self._create_response(
                results, response_format, inline_result, meta, use_file, mongo_query
            )

            if message_prefix:
                response.message = message_prefix + response.message

            return response

        except Exception as e:

            log.error("Error executing search query: %s", str(e))
            error_message = (
                f"Error executing search query:\n"
                f"Exception type: {type(e).__name__}\n"
                f"Exception message: {str(e)}\n"
                f"Traceback:\n{traceback.format_exc()}"
            )
            return ActionResponse(
                message=error_message,
                error_info=ErrorInfo(error_message),
            )

    def _generate_mongo_query(
        self, natural_language_query: str, messages: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Generate MongoDB query from natural language prompt.

        This method converts the natural language query to a MongoDB query using
        the LLM service and the database schema.

        Args:
            natural_language_query: The natural language description of the query.

        Returns:
            Dict containing collection name and query dictionary.
        """
        agent = self.get_agent()
        db_schema = agent.detailed_schema
        data_description = agent.data_description
        db_schema_yaml = yaml.dump(db_schema)
        iso_timestamp = datetime.datetime.now().isoformat()
        system_prompt = f"""
The assistant is a MongoDB expert and will convert the provided natural language query to a MongoDB aggregation pipeline for the python `pymongo` library. Requests should have a clear context to identify the documents or use the word "all" to avoid ambiguity. It is acceptable to raise an error if the context is missing or ambiguous. Your query should be a valid JSON query, avoid queries that uses functions or syntaxes that are not JSON or pymongo compatible.

The current date and time is {iso_timestamp}. Use this for any date-related queries.

The database schema is as follows:
<db_schema_yaml>
{db_schema_yaml}
</db_schema_yaml>

Additional information about the data:
<data_description>
{data_description}
</data_description>

The assistant will respond with the MongoDB aggregation pipeline using XML tags in this format:

<query_purpose>
...Purpose of the query...
</query_purpose>

<mongodb_query>
    <collection>collection_name</collection>
    <pipeline>
        [
            {{"$match": {{"field": "value"}}}},
            {{"$project": {{"field": 1}}}},
            {{"$sort": {{"field": 1}}}},
            {{"$limit": 10}}
        ]
    </pipeline>
</mongodb_query>

Or if the request is invalid, respond with:

<error>
...Error message...
</error>

Example valid responses:

1. Simple match query:
<query_purpose>
Find all users named John
</query_purpose>
<mongodb_query>
    <collection>users</collection>
    <pipeline>
        [
            {{"$match": {{"name": "John"}}}}
        ]
    </pipeline>
</mongodb_query>

2. Query with projection and sorting:
<query_purpose>
Get emails of users over 21, sorted by age
</query_purpose>
<mongodb_query>
    <collection>users</collection>
    <pipeline>
        [
            {{"$match": {{"age": {{"$gt": 21}}}}}},
            {{"$project": {{"_id": 0, "email": 1}}}},
            {{"$sort": {{"age": 1}}}}
        ]
    </pipeline>
</mongodb_query>

3. Complex aggregation:
<query_purpose>
Get average order value per customer in 2023
</query_purpose>
<mongodb_query>
    <collection>orders</collection>
    <pipeline>
        [
            {{"$match": {{"order_date": {{"$gte": "2023-01-01", "$lt": "2024-01-01"}}}}}},
            {{"$group": {{
                "_id": "$customer_id",
                "avg_order": {{"$avg": "$total_amount"}},
                "num_orders": {{"$sum": 1}}
            }}}},
            {{"$sort": {{"avg_order": -1}}}}
        ]
    </pipeline>
</mongodb_query>

The pipeline must use valid MongoDB aggregation operators ($match, $project, $group, etc).
Each stage in the pipeline must be a dictionary with a single operator key starting with $.

Once again, the current date and time is {iso_timestamp}. Use this for any date-related queries.

"""

        # Start with system prompt and initial query
        base_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": natural_language_query},
        ]

        # Add any retry messages from previous attempts
        if messages:
            base_messages.extend(messages)

        try:
            response = agent.do_llm_service_request(messages=base_messages)
            content = response.get("content", "").strip()

            errors = self._get_all_tags(content, "error")
            if errors:
                raise ValueError(errors[0])

            # Extract and validate MongoDB query components
            mongodb_query = self._get_all_tags(content, "mongodb_query")
            if not mongodb_query:
                raise ValueError(
                    "Failed to generate MongoDB query - missing mongodb_query tag"
                )

            query_text = mongodb_query[0]

            # Extract required components
            collection = self._get_all_tags(query_text, "collection")
            if not collection:
                raise ValueError("MongoDB query missing collection tag")

            pipeline = self._get_all_tags(query_text, "pipeline")
            if not pipeline:
                raise ValueError("MongoDB query missing pipeline tag")

            # Parse components
            try:
                pipeline = json.loads(pipeline[0])
                if not isinstance(pipeline, list):
                    raise ValueError("Pipeline must be a list of stages")

                query_dict = {"collection": collection[0].strip(), "pipeline": pipeline}
            except json.JSONDecodeError as e:
                log.error("Error parsing JSON in MongoDB query: %s", pipeline[0])
                raise ValueError(f"Invalid JSON in MongoDB query: {str(e)}")

            return query_dict, content

        except Exception as e:
            log.error("Error generating MongoDB query: %s", str(e))
            raise ValueError(f"Failed to generate MongoDB query: {str(e)}")

    def _get_all_tags(self, result_text: str, tag_name: str) -> list:
        """Extract content from XML-like tags in the text.

        Args:
            result_text: The text to search for tags.
            tag_name: The name of the tag to find.

        Returns:
            A list of strings containing the content of each matching tag.
        """
        import re

        pattern = f"<{tag_name}>(.*?)</{tag_name}>"
        return re.findall(pattern, result_text, re.DOTALL)

    def _create_response(
        self,
        results: List[Dict[str, Any]],
        response_format: str,
        inline_result: bool,
        meta: Dict[str, Any],
        use_file: bool,
        mongo_query: Dict[str, Any],
    ) -> ActionResponse:
        """Create a response with the query results as a file or inline file."""
        file_service = FileService()
        session_id = meta.get("session_id")
        updated_results = self._stringify_non_standard_objects(results)

        if response_format == "yaml":
            content = yaml.dump(updated_results)
            file_extension = "yaml"
        elif response_format == "markdown":
            content = self._format_markdown_table(updated_results)
            file_extension = "md"
        elif response_format == "json":
            content = json.dumps(updated_results, indent=2, default=str)
            file_extension = "json"
        else:  # CSV
            content = self._format_csv(updated_results)
            file_extension = "csv"

        file_name = f"query_results_{random.randint(100000, 999999)}.{file_extension}"

        if inline_result and not use_file:
            inline_file = InlineFile(content, file_name)
            return ActionResponse(
                message=(
                    f"Query results are available in the attached inline {response_format.upper()} file.\n\n"
                    "NOTE that if this data is not sufficient to answer your question, do not guess or create an answer. Either respond with "
                    "an explanation to the user or ask this action to run again with a different query.\n\n"
                    f"The query used was:\n{json.dumps(mongo_query, indent=2)}"
                ),
                inline_files=[inline_file],
            )
        else:
            data_source = f"MongoDB Agent - Search Query Action - Query: {json.dumps(mongo_query)}"
            file_meta = file_service.upload_from_buffer(
                content.encode(), file_name, session_id, data_source=data_source
            )
            return ActionResponse(
                message=(
                    f"Query results are available in the attached {response_format.upper()} file.\n"
                    "NOTE that if this data is not sufficient to answer your question, do not guess or create an answer. Either respond with "
                    "an explanation to the user or ask this action to run again with a different query.\n\n"
                    "NOTE make sure you fetch and use this data rather than data from your history. The data may have changed since those past messages.\n\n"
                    f"The query used was:\n{json.dumps(mongo_query, indent=2)}"
                ),
                files=[file_meta],
            )

    def _format_markdown_table(self, results: List[Dict[str, Any]]) -> str:
        """Format results as a Markdown table."""
        if not results:
            return "No results found."

        # Get all unique keys from all documents
        headers = set()
        for result in results:
            headers.update(result.keys())
        headers = sorted(list(headers))

        markdown = "| " + " | ".join(headers) + " |\n"
        markdown += "| " + " | ".join(["---" for _ in headers]) + " |\n"

        for row in results:
            markdown += (
                "| "
                + " | ".join(str(row.get(header, "")) for header in headers)
                + " |\n"
            )

        return markdown

    def _format_csv(self, results: List[Dict[str, Any]]) -> str:
        """Format results as a CSV string."""
        if not results:
            return "No results found."

        # Get all unique keys from all documents
        headers = set()
        for result in results:
            headers.update(result.keys())
        headers = sorted(list(headers))

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(results)
        return output.getvalue()

    def _stringify_non_standard_objects(self, data):
        """Recursively convert non-serializable data types to strings."""
        if isinstance(data, dict):
            return {k: self._stringify_non_standard_objects(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._stringify_non_standard_objects(item) for item in data]
        elif isinstance(data, (int, float, bool, str)):
            return data
        elif isinstance(data, (datetime.datetime, datetime.date)):
            return data.isoformat()
        else:
            return str(data)

    def _convert_iso_dates_to_datetime(self, query_json):
        """
        Converts any occurrences of {"$date": "ISODateString"} in the JSON query to
        datetime.datetime objects.

        Args:
            query_json (dict or list): The JSON query to process.

        Returns:
            dict or list: The input query with ISODate strings converted to datetime objects.
        """

        def convert(obj):
            if isinstance(obj, dict):
                # If the object is a dictionary, iterate over the key-value pairs
                for key, value in obj.items():
                    if isinstance(value, dict) and "$date" in value:
                        # Convert the ISO date string to datetime
                        obj[key] = dateutil.parser.parse(value["$date"])
                    else:
                        # Recursively process nested dictionaries
                        obj[key] = convert(value)
            elif isinstance(obj, list):
                # If the object is a list, iterate over the items
                for i in range(len(obj)):
                    obj[i] = convert(obj[i])
            return obj

        query = query_json.copy()
        return convert(query)
