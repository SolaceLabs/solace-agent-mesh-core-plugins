"""
A generic, configuration-driven tool for interacting with Nuclia's RAG capabilities.
This tool generates a complete, natural-language answer with embedded citations
and saves the result as a structured artifact for the agent to use.
"""

import re
import requests
import json

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from google.adk.tools import ToolContext
from google.genai import types as adk_types
from nuclia import sdk
from nucliadb_models.search import AskRequest, ResourceProperties, RagStrategyName
from nucliadb_models.filters import FilterExpression
from solace_ai_connector.common.log import log
from solace_ai_connector.common.utils import get_data_value
from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool
from solace_agent_mesh.agent.utils.artifact_helpers import (
    is_filename_safe,
    save_artifact_with_metadata,
)
from solace_agent_mesh.agent.utils.context_helpers import get_original_session_id
from .nuclia_rag_tool_config import NucliaRagToolConfig


class NucliaRagTool(DynamicTool):
    """
    A generic, configuration-driven tool that provides a dynamic interface
    to Nuclia's RAG capabilities.
    """

    # Link the Pydantic config model to this tool
    config_model = NucliaRagToolConfig

    _ADK_TYPE_MAP = {
        "string": adk_types.Type.STRING,
        "boolean": adk_types.Type.BOOLEAN,
        "integer": adk_types.Type.INTEGER,
        "number": adk_types.Type.NUMBER,
    }

    def __init__(self, tool_config: NucliaRagToolConfig):
        """Initializes the tool with a validated configuration model."""
        super().__init__(tool_config)
        if isinstance(tool_config, dict):
            self.tool_config = NucliaRagToolConfig(**tool_config)
        self.log_identifier = "[NucliaRagTool]"
        log.info(
            "%s Initialized with validated configuration for KB: %s",
            self.log_identifier,
            self.tool_config.kb_id,
        )

    @property
    def tool_name(self) -> str:
        """Returns the tool's name."""
        return self.tool_config.tool_name

    @property
    def tool_description(self) -> str:
        """Returns the tool's description."""
        return (
            "Uses Nuclia's RAG capabilities to generate a complete, natural-language answer to a user's query. "
            "This tool is ideal for complex questions that require searching through a knowledge base to synthesize an answer. "
            "It returns a single markdown artifact containing the answer with footnote markers and a formatted list of sources."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        """Dynamically generates the parameter schema from the configuration."""
        properties = {
            "query": adk_types.Schema(
                type=adk_types.Type.STRING,
                description="The natural language query from the user.",
            ),
            "output_filename_base": adk_types.Schema(
                type=adk_types.Type.STRING,
                description="A base name for the output artifact to make it more meaningful. The tool will append `.md`.",
                nullable=True,
            ),
        }
        required = ["query"]

        # Add dynamic parameters from validated config
        for param in self.tool_config.template_parameters:
            if param.context_expression:
                continue

            adk_type = self._ADK_TYPE_MAP.get(param.type, adk_types.Type.STRING)

            properties[param.name] = adk_types.Schema(
                type=adk_type,
                description=param.description,
                nullable=param.nullable,
            )
            if param.required:
                required.append(param.name)

        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties=properties,
            required=required or None,
        )

    def _get_template_parameters(
        self, args: Dict[str, Any], tool_context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """
        Builds a dictionary of template parameters with their values.
        Uses defaults from config if not provided in args.
        """

        template_params = {"query": args.get("query", "")}

        for param in self.tool_config.template_parameters:
            if param.context_expression:
                if tool_context:
                    a2a_context = tool_context.state.get("a2a_context", {})
                    expr = param.context_expression
                    if ":" not in expr:
                        expr = f"dummy:{expr}"
                    value = get_data_value(a2a_context, expr, True)
                    template_params[param.name] = (
                        value if value is not None else param.default
                    )
                else:
                    template_params[param.name] = param.default
            else:
                value = args.get(param.name)
                if value is None:
                    value = param.default
                template_params[param.name] = value

        return template_params

    def _substitute_template_recursively(
        self, template: Any, params: Dict[str, Any]
    ) -> Any:
        """
        Recursively substitutes {param} placeholders in a nested structure.
        """
        if isinstance(template, str):
            # Replace placeholders in strings
            try:
                return template.format(**params)
            except KeyError:
                # If a key is missing, return the template as-is
                return template
        elif isinstance(template, dict):
            # Recursively process dictionary values
            return {
                k: self._substitute_template_recursively(v, params)
                for k, v in template.items()
            }
        elif isinstance(template, list):
            # Recursively process list items
            return [
                self._substitute_template_recursively(item, params) for item in template
            ]
        else:
            # Return as-is for other types
            return template

    def _check_missing_filter_parameters(
        self, template_params: Dict[str, Any]
    ) -> List[str]:
        """
        Checks which parameters required by the filter template are missing or empty.
        Returns a list of missing parameter names.
        """
        if not self.tool_config.filter_expression_template:
            return []

        # Find all {param} placeholders in the template
        template_str = str(self.tool_config.filter_expression_template)
        placeholders = set(re.findall(r"\{(\w+)\}", template_str))

        # Build a set of parameter names that have context_expression
        context_params = {
            param.name
            for param in self.tool_config.template_parameters
            if param.context_expression
        }

        # Check which ones are missing or empty
        missing = []
        for param_name in placeholders:
            if param_name == "query":
                continue
            if param_name in context_params:
                continue
            value = template_params.get(param_name)
            if value is None or value == "":
                missing.append(param_name)

        return missing

    def _apply_prompt_rephrasing(
        self, args: Dict[str, Any], tool_context: ToolContext
    ) -> str:
        """
        Applies prompt rephrasing based on the provided configuration and arguments.
        """
        query = args.get("query", "")

        if not self.tool_config.prompt_rephrasing:
            log.debug(
                "%s No prompt_rephrasing config found. Using original query.",
                self.log_identifier,
            )
            return query

        template_params = self._get_template_parameters(args, tool_context)

        try:
            rephrased_prompt = self.tool_config.prompt_rephrasing.template.format(
                **template_params
            )
            log.info(
                "%s Successfully rephrased prompt using template.", self.log_identifier
            )
            return rephrased_prompt
        except KeyError as e:
            log.error(
                "%s Template formatting failed. Missing key: %s. Using original query.",
                self.log_identifier,
                e,
            )
            return query

    def _apply_filter_template(
        self, args: Dict[str, Any], tool_context: ToolContext
    ) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        """
        Applies the filter expression template by substituting parameters.

        Returns:
            Tuple of (filter_expression, missing_parameters)
            - filter_expression: The substituted filter, or None if template not configured or params missing
            - missing_parameters: List of parameter names that were missing/empty
        """
        if not self.tool_config.filter_expression_template:
            return None, []

        template_params = self._get_template_parameters(args, tool_context)

        missing_params = self._check_missing_filter_parameters(template_params)

        if missing_params:
            log.warning(
                "%s Filter template not applied due to missing parameters: %s",
                self.log_identifier,
                ", ".join(missing_params),
            )
            return None, missing_params

        try:
            filter_expression = self._substitute_template_recursively(
                self.tool_config.filter_expression_template, template_params
            )
            log.info("%s Successfully applied filter template", self.log_identifier)
            return filter_expression, []
        except Exception as e:
            log.error(
                "%s Filter template substitution failed: %s", self.log_identifier, e
            )
            return None, []

    def _build_audit_metadata(
        self, args: Dict[str, Any], tool_context: ToolContext
    ) -> Optional[Dict[str, str]]:
        """
        Builds the audit metadata dictionary using template substitution.

        Returns:
            Dictionary of audit metadata, or None if disabled or no fields configured
        """
        if (
            not self.tool_config.audit_metadata
            or not self.tool_config.audit_metadata.enabled
        ):
            return None

        if not self.tool_config.audit_metadata.fields:
            return None

        template_params = self._get_template_parameters(args, tool_context)

        audit_data = {}
        for key, template in self.tool_config.audit_metadata.fields.items():
            try:
                value = template.format(**template_params)

                if value:
                    audit_data[key] = value

            except KeyError as e:
                log.warning(
                    "%s Audit metadata field '%s' references undefined parameter: %s. "
                    "Add it to template_parameters if needed.",
                    self.log_identifier,
                    key,
                    e,
                )
                continue
            except Exception as e:
                log.warning(
                    "%s Failed to format audit metadata field '%s': %s",
                    self.log_identifier,
                    key,
                    e,
                )
                continue

        if not audit_data:
            return None

        size = len(json.dumps(audit_data).encode("utf-8"))
        if size > 10240:
            log.error(
                "%s Audit metadata size (%d bytes) exceeds 10KB limit",
                self.log_identifier,
                size,
            )
            raise ValueError(f"Audit metadata size ({size} bytes) exceeds 10KB limit")

        return audit_data

    def _create_eph_token(self) -> str:
        """
        Create an ephemeral token for accessing resources.
        """
        base_url = self.tool_config.base_url
        api_key = self.tool_config.api_key
        kb_id = self.tool_config.kb_id
        token = self.tool_config.token

        # Use api_key as the account ID
        account_id = api_key

        # Construct the API endpoint
        endpoint = f"{base_url}/account/{account_id}/kb/{kb_id}/ephemeral_tokens"

        # Set up headers
        headers = {
            "X-NUCLIA-SERVICEACCOUNT": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            # Make the POST request
            response = requests.post(endpoint, headers=headers, json={})
            response.raise_for_status()  # Raise an exception for bad status codes

            # Parse the response and extract the token
            response_data = response.json()
            ephemeral_token = response_data.get("token")

            if not ephemeral_token:
                raise ValueError("No token found in API response")

            return ephemeral_token

        except requests.exceptions.RequestException as e:
            log.error(f"Failed to create ephemeral token: {e}")
            raise
        except (ValueError, KeyError) as e:
            log.error(f"Failed to parse ephemeral token response: {e}")
            raise

    def _create_public_url(self, prefix_url: str, uri: str, token: str) -> str:
        """
        Create a public URL for the given file.
        """
        return f"{prefix_url}{uri}?eph-token={token}&inline=true"

    def _get_inline_citation_links(self) -> bool:
        """Returns whether inline citation links are enabled."""
        return self.tool_config.inline_citation_links

    async def _query_nuclia(
        self,
        rephrased_query: str,
        filter_expression: Optional[Dict[str, Any]] = None,
        audit_metadata: Optional[Dict[str, str]] = None,
    ) -> Optional[Any]:
        """
        Authenticates and performs the generative 'ask' query against Nuclia.

        Returns:
            AskAnswer object containing the response, including learning_id for tracking
        """
        kb_url = f"{self.tool_config.base_url}/kb/{self.tool_config.kb_id}"
        token = self.tool_config.token
        top_k = self.tool_config.top_k

        try:
            log.info(
                "%s Authenticating with knowledge box at %s",
                self.log_identifier,
                kb_url,
            )
            sdk.NucliaAuth().kb(url=kb_url, token=token)

            log.info(
                "%s Performing generative search with top_k=%d.",
                self.log_identifier,
                top_k,
            )
            search = sdk.NucliaSearch()
            ask_query = AskRequest(
                query=rephrased_query,
                citations=True,
                top_k=top_k,
                prefer_markdown=True,
                rephrase=True,
                show=[ResourceProperties.BASIC, ResourceProperties.VALUES],
                rag_strategies=[
                    {"name": RagStrategyName.NEIGHBOURING_PARAGRAPHS},
                    {"name": RagStrategyName.HIERARCHY},
                ],
                audit_metadata=audit_metadata,
            )

            # Add filter if provided
            if filter_expression:
                try:
                    ask_query.filter_expression = FilterExpression(**filter_expression)
                    log.info(
                        "%s Applied filter expression to query",
                        self.log_identifier,
                    )
                except Exception as e:
                    log.error(
                        "%s Failed to apply filter expression: %s. Proceeding without filter.",
                        self.log_identifier,
                        e,
                    )

            # The ask method returns a stream object that also contains the final aggregated result
            ask_response = search.ask(query=ask_query)

            # Based on nucliadb_models.search.SyncAskResponse, the field is 'answer'
            if not ask_response or not ask_response.answer:
                log.warning("%s Nuclia query returned no answer.", self.log_identifier)
                return None

            log.info(
                "%s Nuclia query successful. Answer length: %d chars.",
                self.log_identifier,
                len(ask_response.answer),
            )
            return ask_response

        except Exception as e:
            log.exception(
                "%s An error occurred during the Nuclia query: %s",
                self.log_identifier,
                e,
            )
            return None

    def _format_answer_with_citations(
        self,
        ask_response: Any,  # Expects the full AskAnswer object
    ) -> Tuple[str, List[Dict[str, Any]], str]:
        """
        Injects footnote-style citation markers into the answer text and formats
        the citation sources for display with secure, brokered URLs.
        """
        answer_text = ask_response.answer.decode("utf-8")
        citations = ask_response.citations
        sources = list(ask_response.find_result.resources.values())
        augmented_context = ask_response.augmented_context

        if not citations:
            return answer_text, [], ""

        # Create a single ephemeral token for this request
        ephemeral_token = self._create_eph_token()

        # 1. Build lookup maps for source objects and all paragraph/field positions
        source_map = {source.id: source for source in sources}
        paragraph_positions = {}

        # Populate from original retrieval results
        for source in sources:
            for field_key, field_data in source.fields.items():
                for para_id, para_data in field_data.paragraphs.items():
                    if para_data.position:
                        paragraph_positions[para_id] = para_data.position

        # Populate from augmented context (from RAG strategies)
        if augmented_context:
            if augmented_context.paragraphs:
                for para_id, para_data in augmented_context.paragraphs.items():
                    if para_data.position:
                        paragraph_positions[para_id] = para_data.position
            if augmented_context.fields:
                for field_id, field_data in augmented_context.fields.items():
                    if field_data.position:
                        paragraph_positions[field_id] = field_data.position

        # 2. Group citations by unique source URL to merge duplicates
        grouped_citations = {}
        for paragraph_key, positions_list in citations.items():
            try:
                resource_id = paragraph_key.split("/")[0]
                source_resource = source_map.get(resource_id)

                if not (
                    source_resource
                    and source_resource.data
                    and source_resource.data.files
                ):
                    log.warning(
                        "%s Skipping citation for resource '%s' as it has no file data.",
                        self.log_identifier,
                        resource_id,
                    )
                    continue

                field_id = next(iter(source_resource.data.files.keys()))
                file_info = source_resource.data.files[field_id].value.file
                file_uri = file_info.uri

                secure_url = self._create_public_url(
                    self.tool_config.base_url, file_uri, ephemeral_token
                )

                position = paragraph_positions.get(paragraph_key)
                page_number = (
                    position.page_number if position and position.page_number else 1
                )
                secure_url_with_page = f"{secure_url}#page={page_number}"

                # Use the final URL as the key for grouping
                if secure_url_with_page not in grouped_citations:
                    grouped_citations[secure_url_with_page] = {
                        "title": getattr(source_resource, "title", "Untitled Source"),
                        "url": secure_url_with_page,
                        "page_number": page_number,
                        "all_positions": [],
                    }
                grouped_citations[secure_url_with_page]["all_positions"].extend(
                    positions_list
                )

            except Exception as e:
                log.error(
                    "%s Failed to process and group citation for key '%s': %s",
                    self.log_identifier,
                    paragraph_key,
                    e,
                )
                continue

        # 3. Process grouped citations to create final details and insertion points with new numbering
        citation_details = []
        insertions = []
        citation_counter = 1
        # Sort by URL for deterministic numbering
        for url, group_data in sorted(grouped_citations.items()):
            # Create a single, de-duplicated citation entry for this group
            details = {
                "number": citation_counter,
                "title": group_data["title"],
                "url": group_data["url"],
                "page_number": group_data["page_number"],
            }
            citation_details.append(details)

            # Prepare the marker with the new, sequential citation number
            if self._get_inline_citation_links():
                marker = f" [[{citation_counter}]({group_data['url']})]"
            else:
                marker = f" [{citation_counter}]"

            # Associate this one marker with all character positions from the merged group
            for position_pair in group_data["all_positions"]:
                end_position = position_pair[1]
                insertions.append((end_position, marker))

            citation_counter += 1

        # 4. Insert markers into the answer text, de-duplicating clusters
        positions_to_markers = defaultdict(list)
        for pos, marker in insertions:
            positions_to_markers[pos].append(marker)

        final_insertions = []
        for pos, markers in positions_to_markers.items():
            # Get unique markers and sort them to ensure a consistent order (e.g., [1][5] not [5][1])
            unique_markers = sorted(list(set(markers)))
            combined_marker_str = "".join(unique_markers)
            final_insertions.append((pos, combined_marker_str))

        final_insertions.sort(key=lambda x: x[0], reverse=True)
        modified_text_list = list(answer_text)
        for pos, marker_str in final_insertions:
            modified_text_list.insert(pos, marker_str)
        modified_text = "".join(modified_text_list)
        log.info(
            "%s Injected %d marker groups for %d unique sources into the answer (from %d raw citation references).",
            self.log_identifier,
            len(final_insertions),
            len(citation_details),
            len(insertions),
        )

        # 5. Create a markdown formatted list of citations
        markdown_citations_list = []
        for detail in sorted(citation_details, key=lambda x: x["number"]):
            markdown_citations_list.append(
                f"{detail['number']}. [{detail['title']}]({detail['url']}) (page {detail['page_number']})"
            )
        markdown_citations = "\n".join(markdown_citations_list)
        markdown_citations = markdown_citations.replace("\\n", "\n")

        return modified_text, citation_details, markdown_citations

    async def _save_result_as_artifact(
        self,
        tool_context: ToolContext,
        formatted_answer: str,
        markdown_citations: str,
        original_query: str,
        output_filename_base: Optional[str],
    ) -> Dict[str, Any]:
        """
        Saves the RAG response as a single combined markdown artifact.
        """
        try:
            inv_context = tool_context._invocation_context
            artifact_service = inv_context.artifact_service
            if not artifact_service:
                raise ValueError("ArtifactService is not available in the context.")

            timestamp = datetime.now(timezone.utc)
            max_query_len = self.tool_config.artifact_description_query_max_length
            truncated_query = (
                original_query[:max_query_len] + "..."
                if len(original_query) > max_query_len
                else original_query
            )

            # Combine answer and citations into a single markdown string
            combined_content = (
                f"{formatted_answer}\n\n**Sources:**\n{markdown_citations}"
            )
            combined_bytes = combined_content.encode("utf-8")

            # Determine filename
            base_name: str
            if output_filename_base and is_filename_safe(output_filename_base):
                base_name = output_filename_base
            else:
                if output_filename_base:  # It was provided but unsafe
                    log.warning(
                        "%s Provided output_filename_base '%s' is unsafe. Falling back to default.",
                        self.log_identifier,
                        output_filename_base,
                    )
                # Not provided or unsafe, use default from config
                base_name = self.tool_config.output_filename_base

            # Ensure .md extension
            if not base_name.lower().endswith(".md"):
                filename = f"{base_name}.md"
            else:
                filename = base_name

            description = f"A generative answer with citations from Nuclia RAG for query: '{truncated_query}'."
            log.info("%s Saving combined artifact '%s'", self.log_identifier, filename)

            # Save as a single artifact
            save_result = await save_artifact_with_metadata(
                artifact_service=artifact_service,
                app_name=inv_context.app_name,
                user_id=inv_context.user_id,
                session_id=get_original_session_id(inv_context),
                filename=filename,
                content_bytes=combined_bytes,
                mime_type="text/markdown",
                metadata_dict={"description": description, "source": "Nuclia RAG Tool"},
                timestamp=timestamp,
                tool_context=tool_context,
            )

            return save_result

        except Exception as e:
            log.exception(
                "%s Failed to save result artifact: %s", self.log_identifier, e
            )
            return {"status": "error", "message": str(e)}

    async def _run_async_impl(self, args: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        The main execution logic for the tool.
        """
        tool_context = kwargs.get("tool_context")
        if not tool_context:
            return {
                "status": "error",
                "message": "ToolContext is required for this tool.",
            }

        query = args.get("query")
        output_filename_base = args.get("output_filename_base")

        # 1. Apply prompt rephrasing
        rephrased_query = self._apply_prompt_rephrasing(args, tool_context)

        # 2. Apply filter template
        filter_expression, missing_filter_params = self._apply_filter_template(
            args, tool_context
        )

        # 3. Build audit metadata
        audit_metadata = self._build_audit_metadata(args, tool_context)

        # 4. Query Nuclia (with filters and audit metadata)
        ask_response = await self._query_nuclia(
            rephrased_query, filter_expression, audit_metadata
        )
        if not ask_response:
            return {
                "status": "error",
                "message": "Failed to get a generative answer from Nuclia.",
            }

        # Capture the learning_id for tracking/correlation
        learning_id = ask_response.learning_id
        log.info(
            "%s Nuclia learning_id: %s",
            self.log_identifier,
            learning_id,
        )

        # 5. Verify Answer Quality via Citations
        if not ask_response.citations:
            log.warning(
                "%s Nuclia query returned an answer but no citations. Cannot verify the source.",
                self.log_identifier,
            )
            return {
                "status": "no_answer_found",
                "message_to_llm": f"Unable to find a relevant answer for the query: '{rephrased_query}'. Suggest the user provide a more detailed request or contact HR directly.",
            }

        # 6. Format the Answer
        formatted_answer, _, markdown_citations = self._format_answer_with_citations(
            ask_response
        )

        # 7. Save Result as a single Artifact
        save_result = await self._save_result_as_artifact(
            tool_context,
            formatted_answer,
            markdown_citations,
            query,
            output_filename_base,
        )

        if save_result.get("status") != "success":
            return {
                "status": "error",
                "message": f"Answer was generated but failed to be saved as an artifact. Reason: {save_result.get('message')}",
            }

        # 8. Construct Final Tool Response
        response = {
            "status": "success",
            "nuclia_learning_id": learning_id,
            "response_artifact": {
                "filename": save_result.get("data_filename"),
                "version": save_result.get("data_version"),
                "mime_type": "text/markdown",
            },
        }

        # Add filter information to response
        if filter_expression:
            response["filter_applied"] = True
            response["applied_filter"] = filter_expression
            response["message_to_llm"] = (
                "A complete answer with citations has been generated and saved as a single markdown artifact. Filtering was applied to the search. You can present it to the user using an embed."
            )
        elif missing_filter_params:
            response["filter_applied"] = False
            response["missing_filter_parameters"] = missing_filter_params
            response["message_to_llm"] = (
                f"A complete answer with citations has been generated and saved as a single markdown artifact. "
                f"Note: Filtering was not applied because the following required parameters were missing or empty: {', '.join(missing_filter_params)}. "
                f"You can present it to the user using an embed."
            )
        else:
            response["filter_applied"] = False
            response["message_to_llm"] = (
                "A complete answer with citations has been generated and saved as a single markdown artifact. No filtering was configured. You can present it to the user using an embed."
            )

        return response
