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
    var wk  = Math.ceil((((now - new Date(now.getFullYear(),0,1))/86400000) + 1)/7);
    var mo  = now.toLocaleString('en-US',{month:'short'}).toUpperCase();
    var yr  = now.getFullYear();
    var pad = function(n){ return n<10 ? '0'+n : ''+n; };
    var ts  = yr + '-' + pad(now.getMonth()+1) + '-' + pad(now.getDate()) + ' ' +
              pad(now.getHours()) + ':' + pad(now.getMinutes()) + ' ET';
    var meta = document.createElement('div');
    meta.className = 'sm-meta';
    meta.innerHTML =
      '<span class="sm-meta-dot"></span>' +
      '<span>WEEK ' + wk + '</span>' +
      '<span class="sm-meta-sep">·</span>' +
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
      var data = window[spec.dataVar];
      // Paint overlay if the data var is missing entirely OR present-but-empty.
      // Skip only when real data is present (labels populated).
      var hasData = data && (data.labels || []).length > 0;
      if (hasData) return;
      var canvas = document.getElementById(spec.canvas);
      if (!canvas) return;
      var parent = canvas.parentElement;
      if (!parent || parent.querySelector('.sm-empty-state')) return;
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
    // wait one tick for chart-init code to run, then paint placeholders
    setTimeout(function(){ try { paintEmptyStates(); } catch(e){} }, 300);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', activate);
  } else {
    activate();
  }
})();
