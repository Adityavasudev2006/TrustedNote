"""
Loader for ACI-Bench-style CSVs (dialogue + note pairs).

ACI-Bench / MTS-Dialog releases don't all use identical column names across
splits (e.g. "dialogue" vs "transcript" vs "src", "note" vs "summary" vs
"tgt"), so this auto-detects common variants instead of hardcoding one name.
If your CSV uses something else, pass `transcript_col` / `note_col` explicitly.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

TRANSCRIPT_COL_CANDIDATES = ["dialogue", "transcript", "conversation", "src", "text"]
NOTE_COL_CANDIDATES = ["note", "summary", "clinical_note", "tgt", "target"]
ID_COL_CANDIDATES = ["id", "encounter_id", "ID", "dataset"]


@dataclass
class Example:
    id: str
    transcript: str
    note: str  # reference/gold note, if available


def _pick_column(fieldnames: List[str], candidates: List[str]) -> Optional[str]:
    lower_map = {f.lower(): f for f in fieldnames}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def load_aci_bench(
    csv_path: str,
    transcript_col: Optional[str] = None,
    note_col: Optional[str] = None,
    id_col: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Example]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(
            f"{csv_path} not found. Point this at the ACI-Bench split you downloaded "
            f"(e.g. data/aci-bench/train.csv)."
        )

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        t_col = transcript_col or _pick_column(fieldnames, TRANSCRIPT_COL_CANDIDATES)
        n_col = note_col or _pick_column(fieldnames, NOTE_COL_CANDIDATES)
        i_col = id_col or _pick_column(fieldnames, ID_COL_CANDIDATES)

        if not t_col or not n_col:
            raise ValueError(
                f"Could not auto-detect transcript/note columns in {csv_path}. "
                f"Found columns: {fieldnames}. Pass transcript_col= and note_col= explicitly."
            )

        examples = []
        for i, row in enumerate(reader):
            examples.append(
                Example(
                    id=row.get(i_col, str(i)) if i_col else str(i),
                    transcript=row[t_col],
                    note=row[n_col],
                )
            )
            if limit and len(examples) >= limit:
                break
        return examples
