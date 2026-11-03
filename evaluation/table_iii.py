"""
Build Table III (baseline vs TrustNote) from trustnote batch outputs.

Expects:
  outputs/<run>/summary.json   (from: python -m trustnote batch ... --quality --bertscore)
  outputs/<run>/case-NNNN/report.json

Usage:
  python evaluation/table_iii.py outputs/metrics_eval
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trustnote.evaluation import quality
from trustnote.models import Note


def note_text(note_dict: dict) -> str:
    return "\n".join(x for v in note_dict.values() for x in v)


def claim_stats(report: dict) -> dict:
    retained_ids = {
        cid
        for d in report["sentence_decisions"]
        if d["retained"]
        for cid in d["claim_ids"]
    }
    retained = [c for c in report["claims"] if c["claim"]["id"] in retained_ids]
    if retained:
        unsupported = sum(1 for c in retained if c["label"] != "Supported") / len(retained)
    else:
        unsupported = None
    return {
        "extracted_claims": report["metrics"]["total_claims"],
        "retained_claims": len(retained),
        "unsupported_rate_all_extracted": report["metrics"]["model_estimated_unsupported_claim_rate"],
        "unsupported_rate_retained_only": unsupported,
        "sentence_retention": report["metrics"]["sentence_retention_rate"],
    }


def aggregate_run(run_dir: Path, references: dict[str, str], bertscore: bool) -> dict:
    summary_path = run_dir / "summary.json"
    cases = sorted(run_dir.glob("case-*/report.json"))
    if summary_path.exists():
        entries = json.loads(summary_path.read_text(encoding="utf-8"))
    elif cases:
        entries = []
        for i, case_path in enumerate(cases, 1):
            report = json.loads(case_path.read_text(encoding="utf-8"))
            entry = {"id": report.get("dataset_record", {}).get("id", f"case-{i}"), **report["metrics"]}
            ref = references.get(entry["id"])
            if ref:
                for arm, key in [("baseline", "original_note"), ("filtered", "filtered_note")]:
                    entry[arm] = quality(ref, note_text(report[key]), bertscore=bertscore)
            entries.append(entry)
    else:
        raise FileNotFoundError(f"No summary.json or case-*/report.json under {run_dir}")

    rouge_b, rouge_t = [], []
    bert_b, bert_t = [], []
    claims_b, claims_t = [], []
    unsup_b, unsup_t = [], []
    sent_ret = []

    for entry in entries:
        rid = entry["id"]
        case_idx = entries.index(entry) + 1
        report_path = run_dir / f"case-{case_idx:04}" / "report.json"
        if report_path.exists():
            stats = claim_stats(json.loads(report_path.read_text(encoding="utf-8")))
            claims_b.append(stats["extracted_claims"])
            claims_t.append(stats["retained_claims"])
            unsup_b.append(stats["unsupported_rate_all_extracted"])
            u = stats["unsupported_rate_retained_only"]
            unsup_t.append(u if u is not None else 0.0)
            sent_ret.append(stats["sentence_retention"])
        if "baseline" in entry:
            rouge_b.append(entry["baseline"]["rougeL_f1"])
            if bertscore and "bertscore_f1" in entry["baseline"]:
                bert_b.append(entry["baseline"]["bertscore_f1"])
        if "filtered" in entry:
            rouge_t.append(entry["filtered"]["rougeL_f1"])
            if bertscore and "bertscore_f1" in entry["filtered"]:
                bert_t.append(entry["filtered"]["bertscore_f1"])

    def avg(xs):
        return sum(xs) / len(xs) if xs else None

    return {
        "n_encounters": len(entries),
        "encounter_ids": [e["id"] for e in entries],
        "rouge_l_f_baseline": avg(rouge_b),
        "rouge_l_f_trustnote": avg(rouge_t),
        "bertscore_f1_baseline": avg(bert_b) if bertscore else None,
        "bertscore_f1_trustnote": avg(bert_t) if bertscore else None,
        "claims_baseline_mean": avg(claims_b),
        "claims_trustnote_mean": avg(claims_t),
        "unsupported_baseline_mean": avg(unsup_b),
        "unsupported_trustnote_mean": avg(unsup_t),
        "sentence_retention_baseline": 1.0,
        "sentence_retention_trustnote": avg(sent_ret),
    }


def load_references(jsonl: Path) -> dict[str, str]:
    out = {}
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row["id"]] = row["reference_note"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--data", type=Path, default=Path("data/prepared/valid.jsonl"))
    ap.add_argument("--bertscore", action="store_true")
    args = ap.parse_args()
    refs = load_references(args.data) if args.data.exists() else {}
    try:
        agg = aggregate_run(args.run_dir, refs, args.bertscore)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    print(json.dumps(agg, indent=2))


if __name__ == "__main__":
    main()
