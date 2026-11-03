"""
Member 2's module, stage 1: Note -> atomic claims.

Inspired by FActScore (Min et al., 2023): decompose the generated text into
short, independently-checkable "atomic facts" rather than verifying whole
sentences (a sentence can be half-supported, half-invented).
"""
from __future__ import annotations

import re
from typing import List

from generation.generate import LLMBackend, get_backend
from config import CONFIG

CLAIM_EXTRACTION_PROMPT = """Break the following clinical note into a list of atomic \
clinical claims. Each claim must:
- State exactly one fact (one symptom, one finding, one instruction, etc.)
- Be understandable on its own, without needing the rest of the note
- Preserve clinical meaning exactly (do not add or remove information)

Clinical note:
\"\"\"
{note}
\"\"\"

Return ONLY a numbered list, one claim per line, nothing else.
"""

_SECTION_HEADERS = re.compile(
    r"^(subjective|objective|assessment|plan)\s*:?\s*$", re.IGNORECASE
)


def _rule_based_claims(note: str) -> List[str]:
    """
    Offline fallback: split into sentences, drop section headers and empty
    lines. Coarser than LLM decomposition (a sentence may bundle >1 fact)
    but requires no API/model, useful for quick smoke tests.
    """
    claims: List[str] = []
    for line in note.splitlines():
        line = line.strip(" -*\t")
        if not line or _SECTION_HEADERS.match(line):
            continue
        # strip a leading "Subjective:" style prefix if present on the same line
        line = re.sub(r"^(subjective|objective|assessment|plan)\s*:\s*", "", line,
                       flags=re.IGNORECASE)
        for sent in re.split(r"(?<=[.!?])\s+", line):
            sent = sent.strip()
            if sent and len(sent.split()) > 2:
                claims.append(sent)
    return claims


def _parse_numbered_list(text: str) -> List[str]:
    claims = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^\d+[\.\)]\s*(.+)$", line)
        if m:
            claims.append(m.group(1).strip())
        elif line.startswith(("-", "*")):
            claims.append(line.lstrip("-* ").strip())
    return [c for c in claims if c]


def extract_claims(
    note: str,
    mode: str | None = None,
    backend: LLMBackend | None = None,
) -> List[str]:
    """
    Fixed-ish interface: note -> List[str] of atomic claims.
    mode: "llm" (default, per CONFIG) or "rule".
    """
    mode = mode or CONFIG.CLAIM_EXTRACTION_MODE
    if mode == "rule":
        return _rule_based_claims(note)

    if mode == "llm":
        backend = backend or get_backend()
        prompt = CLAIM_EXTRACTION_PROMPT.format(note=note.strip())
        raw = backend.complete(prompt, max_tokens=600, temperature=0.0)
        claims = _parse_numbered_list(raw)
        # Guard against a malformed LLM response (e.g. prose instead of a list)
        return claims if claims else _rule_based_claims(note)

    raise ValueError(f"Unknown claim extraction mode: {mode}")
