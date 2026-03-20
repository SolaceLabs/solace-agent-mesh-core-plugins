"""Unit tests for utility functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import json

from sam_slack_gateway_adapter import utils


class TestCreateSlackSessionId:
    """Test suite for create_slack_session_id function."""

    def test_session_id_with_thread(self):
        """Test creating session ID with thread timestamp."""
        session_id = utils.create_slack_session_id("C12345", "1234567890.123456")
        assert session_id == "slack-C12345-1234567890_123456"

    def test_session_id_without_thread(self):
        """Test creating session ID without thread timestamp."""
        session_id = utils.create_slack_session_id("C12345", None)
        assert session_id == "slack-C12345"

    def test_session_id_replaces_dots(self):
        """Test that dots in timestamp are replaced with underscores."""
        session_id = utils.create_slack_session_id("C12345", "123.456.789")
        assert "." not in session_id
        assert session_id == "slack-C12345-123_456_789"


class TestCorrectSlackMarkdown:
    """Test suite for correct_slack_markdown function."""

    def test_convert_bold(self):
        """Test converting **bold** to *bold*."""
        text = "This is **bold** text"
        result = utils.correct_slack_markdown(text)
        assert result == "This is *bold* text"

    def test_convert_links(self):
        """Test converting [text](url) to <url|text>."""
        text = "Check out [Google](https://google.com)"
        result = utils.correct_slack_markdown(text)
        assert result == "Check out <https://google.com|Google>"

    def test_convert_headings(self):
        """Test converting ### Heading to *Heading*."""
        text = "### My Heading"
        result = utils.correct_slack_markdown(text)
        assert "*My Heading*" in result

    def test_preserve_code_blocks(self):
        """Test that content inside code blocks is preserved."""
        text = "Normal **bold** text\n```python\n**not bold**\n```\nMore **bold**"
        result = utils.correct_slack_markdown(text)
        assert "```\n**not bold**\n```" in result
        # First bold should be converted
        lines = result.split("\n")
        assert "*bold*" in lines[0]

    def test_remove_language_from_code_blocks(self):
        """Test that language specifiers are removed from code blocks."""
        text = "```python\nprint('hello')\n```"
        result = utils.correct_slack_markdown(text)
        assert result == "```\nprint('hello')\n```"

    def test_non_string_input(self):
        """Test handling non-string input."""
        result = utils.correct_slack_markdown(None)
        assert result is None

    def test_multiple_formatting_types(self):
        """Test handling multiple formatting types together."""
        text = "**Bold** and [link](https://example.com)"
        result = utils.correct_slack_markdown(text)
        assert "*Bold*" in result
        assert "<https://example.com|link>" in result


class TestBuildSlackBlocks:
    """Test suite for build_slack_blocks function."""

    def test_build_with_status_only(self):
        """Test building blocks with only status text."""
        blocks = utils.build_slack_blocks(status_text="Processing...")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "context"
        assert blocks[0]["elements"][0]["text"] == "Processing..."

    def test_build_with_content_only(self):
        """Test building blocks with only content text."""
        blocks = utils.build_slack_blocks(content_text="Hello world")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["text"] == "Hello world"

    def test_build_with_empty_content(self):
        """Test building blocks with empty content text."""
        blocks = utils.build_slack_blocks(content_text="")
        assert len(blocks) == 1
        assert blocks[0]["text"]["text"] == " "  # Slack requires non-empty

    def test_build_with_status_and_content(self):
        """Test building blocks with both status and content."""
        blocks = utils.build_slack_blocks(
            status_text="Processing...", content_text="Here's the result"
        )
        assert len(blocks) == 2
        assert blocks[0]["type"] == "context"
        assert blocks[1]["type"] == "section"

    def test_build_with_feedback_elements(self):
        """Test building blocks with feedback elements."""
        feedback_elements = [
            {"type": "button", "text": {"type": "plain_text", "text": "👍"}}
        ]
        blocks = utils.build_slack_blocks(feedback_elements=feedback_elements)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "actions"
        assert blocks[0]["block_id"] == utils.SLACK_FEEDBACK_BLOCK_ID

    def test_build_with_cancel_button(self):
        """Test building blocks with cancel button."""
        cancel_elements = [
            {"type": "button", "text": {"type": "plain_text", "text": "Cancel"}}
        ]
        blocks = utils.build_slack_blocks(cancel_button_action_elements=cancel_elements)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "actions"
        assert blocks[0]["block_id"] == utils.SLACK_CANCEL_ACTION_BLOCK_ID


