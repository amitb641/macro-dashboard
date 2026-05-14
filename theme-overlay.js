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
  function activate(){
    document.body.classList.add('themed-sm');
    try { injectMetaStrip(); } catch(e){}
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', activate);
  } else {
    activate();
  }
})();
