"""
Member 2's module, stage 2: claim -> supporting transcript evidence.

Inspired by VERISCORE's retrieval stage, but the evidence source is the
doctor-patient transcript instead of Wikipedia/web search.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from config import CONFIG


@dataclass
class EvidenceSpan:
    text: str
    score: float


def split_transcript(transcript: str) -> List[str]:
    """
    Split a transcript into retrieval units. Handles the common
    "Doctor: ..." / "Patient: ..." turn format, and falls back to sentence
    splitting for plain-text transcripts.
    """
    turns = re.findall(r"^[^\n:]{1,20}:\s*.+$", transcript, flags=re.MULTILINE)
    if len(turns) >= 2:
        return [t.strip() for t in turns if t.strip()]
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", transcript) if s.strip()]


class EvidenceRetriever:
    """
    Wraps a sentence-embedding model. Instantiate once and reuse across many
    claims/examples — loading the embedding model is the expensive part.
    """

    def __init__(self, model_name: str | None = None):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name or CONFIG.EMBEDDING_MODEL)

    def retrieve(
        self, claim: str, transcript: str, top_k: int | None = None
    ) -> List[EvidenceSpan]:
        import numpy as np

        top_k = top_k or CONFIG.TOP_K_EVIDENCE
        spans = split_transcript(transcript)
        if not spans:
            return []

        claim_emb = self.model.encode([claim], normalize_embeddings=True)[0]
        span_embs = self.model.encode(spans, normalize_embeddings=True)
        scores = span_embs @ claim_emb  # cosine similarity (embeddings are normalized)

        ranked = sorted(zip(spans, scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [EvidenceSpan(text=s, score=float(sc)) for s, sc in ranked]


class KeywordEvidenceRetriever:
    """
    No-dependency fallback (no sentence-transformers / model download needed):
    ranks transcript spans by token overlap with the claim. Weaker than
    embedding retrieval but useful for quick offline tests.
    """

    def retrieve(
        self, claim: str, transcript: str, top_k: int | None = None
    ) -> List[EvidenceSpan]:
        top_k = top_k or CONFIG.TOP_K_EVIDENCE
        claim_tokens = set(re.findall(r"[a-z]+", claim.lower()))
        spans = split_transcript(transcript)

        scored = []
        for span in spans:
            span_tokens = set(re.findall(r"[a-z]+", span.lower()))
            if not span_tokens:
                continue
            overlap = len(claim_tokens & span_tokens) / len(claim_tokens | span_tokens)
            scored.append((span, overlap))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [EvidenceSpan(text=s, score=sc) for s, sc in scored[:top_k]]
