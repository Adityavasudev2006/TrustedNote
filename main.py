"""
End-to-end runner (ASR and dashboard skipped, per current scope):

    Transcript -> generate_note() -> verify_note() -> verified note + metrics

Usage:
    python main.py
        Interactive: paste/type the conversation, then END on its own line.

    python main.py --csv data/aci-bench/valid.csv --n 20 --gen-backend anthropic --verify-mode nli
    python main.py --csv data/aci-bench/valid.csv --n 3  --gen-backend mock --verify-mode nli  # offline smoke test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import CONFIG, ENV_FILE
from data.loader import load_aci_bench
from generation.generate import generate_note, get_backend
from interactive_pipeline import PipelineOptions, format_clinical_note, run_interactive_pipeline
from verification.pipeline import verify_note
from verification.evidence_retrieval import EvidenceRetriever, KeywordEvidenceRetriever
from verification.verify import NLIVerifier, LLMVerifier
from evaluation.metrics import summarize_run
from session_store import save_session
from web_bridge import bootstrap_interactive_ui, configure_pipeline, dashboard_url, publish_live_session

END_MARKER = "END"


def read_interactive_transcript() -> str:
    print()
    print("=" * 72)
    print("  TrustNote — Doctor–patient conversation input")
    print("=" * 72)
    print()
    print("  Paste or type the full conversation (multiple paragraphs are fine).")
    print(f"  When you are done, type {END_MARKER} on its own line and press Enter.")
    print()
    print("-" * 72)

    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().upper() == END_MARKER:
            break
        lines.append(line)

    transcript = "\n".join(lines).strip()
    if not transcript:
        print("\nNo conversation text was entered. Exiting.", file=sys.stderr)
        sys.exit(1)
    return transcript


def _ensure_backend_configured(backend: str) -> None:
    if backend == "groq" and not CONFIG.GROQ_API_KEY.strip():
        print(
            f"[trustnote] GROQ_API_KEY is not set. Paste your key into:\n  {ENV_FILE}\n"
            "Then run again. Use --gen-backend mock for offline testing without an API key.",
            file=sys.stderr,
        )
        sys.exit(1)
    if backend == "anthropic" and not CONFIG.ANTHROPIC_API_KEY:
        print(
            "[trustnote] ANTHROPIC_API_KEY is not set. "
            "Add it to `.env` or use --gen-backend groq / mock.",
            file=sys.stderr,
        )
        sys.exit(1)


def run_interactive(args) -> None:
    _ensure_backend_configured(args.gen_backend)

    options = PipelineOptions(
        gen_backend=args.gen_backend,
        verify_mode=args.verify_mode,
        dense=args.dense,
        soap_only=args.soap_only,
    )
    configure_pipeline(options)

    if not getattr(args, "no_ui", False):
        ui_url = bootstrap_interactive_ui()
        print(f"[trustnote] Dashboard URL: {ui_url}", flush=True)

    transcript = read_interactive_transcript()
    dashboard = run_interactive_pipeline(transcript, options, echo=True)
    formatted = dashboard.get("formattedNote", "")

    if not getattr(args, "no_ui", False):
        save_session(dashboard, source="Terminal")
        publish_live_session(dashboard)
        print(f"[trustnote] Results are in the web dashboard: {dashboard_url()}", flush=True)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "transcript": transcript,
            "soap_note": dashboard.get("soapNote", {}),
            "formatted_note": formatted,
            "claims": dashboard.get("claims", []),
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        txt_path = out_path.with_suffix(".txt")
        txt_path.write_text(formatted, encoding="utf-8")
        print(f"Saved note to {txt_path}")
        if out_path.suffix == ".json":
            print(f"Saved full record to {out_path}")


def build_retriever(use_embeddings: bool):
    if use_embeddings:
        try:
            return EvidenceRetriever()
        except Exception as e:
            print(f"[trustnote] Embedding retriever unavailable ({e}); using keyword retriever.")
    return KeywordEvidenceRetriever()


def build_verifier(mode: str, gen_backend):
    if mode == "nli":
        return NLIVerifier()
    if mode == "llm":
        return LLMVerifier(backend=gen_backend)
    raise ValueError(mode)


def main():
    ap = argparse.ArgumentParser(
        description="Generate a SOAP clinical note from a doctor–patient conversation."
    )
    ap.add_argument(
        "--csv",
        default=None,
        help="Batch mode: path to an ACI-Bench-style CSV. Omit to enter a conversation interactively.",
    )
    ap.add_argument("--n", type=int, default=20, help="Number of examples to run (Day 5: 20-50).")
    ap.add_argument("--gen-backend", default=CONFIG.GEN_BACKEND,
                     choices=["groq", "anthropic", "local_hf", "mock"])
    ap.add_argument("--verify-mode", default=CONFIG.VERIFY_MODE, choices=["nli", "llm"])
    ap.add_argument(
        "--dense",
        action="store_true",
        help="Use semantic embedding retrieval for claims (downloads a model). Default is fast keyword retrieval.",
    )
    ap.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Batch mode only: keyword retrieval instead of embeddings.",
    )
    ap.add_argument(
        "--soap-only",
        action="store_true",
        help="Only generate and print the SOAP note (skip claim verification).",
    )
    ap.add_argument(
        "--out",
        default="results/clinical_note.json",
        help="Interactive: save JSON + .txt formatted note. Batch: full run JSON (default results/run.json).",
    )
    ap.add_argument(
        "--no-ui",
        action="store_true",
        help="Interactive only: do not start the web dashboard or open a browser.",
    )
    args = ap.parse_args()

    if args.csv is None:
        run_interactive(args)
        return

    _ensure_backend_configured(args.gen_backend)

    if args.out == "results/clinical_note.json":
        args.out = "results/run.json"

    examples = load_aci_bench(args.csv, limit=args.n)
    print(f"[trustnote] Loaded {len(examples)} examples from {args.csv}")

    gen_backend = get_backend(args.gen_backend)
    retriever = build_retriever(use_embeddings=not args.no_embeddings)
    verifier = build_verifier(args.verify_mode, gen_backend)

    generated_notes, references, verify_results, per_example = [], [], [], []

    for ex in examples:
        note = generate_note(ex.transcript, backend=gen_backend)
        vresult = verify_note(
            note, ex.transcript, retriever=retriever, verifier=verifier,
            claim_backend=gen_backend,
        )

        generated_notes.append(note)
        references.append(ex.note)
        verify_results.append(vresult)
        per_example.append({
            "id": ex.id,
            "transcript": ex.transcript,
            "reference_note": ex.note,
            "generated_note": note,
            "verification": vresult,
        })
        rate = vresult["summary"]["unsupported_claim_rate"]
        print(f"  [{ex.id}] {vresult['summary']['total_claims']} claims, "
              f"unsupported rate={rate:.2%}")

    summary = summarize_run(references, generated_notes, verify_results)
    print("\n=== Preliminary results (Review 1 & 2 table) ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"summary": summary, "examples": per_example}, indent=2))
    print(f"\nSaved full results to {out_path}")


if __name__ == "__main__":
    main()
