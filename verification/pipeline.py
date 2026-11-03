"""
Fixed interface (per the project plan):
    verify_note(note: str, transcript: str) -> dict

This is the module Member 3 wires into the (future) dashboard, and the
module Member 1 doesn't need to know the internals of — only this file's
public function.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Optional

from config import CONFIG
from verification.claim_extraction import extract_claims
from verification.evidence_retrieval import (
    EvidenceRetriever,
    EvidenceSpan,
    KeywordEvidenceRetriever,
)
from verification.verify import NLIVerifier, LLMVerifier, VerificationResult


@dataclass
class VerifiedClaim:
    claim: str
    label: str
    confidence: float
    rationale: str
    evidence: List[str]


def _default_retriever(use_embeddings: bool = True):
    if use_embeddings:
        try:
            return EvidenceRetriever()
        except Exception as e:  # e.g. sentence-transformers/model not available
            print(f"[trustnote] Falling back to keyword retriever: {e}")
    return KeywordEvidenceRetriever()


def verify_note(
    note: str,
    transcript: str,
    retriever=None,
    verifier=None,
    claim_mode: Optional[str] = None,
    claim_backend=None,
) -> dict:
    """
    Runs: note -> claims -> evidence -> verification, and returns a
    JSON-serializable dict:

    {
      "claims": [
        {"claim": ..., "label": ..., "confidence": ..., "rationale": ..., "evidence": [...]},
        ...
      ],
      "summary": {
        "total_claims": int,
        "supported": int,
        "contradicted": int,
        "unverifiable": int,
        "unsupported_claim_rate": float   # (contradicted + unverifiable) / total
      }
    }
    """
    retriever = retriever or _default_retriever()
    verifier = verifier or (NLIVerifier() if CONFIG.VERIFY_MODE == "nli" else LLMVerifier())

    claims = extract_claims(note, mode=claim_mode, backend=claim_backend)
    verified: List[VerifiedClaim] = []

    for claim in claims:
        evidence: List[EvidenceSpan] = retriever.retrieve(claim, transcript)
        result: VerificationResult = verifier.verify(claim, evidence)
        verified.append(
            VerifiedClaim(
                claim=claim,
                label=result.label,
                confidence=result.confidence,
                rationale=result.rationale,
                evidence=[e.text for e in evidence],
            )
        )

    total = len(verified)
    supported = sum(1 for c in verified if c.label == "Supported")
    contradicted = sum(1 for c in verified if c.label == "Contradicted")
    unverifiable = sum(1 for c in verified if c.label == "Unverifiable")
    unsupported_rate = (contradicted + unverifiable) / total if total else 0.0

    return {
        "claims": [asdict(c) for c in verified],
        "summary": {
            "total_claims": total,
            "supported": supported,
            "contradicted": contradicted,
            "unverifiable": unverifiable,
            "unsupported_claim_rate": round(unsupported_rate, 4),
        },
    }
