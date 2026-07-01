"""Tests for deep_think_agent/agents.py: builders, runners, and data types."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from pipelines.workflows.deep_think_agent.agents import NO_FACTS_FOUND
from pipelines.workflows.deep_think_agent.agents import PROSE_ONLY_INSTRUCTION
from pipelines.workflows.deep_think_agent.agents import AgentOutputs
from pipelines.workflows.deep_think_agent.agents import ResearchSummaries
from pipelines.workflows.deep_think_agent.agents import _build_aggregate_prompt
from pipelines.workflows.deep_think_agent.agents import _build_align_prompt
from pipelines.workflows.deep_think_agent.agents import _build_contrarian_prompt
from pipelines.workflows.deep_think_agent.agents import (
    _build_coordinator_prompt,
)
from pipelines.workflows.deep_think_agent.agents import _build_finalizer_prompt
from pipelines.workflows.deep_think_agent.agents import _build_keywords_prompt
from pipelines.workflows.deep_think_agent.agents import _build_logic_prompt
from pipelines.workflows.deep_think_agent.agents import _strip_markdown
from pipelines.workflows.deep_think_agent.agents import clean_keywords
from pipelines.workflows.deep_think_agent.agents import parse_search_queries
from pipelines.workflows.deep_think_agent.agents import run_contrarian
from pipelines.workflows.deep_think_agent.agents import run_coordinator
from pipelines.workflows.deep_think_agent.agents import run_logic
from pipelines.workflows.deep_think_agent.agents import run_researcher
from pipelines.workflows.deep_think_agent.client import BraveClient
from pipelines.workflows.deep_think_agent.client import OllamaClient
from pipelines.workflows.deep_think_agent.client import SearxngClient


def test_clean_keywords():
    """Tests clean_keywords with various noisy formats."""
    text = (
        "<think>need keywords for coding</think>\n"
        "```json\n['python', 'modular']\n```\n"
        "python modular programming"
    )
    assert clean_keywords(text) == "python modular programming"

    assert (
        clean_keywords("hello 'world' [test] (run)") == "hello world test run"
    )

    assert (
        clean_keywords("one two three four five six seven eight nine")
        == "one two three four five six seven eight"
    )


def test_parse_search_queries():
    """Tests parse_search_queries with multi-line and edge cases."""
    result = parse_search_queries(
        "<think>planning</think>\nalpha bravo charlie 2026\ndelta echo foxtrot"
    )
    assert result == ["alpha bravo charlie 2026", "delta echo foxtrot"]

    assert parse_search_queries("NO_SEARCH") == []
    assert parse_search_queries("") == []

    long_input = "\n".join(f"query topic {i}" for i in range(8))
    assert len(parse_search_queries(long_input)) == 5


def test_build_coordinator_prompt():
    """Tests _build_coordinator_prompt."""
    prompt = _build_coordinator_prompt("my query")
    assert "my query" in prompt
    assert "Respond in English only" in prompt
    assert "DO NOT use any emojis" in prompt
    assert "Do NOT describe methodology" in prompt
    assert "Do NOT explain limitations" in prompt


def test_build_keywords_prompt():
    """Tests _build_keywords_prompt."""
    prompt = _build_keywords_prompt("my query")
    assert prompt.endswith("my query")
    assert "NO_SEARCH" in prompt


def test_build_align_prompt():
    """Tests _build_align_prompt."""
    prompt = _build_align_prompt("2026-06-29", "my query", "fact A\nfact B")
    assert "2026-06-29" in prompt
    assert "my query" in prompt
    assert "fact A\nfact B" in prompt
    assert "cite its URL" in prompt
    assert "training cutoff" in prompt


def test_build_aggregate_prompt():
    """Tests _build_aggregate_prompt."""
    prompt = _build_aggregate_prompt(
        "2026-06-30", "my query", ["summary one", "summary two"]
    )
    assert "2026-06-30" in prompt
    assert "my query" in prompt
    assert "summary one" in prompt
    assert "summary two" in prompt


def test_build_logic_prompt_with_facts():
    """Tests _build_logic_prompt with facts."""
    prompt = _build_logic_prompt("query", "some facts")
    assert "FACTS from web search" in prompt
    assert "weakly supported" in prompt
    assert "Do NOT summarize" in prompt
    assert "query" in prompt
    assert "Step 1:" not in prompt


def test_build_logic_prompt_no_facts():
    """Tests _build_logic_prompt with NO_FACTS_FOUND."""
    prompt = _build_logic_prompt("query", NO_FACTS_FOUND)
    assert "No web search results are available" in prompt
    assert "FACTS from web search" not in prompt


def test_build_contrarian_prompt_with_facts():
    """Tests _build_contrarian_prompt with facts."""
    prompt = _build_contrarian_prompt("query", "some facts")
    assert "Researcher conclusion" in prompt
    assert "Argue AGAINST" in prompt
    assert "some facts" in prompt
    assert "DO NOT use any emojis" in prompt
    assert "FACTS: some facts" not in prompt


def test_build_contrarian_prompt_no_facts():
    """Tests _build_contrarian_prompt with NO_FACTS_FOUND."""
    prompt = _build_contrarian_prompt("query", NO_FACTS_FOUND)
    assert "No web search results are available" in prompt
    assert "FACTS:" not in prompt


def test_build_finalizer_no_facts():
    """Finalizer uses training-knowledge framing for NO_FACTS_FOUND."""
    outputs = AgentOutputs(
        coordinator="c",
        researcher=NO_FACTS_FOUND,
        logic="l",
        contrarian="co",
        source_urls=[],
    )
    prompt = _build_finalizer_prompt("2026-06-29", "query", outputs)
    assert "training knowledge" in prompt
    assert "ALIGNED CONTEXT below contains facts" not in prompt


def test_build_finalizer_with_facts():
    """Finalizer uses web-facts framing when researcher output is a string."""
    outputs = AgentOutputs(
        coordinator="c",
        researcher="aligned fact data",
        logic="l",
        contrarian="co",
        source_urls=[],
    )
    prompt = _build_finalizer_prompt("2026-06-29", "query", outputs)
    assert "ALIGNED CONTEXT below contains facts" in prompt
    assert "verified ground truth" in prompt
    assert "training knowledge" not in prompt
    # No source_urls means no VERIFIED_SOURCES block, so no citation
    # instruction should be injected either.
    assert "VERIFIED_SOURCES" not in prompt
    assert "Format every citation as a markdown link" not in prompt


def test_build_finalizer_with_source_urls():
    """Finalizer injects VERIFIED_SOURCES when source_urls is non-empty."""
    outputs = AgentOutputs(
        coordinator="c",
        researcher="some facts",
        logic="l",
        contrarian="co",
        source_urls=["https://example.com/a", "https://example.com/b"],
    )
    prompt = _build_finalizer_prompt("2026-06-29", "query", outputs)
    assert "VERIFIED_SOURCES" in prompt
    assert "https://example.com/a" in prompt
    assert "https://example.com/b" in prompt
    assert "Format every citation as a markdown link" in prompt
    # The citation format instruction must appear after the URL list, not
    # before, so the model sees the real URLs before being told how to
    # format a citation around them.
    assert prompt.index("https://example.com/b") < prompt.index(
        "Format every citation as a markdown link"
    )


def test_agent_outputs_immutability():
    """Verifies that AgentOutputs NamedTuple is immutable."""
    outputs = AgentOutputs(
        coordinator="c",
        researcher="r",
        logic="l",
        contrarian="co",
        source_urls=[],
    )
    assert outputs.coordinator == "c"
    with pytest.raises(AttributeError):
        outputs.coordinator = "new_val"  # type: ignore


@pytest.mark.asyncio
async def test_run_coordinator():
    """Tests run_coordinator using Dependency Injection (mock OllamaClient)."""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.async_generate = AsyncMock(return_value="coord-output")

    res = await run_coordinator(mock_client, "e4b-model", "hello")
    assert res == "coord-output"
    mock_client.async_generate.assert_called_once_with(
        "e4b-model",
        "You are a research coordinator. Read the user query and identify "
        "what it is asking for. List the main topics, regions, organizations, "
        "and time periods that are relevant. "
        "Do NOT describe methodology or data systems. "
        "Do NOT explain limitations or what data you would need. "
        "Respond in English only. DO NOT use any emojis. "
        + PROSE_ONLY_INSTRUCTION
        + "Query: hello",
    )


@pytest.mark.asyncio
async def test_gather_researcher_summaries_returns_source_urls():
    """gather_researcher_summaries returns ResearchSummaries with source URL."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_searxng = MagicMock(spec=SearxngClient)

    mock_ollama.async_generate = AsyncMock(
        side_effect=["query alpha beta", "batch summary"]
    )
    mock_searxng.search = AsyncMock(
        return_value=[{"url": "http://source.com", "content": "content"}]
    )

    from pipelines.workflows.deep_think_agent.agents import (
        gather_researcher_summaries,
    )

    result = await gather_researcher_summaries(
        mock_ollama,
        mock_searxng,
        None,
        "e2b-model",
        "e4b-model",
        "user-query",
        "2026-06-30",
    )
    assert isinstance(result, ResearchSummaries)
    assert result.summaries == ["batch summary"]
    assert result.source_urls == ["http://source.com"]
    keywords_model = mock_ollama.async_generate.call_args_list[0][0][0]
    align_model = mock_ollama.async_generate.call_args_list[1][0][0]
    assert keywords_model == "e2b-model"
    assert align_model == "e4b-model"


