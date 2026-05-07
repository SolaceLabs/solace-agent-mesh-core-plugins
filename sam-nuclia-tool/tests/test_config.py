"""Tests for nuclia_rag_tool_config.py Pydantic models."""

import pytest
from pydantic import ValidationError

from sam_nuclia_tool.nuclia_rag_tool_config import (
    NucliaRagToolConfig,
    TemplateParameter,
    PromptRephrasingConfig,
    AuditMetadataConfig,
)

MINIMAL = {
    "tool_name": "test_tool",
    "tool_description": "desc",
    "base_url": "https://nuclia.cloud",
    "account_id": "acct",
    "kb_id": "kb",
    "token": "tok",
}


class TestTemplateParameter:
    def test_valid_string_type(self):
        p = TemplateParameter(name="region", type="string")
        assert p.type == "string"

    def test_valid_boolean_type(self):
        p = TemplateParameter(name="flag", type="boolean")
        assert p.type == "boolean"

    def test_valid_integer_type(self):
        p = TemplateParameter(name="count", type="integer")
        assert p.type == "integer"

    def test_valid_number_type(self):
        p = TemplateParameter(name="score", type="number")
        assert p.type == "number"

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError, match="Parameter type must be one of"):
            TemplateParameter(name="p", type="array")

    def test_valid_identifier_name(self):
        p = TemplateParameter(name="user_email")
        assert p.name == "user_email"

    def test_invalid_identifier_name_raises(self):
        with pytest.raises(ValidationError, match="not a valid Python identifier"):
            TemplateParameter(name="bad-name")

    def test_invalid_identifier_with_space_raises(self):
        with pytest.raises(ValidationError, match="not a valid Python identifier"):
            TemplateParameter(name="bad name")

    def test_context_expression_defaults_to_none(self):
        p = TemplateParameter(name="x")
        assert p.context_expression is None

    def test_context_expression_can_be_set(self):
        p = TemplateParameter(name="x", context_expression="a2a_user_config.email")
        assert p.context_expression == "a2a_user_config.email"

    def test_required_defaults_false(self):
        p = TemplateParameter(name="x")
        assert p.required is False

    def test_default_value(self):
        p = TemplateParameter(name="x", default="fallback")
        assert p.default == "fallback"


class TestPromptRephrasingConfig:
    def test_valid_template_with_query(self):
        cfg = PromptRephrasingConfig(template="Answer {query} well.")
        assert "{query}" in cfg.template

    def test_template_without_query_raises(self):
        with pytest.raises(ValidationError, match="must contain the \\{query\\} placeholder"):
            PromptRephrasingConfig(template="No placeholder here.")

    def test_template_empty_raises(self):
        with pytest.raises(ValidationError):
            PromptRephrasingConfig(template="")


class TestNucliaRagToolConfig:
    def test_minimal_config_validates(self):
        cfg = NucliaRagToolConfig(**MINIMAL)
        assert cfg.tool_name == "test_tool"
        assert cfg.kb_id == "kb"

    def test_trailing_slash_stripped_from_url(self):
        cfg = NucliaRagToolConfig(**{**MINIMAL, "base_url": "https://nuclia.cloud/"})
        assert cfg.base_url == "https://nuclia.cloud"

    def test_multiple_trailing_slashes_stripped(self):
        cfg = NucliaRagToolConfig(**{**MINIMAL, "base_url": "https://nuclia.cloud///"})
        assert cfg.base_url == "https://nuclia.cloud"

    def test_http_url_is_valid(self):
        cfg = NucliaRagToolConfig(**{**MINIMAL, "base_url": "http://nuclia.local"})
        assert cfg.base_url == "http://nuclia.local"

    def test_invalid_url_protocol_raises(self):
        with pytest.raises(ValidationError, match="must start with"):
            NucliaRagToolConfig(**{**MINIMAL, "base_url": "ftp://nuclia.cloud"})

    def test_relative_url_raises(self):
        with pytest.raises(ValidationError, match="must start with"):
            NucliaRagToolConfig(**{**MINIMAL, "base_url": "nuclia.cloud"})

    def test_duplicate_parameter_names_raises(self):
        params = [
            {"name": "region", "type": "string"},
            {"name": "region", "type": "string"},
        ]
        with pytest.raises(ValidationError, match="Duplicate template parameter names"):
            NucliaRagToolConfig(**{**MINIMAL, "template_parameters": params})

    def test_unique_parameter_names_passes(self):
        params = [
            {"name": "region", "type": "string"},
            {"name": "country", "type": "string"},
        ]
        cfg = NucliaRagToolConfig(**{**MINIMAL, "template_parameters": params})
        assert len(cfg.template_parameters) == 2

    def test_deprecated_context_parameters_migrates(self):
        params = [{"name": "region", "type": "string"}]
        cfg = NucliaRagToolConfig(**{**MINIMAL, "context_parameters": params})
        assert len(cfg.template_parameters) == 1
        assert cfg.template_parameters[0].name == "region"

    def test_deprecated_context_parameters_ignored_if_template_parameters_set(self):
        context_params = [{"name": "region", "type": "string"}]
        template_params = [{"name": "country", "type": "string"}]
        cfg = NucliaRagToolConfig(
            **{
                **MINIMAL,
                "context_parameters": context_params,
                "template_parameters": template_params,
            }
        )
        # template_parameters takes precedence; context_parameters not copied
        assert len(cfg.template_parameters) == 1
        assert cfg.template_parameters[0].name == "country"

    def test_output_response_as_artifact_default_true(self):
        cfg = NucliaRagToolConfig(**MINIMAL)
        assert cfg.output_response_as_artifact is True

    def test_inline_citation_links_default_true(self):
        cfg = NucliaRagToolConfig(**MINIMAL)
        assert cfg.inline_citation_links is True

    def test_top_k_default(self):
        cfg = NucliaRagToolConfig(**MINIMAL)
        assert cfg.top_k == 5

    def test_audit_metadata_config(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            audit_metadata={"enabled": True, "fields": {"env": "prod"}},
        )
        assert cfg.audit_metadata.enabled is True
        assert cfg.audit_metadata.fields["env"] == "prod"

    def test_prompt_rephrasing_config(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            prompt_rephrasing={"template": "Context: {query}"},
        )
        assert "{query}" in cfg.prompt_rephrasing.template

    def test_remi_publish_topic(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL, remi_publish_topic="sam/remi/{interaction_id}"
        )
        assert cfg.remi_publish_topic == "sam/remi/{interaction_id}"
