"""Shared interactive SOAP + claims pipeline (terminal and web API)."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any

from trustnote.generation import generate_note as trustnote_generate_note
from trustnote.models import Claim, ClaimList, Note
from trustnote.retrieval import Retriever
from trustnote_adapters import make_interactive_verifier, make_trustnote_llm
from session_dashboard import build_interactive_session

SOAP_SECTIONS = ("Subjective", "Objective", "Assessment", "Plan")

SECTION_EXTRACTION = """Decompose all numbered clinical note sentences in this SOAP section into atomic clinical claims.
Every clinical fact must be covered, including negations. Preserve subject, negation, timing, doses, and units.
Do not add facts. Each claim must stand alone. Use only the numbered sentences provided."""


@dataclass
class PipelineOptions:
    gen_backend: str = "groq"
    verify_mode: str = "nli"
    dense: bool = False
    soap_only: bool = False
    top_k: int = 3
    radius: int = 1


def _split_soap_sections(note: str) -> dict[str, str]:
    text = note.strip()
    pattern = re.compile(
        r"(?im)(?:^|\n)\s*(?:#+\s*)?"
        r"(Subjective|Objective|Assessment|Plan)\s*:\s*"
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return {}
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        name = match.group(1).strip().capitalize()
        if name.lower() == "subjective":
            name = "Subjective"
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


def _body_to_bullets(body: str) -> list[str]:
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    bullets: list[str] = []
    for ln in lines:
        ln = re.sub(r"^[-*•]\s+", "", ln)
        ln = re.sub(r"^\d+[.)]\s+", "", ln)
        if ln:
            bullets.append(ln)
    if not bullets and body.strip():
        bullets = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body.strip()) if s.strip()]
    return bullets


def format_clinical_note(note: str) -> str:
    sections = _split_soap_sections(note)
    width = 72
    bar = "=" * width
    thin = "-" * width
    out: list[str] = ["", bar, "  CLINICAL NOTE (SOAP)", bar, ""]
    if sections:
        for title in SOAP_SECTIONS:
            body = sections.get(title, "").strip()
            out.append(title.upper())
            out.append(thin)
            if body:
                for item in _body_to_bullets(body):
                    out.append(f"  • {item}")
            else:
                out.append("  • (No information documented in this section.)")
            out.append("")
    else:
        out.append(note.strip())
        out.append("")
    out.extend([bar, "  Draft for clinician review — verify before use in care.", bar, ""])
    return "\n".join(out)


def extract_and_verify_claims(
    transcript: str,
    note: Note,
    llm,
    verifier,
    *,
    dense: bool,
    top_k: int,
    radius: int,
    echo: bool = True,
) -> list[dict]:
    retriever = Retriever(transcript, dense=dense, radius=radius)
    verified_rows: list[dict] = []
    claim_num = 0

    if echo:
        print()
        print("=" * 72)
        print("  ATOMIC CLAIMS")
        print("=" * 72)
        print()

    for section, sentences in note.model_dump().items():
        active = [s.strip() for s in sentences if s.strip()]
        if not active:
            continue
        numbered = "\n".join(f"{i}: {s}" for i, s in enumerate(active))
        extracted = llm.ask(
            SECTION_EXTRACTION,
            {
                "section": section,
                "numbered_sentences": numbered,
                "note_context": {section: active},
            },
            ClaimList,
        )
        for item in extracted.claims:
            claim_num += 1
            claim = Claim(
                id=f"C{claim_num:04}",
                section=section,
                source_index=0,
                source_text=active[0],
                text=item.text,
            )
            evidence = retriever.retrieve(claim.text, top_k)
            result = verifier.verify(claim, evidence)
            ev_text = ""
            if getattr(result, "evidence", None):
                ev_text = (result.evidence[0].text or "").strip()
            flags: list[str] = list(getattr(result, "flags", None) or [])
            row = {
                "id": claim.id,
                "section": section,
                "label": result.label,
                "text": claim.text,
                "rationale": getattr(result, "rationale", "") or "",
                "evidence": ev_text,
                "flags": flags,
            }
            verified_rows.append(row)
            if echo:
                print(f"  [{result.label}] {claim.text}", flush=True)
    return verified_rows


def run_interactive_pipeline(
    transcript: str,
    options: PipelineOptions,
    *,
    meta: dict[str, Any] | None = None,
    echo: bool = True,
) -> dict[str, Any]:
    """Run SOAP + claims; print to terminal when echo=True. Returns dashboard session dict."""
    transcript = transcript.strip()
    if not transcript:
        raise ValueError("Conversation text is empty.")

    if echo:
        print()
        print(f"[trustnote] Received {len(transcript):,} characters.")
        print("[Step 1/2] Generating SOAP clinical note (please wait)…", flush=True)

    llm = make_trustnote_llm(options.gen_backend)
    verifier = make_interactive_verifier(options.gen_backend, options.verify_mode)

    note = trustnote_generate_note(transcript, llm)
    formatted = format_clinical_note(note.text())
    if echo:
        print(formatted)

    claims_report: list[dict] = []
    if not options.soap_only:
        if echo:
            print("[Step 2/2] Extracting and tagging claims…", flush=True)
        claims_report = extract_and_verify_claims(
            transcript,
            note,
            llm,
            verifier,
            dense=options.dense,
            top_k=options.top_k,
            radius=options.radius,
            echo=echo,
        )
        if echo:
            print()

    dashboard = build_interactive_session(
        transcript,
        note.model_dump(),
        claims_report,
        formatted_note=formatted,
        meta=meta,
    )
    dashboard["transcriptRaw"] = transcript
    return dashboard
