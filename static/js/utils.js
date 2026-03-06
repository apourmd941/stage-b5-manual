/* File: athena/wizard/utils.js
 * Version: v1.1 — Shared helpers + onReady() for late-loaded modules
 */

function $(sel, root){ return (root||document).querySelector(sel); }
function $all(sel, root){ return Array.from((root||document).querySelectorAll(sel)); }
function text(el, obj){ if(!el) return; el.textContent = (typeof obj==='string') ? obj : JSON.stringify(obj, null, 2); }

function asBool(v){
  if(typeof v==='boolean') return v;
  if(v==null) return false;
  const s=String(v).toLowerCase();
  return ['1','true','yes','on'].includes(s);
}
function asInt(v,d){
  const n=parseInt(v,10);
  return Number.isFinite(n)?n:d;
}

/**
 * IMPORTANT:
 * Many wizard modules are loaded dynamically by wizard_b.js AFTER the page is ready.
 * DOMContentLoaded will NOT fire again, so modules must use onReady(fn).
 */
function onReady(fn){
  try{
    if (document.readyState === 'loading'){
      document.addEventListener('DOMContentLoaded', fn, { once: true });
    } else {
      fn();
    }
  }catch(e){
    // last resort
    try{ fn(); }catch(_){}
  }
}

function makeJobPoller({progressEl, percentEl, statusEl, logEl}){
  let timer = null;
  async function tick(jobId){
    try{
      const r = await fetch(`/api/athena/process/job/${encodeURIComponent(jobId)}`, {cache:'no-store'});
      if(!r.ok) { statusEl && (statusEl.textContent='no-status'); return; }
      const j = await r.json();
      const total = Number(j.total||0), done = Number(j.done||0);
      const status = String(j.status||'running');
      const pct = total>0 ? Math.round((done/total)*100) : (status==='done'?100:0);
      progressEl && (progressEl.value = pct);
      percentEl && (percentEl.textContent = pct+'%');
      statusEl && (statusEl.textContent = status);
      if (Array.isArray(j.latest_lines) && j.latest_lines.length && logEl){
        const now = logEl.textContent || '';
        const add = j.latest_lines.join('\n')+'\n';
        if (!now.includes(add)){
          logEl.textContent = now + add;
          logEl.scrollTop = logEl.scrollHeight;
        }
      }
      if (['done','error','failed'].includes(status)) stop();
    }catch(e){
      statusEl && (statusEl.textContent='idle');
    }
  }
  function start(jobId){ stop(); timer = setInterval(()=>tick(jobId), 800); tick(jobId); }
  function stop(){ if (timer){ clearInterval(timer); timer=null; } }
  return { start, stop };
}

async function ensurePlotly(){
  if (window.Plotly) return;
  const sources = [
    '/static/plotly-2.26.0.min.js',
    'https://cdn.plot.ly/plotly-2.26.0.min.js',
  ];
  let lastErr = null;
  for (const src of sources){
    try{
      await new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = src;
        s.onload = resolve;
        s.onerror = () => reject(new Error('Plotly load failed ' + s.src));
        document.head.appendChild(s);
      });
      if (window.Plotly) return;
    }catch(e){
      lastErr = e;
    }
  }
  throw lastErr || new Error('Plotly failed to load from all sources.');
}

function _btnSetState(btn, state, label){
  if (!btn) return;
  if (!btn.dataset.origText){
    btn.dataset.origText = (btn.textContent || '').trim();
  }
  if (typeof label === 'string'){
    btn.textContent = label;
  }
  const styles = {
    idle:    { bg: '#eee',    fg: '#111', disabled: false },
    busy:    { bg: '#0d6efd', fg: '#fff', disabled: true  },
    success: { bg: '#198754', fg: '#fff', disabled: false },
    error:   { bg: '#dc3545', fg: '#fff', disabled: false },
  };
  const s = styles[state] || styles.idle;
  btn.style.background = s.bg;
  btn.style.color = s.fg;
  btn.disabled = !!s.disabled;
}

function _btnResetAfter(btn, ms){
  if (!btn) return;
  window.setTimeout(() => {
    const orig = btn.dataset.origText || btn.textContent;
    _btnSetState(btn, 'idle', orig);
  }, ms);
}

async function runWithButtonFeedback(btn, opts, fnAsync){
  const {
    busyText = 'Working…',
    successText = 'Done ✓',
    errorText = 'Error',
    resetMs = 900,
  } = (opts || {});
  _btnSetState(btn, 'busy', busyText);
  try{
    const res = await fnAsync();
    const ok = !!(res && res.ok);
    if (ok){
      _btnSetState(btn, 'success', successText);
      _btnResetAfter(btn, resetMs);
    } else {
      _btnSetState(btn, 'error', errorText);
      _btnResetAfter(btn, Math.max(1400, resetMs));
    }
    return res;
  }catch(e){
    _btnSetState(btn, 'error', errorText);
    _btnResetAfter(btn, Math.max(1600, resetMs));
    throw e;
  }
}
