"""Gemma 4 Multi-Agent Deep Think.

4 e4b agents in parallel + 12b finalizer with chain-of-thinking.

Requires Python 3.11+ for asyncio.Runner.
"""

import asyncio
import datetime
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
from pipelines.workflows.deep_think_agent.agents import _build_finalizer_prompt
from pipelines.workflows.deep_think_agent.agents import _Sentinel
from pipelines.workflows.deep_think_agent.agents import run_contrarian
from pipelines.workflows.deep_think_agent.agents import run_coordinator
from pipelines.workflows.deep_think_agent.agents import run_logic
from pipelines.workflows.deep_think_agent.agents import run_researcher
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

        def stream_response():
            # Reuse a single event loop across all async stages. Open WebUI
            # Pipelines runs pipe() in a threadpool with no running loop, so
            # a single Runner replaces the prior multiple asyncio.run() calls.
            with asyncio.Runner() as runner:
                yield "<think>\n"
                yield "Agents initializing...\n\n"

                if callable(__event_emitter__):
                    runner.run(
                        __event_emitter__(
                            {
                                "type": "status",
                                "data": {
                                    "description": (
                                        "Stage 1: Coordinator and Research"
                                        " starting"
                                    ),
                                    "done": False,
                                },
                            }
                        )
                    )

                async def run_stage_1():
                    t1 = asyncio.create_task(
                        run_coordinator(
                            ollama_client,
                            self.valves.gemma_e4b_model,
                            user_message,
                        )
                    )
                    t2 = asyncio.create_task(
                        run_researcher(
                            ollama_client,
                            searxng_client,
                            self.valves.gemma_e4b_model,
                            user_message,
                            today,
                        )
                    )
                    return await asyncio.gather(t1, t2)

                coordinator_output, researcher_facts = runner.run(run_stage_1())

                yield (
                    f"Coordinator:\n\n{_strip_markdown(coordinator_output)}\n\n"
                )

                if researcher_facts is NO_FACTS_FOUND:
                    researcher_snippet = "No web search results found."
                elif len(researcher_facts) > 300:
                    researcher_snippet = researcher_facts[:300] + "..."
                else:
                    researcher_snippet = researcher_facts
                yield (
                    f"Research:\n\n{_strip_markdown(researcher_snippet)}\n\n"
                )

                if callable(__event_emitter__):
                    runner.run(
                        __event_emitter__(
                            {
                                "type": "status",
                                "data": {
                                    "description": (
                                        "Stage 2: Logic and Contrarian starting"
                                    ),
                                    "done": False,
                                },
                            }
                        )
                    )

                async def run_stage_2(facts: str | _Sentinel):
                    t1 = asyncio.create_task(
                        run_logic(
                            ollama_client,
                            self.valves.gemma_e4b_model,
                            user_message,
                            facts,
                        )
                    )
                    t2 = asyncio.create_task(
                        run_contrarian(
                            ollama_client,
                            self.valves.gemma_e4b_model,
                            user_message,
                            facts,
                        )
                    )
                    return await asyncio.gather(t1, t2)

                logic_output, contrarian_output = runner.run(
                    run_stage_2(researcher_facts)
                )

                if callable(__event_emitter__):
                    runner.run(
                        __event_emitter__(
                            {
                                "type": "status",
                                "data": {
                                    "description": "Agents execution completed",
                                    "done": True,
                                },
                            }
                        )
                    )

                yield f"Logic:\n\n{_strip_markdown(logic_output)}\n\n"
                yield (
                    f"Contrarian:\n\n{_strip_markdown(contrarian_output)}\n\n"
                )
                yield "</think>\n\n"

                # Package into immutable NamedTuple to preserve final states
                agent_outputs = AgentOutputs(
                    coordinator=coordinator_output,
                    researcher=researcher_facts,
                    logic=logic_output,
                    contrarian=contrarian_output,
                )

                final_prompt = _build_finalizer_prompt(
                    today, user_message, agent_outputs
                )

                yield from ollama_client.stream_generate(
                    self.valves.gemma_12b_model, final_prompt
                )

        return stream_response()
