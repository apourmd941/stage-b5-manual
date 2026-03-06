# File: athena/b5/metrics.py
# Version: v1.0 — Metrics + frame alignment helpers (ROM/onset)

from __future__ import annotations
from typing import Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd

from .labels import frame_col

def safe_float_series(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s, errors="coerce").astype(float).to_numpy()

def amp_in_window(y: np.ndarray) -> float:
    y = y[np.isfinite(y)]
    if y.size == 0:
        return float("nan")
    return float(np.max(y) - np.min(y))

def onset_index(x: np.ndarray, frac: float = 0.10, hold: int = 3) -> Optional[int]:
    """
    Onset = first index where signal crosses frac*amp away from baseline (x[0]),
    persisting for `hold` samples.
    Direction auto-detected.
    """
    x = x.astype(float)
    if x.size < max(5, hold + 1) or not np.isfinite(x).any():
        return None

    base = float(x[0])
    xmin = float(np.nanmin(x))
    xmax = float(np.nanmax(x))
    amp = xmax - xmin
    if not np.isfinite(amp) or amp <= 0:
        return None

    up = abs(xmax - base) >= abs(base - xmin)
    thr = base + frac * amp if up else base - frac * amp

    mask = (x >= thr) if up else (x <= thr)

    run = 0
    for i, ok in enumerate(mask):
        run = run + 1 if bool(ok) else 0
        if run >= max(1, int(hold)):
            return i - int(hold) + 1
    return None

# Canonical columns for multi-plane metrics
EULER_PELVIS_COLS = ("Pelvis x", "Pelvis y", "Pelvis z")
ZXY_HIP_R = {
    "flex": "Right Hip Flexion/Extension",
    "abd":  "Right Hip Abduction/Adduction",
    "rot":  "Right Hip Internal/External Rotation",
}
ZXY_HIP_L = {
    "flex": "Left Hip Flexion/Extension",
    "abd":  "Left Hip Abduction/Adduction",
    "rot":  "Left Hip Internal/External Rotation",
}
ZXY_KNEE_R = {
    "flex": "Right Knee Flexion/Extension",
    "abd":  "Right Knee Abduction/Adduction",
    "rot":  "Right Knee Internal/External Rotation",
}
ZXY_KNEE_L = {
    "flex": "Left Knee Flexion/Extension",
    "abd":  "Left Knee Abduction/Adduction",
    "rot":  "Left Knee Internal/External Rotation",
}

def build_frame_to_row_map(df: pd.DataFrame) -> Dict[int, int]:
    fr = frame_col(df)
    if fr is None:
        return {}
    vals = pd.to_numeric(df[fr], errors="coerce").astype(float).to_numpy()
    out: Dict[int, int] = {}
    for i, v in enumerate(vals):
        if not np.isfinite(v):
            continue
        k = int(round(float(v)))
        if k not in out:
            out[k] = i
    return out

def rows_from_frames(df: pd.DataFrame, frame0: float, frame1: float) -> Optional[Tuple[int, int]]:
    if not np.isfinite(frame0) or not np.isfinite(frame1):
        return None
    a = int(round(float(frame0)))
    b = int(round(float(frame1)))
    if b < a:
        a, b = b, a
    m = build_frame_to_row_map(df)
    if not m:
        return None
    if a not in m or b not in m:
        return None
    i0 = m[a]
    i1 = m[b]
    if i1 < i0:
        i0, i1 = i1, i0
    return i0, i1

def compute_multiplane_metrics_by_frame(
    xls: Dict[str, pd.DataFrame],
    frame_start: Optional[float],
    frame_end: Optional[float],
    seg: str,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if frame_start is None or frame_end is None:
        return out

    def win(df: pd.DataFrame, col: str) -> Optional[np.ndarray]:
        if col not in df.columns:
            return None
        rr = rows_from_frames(df, float(frame_start), float(frame_end))
        if rr is None:
            return None
        i0, i1 = rr
        y = safe_float_series(df[col])
        if y.size == 0:
            return None
        return y[i0:i1+1]

    if seg == "Pelvis":
        df_e = xls.get("Segment Orientation - Euler")
        if df_e is not None:
            for axis, col in zip(("x", "y", "z"), EULER_PELVIS_COLS):
                arr = win(df_e, col)
                if arr is None:
                    out[f"pelvis_{axis}_rom"] = pd.NA
                    out[f"pelvis_{axis}_onset_frames"] = pd.NA
                else:
                    out[f"pelvis_{axis}_rom"] = amp_in_window(arr)
                    oi = onset_index(arr, frac=0.10, hold=3)
                    out[f"pelvis_{axis}_onset_frames"] = int(oi) if oi is not None else pd.NA

    df_z = xls.get("Joint Angles ZXY")
    if df_z is not None:
        if seg == "R_Hip":
            for k, col in ZXY_HIP_R.items():
                arr = win(df_z, col)
                out[f"R_hip_{k}_rom"] = amp_in_window(arr) if arr is not None else pd.NA
                oi = onset_index(arr, frac=0.10, hold=3) if arr is not None else None
                out[f"R_hip_{k}_onset_frames"] = int(oi) if oi is not None else pd.NA
        elif seg == "L_Hip":
            for k, col in ZXY_HIP_L.items():
                arr = win(df_z, col)
                out[f"L_hip_{k}_rom"] = amp_in_window(arr) if arr is not None else pd.NA
                oi = onset_index(arr, frac=0.10, hold=3) if arr is not None else None
                out[f"L_hip_{k}_onset_frames"] = int(oi) if oi is not None else pd.NA
        elif seg == "R_Knee":
            for k, col in ZXY_KNEE_R.items():
                arr = win(df_z, col)
                out[f"R_knee_{k}_rom"] = amp_in_window(arr) if arr is not None else pd.NA
                oi = onset_index(arr, frac=0.10, hold=3) if arr is not None else None
                out[f"R_knee_{k}_onset_frames"] = int(oi) if oi is not None else pd.NA
        elif seg == "L_Knee":
            for k, col in ZXY_KNEE_L.items():
                arr = win(df_z, col)
                out[f"L_knee_{k}_rom"] = amp_in_window(arr) if arr is not None else pd.NA
                oi = onset_index(arr, frac=0.10, hold=3) if arr is not None else None
                out[f"L_knee_{k}_onset_frames"] = int(oi) if oi is not None else pd.NA

    return out