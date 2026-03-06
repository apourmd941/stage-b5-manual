# File: b5_manual/routes_manual.py
# Standalone Stage B5 Manual routes

from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from flask import Blueprint, request, jsonify
from werkzeug.exceptions import BadRequest

import json
from datetime import datetime

import numpy as np
import pandas as pd

from .job_state import new_job
from .b5.apply import b5_manual_apply, b5_manual_apply_batch, b5_manual_adjust_label_window

# NEW (movement ordering + QC thresholds) — safe fallback
try:
    from .movement_order import movement_rank as _movement_rank, QC as _QC_CFG  # type: ignore
except Exception:
    def _movement_rank(mv: str) -> int:  # type: ignore
        return 10_000_000
    _QC_CFG = {"min_frames": 60, "min_amp_deg": 2.0}


def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on")


def _as_int(v, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


# ==========================================================
# Manual JSONL Sidecar Writer (records Reverse flag too)
# ==========================================================
def _manual_jsonl_path(rep_excel_path: str) -> Path:
    p = Path(rep_excel_path)
    return Path(str(p) + ".manual_labels.jsonl")


def _append_manual_jsonl(rep_excel_path: str, entry: Dict[str, Any]) -> None:
    try:
        outp = _manual_jsonl_path(rep_excel_path)
        outp.parent.mkdir(parents=True, exist_ok=True)
        row = dict(entry)
        row["ts"] = datetime.now().isoformat(timespec="seconds")
        row["rep_excel"] = rep_excel_path
        with open(outp, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _log_entries_to_sidecars(excel_file: str, entries: List[Dict[str, Any]]) -> None:
    for e in entries:
        _append_manual_jsonl(
            rep_excel_path=excel_file,
            entry={
                "project": "fai-mocap",
                "sheet": str(e.get("sheet") or ""),
                "movement": str(e.get("movement") or "unknown"),
                "family": str(e.get("family") or ""),
                "channel": str(e.get("channel") or ""),
                "i0": int(e.get("i0") or 0),
                "i1": int(e.get("i1") or 0),
                "peaks": [int(x) for x in (e.get("peaks") or [])],
                "valleys": [int(x) for x in (e.get("valleys") or [])],
                "reverse": bool(e.get("reverse", False)),
                "pane_key": str(e.get("pane_key") or ""),
            },
        )


# ---- Triplet plan/pane ----
EULER_TRIPLETS = {
    "Pelvis": ("Pelvis x", "Pelvis y", "Pelvis z"),
    "RULeg": ("Right Upper Leg x", "Right Upper Leg y", "Right Upper Leg z"),
    "RLLeg": ("Right Lower Leg x", "Right Lower Leg y", "Right Lower Leg z"),
    "LULeg": ("Left Upper Leg x", "Left Upper Leg y", "Left Upper Leg z"),
    "LLLeg": ("Left Lower Leg x", "Left Lower Leg y", "Left Lower Leg z"),
}
Z_TRIPLETS = {
    "RHip": ("Right Hip Abduction/Adduction", "Right Hip Internal/External Rotation", "Right Hip Flexion/Extension"),
    "RKnee": ("Right Knee Abduction/Adduction", "Right Knee Internal/External Rotation", "Right Knee Flexion/Extension"),
    "LHip": ("Left Hip Abduction/Adduction", "Left Hip Internal/External Rotation", "Left Hip Flexion/Extension"),
    "LKnee": ("Left Knee Abduction/Adduction", "Left Knee Internal/External Rotation", "Left Knee Flexion/Extension"),
}

MOVEMAP: Dict[str, Dict[str, Any]] = {
    "jump_on_both_legs": {"ignore": False, "euler_fams": ["Pelvis", "RULeg", "RLLeg", "LULeg", "LLLeg"], "z_fams": ["RHip", "RKnee", "LHip", "LKnee"]},
    "left_leg_figure_4_(tying_shoes)":  {"ignore": False, "euler_fams": ["Pelvis", "LULeg", "LLLeg"], "z_fams": ["LHip", "LKnee"]},
    "right_leg_figure_4_(tying_shoes)": {"ignore": False, "euler_fams": ["Pelvis", "RULeg", "RLLeg"], "z_fams": ["RHip", "RKnee"]},
    "left_leg_single_leg_hop": {"ignore": False, "euler_fams": ["Pelvis", "LULeg", "LLLeg"], "z_fams": ["LHip", "LKnee"]},
    "right_leg_single_leg_hop": {"ignore": False, "euler_fams": ["Pelvis", "RULeg", "RLLeg"], "z_fams": ["RHip", "RKnee"]},
    "left_leg_standing_shoe_tying": {"ignore": False, "euler_fams": ["Pelvis", "LULeg", "LLLeg"], "z_fams": ["LHip", "LKnee"]},
    "right_leg_standing_shoe_tying": {"ignore": False, "euler_fams": ["Pelvis", "RULeg", "RLLeg"], "z_fams": ["RHip", "RKnee"]},
    "lumbar_flexion_extension": {"ignore": False, "euler_fams": ["Pelvis", "RULeg", "RLLeg", "LULeg", "LLLeg"], "z_fams": ["RHip", "RKnee", "LHip", "LKnee"]},
    "regular_squat": {"ignore": False, "euler_fams": ["Pelvis", "RULeg", "RLLeg", "LULeg", "LLLeg"], "z_fams": ["RHip", "RKnee", "LHip", "LKnee"]},
    "sit_stand": {"ignore": False, "euler_fams": ["Pelvis", "RULeg", "RLLeg", "LULeg", "LLLeg"], "z_fams": ["RHip", "RKnee", "LHip", "LKnee"]},
    "sumo_squat": {"ignore": False, "euler_fams": ["Pelvis", "RULeg", "RLLeg", "LULeg", "LLLeg"], "z_fams": ["RHip", "RKnee", "LHip", "LKnee"]},
    "walking": {"ignore": True},
}

def _frame_col(df: pd.DataFrame) -> Optional[str]:
    for c in ("Frame", "frame", "FRAME"):
        if c in df.columns:
            return c
    return None

def _norm_labels(s: pd.Series) -> pd.Series:
    ss = s.astype("string").str.strip().str.lower()
    return ss.where(~ss.isin({"", "nan", "none", "null"}), pd.NA)

def _label_windows(df: pd.DataFrame) -> Dict[str, List[Tuple[int, int]]]:
    if "Label" not in df.columns:
        return {}
    lab = _norm_labels(df["Label"])
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

def _is_exam_file_from_xls(xls: Dict[str, pd.DataFrame]) -> bool:
    has_zxy = "Joint Angles ZXY" in xls
    has_xzy = "Joint Angles XZY" in xls
    if has_zxy:
        return False
    return bool(has_xzy)

def _build_plan_for_file(xls: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
    is_exam = _is_exam_file_from_xls(xls)

    if is_exam:
        allowed = {"Segment Orientation - Euler", "Joint Angles XZY"}
        sheet_rank = {"Segment Orientation - Euler": 0, "Joint Angles XZY": 1}
    else:
        allowed = {"Segment Orientation - Euler", "Joint Angles ZXY"}
        sheet_rank = {"Segment Orientation - Euler": 0, "Joint Angles ZXY": 1}

    plan: List[Dict[str, Any]] = []
    for sheet, df in xls.items():
        if sheet not in allowed:
            continue
        if _frame_col(df) is None or "Label" not in df.columns:
            continue

        wins = _label_windows(df)
        for mv, spans in wins.items():
            rule = MOVEMAP.get(mv, {"ignore": False})
            if rule.get("ignore", False):
                continue

            fams = rule.get("euler_fams" if sheet == "Segment Orientation - Euler" else "z_fams", [])
            if not fams:
                continue

            triplets = EULER_TRIPLETS if sheet == "Segment Orientation - Euler" else Z_TRIPLETS
            for (i0, i1) in spans:
                for fam in fams:
                    trip = triplets.get(fam)
                    if not trip:
                        continue
                    if any(ch not in df.columns for ch in trip):
                        continue
                    plan.append({
                        "sheet": sheet,
                        "movement": mv,
                        "i0": int(i0),
                        "i1": int(i1),
                        "family": fam,
                        "channels": list(trip),
                    })

    def _key(p: Dict[str, Any]) -> Tuple[Any, ...]:
        mv = str(p.get("movement") or "")
        return (
            int(_movement_rank(mv)),
            mv,
            int(sheet_rank.get(str(p.get("sheet") or ""), 99)),
            str(p.get("family") or ""),
            int(p.get("i0") or 0),
        )

    plan.sort(key=_key)
    return plan

def _pane_series(df: pd.DataFrame, i0: int, i1: int, channels: List[str]) -> Dict[str, Any]:
    fr = _frame_col(df)
    frames = pd.to_numeric(df[fr], errors="coerce").astype(float).values[i0 : i1 + 1].tolist()
    data: Dict[str, Any] = {}
    for ch in channels:
        y = pd.to_numeric(df[ch], errors="coerce").astype(float).values[i0 : i1 + 1]
        y = np.degrees(np.unwrap(np.radians(y)))
        data[ch] = y.tolist()
    return {"frames": frames, "data": data}

def _pane_qc(series: Dict[str, List[float]]) -> Dict[str, Any]:
    try:
        min_frames = int(_QC_CFG.get("min_frames", 60))
    except Exception:
        min_frames = 60
    try:
        min_amp = float(_QC_CFG.get("min_amp_deg", 2.0))
    except Exception:
        min_amp = 2.0

    chans = list(series.keys())
    n = len(series[chans[0]]) if chans else 0

    amp_by: Dict[str, float] = {}
    for ch, y in series.items():
        arr = np.array(y, dtype=float)
        arr = arr[np.isfinite(arr)]
        amp_by[ch] = float(arr.max() - arr.min()) if arr.size else float("nan")

    flags: List[str] = []
    if n < min_frames:
        flags.append("too_short")

    finite_amps = [a for a in amp_by.values() if isinstance(a, (int, float)) and np.isfinite(a)]
    if finite_amps and all(a < min_amp for a in finite_amps):
        flags.append("flat_signal")

    return {
        "status": "warn" if flags else "ok",
        "flags": flags,
        "n_frames": int(n),
        "min_frames": int(min_frames),
        "min_amp_deg": float(min_amp),
        "amp_by_channel": amp_by,
    }


def register_manual_routes(bp: Blueprint) -> None:
    # --------------------------
    # Manual B5 endpoints: scan/next/start/apply/apply_batch/finalize + plan/prepare/pane
    # --------------------------
    @bp.post("/b5/manual/scan")
    def api_b5_manual_scan():
        payload = request.get_json(force=True)

        enriched_dir = Path(str(payload.get("enriched_dir") or "")).expanduser()
        enriched_rep_dir = Path(str(payload.get("enriched_rep_dir") or "")).expanduser()
        file_glob = str(payload.get("file_glob") or "*.xlsx").strip() or "*.xlsx"

        if not str(enriched_dir):
            return jsonify({"ok": False, "error": "missing enriched_dir"}), 200
        if not enriched_dir.exists():
            return jsonify({"ok": False, "error": f"enriched_dir not found: {enriched_dir}"}), 200

        done_stems = set()
        if enriched_rep_dir.exists():
            for m in enriched_rep_dir.glob("*.xlsx.done"):
                stem = m.name[:-len(".xlsx.done")]
                done_stems.add(stem.lower())

        candidates = [p for p in enriched_dir.glob(file_glob) if p.is_file()]
        candidates.sort(key=lambda x: x.name.lower())

        pending = []
        completed = []
        for p in candidates:
            if p.name.lower() in done_stems:
                completed.append(str(p))
            else:
                pending.append(str(p))

        return jsonify({"ok": True, "pending": pending, "completed": completed, "pending_count": len(pending), "completed_count": len(completed)})

    @bp.post("/b5/manual/next")
    def api_b5_manual_next():
        payload = request.get_json(force=True)

        enriched_dir = Path(str(payload.get("enriched_dir") or "")).expanduser()
        enriched_rep_dir = Path(str(payload.get("enriched_rep_dir") or "")).expanduser()
        file_glob = str(payload.get("file_glob") or "*.xlsx").strip() or "*.xlsx"

        if not str(enriched_dir):
            return jsonify({"ok": False, "error": "missing enriched_dir"}), 200
        if not enriched_dir.exists():
            return jsonify({"ok": False, "error": f"enriched_dir not found: {enriched_dir}"}), 200

        done_stems = set()
        if enriched_rep_dir.exists():
            for m in enriched_rep_dir.glob("*.xlsx.done"):
                stem = m.name[:-len(".xlsx.done")]
                done_stems.add(stem.lower())

        candidates = [p for p in enriched_dir.glob(file_glob) if p.is_file()]
        candidates.sort(key=lambda x: x.name.lower())

        pending = []
        completed = []
        for p in candidates:
            if p.name.lower() in done_stems:
                completed.append(str(p))
            else:
                pending.append(str(p))

        nxt = pending[0] if pending else None
        return jsonify({"ok": True, "file": nxt, "pending_count": len(pending), "completed_count": len(completed)})

    @bp.post("/b5/manual/start")
    def api_b5_manual_start():
        return jsonify({"ok": True, "job_id": new_job("b5_manual_apply")})

    @bp.post("/b5/manual/apply")
    def api_b5_manual_apply_route():
        payload = request.get_json(force=True)
        job_id = payload.get("job_id") or None

        if not payload.get("file"):
            raise BadRequest("Missing 'file' in payload")
        if not isinstance(payload.get("entries"), list):
            raise BadRequest("Missing or invalid 'entries' list")
        if not _as_bool(payload.get("in_place")) and not payload.get("output_dir"):
            raise BadRequest("in_place=False requires 'output_dir'")

        res = b5_manual_apply(job_id, payload)

        try:
            if res.get("ok") and isinstance(payload.get("entries"), list):
                excel_file = str(payload.get("file") or "")
                _log_entries_to_sidecars(excel_file, payload["entries"])
        except Exception:
            pass

        return jsonify(res)

    @bp.post("/b5/manual/apply_batch")
    def api_b5_manual_apply_batch_route():
        payload = request.get_json(force=True)
        job_id = payload.get("job_id") or None
        files = payload.get("files")

        if not isinstance(files, list) or not files:
            raise BadRequest("Missing or invalid 'files' array")

        parallel = _as_int(payload.get("parallel_workers"), 8)
        res = b5_manual_apply_batch(job_id, payload, parallel_workers=parallel)

        try:
            if res.get("ok"):
                for block in files or []:
                    excel_file = str(block.get("file") or "")
                    entries = block.get("entries") or []
                    if entries:
                        _log_entries_to_sidecars(excel_file, entries)
        except Exception:
            pass

        return jsonify(res)

    # NEW: adjust label window
    @bp.post("/b5/manual/adjust_label_window")
    def api_b5_manual_adjust_label_window_route():
        payload = request.get_json(force=True) or {}
        if not payload.get("file"):
            raise BadRequest("Missing 'file' in payload")
        if not payload.get("movement"):
            raise BadRequest("Missing 'movement' in payload")
        if payload.get("sheet") is None:
            raise BadRequest("Missing 'sheet' in payload")
        if payload.get("i0") is None or payload.get("i1") is None:
            raise BadRequest("Missing 'i0'/'i1' in payload")

        res = b5_manual_adjust_label_window(payload)
        return jsonify(res)

    @bp.post("/b5/manual/finalize")
    def api_b5_manual_finalize():
        payload = request.get_json(force=True) or {}
        file_raw = str(payload.get("file") or "").strip()
        rep_dir = Path(str(payload.get("output_dir") or "")).expanduser()

        if not file_raw:
            return jsonify({"ok": False, "error": "missing file"}), 200
        if not rep_dir.exists() or not rep_dir.is_dir():
            return jsonify({"ok": False, "error": f"output_dir not found or not a directory: {rep_dir}"}), 200

        file_name = Path(file_raw).name
        if not file_name.lower().endswith((".xlsx", ".xlsm", ".xls")):
            return jsonify({"ok": False, "error": f"file does not look like an Excel workbook: {file_name}"}), 200

        src_path = Path(file_raw).expanduser()
        if not src_path.exists():
            guess = rep_dir.parent / "enriched" / file_name
            if guess.exists():
                src_path = guess
            else:
                return jsonify({"ok": False, "error": f"source enriched file not found: {src_path} (also tried {guess})"}), 200

        try:
            enriched_dir = src_path.parent
            archived_dir = enriched_dir / "archived"
            archived_dir.mkdir(parents=True, exist_ok=True)

            dest_path = archived_dir / file_name
            if dest_path.exists():
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                dest_path = archived_dir / f"{Path(file_name).stem}__archived_{ts}{Path(file_name).suffix}"

            import shutil
            shutil.move(str(src_path), str(dest_path))

            marker = rep_dir / f"{file_name}.done"
            marker.touch(exist_ok=True)

            return jsonify({
                "ok": True,
                "marker": str(marker),
                "moved_from": str(src_path),
                "moved_to": str(dest_path),
                "rep_dir": str(rep_dir),
            })
        except Exception as e:
            return jsonify({"ok": False, "error": f"finalize_failed: {e}"}), 200

    @bp.post("/b5/manual/plan")
    def api_b5_manual_plan():
        payload = request.get_json(force=True)
        f = Path(str(payload.get("file") or "")).expanduser()
        if not f.exists():
            return jsonify({"ok": False, "error": f"file not found: {f}"}), 404
        try:
            xls = pd.read_excel(f, sheet_name=None)
            plan = _build_plan_for_file(xls)
            return jsonify({"ok": True, "file": str(f), "panes": plan})
        except Exception as e:
            return jsonify({"ok": False, "error": f"read_failed: {e}"}), 400

    @bp.post("/b5/manual/prepare")
    def api_b5_manual_prepare():
        payload = request.get_json(force=True) or {}
        src_raw = (payload.get("file") or "").strip()
        out_dir_raw = (payload.get("output_dir") or "").strip()

        if not src_raw:
            return jsonify({"ok": False, "error": "missing 'file'"}), 200
        if not out_dir_raw:
            return jsonify({"ok": False, "error": "missing 'output_dir'"}), 200

        src = Path(src_raw).expanduser()
        out_dir = Path(out_dir_raw).expanduser()

        if not src.exists():
            return jsonify({"ok": False, "error": f"source not found: {src}"}), 200
        if not out_dir.exists():
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return jsonify({"ok": False, "error": f"cannot create output_dir: {e}"}), 200

        dst = out_dir / src.name
        try:
            if not dst.exists():
                import shutil
                shutil.copy2(str(src), str(dst))
                msg = f"copied new file to {dst}"
            else:
                msg = f"already exists at {dst}"
            return jsonify({"ok": True, "rep_file": str(dst), "note": msg})
        except Exception as e:
            return jsonify({"ok": False, "error": f"prepare_failed: {e}"}), 200

    @bp.post("/b5/manual/pane")
    def api_b5_manual_pane():
        payload = request.get_json(force=True)
        f = Path(str(payload.get("file") or "")).expanduser()
        sheet = str(payload.get("sheet") or "").strip()
        family = str(payload.get("family") or "").strip()
        i0 = _as_int(payload.get("i0"), 0)
        i1 = _as_int(payload.get("i1"), 0)

        if not f.exists():
            return jsonify({"ok": False, "error": f"file not found: {f}"}), 404
        try:
            xls = pd.read_excel(f, sheet_name=None)
            if sheet not in xls:
                return jsonify({"ok": False, "error": f"sheet not found: {sheet}"}), 404
            df = xls[sheet]

            is_exam = _is_exam_file_from_xls(xls)
            if is_exam and sheet == "Joint Angles ZXY":
                return jsonify({"ok": False, "error": "ZXY not used for exam files"}), 400
            if (not is_exam) and sheet == "Joint Angles XZY":
                return jsonify({"ok": False, "error": "XZY not used for movements files"}), 400

            trip = (EULER_TRIPLETS if sheet == "Segment Orientation - Euler" else Z_TRIPLETS).get(family)
            if not trip:
                return jsonify({"ok": False, "error": f"family not recognized: {family}"}), 400
            if any(ch not in df.columns for ch in trip):
                return jsonify({"ok": False, "error": f"missing columns for {family}: {trip}"}), 400

            n = len(df)
            i0 = max(0, min(i0, n - 1))
            i1 = max(0, min(i1, n - 1))
            if i1 < i0:
                i0, i1 = i1, i0

            ser = _pane_series(df, i0, i1, list(trip))
            qc = _pane_qc(ser["data"])

            return jsonify({
                "ok": True,
                "frames": ser["frames"],
                "channels": list(trip),
                "series": ser["data"],
                "qc": qc,
            })
        except Exception as e:
            return jsonify({"ok": False, "error": f"read_failed: {e}"}), 400
