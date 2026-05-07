"""Shared fixtures for sam-nuclia-tool tests."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from sam_nuclia_tool.nuclia_rag_tool_config import (
    NucliaRagToolConfig,
    TemplateParameter,
    PromptRephrasingConfig,
    AuditMetadataConfig,
)

MINIMAL_CONFIG_DICT = {
    "tool_name": "test_nuclia_tool",
    "tool_description": "Test description",
    "base_url": "https://nuclia.cloud",
    "account_id": "test-account",
    "kb_id": "test-kb",
    "token": "test-token",
}


@pytest.fixture
def minimal_config():
    return NucliaRagToolConfig(**MINIMAL_CONFIG_DICT)


@pytest.fixture
def config_with_rephrasing():
    return NucliaRagToolConfig(
        **MINIMAL_CONFIG_DICT,
        prompt_rephrasing=PromptRephrasingConfig(
            template="Context: region={region}. Query: {query}"
        ),
        template_parameters=[
            TemplateParameter(name="region", type="string", default="global"),
        ],
    )


@pytest.fixture
def config_with_filter():
    return NucliaRagToolConfig(
        **MINIMAL_CONFIG_DICT,
        filter_expression_template={"field": {"country": "{country}"}},
        template_parameters=[
            TemplateParameter(name="country", type="string", default=""),
        ],
    )


@pytest.fixture
def config_with_audit():
    return NucliaRagToolConfig(
        **MINIMAL_CONFIG_DICT,
        audit_metadata=AuditMetadataConfig(
            enabled=True,
            fields={
                "environment": "production",
                "query_text": "{query}",
            },
        ),
    )


@pytest.fixture
def mock_tool_context():
    ctx = MagicMock()
    ctx.state = {}
    ctx._invocation_context = MagicMock()
    ctx._invocation_context.agent = MagicMock()
    ctx._invocation_context.agent.host_component = MagicMock()
    ctx._invocation_context.artifact_service = MagicMock()
    return ctx


def _make_paragraph(text="Sample text", page_number=1):
    para = MagicMock()
    para.text = text
    para.position = MagicMock()
    para.position.page_number = page_number
    return para


def _make_field(paragraphs: dict):
    field = MagicMock()
    field.paragraphs = paragraphs
    return field


def _make_file_value(uri="/files/doc.pdf"):
    file_val = MagicMock()
    file_val.file.uri = uri
    return file_val


def _make_source(resource_id, title="Test Doc", file_uri="/files/doc.pdf"):
    source = MagicMock()
    source.id = resource_id
    source.title = title
    source.data = MagicMock()
    source.data.files = {"f/file": _make_file_value(file_uri)}
    paragraph = _make_paragraph()
    source.fields = {"f/file": _make_field({f"{resource_id}/f/file/0-100": paragraph})}
    return source


@pytest.fixture
def mock_ask_response():
    """Builds a realistic mock AskAnswer with one citation."""
    resource_id = "resource-abc"
    para_key = f"{resource_id}/f/file/0-100"

    source = _make_source(resource_id, title="Test Document", file_uri="/files/doc.pdf")
    # Give the paragraph a position
    source.fields["f/file"].paragraphs[para_key].position.page_number = 3

    find_result = MagicMock()
    find_result.resources = {resource_id: source}

    response = MagicMock()
    response.answer = b"This is the answer text."
    response.citations = {para_key: [[0, 4]]}
    response.find_result = find_result
    response.augmented_context = None
    response.learning_id = "learn-xyz"
    response.status = "success"
    return response
