"""Map main.py generation backends to TrustNote LLM + verifier clients."""
from __future__ import annotations

from config import CONFIG
from trustnote.llm import Groq
from trustnote.models import ClaimList, Judgment, Note
from trustnote.verification import LLMVerifier, NLIVerifier


class MockTrustNoteLLM:
    """Offline stub for interactive JSON smoke tests."""

    model = "mock-trustnote"

    def __init__(self):
        self.calls = []

    def ask(self, system, data, schema):
        if schema is ClaimList:
            block = data.get("numbered_sentences") or data.get("source_sentence", "")
            parts = [p.strip() for p in str(block).split("\n") if p.strip()]
            if not parts:
                parts = [str(block)]
            return ClaimList(claims=[{"text": p.split(": ", 1)[-1] if ": " in p else p} for p in parts[:5]])
        if schema is Judgment:
            return Judgment(label="Supported", evidence_ids=[data["evidence"][0]["id"]], rationale="Mock verifier.")
        transcript = data.get("transcript", "")
        return Note(
            Subjective=[s.strip() for s in transcript.split(".")[:2] if s.strip()],
            Objective=[],
            Assessment=["Based on reported symptoms."],
            Plan=["Follow up as clinically indicated."],
        )


def make_trustnote_llm(gen_backend: str):
    if gen_backend == "groq":
        interval = max(8.0, float(CONFIG.GROQ_REQUEST_INTERVAL))
        return Groq(
            CONFIG.GROQ_MODEL,
            max_output=max(4096, int(CONFIG.GEN_MAX_NEW_TOKENS)),
            interval=min(60.0, interval),
        )
    if gen_backend == "mock":
        return MockTrustNoteLLM()
    raise ValueError(
        f"Interactive dashboard JSON requires --gen-backend groq or mock (got {gen_backend}). "
        "Anthropic/local_hf batch mode is still available via --csv."
    )


def make_trustnote_clients(gen_backend: str, verify_mode: str):
    llm = make_trustnote_llm(gen_backend)
    if verify_mode == "nli":
        verifier = NLIVerifier()
    else:
        verifier = LLMVerifier(llm)
    return llm, verifier


def make_interactive_verifier(gen_backend: str, verify_mode: str):
    """Prefer local NLI (no per-claim API calls); fall back to LLM verifier."""
    import sys

    if gen_backend == "mock" or verify_mode == "llm":
        return LLMVerifier(make_trustnote_llm(gen_backend))
    try:
        return NLIVerifier()
    except Exception as exc:
        print(
            f"[trustnote] Local NLI verifier unavailable ({exc}). "
            "Using LLM verifier — slower. Install `.[ml]` and download the NLI model, or pass --verify-mode llm.",
            file=sys.stderr,
        )
        return LLMVerifier(make_trustnote_llm(gen_backend))