class TestSendSlackMessage:
    """Test suite for send_slack_message - tests timestamp extraction behavior."""

    @pytest.mark.asyncio
    async def test_extracts_timestamp_from_response(self):
        """Test that timestamp is correctly extracted from Slack API response."""
        mock_adapter = MagicMock()
        mock_adapter.slack_app.client.chat_postMessage = AsyncMock(
            return_value={"ts": "1234567890.123456", "ok": True}
        )

        ts = await utils.send_slack_message(
            mock_adapter, "C12345", "1234567890.000000", "Hello", None
        )

        # Behavior: function returns the timestamp from the response
        assert ts == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_returns_none_on_api_failure(self):
        """Test that API failures return None instead of raising."""
        mock_adapter = MagicMock()
        mock_adapter.slack_app.client.chat_postMessage = AsyncMock(
            side_effect=Exception("API Error")
        )

        ts = await utils.send_slack_message(
            mock_adapter, "C12345", None, "Hello", None
        )

        # Behavior: errors are handled gracefully
        assert ts is None


class TestUpdateSlackMessage:
    """Test suite for update_slack_message - tests error handling."""

    @pytest.mark.asyncio
    async def test_errors_are_suppressed(self):
        """Test that update errors don't raise exceptions."""
        mock_adapter = MagicMock()
        mock_adapter.slack_app.client.chat_update = AsyncMock(
            side_effect=Exception("API Error")
        )

        # Behavior: should not raise exception even on error
        await utils.update_slack_message(
            mock_adapter, "C12345", "1234567890.123456", "Updated", None
        )


class TestUploadSlackFile:
    """Test suite for upload_slack_file - tests 3-step upload flow."""

    @pytest.mark.asyncio
    async def test_completes_three_step_upload_flow(self):
        """Test that file upload follows Slack's 3-step process correctly."""
        mock_adapter = MagicMock()

        # Step 1: Get upload URL
        mock_adapter.slack_app.client.files_getUploadURLExternal = AsyncMock(
            return_value={
                "upload_url": "https://upload.slack.com/test",
                "file_id": "F12345",
            }
        )

        # Step 3: Complete upload
        mock_adapter.slack_app.client.files_completeUploadExternal = AsyncMock()

        # Step 2: Mock the HTTP POST
        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        with patch("asyncio.to_thread", return_value=mock_response):
            await utils.upload_slack_file(
                mock_adapter,
                "C12345",
                "1234567890.123456",
                "test.txt",
                b"file content",
                "Here's the file",
            )

        # Behavior: verify all 3 steps were executed
        mock_adapter.slack_app.client.files_getUploadURLExternal.assert_called_once()
        mock_adapter.slack_app.client.files_completeUploadExternal.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_errors_dont_crash(self):
        """Test that upload failures are handled gracefully."""
        mock_adapter = MagicMock()
        mock_adapter.slack_app.client.files_getUploadURLExternal = AsyncMock(
            side_effect=Exception("Upload failed")
        )

        with patch.object(utils, "send_slack_message", new_callable=AsyncMock):
            # Behavior: should not raise exception
            await utils.upload_slack_file(
                mock_adapter,
                "C12345",
                None,
                "test.txt",
                b"file content",
            )


class TestCreateFeedbackBlocks:
    """Test suite for create_feedback_blocks function."""

    def test_create_feedback_blocks(self):
        """Test creating feedback blocks."""
        blocks = utils.create_feedback_blocks("task-123", "user-123", "session-123")

        assert len(blocks) == 2
        assert blocks[0]["type"] == "button"
        assert blocks[0]["action_id"] == utils.THUMBS_UP_ACTION_ID
        assert blocks[1]["action_id"] == utils.THUMBS_DOWN_ACTION_ID

        # Verify payload can be parsed
        payload = json.loads(blocks[0]["value"])
        assert payload["task_id"] == "task-123"
        assert payload["user_id"] == "user-123"
        assert payload["session_id"] == "session-123"

    def test_create_feedback_blocks_too_large(self):
        """Test handling when payload is too large."""
        # Create a task_id that will exceed 2000 chars when serialized
        large_task_id = "x" * 2000
        blocks = utils.create_feedback_blocks(large_task_id, "user", "session")

        assert blocks == []


