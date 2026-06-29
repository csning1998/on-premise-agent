"""Tests for Gemma 4 Multi-Agent Deep Think."""

from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import httpx
import pytest
import requests

# Add workflows to path if needed, but since it's running inside repository
# root, it will be imported via pipelines.workflows
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
from pipelines.workflows.deep_think_agent.client import parse_json_chunk


def test_parse_json_chunk():
    """Tests parse_json_chunk with valid and invalid data."""
    # Valid JSON
    assert parse_json_chunk(b'{"response": "hello"}') == {"response": "hello"}
    # Invalid JSON
    assert parse_json_chunk(b"invalid-json") is None
    # Empty byte line
    assert parse_json_chunk(b"") is None


def test_clean_keywords():
    """Tests clean_keywords with various noisy formats."""
    # With thinking blocks and markdown blocks
    text = (
        "<think>need keywords for coding</think>\n"
        "```json\n['python', 'modular']\n```\n"
        "python modular programming"
    )
    assert clean_keywords(text) == "python modular programming"

    # With noise symbols
    assert (
        clean_keywords("hello 'world' [test] (run)") == "hello world test run"
    )

    # Truncates to 5 words
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


@pytest.mark.asyncio
async def test_ollama_client_async_generate_success():
    """Tests OllamaClient.async_generate success state."""
    client = OllamaClient("http://fake-ollama")

    mock_request = httpx.Request("POST", "http://fake-ollama")
    mock_resp = httpx.Response(
        200, json={"response": "agent output response  "}, request=mock_request
    )
    with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
        result = await client.async_generate("test-model", "test-prompt")
        assert result == "agent output response"
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_ollama_client_async_generate_failure():
    """Tests OllamaClient.async_generate failure state."""
    client = OllamaClient("http://fake-ollama")

    with patch(
        "httpx.AsyncClient.post", side_effect=httpx.HTTPError("Network error")
    ) as mock_post:
        result = await client.async_generate("test-model", "test-prompt")
        assert result == "ERROR: Agent timeout."
        mock_post.assert_called_once()


def test_ollama_client_stream_generate():
    """Tests OllamaClient.stream_generate iterator functionality."""
    client = OllamaClient("http://fake-ollama")

    # Mock requests.post context manager and response
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.iter_lines.return_value = [
        b'{"response": "hello ", "done": false}',
        b'{"response": "world", "done": false}',
        b'{"response": "!", "done": true}',
    ]

    with patch("requests.post", return_value=mock_response) as mock_post:
        gen = client.stream_generate("test-model", "test-prompt")
        results = list(gen)
        assert results == ["hello ", "world"]
        mock_post.assert_called_once()


def test_ollama_client_stream_generate_failure():
    """Tests OllamaClient.stream_generate failure state handling."""
    client = OllamaClient("http://fake-ollama")

    with patch(
        "requests.post",
        side_effect=requests.exceptions.RequestException("Request failed"),
    ) as mock_post:
        gen = client.stream_generate("test-model", "test-prompt")
        results = list(gen)
        assert len(results) == 1
        assert "Error: Request failed" in results[0]
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_searxng_client_search():
    """Tests SearxngClient.search API calls."""
    client = SearxngClient("http://fake-searxng")

    mock_results = [{"url": "http://example.com", "content": "example content"}]
    mock_request = httpx.Request("GET", "http://fake-searxng")
    mock_resp = httpx.Response(
        200, json={"results": mock_results}, request=mock_request
    )
    with patch("httpx.AsyncClient.get", return_value=mock_resp) as mock_get:
        results = await client.search("python testing")
        assert results == mock_results
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_run_coordinator():
    """Tests run_coordinator using Dependency Injection (mock OllamaClient)."""
    mock_client = MagicMock(spec=OllamaClient)
    # Define async mock for async_generate
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

    # First call yields keywords, second yields aligned facts
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
async def test_run_researcher_empty_results():
    """Tests run_researcher returns NO_FACTS_FOUND when search is empty."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_searxng = MagicMock(spec=SearxngClient)
    mock_ollama.async_generate = AsyncMock(return_value="keywords")
    mock_searxng.search = AsyncMock(return_value=[])

    res = await run_researcher(
        mock_ollama, mock_searxng, "e4b-model", "user-query", "2026-06-29"
    )
    assert res == NO_FACTS_FOUND
    assert mock_ollama.async_generate.call_count == 1


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


def test_build_finalizer_no_facts():
    """Finalizer uses training-knowledge framing for NO_FACTS_FOUND."""
    outputs = AgentOutputs(
        coordinator="c", researcher=NO_FACTS_FOUND, logic="l", contrarian="co"
    )
    prompt = _build_finalizer_prompt("2026-06-29", "query", outputs)
    assert "training knowledge" in prompt
    assert "ALIGNED CONTEXT below contains facts" not in prompt


def test_pipe_uses_utc_for_date():
    """Regression guard: pipe() must compute today in UTC."""
    dta_path = (
        Path(__file__).resolve().parent.parent
        / "pipelines/workflows/deep_think_agent.py"
    )
    source = dta_path.read_text()
    assert "datetime.timezone.utc" in source, (
        "pipe() must use datetime.datetime.now(datetime.timezone.utc), "
        "not datetime.date.today()"
    )


def test_agent_outputs_immutability():
    """Verifies that AgentOutputs NamedTuple is immutable."""
    outputs = AgentOutputs(
        coordinator="c", researcher="r", logic="l", contrarian="co"
    )
    assert outputs.coordinator == "c"
    with pytest.raises(AttributeError):
        # NamedTuple fields are read-only
        outputs.coordinator = "new_val"  # type: ignore
