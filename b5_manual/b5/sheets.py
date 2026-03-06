# File: athena/b5/sheets.py
# Version: v1.0 — Builds B5_Reps + B5_Dashboard

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import json
import re
import numpy as np
import pandas as pd

from .labels import frame_col
from .markers import read_written_markers
from .metrics import compute_multiplane_metrics_by_frame

B5_REPS_SHEET = "B5_Reps"
B5_DASH_SHEET = "B5_Dashboard"

def segment_from_family(family: str) -> str:
    fam = (family or "").strip()
    if fam.lower() in ("pelvis",):
        return "Pelvis"
    if fam.lower() in ("rhip", "r_hip", "right_hip"):
        return "R_Hip"
    if fam.lower() in ("lhip", "l_hip", "left_hip"):
        return "L_Hip"
    if fam.lower() in ("rknee", "r_knee", "right_knee"):
        return "R_Knee"
    if fam.lower() in ("lknee", "l_knee", "left_knee"):
        return "L_Knee"
    if fam.lower().startswith("ru"):
        return "R_ULeg"
    if fam.lower().startswith("rl"):
        return "R_LLeg"
    if fam.lower().startswith("lu"):
        return "L_ULeg"
    if fam.lower().startswith("ll"):
        return "L_LLeg"
    return fam or "Unknown"

def safe_int(x) -> Optional[int]:
    try:
        if x is None:
            return None
        return int(x)
    except Exception:
        return None

def row_to_frame(df: pd.DataFrame, row_idx: int) -> Optional[float]:
    fr = frame_col(df)
    if fr is None:
        return None
    if row_idx < 0 or row_idx >= len(df):
        return None
    v = df[fr].iloc[row_idx]
    try:
        return float(v)
    except Exception:
        return None

