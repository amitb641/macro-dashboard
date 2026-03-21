#!/usr/bin/env node
/**
 * Build stability checks for U.S. Macro Dashboard
 * Run: node tests/build-check.js
 *
 * Catches:
 *  - Unclosed/mismatched div tags per tab panel
 *  - Orphaned canvas elements (HTML exists, JS missing)
 *  - Missing DOM elements (JS references, HTML missing)
 *  - Broken iframe src references
 *  - JS syntax errors in script blocks
 *  - Unwired build functions
 */

const fs = require('fs');
const path = require('path');

const HTML_PATH = path.join(__dirname, '..', 'index.html');
const html = fs.readFileSync(HTML_PATH, 'utf8');

let passed = 0, failed = 0, warnings = 0;

function pass(msg) { console.log(`  \x1b[32m✓\x1b[0m ${msg}`); passed++; }
function fail(msg) { console.log(`  \x1b[31m✗\x1b[0m ${msg}`); failed++; }
function warn(msg) { console.log(`  \x1b[33m⚠\x1b[0m ${msg}`); warnings++; }

// ── 1. Div balance per tab-panel ──────────────────────────────────────────
console.log('\n\x1b[1m1. Tab Panel Div Balance\x1b[0m');
const tabPanelRe = /<div\s+class="tab-panel"\s+id="tab-([^"]+)">/g;
const tabIds = [];
let m;
while ((m = tabPanelRe.exec(html)) !== null) {
  tabIds.push({ id: m[1], start: m.index });
}

tabIds.forEach((tab, i) => {
  const end = i < tabIds.length - 1 ? tabIds[i + 1].start : html.length;
  const section = html.substring(tab.start, end);

  // Count opening divs (with attributes or bare)
  const opens = (section.match(/<div[\s>\/]/gi) || []).length;
  const closes = (section.match(/<\/div>/gi) || []).length;

  if (opens === closes) {
    pass(`tab-${tab.id}: ${opens} opens, ${closes} closes — balanced`);
  } else {
    fail(`tab-${tab.id}: ${opens} opens vs ${closes} closes — IMBALANCED (diff: ${opens - closes})`);
  }
});

// ── 2. Canvas ↔ JS wiring ────────────────────────────────────────────────
console.log('\n\x1b[1m2. Canvas ↔ JS Wiring\x1b[0m');
const canvasIds = [...html.matchAll(/<canvas\s+id="([^"]+)"/g)].map(m => m[1]);

canvasIds.forEach(id => {
  const jsRef = html.includes(`getElementById("${id}")`);
  if (jsRef) {
    pass(`canvas#${id} — wired to JS`);
  } else {
    fail(`canvas#${id} — NO JS reference found`);
  }
});

if (!canvasIds.length) warn('No canvas elements found');

// ── 3. DOM getElementById references ─────────────────────────────────────
console.log('\n\x1b[1m3. DOM Element References\x1b[0m');
const domRefs = [...html.matchAll(/getElementById\("([^"]+)"\)/g)].map(m => m[1]);
const uniqueRefs = [...new Set(domRefs)];
let missingEls = 0;

uniqueRefs.forEach(id => {
  const exists = html.includes(`id="${id}"`);
  if (!exists) {
    fail(`getElementById("${id}") — element NOT found in HTML`);
    missingEls++;
  }
});

if (missingEls === 0) pass(`All ${uniqueRefs.length} getElementById targets exist in HTML`);

// ── 4. Build function wiring ─────────────────────────────────────────────
console.log('\n\x1b[1m4. Build Function ↔ Tab Switcher\x1b[0m');
const buildFns = [...html.matchAll(/function\s+(build\w+Tab)\s*\(\)/g)].map(m => m[1]);
const tabSwitcherBlock = html.substring(
  html.indexOf('// TAB SWITCHING') || 0,
  html.indexOf('// TAB SWITCHING') + 2000
);

buildFns.forEach(fn => {
  const calledInSwitcher = tabSwitcherBlock.includes(`${fn}()`);
  if (calledInSwitcher) {
    pass(`${fn}() — called in tab switcher`);
  } else {
    fail(`${fn}() — NOT called in tab switcher`);
  }
});

// ── 5. iframe src file references ────────────────────────────────────────
console.log('\n\x1b[1m5. iframe Source Files\x1b[0m');
const iframeSrcs = [...html.matchAll(/<iframe[^>]+src="([^"]+)"/g)].map(m => m[1]);
const baseDir = path.dirname(HTML_PATH);

if (!iframeSrcs.length) {
  pass('No iframes to check');
} else {
  iframeSrcs.forEach(src => {
    const fullPath = path.resolve(baseDir, src);
    if (fs.existsSync(fullPath)) {
      pass(`iframe src="${src}" — file exists`);
    } else {
      fail(`iframe src="${src}" — FILE NOT FOUND at ${fullPath}`);
    }
  });
}

// ── 6. JS syntax validation ─────────────────────────────────────────────
console.log('\n\x1b[1m6. JavaScript Syntax\x1b[0m');
const scriptBlocks = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)];

scriptBlocks.forEach((m, i) => {
  try {
    new Function(m[1]);
    pass(`Script block ${i + 1} — syntax OK (${m[1].length} chars)`);
  } catch (e) {
    fail(`Script block ${i + 1} — SYNTAX ERROR: ${e.message}`);
  }
});

// ── 7. Data variable completeness ────────────────────────────────────────
console.log('\n\x1b[1m7. Data Variables\x1b[0m');
const dataConsts = [...html.matchAll(/const\s+([A-Z][A-Z_0-9]+)\s*=/g)].map(m => m[1]);
const uniqueData = [...new Set(dataConsts)];

uniqueData.forEach(name => {
  // Count references (excluding the declaration itself)
  const refCount = (html.match(new RegExp(`\\b${name}\\b`, 'g')) || []).length;
  if (refCount <= 1) {
    warn(`${name} — declared but only referenced ${refCount} time(s) (possibly unused)`);
  }
});
pass(`${uniqueData.length} data constants found`);

// ── 8. Active tab default ────────────────────────────────────────────────
console.log('\n\x1b[1m8. Default Active Tab\x1b[0m');
const activeTabMatch = html.match(/<div\s+class="tab-panel\s+active"\s+id="tab-([^"]+)">/);
if (activeTabMatch) {
  pass(`Default active tab: tab-${activeTabMatch[1]}`);
} else {
  warn('No default active tab found — page may load blank');
}

const activeNavMatch = html.match(/class="nav-btn\s+active"[^>]*data-tab="([^"]+)"/);
if (activeNavMatch) {
  pass(`Default active nav button: ${activeNavMatch[1]}`);
  if (activeTabMatch && activeNavMatch[1] !== activeTabMatch[1]) {
    fail(`Nav button (${activeNavMatch[1]}) and tab panel (${activeTabMatch[1]}) don't match!`);
  }
}

// ── Summary ──────────────────────────────────────────────────────────────
console.log('\n' + '─'.repeat(50));
console.log(`\x1b[1mResults: ${passed} passed, ${failed} failed, ${warnings} warnings\x1b[0m`);
if (failed > 0) {
  console.log('\x1b[31m\x1b[1mBUILD CHECK FAILED\x1b[0m\n');
  process.exit(1);
} else {
  console.log('\x1b[32m\x1b[1mBUILD CHECK PASSED\x1b[0m\n');
  process.exit(0);
}