@pytest.mark.asyncio
async def test_run_researcher_success():
    """Tests run_researcher map-reduce: keywords, search, align, aggregate."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_searxng = MagicMock(spec=SearxngClient)

    mock_ollama.async_generate = AsyncMock(
        side_effect=[
            "query alpha beta gamma",
            "batch summary",
            "aggregated result",
        ]
    )
    mock_searxng.search = AsyncMock(
        return_value=[{"url": "http://test.com", "content": "text content"}]
    )

    res = await run_researcher(
        mock_ollama,
        mock_searxng,
        None,
        "e2b-model",
        "e4b-model",
        "12b-model",
        "user-query",
        "2026-06-29",
    )
    assert res == "aggregated result"
    assert mock_ollama.async_generate.call_count == 3
    mock_searxng.search.assert_called_once()
    keywords_model = mock_ollama.async_generate.call_args_list[0][0][0]
    align_model = mock_ollama.async_generate.call_args_list[1][0][0]
    assert keywords_model == "e2b-model"
    assert align_model == "e4b-model"
    align_prompt = mock_ollama.async_generate.call_args_list[1][0][1]
    assert "2026-06-29" in align_prompt
    assert "user-query" in align_prompt
    assert "cite its URL" in align_prompt


@pytest.mark.asyncio
async def test_run_researcher_with_brave_client():
    """Tests run_researcher fans out to both SearXNG and Brave when provided."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_searxng = MagicMock(spec=SearxngClient)
    mock_brave = MagicMock(spec=BraveClient)

    mock_ollama.async_generate = AsyncMock(
        side_effect=[
            "query alpha beta gamma",
            "merged summary",
            "aggregated result",
        ]
    )
    mock_searxng.search = AsyncMock(
        return_value=[
            {"url": "http://searxng.com", "content": "searxng content"}
        ]
    )
    mock_brave.search = AsyncMock(
        return_value=[{"url": "http://brave.com", "content": "brave content"}]
    )

    res = await run_researcher(
        mock_ollama,
        mock_searxng,
        mock_brave,
        "e2b-model",
        "e4b-model",
        "12b-model",
        "user-query",
        "2026-06-29",
    )
    assert res == "aggregated result"
    assert mock_ollama.async_generate.call_count == 3
    mock_searxng.search.assert_called_once()
    mock_brave.search.assert_called_once()
    align_prompt = mock_ollama.async_generate.call_args_list[1][0][1]
    assert "http://searxng.com" in align_prompt
    assert "http://brave.com" in align_prompt


