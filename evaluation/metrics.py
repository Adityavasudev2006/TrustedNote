"""
Metrics for both generation quality (vs. reference note) and verification
quality (from a verify_note() output). Matches the "Expected Preliminary
Results" table in the project plan.
"""
from __future__ import annotations

from typing import Dict, List


def rouge_l(reference: str, hypothesis: str) -> float:
    from rouge_score import rouge_scorer

    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    return scorer.score(reference, hypothesis)["rougeL"].fmeasure


def bertscore_f1(references: List[str], hypotheses: List[str]) -> float:
    """Batched — much faster than calling per-example (loads the model once)."""
    from bert_score import score as bert_score_fn

    _, _, f1 = bert_score_fn(hypotheses, references, lang="en", verbose=False)
    return float(f1.mean())


def clinical_entity_f1(reference: str, hypothesis: str, nlp=None) -> float:
    """
    Approximate clinical entity overlap using spaCy's generic NER as a stand-in
    for a clinical NER model (scispacy would be more accurate but is a heavier
    dependency — swap in `en_core_sci_sm` here if you install it later).
    """
    if nlp is None:
        import spacy

        nlp = spacy.load("en_core_web_sm")

    ref_ents = {ent.text.lower() for ent in nlp(reference).ents}
    hyp_ents = {ent.text.lower() for ent in nlp(hypothesis).ents}

    if not ref_ents and not hyp_ents:
        return 1.0
    if not hyp_ents or not ref_ents:
        return 0.0

    overlap = ref_ents & hyp_ents
    precision = len(overlap) / len(hyp_ents)
    recall = len(overlap) / len(ref_ents)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def unsupported_claim_rate(verify_result: dict) -> float:
    """Convenience passthrough — the pipeline already computes this."""
    return verify_result["summary"]["unsupported_claim_rate"]


def summarize_run(
    references: List[str],
    hypotheses: List[str],
    verify_results: List[dict],
) -> Dict:
    """
    Produces the "Actual result" row for the plan's Review-1/2 table:
    ROUGE-L, BERTScore, and aggregate claim-verification counts.
    """
    rouge_scores = [rouge_l(r, h) for r, h in zip(references, hypotheses)]
    bert_f1 = bertscore_f1(references, hypotheses) if references and hypotheses else 0.0

    total = sum(v["summary"]["total_claims"] for v in verify_results)
    supported = sum(v["summary"]["supported"] for v in verify_results)
    contradicted = sum(v["summary"]["contradicted"] for v in verify_results)
    unverifiable = sum(v["summary"]["unverifiable"] for v in verify_results)

    return {
        "rouge_l": round(sum(rouge_scores) / len(rouge_scores), 4) if rouge_scores else 0.0,
        "bertscore_f1": round(bert_f1, 4),
        "total_claims": total,
        "supported": supported,
        "contradicted": contradicted,
        "unverifiable": unverifiable,
        "unsupported_claim_rate": round((contradicted + unverifiable) / total, 4) if total else 0.0,
    }
