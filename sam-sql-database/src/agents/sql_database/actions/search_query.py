"""Action for executing search queries based on natural language prompts."""

from typing import Dict, Any, List, Tuple
import yaml
import json
import random
import io
import re
import csv
import datetime
import dateutil.parser
from collections.abc import Mapping

from solace_agent_mesh.common.action import Action
from solace_agent_mesh.services.file_service import FileService
from solace_agent_mesh.common.action_response import (
    ActionResponse,
    ErrorInfo,
    InlineFile,
)

MAX_TOTAL_INLINE_FILE_SIZE = 100000  # 100KB


class SearchQuery(Action):
    """Action for executing search queries based on natural language prompts."""

    def __init__(self, **kwargs):
        """Initialize the action."""
        super().__init__(
            {
                "name": "search_query",
                "prompt_directive": (
                    "Execute one or more search queries on the SQL database. "
                    "Converts natural language to SQL and returns results. "
                    "You can include multiple related questions in a single query for more efficient processing. "
                    "Each query will be returned as a separate file. "
                    "NOTE that there is no history stored for previous queries, so it is essential to provide all required context in the query."
                ),
                "params": [
                    {
                        "name": "query",
                        "desc": "Natural language description of the search query or queries, including any data required for context. Multiple related questions can be included for more efficient processing. Note that amfs links with resolve=true may be embedded in this parameter.",
                        "type": "string",
                        "required": True,
                    },
                    {
                        "name": "response_format",
                        "desc": "Format of the response (yaml, json or csv)",
                        "type": "string",
                        "required": False,
                        "default": "yaml",
                    },
                    {
                        "name": "inline_result",
                        "desc": "Whether to return the result as an inline file (True) or a regular file (False)",
                        "type": "boolean",
                        "required": False,
                        "default": True,
                    },
                ],
                "required_scopes": ["<agent_name>:search_query:execute"],
            },
            **kwargs,
        )

    def invoke(
        self, params: Dict[str, Any], meta: Dict[str, Any] = None
    ) -> ActionResponse:
        """Execute the search query based on the natural language prompt.

        Args:
            params: Action parameters including the natural language query and response format
            meta: Optional metadata

        Returns:
            ActionResponse containing the query results
        """
        try:
            query = params.get("query")
            if not query:
                raise ValueError("Natural language query is required")

            response_format = params.get("response_format", "yaml").lower()
            if response_format not in ["yaml", "json", "csv"]:
                raise ValueError("Invalid response format. Choose 'yaml', 'json', or 'csv'")

            # Get the SQL queries from the natural language query
            sql_queries = self._generate_sql_queries(query)

            # Execute each query and collect results
            db_handler = self.get_agent().get_db_handler()
            query_results = []
            failed_queries = []

            for purpose, sql_query in sql_queries:
                try:
                    results = db_handler.execute_query(sql_query)
                    query_results.append((purpose, sql_query, results))
                except Exception as e:
                    failed_queries.append((purpose, sql_query, str(e)))

            inline_result = params.get("inline_result", True)
            if isinstance(inline_result, str):
                inline_result = inline_result.lower() == "true"

            # Create response with files for each successful query
            return self._create_multi_query_response(
                query_results=query_results,
                failed_queries=failed_queries,
                response_format=response_format,
                inline_result=inline_result,
                meta=meta,
                query={"query": query},
            )

        except Exception as e:
            return ActionResponse(
                message=f"Error executing search query: {str(e)}",
                error_info=ErrorInfo(str(e)),
            )

    def _generate_sql_queries(
        self, natural_language_query: str
    ) -> List[Tuple[str, str]]:
        """Generate SQL queries from natural language prompt.

        Args:
            natural_language_query: Natural language description of the query

        Returns:
            List of tuples containing (query_purpose, sql_query)

        Raises:
            ValueError: If query generation fails
        """
        agent = self.get_agent()
        db_schema = agent.detailed_schema
        data_description = agent.data_description
        db_type = agent.db_type
        db_schema_yaml = yaml.dump(db_schema)
        current_timestamp = datetime.datetime.now().isoformat()

        system_prompt = f"""
You are an SQL expert and will convert the provided natural language query to one or more SQL queries for {db_type}.
If the user's request requires multiple SQL queries to fully answer, generate all necessary queries.
Requests should have a clear context to identify the person or entity or use the word "all" to avoid ambiguity.
It is required to raise an error if the context is missing or ambiguous.

The database schema is as follows:
<db_schema_yaml>
{db_schema_yaml}
</db_schema_yaml>

Additional information about the data:
<data_description>
{data_description}
</data_description>

The current date and time are available as:
current_date_time: {current_timestamp}

For each query needed to answer the user's request, respond with the following format:

<query_purpose>
...Purpose of the query...
</query_purpose>
<sql_query>
...SQL query...
</sql_query>

If multiple queries are needed, repeat the above format for each query.

Or if the request is invalid, respond with an error message:

<error>
...Error message...
</error>


Ensure that all SQL queries are compatible with {db_type}.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": natural_language_query},
        ]

        try:
            response = agent.do_llm_service_request(messages=messages)
            content = response.get("content", "").strip()

            errors = self._get_all_tags(content, "error")
            if errors:
                raise ValueError(errors[0])

            sql_queries = self._get_all_tags(content, "sql_query")
            purposes = self._get_all_tags(content, "query_purpose")

            if not sql_queries:
                raise ValueError("Failed to generate SQL query")

            # Match purposes with queries
            if len(purposes) != len(sql_queries):
                # If counts don't match, use generic purposes
                purposes = [f"Query {i+1}" for i in range(len(sql_queries))]

            return list(zip(purposes, sql_queries))

        except Exception as e:
            raise ValueError(f"Failed to generate SQL query: {str(e)}")

    def _get_all_tags(self, result_text: str, tag_name: str) -> list:
        """Extract content from XML-like tags in the text.

        Args:
            result_text: Text to search for tags
            tag_name: Name of the tag to find

        Returns:
            List of strings containing the content of each matching tag
        """
        pattern = f"<{tag_name}>(.*?)</{tag_name}>"
        return re.findall(pattern, result_text, re.DOTALL)

    def _create_multi_query_response(
        self,
        query_results: List[Tuple[str, str, List[Dict[str, Any]]]],
        failed_queries: List[Tuple[str, str, str]],
        response_format: str,
        inline_result: bool,
        meta: Dict[str, Any],
        query: Dict[str, Any],
    ) -> ActionResponse:
        """Create a response with multiple query results as files.

        Args:
            query_results: List of tuples (purpose, sql_query, results)
            failed_queries: List of tuples (purpose, sql_query, error_message)
            response_format: Format for the result files
            inline_result: Whether to return inline files
            meta: Metadata including session_id
            query: Original query for file metadata

        Returns:
            ActionResponse with files or inline files for each query result
        """
        file_service = FileService()
        session_id = meta.get("session_id")

        # Build message with query summary
        message_parts = []

        if not query_results and not failed_queries:
            return ActionResponse(
                message="No SQL queries were generated from your request. Please try again with a more specific query.",
            )

        # Add summary of successful queries
        if query_results:
            message_parts.append(
                f"Successfully executed {len(query_results)} SQL queries:"
            )
            for i, (purpose, sql_query, _) in enumerate(query_results, 1):
                message_parts.append(f"\n{i}. {purpose}\nSQL: ```{sql_query}```")

        # Add summary of failed queries
        if failed_queries:
            message_parts.append(
                f"\n\nFailed to execute {len(failed_queries)} SQL queries:"
            )
            for i, (purpose, sql_query, error) in enumerate(failed_queries, 1):
                message_parts.append(
                    f"\n{i}. {purpose}\nSQL: ```{sql_query}```\nError: {error}"
                )

        # Create files for each successful query
        files = []
        inline_files = []
        total_size = 0

        for i, (purpose, sql_query, results) in enumerate(query_results, 1):
            updated_results = self._stringify_non_standard_objects(results)

            # Format the results based on the requested format
            if response_format == "yaml":
                content = yaml.dump(updated_results)
                file_extension = "yaml"
            elif response_format == "json":
                content = json.dumps(updated_results, indent=2, default=str)
                file_extension = "json"
            else:  # CSV
                content = self._format_csv(updated_results)
                file_extension = "csv"

            # Create a unique filename for each query
            file_name = (
                f"query_{i}_results_{random.randint(100000, 999999)}.{file_extension}"
            )

            total_size += len(content)
            if total_size > MAX_TOTAL_INLINE_FILE_SIZE:
                inline_result = False

            if inline_result:
                inline_files.append(InlineFile(content, file_name))
            else:
                data_source = f"SQL Agent - Search Query {i} - {purpose}"
                file_meta = file_service.upload_from_buffer(
                    content.encode(), file_name, session_id, data_source=data_source
                )
                files.append(file_meta)

        # Add file summary to message
        if query_results:
            if inline_files:
                message_parts.append(
                    f"\n\nResults are available in {len(inline_files)} attached inline {response_format.upper()} files."
                )
            if files:
                message_parts.append(
                    f"\n\nResults are {'also ' if len(inline_files) > 0 else ''} available in {len(files)} attached {response_format.upper()} files."
                )
                
        # Add response guidelines if they exist
        agent = self.get_agent()
        if hasattr(agent, 'response_guidelines') and agent.response_guidelines:
            message_parts.append(f"\n\nGuidelines:\n{agent.response_guidelines}")
        
        return ActionResponse(
            message="\n".join(message_parts),
            files=files if files else None,
            inline_files=inline_files if inline_files else None,
        )

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
        if isinstance(data, dict) or isinstance(data, Mapping):
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