@pytest.mark.asyncio
async def test_run_researcher_empty_results():
    """Tests run_researcher returns NO_FACTS_FOUND when search is empty."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_searxng = MagicMock(spec=SearxngClient)
    mock_ollama.async_generate = AsyncMock(return_value="keywords")
    mock_searxng.search = AsyncMock(return_value=[])

    res = await run_researcher(
        mock_ollama,
        mock_searxng,
        None,
        "e2b-model",
        "e4b-model",
        "12b-model",
        "user-query",
        "2026-06-29",
    )
    assert res is NO_FACTS_FOUND
    assert mock_ollama.async_generate.call_count == 1


@pytest.mark.asyncio
async def test_run_researcher_no_search_keyword():
    """Tests run_researcher returns early when model signals NO_SEARCH."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_searxng = MagicMock(spec=SearxngClient)
    mock_ollama.async_generate = AsyncMock(return_value="NO_SEARCH")
    mock_searxng.search = AsyncMock()

    res = await run_researcher(
        mock_ollama,
        mock_searxng,
        None,
        "e2b-model",
        "e4b-model",
        "12b-model",
        "user-query",
        "2026-06-29",
    )
    assert res == "No search results."
    mock_searxng.search.assert_not_called()
    assert mock_ollama.async_generate.call_count == 1


