# File: athena/b5/file_kind.py
# Version: v1.0 — File-kind / sheet selection helpers

from __future__ import annotations
from pathlib import Path
from typing import Optional, Set

def classify_file_kind(path: Path) -> str:
    """
    Classify Excel file type based on its filename.

    - "movements" in name -> "movements"
    - "exam"      in name -> "exam"
    - otherwise            -> "unknown"
    """
    name = path.name.lower()
    if "movements" in name:
        return "movements"
    if "exam" in name:
        return "exam"
    return "unknown"


def allowed_sheets_for_file(path: Path) -> Optional[Set[str]]:
    """
    Return a set of allowed sheet names for this file, or None to allow all.

    - For movement files: Euler + ZXY
    - For exam files:     Euler + XZY
    - For unknown files:  no restriction (None)
    """
    kind = classify_file_kind(path)
    if kind == "movements":
        return {"Segment Orientation - Euler", "Joint Angles ZXY"}
    if kind == "exam":
        return {"Segment Orientation - Euler", "Joint Angles XZY"}
    return None