"""
Member 2's module, stage 3: (claim, evidence) -> Supported / Contradicted / Unverifiable.

Two interchangeable verifiers:
  - NLIVerifier: local entailment model. This is the practical stand-in for
    AlignScore's "unified alignment function" — same idea (does the evidence
    entail the claim?), implemented with an off-the-shelf NLI checkpoint
    since AlignScore's own trained weights aren't something we can bundle.
  - LLMVerifier: Claude-as-judge, closer to VERISCORE's verification stage.
    Slower and costs API calls, but tends to handle clinical nuance
    (negation, hedging, "maybe") better than a generic NLI model — which
    matters, per the "Fact-Controlled Diagnosis of Hallucinations in
    Medical Text" (2025) finding that general-domain detectors underperform
    on clinical hallucinations.

Both return the SAME three labels so the rest of the pipeline doesn't care
which one produced them.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List

from config import CONFIG
from generation.generate import LLMBackend, get_backend
from verification.evidence_retrieval import EvidenceSpan

LABELS = ("Supported", "Contradicted", "Unverifiable")


@dataclass
class VerificationResult:
    label: str          # one of LABELS
    confidence: float
    rationale: str = ""


class NLIVerifier:
    """
    Local, fast, no API cost. Loaded lazily — importing this file doesn't
    require the model weights unless you instantiate this class.
    """

    def __init__(self, model_name: str | None = None):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        import torch

        self.model_name = model_name or CONFIG.NLI_MODEL
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        self.model.eval()
        self._torch = torch
        # MoritzLaurer's mnli-fever-anli checkpoints use label order
        # 0: entailment, 1: neutral, 2: contradiction — verified via model.config.id2label
        self.id2label = {v.lower(): k for k, v in self.model.config.id2label.items()}

    def verify(self, claim: str, evidence: List[EvidenceSpan]) -> VerificationResult:
        if not evidence:
            return VerificationResult("Unverifiable", 1.0, "No evidence retrieved.")

        premise = " ".join(e.text for e in evidence)
        inputs = self.tokenizer(premise, claim, return_tensors="pt", truncation=True)
        with self._torch.no_grad():
            logits = self.model(**inputs).logits[0]
        probs = self._torch.softmax(logits, dim=-1).tolist()

        entail_p = probs[self.id2label.get("entailment", 0)]
        contra_p = probs[self.id2label.get("contradiction", 2)]

        if contra_p >= CONFIG.NLI_CONTRADICT_THRESHOLD:
            return VerificationResult("Contradicted", contra_p,
                                       "Transcript evidence conflicts with this claim.")
        if entail_p >= CONFIG.NLI_ENTAIL_THRESHOLD:
            return VerificationResult("Supported", entail_p,
                                       "Transcript evidence entails this claim.")
        return VerificationResult("Unverifiable", max(entail_p, contra_p),
                                   "No adequate entailment or contradiction found.")


VERIFY_PROMPT = """You are checking a clinical note claim against a doctor-patient \
transcript for a hallucination-detection system.

Claim:
"{claim}"

Relevant transcript evidence:
\"\"\"
{evidence}
\"\"\"

Classify the claim as exactly one of: Supported, Contradicted, Unverifiable.
- Supported: the evidence adequately confirms the claim.
- Contradicted: the evidence conflicts with the claim.
- Unverifiable: the claim is plausible but the evidence does not confirm or deny it \
(e.g. it is not mentioned).

Respond ONLY as JSON: {{"label": "...", "rationale": "..."}}
"""


class LLMVerifier:
    def __init__(self, backend: LLMBackend | None = None):
        self.backend = backend or get_backend()

    def verify(self, claim: str, evidence: List[EvidenceSpan]) -> VerificationResult:
        if not evidence:
            return VerificationResult("Unverifiable", 1.0, "No evidence retrieved.")

        evidence_text = "\n".join(f"- {e.text}" for e in evidence)
        prompt = VERIFY_PROMPT.format(claim=claim, evidence=evidence_text)
        raw = self.backend.complete(prompt, max_tokens=200, temperature=0.0)

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                label = parsed.get("label", "Unverifiable")
                if label not in LABELS:
                    label = "Unverifiable"
                return VerificationResult(label, 1.0, parsed.get("rationale", ""))
            except json.JSONDecodeError:
                pass
        return VerificationResult("Unverifiable", 0.0, f"Could not parse verifier output: {raw!r}")


def get_verifier(mode: str | None = None):
    mode = mode or CONFIG.VERIFY_MODE
    if mode == "nli":
        return NLIVerifier()
    if mode == "llm":
        return LLMVerifier()
    raise ValueError(f"Unknown verify mode: {mode}")