@pytest.mark.asyncio
async def test_run_researcher_searxng_exception():
    """Tests run_researcher returns NO_FACTS_FOUND when searxng raises."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_searxng = MagicMock(spec=SearxngClient)
    mock_ollama.async_generate = AsyncMock(return_value="keywords")
    mock_searxng.search = AsyncMock(side_effect=Exception("Network failure"))

    res = await run_researcher(
        mock_ollama,
        mock_searxng,
        None,
        "e2b-model",
        "e4b-model",
        "12b-model",
        "user-query",
        "2026-06-29",
    )
    assert res is NO_FACTS_FOUND


@pytest.mark.asyncio
async def test_run_logic():
    """Tests run_logic using Dependency Injection."""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.async_generate = AsyncMock(return_value="logic-output")

    res = await run_logic(mock_client, "e4b-model", "query", "facts")
    assert res == "logic-output"
    mock_client.async_generate.assert_called_once_with(
        "e4b-model",
        "You are a logic verifier. Query: query\n"
        "FACTS from web search: facts\n"
        "Do NOT summarize or repeat the FACTS. "
        "Identify ONLY: (1) claims that are weakly supported or lack evidence, "
        "(2) internal contradictions between sources, "
        "(3) assumptions presented as verified facts. "
        "If no weaknesses exist, state so explicitly. "
        "DO NOT use any emojis. " + PROSE_ONLY_INSTRUCTION,
    )


@pytest.mark.asyncio
async def test_run_logic_no_facts():
    """Tests run_logic adjusts prompt when facts sentinel is NO_FACTS_FOUND."""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.async_generate = AsyncMock(return_value="logic-no-facts-output")

    res = await run_logic(mock_client, "e4b-model", "query", NO_FACTS_FOUND)
    assert res == "logic-no-facts-output"
    mock_client.async_generate.assert_called_once_with(
        "e4b-model",
        "You are a logic verifier. Query: query\n"
        "No web search results are available. "
        "Reason from general knowledge only and note the absence "
        "of current data. "
        "DO NOT use any emojis. " + PROSE_ONLY_INSTRUCTION,
    )


@pytest.mark.asyncio
async def test_run_contrarian():
    """Tests run_contrarian using Dependency Injection."""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.async_generate = AsyncMock(return_value="contrarian-output")

    res = await run_contrarian(mock_client, "e4b-model", "query", "facts")
    assert res == "contrarian-output"
    mock_client.async_generate.assert_called_once_with(
        "e4b-model",
        "Query: query\n"
        "Researcher conclusion:\nfacts\n"
        "You are a contrarian. Argue AGAINST the researcher's conclusions. "
        "Do NOT repeat or agree with any of the researcher's claims. "
        "For each major conclusion, provide: the opposing view, "
        "missing evidence, or an alternative explanation. "
        "DO NOT use any emojis. " + PROSE_ONLY_INSTRUCTION,
    )


@pytest.mark.asyncio
async def test_run_contrarian_no_facts():
    """Tests run_contrarian handles NO_FACTS_FOUND sentinel."""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.async_generate = AsyncMock(
        return_value="contrarian-no-facts-output"
    )

    res = await run_contrarian(
        mock_client, "e4b-model", "query", NO_FACTS_FOUND
    )
    assert res == "contrarian-no-facts-output"
    mock_client.async_generate.assert_called_once_with(
        "e4b-model",
        "List counter-arguments for query: query\n"
        "No web search results are available. "
        "Reason from general knowledge only.\nDO NOT use any emojis. "
        + PROSE_ONLY_INSTRUCTION,
    )


def test_strip_markdown_headers():
    """Strips markdown headers of any level (1-6)."""
    assert _strip_markdown("# Title\nbody") == "Title\nbody"
    assert _strip_markdown("### Subheading\nbody") == "Subheading\nbody"


def test_strip_markdown_bold():
    """Unwraps bold text, keeping the inner content."""
    assert _strip_markdown("This is **bold** text") == "This is bold text"


def test_strip_markdown_code_fence():
    """Removes fenced code blocks entirely, including the language tag."""
    text = "before\n```python\nprint('x')\n```\nafter"
    assert _strip_markdown(text) == "before\n\nafter"


def test_strip_markdown_bullet_list():
    """Strips bullet list markers (-, *, +), leaving plain lines."""
    text = "- first point\n* second point\n+ third point"
    assert _strip_markdown(text) == "first point\nsecond point\nthird point"


def test_strip_markdown_numbered_list():
    """Strips numbered list markers, leaving plain lines."""
    text = "1. first point\n2. second point\n10. tenth point"
    assert _strip_markdown(text) == "first point\nsecond point\ntenth point"


def test_strip_markdown_emoji():
    """Removes emoji characters from the covered Unicode ranges."""
    assert _strip_markdown("Great news 🎉 today") == "Great news  today"


def test_strip_markdown_collapses_blank_lines():
    """Collapses 3+ consecutive newlines down to a single blank line."""
    assert _strip_markdown("a\n\n\n\nb") == "a\n\nb"


def test_strip_markdown_bold_spans_newline():
    """Unwraps bold text even when the span crosses a line break."""
    assert _strip_markdown("**term\ndefinition**") == "term\ndefinition"


def test_strip_markdown_code_fence_ignores_inline_backticks():
    """Strips a real fenced block without corrupting nearby prose.

    Prose containing inline triple backticks must survive intact.
    """
    text = (
        "Use the ```git``` command carefully.\n"
        "Some unrelated prose continues.\n"
        "```python\n"
        "real_code()\n"
        "```\n"
        "Final remark."
    )
    result = _strip_markdown(text)
    assert "```git```" in result
    assert "Some unrelated prose continues." in result
    assert "real_code()" not in result
    assert "Final remark." in result


def test_strip_markdown_numbered_prose_not_stripped():
    """A prose sentence starting with a digit is not a one-item list.

    A single isolated digit-dot line must not be mistaken for a list item.
    """
    text = "2. The study found significant results across all cohorts."
    assert _strip_markdown(text) == text
