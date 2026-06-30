"""Tests for deep_think_agent/client.py.

Includes tests for OllamaClient, SearxngClient, and parse_json_chunk.
"""

from unittest.mock import MagicMock
from unittest.mock import patch

import httpx
import pytest
import requests

from pipelines.workflows.deep_think_agent.client import OllamaClient
from pipelines.workflows.deep_think_agent.client import SearxngClient
from pipelines.workflows.deep_think_agent.client import parse_json_chunk


def test_parse_json_chunk():
    """Tests parse_json_chunk with valid and invalid data."""
    assert parse_json_chunk(b'{"response": "hello"}') == {"response": "hello"}
    assert parse_json_chunk(b"invalid-json") is None
    assert parse_json_chunk(b"") is None


@pytest.mark.asyncio
async def test_ollama_client_async_generate_success():
    """Tests OllamaClient.async_generate success state."""
    client = OllamaClient("http://fake-ollama")

    mock_request = httpx.Request("POST", "http://fake-ollama")
    mock_resp = httpx.Response(
        200, json={"response": "agent output response  "}, request=mock_request
    )
    with patch(
        "pipelines.workflows.deep_think_agent.client.httpx.AsyncClient.post",
        return_value=mock_resp,
    ) as mock_post:
        result = await client.async_generate("test-model", "test-prompt")
        assert result == "agent output response"
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_ollama_client_async_generate_failure():
    """Tests OllamaClient.async_generate failure state."""
    client = OllamaClient("http://fake-ollama")

    with patch(
        "pipelines.workflows.deep_think_agent.client.httpx.AsyncClient.post",
        side_effect=httpx.HTTPError("Network error"),
    ) as mock_post:
        result = await client.async_generate("test-model", "test-prompt")
        assert result == "ERROR: Agent timeout."
        mock_post.assert_called_once()


def test_ollama_client_stream_generate():
    """Tests OllamaClient.stream_generate iterator functionality."""
    client = OllamaClient("http://fake-ollama")

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.iter_lines.return_value = [
        b'{"response": "hello ", "done": false}',
        b'{"response": "world", "done": false}',
        b'{"response": "!", "done": true}',
    ]

    with patch(
        "pipelines.workflows.deep_think_agent.client.requests.post",
        return_value=mock_response,
    ) as mock_post:
        gen = client.stream_generate("test-model", "test-prompt")
        results = list(gen)
        assert results == ["hello ", "world"]
        mock_post.assert_called_once()


def test_ollama_client_stream_generate_failure():
    """Tests OllamaClient.stream_generate failure state handling."""
    client = OllamaClient("http://fake-ollama")

    with patch(
        "pipelines.workflows.deep_think_agent.client.requests.post",
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
    with patch(
        "pipelines.workflows.deep_think_agent.client.httpx.AsyncClient.get",
        return_value=mock_resp,
    ) as mock_get:
        results = await client.search("python testing")
        assert results == mock_results
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_searxng_client_search_http_error():
    """Tests SearxngClient.search returns empty list on HTTP error."""
    client = SearxngClient("http://fake-searxng")

    with patch(
        "pipelines.workflows.deep_think_agent.client.httpx.AsyncClient.get",
        side_effect=httpx.HTTPError("Connection refused"),
    ):
        results = await client.search("python testing")
        assert results == []


@pytest.mark.asyncio
async def test_searxng_client_search_value_error():
    """Tests SearxngClient.search returns empty list on JSON parse error."""
    client = SearxngClient("http://fake-searxng")

    mock_request = httpx.Request("GET", "http://fake-searxng")
    mock_resp = httpx.Response(
        200, content=b"not-valid-json", request=mock_request
    )
    with patch(
        "pipelines.workflows.deep_think_agent.client.httpx.AsyncClient.get",
        return_value=mock_resp,
    ):
        results = await client.search("python testing")
        assert results == []


def test_ollama_client_stream_generate_done_first():
    """Tests stream_generate yields nothing when first chunk is already done."""
    client = OllamaClient("http://fake-ollama")

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.iter_lines.return_value = [
        b'{"response": "!", "done": true}',
    ]

    with patch(
        "pipelines.workflows.deep_think_agent.client.requests.post",
        return_value=mock_response,
    ):
        results = list(client.stream_generate("test-model", "test-prompt"))
        assert results == []
