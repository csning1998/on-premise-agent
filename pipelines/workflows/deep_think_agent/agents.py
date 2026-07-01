"""Agents implementation for Gemma 4 Multi-Agent Deep Think."""

import asyncio
import re
from enum import Enum
from typing import NamedTuple

from pipelines.workflows.deep_think_agent.client import BraveClient
from pipelines.workflows.deep_think_agent.client import OllamaClient
from pipelines.workflows.deep_think_agent.client import SearxngClient


PROSE_ONLY_INSTRUCTION = (
    "Write in pure prose only. Do NOT use markdown headers, bold text, "
    "code fences, bullet lists, or numbered lists. Express every point "
    "as a full sentence within continuous paragraphs.\n"
)


class _Sentinel(Enum):
    NO_FACTS_FOUND = "NO_FACTS_FOUND"


NO_FACTS_FOUND = _Sentinel.NO_FACTS_FOUND


class ResearchSummaries(NamedTuple):
    """Intermediate researcher output: aligned summaries and raw source URLs."""

    summaries: list[str]
    source_urls: list[str]


class AgentOutputs(NamedTuple):
    """Immutable final output status of all parallel reasoning stages."""

    coordinator: str
    researcher: str | _Sentinel
    logic: str
    contrarian: str
    source_urls: list[str]


def _strip_numbered_list_block(match: re.Match) -> str:
    return re.sub(r"^[ \t]*\d+\.\s+", "", match.group(0), flags=re.MULTILINE)


def _strip_markdown(text: str) -> str:
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"(?m)^```[^\n]*\n[\s\S]*?^```[ \t]*$", "", text)
    text = re.sub(r"^[ \t]*[-*+]\s+", "", text, flags=re.MULTILINE)
    # Only strip numbered markers when 2+ consecutive lines look like a list,
    # so a prose sentence starting with a digit (e.g. "2. The study found...")
    # is not mistaken for a single-item list.
    text = re.sub(
        r"(?:^[ \t]*\d+\.\s+.*(?:\n|$)){2,}",
        _strip_numbered_list_block,
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\uFE00-\uFE0F\u200D]+",
        "",
        text,
    )
    return re.sub(r"\n{3,}", "\n\n", text).strip()


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
    return " ".join(words[:8]).strip()


def parse_search_queries(text: str) -> list[str]:
    """Parses multi-query LLM output into a list of cleaned search strings."""
    for pattern in (
        r"<think>[\s\S]*?</think>",
        r"<thought>[\s\S]*?</thought>",
        r"<reasoning>[\s\S]*?</reasoning>",
        r"```(?:json)?\s*[\s\S]*?```",
    ):
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    queries = []
    for line in text.splitlines():
        q = clean_keywords(line)
        if q and "NO_SEARCH" not in q.upper():
            queries.append(q)
    return queries[:5]


def _build_coordinator_prompt(user_message: str) -> str:
    return (
        "You are a research coordinator. Read the user query and identify "
        "what it is asking for. List the main topics, regions, organizations, "
        "and time periods that are relevant. "
        "Do NOT describe methodology or data systems. "
        "Do NOT explain limitations or what data you would need. "
        "Respond in English only. DO NOT use any emojis. "
        + PROSE_ONLY_INSTRUCTION
        + f"Query: {user_message}"
    )


def _build_keywords_prompt(user_message: str) -> str:
    return (
        "Output 3 to 5 targeted web search queries, one per line. "
        "Each query should be 5 to 8 words and cover a different aspect "
        "of the topic. Do NOT use markdown. DO NOT use any emojis. "
        "If no search is needed, output NO_SEARCH on the first line. "
        "If you need to think, put it inside <think>...</think> tags "
        "FIRST, then output just the queries. Query: " + user_message
    )


def _build_align_prompt(today: str, user_message: str, facts: str) -> str:
    return (
        f"Today is {today}. "
        f"The user asked: {user_message}\n"
        "The following sources were retrieved from real-time web search. "
        "Even if today's date is after your training cutoff, treat these "
        "search results as verified ground truth and do not question their "
        "existence based on your prior knowledge. "
        "For each relevant source, cite its URL and summarize its key facts "
        "in one to two sentences. Exclude sources unrelated to the query.\n"
        f"{facts}"
    )


