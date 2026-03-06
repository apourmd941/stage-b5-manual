/* File: athena/wizard/b5_manual_state.js
 * Version: v1.0 — Manual B5 state + resume helpers + pane helpers
 */

onReady(function(){
  const plotEl = document.getElementById('manualPlot');
  if (!plotEl) return;

  // ---- SINGLE state owner ----
  window.__B5MAN__ = {
    file: null,
    panes: [],
    paneIndex: 0,
    mode: null,          // 'peak' | 'valley'
    chIndex: 0,
    frames: [],
    channels: [],
    series: {},
    qc: null,
    clicks: {},          // key -> channel -> {peaks, valleys}
    reversePanes: {},    // key -> true/false
    _lastHoverX: null
  };

  // Resume state (explicit button)
  window.__B5_RESUME_KEY__ = 'athena_b5_manual_resume_v1';

  window.__b5_saveResumeState__ = function(){
    const st = window.__B5MAN__;
    if (!st || !st.file) return;
    try{
      window.__b5_normalizeClickStore__ && window.__b5_normalizeClickStore__();
      const payload = {
        file: st.file,
        sourceFile: st.sourceFile || null,
        repFile: st.repFile || null,
        paneIndex: st.paneIndex || 0,
        clicks: st.clicks || {},
        reversePanes: st.reversePanes || {},
        windowShift: st.windowShift || {},
        ts: Date.now()
      };
      localStorage.setItem(window.__B5_RESUME_KEY__, JSON.stringify(payload));
    }catch(e){
      console.warn('Failed to save resume state', e);
    }
  };

  window.__b5_loadResumeState__ = function(){
    try{
      const raw = localStorage.getItem(window.__B5_RESUME_KEY__);
      if (!raw) return null;
      return JSON.parse(raw);
    }catch(e){
      console.warn('Failed to load resume state', e);
      return null;
    }
  };

  window.__b5_clearResumeState__ = function(){
    try{
      localStorage.removeItem(window.__B5_RESUME_KEY__);
      return { ok:true, note:'Resume state cleared.' };
    }catch(e){
      return { ok:false, error:String(e) };
    }
  };

  // Pane helpers
  window.__b5_paneKey__ = function(p){
    return [p.sheet, p.movement, p.family, p.i0, p.i1].join('|');
  };
  window.__b5_clickKey__ = function(p){
    return [p.sheet, p.movement, p.family].join('|');
  };
  window.__b5_normalizeClickStore__ = function(){
    const st = window.__B5MAN__;
    if (!st || !st.clicks) return;
    const normalized = {};
    for (const key of Object.keys(st.clicks)){
      const store = st.clicks[key];
      if (!store || typeof store !== 'object') continue;
      const parts = String(key).split('|');
      const nk = parts.length >= 3 ? parts.slice(0, 3).join('|') : String(key);
      const target = (normalized[nk] ||= {});
      for (const ch of Object.keys(store)){
        const slot = store[ch];
        if (!slot || typeof slot !== 'object') continue;
        const tslot = (target[ch] ||= { peaks: [], valleys: [] });
        const peaks = Array.isArray(slot.peaks) ? slot.peaks : [];
        const valleys = Array.isArray(slot.valleys) ? slot.valleys : [];
        tslot.peaks = Array.from(new Set(tslot.peaks.concat(peaks))).sort((a, b) => a - b);
        tslot.valleys = Array.from(new Set(tslot.valleys.concat(valleys))).sort((a, b) => a - b);
      }
    }
    st.clicks = normalized;
  };
  window.__b5_currentPane__ = function(){
    const st = window.__B5MAN__;
    return (st.panes && st.panes.length) ? st.panes[st.paneIndex] : null;
  };
  window.__b5_isReverseOn__ = function(){
    const st = window.__B5MAN__;
    const p = window.__b5_currentPane__();
    if (!p) return false;
    return !!st.reversePanes[window.__b5_paneKey__(p)];
  };
});
