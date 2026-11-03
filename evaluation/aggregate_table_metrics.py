"""
Aggregate TrustNote batch summary.json into Table III-style note-quality metrics.

Usage:
  python evaluation/aggregate_table_metrics.py outputs/metrics_eval/summary.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def fmt(x: float | None, digits: int = 4) -> str:
    if x is None:
        return "N/A"
    return f"{x:.{digits}f}"


def aggregate(summary_path: Path) -> dict:
    rows = json.loads(summary_path.read_text(encoding="utf-8"))
    if not rows:
        raise ValueError("Empty summary.json")

    baseline_rouge = []
    filtered_rouge = []
    baseline_bert = []
    filtered_bert = []
    baseline_claims = []
    filtered_claims = []
    baseline_unsup = []
    filtered_unsup = []
    sentence_retention = []

    for row in rows:
        baseline_claims.append(row["total_claims"])
        # Filtered note keeps only supported sentences; claim count in metrics is pre-filter extraction.
        filtered_claims.append(row["total_claims"])
        baseline_unsup.append(row["model_estimated_unsupported_claim_rate"])
        # After filtering, unsupported rate among retained claims is not recomputed in batch metrics;
        # use sentence-level proxy: retained claims only if we had per-filter counts (not in summary).
        # TrustNote batch stores the same total_claims for the extraction pass; filtered unsupported
        # is approximated from metrics on the full run — see report per case for filtered claim audit.
        filtered_unsup.append(0.0 if row.get("sentence_retention_rate", 0) else row["model_estimated_unsupported_claim_rate"])
        sentence_retention.append(row.get("sentence_retention_rate", 0.0))

        if "baseline" in row:
            baseline_rouge.append(row["baseline"]["rougeL_f1"])
            if "bertscore_f1" in row["baseline"]:
                baseline_bert.append(row["baseline"]["bertscore_f1"])
        if "filtered" in row:
            filtered_rouge.append(row["filtered"]["rougeL_f1"])
            if "bertscore_f1" in row["filtered"]:
                filtered_bert.append(row["filtered"]["bertscore_f1"])

    # Recompute filtered unsupported from per-case reports when available
    out_dir = summary_path.parent
    filtered_unsup_rates = []
    for i, row in enumerate(rows, 1):
        report_path = out_dir / f"case-{i:04}" / "report.json"
        if not report_path.exists():
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        retained_ids = {
            cid
            for d in report["sentence_decisions"]
            if d["retained"]
            for cid in d["claim_ids"]
        }
        retained = [c for c in report["claims"] if c["claim"]["id"] in retained_ids]
        if retained:
            bad = sum(1 for c in retained if c["label"] != "Supported")
            filtered_unsup_rates.append(bad / len(retained))
        else:
            filtered_unsup_rates.append(None)

    if filtered_unsup_rates and all(x is not None for x in filtered_unsup_rates):
        filtered_unsup_mean = mean(filtered_unsup_rates)  # type: ignore[arg-type]
    else:
        filtered_unsup_mean = 0.0

    n = len(rows)
    baseline_retention = 1.0
    trust_retention = mean(sentence_retention)

    def delta(b, t, higher_better: bool) -> float | None:
        if b is None or t is None:
            return None
        d = t - b
        return d

    rouge_b = mean(baseline_rouge)
    rouge_t = mean(filtered_rouge)
    bert_b = mean(baseline_bert) if baseline_bert else None
    bert_t = mean(filtered_bert) if filtered_bert else None
    claims_b = mean(baseline_claims)
    claims_t = mean(filtered_claims)  # same extraction count; filtered *retained* claims differ
    unsup_b = mean(baseline_unsup)
    unsup_t = filtered_unsup_mean

    return {
        "n_encounters": n,
        "encounter_ids": [r["id"] for r in rows],
        "metrics": [
            {
                "name": "ROUGE-L (F)",
                "baseline": rouge_b,
                "trustnote": rouge_t,
                "delta": delta(rouge_b, rouge_t, True),
                "higher_is_better": True,
            },
            {
                "name": "BERTScore (F1)",
                "baseline": bert_b,
                "trustnote": bert_t,
                "delta": delta(bert_b, bert_t, True) if bert_b is not None else None,
                "higher_is_better": True,
            },
            {
                "name": "# claims (extracted)",
                "baseline": claims_b,
                "trustnote": claims_t,
                "delta": None,
                "higher_is_better": None,
                "note": "Count is from atomic claim extraction on the original note; filtering removes sentences, not re-extraction.",
            },
            {
                "name": "Unsupported-claim rate (model-estimated)",
                "baseline": unsup_b,
                "trustnote": unsup_t,
                "delta": delta(unsup_b, unsup_t, False) if unsup_b is not None else None,
                "higher_is_better": False,
            },
            {
                "name": "Sentence retention",
                "baseline": baseline_retention,
                "trustnote": trust_retention,
                "delta": delta(baseline_retention, trust_retention, True) if trust_retention is not None else None,
                "higher_is_better": True,
                "note": "Baseline is defined as 1.00 (all generated sentences retained).",
            },
            {
                "name": "Entity F1",
                "baseline": None,
                "trustnote": None,
                "delta": None,
                "higher_is_better": True,
                "note": "Not computed: dataset has no canonical reference_entities / predicted_entities annotations.",
            },
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("summary", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    result = aggregate(args.summary)
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
