"""Persist generated sessions for the web dashboard."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
SESSIONS_DIR = PROJECT_ROOT / "data" / "sessions"
INDEX_PATH = SESSIONS_DIR / "index.json"


def _load_index() -> list[dict[str, Any]]:
    if not INDEX_PATH.is_file():
        return []
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(rows: list[dict[str, Any]]) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def list_session_rows() -> list[dict[str, Any]]:
    return sorted(_load_index(), key=lambda r: r.get("createdAt", 0), reverse=True)


def new_session_id() -> str:
    return f"s-{int(time.time())}-{uuid.uuid4().hex[:4]}"


def save_session(dashboard: dict[str, Any], *, source: str = "Web") -> str:
    session_id = dashboard.get("session", {}).get("id") or new_session_id()
    dashboard.setdefault("session", {})["id"] = session_id
    dashboard["session"]["source"] = source

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{session_id}.json"
    path.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False), encoding="utf-8")

    row = {
        "id": session_id,
        "patient": dashboard.get("patient", {}).get("name", "Patient"),
        "doctor": dashboard.get("session", {}).get("doctorName", "Clinician"),
        "time": dashboard.get("session", {}).get("time", "Today"),
        "source": source,
        "status": dashboard.get("session", {}).get("status", "Ready for review"),
        "risk": dashboard.get("session", {}).get("riskLevel", "low"),
        "claims": dashboard.get("session", {}).get("totalClaims", 0),
        "rate": dashboard.get("session", {}).get("unsupportedPercentage", 0),
        "createdAt": time.time(),
    }
    rows = [r for r in _load_index() if r.get("id") != session_id]
    rows.insert(0, row)
    _save_index(rows)
    return session_id


def load_session(session_id: str) -> dict[str, Any] | None:
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