class TestCreateFeedbackInputBlocks:
    """Test suite for create_feedback_input_blocks function."""

    def test_create_feedback_input_blocks(self):
        """Test creating feedback input blocks."""
        original_payload = {
            "task_id": "task-123",
            "user_id": "user-123",
            "session_id": "session-123",
        }

        blocks = utils.create_feedback_input_blocks("up", original_payload)

        # Should have section, input, and actions blocks
        assert len(blocks) == 3
        assert blocks[0]["type"] == "section"
        assert blocks[1]["type"] == "input"
        assert blocks[2]["type"] == "actions"

        # Verify submit button has rating in payload
        submit_button = blocks[2]["elements"][0]
        payload = json.loads(submit_button["value"])
        assert payload["rating"] == "up"
        assert payload["task_id"] == "task-123"

    def test_create_feedback_input_blocks_too_large(self):
        """Test handling when payload is too large."""
        large_payload = {"task_id": "x" * 2000}
        blocks = utils.create_feedback_input_blocks("up", large_payload)

        # Should return error block
        assert len(blocks) == 1
        assert blocks[0]["type"] == "context"
        assert "too large" in blocks[0]["elements"][0]["text"].lower()


class TestTransformCitationsForSlack:
    """Test suite for transform_citations_for_slack function."""

    def test_web_search_citation_with_url(self):
        """Test transforming web search citation [[cite:s0r0]] with URL mapping."""
        text = "Python is popular.[[cite:s0r0]] It was created by Guido."
        citation_map = {
            "s0r0": {
                "sourceUrl": "https://www.python.org/about/",
                "title": "About Python",
            }
        }
        result = utils.transform_citations_for_slack(text, citation_map)
        assert "[[cite:" not in result
        assert "<https://www.python.org/about/|About Python>" in result

    def test_deep_research_citation_with_url(self):
        """Test transforming deep research citation [[cite:research0]] with URL."""
        text = "AI is transforming industries.[[cite:research0]]"
        citation_map = {
            "research0": {
                "sourceUrl": "https://arxiv.org/abs/2301.00001",
                "title": "AI Impact Study",
            }
        }
        result = utils.transform_citations_for_slack(text, citation_map)
        assert "[[cite:" not in result
        assert "<https://arxiv.org/abs/2301.00001|AI Impact Study>" in result

    def test_document_search_citation_with_url(self):
        """Test transforming document search citation [[cite:idx0r0]] with URL."""
        text = "The report states.[[cite:idx0r0]]"
        citation_map = {
            "idx0r0": {
                "sourceUrl": "https://docs.example.com/report.pdf",
                "title": "Annual Report 2024",
            }
        }
        result = utils.transform_citations_for_slack(text, citation_map)
        assert "[[cite:" not in result
        assert "<https://docs.example.com/report.pdf|Annual Report 2024>" in result

    def test_citation_without_mapping_is_stripped(self):
        """Test that citations without URL mapping are stripped cleanly."""
        text = "Python is popular.[[cite:s0r0]] It was created by Guido."
        result = utils.transform_citations_for_slack(text, {})
        assert "[[cite:" not in result
        assert "Python is popular. It was created by Guido." == result

    def test_citation_with_no_map_at_all(self):
        """Test that citations are stripped when no citation_map is provided."""
        text = "Some fact.[[cite:research0]] Another fact."
        result = utils.transform_citations_for_slack(text, None)
        assert "[[cite:" not in result
        assert "Some fact. Another fact." == result

    def test_multi_citation_with_urls(self):
        """Test transforming comma-separated multi-citations."""
        text = "Multiple sources agree.[[cite:s0r0, s0r1]]"
        citation_map = {
            "s0r0": {
                "sourceUrl": "https://example.com/a",
                "title": "Source A",
            },
            "s0r1": {
                "sourceUrl": "https://example.com/b",
                "title": "Source B",
            },
        }
        result = utils.transform_citations_for_slack(text, citation_map)
        assert "[[cite:" not in result
        assert "<https://example.com/a|Source A>" in result
        assert "<https://example.com/b|Source B>" in result

    def test_single_bracket_citation(self):
        """Test that single-bracket variant [cite:s0r0] is also handled."""
        text = "A fact.[cite:s0r0]"
        citation_map = {
            "s0r0": {
                "sourceUrl": "https://example.com",
                "title": "Example",
            }
        }
        result = utils.transform_citations_for_slack(text, citation_map)
        assert "[cite:" not in result
        assert "<https://example.com|Example>" in result

    def test_citation_url_without_title_shows_domain(self):
        """Test that URL without title falls back to domain display."""
        text = "A fact.[[cite:s0r0]]"
        citation_map = {
            "s0r0": {
                "sourceUrl": "https://www.example.com/some/long/path",
            }
        }
        result = utils.transform_citations_for_slack(text, citation_map)
        assert "<https://www.example.com/some/long/path|example.com>" in result

    def test_citation_with_metadata_link(self):
        """Test that metadata.link is used as fallback URL."""
        text = "A fact.[[cite:s0r0]]"
        citation_map = {
            "s0r0": {
                "metadata": {"link": "https://fallback.example.com"},
                "title": "Fallback Source",
            }
        }
        result = utils.transform_citations_for_slack(text, citation_map)
        assert "<https://fallback.example.com|Fallback Source>" in result

    def test_multiple_separate_citations(self):
        """Test multiple separate citations in the same text."""
        text = "Fact one.[[cite:s0r0]] Fact two.[[cite:s0r1]]"
        citation_map = {
            "s0r0": {"sourceUrl": "https://a.com", "title": "A"},
            "s0r1": {"sourceUrl": "https://b.com", "title": "B"},
        }
        result = utils.transform_citations_for_slack(text, citation_map)
        assert "[[cite:" not in result
        assert "<https://a.com|A>" in result
        assert "<https://b.com|B>" in result

    def test_non_string_input(self):
        """Test handling non-string input."""
        result = utils.transform_citations_for_slack(None)
        assert result is None

    def test_text_without_citations(self):
        """Test that text without citations is returned unchanged."""
        text = "Just regular text with no citations."
        result = utils.transform_citations_for_slack(text)
        assert result == text

    def test_correct_slack_markdown_integrates_citations(self):
        """Test that correct_slack_markdown also transforms citations."""
        text = "**Bold fact**.[[cite:s0r0]] More text."
        citation_map = {
            "s0r0": {
                "sourceUrl": "https://example.com",
                "title": "Example",
            }
        }
        result = utils.correct_slack_markdown(text, citation_map)
        # Citations should be transformed
        assert "[[cite:" not in result
        assert "<https://example.com|Example>" in result
        # Bold should also be converted
        assert "*Bold fact*" in result

    def test_mixed_search_turns(self):
        """Test citations from different search turns (s0r0, s1r0)."""
        text = "First search.[[cite:s0r0]] Second search.[[cite:s1r0]]"
        citation_map = {
            "s0r0": {"sourceUrl": "https://first.com", "title": "First"},
            "s1r0": {"sourceUrl": "https://second.com", "title": "Second"},
        }
        result = utils.transform_citations_for_slack(text, citation_map)
        assert "<https://first.com|First>" in result
        assert "<https://second.com|Second>" in result


