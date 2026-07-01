"""Client implementations for Ollama, SearXNG, and Brave Search APIs."""

import json
import urllib.parse
from typing import Generator

import httpx
import requests


def parse_json_chunk(line: bytes | str) -> dict | None:
    """Parses a single JSON line chunk from Ollama stream.

    Avoids nested try-except blocks.
    """
    try:
        return json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None


class OllamaClient:
    """Client for Ollama server API requests."""

    def __init__(self, base_url: str):
        """Initializes the client with a base URL."""
        self.base_url = base_url

    async def async_generate(self, model: str, prompt: str) -> str:
        """Asynchronously calls Ollama generate endpoint."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "keep_alive": "5m",
                    },
                    timeout=300,
                )
                response.raise_for_status()
                return response.json().get("response", "").strip()
            except httpx.HTTPError as e:
                print(
                    f"Ollama async generate failed: {e}."
                    f"Requested model was: '{model}'"
                )
                return "ERROR: Agent timeout."

    def stream_generate(
        self, model: str, prompt: str
    ) -> Generator[str, None, None]:
        """Streams generate response from Ollama server."""
        try:
            with requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {"num_ctx": 16384},
                },
                stream=True,
                timeout=300,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    chunk = parse_json_chunk(line)
                    if chunk and not chunk.get("done", False):
                        yield chunk.get("response", "")
        except requests.exceptions.RequestException as e:
            print(
                f"Stream generate failed: {e}. Requested model was: '{model}'"
            )
            yield "ERROR: Agent timeout or connection failure."


class SearxngClient:
    """Client for SearXNG API requests."""

    def __init__(self, base_url: str):
        """Initializes the client with a base URL."""
        self.base_url = base_url

    async def search(self, query: str) -> list:
        """Queries SearXNG search endpoint."""
        encoded_query = urllib.parse.quote(query, safe="")
        search_url = f"{self.base_url}/search?q={encoded_query}&format=json"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(search_url, timeout=60)
                response.raise_for_status()
                return response.json().get("results", [])
            except (httpx.HTTPError, ValueError) as e:
                print(f"SearXNG search failed: {e}")
                return []


class BraveClient:
    """Client for Brave Search API."""

    def __init__(self, api_key: str):
        """Initializes the client with a Brave Search API key."""
        self._api_key = api_key

    async def search(self, query: str) -> list:
        """Queries Brave Search API and returns list of result.

        Result is compatible with SearXNG-compatible format.
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                        "X-Subscription-Token": self._api_key,
                    },
                    params={"q": query, "count": 10},
                    timeout=httpx.Timeout(
                        connect=5.0, read=25.0, write=5.0, pool=5.0
                    ),
                )
                response.raise_for_status()
                results = response.json().get("web", {}).get("results", [])
                return [
                    {
                        "url": r.get("url", ""),
                        "content": r.get("description", ""),
                    }
                    for r in results
                ]
            except (httpx.HTTPError, ValueError) as e:
                print(f"Brave Search failed: {e}")
                return []
