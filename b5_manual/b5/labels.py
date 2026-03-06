# File: athena/b5/labels.py
# Version: v1.0 — Label/column helpers + window parsing

from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import re
import pandas as pd

B5_LABEL_COL   = "Label"
B5_FRAME_CANDS = ["Frame", "frame", "FRAME"]
EMPTY_LABELS   = {"", "nan", "none", "null"}

def frame_col(df: pd.DataFrame) -> Optional[str]:
    for c in B5_FRAME_CANDS:
        if c in df.columns:
            return c
    return None

def norm_labels(s: pd.Series) -> pd.Series:
    ss = s.astype("string").str.strip().str.lower()
    return ss.where(~ss.isin(EMPTY_LABELS), pd.NA)

def label_windows(df: pd.DataFrame) -> Dict[str, List[Tuple[int, int]]]:
    """Return movement -> list of (row_i0, row_i1) inclusive ranges for contiguous equal labels (normalized)."""
    if B5_LABEL_COL not in df.columns:
        return {}
    lab = norm_labels(df[B5_LABEL_COL])
    wins: Dict[str, List[Tuple[int, int]]] = {}
    cur = None
    start = None
    for i, v in enumerate(lab):
        if pd.isna(v):
            if cur is not None:
                wins.setdefault(cur, []).append((start, i - 1))
                cur = None
                start = None
        else:
            if cur is None:
                cur = v
                start = i
            elif v != cur:
                wins.setdefault(cur, []).append((start, i - 1))
                cur = v
                start = i
    if cur is not None and start is not None:
        wins.setdefault(cur, []).append((start, len(lab) - 1))
    return wins

def col_safe(s: str) -> str:
    s = s.replace("/", "_").replace("(", "").replace(")", "")
    return re.sub(r"[^A-Za-z0-9_]+", "_", s).strip("_")

def insert_after(df: pd.DataFrame, anchor: str, col: str, default_val=""):
    if col in df.columns:
        return
    cols = list(df.columns)
    if anchor in cols:
        idx = cols.index(anchor) + 1
    else:
        fr = frame_col(df)
        idx = (cols.index(fr) + 1) if fr else len(cols)
    df.insert(idx, col, default_val)