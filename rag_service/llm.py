"""Azure OpenAI client + grounded-answer generation for the rag_service.

The /query endpoint calls `generate_answer(question, chunks)` after hybrid
retrieval. The model gets a system prompt that:
  1. Names its role ("Epsilon AI assistant").
  2. For small talk / greetings, replies normally and introduces itself
     instead of pretending to find an answer in the docs.
  3. For substantive questions, answers strictly from the retrieved
     chunks and admits when the answer is not in the context.

The Azure client is constructed lazily on first use. If any required env
var is missing the module reports `is_enabled() == False` and the caller
should fall back to returning chunks only — the service still boots and
ingestion / retrieval still work without the LLM.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger("rag_service.llm")

# Lazy singletons. The Azure SDK reads creds at construction time, so we
# defer instantiation until the first call (a) to keep startup cheap and
# (b) so a missing/invalid key surfaces as a 500 on /query rather than a
# crash at boot.
_client: Any = None
_client_init_failed: bool = False


SYSTEM_PROMPT = """You are "Epsilon AI", a helpful assistant for the Epsilon AI platform.

Your job is to answer the user's question using ONLY the information in
the <context> block below, which comes from the user's own uploaded
documents.

Rules:
1. If the user just greets you (e.g. "hi", "hello", "hey", "good
   morning") or asks who you are, reply briefly, greet them back, and
   introduce yourself: explain that you are the Epsilon AI assistant and
   that you can answer questions about the documents they have
   uploaded. Do NOT invent document content in that case.
2. For any other question, answer using the context only. Quote or
   paraphrase the relevant passage in your own words.
3. DO NOT include page-number citations, source references, or any
   bracketed/parenthetical markers like "(p. 4)", "(page 4)",
   "(ص. 13)", "[chunk 2]", or "(source: ...)". The user wants a clean
   answer with no inline citations at all.
4. If the context does not contain the answer, say so plainly — do not
   guess and do not use outside knowledge.
5. Keep answers concise and well structured (short paragraphs or
   bullets). Match the language the user wrote in (Arabic or English).
"""


# Belt-and-suspenders citation scrubber. The system prompt already
# tells the model not to emit page references, but LLMs occasionally
# slip one in. These regexes catch the common shapes — English `(p. 4)`,
# `(page 4)`, `[p. 4]`, Arabic `(ص. 13)`, `[chunk 2]`, `(source: ...)`,
# etc. — and remove them after generation.
_CITATION_PATTERNS = [
    # Parenthesised page refs:  (p. 4)  (p.4)  (p 4)  (pp. 4-5)
    re.compile(r"\s*[\(\[]\s*pp?\.?\s*\d+(?:\s*[-–,]\s*\d+)*\s*[\)\]]", re.IGNORECASE),
    # (page 4) / (pages 4-5) / [page 4]
    re.compile(r"\s*[\(\[]\s*pages?\.?\s*\d+(?:\s*[-–,]\s*\d+)*\s*[\)\]]", re.IGNORECASE),
    # Arabic page markers:  (ص. 13)  (ص 13)  (ص13)  (صفحة 13)
    re.compile(r"\s*[\(\[]\s*(?:ص|صفحة)\.?\s*\d+(?:\s*[-–,]\s*\d+)*\s*[\)\]]"),
    # (chunk 2) / [chunk 2]
    re.compile(r"\s*[\(\[]\s*chunks?\s*\d+(?:\s*[-–,]\s*\d+)*\s*[\)\]]", re.IGNORECASE),
    # (source: ...) / (sources: p.4, p.5) / (ref: ...)
    re.compile(r"\s*[\(\[]\s*(?:source|sources|ref|refs|reference|references)\s*[:：][^\)\]]*[\)\]]", re.IGNORECASE),
]


def _strip_citations(text: str) -> str:
    """Remove any inline page/chunk/source citations the LLM may have
    emitted, then tidy up the whitespace left behind."""
    if not text:
        return text
    cleaned = text
    for pat in _CITATION_PATTERNS:
        cleaned = pat.sub("", cleaned)
    # Tidy: collapse "word  ," / "word  ." artefacts left by removed
    # parentheticals, and squeeze runs of blank lines.
    cleaned = re.sub(r"[ \t]+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# Cheap pattern that catches the most common greeting-only messages so
# we can skip retrieval entirely and let the LLM introduce itself. The
# LLM's system prompt also handles greetings on its own, but skipping
# retrieval here saves a database round-trip and an embed call for the
# trivial "hi" case.
_GREETING_RE = re.compile(
    r"^\s*(hi+|hello+|hey+|yo|hola|salam|salaam|"
    r"good\s+(morning|afternoon|evening)|"
    r"مرحبا|مرحبًا|اهلا|أهلا|السلام\s*عليكم|"
    r"who\s+are\s+you|what\s+can\s+you\s+do|"
    r"how\s+are\s+you)\s*[!.?]*\s*$",
    re.IGNORECASE,
)


def is_greeting(text: str) -> bool:
    """Return True for messages that look like pure small talk."""
    if not text:
        return False
    return bool(_GREETING_RE.match(text.strip()))


def is_enabled() -> bool:
    """True when the four AZURE_OPENAI_* env vars are populated."""
    return all(
        os.getenv(k)
        for k in (
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_DEPLOYMENT",
            "AZURE_OPENAI_API_VERSION",
        )
    )


def _get_client():
    """Construct (once) and return the AzureOpenAI client, or None if creds
    are missing / the SDK is unavailable / construction failed earlier."""
    global _client, _client_init_failed
    if _client is not None:
        return _client
    if _client_init_failed or not is_enabled():
        return None
    try:
        from openai import AzureOpenAI  # imported lazily so a missing dep
                                        # doesn't break ingestion-only setups

        _client = AzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        )
        logger.info(
            "llm: Azure OpenAI client ready (deployment=%s, api_version=%s)",
            os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            os.getenv("AZURE_OPENAI_API_VERSION"),
        )
        return _client
    except Exception as exc:  # noqa: BLE001 — degrade, don't crash
        _client_init_failed = True
        logger.exception("llm: failed to construct Azure OpenAI client: %s", exc)
        return None


def _format_context(chunks: list[dict], max_chars: int = 12000) -> str:
    """Stitch retrieved chunks into a single <context> block that fits in
    the prompt budget. Primary hits come first, neighbour-expansion rows
    are folded in after their parent so the model sees them as context."""
    parts: list[str] = []
    total = 0
    for i, c in enumerate(chunks, start=1):
        content = (c.get("content") or "").strip()
        if not content:
            continue
        page = c.get("page_number")
        section = (c.get("metadata") or {}).get("section_title", "") if isinstance(c.get("metadata"), dict) else ""
        header = f"[chunk {i} | page {page}"
        if section:
            header += f" | section: {section}"
        header += "]"
        block = f"{header}\n{content}"
        # Truncate per-chunk to keep one very long page from starving the
        # budget for the others.
        if len(block) > max_chars // 2:
            block = block[: max_chars // 2] + " …"
        if total + len(block) + 2 > max_chars:
            break
        parts.append(block)
        total += len(block) + 2
    return "\n\n".join(parts)


def generate_answer(
    question: str,
    chunks: list[dict],
    *,
    is_greeting_only: bool = False,
) -> str:
    """Call Azure OpenAI to synthesise an answer from the retrieved chunks.

    Returns a human-readable answer string. On any failure (missing
    creds, network error, model error) returns a short fallback message
    — the caller is expected to still render the source chunks below
    so the user gets at least the retrieval result.
    """
    client = _get_client()
    if client is None:
        return ""  # caller will fall back to chunks-only rendering

    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")

    if is_greeting_only or not chunks:
        # No retrieval results — let the LLM greet / introduce itself
        # using just the system prompt, with an empty context block.
        user_content = (
            f"<context>\n(no documents retrieved for this message)\n</context>\n\n"
            f"User message: {question}"
        )
    else:
        context = _format_context(chunks)
        user_content = (
            f"<context>\n{context}\n</context>\n\n"
            f"Question: {question}"
        )

    try:
        # Note: gpt-5 family deployments only accept default temperature
        # and use `max_completion_tokens` instead of `max_tokens`, so we
        # pass only the universally-supported fields here.
        resp = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
            max_completion_tokens=800,
        )
        answer = (resp.choices[0].message.content or "").strip()
        if not answer:
            logger.warning("llm: model returned empty content")
            return answer
        # Strip any inline page / chunk / source citations the model may
        # have emitted despite the system-prompt rule against them.
        return _strip_citations(answer)
    except Exception as exc:  # noqa: BLE001
        logger.exception("llm: chat.completions.create failed: %s", exc)
        return ""