def build_b5_reps_and_dashboard(
    file_path: Path,
    xls: Dict[str, pd.DataFrame],
    entries: List[Dict[str, Any]],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build:
      - B5_Reps: one row per rep per movement per segment/channel
      - B5_Dashboard: one row per movement with rep counts + readable event strings + JSON
    """
    grouped: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}

    for e in entries:
        sheet = str(e.get("sheet") or "")
        movement = str(e.get("movement") or "").strip().lower()
        family = str(e.get("family") or "")
        channel = str(e.get("channel") or "")
        i0 = safe_int(e.get("i0"))
        i1 = safe_int(e.get("i1"))

        peaks = [int(x) for x in (e.get("peaks") or []) if isinstance(x, (int, float, str))]
        valleys = [int(x) for x in (e.get("valleys") or []) if isinstance(x, (int, float, str))]

        pane_key = str(e.get("pane_key") or "").strip()
        reverse = bool(e.get("reverse")) if "reverse" in e else False

        key = (sheet, movement, family, channel)
        grouped[key] = {
            "sheet": sheet,
            "movement": movement,
            "family": family,
            "segment": segment_from_family(family),
            "channel": channel,
            "i0": i0,
            "i1": i1,
            "pane_key": pane_key or f"{sheet}|{movement}|{family}|{i0}|{i1}",
            "reverse": reverse,
            "source": "manual",
            "peaks_row_payload": sorted(set(int(p) for p in peaks)),
            "valleys_row_payload": sorted(set(int(v) for v in valleys)),
        }

    reps_rows: List[Dict[str, Any]] = []
    dash_rows: Dict[str, Dict[str, Any]] = {}

    m = re.match(r"^(Patient\d+)_([A-Za-z0-9_]+)_movements\.xlsx$", file_path.name, flags=re.IGNORECASE)
    patient_id = m.group(1) if m else ""
    timepoint = m.group(2) if m else ""

    for (sheet, movement, family, channel), g in grouped.items():
        if sheet not in xls:
            continue
        df = xls[sheet]
        if frame_col(df) is None:
            continue

        peaks_written, valleys_written = read_written_markers(
            df=df,
            movement=movement,
            i0=g.get("i0"),
            i1=g.get("i1"),
            family=family,
            channel=channel,
        )

        if valleys_written:
            vrows = valleys_written
            prows = peaks_written if peaks_written else g["peaks_row_payload"]
            marker_source = "sheet_truth"
        else:
            vrows = g["valleys_row_payload"]
            prows = g["peaks_row_payload"]
            marker_source = "payload_fallback"

        vrows = [v for v in vrows if 0 <= v < len(df)]
        prows = [p for p in prows if 0 <= p < len(df)]
        vrows = sorted(set(vrows))
        prows = sorted(set(prows))

        req_peaks = len(g["peaks_row_payload"])
        req_valleys = len(g["valleys_row_payload"])
        kept_peaks = len(prows)
        kept_valleys = len(vrows)

        rep_events: List[Dict[str, Any]] = []
        for i in range(len(vrows) - 1):
            v0 = vrows[i]
            v1 = vrows[i + 1]
            if v1 <= v0:
                continue

            p_between = [p for p in prows if v0 < p < v1]
            p = p_between[0] if p_between else None

            rep_id = i + 1
            row_start = v0
            row_peak = p
            row_end = v1

            rep_events.append({"rep": rep_id, "start_row": row_start, "peak_row": row_peak, "end_row": row_end})

            seg = g["segment"]
            frame_start = row_to_frame(df, row_start)
            frame_end = row_to_frame(df, row_end)

            metrics = compute_multiplane_metrics_by_frame(
                xls=xls,
                frame_start=frame_start,
                frame_end=frame_end,
                seg=seg,
            )

            reps_rows.append({
                "file": str(file_path),
                "file_name": file_path.name,
                "patient_id": patient_id,
                "timepoint": timepoint,

                "movement": movement,
                "segment": seg,
                "family": family,
                "sheet": sheet,
                "channel": channel,

                "pane_key": g.get("pane_key") or "",
                "reverse": bool(g.get("reverse", False)),
                "source": str(g.get("source") or "manual"),
                "marker_source": marker_source,

                "requested_peaks": req_peaks,
                "requested_valleys": req_valleys,
                "used_peaks": kept_peaks,
                "used_valleys": kept_valleys,

                "rep_id": rep_id,
                "start_row": row_start,
                "peak_row": row_peak if row_peak is not None else pd.NA,
                "end_row": row_end,

                "start_frame": frame_start,
                "peak_frame": row_to_frame(df, row_peak) if row_peak is not None else pd.NA,
                "end_frame": frame_end,

                "i0": g["i0"] if g["i0"] is not None else pd.NA,
                "i1": g["i1"] if g["i1"] is not None else pd.NA,

                **metrics,
            })

        d = dash_rows.setdefault(movement, {
            "file": str(file_path),
            "file_name": file_path.name,
            "patient_id": patient_id,
            "timepoint": timepoint,
            "movement": movement,

            "n_reps_Pelvis": 0,
            "n_reps_R_Hip": 0,
            "n_reps_L_Hip": 0,
            "n_reps_R_Knee": 0,
            "n_reps_L_Knee": 0,

            "segments_present": "",
            "rep_events_json": "",
            "rep_events_text": "",
            "pane_reverse_json": "",
            "debug_counts_json": "",
        })

        seg = g["segment"]
        nreps_here = max(0, len(vrows) - 1)

        if seg == "Pelvis":
            d["n_reps_Pelvis"] = max(d["n_reps_Pelvis"], nreps_here)
        elif seg == "R_Hip":
            d["n_reps_R_Hip"] = max(d["n_reps_R_Hip"], nreps_here)
        elif seg == "L_Hip":
            d["n_reps_L_Hip"] = max(d["n_reps_L_Hip"], nreps_here)
        elif seg == "R_Knee":
            d["n_reps_R_Knee"] = max(d["n_reps_R_Knee"], nreps_here)
        elif seg == "L_Knee":
            d["n_reps_L_Knee"] = max(d["n_reps_L_Knee"], nreps_here)

        seg_bundle = []
        for ev in rep_events:
            seg_bundle.append({
                "rep": ev["rep"],
                "start_row": ev["start_row"],
                "peak_row": ev["peak_row"],
                "end_row": ev["end_row"],
                "start_frame": row_to_frame(df, ev["start_row"]),
                "peak_frame": row_to_frame(df, ev["peak_row"]) if ev["peak_row"] is not None else None,
                "end_frame": row_to_frame(df, ev["end_row"]),
            })

        if "___json_bundles" not in d:
            d["___json_bundles"] = {}
        d["___json_bundles"][f"{seg}:{channel}"] = seg_bundle

        if "___pane_reverse" not in d:
            d["___pane_reverse"] = {}
        if "___debug_counts" not in d:
            d["___debug_counts"] = []

        pane_key = g.get("pane_key") or ""
        if pane_key:
            d["___pane_reverse"][pane_key] = bool(g.get("reverse", False))

        d["___debug_counts"].append({
            "sheet": sheet,
            "movement": movement,
            "segment": seg,
            "family": family,
            "channel": channel,
            "marker_source": marker_source,
            "requested_peaks": req_peaks,
            "requested_valleys": req_valleys,
            "used_peaks": kept_peaks,
            "used_valleys": kept_valleys,
        })

    for mv, d in dash_rows.items():
        bundles = d.pop("___json_bundles", {})
        pane_reverse = d.pop("___pane_reverse", {})
        dbg_counts = d.pop("___debug_counts", [])

        d["segments_present"] = ";".join(sorted({k.split(":", 1)[0] for k in bundles.keys()}))
        d["rep_events_json"] = json.dumps(bundles, ensure_ascii=False)
        d["pane_reverse_json"] = json.dumps(pane_reverse, ensure_ascii=False)
        d["debug_counts_json"] = json.dumps(dbg_counts, ensure_ascii=False)

        parts = []
        for key in sorted(bundles.keys()):
            seg = key.split(":", 1)[0]
            evs = bundles[key]
            if not evs:
                continue
            ev_txt = []
            for ev in evs:
                ev_txt.append(f"r{ev['rep']}:{ev['start_row']}-{ev['peak_row'] if ev['peak_row'] is not None else 'NA'}-{ev['end_row']}")
            parts.append(f"{seg}({key.split(':',1)[1]}): " + " | ".join(ev_txt))
        d["rep_events_text"] = " ; ".join(parts)

    reps_df = pd.DataFrame(reps_rows)
    dash_df = pd.DataFrame(list(dash_rows.values()))

    if not reps_df.empty:
        base_cols = [
            "file", "file_name", "patient_id", "timepoint",
            "movement", "segment", "family",
            "sheet", "channel",
            "pane_key", "reverse", "source", "marker_source",
            "requested_peaks", "requested_valleys", "used_peaks", "used_valleys",
            "rep_id",
            "start_row", "peak_row", "end_row",
            "start_frame", "peak_frame", "end_frame",
            "i0", "i1",
        ]
        metric_cols = [c for c in reps_df.columns if c not in base_cols]
        reps_df = reps_df.reindex(columns=base_cols + sorted(metric_cols))

    if not dash_df.empty:
        dash_cols = [
            "file", "file_name", "patient_id", "timepoint",
            "movement",
            "n_reps_Pelvis", "n_reps_R_Hip", "n_reps_L_Hip", "n_reps_R_Knee", "n_reps_L_Knee",
            "segments_present",
            "rep_events_text",
            "rep_events_json",
            "pane_reverse_json",
            "debug_counts_json",
        ]
        dash_df = dash_df.reindex(columns=[c for c in dash_cols if c in dash_df.columns])

    return reps_df, dash_df