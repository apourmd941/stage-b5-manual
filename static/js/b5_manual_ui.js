/* File: athena/wizard/b5_manual_ui.js
 * Version: v1.5 — Manual B5 UI wiring + movement-window controls + conflict-aware Apply + button feedback for Preview/Apply + compact layout
 *
 * Adds:
 * - runWithButtonFeedback() for Preview + Apply buttons
 */

document.addEventListener("DOMContentLoaded", function () {
  const plotEl = document.getElementById("manualPlot");
  if (!plotEl) return;

  const elLog = document.getElementById("manLog");
  function log(obj) {
    text(elLog, obj);
  }

  function valById(id) {
    const el = document.getElementById(id);
    return el ? (el.value || "").trim() : "";
  }

  function uniqSortInts(arr) {
    return Array.from(
      new Set((arr || []).map((v) => parseInt(v, 10)).filter(Number.isFinite)),
    ).sort((a, b) => a - b);
  }

  function currentEntriesForPane() {
    const st = window.__B5MAN__;
    const p = window.__b5_currentPane__();
    if (!p) return [];

    const clickKey = window.__b5_clickKey__(p);
    const paneKey = window.__b5_paneKey__(p);
    const store = st.clicks[clickKey] || {};
    const entries = [];
    const rev = !!st.reversePanes[paneKey];

    for (const ch of st.channels) {
      const slot = store[ch];
      if (!slot) continue;

      const peaks_idx = uniqSortInts(slot.peaks || []);
      const valleys_idx = uniqSortInts(slot.valleys || []);

      if (peaks_idx.length || valleys_idx.length) {
        entries.push({
          sheet: p.sheet,
          movement: p.movement,
          family: p.family,
          channel: ch,
          i0: p.i0,
          i1: p.i1,
          peaks: peaks_idx,
          valleys: valleys_idx,
          reverse: rev,
          pane_key: paneKey,
        });
      }
    }
    return entries;
  }

  function allEntriesForFile() {
    const st = window.__B5MAN__;
    const entries = [];
    const seen = new Set();

    for (const p of st.panes) {
      const clickKey = window.__b5_clickKey__(p);
      const paneKey = window.__b5_paneKey__(p);
      const store = st.clicks[clickKey] || {};
      const rev = !!st.reversePanes[paneKey];

      for (const ch in store) {
        const slot = store[ch];
        if (!slot) continue;

        const entryKey = [p.sheet, p.movement, p.family, ch].join("|");
        if (seen.has(entryKey)) continue;

        const peaks_idx = uniqSortInts(slot.peaks || []);
        const valleys_idx = uniqSortInts(slot.valleys || []);

        if (peaks_idx.length || valleys_idx.length) {
          entries.push({
            sheet: p.sheet,
            movement: p.movement,
            family: p.family,
            channel: ch,
            i0: p.i0,
            i1: p.i1,
            peaks: peaks_idx,
            valleys: valleys_idx,
            reverse: rev,
            pane_key: paneKey,
          });
          seen.add(entryKey);
        }
      }
    }
    return entries;
  }

  // ======================================================
  // Shift+V auto-fill valleys (Reverse-aware) — RESTORED
  // ======================================================
  function autoFillValleysForActiveChannel() {
    const st = window.__B5MAN__;
    const p = window.__b5_currentPane__();
    if (!st || !p) return;

    const clickKey = window.__b5_clickKey__(p);
    const paneKey = window.__b5_paneKey__(p);
    const ch = st.channels[st.chIndex] || st.channels[0];
    if (!ch) {
      log("No channel selected.");
      return;
    }

    const store = (st.clicks[clickKey] ||= {});
    const slot = (store[ch] ||= { peaks: [], valleys: [] });

    const reverseOn = !!st.reversePanes[paneKey];

    // Semantic mapping (Reverse swaps meaning)
    const semanticPeaks = reverseOn ? slot.valleys || [] : slot.peaks || [];
    const semanticValleys = reverseOn ? slot.peaks || [] : slot.valleys || [];

    const peaks = uniqSortInts(semanticPeaks);
    if (!peaks.length) {
      log("Add peaks first, then Shift+V to auto-fill valleys.");
      return;
    }

    const out = uniqSortInts(semanticValleys);

    const Y = st.series[ch] || [];
    if (!Array.isArray(Y) || !Y.length) {
      log("No series data for active channel.");
      return;
    }

    const rel = (abs) => abs - p.i0;

    function pickBestBetween(aAbs, bAbs) {
      if (aAbs >= bAbs) return null;

      const a = Math.max(0, rel(aAbs));
      const b = Math.min(Y.length - 1, rel(bAbs));
      if (b < a) return null;

      let bestRel = a;
      let bestVal = reverseOn ? -Infinity : Infinity;

      for (let k = a; k <= b; k++) {
        const v = Y[k];
        if (!isFinite(v)) continue;
        if (!reverseOn) {
          if (v < bestVal) {
            bestVal = v;
            bestRel = k;
          }
        } else {
          if (v > bestVal) {
            bestVal = v;
            bestRel = k;
          }
        }
      }
      return p.i0 + bestRel;
    }

    // Leading valley
    {
      const first = peaks[0];
      const aAbs = p.i0;
      const bAbs = Math.max(p.i0, first - 3);
      const vAbs = pickBestBetween(aAbs, bAbs);
      if (vAbs != null && out.indexOf(vAbs) < 0) out.push(vAbs);
    }

    // Between peaks
    for (let i = 0; i < peaks.length - 1; i++) {
      const aAbs = Math.max(peaks[i] + 3, p.i0);
      const bAbs = Math.min(peaks[i + 1] - 3, p.i1);
      const vAbs = pickBestBetween(aAbs, bAbs);
      if (vAbs != null && out.indexOf(vAbs) < 0) out.push(vAbs);
    }

    // Trailing valley
    {
      const last = peaks[peaks.length - 1];
      const aAbs = Math.max(last + 3, p.i0);
      const bAbs = p.i1;
      const vAbs = pickBestBetween(aAbs, bAbs);
      if (vAbs != null && out.indexOf(vAbs) < 0) out.push(vAbs);
    }

    out.sort((a, b) => a - b);

    // Store back respecting reverse mode
    if (!reverseOn) {
      slot.peaks = peaks;
      slot.valleys = out;
    } else {
      slot.valleys = peaks; // semantic peaks
      slot.peaks = out; // semantic valleys
    }

    try {
      window.__b5_saveResumeState__();
    } catch (_) {}
    try {
      window.__b5_redrawPlot__();
    } catch (_) {}
    log({
      ok: true,
      action: "autoFillValleys",
      channel: ch,
      reverse: reverseOn,
      peaks: peaks.length,
      valleys: out.length,
    });
  }

  function compactHeaderLayout() {
    function ensurePaneLayout() {
      const paneLabel = document.getElementById("manPaneLabel");
      const prevBtn = document.getElementById("manPrevPane");
      if (!paneLabel || !prevBtn) return;

      const paneKv = prevBtn.closest(".kv");
      if (!paneKv) return;

      let paneSection = paneKv.querySelector(".pane-section");
      if (!paneSection) {
        paneSection = document.createElement("div");
        paneSection.className = "pane-section";

        const labelEl = paneKv.querySelector("label");
        const toMove = Array.from(paneKv.children).filter((el) => el !== labelEl);
        for (const el of toMove) paneSection.appendChild(el);
        paneKv.appendChild(paneSection);
      }

      let labelRow = paneSection.querySelector("#manPaneLabelRow");
      if (!labelRow) {
        labelRow = document.createElement("div");
        labelRow.id = "manPaneLabelRow";
        paneSection.insertBefore(labelRow, paneSection.firstChild);
      }
      if (paneLabel.parentElement !== labelRow) labelRow.appendChild(paneLabel);

      let btnRow = paneSection.querySelector("#manPaneButtons");
      if (!btnRow) {
        btnRow = document.createElement("div");
        btnRow.id = "manPaneButtons";
        btnRow.className = "pane-row";
        paneSection.insertBefore(btnRow, labelRow.nextSibling);
      }

      const btnIds = [
        "manPrevPane",
        "manNextPane",
        "manModePeak",
        "manModeValley",
        "manReverse",
        "manUndo",
        "manReset",
        "manSavePane",
      ];
      for (const id of btnIds) {
        const btn = document.getElementById(id);
        if (btn && btn.parentElement !== btnRow) btnRow.appendChild(btn);
      }

      let tip = document.getElementById("manPaneTip");
      if (!tip) {
        const mutedBlocks = Array.from(paneSection.querySelectorAll(".muted"));
        tip = mutedBlocks.find((el) =>
          (el.textContent || "").trim().toLowerCase().startsWith("tip:"),
        );
        if (tip) tip.id = "manPaneTip";
      }
      if (tip) {
        if (!tip.classList.contains("pane-tip")) tip.classList.add("pane-tip");
        if (tip.parentElement !== paneSection) paneSection.appendChild(tip);
      }

      paneSection.style.display = "block";
      labelRow.style.display = "block";
      labelRow.style.marginBottom = "6px";
      btnRow.style.display = "flex";
      btnRow.style.flexWrap = "wrap";
      btnRow.style.alignItems = "center";
      btnRow.style.gap = "8px";
      if (tip) {
        tip.style.display = "block";
        tip.style.marginTop = "6px";
        tip.style.whiteSpace = "normal";
      }
    }

    ensurePaneLayout();

    const paneLabel = document.getElementById("manPaneLabel");
    if (paneLabel) {
      paneLabel.style.display = "block";
      paneLabel.style.whiteSpace = "nowrap";
      paneLabel.style.overflow = "hidden";
      paneLabel.style.textOverflow = "ellipsis";
      paneLabel.style.maxWidth = "1200px";
    }

    const savePaneBtn = document.getElementById("manSavePane");
    const btnRow = savePaneBtn ? savePaneBtn.parentElement : null;
    if (btnRow) {
      const container = btnRow.parentElement;
      if (container) {
        const tip = document.getElementById("manPaneTip");
        if (tip) {
          tip.style.marginTop = "6px";
          tip.style.whiteSpace = "normal";
          tip.style.overflow = "hidden";
          tip.style.textOverflow = "ellipsis";
          tip.style.maxWidth = "980px";
          tip.textContent =
            "Tip: Reverse toggles peak/valley meaning for inverted signals. Hotkeys: P=Peak, V=Valley, Shift+V=Auto-fill, R=Reverse.";
        }
      }
    }

    const currentFile = document.getElementById("manFile");
    if (currentFile && currentFile.parentElement) {
      currentFile.parentElement.style.marginBottom = "6px";
    }
  }

  function ensureManualStateFields() {
    const st = window.__B5MAN__;
    if (!st) return;
    if (!("sourceFile" in st)) st.sourceFile = null;
    if (!("repFile" in st)) st.repFile = null;
    if (!("windowShift" in st)) st.windowShift = {};
  }

  async function loadPane() {
    ensureManualStateFields();
    const st = window.__B5MAN__;
    const p = window.__b5_currentPane__();

    st.mode = null;
    st.qc = null;
    window.__b5_updateModeButtons__();
    window.__b5_updateReverseButton__();

    if (!p) {
      const lbl = document.getElementById("manPaneLabel");
      if (lbl) lbl.textContent = "—";
      try {
        window.Plotly && window.Plotly.purge(plotEl);
      } catch (_) {}
      log("No pane.");
      return;
    }

    const pane = await window.__b5_apiPane__(
      st.file,
      p.sheet,
      p.i0,
      p.i1,
      p.family,
    );
    if (!pane || !pane.ok) {
      log(pane || { ok: false, error: "pane request failed" });
      return;
    }

    st.frames = pane.frames || [];
    st.channels = pane.channels || [];
    st.series = pane.series || {};
    st.qc = pane.qc || null;
    st.chIndex = 0;

    window.__b5_updatePaneLabel__();

    try {
      await ensurePlotly();
    } catch (e) {
      log({ ok: false, error: "Failed to load Plotly", detail: String(e) });
      return;
    }

    try {
      window.Plotly.purge(plotEl);
    } catch (_) {}
    window.__b5_redrawPlot__();
    window.__b5_plot_bindHandlers__();

    if (window.__b5_manual_updateWinLabel__)
      window.__b5_manual_updateWinLabel__();
  }

  async function loadNextFile() {
    ensureManualStateFields();
    const st = window.__B5MAN__;

    const nx = await window.__b5_apiNext__();
    log({ step: "next", response: nx });

    if (!nx || !nx.ok) {
      log({ ok: false, where: "next", error: (nx && nx.error) || "unknown" });
      return { ok: false };
    }
    if (!nx.file) {
      log("No pending files in enriched.");
      const fInput = document.getElementById("manFile");
      if (fInput) fInput.value = "";
      st.file = null;
      st.sourceFile = null;
      st.repFile = null;
      st.panes = [];
      st.paneIndex = 0;
      st.qc = null;
      window.__b5_saveResumeState__();
      return { ok: true, file: null };
    }

    const outDir = (
      document.getElementById("manEnrichedRep")?.value || ""
    ).trim();
    if (!outDir) {
      log({ ok: false, error: "Set Enriched-Rep folder first." });
      return { ok: false };
    }

    const prep = await window.__b5_apiPrepare__(nx.file, outDir);
    log({ step: "prepare", response: prep });
    if (!prep || !prep.ok) {
      log({
        ok: false,
        where: "prepare",
        error: (prep && prep.error) || "unknown",
      });
      return { ok: false };
    }

    st.sourceFile = nx.file;
    st.repFile = prep.rep_file || prep.repFile || prep.output || null;
    st.file = st.repFile || nx.file;

    const fInput = document.getElementById("manFile");
    if (fInput) fInput.value = st.file;

    const pl = await window.__b5_apiPlan__(st.file);
    log({
      step: "plan",
      panes: pl && pl.panes ? pl.panes.length : 0,
      response: pl,
    });

    if (!pl || !pl.ok || !pl.panes || !pl.panes.length) {
      log(
        pl && pl.ok
          ? "No panes in file."
          : pl || { ok: false, error: "plan request failed" },
      );
      return { ok: false };
    }

    st.panes = pl.panes;
    st.paneIndex = 0;
    st.clicks = {};
    st.reversePanes = {};
    st.windowShift = {};
    st.mode = null;
    st.qc = null;
    st.chIndex = 0;

    window.__b5_saveResumeState__();
    await loadPane();

    return { ok: true, file: st.file };
  }

  async function resumeLastSession() {
    ensureManualStateFields();
    const st = window.__B5MAN__;
    const saved = window.__b5_loadResumeState__();

    if (!saved || !saved.file) {
      log("No saved session to resume.");
      return { ok: false, error: "no_saved_session" };
    }

    st.file = saved.file;
    st.sourceFile = saved.sourceFile || null;
    st.repFile = saved.repFile || null;

    st.paneIndex = saved.paneIndex || 0;
    st.clicks = saved.clicks || {};
    st.reversePanes = saved.reversePanes || {};
    st.windowShift = saved.windowShift || {};
    st.mode = null;
    st.qc = null;
    st.chIndex = 0;
    window.__b5_normalizeClickStore__ && window.__b5_normalizeClickStore__();

    const fInput = document.getElementById("manFile");
    if (fInput) fInput.value = st.file;

    const pl = await window.__b5_apiPlan__(st.file);
    if (!pl || !pl.ok || !pl.panes || !pl.panes.length) {
      log("Could not rebuild panes for saved session.");
      return { ok: false, error: "plan_failed" };
    }

    st.panes = pl.panes;
    st.paneIndex = Math.min(st.paneIndex, st.panes.length - 1);

    await loadPane();

    return {
      ok: true,
      resumed: true,
      file: st.file,
      pane: st.paneIndex + 1,
      total_panes: st.panes.length,
      saved_at: saved.ts || null,
    };
  }

  function mountWindowControls() {
    const st = window.__B5MAN__;
    const savePaneBtn = document.getElementById("manSavePane");
    if (!savePaneBtn) return;

    if (document.getElementById("b5WinCtrl")) return;

    const wrap = document.createElement("div");
    wrap.id = "b5WinCtrl";
    wrap.className = "inline";
    wrap.style.display = "flex";
    wrap.style.flexWrap = "wrap";
    wrap.style.alignItems = "center";
    wrap.style.gap = "6px";
    wrap.style.marginLeft = "10px";

    const label = document.createElement("span");
    label.id = "b5WinLabel";
    label.className = "muted";
    label.style.marginLeft = "10px";
    label.style.whiteSpace = "nowrap";
    label.style.display = "inline-block";
    label.style.minWidth = "260px";

    const stepSel = document.createElement("select");
    stepSel.id = "b5WinStep";
    stepSel.className = "btn";
    ["50", "100", "150", "200", "250"].forEach((v) => {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      stepSel.appendChild(o);
    });
    stepSel.value = "200";
    stepSel.title = "Step (frames)";

    function mkBtn(id, txt) {
      const b = document.createElement("button");
      b.id = id;
      b.type = "button";
      b.className = "btn";
      b.textContent = txt;
      return b;
    }

    const bSminus = mkBtn("b5StartMinus", "Start −");
    const bSplus = mkBtn("b5StartPlus", "Start +");
    const bEminus = mkBtn("b5EndMinus", "End −");
    const bEplus = mkBtn("b5EndPlus", "End +");
    const bPrev = mkBtn("b5WinPreview", "Preview");
    const bApply = mkBtn("b5WinApply", "Apply");

    wrap.appendChild(stepSel);
    wrap.appendChild(bSminus);
    wrap.appendChild(bSplus);
    wrap.appendChild(bEminus);
    wrap.appendChild(bEplus);
    wrap.appendChild(bPrev);
    wrap.appendChild(bApply);
    wrap.appendChild(label);

    savePaneBtn.parentElement.appendChild(wrap);

    function currentWindowFrames() {
      const p = window.__b5_currentPane__();
      const st = window.__B5MAN__;
      if (!p || !st.frames || !st.frames.length) return null;
      return { start: st.frames[0], end: st.frames[st.frames.length - 1] };
    }

    function getShift(mv) {
      st.windowShift ||= {};
      if (!st.windowShift[mv]) st.windowShift[mv] = { ds: 0, de: 0 };
      return st.windowShift[mv];
    }

    function updateLabel() {
      const p = window.__b5_currentPane__();
      const w = currentWindowFrames();
      if (!p || !w) {
        label.textContent = "Window: —";
        return;
      }
      const mv = String(p.movement || "");
      const sh = getShift(mv);
      const ds = sh.ds || 0;
      const de = sh.de || 0;
      label.textContent = `Window: ${Math.round(w.start)} → ${Math.round(w.end)} | Δstart=${ds} Δend=${de}`;
    }

    function stepVal() {
      return parseInt(stepSel.value || "200", 10) || 200;
    }

    async function previewShiftedWindow() {
      const st = window.__B5MAN__;
      const p = window.__b5_currentPane__();
      if (!p) return { ok: false };

      const mv = p.movement;
      const sh = getShift(mv);
      const ds = sh.ds || 0;
      const de = sh.de || 0;
      if (ds === 0 && de === 0) {
        log("No shift set.");
        return { ok: false };
      }

      const i0p = Math.max(0, (p.i0 || 0) - ds);
      const i1p = Math.max(i0p, (p.i1 || 0) + de);

      const pane = await window.__b5_apiPane__(
        st.file,
        p.sheet,
        i0p,
        i1p,
        p.family,
      );
      if (!pane || !pane.ok) {
        log(pane || { ok: false });
        return { ok: false };
      }

      st.frames = pane.frames || [];
      st.channels = pane.channels || [];
      st.series = pane.series || {};
      st.qc = pane.qc || null;
      st.chIndex = 0;

      window.__b5_updatePaneLabel__();
      window.__b5_redrawPlot__();
      window.__b5_plot_bindHandlers__();
      updateLabel();
      return { ok: true };
    }

    bSminus.onclick = async () => {
      await runWithButtonFeedback(
        bSminus,
        {
          busyText: "Shifting…",
          successText: "Shifted ✓",
          errorText: "Shift failed",
          resetMs: 500,
        },
        async () => {
          const p = window.__b5_currentPane__();
          if (!p) return { ok: false };
          const sh = getShift(p.movement);
          sh.ds = Math.max(0, (sh.ds || 0) + stepVal());
          updateLabel();
          window.__b5_saveResumeState__();
          await previewShiftedWindow();
          return { ok: true };
        },
      );
    };
    bSplus.onclick = async () => {
      await runWithButtonFeedback(
        bSplus,
        {
          busyText: "Shifting…",
          successText: "Shifted ✓",
          errorText: "Shift failed",
          resetMs: 500,
        },
        async () => {
          const p = window.__b5_currentPane__();
          if (!p) return { ok: false };
          const sh = getShift(p.movement);
          sh.ds = Math.max(0, (sh.ds || 0) - stepVal());
          updateLabel();
          window.__b5_saveResumeState__();
          await previewShiftedWindow();
          return { ok: true };
        },
      );
    };
    bEplus.onclick = async () => {
      await runWithButtonFeedback(
        bEplus,
        {
          busyText: "Shifting…",
          successText: "Shifted ✓",
          errorText: "Shift failed",
          resetMs: 500,
        },
        async () => {
          const p = window.__b5_currentPane__();
          if (!p) return { ok: false };
          const sh = getShift(p.movement);
          sh.de = Math.max(0, (sh.de || 0) + stepVal());
          updateLabel();
          window.__b5_saveResumeState__();
          await previewShiftedWindow();
          return { ok: true };
        },
      );
    };
    bEminus.onclick = async () => {
      await runWithButtonFeedback(
        bEminus,
        {
          busyText: "Shifting…",
          successText: "Shifted ✓",
          errorText: "Shift failed",
          resetMs: 500,
        },
        async () => {
          const p = window.__b5_currentPane__();
          if (!p) return { ok: false };
          const sh = getShift(p.movement);
          sh.de = Math.max(0, (sh.de || 0) - stepVal());
          updateLabel();
          window.__b5_saveResumeState__();
          await previewShiftedWindow();
          return { ok: true };
        },
      );
    };

    // Preview with button feedback
    bPrev.onclick = async () => {
      await runWithButtonFeedback(
        bPrev,
        {
          busyText: "Preview…",
          successText: "Preview ✓",
          errorText: "Preview failed",
          resetMs: 650,
        },
        async () => {
          const st = window.__B5MAN__;
          const p = window.__b5_currentPane__();
          if (!p) return { ok: false };

          const mv = p.movement;
          const sh = getShift(mv);
          const ds = sh.ds || 0;
          const de = sh.de || 0;
          if (ds === 0 && de === 0) {
            log("No shift set.");
            return { ok: false };
          }

          const i0p = Math.max(0, (p.i0 || 0) - ds);
          const i1p = Math.max(i0p, (p.i1 || 0) + de);

          const pane = await window.__b5_apiPane__(
            st.file,
            p.sheet,
            i0p,
            i1p,
            p.family,
          );
          if (!pane || !pane.ok) {
            log(pane || { ok: false });
            return { ok: false };
          }

          st.frames = pane.frames || [];
          st.channels = pane.channels || [];
          st.series = pane.series || {};
          st.qc = pane.qc || null;
          st.chIndex = 0;

          window.__b5_updatePaneLabel__();
          window.__b5_redrawPlot__();
          window.__b5_plot_bindHandlers__();
          updateLabel();
          log({ ok: true, preview: { i0: i0p, i1: i1p, ds, de } });
          return { ok: true };
        },
      );
    };

    // Apply with button feedback (covers both safe + force overwrite calls)
    bApply.onclick = async () => {
      await runWithButtonFeedback(
        bApply,
        {
          busyText: "Applying…",
          successText: "Applied ✓",
          errorText: "Apply failed",
          resetMs: 850,
        },
        async () => {
          const st = window.__B5MAN__;
          const p = window.__b5_currentPane__();
          if (!p) return { ok: false };

          const mv = p.movement;
          const sh = getShift(mv);
          const ds = sh.ds || 0;
          const de = sh.de || 0;
          if (ds === 0 && de === 0) {
            log("No shift set.");
            return { ok: false };
          }

          // safe attempt
          let resp = await window.__b5_apiAdjustLabelWindow__({
            file: st.file,
            movement: mv,
            sheet: p.sheet,
            i0: p.i0,
            i1: p.i1,
            delta_start: ds,
            delta_end: de,
            tol: 0.49,
            force_overwrite: false,
            write_debug_file: true,
          });
          log(resp);
          if (!resp || !resp.ok) return { ok: false };

          const nconf = resp.total_conflicts || 0;
          if (nconf > 0 && !resp.force_overwrite) {
            const ok = window.confirm(
              `Apply found ${nconf} conflicting labels in the expanded window.\n\nOverwrite those labels with "${mv}"?`,
            );
            if (!ok) {
              log({
                ok: true,
                note: "Overwrite declined. Window may remain unchanged due to conflicts.",
              });
              return { ok: false };
            }
            resp = await window.__b5_apiAdjustLabelWindow__({
              file: st.file,
              movement: mv,
              sheet: p.sheet,
              i0: p.i0,
              i1: p.i1,
              delta_start: ds,
              delta_end: de,
              tol: 0.49,
              force_overwrite: true,
              write_debug_file: true,
            });
            log(resp);
            if (!resp || !resp.ok) return { ok: false };
          }

          const pl = await window.__b5_apiPlan__(st.file);
          if (!pl || !pl.ok || !pl.panes) {
            log(pl || { ok: false });
            return { ok: false };
          }

          st.panes = pl.panes;

          const candidates = st.panes
            .map((pp, idx) => ({ pp, idx }))
            .filter(
              (x) =>
                x.pp.movement === p.movement &&
                x.pp.sheet === p.sheet &&
                x.pp.family === p.family,
            );

          if (candidates.length) {
            let best = candidates[0];
            let bestDist = Math.abs((best.pp.i0 || 0) - (p.i0 || 0));
            for (const c of candidates) {
              const d = Math.abs((c.pp.i0 || 0) - (p.i0 || 0));
              if (d < bestDist) {
                best = c;
                bestDist = d;
              }
            }
            st.paneIndex = best.idx;
          } else {
            st.paneIndex = 0;
          }

          sh.ds = 0;
          sh.de = 0;
          window.__b5_saveResumeState__();
          await loadPane();
          updateLabel();
          return { ok: true };
        },
      );
    };

    window.__b5_manual_updateWinLabel__ = updateLabel;
    updateLabel();
  }

  // ---------- Buttons wiring (existing feedback colors) ----------
  const btnScan = document.getElementById("manScan");
  const btnNext = document.getElementById("manNext");
  const btnSaveOnly = document.getElementById("manSaveOnly");
  const btnFinalize = document.getElementById("manFinalize");
  const btnResume = document.getElementById("manResume");
  const btnClearResume = document.getElementById("manClearResume");

  const btnPrevPane = document.getElementById("manPrevPane");
  const btnNextPane = document.getElementById("manNextPane");
  const btnPeak = document.getElementById("manModePeak");
  const btnVal = document.getElementById("manModeValley");
  const btnReverse = document.getElementById("manReverse");
  const btnUndo = document.getElementById("manUndo");
  const btnReset = document.getElementById("manReset");
  const btnSavePane = document.getElementById("manSavePane");

  if (btnScan) {
    btnScan.onclick = async () => {
      await runWithButtonFeedback(
        btnScan,
        {
          busyText: "Scanning…",
          successText: "Scan ✓",
          errorText: "Scan failed",
          resetMs: 700,
        },
        async () => {
          const j = await window.__b5_apiScan__();
          log(j);
          return j;
        },
      );
    };
  }

  if (btnNext) {
    btnNext.onclick = async () => {
      await runWithButtonFeedback(
        btnNext,
        {
          busyText: "Loading…",
          successText: "Loaded ✓",
          errorText: "Load failed",
          resetMs: 700,
        },
        async () => {
          const r = await loadNextFile();
          mountWindowControls();
          compactHeaderLayout();
          return { ok: !!(r && r.ok) };
        },
      );
    };
  }

  if (btnSaveOnly) {
    btnSaveOnly.onclick = async () => {
      await runWithButtonFeedback(
        btnSaveOnly,
        {
          busyText: "Saving…",
          successText: "Saved ✓",
          errorText: "Save failed",
          resetMs: 800,
        },
        async () => {
          const st = window.__B5MAN__;
          if (!st.file) {
            log("No file loaded.");
            return { ok: false };
          }

          const outDir = valById("manEnrichedRep");
          if (!outDir) {
            log("Set Enriched-Rep folder first.");
            return { ok: false };
          }

          const entries = allEntriesForFile();
          if (!entries.length) {
            log("Nothing to save yet.");
            return { ok: false };
          }

          window.__b5_saveResumeState__();
          const j = await window.__b5_apiApply__(st.file, outDir, entries);
          log(j);
          return j;
        },
      );
    };
  }

  if (btnFinalize) {
    btnFinalize.onclick = async () => {
      await runWithButtonFeedback(
        btnFinalize,
        {
          busyText: "Finalizing…",
          successText: "Finalized ✓",
          errorText: "Finalize failed",
          resetMs: 900,
        },
        async () => {
          const st = window.__B5MAN__;
          if (!st.sourceFile) {
            log("No source file loaded.");
            return { ok: false };
          }

          const outDir = valById("manEnrichedRep");
          if (!outDir) {
            log("Set Enriched-Rep folder first.");
            return { ok: false };
          }

          window.__b5_saveResumeState__();

          const r = await fetch("/api/athena/b5/manual/finalize", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ file: st.sourceFile, output_dir: outDir }),
          });
          const j = await r.json();
          log(j);
          return j;
        },
      );
    };
  }

  if (btnResume) {
    btnResume.onclick = async () => {
      await runWithButtonFeedback(
        btnResume,
        {
          busyText: "Resuming…",
          successText: "Resumed ✓",
          errorText: "No session",
          resetMs: 900,
        },
        async () => {
          const j = await resumeLastSession();
          log(j);
          mountWindowControls();
          compactHeaderLayout();
          return j;
        },
      );
    };
  }

  if (btnClearResume) {
    btnClearResume.onclick = async () => {
      await runWithButtonFeedback(
        btnClearResume,
        {
          busyText: "Clearing…",
          successText: "Cleared ✓",
          errorText: "Clear failed",
          resetMs: 700,
        },
        async () => {
          const j = window.__b5_clearResumeState__();
          log(j);
          return j;
        },
      );
    };
  }

  if (btnPrevPane) {
    btnPrevPane.onclick = async () => {
      await runWithButtonFeedback(
        btnPrevPane,
        {
          busyText: "Loading…",
          successText: "Loaded ✓",
          errorText: "Load failed",
          resetMs: 600,
        },
        async () => {
          const st = window.__B5MAN__;
          if (st.paneIndex > 0) {
            st.paneIndex--;
            window.__b5_saveResumeState__();
            await loadPane();
            compactHeaderLayout();
            return { ok: true };
          }
          return { ok: false };
        },
      );
    };
  }

  if (btnNextPane) {
    btnNextPane.onclick = async () => {
      await runWithButtonFeedback(
        btnNextPane,
        {
          busyText: "Loading…",
          successText: "Loaded ✓",
          errorText: "Load failed",
          resetMs: 600,
        },
        async () => {
          const st = window.__B5MAN__;
          if (st.paneIndex < st.panes.length - 1) {
            st.paneIndex++;
            window.__b5_saveResumeState__();
            await loadPane();
            compactHeaderLayout();
            return { ok: true };
          }
          return { ok: false };
        },
      );
    };
  }

  if (btnPeak) {
    btnPeak.onclick = () => {
      window.__B5MAN__.mode = "peak";
      window.__b5_updateModeButtons__();
    };
  }
  if (btnVal) {
    btnVal.onclick = () => {
      window.__B5MAN__.mode = "valley";
      window.__b5_updateModeButtons__();
    };
  }
  if (btnReverse) {
    btnReverse.onclick = () => {
      const st = window.__B5MAN__;
      const p = window.__b5_currentPane__();
      if (!p) {
        log("No pane.");
        return;
      }
      const key = window.__b5_paneKey__(p);
      st.reversePanes[key] = !st.reversePanes[key];
      window.__b5_saveResumeState__();
      window.__b5_updateReverseButton__();
      window.__b5_updatePaneLabel__();
      window.__b5_redrawPlot__();
    };
  }

  if (btnUndo) {
    btnUndo.onclick = () => {
      const st = window.__B5MAN__;
      const p = window.__b5_currentPane__();
      if (!p) return;
      const clickKey = window.__b5_clickKey__(p);
      const paneKey = window.__b5_paneKey__(p);
      const ch = st.channels[st.chIndex] || st.channels[0];
      const slot = ((st.clicks[clickKey] ||= {})[ch] ||= { peaks: [], valleys: [] });
      const isRev = !!st.reversePanes[paneKey];
      const effectiveMode = isRev
        ? st.mode === "peak"
          ? "valley"
          : "peak"
        : st.mode;
      const arr = effectiveMode === "peak" ? slot.peaks : slot.valleys;
      if (arr && arr.length) {
        const i0 = p.i0 ?? 0;
        const i1 = p.i1 ?? i0;
        let idx = -1;
        for (let i = arr.length - 1; i >= 0; i--) {
          const v = arr[i];
          if (v >= i0 && v <= i1) {
            idx = i;
            break;
          }
        }
        if (idx >= 0) arr.splice(idx, 1);
      }
      window.__b5_saveResumeState__();
      window.__b5_redrawPlot__();
    };
  }

  if (btnReset) {
    btnReset.onclick = () => {
      const st = window.__B5MAN__;
      const p = window.__b5_currentPane__();
      if (!p) return;
      const clickKey = window.__b5_clickKey__(p);
      const store = st.clicks[clickKey];
      if (store) {
        const i0 = p.i0 ?? 0;
        const i1 = p.i1 ?? i0;
        for (const ch of Object.keys(store)) {
          const slot = store[ch];
          if (!slot) continue;
          slot.peaks = (slot.peaks || []).filter((v) => v < i0 || v > i1);
          slot.valleys = (slot.valleys || []).filter((v) => v < i0 || v > i1);
        }
      }
      window.__b5_saveResumeState__();
      window.__b5_redrawPlot__();
    };
  }

  if (btnSavePane) {
    btnSavePane.onclick = async () => {
      await runWithButtonFeedback(
        btnSavePane,
        {
          busyText: "Saving…",
          successText: "Saved ✓",
          errorText: "Save failed",
          resetMs: 800,
        },
        async () => {
          const st = window.__B5MAN__;
          const p = window.__b5_currentPane__();
          if (!p) {
            log("No pane.");
            return { ok: false };
          }

          const outDir = valById("manEnrichedRep");
          if (!outDir) {
            log("Set Enriched-Rep folder first.");
            return { ok: false };
          }

          const entries = currentEntriesForPane();
          if (!entries.length) {
            log("No clicks to save for this pane.");
            return { ok: false };
          }

          window.__b5_saveResumeState__();
          const j = await window.__b5_apiApply__(st.file, outDir, entries);
          log(j);
          return j;
        },
      );
    };
  }

  // Hotkey: Shift+V to auto-fill valleys for active channel
  document.addEventListener("keydown", function (e) {
    const tag = (
      (document.activeElement && document.activeElement.tagName) ||
      ""
    ).toLowerCase();
    if (tag === "input" || tag === "textarea") return;

    if (e.key === "V" && e.shiftKey) {
      autoFillValleysForActiveChannel();
      e.preventDefault();
    }
  });

  mountWindowControls();
  compactHeaderLayout();
});
