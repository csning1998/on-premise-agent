"""Tests for deep_think_agent/agents.py: builders, runners, and data types."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from pipelines.workflows.deep_think_agent.agents import NO_FACTS_FOUND
from pipelines.workflows.deep_think_agent.agents import AgentOutputs
from pipelines.workflows.deep_think_agent.agents import _build_align_prompt
from pipelines.workflows.deep_think_agent.agents import _build_contrarian_prompt
from pipelines.workflows.deep_think_agent.agents import (
    _build_coordinator_prompt,
)
from pipelines.workflows.deep_think_agent.agents import _build_finalizer_prompt
from pipelines.workflows.deep_think_agent.agents import _build_keywords_prompt
from pipelines.workflows.deep_think_agent.agents import _build_logic_prompt
from pipelines.workflows.deep_think_agent.agents import clean_keywords
from pipelines.workflows.deep_think_agent.agents import run_contrarian
from pipelines.workflows.deep_think_agent.agents import run_coordinator
from pipelines.workflows.deep_think_agent.agents import run_logic
from pipelines.workflows.deep_think_agent.agents import run_researcher
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
        clean_keywords("one two three four five six seven")
        == "one two three four five"
    )


def test_build_coordinator_prompt():
    """Tests _build_coordinator_prompt."""
    prompt = _build_coordinator_prompt("my query")
    assert "my query" in prompt
    assert "Respond in English only" in prompt
    assert "DO NOT use any emojis" in prompt


def test_build_keywords_prompt():
    """Tests _build_keywords_prompt."""
    prompt = _build_keywords_prompt("my query")
    assert prompt.endswith("my query")
    assert "NO_SEARCH" in prompt


def test_build_align_prompt():
    """Tests _build_align_prompt."""
    prompt = _build_align_prompt("2026-06-29", "fact A\nfact B")
    assert "2026-06-29" in prompt
    assert "verified ground truth" in prompt
    assert "fact A\nfact B" in prompt


def test_build_logic_prompt_with_facts():
    """Tests _build_logic_prompt with facts."""
    prompt = _build_logic_prompt("query", "some facts")
    assert "FACTS from web search" in prompt
    assert "Step 1:" in prompt
    assert "query" in prompt


def test_build_logic_prompt_no_facts():
    """Tests _build_logic_prompt with NO_FACTS_FOUND."""
    prompt = _build_logic_prompt("query", NO_FACTS_FOUND)
    assert "No web search results are available" in prompt
    assert "FACTS from web search" not in prompt


def test_build_contrarian_prompt_with_facts():
    """Tests _build_contrarian_prompt with facts."""
    prompt = _build_contrarian_prompt("query", "some facts")
    assert "FACTS: some facts" in prompt
    assert "DO NOT use any emojis" in prompt


def test_build_contrarian_prompt_no_facts():
    """Tests _build_contrarian_prompt with NO_FACTS_FOUND."""
    prompt = _build_contrarian_prompt("query", NO_FACTS_FOUND)
    assert "No web search results are available" in prompt
    assert "FACTS:" not in prompt


def test_build_finalizer_no_facts():
    """Finalizer uses training-knowledge framing for NO_FACTS_FOUND."""
    outputs = AgentOutputs(
        coordinator="c", researcher=NO_FACTS_FOUND, logic="l", contrarian="co"
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
    )
    prompt = _build_finalizer_prompt("2026-06-29", "query", outputs)
    assert "ALIGNED CONTEXT below contains facts" in prompt
    assert "verified ground truth" in prompt
    assert "training knowledge" not in prompt


def test_agent_outputs_immutability():
    """Verifies that AgentOutputs NamedTuple is immutable."""
    outputs = AgentOutputs(
        coordinator="c", researcher="r", logic="l", contrarian="co"
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
        "Break down the query: hello\nRespond in English only. "
        "DO NOT use any emojis.",
    )


@pytest.mark.asyncio
async def test_run_researcher_success():
    """Tests run_researcher using Dependency Injection."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_searxng = MagicMock(spec=SearxngClient)

    mock_ollama.async_generate = AsyncMock()
    mock_ollama.async_generate.side_effect = ["keywords", "aligned facts"]

    mock_searxng.search = AsyncMock(
        return_value=[{"url": "http://test.com", "content": "text content"}]
    )

    res = await run_researcher(
        mock_ollama, mock_searxng, "e4b-model", "user-query", "2026-06-29"
    )
    assert res == "aligned facts"
    assert mock_ollama.async_generate.call_count == 2
    mock_searxng.search.assert_called_once_with("keywords")
    align_prompt = mock_ollama.async_generate.call_args_list[1][0][1]
    assert "2026-06-29" in align_prompt
    assert "verified ground truth" in align_prompt


@pytest.mark.asyncio
async def test_run_researcher_empty_results():
    """Tests run_researcher returns NO_FACTS_FOUND when search is empty."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_searxng = MagicMock(spec=SearxngClient)
    mock_ollama.async_generate = AsyncMock(return_value="keywords")
    mock_searxng.search = AsyncMock(return_value=[])

    res = await run_researcher(
        mock_ollama, mock_searxng, "e4b-model", "user-query", "2026-06-29"
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
        mock_ollama, mock_searxng, "e4b-model", "user-query", "2026-06-29"
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
        mock_ollama, mock_searxng, "e4b-model", "user-query", "2026-06-29"
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
        "FACTS from web search (treat as ground truth): facts\n"
        "Step 1: Identify any conflicts between sources. "
        "Step 2: For each conflict, reason which claim is more credible "
        "based on source specificity, recency, and reliability. "
        "Step 3: Output a reconciled summary of what is most likely true. "
        "Do NOT merely list conflicts without resolution. "
        "DO NOT use any emojis.",
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
        "DO NOT use any emojis.",
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
        "List counter-arguments for query: query\n"
        "FACTS: facts\nDO NOT use any emojis.",
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
        "Reason from general knowledge only.\nDO NOT use any emojis.",
    )
