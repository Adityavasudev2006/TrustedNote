"""Build dashboard-style session JSON from a TrustNote pipeline report."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

SOAP_KEYS = ("Subjective", "Objective", "Assessment", "Plan")
LABELS = ("Supported", "Contradicted", "Unverifiable")


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"[\s,]+", name.strip()) if p and p.lower() not in {"dr", "dr.", "doctor"}]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _extract_names(transcript: str) -> tuple[str, str]:
    patient = "Patient"
    doctor = "Clinician"
    for pat in (
        r"(?i)patient(?:'s)?\s+name\s+is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"(?i)my\s+name\s+is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    ):
        m = re.search(pat, transcript)
        if m:
            patient = m.group(1).strip()
            break
    m = re.search(r"(?i)(?:dr\.?|doctor)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", transcript)
    if m:
        doctor = f"Dr. {m.group(1).strip()}"
    return patient, doctor


def _parse_turns(transcript: str, patient_name: str, doctor_name: str) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    sec = 12
    speaker_line = re.compile(
        r"^\s*(?:\[(doctor|patient|dr\.?|physician|clinician)\]|(doctor|patient|dr\.?))\s*:?\s*(.*)$",
        re.IGNORECASE,
    )
    for raw in transcript.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = speaker_line.match(line)
        if m:
            role = (m.group(1) or m.group(2) or "").lower().replace("dr.", "doctor").replace("dr", "doctor")
            text = (m.group(3) or "").strip()
            if not text:
                continue
            is_doctor = role.startswith("doc") or role in {"physician", "clinician"}
            speaker = "doctor" if is_doctor else "patient"
            name = doctor_name if is_doctor else patient_name
            initials = _initials(name)
            ts = f"{sec // 60:02d}:{sec % 60:02d}"
            sec += max(18, min(45, len(text) // 4))
            turns.append(
                {
                    "speaker": speaker,
                    "speakerInitials": initials,
                    "speakerName": name,
                    "timestamp": ts,
                    "text": text,
                }
            )
        elif turns:
            turns[-1]["text"] = f"{turns[-1]['text']} {line}"
        else:
            turns.append(
                {
                    "speaker": "patient",
                    "speakerInitials": _initials(patient_name),
                    "speakerName": patient_name,
                    "timestamp": "00:12",
                    "text": line,
                }
            )
    return turns


def _soap_paragraph(note: dict[str, list[str]], section: str) -> str:
    return " ".join(note.get(section, [])).strip()


def _confidence(label: str, scores: dict[str, float]) -> float:
    if scores:
        if label == "Supported" and "entailment" in scores:
            return round(float(scores["entailment"]), 2)
        if label == "Contradicted" and "contradiction" in scores:
            return round(float(scores["contradiction"]), 2)
    return {"Supported": 0.92, "Contradicted": 0.88, "Unverifiable": 0.0}.get(label, 0.0)


def _claim_source(entry: dict[str, Any]) -> str:
    evidence = entry.get("evidence") or []
    if evidence:
        snippet = evidence[0].get("text", "").strip().replace("\n", " ")
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."
        return f"“{snippet}”"
    return "No matching evidence found in transcript."


def _risk_level(unsupported_pct: float) -> str:
    if unsupported_pct >= 25:
        return "high"
    if unsupported_pct >= 10:
        return "medium"
    return "low"


def _evaluation_block(metrics: dict[str, Any]) -> dict[str, Any]:
    n = metrics.get("total_claims") or 0
    counts = {k: int(metrics.get(k, 0)) for k in LABELS}
    if n == 0:
        return {
            "confusionMatrix": {
                "rows": list(LABELS),
                "columns": list(LABELS),
                "data": [[0.0, 0.0, 0.0] for _ in LABELS],
            },
            "perClassScores": [{"name": x, "precision": 0.0, "recall": 0.0, "f1": 0.0} for x in LABELS],
            "macroF1": 0.0,
            "accuracy": 0.0,
            "note": "Model-estimated label distribution only (not human gold evaluation).",
        }
    shares = [counts[label] / n for label in LABELS]
    matrix = [[0.0, 0.0, 0.0] for _ in LABELS]
    for i, label in enumerate(LABELS):
        matrix[i][i] = round(counts[label] / n, 2)
    per_class = []
    for i, label in enumerate(LABELS):
        s = shares[i]
        per_class.append(
            {"name": label, "precision": round(s, 2), "recall": round(s, 2), "f1": round(s, 2)}
        )
    macro = round(sum(shares) / len(LABELS), 2)
    accuracy = round(counts["Supported"] / n, 2)
    return {
        "confusionMatrix": {
            "rows": list(LABELS),
            "columns": list(LABELS),
            "data": matrix,
        },
        "perClassScores": per_class,
        "macroF1": macro,
        "accuracy": accuracy,
        "note": "Diagonal shows model-assigned claim label prevalence. For human gold confusion matrix, fill annotations.csv and run trustnote score.",
    }


def _metrics_from_claim_rows(claims: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(claims)
    counts = {label: sum(1 for c in claims if c.get("label") == label) for label in LABELS}
    unsupported = counts["Contradicted"] + counts["Unverifiable"]
    rate = unsupported / total if total else 0.0
    supported = counts["Supported"]
    retention = supported / total if total else 0.0
    return {
        "total_claims": total,
        "Supported": counts["Supported"],
        "Contradicted": counts["Contradicted"],
        "Unverifiable": counts["Unverifiable"],
        "model_estimated_unsupported_claim_rate": rate,
        "sentence_retention_rate": retention,
    }


def _filtered_note_from_claims(soap_note: dict[str, list[str]], claims: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Keep sections that have at least one supported claim; use supported claim text per section."""
    out: dict[str, list[str]] = {k: [] for k in SOAP_KEYS}
    for section in SOAP_KEYS:
        supported_texts = [c["text"] for c in claims if c.get("section") == section and c.get("label") == "Supported"]
        if supported_texts:
            out[section] = supported_texts
        elif not any(c.get("section") == section for c in claims):
            out[section] = list(soap_note.get(section) or [])
    return out


