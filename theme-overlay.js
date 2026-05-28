// ═════════════════════════════════════════════════════════════════
//  SYSTEM-MAP THEME OVERLAY ACTIVATOR (B7)
//  - Adds `themed-sm` class on body so the CSS overlay applies.
//  - Injects the meta strip (WEEK · MONTH · PIPELINE OK · LAST RUN).
//  - SKIPS section-header injection from the original mockup,
//    because that JS used a hardcoded TAB_HEAD map that would now
//    conflict with new tabs added post-mockup (Fiscal, etc.).
// ═════════════════════════════════════════════════════════════════
(function(){
  function injectMetaStrip(){
    if (document.querySelector('.sm-meta')) return;
    var eyebrow = document.querySelector('body > .eyebrow');
    if (!eyebrow) return;
    var now = new Date();
    // WEEK is already on the wordmark above; sm-meta carries the
    // pieces the wordmark doesn't (month-year + operational status).
    var mo  = now.toLocaleString('en-US',{month:'short'}).toUpperCase();
    var yr  = now.getFullYear();
    var pad = function(n){ return n<10 ? '0'+n : ''+n; };
    var ts  = yr + '-' + pad(now.getMonth()+1) + '-' + pad(now.getDate()) + ' ' +
              pad(now.getHours()) + ':' + pad(now.getMinutes()) + ' ET';
    var meta = document.createElement('div');
    meta.className = 'sm-meta';
    meta.innerHTML =
      '<span class="sm-meta-dot"></span>' +
      '<span>' + mo + ' ' + yr + '</span>' +
      '<span class="sm-meta-sep">·</span>' +
      '<span class="sm-meta-bold">PIPELINE OK</span>' +
      '<span class="sm-meta-sep">·</span>' +
      '<span>LAST RUN ' + ts + '</span>';
    eyebrow.parentNode.insertBefore(meta, eyebrow);
  }
  // ── empty-state overlay for B3 charts whose data hasn't been
  //    fetched yet (collector adds the series in B3; first CI run
  //    after merge to main populates raw_data.json). Until then
  //    show a subtle "awaiting first pipeline run" placeholder.
  function paintEmptyStates(){
    var emptyMap = [
      { canvas: 'c-jolts',         dataVar: 'JOLTS_DATA',         label: 'JOLTS labour-churn data' },
      { canvas: 'c-fed-liquidity', dataVar: 'FED_LIQUIDITY_DATA', label: 'Fed H.4.1 balance-sheet data' },
      { canvas: 'c-cpi-breadth',   dataVar: 'CPI_BREADTH',        label: 'Cleveland Fed trimmed/median CPI' }
    ];
    emptyMap.forEach(function(spec){
      var canvas = document.getElementById(spec.canvas);
      if (!canvas) return;
      var parent = canvas.parentElement;
      if (!parent) return;
      // Check data multiple ways — the data vars are declared `let` in
      // the inline <script> in index.html, so they're NOT on `window`
      // even after hydration. Instead, look at the actual Chart.js
      // instance attached to the canvas: if Chart.getChart() returns
      // a chart with non-empty labels, real data has rendered. Fall
      // back to window[varName] for any future migration that does
      // expose vars globally.
      var data = window[spec.dataVar];
      var chart = (window.Chart && window.Chart.getChart) ? window.Chart.getChart(canvas) : null;
      var hasData =
        (chart && chart.data && (chart.data.labels || []).length > 0) ||
        (data  && (data.labels  || []).length > 0);
      var existing = parent.querySelector('.sm-empty-state');
      if (hasData) {
        if (existing) existing.remove();
        return;
      }
      if (existing) return;
      var overlay = document.createElement('div');
      overlay.className = 'sm-empty-state';
      overlay.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px;font-family:"DM Mono",monospace;color:#5A6B7D;font-size:11px;letter-spacing:.12em;text-transform:uppercase;text-align:center;padding:24px;pointer-events:none;';
      overlay.innerHTML =
        '<div style="font-size:22px;opacity:.5">◌</div>' +
        '<div style="font-weight:700;color:#5A6B7D">Awaiting first pipeline run</div>' +
        '<div style="text-transform:none;letter-spacing:.02em;font-family:\'DM Sans\',sans-serif;font-size:12px;color:#5A6B7D;max-width:380px;line-height:1.5">' +
          spec.label + ' was added to the collector this week. Series will populate on the next weekly CI run (Sat 08:00 ET).' +
        '</div>';
      // make parent relative so absolute overlay sits inside
      var p = getComputedStyle(parent).position;
      if (p === 'static') parent.style.position = 'relative';
      parent.appendChild(overlay);
    });
  }

  function activate(){
    document.body.classList.add('themed-sm');
    try { injectMetaStrip(); } catch(e){}
    // wait one tick for chart-init code to run, then paint placeholders.
    // Re-run at +2s so any late-hydrating data var (cached HTML, delayed
    // inline-script execution) still clears a stale overlay.
    setTimeout(function(){ try { paintEmptyStates(); } catch(e){} }, 300);
    setTimeout(function(){ try { paintEmptyStates(); } catch(e){} }, 2000);
    // Hook into the hydration system so the overlay is re-evaluated
    // after /api/state.json resolves. Without this, the placeholder
    // painted at 300/2000ms (before slow-mobile hydration completes)
    // stayed forever even after FED_LIQUIDITY_DATA etc. populated —
    // the chart drew real data underneath but the "Awaiting first
    // pipeline run" overlay never lifted.
    try {
      window.MD = window.MD || {};
      if (window.MD._hydrationDone) {
        setTimeout(function(){ try { paintEmptyStates(); } catch(e){} }, 100);
      } else {
        window.MD._hydrationCallbacks = window.MD._hydrationCallbacks || [];
        window.MD._hydrationCallbacks.push(function(){
          setTimeout(function(){ try { paintEmptyStates(); } catch(e){} }, 100);
        });
      }
    } catch(e){}
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', activate);
  } else {
    activate();
  }
})();
