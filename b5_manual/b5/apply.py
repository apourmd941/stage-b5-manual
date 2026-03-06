# File: athena/b5/apply.py
# Version: v1.4 — Apply manual B5 entries + build B5 sheets + label-window adjust with FORCE overwrite + optional debug file
#
# v1.4 changes:
# - b5_manual_adjust_label_window supports force_overwrite:
#     • if False (default): conflicts are skipped (safe mode)
#     • if True: overwrite conflicting labels inside new window
# - Returns overwritten label stats (top counts) for audit
# - Optional: write_debug_file=true writes <workbook>.adjust_label_debug.json

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import os
import time
import json as _json
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd
from tqdm import tqdm

from .file_kind import classify_file_kind, allowed_sheets_for_file
from .labels import B5_LABEL_COL, frame_col, label_windows, norm_labels
from .markers import clear_range_for_base, inside_window_and_label, write_label_row
from .sheets import build_b5_reps_and_dashboard, B5_REPS_SHEET, B5_DASH_SHEET


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def read_excel_any(path: Path) -> Dict[str, pd.DataFrame]:
    return pd.read_excel(path, sheet_name=None)

# ----------------------
# Shared job state (optional)
# ----------------------
try:
    from ..job_state import update_job, bump
except Exception:
    def update_job(job_id: str, **kw):  # type: ignore
        pass
    def bump(job_id: str, n: int = 1):  # type: ignore
        pass


# ==========================================================
# Movement label window adjuster (Label column editor)
# ==========================================================
def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default

