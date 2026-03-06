# File: athena/b5/markers.py
# Version: v1.0 — Marker column write/read helpers (PeakID/ValleyID truth)

from __future__ import annotations
from typing import List, Optional, Tuple
import pandas as pd

from .labels import B5_LABEL_COL, col_safe, insert_after, norm_labels

def write_label_row(df: pd.DataFrame, abs_idx: int, family: str, channel_name: str, tag: str, order: int):
    """
    tag = "Peak" or "Valley"
    Creates columns if missing and writes the tag + ID at abs_idx.
    """
    base = f"{family}_{col_safe(channel_name)}"
    if tag == "Peak":
        pcol, pid = base + "_PLabel", base + "_PeakID"
        insert_after(df, B5_LABEL_COL, pcol, "")
        insert_after(df, B5_LABEL_COL, pid, "")
        df.at[df.index[abs_idx], pcol] = "Peak"
        df.at[df.index[abs_idx], pid] = int(order)
    else:
        vcol, vid = base + "_VLabel", base + "_ValleyID"
        insert_after(df, B5_LABEL_COL, vcol, "")
        insert_after(df, B5_LABEL_COL, vid, "")
        df.at[df.index[abs_idx], vcol] = "Valley"
        df.at[df.index[abs_idx], vid] = int(order)

def clear_range_for_base(df: pd.DataFrame, i0: int, i1: int, family: str, channel_name: str):
    base = f"{family}_{col_safe(channel_name)}"
    for suf in ("PLabel", "PeakID", "VLabel", "ValleyID"):
        col = f"{base}_{suf}"
        if col not in df.columns:
            insert_after(df, B5_LABEL_COL, col, "")
        df.loc[i0:i1, col] = ""

def inside_window_and_label(df: pd.DataFrame, mv: str, idxs: List[int]) -> List[int]:
    """Keep only rows where Label==mv and index is valid (defensive)."""
    mv = (mv or "").strip().lower()
    if B5_LABEL_COL not in df.columns:
        return []
    lab = norm_labels(df[B5_LABEL_COL])
    kept = []
    for i in idxs:
        if 0 <= i < len(df) and lab.iat[i] == mv:
            kept.append(i)
    return kept

def marker_cols(family: str, channel: str) -> Tuple[str, str, str, str]:
    base = f"{family}_{col_safe(channel)}"
    p_label = base + "_PLabel"
    p_id    = base + "_PeakID"
    v_label = base + "_VLabel"
    v_id    = base + "_ValleyID"
    return p_label, p_id, v_label, v_id

def read_written_markers(
    df: pd.DataFrame,
    movement: str,
    i0: Optional[int],
    i1: Optional[int],
    family: str,
    channel: str,
) -> Tuple[List[int], List[int]]:
    """
    Truth-based: read peaks/valleys from the written PeakID/ValleyID columns.
    Returns (peaks_rows, valleys_rows) as absolute row indices (0-based).
    If columns missing or no markers found, returns ([], []).
    """
    _, p_id, _, v_id = marker_cols(family, channel)
    if p_id not in df.columns and v_id not in df.columns:
        return [], []

    n = len(df)
    a = 0 if i0 is None else max(0, min(int(i0), n - 1))
    b = (n - 1) if i1 is None else max(0, min(int(i1), n - 1))
    if b < a:
        a, b = b, a

    mv = (movement or "").strip().lower()
    lab = norm_labels(df[B5_LABEL_COL]) if B5_LABEL_COL in df.columns else None

    def _collect(col: str) -> List[int]:
        if col not in df.columns:
            return []
        s = pd.to_numeric(df[col], errors="coerce")
        idxs = s.iloc[a:b+1].index[s.iloc[a:b+1].notna()].to_list()
        pos = []
        for ix in idxs:
            try:
                p = int(df.index.get_loc(ix))
            except Exception:
                continue
            pos.append(p)
        if lab is not None and mv:
            pos = [p for p in pos if 0 <= p < n and lab.iat[p] == mv]
        return sorted(set(pos))

    peaks = _collect(p_id)
    valleys = _collect(v_id)
    return peaks, valleys