class TestGetDomainFromUrl:
    """Test suite for _get_domain_from_url helper function."""

    def test_simple_url(self):
        """Test extracting domain from a simple URL."""
        assert utils._get_domain_from_url("https://example.com/path") == "example.com"

    def test_www_prefix_removed(self):
        """Test that www. prefix is stripped."""
        assert utils._get_domain_from_url("https://www.example.com") == "example.com"

    def test_subdomain_preserved(self):
        """Test that non-www subdomains are preserved."""
        assert utils._get_domain_from_url("https://api.example.com") == "api.example.com"

    def test_complex_url(self):
        """Test domain extraction from complex URL with path and query."""
        result = utils._get_domain_from_url("https://finance.yahoo.com/quote/NVDA/?p=NVDA")
        assert result == "finance.yahoo.com"

    def test_invalid_url_returns_input(self):
        """Test that invalid URLs return the input string."""
        result = utils._get_domain_from_url("not-a-url")
        assert result == "not-a-url"


class TestTransformCitationsForMarkdown:
    """Test suite for transform_citations_for_markdown function."""

    def test_produces_standard_markdown_links(self):
        """Test that output uses [text](url) format, not Slack <url|text>."""
        text = "A fact.[[cite:research0]]"
        citation_map = {
            "research0": {
                "sourceUrl": "https://example.com/article",
                "title": "Example Article",
            }
        }
        result = utils.transform_citations_for_markdown(text, citation_map)
        assert "[Example Article](https://example.com/article)" in result
        # Must NOT contain Slack mrkdwn format
        assert "<https://" not in result
        assert "[[cite:" not in result

    def test_domain_fallback_in_markdown(self):
        """Test domain fallback when no title is provided."""
        text = "A fact.[[cite:s0r0]]"
        citation_map = {
            "s0r0": {"sourceUrl": "https://www.example.com/long/path"},
        }
        result = utils.transform_citations_for_markdown(text, citation_map)
        assert "[example.com](https://www.example.com/long/path)" in result

    def test_multi_citations_in_markdown(self):
        """Test multiple citations produce markdown links."""
        text = "Sources agree.[[cite:research0, research1]]"
        citation_map = {
            "research0": {"sourceUrl": "https://a.com", "title": "Source A"},
            "research1": {"sourceUrl": "https://b.com", "title": "Source B"},
        }
        result = utils.transform_citations_for_markdown(text, citation_map)
        assert "[Source A](https://a.com)" in result
        assert "[Source B](https://b.com)" in result

    def test_no_map_strips_citations(self):
        """Test that citations are stripped when no map is provided."""
        text = "A fact.[[cite:research0]] More text."
        result = utils.transform_citations_for_markdown(text, None)
        assert "[[cite:" not in result
        assert "A fact. More text." == result

    def test_non_string_input(self):
        """Test handling non-string input."""
        result = utils.transform_citations_for_markdown(None)
        assert result is None

    def test_title_only_no_url(self):
        """Test citation with title but no URL uses italic markdown."""
        text = "A fact.[[cite:research0]]"
        citation_map = {
            "research0": {"title": "Internal Report"},
        }
        result = utils.transform_citations_for_markdown(text, citation_map)
        assert "*Internal Report*" in result
        assert "[[cite:" not in result

    def test_deep_research_report_style(self):
        """Test realistic deep research report with multiple research citations."""
        text = (
            "## Executive Summary\n\n"
            "AI is transforming industries.[[cite:research0]] "
            "The market is growing rapidly.[[cite:research1]][[cite:research2]]\n\n"
            "## Analysis\n\n"
            "Key findings include.[[cite:research0, research3]]"
        )
        citation_map = {
            "research0": {"sourceUrl": "https://arxiv.org/paper1", "title": "AI Impact Study"},
            "research1": {"sourceUrl": "https://mckinsey.com/report", "title": "McKinsey AI Report"},
            "research2": {"sourceUrl": "https://gartner.com/hype", "title": "Gartner Hype Cycle"},
            "research3": {"sourceUrl": "https://nature.com/article", "title": "Nature AI Review"},
        }
        result = utils.transform_citations_for_markdown(text, citation_map)
        assert "[[cite:" not in result
        assert "[AI Impact Study](https://arxiv.org/paper1)" in result
        assert "[McKinsey AI Report](https://mckinsey.com/report)" in result
        assert "[Gartner Hype Cycle](https://gartner.com/hype)" in result
        assert "[Nature AI Review](https://nature.com/article)" in result
        # Verify markdown structure is preserved
        assert "## Executive Summary" in result
        assert "## Analysis" in result