def _safe_float(v, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return default

def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on")

def _sheet_frame_stats(df: pd.DataFrame) -> Dict[str, Any]:
    fr = frame_col(df)
    if fr is None:
        return {"ok": False, "error": "no_frame_col"}
    s = pd.to_numeric(df[fr], errors="coerce").astype(float)
    s2 = s[s.notna()]
    if s2.empty:
        return {"ok": False, "error": "frame_all_nan", "frame_col": fr}
    return {
        "ok": True,
        "frame_col": fr,
        "min_frame": float(s2.min()),
        "max_frame": float(s2.max()),
        "n_rows": int(len(df)),
        "n_frame_valid": int(s2.shape[0]),
        "frame_head": [None if pd.isna(x) else float(x) for x in s.head(5).tolist()],
        "frame_tail": [None if pd.isna(x) else float(x) for x in s.tail(5).tolist()],
    }

def _top_counts(series: pd.Series, k: int = 10) -> List[Tuple[str, int]]:
    try:
        vc = series.value_counts(dropna=False)
        out: List[Tuple[str, int]] = []
        for idx, cnt in vc.head(k).items():
            out.append((str(idx), int(cnt)))
        return out
    except Exception:
        return []

def _sheet_label_adjust(
    df: pd.DataFrame,
    movement: str,
    old_frame0: int,
    old_frame1: int,
    new_frame0: int,
    new_frame1: int,
    tol: float = 0.49,
    force_overwrite: bool = False,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Adjust Label column for a movement within a sheet using frame bounds.

    - Uses float Frame values with tolerance.
    - If force_overwrite=False: conflicts are skipped (safe)
    - If force_overwrite=True: conflicts are overwritten with the target movement label
    """
    fr = frame_col(df)
    if fr is None or B5_LABEL_COL not in df.columns:
        return df, {"ok": False, "error": "missing Frame or Label"}

    mv = (movement or "").strip().lower()
    if not mv:
        return df, {"ok": False, "error": "missing movement"}

    frames = pd.to_numeric(df[fr], errors="coerce").astype(float)

    lo0, lo1 = sorted([int(old_frame0), int(old_frame1)])
    ne0, ne1 = sorted([int(new_frame0), int(new_frame1)])

    mask_old = frames.notna() & (frames >= (lo0 - tol)) & (frames <= (lo1 + tol))
    mask_new = frames.notna() & (frames >= (ne0 - tol)) & (frames <= (ne1 + tol))

    lab_norm = norm_labels(df[B5_LABEL_COL])

    conflicts_mask = mask_new & lab_norm.notna() & (lab_norm != mv)
    n_conflicts = int(conflicts_mask.sum())

    # Capture what we would overwrite (for audit)
    overwritten_top: List[Tuple[str, int]] = []
    if n_conflicts:
        raw_vals = df.loc[conflicts_mask, B5_LABEL_COL].astype("string")
        overwritten_top = _top_counts(raw_vals, k=8)

    if force_overwrite:
        # overwrite ANY non-mv label inside new window (including conflicts + blanks)
        set_mask = mask_new & (lab_norm.isna() | (lab_norm != mv))
    else:
        # set only blanks or already mv; do not overwrite other labels
        set_mask = mask_new & (~conflicts_mask) & (lab_norm.isna() | (lab_norm == mv))

    # Clear labels only for mv labels that were in old but no longer in new
    clear_mask = mask_old & (~mask_new) & (lab_norm == mv)

    # Count actual changes (not just matches)
    before = df[B5_LABEL_COL].astype("string")

    df.loc[set_mask, B5_LABEL_COL] = mv
    df.loc[clear_mask, B5_LABEL_COL] = ""

    after = df[B5_LABEL_COL].astype("string")
    changed_mask = before.ne(after)
    n_changed = int(changed_mask.sum())

    # Near start/end sanity
    try:
        near0 = (frames >= (ne0 - 5 - tol)) & (frames <= (ne0 + 5 + tol))
        near1 = (frames >= (ne1 - 5 - tol)) & (frames <= (ne1 + 5 + tol))
        n_near0 = int(near0.sum())
        n_near1 = int(near1.sum())
        n_near0_mv = int((near0 & (norm_labels(df[B5_LABEL_COL]) == mv)).sum())
        n_near1_mv = int((near1 & (norm_labels(df[B5_LABEL_COL]) == mv)).sum())
    except Exception:
        n_near0 = n_near1 = n_near0_mv = n_near1_mv = -1

    return df, {
        "ok": True,
        "frame_col": fr,
        "old_frame0": lo0,
        "old_frame1": lo1,
        "new_frame0": ne0,
        "new_frame1": ne1,
        "tol": float(tol),
        "force_overwrite": bool(force_overwrite),
        "n_rows": int(len(df)),
        "n_in_old": int(mask_old.sum()),
        "n_in_new": int(mask_new.sum()),
        "conflicts": int(n_conflicts),
        "overwritten_top": overwritten_top,
        "changed_rows": int(n_changed),
        "near_start_rows": int(n_near0),
        "near_end_rows": int(n_near1),
        "near_start_mv": int(n_near0_mv),
        "near_end_mv": int(n_near1_mv),
    }

def b5_manual_adjust_label_window(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Payload:
      - file (rep workbook path) REQUIRED
      - movement (str) REQUIRED
      - sheet (anchor sheet) REQUIRED
      - i0, i1 (anchor row bounds from pane) REQUIRED
      - delta_start (int) default 0
      - delta_end   (int) default 0
      - tol (float) default 0.49
      - force_overwrite (bool) default False
      - write_debug_file (bool) default False
    """
    t0 = time.perf_counter()
    debug: List[Dict[str, Any]] = []

    def d(step: str, **kw):
        debug.append({"step": step, **kw})

    file_raw = str(payload.get("file") or "").strip()
    if not file_raw:
        return {"ok": False, "error": "missing file", "debug": debug}
    f = Path(file_raw).expanduser()
    if not f.exists():
        return {"ok": False, "error": f"file not found: {f}", "debug": debug}

    movement = str(payload.get("movement") or "").strip().lower()
    if not movement:
        return {"ok": False, "error": "missing movement", "debug": debug}

    sheet_anchor = str(payload.get("sheet") or "").strip()
    i0 = _safe_int(payload.get("i0"), 0)
    i1 = _safe_int(payload.get("i1"), 0)
    if i1 < i0:
        i0, i1 = i1, i0

    delta_start = max(0, _safe_int(payload.get("delta_start"), 0))
    delta_end   = max(0, _safe_int(payload.get("delta_end"), 0))
    tol = _safe_float(payload.get("tol", 0.49), 0.49)
    force_overwrite = _as_bool(payload.get("force_overwrite", False))
    write_debug_file = _as_bool(payload.get("write_debug_file", False))

    d("inputs", file=str(f), movement=movement, sheet=sheet_anchor, i0=i0, i1=i1,
      delta_start=delta_start, delta_end=delta_end, tol=tol, force_overwrite=force_overwrite, write_debug_file=write_debug_file)

    t_read0 = time.perf_counter()
    try:
        xls = read_excel_any(f)
    except Exception as e:
        return {"ok": False, "error": f"read_failed: {e}", "debug": debug}
    t_read1 = time.perf_counter()
    d("read_excel", ms=int((t_read1 - t_read0) * 1000), sheets=list(xls.keys()))

    if sheet_anchor not in xls:
        return {"ok": False, "error": f"anchor sheet not found: {sheet_anchor}", "debug": debug}

    df_anchor = xls[sheet_anchor]
    fr_anchor = frame_col(df_anchor)
    if fr_anchor is None:
        return {"ok": False, "error": "anchor sheet missing Frame column", "debug": debug}
    if B5_LABEL_COL not in df_anchor.columns:
        return {"ok": False, "error": "anchor sheet missing Label column", "debug": debug}

    n = len(df_anchor)
    i0c = max(0, min(i0, n - 1))
    i1c = max(0, min(i1, n - 1))
    if i1c < i0c:
        i0c, i1c = i1c, i0c

    f0 = df_anchor[fr_anchor].iloc[i0c]
    f1 = df_anchor[fr_anchor].iloc[i1c]
    try:
        old_frame0 = int(round(float(f0)))
        old_frame1 = int(round(float(f1)))
    except Exception as e:
        return {"ok": False, "error": f"could not parse Frame values: {e}", "debug": debug}

    new_frame0 = old_frame0 - delta_start
    new_frame1 = old_frame1 + delta_end

    d("anchor_bounds", frame_col=fr_anchor, anchor_n_rows=int(n), anchor_i0=int(i0c), anchor_i1=int(i1c),
      anchor_frame0=float(f0), anchor_frame1=float(f1),
      old_frame0=old_frame0, old_frame1=old_frame1, new_frame0=new_frame0, new_frame1=new_frame1)

    targets = ["Segment Orientation - Euler", "Joint Angles ZXY", "Joint Angles XZY"]

    for sh in targets:
        if sh in xls:
            d("sheet_stats_before", sheet=sh, **_sheet_frame_stats(xls[sh]))

    per_sheet: Dict[str, Any] = {}
    total_changed = 0
    total_conflicts = 0
    any_ok = False

    t_edit0 = time.perf_counter()
    for sh in targets:
        if sh not in xls:
            per_sheet[sh] = {"ok": False, "error": "missing_sheet"}
            continue
        df2, res = _sheet_label_adjust(
            df=xls[sh],
            movement=movement,
            old_frame0=old_frame0,
            old_frame1=old_frame1,
            new_frame0=new_frame0,
            new_frame1=new_frame1,
            tol=tol,
            force_overwrite=force_overwrite,
        )
        xls[sh] = df2
        per_sheet[sh] = res
        if res.get("ok"):
            any_ok = True
            total_changed += int(res.get("changed_rows", 0))
            total_conflicts += int(res.get("conflicts", 0))
    t_edit1 = time.perf_counter()
    d("edit_done", ms=int((t_edit1 - t_edit0) * 1000), total_changed=total_changed, total_conflicts=total_conflicts)

    if not any_ok:
        return {"ok": False, "error": "no editable sheets", "debug": debug, "per_sheet": per_sheet}

    t_write0 = time.perf_counter()
    try:
        ensure_dir(f.parent)
        with pd.ExcelWriter(f, engine="openpyxl") as w:
            for name, dfw in xls.items():
                dfw.to_excel(w, sheet_name=name[:31], index=False)
    except Exception as e:
        return {"ok": False, "error": f"write_failed: {e}", "debug": debug, "per_sheet": per_sheet}
    t_write1 = time.perf_counter()
    d("write_excel", ms=int((t_write1 - t_write0) * 1000))

    timing_ms = int((time.perf_counter() - t0) * 1000)

    out = {
        "ok": True,
        "file": str(f),
        "movement": movement,
        "anchor_sheet": sheet_anchor,
        "anchor_i0": int(i0c),
        "anchor_i1": int(i1c),
        "old_frame0": int(old_frame0),
        "old_frame1": int(old_frame1),
        "new_frame0": int(new_frame0),
        "new_frame1": int(new_frame1),
        "delta_start": int(delta_start),
        "delta_end": int(delta_end),
        "tol": float(tol),
        "force_overwrite": bool(force_overwrite),
        "total_changed_rows": int(total_changed),
        "total_conflicts": int(total_conflicts),
        "per_sheet": per_sheet,
        "timing_ms": timing_ms,
        "debug": debug,
    }

    # Optional debug file next to workbook
    if write_debug_file:
        try:
            dbg_path = Path(str(f) + ".adjust_label_debug.json")
            with open(dbg_path, "w", encoding="utf-8") as fp:
                _json.dump(out, fp, ensure_ascii=False, indent=2)
            out["debug_file"] = str(dbg_path)
        except Exception as e:
            out["debug_file_error"] = str(e)

    return out


# ==========================================================
# Existing apply logic (unchanged)
# ==========================================================
def apply_entries_to_file(
    src_path: Path,
    entries: List[Dict[str, Any]],
    in_place: bool,
    output_dir: Optional[Path],
) -> Dict[str, Any]:
    try:
        xls = read_excel_any(src_path)
    except Exception as e:
        return {"file": str(src_path), "ok": False, "error": f"read_failed: {e}"}

    allowed_sheets = allowed_sheets_for_file(src_path)
    file_kind = classify_file_kind(src_path)

    out_path: Path
    if in_place:
        out_path = src_path
    else:
        if not output_dir:
            return {"file": str(src_path), "ok": False, "error": "output_dir required when in_place=False"}
        ensure_dir(output_dir)
        out_path = output_dir / src_path.name

    n_written = 0
    per_sheet_counts: Dict[str, int] = {}

    by_sheet: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        sh = e.get("sheet", "")
        by_sheet.setdefault(sh, []).append(e)

    for sheet_name, sheet_entries in by_sheet.items():
        if allowed_sheets is not None and sheet_name not in allowed_sheets:
            continue
        if sheet_name not in xls:
            continue

        df = xls[sheet_name]
        if frame_col(df) is None or B5_LABEL_COL not in df.columns:
            continue

        _ = label_windows(df)

        for e in sheet_entries:
            mv = (e.get("movement") or "").strip().lower()
            i0 = int(e.get("i0"))
            i1 = int(e.get("i1"))
            fam = e.get("family")
            ch = e.get("channel")

            if fam is None or ch is None:
                continue

            i0 = max(0, min(i0, len(df) - 1))
            i1 = max(0, min(i1, len(df) - 1))
            if i1 < i0:
                i0, i1 = i1, i0

            clear_range_for_base(df, i0, i1, fam, ch)

            peaks = e.get("peaks") or []
            valleys = e.get("valleys") or []

            p_keep = inside_window_and_label(df, mv, peaks)
            v_keep = inside_window_and_label(df, mv, valleys)

            p_keep_sorted = sorted(set(p_keep))
            v_keep_sorted = sorted(set(v_keep))

            for k, idx_abs in enumerate(p_keep_sorted, start=1):
                write_label_row(df, idx_abs, fam, ch, "Peak", k)
            for k, idx_abs in enumerate(v_keep_sorted, start=1):
                write_label_row(df, idx_abs, fam, ch, "Valley", k)

            wrote = len(p_keep_sorted) + len(v_keep_sorted)
            n_written += wrote
            per_sheet_counts[sheet_name] = per_sheet_counts.get(sheet_name, 0) + wrote

        xls[sheet_name] = df

    try:
        reps_df, dash_df = build_b5_reps_and_dashboard(out_path, xls, entries)
        xls[B5_REPS_SHEET] = reps_df
        xls[B5_DASH_SHEET] = dash_df
    except Exception as e:
        return {"file": str(src_path), "ok": False, "error": f"b5_sheet_build_failed: {e}"}

    try:
        ensure_dir(out_path.parent)
        with pd.ExcelWriter(out_path, engine="openpyxl") as w:
            for name, dfw in xls.items():
                dfw.to_excel(w, sheet_name=name[:31], index=False)
    except Exception as e:
        return {"file": str(src_path), "ok": False, "error": f"write_failed: {e}"}

    return {
        "file": str(src_path),
        "ok": True,
        "output": str(out_path),
        "n_written": n_written,
        "per_sheet": per_sheet_counts,
        "file_kind": file_kind,
        "allowed_sheets": sorted(list(allowed_sheets)) if allowed_sheets is not None else None,
        "b5_sheets": [B5_REPS_SHEET, B5_DASH_SHEET],
    }

def b5_manual_apply(job_id: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
    src_path = Path(payload.get("file") or "").expanduser()
    in_place = bool(payload.get("in_place", False))
    out_dir = Path(payload.get("output_dir")).expanduser() if payload.get("output_dir") else None
    entries = payload.get("entries") or []

    if job_id:
        update_job(job_id, status="b5_manual_apply", total=1, done=0)

    res = apply_entries_to_file(src_path, entries, in_place, out_dir)

    if job_id:
        bump(job_id)
        update_job(job_id, status="done", result=res)
    return res

def b5_manual_apply_batch(
    job_id: Optional[str],
    payload: Dict[str, Any],
    parallel_workers: int = max(1, (os.cpu_count() or 1)),
) -> Dict[str, Any]:
    items = payload.get("files") or []
    if not items:
        return {"ok": False, "error": "payload.files is empty"}

    if job_id:
        update_job(job_id, status="b5_manual_apply_batch", total=len(items), done=0)

    results = []
    errors = []

    with ProcessPoolExecutor(max_workers=parallel_workers) as ex:
        futs = {
            ex.submit(
                apply_entries_to_file,
                Path(it.get("file") or "").expanduser(),
                it.get("entries") or [],
                bool(it.get("in_place", False)),
                Path(it.get("output_dir")).expanduser() if it.get("output_dir") else None,
            ): it
            for it in items
        }
        for fut in tqdm(as_completed(futs), total=len(futs), desc="B5 Manual Apply"):
            it = futs[fut]
            try:
                r = fut.result()
                if r.get("ok"):
                    results.append(r)
                else:
                    errors.append(r)
            except Exception as e:
                errors.append({"file": it.get("file"), "ok": False, "error": repr(e)})
            finally:
                if job_id:
                    bump(job_id)

    manifest = {
        "ok": True,
        "n_files": len(items),
        "n_ok": len(results),
        "n_err": len(errors),
        "results": results,
        "errors": errors,
    }
    if job_id:
        update_job(job_id, status="done", result=manifest, errors=errors)
    return manifest