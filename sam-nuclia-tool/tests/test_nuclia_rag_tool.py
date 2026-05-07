"""Tests for nuclia_rag_tool.py — NucliaRagTool implementation."""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

import requests

from sam_nuclia_tool.nuclia_rag_tool import NucliaRagTool
from sam_nuclia_tool.nuclia_rag_tool_config import (
    NucliaRagToolConfig,
    TemplateParameter,
    PromptRephrasingConfig,
    AuditMetadataConfig,
)

MINIMAL = {
    "tool_name": "test_nuclia_tool",
    "tool_description": "Test description",
    "base_url": "https://nuclia.cloud",
    "account_id": "test-account",
    "kb_id": "test-kb",
    "token": "test-token",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tool(extra=None):
    cfg = NucliaRagToolConfig(**{**MINIMAL, **(extra or {})})
    return NucliaRagTool(cfg)


def make_tool_context(state=None):
    ctx = MagicMock()
    ctx.state = state or {}
    ctx._invocation_context = MagicMock()
    ctx._invocation_context.agent = MagicMock()
    ctx._invocation_context.agent.host_component = MagicMock()
    ctx._invocation_context.artifact_service = MagicMock()
    return ctx


def _para_key(resource_id, suffix="f/file/0-100"):
    return f"{resource_id}/{suffix}"


def _make_source(resource_id, title="Doc", file_uri="/files/doc.pdf", page_number=1):
    para_key = _para_key(resource_id)
    position = MagicMock()
    position.page_number = page_number
    paragraph = MagicMock()
    paragraph.text = "paragraph text"
    paragraph.position = position

    field = MagicMock()
    field.paragraphs = {para_key: paragraph}

    file_val = MagicMock()
    file_val.file.uri = file_uri

    source = MagicMock()
    source.id = resource_id
    source.title = title
    source.data = MagicMock()
    source.data.files = {"f/file": file_val}
    source.fields = {"f/file": field}
    return source


def _make_ask_response(
    answer=b"Answer text.",
    citations=None,
    resource_id="res-1",
    learning_id="learn-1",
    status="success",
    augmented_context=None,
):
    source = _make_source(resource_id)
    para_key = _para_key(resource_id)
    find_result = MagicMock()
    find_result.resources = {resource_id: source}
    response = MagicMock()
    response.answer = answer
    response.citations = citations if citations is not None else {para_key: [[0, 6]]}
    response.find_result = find_result
    response.augmented_context = augmented_context
    response.learning_id = learning_id
    response.status = status
    return response


# ---------------------------------------------------------------------------
# TestNucliaRagToolInit
# ---------------------------------------------------------------------------

class TestNucliaRagToolInit:
    def test_init_with_config_object(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        assert tool.tool_config.kb_id == "test-kb"
        assert tool.log_identifier == "[NucliaRagTool]"

    def test_init_with_dict_creates_config(self):
        tool = NucliaRagTool(MINIMAL)
        assert isinstance(tool.tool_config, NucliaRagToolConfig)
        assert tool.tool_config.token == "test-token"


# ---------------------------------------------------------------------------
# TestToolProperties
# ---------------------------------------------------------------------------

class TestToolProperties:
    def test_tool_name(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        assert tool.tool_name == "test_nuclia_tool"

    def test_tool_description(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        assert "Nuclia" in tool.tool_description

    def test_parameters_schema_no_template_params(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        schema = tool.parameters_schema
        assert "query" in schema.properties

    def test_parameters_schema_with_template_params(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            template_parameters=[
                TemplateParameter(name="region", type="string", description="Region"),
            ],
        )
        tool = NucliaRagTool(cfg)
        schema = tool.parameters_schema
        assert "query" in schema.properties
        assert "region" in schema.properties

    def test_parameters_schema_excludes_context_expression_params(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            template_parameters=[
                TemplateParameter(
                    name="user_id",
                    type="string",
                    context_expression="a2a_user_config.id",
                ),
            ],
        )
        tool = NucliaRagTool(cfg)
        schema = tool.parameters_schema
        assert "user_id" not in schema.properties

    def test_parameters_schema_with_artifact_output_includes_filename(self):
        cfg = NucliaRagToolConfig(**MINIMAL, output_response_as_artifact=True)
        tool = NucliaRagTool(cfg)
        schema = tool.parameters_schema
        assert "output_filename_base" in schema.properties


# ---------------------------------------------------------------------------
# TestGetTemplateParameters
# ---------------------------------------------------------------------------

class TestGetTemplateParameters:
    def test_no_template_parameters_returns_query(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        result = tool._get_template_parameters({"query": "hello"})
        assert result == {"query": "hello"}

    def test_param_without_context_expression_uses_arg(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            template_parameters=[TemplateParameter(name="region", default="default")],
        )
        tool = NucliaRagTool(cfg)
        result = tool._get_template_parameters({"query": "q", "region": "EMEA"})
        assert result["region"] == "EMEA"

    def test_param_without_context_expression_falls_back_to_default(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            template_parameters=[TemplateParameter(name="region", default="global")],
        )
        tool = NucliaRagTool(cfg)
        result = tool._get_template_parameters({"query": "q"})
        assert result["region"] == "global"

    def test_param_with_context_expression_and_no_tool_context_uses_default(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            template_parameters=[
                TemplateParameter(
                    name="email",
                    context_expression="a2a_user_config.email",
                    default="anon@test.com",
                )
            ],
        )
        tool = NucliaRagTool(cfg)
        result = tool._get_template_parameters({"query": "q"}, tool_context=None)
        assert result["email"] == "anon@test.com"

    def test_param_with_context_expression_extracts_from_state(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            template_parameters=[
                TemplateParameter(
                    name="country",
                    context_expression="user_profile.country",
                    default="unknown",
                )
            ],
        )
        tool = NucliaRagTool(cfg)
        ctx = make_tool_context(state={"a2a_context": {"user_profile": {"country": "NL"}}})
        result = tool._get_template_parameters({"query": "q"}, tool_context=ctx)
        assert result["country"] == "NL"

    def test_param_context_expression_missing_value_uses_default(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            template_parameters=[
                TemplateParameter(
                    name="dept",
                    context_expression="profile.dept",
                    default="general",
                )
            ],
        )
        tool = NucliaRagTool(cfg)
        ctx = make_tool_context(state={"a2a_context": {}})
        result = tool._get_template_parameters({"query": "q"}, tool_context=ctx)
        assert result["dept"] == "general"


# ---------------------------------------------------------------------------
# TestSubstituteTemplateRecursively
# ---------------------------------------------------------------------------

class TestSubstituteTemplateRecursively:
    def test_string_substitution(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        assert tool._substitute_template_recursively("{x}", {"x": "hello"}) == "hello"

    def test_string_missing_key_returns_original(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        result = tool._substitute_template_recursively("{missing}", {"x": "v"})
        assert result == "{missing}"

    def test_dict_substitution(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        result = tool._substitute_template_recursively({"key": "{val}"}, {"val": "42"})
        assert result == {"key": "42"}

    def test_list_substitution(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        result = tool._substitute_template_recursively(["{a}", "{b}"], {"a": "1", "b": "2"})
        assert result == ["1", "2"]

    def test_non_string_passthrough(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        assert tool._substitute_template_recursively(42, {}) == 42
        assert tool._substitute_template_recursively(True, {}) is True
        assert tool._substitute_template_recursively(None, {}) is None

    def test_nested_dict_substitution(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        tmpl = {"outer": {"inner": "{val}"}}
        result = tool._substitute_template_recursively(tmpl, {"val": "found"})
        assert result["outer"]["inner"] == "found"


# ---------------------------------------------------------------------------
# TestCheckMissingFilterParameters
# ---------------------------------------------------------------------------

class TestCheckMissingFilterParameters:
    def test_no_filter_template_returns_empty(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        assert tool._check_missing_filter_parameters({"query": "q"}) == []

    def test_all_params_present(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            filter_expression_template={"field": "{country}"},
            template_parameters=[TemplateParameter(name="country", default="")],
        )
        tool = NucliaRagTool(cfg)
        assert tool._check_missing_filter_parameters({"query": "q", "country": "NL"}) == []

    def test_missing_param_reported(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            filter_expression_template={"field": "{country}"},
            template_parameters=[TemplateParameter(name="country", default="")],
        )
        tool = NucliaRagTool(cfg)
        missing = tool._check_missing_filter_parameters({"query": "q", "country": ""})
        assert "country" in missing

    def test_query_placeholder_never_missing(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            filter_expression_template={"q": "{query}"},
        )
        tool = NucliaRagTool(cfg)
        assert tool._check_missing_filter_parameters({"query": ""}) == []

    def test_context_expression_params_not_missing(self):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            filter_expression_template={"field": "{email}"},
            template_parameters=[
                TemplateParameter(
                    name="email",
                    context_expression="profile.email",
                    default="",
                )
            ],
        )
        tool = NucliaRagTool(cfg)
        result = tool._check_missing_filter_parameters({"query": "q"})
        assert "email" not in result


# ---------------------------------------------------------------------------
# TestApplyPromptRephrasing
# ---------------------------------------------------------------------------

class TestApplyPromptRephrasing:
    def test_no_rephrasing_config_returns_original_query(self, minimal_config, mock_tool_context):
        tool = NucliaRagTool(minimal_config)
        result = tool._apply_prompt_rephrasing({"query": "original"}, mock_tool_context)
        assert result == "original"

    def test_rephrasing_formats_template(self, config_with_rephrasing, mock_tool_context):
        tool = NucliaRagTool(config_with_rephrasing)
        result = tool._apply_prompt_rephrasing(
            {"query": "what is X?", "region": "EMEA"}, mock_tool_context
        )
        assert "what is X?" in result
        assert "EMEA" in result

    def test_rephrasing_missing_key_returns_original(self, mock_tool_context):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            prompt_rephrasing=PromptRephrasingConfig(
                template="Context: {missing_param}. {query}"
            ),
        )
        tool = NucliaRagTool(cfg)
        result = tool._apply_prompt_rephrasing({"query": "fallback"}, mock_tool_context)
        assert result == "fallback"


# ---------------------------------------------------------------------------
# TestApplyFilterTemplate
# ---------------------------------------------------------------------------

class TestApplyFilterTemplate:
    def test_no_filter_template(self, minimal_config, mock_tool_context):
        tool = NucliaRagTool(minimal_config)
        expr, missing = tool._apply_filter_template({"query": "q"}, mock_tool_context)
        assert expr is None
        assert missing == []

    def test_filter_with_missing_params(self, config_with_filter, mock_tool_context):
        tool = NucliaRagTool(config_with_filter)
        # country is empty string = missing
        expr, missing = tool._apply_filter_template(
            {"query": "q", "country": ""}, mock_tool_context
        )
        assert expr is None
        assert "country" in missing

    def test_filter_applied_successfully(self, config_with_filter, mock_tool_context):
        tool = NucliaRagTool(config_with_filter)
        expr, missing = tool._apply_filter_template(
            {"query": "q", "country": "NL"}, mock_tool_context
        )
        assert missing == []
        assert expr is not None
        assert expr["field"]["country"] == "NL"

    def test_filter_substitution_exception_returns_none(self, mock_tool_context):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            filter_expression_template={"field": "{country}"},
            template_parameters=[TemplateParameter(name="country", default="NL")],
        )
        tool = NucliaRagTool(cfg)
        # Patch _substitute_template_recursively to raise
        with patch.object(tool, "_substitute_template_recursively", side_effect=RuntimeError("boom")):
            expr, missing = tool._apply_filter_template({"query": "q", "country": "NL"}, mock_tool_context)
        assert expr is None
        assert missing == []


# ---------------------------------------------------------------------------
# TestBuildAuditMetadata
# ---------------------------------------------------------------------------

class TestBuildAuditMetadata:
    def test_audit_disabled_returns_none(self, mock_tool_context):
        cfg = NucliaRagToolConfig(
            **MINIMAL, audit_metadata=AuditMetadataConfig(enabled=False)
        )
        tool = NucliaRagTool(cfg)
        assert tool._build_audit_metadata({"query": "q"}, mock_tool_context) is None

    def test_audit_no_fields_returns_none(self, mock_tool_context):
        cfg = NucliaRagToolConfig(
            **MINIMAL, audit_metadata=AuditMetadataConfig(enabled=True, fields={})
        )
        tool = NucliaRagTool(cfg)
        assert tool._build_audit_metadata({"query": "q"}, mock_tool_context) is None

    def test_audit_not_configured_returns_none(self, minimal_config, mock_tool_context):
        tool = NucliaRagTool(minimal_config)
        assert tool._build_audit_metadata({"query": "q"}, mock_tool_context) is None

    def test_audit_returns_substituted_dict(self, config_with_audit, mock_tool_context):
        tool = NucliaRagTool(config_with_audit)
        result = tool._build_audit_metadata({"query": "my query"}, mock_tool_context)
        assert result["environment"] == "production"
        assert result["query_text"] == "my query"

    def test_audit_empty_value_skipped(self, mock_tool_context):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            audit_metadata=AuditMetadataConfig(
                enabled=True,
                fields={"env": "prod", "empty_field": "{missing_param}"},
            ),
        )
        tool = NucliaRagTool(cfg)
        result = tool._build_audit_metadata({"query": "q"}, mock_tool_context)
        assert result["env"] == "prod"
        assert "empty_field" not in result

    def test_audit_all_fields_skip_returns_none(self, mock_tool_context):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            audit_metadata=AuditMetadataConfig(
                enabled=True,
                fields={"f1": "{missing1}", "f2": "{missing2}"},
            ),
        )
        tool = NucliaRagTool(cfg)
        result = tool._build_audit_metadata({"query": "q"}, mock_tool_context)
        assert result is None

    def test_audit_size_exceeds_10kb_raises(self, mock_tool_context):
        big_value = "x" * 11000
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            audit_metadata=AuditMetadataConfig(
                enabled=True,
                fields={"big": big_value},
            ),
        )
        tool = NucliaRagTool(cfg)
        with pytest.raises(ValueError, match="exceeds 10KB limit"):
            tool._build_audit_metadata({"query": "q"}, mock_tool_context)


# ---------------------------------------------------------------------------
# TestCreateEphToken
# ---------------------------------------------------------------------------

class TestCreateEphToken:
    def test_success_returns_token(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        mock_response = MagicMock()
        mock_response.json.return_value = {"token": "eph-abc123"}
        with patch("requests.post", return_value=mock_response) as mock_post:
            result = tool._create_eph_token()
        assert result == "eph-abc123"
        mock_post.assert_called_once()

    def test_http_error_propagates(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
        with patch("requests.post", return_value=mock_response):
            with pytest.raises(requests.exceptions.HTTPError):
                tool._create_eph_token()

    def test_request_exception_propagates(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("conn")):
            with pytest.raises(requests.exceptions.ConnectionError):
                tool._create_eph_token()

    def test_missing_token_in_response_raises_value_error(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        mock_response = MagicMock()
        mock_response.json.return_value = {"not_token": "oops"}
        with patch("requests.post", return_value=mock_response):
            with pytest.raises(ValueError, match="No token found"):
                tool._create_eph_token()


# ---------------------------------------------------------------------------
# TestCreatePublicUrl
# ---------------------------------------------------------------------------

class TestCreatePublicUrl:
    def test_url_format(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        url = tool._create_public_url("https://host", "/files/doc.pdf", "mytoken")
        assert url == "https://host/files/doc.pdf?eph-token=mytoken&inline=true"


# ---------------------------------------------------------------------------
# TestFormatAnswerWithCitations
# ---------------------------------------------------------------------------

class TestFormatAnswerWithCitations:
    def test_no_citations_returns_original_text(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        resp = MagicMock()
        resp.answer = b"Just an answer."
        resp.citations = {}
        resp.find_result = MagicMock()
        resp.find_result.resources = {}
        resp.augmented_context = None
        text, details, md = tool._format_answer_with_citations(resp)
        assert text == "Just an answer."
        assert details == []
        assert md == ""

    def test_single_citation_inserts_plain_marker(self):
        cfg = NucliaRagToolConfig(**MINIMAL, inline_citation_links=False)
        tool = NucliaRagTool(cfg)
        ask_resp = _make_ask_response()
        with patch.object(tool, "_create_eph_token", return_value="tok"):
            text, details, md = tool._format_answer_with_citations(ask_resp)
        assert "[1]" in text
        assert len(details) == 1
        assert "1." in md

    def test_single_citation_inserts_inline_link_marker(self):
        cfg = NucliaRagToolConfig(**MINIMAL, inline_citation_links=True)
        tool = NucliaRagTool(cfg)
        ask_resp = _make_ask_response()
        with patch.object(tool, "_create_eph_token", return_value="tok"):
            text, details, md = tool._format_answer_with_citations(ask_resp)
        assert "[[1](" in text

    def test_citation_markdown_list_format(self):
        cfg = NucliaRagToolConfig(**MINIMAL, inline_citation_links=False)
        tool = NucliaRagTool(cfg)
        ask_resp = _make_ask_response()
        with patch.object(tool, "_create_eph_token", return_value="tok"):
            _, details, md = tool._format_answer_with_citations(ask_resp)
        assert "1." in md
        assert "page" in md

    def test_citation_skipped_when_no_file_data(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        resource_id = "res-no-file"
        para_key = _para_key(resource_id)

        source = MagicMock()
        source.id = resource_id
        source.data = MagicMock()
        source.data.files = {}  # no files

        find_result = MagicMock()
        find_result.resources = {resource_id: source}

        resp = MagicMock()
        resp.answer = b"Answer."
        resp.citations = {para_key: [[0, 4]]}
        resp.find_result = find_result
        resp.augmented_context = None

        with patch.object(tool, "_create_eph_token", return_value="tok"):
            text, details, md = tool._format_answer_with_citations(resp)
        # Citation was skipped so no details
        assert details == []

    def test_multiple_paragraphs_same_url_grouped(self):
        cfg = NucliaRagToolConfig(**MINIMAL, inline_citation_links=False)
        tool = NucliaRagTool(cfg)

        resource_id = "res-multi"
        source = _make_source(resource_id, file_uri="/files/same.pdf", page_number=1)
        # Add a second paragraph in the same field with the SAME page number
        para_key_2 = f"{resource_id}/f/file/100-200"
        position2 = MagicMock()
        position2.page_number = 1  # Same page → same URL key → grouped
        paragraph2 = MagicMock()
        paragraph2.text = "more text"
        paragraph2.position = position2
        source.fields["f/file"].paragraphs[para_key_2] = paragraph2

        find_result = MagicMock()
        find_result.resources = {resource_id: source}

        resp = MagicMock()
        resp.answer = b"Long answer text here."
        resp.citations = {
            _para_key(resource_id): [[0, 4]],
            para_key_2: [[5, 10]],
        }
        resp.find_result = find_result
        resp.augmented_context = None

        with patch.object(tool, "_create_eph_token", return_value="tok"):
            text, details, md = tool._format_answer_with_citations(resp)
        # Both paragraphs from same resource/URL/page → grouped into 1 citation number
        assert len(details) == 1

    def test_augmented_context_positions_used(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        resource_id = "res-aug"
        para_key = _para_key(resource_id)

        source = _make_source(resource_id)
        # Remove position from original field
        source.fields["f/file"].paragraphs[para_key].position = None

        find_result = MagicMock()
        find_result.resources = {resource_id: source}

        # Provide position via augmented context
        aug_position = MagicMock()
        aug_position.page_number = 5
        aug_para = MagicMock()
        aug_para.position = aug_position

        augmented_context = MagicMock()
        augmented_context.paragraphs = {para_key: aug_para}
        augmented_context.fields = {}

        resp = MagicMock()
        resp.answer = b"Augmented answer."
        resp.citations = {para_key: [[0, 4]]}
        resp.find_result = find_result
        resp.augmented_context = augmented_context

        with patch.object(tool, "_create_eph_token", return_value="tok"):
            text, details, md = tool._format_answer_with_citations(resp)
        assert len(details) == 1
        assert details[0]["page_number"] == 5

    def test_eph_token_exception_propagates(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        ask_resp = _make_ask_response()
        with patch.object(tool, "_create_eph_token", side_effect=Exception("token error")):
            with pytest.raises(Exception, match="token error"):
                tool._format_answer_with_citations(ask_resp)


# ---------------------------------------------------------------------------
# TestQueryNuclia
# ---------------------------------------------------------------------------

class TestQueryNuclia:
    async def test_returns_none_when_ask_returns_no_answer(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        mock_search = MagicMock()
        mock_search.ask.return_value = None
        with (
            patch("sam_nuclia_tool.nuclia_rag_tool.sdk") as mock_sdk,
        ):
            mock_sdk.NucliaAuth.return_value = MagicMock()
            mock_sdk.NucliaSearch.return_value = mock_search
            result = await tool._query_nuclia("test query")
        assert result is None

    async def test_returns_response_on_success(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        mock_response = MagicMock()
        mock_response.answer = b"Great answer"
        mock_search = MagicMock()
        mock_search.ask.return_value = mock_response
        with patch("sam_nuclia_tool.nuclia_rag_tool.sdk") as mock_sdk:
            mock_sdk.NucliaAuth.return_value = MagicMock()
            mock_sdk.NucliaSearch.return_value = mock_search
            result = await tool._query_nuclia("test query")
        assert result is mock_response

    async def test_exception_returns_none(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        with patch("sam_nuclia_tool.nuclia_rag_tool.sdk") as mock_sdk:
            mock_sdk.NucliaAuth.return_value = MagicMock()
            mock_sdk.NucliaSearch.side_effect = RuntimeError("network error")
            result = await tool._query_nuclia("test query")
        assert result is None

    async def test_filter_expression_applied(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        mock_response = MagicMock()
        mock_response.answer = b"With filter"
        mock_search = MagicMock()
        mock_search.ask.return_value = mock_response
        filter_expr = {"field": {"country": "NL"}}
        with patch("sam_nuclia_tool.nuclia_rag_tool.sdk") as mock_sdk:
            mock_sdk.NucliaAuth.return_value = MagicMock()
            mock_sdk.NucliaSearch.return_value = mock_search
            with patch("sam_nuclia_tool.nuclia_rag_tool.FilterExpression"):
                result = await tool._query_nuclia("q", filter_expression=filter_expr)
        assert result is mock_response

    async def test_filter_expression_error_proceeds_without_filter(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        mock_response = MagicMock()
        mock_response.answer = b"No filter fallback"
        mock_search = MagicMock()
        mock_search.ask.return_value = mock_response
        with patch("sam_nuclia_tool.nuclia_rag_tool.sdk") as mock_sdk:
            mock_sdk.NucliaAuth.return_value = MagicMock()
            mock_sdk.NucliaSearch.return_value = mock_search
            with patch(
                "sam_nuclia_tool.nuclia_rag_tool.FilterExpression",
                side_effect=Exception("bad filter"),
            ):
                result = await tool._query_nuclia("q", filter_expression={"bad": "data"})
        assert result is mock_response


# ---------------------------------------------------------------------------
# TestRunAsyncImpl
# ---------------------------------------------------------------------------

class TestRunAsyncImpl:
    async def test_no_tool_context_returns_error(self, minimal_config):
        tool = NucliaRagTool(minimal_config)
        result = await tool._run_async_impl(args={"query": "q"})
        assert result["status"] == "error"
        assert "ToolContext" in result["message"]

    async def test_nuclia_failure_returns_error(self, minimal_config, mock_tool_context):
        tool = NucliaRagTool(minimal_config)
        with patch.object(tool, "_query_nuclia", new=AsyncMock(return_value=None)):
            result = await tool._run_async_impl(
                args={"query": "q"}, tool_context=mock_tool_context
            )
        assert result["status"] == "error"

    async def test_no_citations_returns_no_answer_found(self, minimal_config, mock_tool_context):
        tool = NucliaRagTool(minimal_config)
        mock_resp = _make_ask_response(citations={})
        with patch.object(tool, "_query_nuclia", new=AsyncMock(return_value=mock_resp)):
            result = await tool._run_async_impl(
                args={"query": "q"}, tool_context=mock_tool_context
            )
        assert result["status"] == "no_answer_found"

    async def test_success_response_content(self, mock_tool_context):
        cfg = NucliaRagToolConfig(**MINIMAL, output_response_as_artifact=False)
        tool = NucliaRagTool(cfg)
        mock_resp = _make_ask_response()
        with (
            patch.object(tool, "_query_nuclia", new=AsyncMock(return_value=mock_resp)),
            patch.object(tool, "_create_eph_token", return_value="tok"),
        ):
            result = await tool._run_async_impl(
                args={"query": "q"}, tool_context=mock_tool_context
            )
        assert result["status"] == "success"
        assert "response_content" in result

    async def test_success_response_as_artifact(self, mock_tool_context):
        cfg = NucliaRagToolConfig(**MINIMAL, output_response_as_artifact=True)
        tool = NucliaRagTool(cfg)
        mock_resp = _make_ask_response()
        save_result = {"status": "success", "data_filename": "out.md", "data_version": 1}
        with (
            patch.object(tool, "_query_nuclia", new=AsyncMock(return_value=mock_resp)),
            patch.object(tool, "_save_result_as_artifact", new=AsyncMock(return_value=save_result)),
            patch.object(tool, "_create_eph_token", return_value="tok"),
        ):
            result = await tool._run_async_impl(
                args={"query": "q"}, tool_context=mock_tool_context
            )
        assert result["status"] == "success"
        assert "response_artifact" in result
        assert result["response_artifact"]["filename"] == "out.md"

    async def test_artifact_save_failure_returns_error(self, mock_tool_context):
        cfg = NucliaRagToolConfig(**MINIMAL, output_response_as_artifact=True)
        tool = NucliaRagTool(cfg)
        mock_resp = _make_ask_response()
        save_result = {"status": "error", "message": "disk full"}
        with (
            patch.object(tool, "_query_nuclia", new=AsyncMock(return_value=mock_resp)),
            patch.object(tool, "_save_result_as_artifact", new=AsyncMock(return_value=save_result)),
            patch.object(tool, "_create_eph_token", return_value="tok"),
        ):
            result = await tool._run_async_impl(
                args={"query": "q"}, tool_context=mock_tool_context
            )
        assert result["status"] == "error"

    async def test_citations_in_response_when_flag_set(self, mock_tool_context):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            output_response_as_artifact=False,
            include_citations_in_tool_response=True,
        )
        tool = NucliaRagTool(cfg)
        mock_resp = _make_ask_response()
        with (
            patch.object(tool, "_query_nuclia", new=AsyncMock(return_value=mock_resp)),
            patch.object(tool, "_create_eph_token", return_value="tok"),
        ):
            result = await tool._run_async_impl(
                args={"query": "q"}, tool_context=mock_tool_context
            )
        assert "citations" in result

    async def test_filter_applied_in_response(self, mock_tool_context):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            output_response_as_artifact=False,
            filter_expression_template={"field": "{country}"},
            template_parameters=[TemplateParameter(name="country", default="")],
        )
        tool = NucliaRagTool(cfg)
        mock_resp = _make_ask_response()
        with (
            patch.object(tool, "_query_nuclia", new=AsyncMock(return_value=mock_resp)),
            patch.object(tool, "_create_eph_token", return_value="tok"),
        ):
            result = await tool._run_async_impl(
                args={"query": "q", "country": "DE"}, tool_context=mock_tool_context
            )
        assert result["filter_applied"] is True
        assert "applied_filter" in result

    async def test_missing_filter_params_in_response(self, mock_tool_context):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            output_response_as_artifact=False,
            filter_expression_template={"field": "{country}"},
            template_parameters=[TemplateParameter(name="country", default="")],
        )
        tool = NucliaRagTool(cfg)
        mock_resp = _make_ask_response()
        with (
            patch.object(tool, "_query_nuclia", new=AsyncMock(return_value=mock_resp)),
            patch.object(tool, "_create_eph_token", return_value="tok"),
        ):
            result = await tool._run_async_impl(
                args={"query": "q", "country": ""}, tool_context=mock_tool_context
            )
        assert result["filter_applied"] is False
        assert "missing_filter_parameters" in result
        assert "country" in result["missing_filter_parameters"]

    async def test_no_filter_configured_in_response(self, mock_tool_context):
        cfg = NucliaRagToolConfig(**MINIMAL, output_response_as_artifact=False)
        tool = NucliaRagTool(cfg)
        mock_resp = _make_ask_response()
        with (
            patch.object(tool, "_query_nuclia", new=AsyncMock(return_value=mock_resp)),
            patch.object(tool, "_create_eph_token", return_value="tok"),
        ):
            result = await tool._run_async_impl(
                args={"query": "q"}, tool_context=mock_tool_context
            )
        assert result["filter_applied"] is False
        assert "missing_filter_parameters" not in result

    async def test_remi_publish_called_when_configured(self, mock_tool_context):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            output_response_as_artifact=False,
            remi_publish_topic="sam/remi/{interaction_id}/{tool_name}/{learning_id}",
        )
        tool = NucliaRagTool(cfg)
        mock_resp = _make_ask_response()
        mock_tool_context.state = {"a2a_context": {"logical_task_id": "task-123"}}
        with (
            patch.object(tool, "_query_nuclia", new=AsyncMock(return_value=mock_resp)),
            patch.object(tool, "_create_eph_token", return_value="tok"),
        ):
            result = await tool._run_async_impl(
                args={"query": "q"}, tool_context=mock_tool_context
            )
        mock_tool_context._invocation_context.agent.host_component.publish_a2a_message.assert_called_once()
        assert result["status"] == "success"

    async def test_remi_publish_no_host_component_no_exception(self, mock_tool_context):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            output_response_as_artifact=False,
            remi_publish_topic="sam/remi/{interaction_id}/{tool_name}/{learning_id}",
        )
        tool = NucliaRagTool(cfg)
        mock_resp = _make_ask_response()
        # Remove host_component
        mock_tool_context._invocation_context.agent.host_component = None
        with (
            patch.object(tool, "_query_nuclia", new=AsyncMock(return_value=mock_resp)),
            patch.object(tool, "_create_eph_token", return_value="tok"),
        ):
            result = await tool._run_async_impl(
                args={"query": "q"}, tool_context=mock_tool_context
            )
        assert result["status"] == "success"

    async def test_remi_publish_exception_does_not_fail_tool(self, mock_tool_context):
        cfg = NucliaRagToolConfig(
            **MINIMAL,
            output_response_as_artifact=False,
            remi_publish_topic="sam/remi/{interaction_id}/{tool_name}/{learning_id}",
        )
        tool = NucliaRagTool(cfg)
        mock_resp = _make_ask_response()
        mock_tool_context._invocation_context.agent.host_component.publish_a2a_message.side_effect = RuntimeError("publish failed")
        with (
            patch.object(tool, "_query_nuclia", new=AsyncMock(return_value=mock_resp)),
            patch.object(tool, "_create_eph_token", return_value="tok"),
        ):
            result = await tool._run_async_impl(
                args={"query": "q"}, tool_context=mock_tool_context
            )
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# TestSaveResultAsArtifact
# ---------------------------------------------------------------------------

class TestSaveResultAsArtifact:
    async def test_artifact_saved_successfully(self, minimal_config, mock_tool_context):
        tool = NucliaRagTool(minimal_config)
        save_return = {"status": "success", "data_filename": "out.md", "data_version": 1}
        with patch(
            "sam_nuclia_tool.nuclia_rag_tool.save_artifact_with_metadata",
            new=AsyncMock(return_value=save_return),
        ):
            result = await tool._save_result_as_artifact(
                mock_tool_context, "answer", "citations", "query", None
            )
        assert result["status"] == "success"
        assert result["data_filename"] == "out.md"

    async def test_artifact_no_service_returns_error(self, minimal_config, mock_tool_context):
        tool = NucliaRagTool(minimal_config)
        mock_tool_context._invocation_context.artifact_service = None
        result = await tool._save_result_as_artifact(
            mock_tool_context, "answer", "citations", "query", None
        )
        assert result["status"] == "error"

    async def test_artifact_uses_provided_filename(self, minimal_config, mock_tool_context):
        tool = NucliaRagTool(minimal_config)
        save_return = {"status": "success", "data_filename": "myfile.md", "data_version": 1}
        with patch(
            "sam_nuclia_tool.nuclia_rag_tool.save_artifact_with_metadata",
            new=AsyncMock(return_value=save_return),
        ) as mock_save:
            await tool._save_result_as_artifact(
                mock_tool_context, "answer", "citations", "query", "myfile"
            )
        call_kwargs = mock_save.call_args
        assert "myfile" in str(call_kwargs)

    async def test_artifact_unsafe_filename_uses_default(self, minimal_config, mock_tool_context):
        tool = NucliaRagTool(minimal_config)
        save_return = {"status": "success", "data_filename": "nuclia_answer.md", "data_version": 1}
        with patch(
            "sam_nuclia_tool.nuclia_rag_tool.save_artifact_with_metadata",
            new=AsyncMock(return_value=save_return),
        ) as mock_save:
            await tool._save_result_as_artifact(
                mock_tool_context, "answer", "citations", "query", "../../bad/path"
            )
        call_kwargs = mock_save.call_args
        assert "nuclia_answer" in str(call_kwargs)