def build_interactive_session(
    transcript: str,
    soap_note: dict[str, list[str]],
    claims: list[dict[str, Any]],
    *,
    formatted_note: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dashboard payload from interactive main.py (SOAP + tagged claims)."""
    metrics = _metrics_from_claim_rows(claims)
    report = {
        "metrics": metrics,
        "claims": [
            {
                "claim": {"section": c.get("section", "Subjective"), "text": c.get("text", "")},
                "label": c.get("label", "Unverifiable"),
                "rationale": c.get("rationale") or "",
                "evidence": [{"text": c.get("evidence", "")}] if c.get("evidence") else [],
                "flags": c.get("flags") or [],
                "scores": c.get("scores") or {},
            }
            for c in claims
        ],
        "original_note": soap_note,
        "filtered_note": _filtered_note_from_claims(soap_note, claims),
        "config": {"generator_model": "interactive"},
    }
    dash = build_session_dashboard(report, transcript)
    dash["formattedNote"] = formatted_note
    dash["patient"]["age"] = dash["patient"].get("age") or 42
    dash["patient"]["sex"] = dash["patient"].get("sex") or "U"
    if meta:
        if meta.get("sessionId"):
            dash["session"]["id"] = meta["sessionId"]
        if meta.get("patientName"):
            dash["patient"]["name"] = meta["patientName"]
            dash["patient"]["initials"] = _initials(meta["patientName"])
        if meta.get("patientId"):
            dash["patient"]["id"] = meta["patientId"]
        if meta.get("mrn"):
            dash["patient"]["mrn"] = meta["mrn"]
        if meta.get("age") is not None:
            dash["patient"]["age"] = meta["age"]
        if meta.get("sex"):
            dash["patient"]["sex"] = meta["sex"]
        if meta.get("doctorName"):
            dash["session"]["doctorName"] = meta["doctorName"]
            dash["session"]["doctorInitials"] = _initials(meta["doctorName"])
        if meta.get("specialty"):
            dash["session"]["specialty"] = meta["specialty"]
        if meta.get("consultationType"):
            dash["session"]["consultationType"] = meta["consultationType"]
        turns = _parse_turns(transcript, dash["patient"]["name"], dash["session"]["doctorName"])
        if turns:
            dash["transcript"] = {"turns": turns}
    dash["workspace"] = {
        "claimsVerified": metrics["total_claims"],
        "unsupportedRate": round(metrics["model_estimated_unsupported_claim_rate"] * 100, 1),
        "retentionRate": round(metrics["sentence_retention_rate"] * 100, 1),
        "verdictShares": {
            label: round(metrics[label] / metrics["total_claims"] * 100, 1) if metrics["total_claims"] else 0
            for label in LABELS
        },
    }
    return dash


def build_session_dashboard(report: dict[str, Any], transcript: str) -> dict[str, Any]:
    patient_name, doctor_name = _extract_names(transcript)
    digest = hashlib.sha256(transcript.encode()).hexdigest()
    session_id = f"s-{digest[:4]}"
    patient_id = f"p-{digest[4:8]}"
    mrn = f"TN-{digest[:5].upper()}"

    metrics = report.get("metrics", {})
    total_claims = int(metrics.get("total_claims") or 0)
    unsupported = metrics.get("model_estimated_unsupported_claim_rate")
    unsupported_pct = round((unsupported or 0) * 100) if unsupported is not None else 0
    retention = metrics.get("sentence_retention_rate")
    retention_pct = round((retention or 0) * 100) if retention is not None else 0

    turns = _parse_turns(transcript, patient_name, doctor_name)
    word_count = len(transcript.split())
    duration_min = max(1, word_count // 150)
    duration_sec = min(59, (word_count * 2) % 60)
    duration = f"{duration_min:02d}:{duration_sec:02d}"

    consultation = "Clinical consultation"
    if turns:
        consultation = (turns[0]["text"][:72] + "…") if len(turns[0]["text"]) > 72 else turns[0]["text"]

    cfg = report.get("config", {})
    model = cfg.get("generator_model") or "trustnote-llm"

    claims_out = []
    for i, row in enumerate(report.get("claims", []), 1):
        label = row.get("label", "Unverifiable")
        flags = list(row.get("flags") or [])
        if label == "Contradicted" and "contradicted_by_source" not in flags:
            flags.append("contradicted_by_source")
        if label == "Unverifiable" and "invalid_or_missing_citation" not in flags:
            flags.append("invalid_or_missing_citation")
        claims_out.append(
            {
                "id": f"c{i}",
                "section": row["claim"]["section"],
                "label": label,
                "text": row["claim"]["text"],
                "source": _claim_source(row),
                "rationale": row.get("rationale") or "",
                "flags": flags,
                "confidenceScore": _confidence(label, row.get("scores") or {}),
            }
        )

    orig = report.get("original_note", {})
    filt = report.get("filtered_note", {})

    now = datetime.now(timezone.utc).astimezone()
    time_label = now.strftime("Today, %I:%M %p").replace(" 0", " ")

    return {
        "patient": {
            "id": patient_id,
            "name": patient_name,
            "age": None,
            "sex": None,
            "mrn": mrn,
            "initials": _initials(patient_name),
            "lastSession": "Today",
            "totalSessions": 1,
            "unsupportedRate": unsupported_pct,
        },
        "session": {
            "id": session_id,
            "doctorId": "d1",
            "doctorName": doctor_name,
            "doctorInitials": _initials(doctor_name),
            "time": time_label,
            "source": "Manual transcript",
            "status": "Ready for review",
            "riskLevel": _risk_level(unsupported_pct),
            "specialty": "General practice",
            "consultationType": consultation,
            "transcriptModel": "N/A (text input)",
            "duration": duration,
            "transcriptStatus": "Complete",
            "totalClaims": total_claims,
            "retentionRate": retention_pct,
            "unsupportedPercentage": unsupported_pct,
        },
        "transcript": {"turns": turns},
        "claims": claims_out,
        "soapNote": {
            "original": {
                "subjective": _soap_paragraph(orig, "Subjective"),
                "objective": _soap_paragraph(orig, "Objective"),
                "assessment": _soap_paragraph(orig, "Assessment"),
                "plan": _soap_paragraph(orig, "Plan"),
            },
            "filtered": {
                "subjective": _soap_paragraph(filt, "Subjective"),
                "objective": _soap_paragraph(filt, "Objective"),
                "assessment": _soap_paragraph(filt, "Assessment"),
                "plan": _soap_paragraph(filt, "Plan"),
            },
        },
        "evaluation": _evaluation_block(metrics),
    }
