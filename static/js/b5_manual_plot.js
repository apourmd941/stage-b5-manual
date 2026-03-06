/* File: athena/wizard/b5_manual_plot.js
 * Version: v1.0 — Manual B5 plotting + marker rendering
 */

onReady(function(){
  const plotEl = document.getElementById('manualPlot');
  if (!plotEl) return;

  const elPaneLabel = document.getElementById('manPaneLabel');

  function updateModeButtons(){
    const st = window.__B5MAN__;
    const peakBtn = document.getElementById('manModePeak');
    const valBtn  = document.getElementById('manModeValley');

    if (peakBtn){
      peakBtn.style.background = (st.mode==='peak') ? '#007bff' : '#eee';
      peakBtn.style.color      = (st.mode==='peak') ? '#fff'    : '#111';
    }
    if (valBtn){
      valBtn.style.background = (st.mode==='valley') ? '#ff7f0e' : '#eee';
      valBtn.style.color      = (st.mode==='valley') ? '#fff'    : '#111';
    }
  }

  function updateReverseButton(){
    const btn = document.getElementById('manReverse');
    if (!btn) return;
    const p = window.__b5_currentPane__();
    if (!p){
      btn.style.background = '#eee';
      btn.style.color = '#111';
      return;
    }
    const on = window.__b5_isReverseOn__();
    btn.style.background = on ? '#6f42c1' : '#eee';
    btn.style.color = on ? '#fff' : '#111';
  }

  function updatePaneLabel(){
    const st = window.__B5MAN__;
    const p = window.__b5_currentPane__();
    if (!p || !elPaneLabel) return;

    const rev = window.__b5_isReverseOn__() ? 'ON' : 'OFF';
    const chans = (st.channels && st.channels.length) ? st.channels.join(' • ') : '';

    let qcBadge = '';
    try{
      const qc = st.qc;
      if (qc && qc.status === 'warn'){
        const flags = Array.isArray(qc.flags) ? qc.flags : [];
        qcBadge = ' | ⚠ ' + (flags.length ? flags.join(',') : 'qc');
      } else if (qc && qc.status === 'ok'){
        qcBadge = ' | ✅';
      } else {
        qcBadge = '';
      }
    }catch(_){
      qcBadge = '';
    }

    elPaneLabel.textContent =
      p.sheet + ' | ' + p.movement + ' | ' + p.family +
      ' | Reverse: ' + rev +
      qcBadge +
      (chans ? (' | ' + chans) : '') +
      ' (pane ' + (st.paneIndex+1) + '/' + st.panes.length + ')';
  }

  function nearestIndex(frames, x){
    let i=0, best=1e12;
    for (let k=0;k<frames.length;k++){
      const d=Math.abs(frames[k]-x);
      if (d<best){best=d;i=k;}
    }
    return i;
  }

  function buildMarkerShapes(st, p){
    const key = window.__b5_clickKey__(p);
    const store = st.clicks[key] || {};
    const shapes = [];
    for (const ch of st.channels){
      const slot = store[ch] || {peaks:[], valleys:[]};
      (slot.peaks||[]).forEach(abs=>{
        const rel = abs - p.i0;
        if (rel>=0 && rel<st.frames.length){
          const x = st.frames[rel];
          shapes.push({ type:'line', x0:x, x1:x, xref:'x', yref:'paper', y0:0, y1:1,
                        line:{ dash:'dash', color:'#1f77b4', width:1.5 }});
        }
      });
      (slot.valleys||[]).forEach(abs=>{
        const rel = abs - p.i0;
        if (rel>=0 && rel<st.frames.length){
          const x = st.frames[rel];
          shapes.push({ type:'line', x0:x, x1:x, xref:'x', yref:'paper', y0:0, y1:1,
                        line:{ dash:'dash', color:'#ff7f0e', width:1.5 }});
        }
      });
    }
    return shapes;
  }

  window.__b5_redrawPlot__ = function(){
    const st = window.__B5MAN__;
    const p = window.__b5_currentPane__();
    if (!p) return;

    const data = st.channels.map((ch, ci)=>({
      x: st.frames,
      y: st.series[ch],
      type:'scatter',
      mode:'lines',
      name: ch,
      line:{ width: (ci===st.chIndex)? 3 : 1.25 },
      opacity: (ci===st.chIndex)? 1.0 : 0.6,
      hoverinfo:'none',
      hovertemplate:null
    }));

    const layout = {
      margin:{l:60,r:10,t:30,b:40},
      legend:{orientation:'h', y:-0.2},
      hovermode:'x unified',
      hoverlabel:{ bgcolor:'rgba(0,0,0,0)', bordercolor:'rgba(0,0,0,0)', font:{color:'rgba(0,0,0,0)'} },
      xaxis:{ showspikes:true, spikemode:'across', spikesnap:'cursor', spikethickness:1, spikedash:'solid' },
      yaxis:{ showspikes:false },
      dragmode:'pan',
      shapes: buildMarkerShapes(st, p)
    };

    const config = { responsive:true, displaylogo:false };
    window.Plotly.react(plotEl, data, layout, config);
  };

  window.__b5_plot_bindHandlers__ = function(){
    const st = window.__B5MAN__;
    const p = window.__b5_currentPane__();
    if (!p) return;

    // clear old listeners safely
    try{
      plotEl.removeAllListeners && plotEl.removeAllListeners('plotly_click');
      plotEl.removeAllListeners && plotEl.removeAllListeners('plotly_legendclick');
      plotEl.removeAllListeners && plotEl.removeAllListeners('plotly_hover');
      plotEl.removeAllListeners && plotEl.removeAllListeners('plotly_unhover');
    }catch(_){}

    plotEl.on('plotly_click', function(evt){
      const st = window.__B5MAN__;
      const p = window.__b5_currentPane__();
      if (!p) return;

      if (!st.mode) return;

      const pt = evt.points && evt.points[0];
      if (!pt) return;

      const idx = nearestIndex(st.frames, pt.x);
      const abs = p.i0 + idx;

      const key = window.__b5_clickKey__(p);
      const paneKey = window.__b5_paneKey__(p);
      const ch  = st.channels[st.chIndex] || st.channels[0];
      const store = (st.clicks[key] ||= {});
      const slot  = (store[ch] ||= {peaks:[], valleys:[]});

      const isRev = !!st.reversePanes[paneKey];
      const effectiveMode = isRev ? (st.mode === 'peak' ? 'valley' : 'peak') : st.mode;

      const TOL = 20;
      function deleteNearest(list){
        if (!list || !list.length) return false;
        let bestIdx = -1, bestDist = Infinity;
        for (let i=0;i<list.length;i++){
          const d = Math.abs(list[i] - abs);
          if (d < bestDist){ bestDist = d; bestIdx = i; }
        }
        if (bestIdx >= 0 && bestDist <= TOL){
          list.splice(bestIdx, 1);
          return true;
        }
        return false;
      }

      if (effectiveMode === 'peak'){
        if (!deleteNearest(slot.peaks)){
          if (slot.peaks.indexOf(abs) < 0) slot.peaks.push(abs);
          slot.peaks.sort((a,b)=>a-b);
        }
      } else {
        if (!deleteNearest(slot.valleys)){
          if (slot.valleys.indexOf(abs) < 0) slot.valleys.push(abs);
          slot.valleys = Array.from(new Set(slot.valleys)).sort((a,b)=>a-b);
        }
      }

      window.__b5_saveResumeState__();
      window.__b5_redrawPlot__();
    });

    plotEl.on('plotly_legendclick', function(e){
      try{
        const chName = e && e.data && e.data[e.curveNumber] && e.data[e.curveNumber].name;
        const idx = window.__B5MAN__.channels.indexOf(chName);
        if (idx >= 0){
          window.__B5MAN__.chIndex = idx;
          window.__b5_redrawPlot__();
        }
      }catch(_){}
      return false;
    });

    plotEl.on('plotly_hover', function(evt){
      const pt = evt.points && evt.points[0];
      if (pt){ window.__B5MAN__._lastHoverX = pt.x; }
    });
    plotEl.on('plotly_unhover', function(){
      window.__B5MAN__._lastHoverX = null;
    });
  };

  // expose label/button updaters for UI module
  window.__b5_updateModeButtons__ = updateModeButtons;
  window.__b5_updateReverseButton__ = updateReverseButton;
  window.__b5_updatePaneLabel__ = updatePaneLabel;
});
