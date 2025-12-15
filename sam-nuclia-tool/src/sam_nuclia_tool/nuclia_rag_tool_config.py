"""
Pydantic configuration models for the NucliaRagTool.

This module defines the validated configuration schema for the generic Nuclia RAG tool,
providing type safety, automatic validation, and clear documentation of all configuration options.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self


class TemplateParameter(BaseModel):
    """
    Defines a dynamic parameter that can be used in templates (prompt rephrasing and filters).

    These parameters can either be passed by the LLM at runtime, or automatically extracted
    from the context using a context_expression.
    """

    name: str = Field(
        description="The name of the parameter. Must be a valid Python identifier."
    )
    description: str = Field(
        default="",
        description="A description of the parameter for the LLM to understand its purpose.",
    )
    type: str = Field(
        default="string",
        description="The data type of the parameter. Must be one of: string, boolean, integer, number.",
    )
    required: bool = Field(
        default=False,
        description="Whether this parameter is required when calling the tool.",
    )
    nullable: bool = Field(
        default=True, description="Whether this parameter can be null/None."
    )
    default: Optional[Any] = Field(
        default=None,
        description="The default value to use if the parameter is not provided.",
    )
    context_expression: Optional[str] = Field(
        default=None,
        description=(
            "Optional expression to extract the parameter value from the context. "
            "If provided, the parameter will be automatically populated from the context "
            "and will not be exposed to the LLM. "
            "Example: 'a2a_user_config.user_profile.workEmail'"
        ),
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validates that the type is one of the allowed values."""
        allowed_types = {"string", "boolean", "integer", "number"}
        if v not in allowed_types:
            raise ValueError(
                f"Parameter type must be one of {allowed_types}, got '{v}'"
            )
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validates that the name is a valid Python identifier."""
        if not v.isidentifier():
            raise ValueError(f"Parameter name '{v}' is not a valid Python identifier")
        return v


class PromptRephrasingConfig(BaseModel):
    """
    Configuration for dynamic prompt rephrasing using templates.

    This allows the tool to enrich the user's query with contextual information
    before sending it to Nuclia for retrieval.
    """

    template: str = Field(
        description=(
            "The prompt template string. Must contain {query} placeholder for the user's query. "
            "Can contain other placeholders matching template_parameters names."
        ),
        min_length=1,
    )

    @field_validator("template")
    @classmethod
    def validate_template_has_query(cls, v: str) -> str:
        """Validates that the template contains the required {query} placeholder."""
        if "{query}" not in v:
            raise ValueError(
                "Prompt rephrasing template must contain the {query} placeholder"
            )
        return v


class AuditMetadataConfig(BaseModel):
    """
    Configuration for audit metadata to be included in Nuclia search requests.

    All dynamic values must come from template_parameters. Use static strings
    for constant values.
    """

    enabled: bool = Field(
        default=True, description="Whether to include audit metadata in requests"
    )

    fields: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Dictionary of audit metadata fields. Keys are the metadata field names, "
            "values are templates that can contain:\n"
            "- Static text: 'production'\n"
            "- {query}: The user's query\n"
            "- Any template_parameters: {country}, {cla}, {user_email}, etc.\n"
            "\n"
            "All dynamic values must be defined in template_parameters."
        ),
        examples=[
            {
                "environment": "production",
                "agent": "nuclia_agent",
                "user_country": "{country}",
                "user_email": "{user_email}",
                "query_text": "{query}",
            }
        ],
    )


class NucliaRagToolConfig(BaseModel):
    """
    Complete configuration model for the NucliaRagTool.

    This model validates all configuration options and provides sensible defaults
    where appropriate.
    """

    tool_name: str = Field(
        default="NucliaRagTool",
        description="The name of the tool as it will appear to the agent.",
        min_length=1,
    )

    # --- Required Nuclia Connection Details ---
    base_url: str = Field(
        description="The base URL for the Nuclia API (e.g., 'https://europe-1.nuclia.cloud/api/v1')"
    )
    kb_id: str = Field(
        description="The unique ID of the Nuclia Knowledge Box to query", min_length=1
    )
    token: str = Field(
        description="The Nuclia Service Account API token for authentication",
        min_length=1,
    )
    api_key: str = Field(description="The Nuclia Account ID", min_length=1)

    # --- Performance & Cost Control ---
    top_k: int = Field(
        default=5,
        ge=1,
        le=200,
        description="Maximum number of context paragraphs to retrieve from Nuclia (1-200)",
    )

    output_response_as_artifact: bool = Field(
        default=True,
        description="If true, the tool's response will be output as a markdown artifact",
    )

    # --- Artifact Configuration ---
    output_filename_base: str = Field(
        default="nuclia_answer",
        description="Base name for output artifacts. The tool will append '.md' extension.",
    )

    artifact_description_query_max_length: int = Field(
        default=150,
        ge=1,
        description="Maximum character length of the query to include in artifact descriptions",
    )
    inline_citation_links: bool = Field(
        default=True,
        description="If true, citation markers will be rendered as clickable markdown links",
    )

    include_citations_in_tool_response: bool = Field(
        default=False,
        description="If true, citations are included as a separate field in the tool response",
    )

    # --- Template-Based Configuration ---
    template_parameters: List[TemplateParameter] = Field(
        default_factory=list,
        description=(
            "List of dynamic parameters that can be used in prompt rephrasing, filter templates, "
            "and audit metadata. These parameters become part of the tool's schema."
        ),
    )

    prompt_rephrasing: Optional[PromptRephrasingConfig] = Field(
        default=None,
        description=(
            "Configuration for dynamic prompt rephrasing. If not provided, "
            "the original user query is sent to Nuclia without modification."
        ),
    )

    filter_expression_template: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Template for Nuclia filter expressions. Can contain placeholders matching "
            "template_parameters names. If any required parameters are missing at runtime, "
            "no filtering will be applied."
        ),
    )

    audit_metadata: Optional[AuditMetadataConfig] = Field(
        default=None,
        description=(
            "Configuration for audit metadata to include in Nuclia search requests. "
            "Uses template-based substitution from template_parameters. "
            "This metadata can be used for filtering and analyzing activity logs."
        ),
    )

    # --- Backward Compatibility (Deprecated) ---
    context_parameters: Optional[List[TemplateParameter]] = Field(
        default=None,
        description="DEPRECATED: Use 'template_parameters' instead. Provided for backward compatibility.",
        exclude=True,  # Don't include in serialization
    )

    @model_validator(mode="after")
    def handle_deprecated_context_parameters(self) -> Self:
        """
        Handles backward compatibility for the deprecated 'context_parameters' field.

        If 'context_parameters' is provided and 'template_parameters' is empty,
        copies the values and logs a deprecation warning.
        """
        if self.context_parameters is not None:
            from solace_ai_connector.common.log import log

            log.warning(
                "[NucliaRagTool] 'context_parameters' is deprecated. "
                "Please use 'template_parameters' instead."
            )
            if not self.template_parameters:
                self.template_parameters = self.context_parameters
        return self

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validates that base_url is a properly formatted URL."""
        # Basic URL validation - ensure it starts with http:// or https://
        if not v.startswith(("http://", "https://")):
            raise ValueError(
                f"base_url must start with 'http://' or 'https://', got '{v}'"
            )
        # Remove trailing slash for consistency
        return v.rstrip("/")

    @field_validator("template_parameters")
    @classmethod
    def validate_unique_parameter_names(
        cls, v: List[TemplateParameter]
    ) -> List[TemplateParameter]:
        """Validates that all template parameter names are unique."""
        names = [param.name for param in v]
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            raise ValueError(
                f"Duplicate template parameter names found: {set(duplicates)}"
            )
        return v

    class Config:
        """Pydantic model configuration."""

        # Allow extra fields for forward compatibility
        extra = "allow"
        # Use enum values instead of enum objects in serialization
        use_enum_values = True
