"""
LLM synthesis engine for the Researcher module.

Turns gathered sources into a written answer/report. Two engines are supported:

- **Perplexity** (``api.perplexity.ai``) — preferred: it returns a cited answer
  directly.
- **OpenRouter** (``openrouter.ai/api/v1``) — used to synthesize over fetched
  source text when Perplexity is not configured.

The engine is selected from ``NINJA_RESEARCHER_LLM`` (``auto`` by default, which
prefers Perplexity then OpenRouter) and ``NINJA_RESEARCHER_MODEL``. When no
engine is available (or the mode is disabled) :func:`resolve_synthesis_engine`
returns ``None`` and callers fall back to their deterministic templates.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from ninja_common.logging_utils import get_logger
from ninja_common.secrets import get_secret


logger = get_logger(__name__)


EngineKind = Literal["perplexity", "openrouter"]

_PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
_PERPLEXITY_SEARCH_URL = "https://api.perplexity.ai/search"
_PERPLEXITY_CHAT_URL = "https://api.perplexity.ai/chat/completions"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_PERPLEXITY_MODEL = "sonar-pro"
_DEFAULT_OPENROUTER_MODEL = "anthropic/claude-sonnet-4"

_DISABLED = {"off", "none", "disable", "disabled", "template", "templates"}

_REPORT_STYLES: dict[str, str] = {
    "comprehensive": "a comprehensive, well-structured report (max 5 sections)",
    "summary": "a concise executive-style summary (max 3 sections)",
    "technical": "a technical, in-depth analysis (max 5 sections)",
    "executive": "an executive brief focused on decisions and impact (max 3 sections)",
}

_REPORT_MAX_TOKENS: dict[str, int] = {
    "comprehensive": 4096,
    "technical": 4096,
    "summary": 1024,
    "executive": 1024,
}


@dataclass(frozen=True)
class SynthesisEngine:
    """A resolved OpenAI-compatible chat-completions engine."""

    kind: EngineKind
    model: str
    api_key: str
    base_url: str

    @property
    def label(self) -> str:
        """Return a stable ``provider/model`` label for reporting and logs."""
        return f"{self.kind}/{self.model}"


def _env_model() -> str:
    """Return the configured synthesis model, if any."""
    return os.environ.get("NINJA_RESEARCHER_MODEL", "").strip()


def _looks_like_openrouter(model: str) -> bool:
    """Return True when a model id is namespaced (``vendor/model``), not ``sonar*``."""
    return "/" in model and not model.startswith("sonar")


def resolve_synthesis_engine() -> SynthesisEngine | None:
    """
    Resolve the configured synthesis engine.

    ``NINJA_RESEARCHER_LLM`` controls selection:

    - ``off``/``none``/``disabled``/``template`` → no engine (templates only)
    - ``perplexity`` → Perplexity only (``None`` if no key)
    - ``openrouter`` → OpenRouter only (``None`` if no key)
    - ``auto`` (default) → Perplexity if available, else OpenRouter, else ``None``

    Returns:
        A resolved :class:`SynthesisEngine`, or ``None`` when unavailable.
    """
    mode = os.environ.get("NINJA_RESEARCHER_LLM", "auto").strip().lower()
    if mode in _DISABLED:
        return None

    model = _env_model()
    perplexity_key = get_secret("PERPLEXITY_API_KEY") or ""
    openrouter_key = get_secret("OPENROUTER_API_KEY") or ""

    def perplexity() -> SynthesisEngine | None:
        if not perplexity_key:
            return None
        chosen = model if model and not _looks_like_openrouter(model) else _DEFAULT_PERPLEXITY_MODEL
        return SynthesisEngine("perplexity", chosen, perplexity_key, _PERPLEXITY_BASE_URL)

    def openrouter() -> SynthesisEngine | None:
        if not openrouter_key:
            return None
        chosen = model if model and _looks_like_openrouter(model) else _DEFAULT_OPENROUTER_MODEL
        return SynthesisEngine("openrouter", chosen, openrouter_key, _OPENROUTER_BASE_URL)

    if mode == "perplexity":
        return perplexity()
    if mode == "openrouter":
        return openrouter()
    return perplexity() or openrouter()


async def complete(
    engine: SynthesisEngine,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    return_citations: bool = False,
    timeout_s: float = 90.0,
) -> tuple[str, list[str]]:
    """
    Run a chat completion against the engine.

    Args:
        engine: Resolved synthesis engine.
        messages: OpenAI-style chat messages.
        temperature: Sampling temperature.
        max_tokens: Maximum generated tokens.
        return_citations: Ask Perplexity to return citation URLs.
        timeout_s: Per-request timeout in seconds.

    Returns:
        ``(content, citations)``; citations are empty for non-Perplexity engines.

    Raises:
        httpx.HTTPStatusError: On a non-2xx response.
        httpx.HTTPError: On transport failures.
    """
    payload: dict[str, Any] = {
        "model": engine.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if return_citations and engine.kind == "perplexity":
        payload["return_citations"] = True

    url = (
        _PERPLEXITY_CHAT_URL
        if engine.kind == "perplexity"
        else f"{engine.base_url}/chat/completions"
    )
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {engine.api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

    content = ""
    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = str(message.get("content") or "")

    raw_citations = data.get("citations") or []
    citations = [c for c in raw_citations if isinstance(c, str)]

    return content.strip(), citations


def _sources_block(sources: list[dict[str, Any]], limit: int = 20) -> str:
    """Render sources as an indexed block for the prompt."""
    lines: list[str] = []
    for index, source in enumerate(sources[:limit], 1):
        title = source.get("title") or "Untitled"
        url = source.get("url") or ""
        date = source.get("date") or source.get("last_updated") or ""
        body = source.get("snippet") or source.get("content") or source.get("description") or ""
        date_suffix = f" ({date})" if date else ""
        lines.append(f"[{index}] {title}{date_suffix} ({url})\n{str(body).strip()[:1500]}")
    return "\n\n".join(lines)


def build_report_messages(
    topic: str, sources: list[dict[str, Any]], report_type: str
) -> list[dict[str, str]]:
    """Build the chat messages that ask for a synthesized report."""
    style = _REPORT_STYLES.get(report_type, _REPORT_STYLES["comprehensive"])
    system = (
        f"You are a meticulous research analyst. Write {style} on the user's topic.\n"
        "Rules:\n"
        "- Use ONLY the provided sources [1..N]; never invent facts, numbers or URLs.\n"
        "- Start with a direct 1-2 sentence answer, then Markdown sections (headers, bullets).\n"
        "- Cite every factual sentence inline, e.g. [1][3].\n"
        "- Note uncertainty or disagreement between sources explicitly.\n"
        "- No separate References section needed beyond a final 'Sources' list with [N] links."
    )
    user = f"Topic: {topic}\n\nSources:\n\n{_sources_block(sources)}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_answer_messages(query: str, sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build the chat messages that ask for a direct answer from search results."""
    system = (
        "You are a meticulous research analyst answering from provided results only.\n"
        "Rules:\n"
        "- Start with a direct 1-2 sentence answer (3-6 sentences total).\n"
        "- Cite every factual sentence inline, e.g. [1][2].\n"
        "- Never invent facts, numbers or URLs.\n"
        "- If results are insufficient, say so explicitly."
    )
    user = f"Question: {query}\n\nSearch results:\n\n{_sources_block(sources)}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def synthesize_report(
    engine: SynthesisEngine,
    topic: str,
    sources: list[dict[str, Any]],
    report_type: str,
) -> str:
    """Synthesize a Markdown report from sources using the engine."""
    max_tokens = _REPORT_MAX_TOKENS.get(report_type, 4096)
    content, _ = await complete(
        engine,
        build_report_messages(topic, sources, report_type),
        max_tokens=max_tokens,
        return_citations=engine.kind == "perplexity",
    )
    return content


async def synthesize_answer(
    engine: SynthesisEngine,
    query: str,
    sources: list[dict[str, Any]],
) -> str:
    """Synthesize a short direct answer from search results using the engine."""
    content, _ = await complete(
        engine,
        build_answer_messages(query, sources),
        max_tokens=1024,
        return_citations=engine.kind == "perplexity",
    )
    return content
