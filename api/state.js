// /api/state.json — gated delivery of the dashboard state bundle.
//
// Why this exists
// ---------------
// The dashboard was historically a static HTML file with every chart
// dataset inlined as a `const X = [...]`. That made the site trivially
// scrapeable / cloneable — a curl of `index.html` exposed the entire
// data layer in plain JSON. This endpoint moves the data behind an
// Origin-gated function so a clone hosted elsewhere cannot pull
// against our deployment.
//
// What it does NOT do
// -------------------
// This is *deterrence*, not authentication. An attacker willing to
// spoof an Origin header via curl can still pull the payload. The
// goal is to defeat casual scrapers and copy-paste cloners that use
// a browser, where the same-origin policy + the Origin header check
// below combine to block cross-site fetches.
//
// Allowed origins
// ---------------
// - The Vercel deploy URL itself (resolved via VERCEL_URL env var)
// - Any host listed in ALLOWED_ORIGINS (comma-separated)
// - localhost / 127.0.0.1 on any port (dev convenience)
// - Empty Origin header (legitimate same-origin nav from index.html;
//   modern browsers omit it on same-origin GETs)

const fs = require('fs');
const path = require('path');

function _allowed(origin) {
  if (!origin) return true; // same-origin GET — browsers omit Origin
  try {
    const u = new URL(origin);
    const host = u.hostname;
    if (host === 'localhost' || host === '127.0.0.1') return true;
    if (host.endsWith('.vercel.app')) {
      // Trust *.vercel.app (covers preview deploys + dev URL).
      // Tighten this list once the prod domain is fixed.
      return true;
    }
    const envOrigin = process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : '';
    if (envOrigin && origin === envOrigin) return true;
    const extra = (process.env.ALLOWED_ORIGINS || '')
      .split(',').map(s => s.trim()).filter(Boolean);
    if (extra.includes(origin)) return true;
    if (extra.includes(host)) return true;
    return false;
  } catch (_) {
    return false;
  }
}

module.exports = async function handler(req, res) {
  // Only GET / HEAD.
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.statusCode = 405;
    res.setHeader('Allow', 'GET, HEAD');
    return res.end('method not allowed');
  }

  const origin = req.headers.origin || '';
  const referer = req.headers.referer || '';
  // Referer fallback — when Origin is absent but Referer points
  // somewhere foreign, refuse. (Browser-initiated cross-origin fetches
  // set both; curl can leave both blank, which we allow same-origin.)
  const ok = _allowed(origin) && (referer === '' || _allowed(new URL(referer).origin));
  if (!ok) {
    res.statusCode = 403;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    return res.end(JSON.stringify({ error: 'origin not allowed' }));
  }

  // Strict CORS — echo back only allowed origins, never *.
  if (origin) res.setHeader('Access-Control-Allow-Origin', origin);
  res.setHeader('Vary', 'Origin');
  res.setHeader('Cache-Control', 'no-store, max-age=0');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');

  // Read the state bundle from the deployment.
  // Vercel serverless functions can read files from the project root
  // bundled at build time.
  const statePath = path.join(process.cwd(), 'data', 'state.json');
  try {
    const buf = fs.readFileSync(statePath);
    res.statusCode = 200;
    if (req.method === 'HEAD') return res.end();
    return res.end(buf);
  } catch (e) {
    res.statusCode = 503;
    return res.end(JSON.stringify({ error: 'state unavailable', detail: String(e && e.code || e) }));
  }
};
