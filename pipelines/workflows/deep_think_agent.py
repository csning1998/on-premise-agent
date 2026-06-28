"""Gemma 4 Multi-Agent Deep Think.

4 e4b agents in parallel + 26b-a4b finalizer with chain-of-thinking.
"""

import asyncio
from typing import Generator
from typing import Iterator
from typing import List
from typing import Union

from pydantic import BaseModel
from pydantic import Field

from pipelines.workflows.deep_think_agent.agents import AgentOutputs
from pipelines.workflows.deep_think_agent.agents import run_contrarian
from pipelines.workflows.deep_think_agent.agents import run_coordinator
from pipelines.workflows.deep_think_agent.agents import run_logic
from pipelines.workflows.deep_think_agent.agents import run_researcher
from pipelines.workflows.deep_think_agent.client import OllamaClient
from pipelines.workflows.deep_think_agent.client import SearxngClient
from pipelines.workflows.deep_think_agent.config import OLLAMA_BASE_URL
from pipelines.workflows.deep_think_agent.config import SEARXNG_BASE_URL


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
        e4b_model: str = Field(
            default="gemma4:E4B-it-qat",
            description="Model identifier for all e4b agents.",
        )
        a4b_model: str = Field(
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

        Executes 4 e4b agents in parallel, followed by a 26b finalizer
        using UI thinking blocks.
        """
        __event_emitter__ = body.get("__event_emitter__")

        ollama_client = OllamaClient(self.valves.ollama_url)
        searxng_client = SearxngClient(self.valves.searxng_url)

        def stream_response():
            yield "<thought>\n"
            yield "#### Agents Initializing...\n"

            # Stage 1: Run Coordinator and Researcher in parallel
            async def run_stage_1():
                if __event_emitter__:
                    await __event_emitter__(
                        {
                            "type": "status",
                            "data": {
                                "description": (
                                    "Stage 1: Coordinator and Research starting"
                                ),
                                "done": False,
                            },
                        }
                    )
                coordinator_task = asyncio.create_task(
                    run_coordinator(
                        ollama_client, self.valves.e4b_model, user_message
                    )
                )
                researcher_task = asyncio.create_task(
                    run_researcher(
                        ollama_client,
                        searxng_client,
                        self.valves.e4b_model,
                        user_message,
                    )
                )
                return await asyncio.gather(coordinator_task, researcher_task)

            coordinator_output, researcher_facts = asyncio.run(run_stage_1())
            yield "</thought>\n\n"

            yield "<thought>\n"
            yield f"#### Coordinator\n{coordinator_output}\n\n"
            yield "</thought>\n\n"

            yield "<thought>\n"
            yield f"#### Research\n{researcher_facts[:300]}...\n\n"
            yield "</thought>\n\n"

            # Stage 2: Run Logic and Contrarian in parallel
            async def run_stage_2(facts):
                if __event_emitter__:
                    await __event_emitter__(
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
                logic_task = asyncio.create_task(
                    run_logic(
                        ollama_client,
                        self.valves.e4b_model,
                        user_message,
                        facts,
                    )
                )
                contrarian_task = asyncio.create_task(
                    run_contrarian(
                        ollama_client,
                        self.valves.e4b_model,
                        user_message,
                        facts,
                    )
                )
                res = await asyncio.gather(logic_task, contrarian_task)
                if __event_emitter__:
                    await __event_emitter__(
                        {
                            "type": "status",
                            "data": {
                                "description": "Agents execution completed",
                                "done": True,
                            },
                        }
                    )
                return res

            logic_output, contrarian_output = asyncio.run(
                run_stage_2(researcher_facts)
            )

            yield "<thought>\n"
            yield f"#### Logic\n{logic_output}\n\n"
            yield "</thought>\n\n"

            yield "<thought>\n"
            yield f"#### Contrarian\n{contrarian_output}\n"
            yield "</thought>\n\n"

            # Package into immutable NamedTuple to preserve final states
            agent_outputs = AgentOutputs(
                coordinator=coordinator_output,
                researcher=researcher_facts,
                logic=logic_output,
                contrarian=contrarian_output,
            )

            aligned_context = (
                f"COORDINATOR: {agent_outputs.coordinator}\n"
                f"RESEARCH FACTS: {agent_outputs.researcher}\n"
                f"LOGIC CHECK: {agent_outputs.logic}\n"
                f"CONTRARIAN: {agent_outputs.contrarian}"
            )

            final_prompt = (
                "You are the finalizer. "
                "CRITICAL: If you use <think> tags for reasoning, "
                "you MUST output your final answer OUTSIDE and AFTER "
                "the </think> tag. "
                "Do NOT place your final answer inside the thinking process. "
                "DO NOT use any emojis. "
                f"ALIGNED CONTEXT: {aligned_context} \n "
                f"USER QUERY: {user_message}"
            )

            yield from ollama_client.stream_generate(
                self.valves.a4b_model, final_prompt
            )

        return stream_response()
