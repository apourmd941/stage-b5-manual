/* File: athena/wizard/b5_manual_api.js
 * Version: v1.1 — Manual B5 API functions (+ adjust_label_window)
 */

document.addEventListener('DOMContentLoaded', function(){
  const plotEl = document.getElementById('manualPlot');
  if (!plotEl) return;

  window.__b5_apiScan__ = async function(){
    const enriched = document.getElementById('manEnriched').value.trim();
    const rep      = document.getElementById('manEnrichedRep').value.trim();
    const glob     = document.getElementById('manGlob').value.trim() || '*.xlsx';
    const r = await fetch('/api/athena/b5/manual/scan',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({enriched_dir:enriched,enriched_rep_dir:rep,file_glob:glob})
    });
    return await r.json();
  };

  window.__b5_apiNext__ = async function(){
    const enriched = document.getElementById('manEnriched').value.trim();
    const rep      = document.getElementById('manEnrichedRep').value.trim();
    const glob     = document.getElementById('manGlob').value.trim() || '*.xlsx';
    const r = await fetch('/api/athena/b5/manual/next',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({enriched_dir:enriched,enriched_rep_dir:rep,file_glob:glob})
    });
    return await r.json();
  };

  window.__b5_apiPlan__ = async function(file){
    const r = await fetch('/api/athena/b5/manual/plan',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({file})
    });
    return await r.json();
  };

  window.__b5_apiPrepare__ = async function(file, outDir){
    const r = await fetch('/api/athena/b5/manual/prepare',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({file, output_dir: outDir})
    });
    return await r.json();
  };

  window.__b5_apiPane__ = async function(file, sheet, i0, i1, family){
    const r = await fetch('/api/athena/b5/manual/pane',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({file, sheet, i0, i1, family})
    });
    return await r.json();
  };

  window.__b5_apiApply__ = async function(file, outDir, entries){
    const r = await fetch('/api/athena/b5/manual/apply',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({file, in_place:false, output_dir: outDir, entries})
    });
    return await r.json();
  };

  window.__b5_apiAdjustLabelWindow__ = async function(payload){
    const r = await fetch('/api/athena/b5/manual/adjust_label_window',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload || {})
    });
    return await r.json();
  };
});