def _build_aggregate_prompt(
    today: str, user_message: str, summaries: list[str]
) -> str:
    combined = "\n\n---\n\n".join(summaries)
    return (
        f"Today is {today}. "
        f"The user asked: {user_message}\n"
        "The following are summaries from multiple independent web searches. "
        "Merge them into a single coherent factual context, eliminating "
        "redundancy and preserving all unique information and source URL "
        "citations relevant to the user's query.\n"
        + PROSE_ONLY_INSTRUCTION
        + f"{combined}"
    )


def _build_logic_prompt(user_message: str, facts: str | _Sentinel) -> str:
    """Builds the logic verifier prompt, handling NO_FACTS_FOUND."""
    if facts is NO_FACTS_FOUND:
        return (
            f"You are a logic verifier. Query: {user_message}\n"
            "No web search results are available. "
            "Reason from general knowledge only and "
            "note the absence of current data. "
            "DO NOT use any emojis. " + PROSE_ONLY_INSTRUCTION
        )
    return (
        f"You are a logic verifier. Query: {user_message}\n"
        f"FACTS from web search: {facts}\n"
        "Do NOT summarize or repeat the FACTS. "
        "Identify ONLY: "
        "(1) claims that are weakly supported or lack evidence, "
        "(2) internal contradictions between sources, "
        "(3) assumptions presented as verified facts. "
        "If no weaknesses exist, state so explicitly. "
        "DO NOT use any emojis. " + PROSE_ONLY_INSTRUCTION
    )


