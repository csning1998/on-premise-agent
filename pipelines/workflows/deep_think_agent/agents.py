"""Agents implementation for Gemma 4 Multi-Agent Deep Think."""

import re
from enum import Enum
from typing import NamedTuple

from pipelines.workflows.deep_think_agent.client import OllamaClient
from pipelines.workflows.deep_think_agent.client import SearxngClient


class _Sentinel(Enum):
    NO_FACTS_FOUND = "NO_FACTS_FOUND"


NO_FACTS_FOUND = _Sentinel.NO_FACTS_FOUND


class AgentOutputs(NamedTuple):
    """Immutable final output status of all parallel reasoning stages."""

    coordinator: str
    researcher: str | _Sentinel
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


def _build_coordinator_prompt(user_message: str) -> str:
    return (
        f"Break down the query: {user_message}\n"
        "Respond in English only. DO NOT use any emojis."
    )


def _build_keywords_prompt(user_message: str) -> str:
    return (
        "You must output ONLY 3-5 search keywords for web search. "
        "Do NOT use markdown. DO NOT use any emojis. "
        "If no search is needed, output NO_SEARCH. "
        "If you need to think, put it inside <think>...</think> tags FIRST, "
        "then output just the keywords. Query: " + user_message
    )


def _build_align_prompt(today: str, facts: str) -> str:
    return (
        f"Today is {today}. "
        "The following facts are retrieved from real-time web search "
        "and reflect events that have already occurred. "
        "Treat them as verified ground truth. "
        f"Align and summarize:\n{facts}"
    )


def _build_logic_prompt(user_message: str, facts: str | _Sentinel) -> str:
    """Builds the logic verifier prompt, handling NO_FACTS_FOUND."""
    if facts is NO_FACTS_FOUND:
        return (
            f"You are a logic verifier. Query: {user_message}\n"
            "No web search results are available. "
            "Reason from general knowledge only and "
            "note the absence of current data. "
            "DO NOT use any emojis."
        )
    return (
        f"You are a logic verifier. Query: {user_message}\n"
        f"FACTS from web search (treat as ground truth): {facts}\n"
        "Step 1: Identify any conflicts between sources. "
        "Step 2: For each conflict, reason which claim is more credible "
        "based on source specificity, recency, and reliability. "
        "Step 3: Output a reconciled summary of what is most likely true. "
        "Do NOT merely list conflicts without resolution. "
        "DO NOT use any emojis."
    )


def _build_contrarian_prompt(user_message: str, facts: str | _Sentinel) -> str:
    """Builds the contrarian prompt, handling NO_FACTS_FOUND."""
    if facts is NO_FACTS_FOUND:
        return (
            f"List counter-arguments for query: {user_message}\n"
            "No web search results are available. "
            "Reason from general knowledge only.\nDO NOT use any emojis."
        )
    return (
        f"List counter-arguments for query: {user_message}\n"
        f"FACTS: {facts}\nDO NOT use any emojis."
    )


def _build_finalizer_prompt(
    today: str, user_message: str, agent_outputs: AgentOutputs
) -> str:
    """Builds the finalizer prompt, synthesizing outputs from all agents."""
    aligned_context = (
        f"COORDINATOR: {agent_outputs.coordinator}\n"
        f"RESEARCH FACTS: {agent_outputs.researcher}\n"
        f"LOGIC CHECK: {agent_outputs.logic}\n"
        f"CONTRARIAN: {agent_outputs.contrarian}"
    )

    if agent_outputs.researcher is NO_FACTS_FOUND:
        facts_instruction = (
            "No real-time web search results are available for this query. "
            "Answer based on your training knowledge and note this limitation. "
        )
    else:
        facts_instruction = (
            "The ALIGNED CONTEXT below contains facts retrieved from real-time "
            "web search. Treat all facts in ALIGNED CONTEXT as verified "
            "ground truth reflecting real, already-occurred events. "
            "When ALIGNED CONTEXT contains conflicting information, "
            "synthesize a best-estimate answer based on the most credible "
            "evidence. Commit to the most likely correct answer; do not "
            "present all conflicting views equally without resolution. "
        )

    return (
        f"Today is {today}. "
        "You are the finalizer. "
        "CRITICAL: If you use <think> tags for reasoning, "
        "you MUST output your final answer OUTSIDE and AFTER the </think> tag. "
        "Do NOT place your final answer inside the thinking process. "
        "Inside <think> tags, write in pure prose only. "
        "Do NOT use markdown headers (#, ##, ###), bold text (**), "
        "or code fences (```) inside your thinking. "
        + facts_instruction
        + "DO NOT use any emojis. "
        f"<aligned_context>\n{aligned_context}\n</aligned_context>\n"
        f"<user_query>\n{user_message}\n</user_query>"
    )


async def run_coordinator(
    client: OllamaClient, model: str, user_message: str
) -> str:
    """Coordinator agent - breaks down the query."""
    return await client.async_generate(
        model, _build_coordinator_prompt(user_message)
    )


async def run_researcher(
    ollama_client: OllamaClient,
    searxng_client: SearxngClient,
    gemma_e4b_model: str,
    user_message: str,
    today: str,
) -> str | _Sentinel:
    """Researcher agent - queries external facts and aligns them."""
    raw_keywords = await ollama_client.async_generate(
        gemma_e4b_model, _build_keywords_prompt(user_message)
    )
    keywords = clean_keywords(raw_keywords)

    if not keywords or "NO_SEARCH" in keywords:
        return "No search results."

    try:
        results = await searxng_client.search(keywords)
        results = results[:10]
        if not results:
            return NO_FACTS_FOUND
        facts = "\n".join(
            [
                f"Source: {r.get('url', '')}\nContent: {r.get('content', '')}"
                for r in results
            ]
        )
        return await ollama_client.async_generate(
            gemma_e4b_model, _build_align_prompt(today, facts)
        )
    except Exception:
        return NO_FACTS_FOUND


async def run_logic(
    client: OllamaClient, model: str, user_message: str, facts: str | _Sentinel
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
    return await client.async_generate(
        model, _build_logic_prompt(user_message, facts)
    )


async def run_contrarian(
    client: OllamaClient, model: str, user_message: str, facts: str | _Sentinel
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
    return await client.async_generate(
        model, _build_contrarian_prompt(user_message, facts)
    )