class TestCaptureRagSourcesLogic:
    """Test suite for the citation map building logic used by _capture_rag_sources.

    Tests the pure logic without importing the adapter (which requires solace_agent_mesh).
    """

    def _build_citation_map(self, existing_map, sources):
        """Replicate the _capture_rag_sources logic for testing."""
        citation_map = existing_map or {}
        for source in sources:
            citation_id = source.get("citationId")
            if not citation_id:
                continue
            citation_map[citation_id] = {
                "sourceUrl": source.get("sourceUrl"),
                "url": source.get("url"),
                "title": source.get("title"),
                "filename": source.get("filename"),
                "metadata": source.get("metadata", {}),
            }
        return citation_map

    def test_builds_citation_map_from_sources(self):
        """Test building a citation map from RAG sources."""
        sources = [
            {
                "citationId": "s0r0",
                "sourceUrl": "https://example.com",
                "title": "Example",
                "filename": "example.com",
                "metadata": {"link": "https://example.com", "type": "web_search"},
            },
            {
                "citationId": "s0r1",
                "sourceUrl": "https://other.com",
                "title": "Other",
                "filename": "other.com",
                "metadata": {},
            },
        ]
        result = self._build_citation_map(None, sources)
        assert "s0r0" in result
        assert "s0r1" in result
        assert result["s0r0"]["sourceUrl"] == "https://example.com"
        assert result["s0r1"]["title"] == "Other"

    def test_merges_with_existing_map(self):
        """Test merging new sources with an existing citation map."""
        existing = {
            "s0r0": {"sourceUrl": "https://existing.com", "title": "Existing"},
        }
        new_sources = [
            {"citationId": "s1r0", "sourceUrl": "https://new.com", "title": "New", "metadata": {}},
        ]
        result = self._build_citation_map(existing, new_sources)
        assert "s0r0" in result
        assert "s1r0" in result
        assert result["s0r0"]["sourceUrl"] == "https://existing.com"
        assert result["s1r0"]["sourceUrl"] == "https://new.com"

    def test_skips_sources_without_citation_id(self):
        """Test that sources missing citationId are skipped."""
        sources = [
            {"sourceUrl": "https://no-id.com", "title": "No ID"},
            {"citationId": "s0r0", "sourceUrl": "https://has-id.com", "title": "Has ID", "metadata": {}},
        ]
        result = self._build_citation_map(None, sources)
        assert len(result) == 1
        assert "s0r0" in result

    def test_empty_sources_returns_empty_map(self):
        """Test that empty sources list returns empty map."""
        result = self._build_citation_map(None, [])
        assert result == {}

    def test_preserves_metadata(self):
        """Test that metadata dict is preserved in citation map."""
        sources = [
            {
                "citationId": "research0",
                "sourceUrl": "https://arxiv.org/paper",
                "title": "AI Paper",
                "metadata": {"link": "https://arxiv.org/paper", "type": "deep_research", "favicon": "https://google.com/s2/favicons?domain=arxiv.org"},
            },
        ]
        result = self._build_citation_map(None, sources)
        assert result["research0"]["metadata"]["type"] == "deep_research"
        assert result["research0"]["metadata"]["favicon"].startswith("https://google.com")

    def test_tool_result_rag_metadata_structure(self):
        """Test extracting sources from the actual tool_result.result_data.rag_metadata structure."""
        # Simulate the actual data structure from web search tool results
        tool_result_data = {
            "type": "tool_result",
            "tool_name": "web_search_google",
            "result_data": {
                "rag_metadata": {
                    "query": "NVDA stock price",
                    "searchType": "web_search",
                    "sources": [
                        {
                            "citationId": "s0r0",
                            "sourceUrl": "https://finance.yahoo.com/quote/NVDA/",
                            "title": "NVIDIA Corporation (NVDA) Stock Price",
                            "filename": "finance.yahoo.com",
                            "metadata": {"link": "https://finance.yahoo.com/quote/NVDA/", "type": "web_search"},
                        },
                        {
                            "citationId": "s0r1",
                            "sourceUrl": "https://www.google.com/finance/quote/NVDA:NASDAQ",
                            "title": "NVDA Stock Price - Google Finance",
                            "filename": "google.com",
                            "metadata": {"link": "https://www.google.com/finance/quote/NVDA:NASDAQ", "type": "web_search"},
                        },
                    ],
                },
            },
        }

        # Extract sources the same way the adapter does
        result_data = tool_result_data.get("result_data", {})
        rag_metadata = result_data.get("rag_metadata", {})
        sources = rag_metadata.get("sources", [])

        result = self._build_citation_map(None, sources)
        assert len(result) == 2
        assert result["s0r0"]["sourceUrl"] == "https://finance.yahoo.com/quote/NVDA/"
        assert result["s0r1"]["title"] == "NVDA Stock Price - Google Finance"

    def test_citation_map_used_by_transform(self):
        """End-to-end: build citation map from sources, then transform text."""
        sources = [
            {
                "citationId": "s0r0",
                "sourceUrl": "https://finance.yahoo.com/quote/NVDA/",
                "title": "NVIDIA Stock",
                "metadata": {},
            },
        ]
        citation_map = self._build_citation_map(None, sources)

        text = "NVDA is at $180.[[cite:s0r0]]"
        result = utils.transform_citations_for_slack(text, citation_map)
        assert "[[cite:" not in result
        assert "<https://finance.yahoo.com/quote/NVDA/|NVIDIA Stock>" in result