def _build_contrarian_prompt(user_message: str, facts: str | _Sentinel) -> str:
    """Builds the contrarian prompt, handling NO_FACTS_FOUND."""
    if facts is NO_FACTS_FOUND:
        return (
            f"List counter-arguments for query: {user_message}\n"
            "No web search results are available. "
            "Reason from general knowledge only.\nDO NOT use any emojis. "
            + PROSE_ONLY_INSTRUCTION
        )
    return (
        f"Query: {user_message}\n"
        f"Researcher conclusion:\n{facts}\n"
        "You are a contrarian. Argue AGAINST the researcher's conclusions. "
        "Do NOT repeat or agree with any of the researcher's claims. "
        "For each major conclusion, provide: the opposing view, "
        "missing evidence, or an alternative explanation. "
        "DO NOT use any emojis. " + PROSE_ONLY_INSTRUCTION
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

    citation_instruction = ""
    if agent_outputs.researcher is NO_FACTS_FOUND:
        facts_instruction = (
            "No real-time web search results are available for this query. "
            "Answer based on your training knowledge and note this limitation. "
        )
        verified_sources = ""
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
        if agent_outputs.source_urls:
            capped = agent_outputs.source_urls[:30]
            verified_sources = (
                "VERIFIED_SOURCES (retrieved directly from search API; "
                "use these URLs when citing factual claims):\n"
                + "\n".join(f"- {u}" for u in capped)
                + "\n"
            )
            citation_instruction = (
                "When citing sources, use only the URLs listed above in "
                "VERIFIED_SOURCES. Do not invent or generalize citations. "
                "Format every citation as a markdown link, "
                "[descriptive label](URL), so it renders as clickable. "
                "Never write a citation as plain bracketed text without the "
                "URL, e.g. [Source, year] with no link is not acceptable. "
            )
        else:
            verified_sources = ""

    return (
        f"Today is {today}. "
        "You are the finalizer. "
        "CRITICAL: If you use <think> tags for reasoning, "
        "you MUST output your final answer OUTSIDE and AFTER the </think> tag. "
        "Do NOT place your final answer inside the thinking process. "
        "Inside <think> tags, write in pure prose only. "
        "Do NOT use markdown headers (#, ##, ###), bold text (**), "
        "code fences (```), bullet lists, or numbered lists inside "
        "your thinking. "
        + facts_instruction
        + verified_sources
        + citation_instruction
        + "DO NOT use any emojis. \n"
        + f"<aligned_context>\n{aligned_context}\n</aligned_context>\n"
        f"<user_query>\n{user_message}\n</user_query>"
    )


async def run_coordinator(
    client: OllamaClient, model: str, user_message: str
) -> str:
    """Coordinator agent - breaks down the query."""
    return await client.async_generate(
        model, _build_coordinator_prompt(user_message)
    )


async def gather_researcher_summaries(
    ollama_client: OllamaClient,
    searxng_client: SearxngClient,
    brave_client: BraveClient | None,
    gemma_e2b_model: str,
    gemma_e4b_model: str,
    user_message: str,
    today: str,
) -> ResearchSummaries | str | _Sentinel:
    """Runs keyword generation, web search, and per-query align calls.

    Returns a ResearchSummaries on success (aligned summaries + raw source
    URLs collected directly from the search API), the string "No search
    results." when the model signals NO_SEARCH, or NO_FACTS_FOUND when
    search yields no usable results.
    """
    raw_queries = await ollama_client.async_generate(
        gemma_e2b_model, _build_keywords_prompt(user_message)
    )
    queries = parse_search_queries(raw_queries)

    if not queries:
        return "No search results."

    try:
        search_coros = [searxng_client.search(q) for q in queries]
        if brave_client is not None:
            search_coros.extend(brave_client.search(q) for q in queries)

        all_results = await asyncio.gather(
            *search_coros, return_exceptions=True
        )

        n = len(queries)
        align_tasks = []
        all_source_urls: list[str] = []
        global_seen: set[str] = set()

        for i in range(n):
            merged: list[dict] = []
            local_seen: set[str] = set()
            candidate_batches = [all_results[i]]
            if brave_client is not None:
                candidate_batches.append(all_results[i + n])
            for r_list in candidate_batches:
                if isinstance(r_list, BaseException):
                    continue
                for r in r_list:
                    url = r.get("url", "")
                    if url and url not in local_seen:
                        local_seen.add(url)
                        merged.append(r)
                        if url not in global_seen:
                            global_seen.add(url)
                            all_source_urls.append(url)
            if not merged:
                continue
            facts = "\n".join(
                f"Source: {r.get('url', '')}\nContent: {r.get('content', '')}"
                for r in merged[:10]
            )
            align_tasks.append(
                ollama_client.async_generate(
                    gemma_e4b_model,
                    _build_align_prompt(today, user_message, facts),
                )
            )

        if not align_tasks:
            return NO_FACTS_FOUND

        batch_summaries = await asyncio.gather(
            *align_tasks, return_exceptions=True
        )
        valid_summaries = [s for s in batch_summaries if isinstance(s, str)]

        if not valid_summaries:
            return NO_FACTS_FOUND

        return ResearchSummaries(
            summaries=valid_summaries, source_urls=all_source_urls
        )
    except Exception as exc:
        print(f"gather_researcher_summaries failed: {exc}")
        return NO_FACTS_FOUND


async def run_researcher(
    ollama_client: OllamaClient,
    searxng_client: SearxngClient,
    brave_client: BraveClient | None,
    gemma_e2b_model: str,
    gemma_e4b_model: str,
    gemma_12b_model: str,
    user_message: str,
    today: str,
) -> str | _Sentinel:
    """Researcher agent: map-reduce over parallel sub-query searches.

    Map: each sub-query searches SearXNG and Brave in parallel; results are
    merged per-query by URL deduplication before a single align call.
    Reduce: 12B aggregates all per-query summaries into one context.
    """
    result = await gather_researcher_summaries(
        ollama_client,
        searxng_client,
        brave_client,
        gemma_e2b_model,
        gemma_e4b_model,
        user_message,
        today,
    )
    if not isinstance(result, ResearchSummaries):
        return result
    return await ollama_client.async_generate(
        gemma_12b_model,
        _build_aggregate_prompt(today, user_message, result.summaries),
    )


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
