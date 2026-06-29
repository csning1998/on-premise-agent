"""Agents implementation for Gemma 4 Multi-Agent Deep Think."""

import re
from typing import NamedTuple

from pipelines.workflows.deep_think_agent.client import OllamaClient
from pipelines.workflows.deep_think_agent.client import SearxngClient


class AgentOutputs(NamedTuple):
    """Immutable final output status of all parallel reasoning stages."""

    coordinator: str
    researcher: str
    logic: str
    contrarian: str


def clean_keywords(text: str) -> str:
    """Removes markdown code blocks, JSON artifacts, and noise from keywords."""
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<thought>[\s\S]*?</thought>", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"<reasoning>[\s\S]*?</reasoning>", "", text, flags=re.IGNORECASE
    )
    text = re.sub(r"```(?:json)?\s*[\s\S]*?```", "", text)
    text = re.sub(r"\{.*?\}", "", text)
    text = re.sub(r"[\"\'\[\]\(\)]", "", text)
    words = re.findall(r"\w+", text)
    return " ".join(words[:5]).strip()


async def run_coordinator(
    client: OllamaClient, model: str, user_message: str
) -> str:
    """Coordinator agent - breaks down the query."""
    prompt = f"Break down the query: {user_message}\nDO NOT use any emojis."
    return await client.async_generate(model, prompt)


async def run_researcher(
    ollama_client: OllamaClient,
    searxng_client: SearxngClient,
    gemma_e4b_model: str,
    user_message: str,
    today: str,
) -> str:
    """Researcher agent - queries external facts and aligns them."""
    keywords_prompt = (
        "You must output ONLY 3-5 search keywords for web search. "
        "Do NOT use markdown. DO NOT use any emojis. "
        "If no search is needed, output NO_SEARCH. "
        "If you need to think, put it inside <think>...</think> tags FIRST, "
        "then output just the keywords. Query: " + user_message
    )
    raw_keywords = await ollama_client.async_generate(
        gemma_e4b_model, keywords_prompt
    )
    keywords = clean_keywords(raw_keywords)

    if not keywords or "NO_SEARCH" in keywords:
        return "No search results."

    try:
        results = await searxng_client.search(keywords)
        results = results[:10]
        facts = "\n".join(
            [
                f"Source: {r.get('url', '')}\nContent: {r.get('content', '')}"
                for r in results
            ]
        )
        align_prompt = (
            f"Today is {today}. "
            "The following facts are retrieved from real-time web search "
            "and reflect events that have already occurred. "
            "Treat them as verified ground truth. "
            f"Align and summarize:\n{facts}"
        )
        return await ollama_client.async_generate(gemma_e4b_model, align_prompt)
    except Exception as e:
        return f"Search failed: {e}"


async def run_logic(
    client: OllamaClient, model: str, user_message: str, facts: str
) -> str:
    """Logic Verifier agent that reconciles conflicts and verifies consistency.

    `facts` is interpolated into the prompt without length truncation. The
    current configuration is safe because `facts` originates from the E4B
    researcher whose output is bounded by its own n_ctx=4096. If the researcher
    model is replaced with a larger one (e.g. 12b, n_ctx=16384), the researcher
    output can exceed the logic model's context window and cause silent
    truncation or hallucination at the Ollama layer.

    Args:
        client: Ollama client used to call async_generate.
        model: Model identifier passed to the client.
        user_message: Original user query.
        facts: Aligned researcher output. Unbounded; see note above.

    Returns:
        Reconciled logical analysis as a plain string.
    """
    prompt = (
        f"You are a logic verifier. Query: {user_message}\n"
        f"FACTS from web search (treat as ground truth): {facts}\n"
        "Step 1: Identify any conflicts between sources. "
        "Step 2: For each conflict, reason which claim is more credible "
        "based on source specificity, recency, and reliability. "
        "Step 3: Output a reconciled summary of what is most likely true. "
        "Do NOT merely list conflicts without resolution. "
        "DO NOT use any emojis."
    )
    return await client.async_generate(model, prompt)


async def run_contrarian(
    client: OllamaClient, model: str, user_message: str, facts: str
) -> str:
    """Contrarian agent that challenges assumptions against retrieved facts.

    Carries the same ``facts`` length constraint as ``run_logic``. See that
    function's docstring for the full risk scenario and trigger condition.

    Args:
        client: Ollama client used to call async_generate.
        model: Model identifier passed to the client.
        user_message: Original user query.
        facts: Aligned researcher output. Unbounded; see run_logic.

    Returns:
        Counter-arguments and assumption challenges as a plain string.
    """
    prompt = (
        f"List counter-arguments for query: {user_message}\n"
        f"FACTS: {facts}\nDO NOT use any emojis."
    )
    return await client.async_generate(model, prompt)
