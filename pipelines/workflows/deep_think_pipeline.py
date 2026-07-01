"""Gemma 4 Multi-Agent Deep Think.

4 e4b agents in parallel + 12b finalizer with chain-of-thinking.

Requires Python 3.11+ for asyncio.Runner.
"""

import asyncio
import datetime
import os
import re
from typing import Any
from typing import Callable
from typing import Coroutine
from typing import Generator
from typing import Iterator
from typing import List
from typing import Optional
from typing import Union

from pydantic import BaseModel
from pydantic import Field

from pipelines.workflows.deep_think_agent.agents import NO_FACTS_FOUND
from pipelines.workflows.deep_think_agent.agents import AgentOutputs
from pipelines.workflows.deep_think_agent.agents import ResearchSummaries
from pipelines.workflows.deep_think_agent.agents import _build_aggregate_prompt
from pipelines.workflows.deep_think_agent.agents import _build_contrarian_prompt
from pipelines.workflows.deep_think_agent.agents import (
    _build_coordinator_prompt,
)
from pipelines.workflows.deep_think_agent.agents import _build_finalizer_prompt
from pipelines.workflows.deep_think_agent.agents import _build_logic_prompt
from pipelines.workflows.deep_think_agent.agents import (
    gather_researcher_summaries,
)
from pipelines.workflows.deep_think_agent.client import BraveClient
from pipelines.workflows.deep_think_agent.client import OllamaClient
from pipelines.workflows.deep_think_agent.client import SearxngClient
from pipelines.workflows.deep_think_agent.config import OLLAMA_BASE_URL
from pipelines.workflows.deep_think_agent.config import SEARXNG_BASE_URL


def _strip_markdown(text: str) -> str:
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"```[^\n]*\n[\s\S]*?```", "", text)
    text = re.sub(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF︀-️‍]+", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class Pipeline:
    """Open WebUI Pipeline for 4-agent multi-stage reasoning."""

    id: str = "gemma_4_multi_agent"
    name: str = "Gemma 4 Multi-Agent Deep Think"

    class Valves(BaseModel):
        """Configuration options for the pipeline."""

        pipelines: List[str] = Field(
            default=["*"],
            description="Target pipeline IDs for this valve configuration.",
        )
        ollama_url: str = Field(
            default=OLLAMA_BASE_URL,
            description="Base URL for the Ollama API.",
        )
        searxng_url: str = Field(
            default=SEARXNG_BASE_URL,
            description="Base URL for the SearXNG API.",
        )
        gemma_e4b_model: str = Field(
            default="gemma4:E4B-it-qat",
            description="Model identifier for all e4b agents.",
        )
        gemma_12b_model: str = Field(
            default="gemma4:12b-it-qat",
            description="Model identifier for finalizer.",
        )
        brave_api_key: str = Field(
            default=os.environ.get("BRAVE_API_KEY", ""),
            description="Brave Search API key. Leave empty to disable.",
        )

    def __init__(self):
        """Initializes the pipeline with default valves."""
        self.valves = self.Valves()

    async def on_startup(self):
        """Lifecycle event triggered when the pipeline starts."""
        print(f"Pipeline {self.name} started.")

    async def on_shutdown(self):
        """Lifecycle event triggered when the pipeline shuts down."""
        print(f"Pipeline {self.name} shutting down.")

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        """Main pipeline orchestration.

        Executes 4 e4b agents in parallel, followed by a 12b finalizer
        using UI thinking blocks.
        """
        __event_emitter__: Optional[
            Callable[[Any], Coroutine[Any, Any, None]]
        ] = body.get("__event_emitter__")

        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        ollama_client = OllamaClient(self.valves.ollama_url)
        searxng_client = SearxngClient(self.valves.searxng_url)
        brave_client = (
            BraveClient(self.valves.brave_api_key)
            if self.valves.brave_api_key
            else None
        )

        def stream_response():
            with asyncio.Runner() as runner:

                def emit(description: str, done: bool = False):
                    if callable(__event_emitter__):
                        runner.run(
                            __event_emitter__(
                                {
                                    "type": "status",
                                    "data": {
                                        "description": description,
                                        "done": done,
                                    },
                                }
                            )
                        )

                emit("Stage 1: Coordinator analyzing query")
                yield "<think>\n"
                yield "Coordinator:\n\n"
                coordinator_chunks: list[str] = []
                for chunk in ollama_client.stream_generate(
                    self.valves.gemma_e4b_model,
                    _build_coordinator_prompt(user_message),
                ):
                    yield chunk
                    coordinator_chunks.append(chunk)
                coordinator_output = _strip_markdown(
                    "".join(coordinator_chunks)
                )
                yield "\n\n</think>\n\n"

                emit("Stage 2: Researcher gathering facts")
                summaries_result = runner.run(
                    gather_researcher_summaries(
                        ollama_client,
                        searxng_client,
                        brave_client,
                        self.valves.gemma_e4b_model,
                        user_message,
                        today,
                    )
                )
                yield "<think>\n"
                yield "Research:\n\n"
                if isinstance(summaries_result, ResearchSummaries):
                    researcher_chunks: list[str] = []
                    for chunk in ollama_client.stream_generate(
                        self.valves.gemma_12b_model,
                        _build_aggregate_prompt(
                            today, user_message, summaries_result.summaries
                        ),
                    ):
                        yield chunk
                        researcher_chunks.append(chunk)
                    researcher_facts = "".join(researcher_chunks)
                    source_urls = summaries_result.source_urls
                else:
                    source_urls = []
                    if summaries_result is NO_FACTS_FOUND:
                        yield "No web search results found."
                        researcher_facts = NO_FACTS_FOUND
                    elif summaries_result == "No search results.":
                        yield summaries_result
                        researcher_facts = NO_FACTS_FOUND
                    else:
                        yield summaries_result
                        researcher_facts = summaries_result
                yield "\n\n</think>\n\n"

                emit("Stage 3: Logic verification")
                yield "<think>\n"
                yield "Logic:\n\n"
                logic_chunks: list[str] = []
                for chunk in ollama_client.stream_generate(
                    self.valves.gemma_e4b_model,
                    _build_logic_prompt(user_message, researcher_facts),
                ):
                    yield chunk
                    logic_chunks.append(chunk)
                logic_output = _strip_markdown("".join(logic_chunks))
                yield "\n\n</think>\n\n"

                emit("Stage 4: Contrarian analysis")
                yield "<think>\n"
                yield "Contrarian:\n\n"
                contrarian_chunks: list[str] = []
                for chunk in ollama_client.stream_generate(
                    self.valves.gemma_e4b_model,
                    _build_contrarian_prompt(user_message, researcher_facts),
                ):
                    yield chunk
                    contrarian_chunks.append(chunk)
                contrarian_output = _strip_markdown("".join(contrarian_chunks))
                yield "\n\n</think>\n\n"

                emit("Agents execution completed", done=True)

                agent_outputs = AgentOutputs(
                    coordinator=coordinator_output,
                    researcher=researcher_facts,
                    logic=logic_output,
                    contrarian=contrarian_output,
                    source_urls=source_urls,
                )

                final_prompt = _build_finalizer_prompt(
                    today, user_message, agent_outputs
                )

                yield from ollama_client.stream_generate(
                    self.valves.gemma_12b_model, final_prompt
                )

        return stream_response()
