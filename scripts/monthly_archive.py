#!/usr/bin/env python3
"""
Monthly Archive — durable, unpruned historical record of the dashboard.

Distinct from snapshot.py (rolling, capped at a few runs, exists for
operational rollback) — this is the permanent archive: one directory per
calendar month, upserted on every pipeline run, NEVER pruned. Volume is
tiny (~2-3 MB/month of raw_data.json + index.html), so "keep forever" is
the right default at this scale — do not add a retention cap here without
re-deriving the cost/benefit, this table's entire purpose is being the
long-term record snapshot.py deliberately isn't.

Semantics: keyed by calendar month, not run date. Every pipeline run this
month overwrites data/monthly_archive/<YYYY-MM>/ in place, so whatever the
LAST successful run within a month writes is what survives once the next
month's directory is created. No special "is this the final run of the
month" trigger logic needed — upsert-by-month gives that for free.

Each month directory contains:
  manifest.json  — run metadata: dates, git sha/branch, validation status,
                   CEO-grade verdict (if produced by this branch's
                   pipeline), file sizes + sha256 checksums
  metrics.json   — tidy long-format snapshot of signals.json's ~30 scalar
                   values (unemployment, CPI, Fed funds, etc.) — the fast
                   path for trend queries without parsing raw_data.json
  raw_data.json  — full API pull, same as snapshot.py captures
  state.json     — Tier-1 chart payload (dev only; absent on main — this
                   script is written to work identically on both, every
                   optional file is existence-gated)
  index.html     — full rendered dashboard as of that month

This script must never fail the pipeline — archiving history is valuable
but not worth blocking a live publish over. All I/O is wrapped; on any
error this prints a warning and exits 0.

The queryable SQLite index (data/monthly_archive.db) is a SEPARATE,
on-demand build step — see build_archive_index.py. It is intentionally
not committed to git (rebuild is <1s from these manifests; a binary DB
file would bloat every commit with an undiffable blob for zero benefit).

Usage: python scripts/monthly_archive.py
"""

import hashlib, json, shutil, sys, datetime, subprocess
from pathlib import Path

ROOT         = Path(__file__).parent.parent
DATA_DIR     = ROOT / 'data'
ARCHIVE_DIR  = DATA_DIR / 'monthly_archive'
RAW_FILE     = DATA_DIR / 'raw_data.json'
STATE_FILE   = DATA_DIR / 'state.json'
SIG_FILE     = DATA_DIR / 'signals.json'
VAL_FILE     = DATA_DIR / 'validation_report.json'
CEO_FILE     = DATA_DIR / 'ceo_grade_verdict.json'
HTML_FILE    = ROOT / 'index.html'

SCHEMA_VERSION = 1

# Labels + units for the metrics.json tidy export. Only series_ids present
# in signals.json's `values` dict at run time are written — this list is
# just presentation metadata, not a completeness requirement.
METRIC_META = {
    'unrate':        ('Unemployment Rate', '%'),
    'u6rate':        ('U-6 Underemployment Rate', '%'),
    'cpi_yoy':       ('Headline CPI YoY', '%'),
    'core_cpi_yoy':  ('Core CPI YoY', '%'),
    'pce_yoy':       ('Headline PCE YoY', '%'),
    'core_pce_yoy':  ('Core PCE YoY', '%'),
    'ffr':           ('Fed Funds Rate', '%'),
    'dgs2':          ('2Y Treasury', '%'),
    'dgs5':          ('5Y Treasury', '%'),
    'dgs10':         ('10Y Treasury', '%'),
    'dgs30':         ('30Y Treasury', '%'),
    'spread_10_2_bp':('10Y-2Y Spread', 'bp'),
    'mortgage30':    ('30yr Mortgage Rate', '%'),
    'wti':           ('WTI Crude', '$/bbl'),
    'brent':         ('Brent Crude', '$/bbl'),
    'umcsent':       ('UMich Consumer Sentiment', 'index'),
    'saving_rate':   ('Personal Saving Rate', '%'),
    'tdsp':          ('Debt Service Ratio', '%'),
    'cc_delinq':     ('CC 90+ DPD Rate', '%'),
    'nfp_mom':       ('Nonfarm Payrolls MoM', 'K'),
    'nfp_level':     ('Nonfarm Payrolls Level', 'K'),
    'wages_yoy':     ('Wage Growth YoY', '%'),
    'atl_wage_3m':   ('Atlanta Fed Wage Tracker 3MMA', '%'),
    'gdp_growth_q':  ('Real GDP Growth (Quarterly Annualized)', '%'),
    'housing_starts':('Housing Starts', 'K SAAR'),
    'cs_hpi_yoy':    ('Case-Shiller Home Price YoY', '%'),
    'ig_oas':        ('IG Credit Spread (OAS)', 'bp'),
    'hy_oas':        ('HY Credit Spread (OAS)', 'bp'),
    'icsa':          ('Initial Jobless Claims', ''),
    'ccsa':          ('Continued Jobless Claims', ''),
}


def _sha256(path: Path) -> str:
    if not path.exists():
        return ''
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _git_sha() -> str:
    try:
        r = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                            capture_output=True, text=True, timeout=5, cwd=str(ROOT))
        return r.stdout.strip() if r.returncode == 0 else 'unknown'
    except Exception:
        return 'unknown'


def _git_branch() -> str:
    try:
        r = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                            capture_output=True, text=True, timeout=5, cwd=str(ROOT))
        return r.stdout.strip() if r.returncode == 0 else 'unknown'
    except Exception:
        return 'unknown'


def _build_metrics_json(month: str, run_date: str) -> dict:
    """Tidy long-format export of signals.json's scalar values."""
    metrics = []
    if SIG_FILE.exists():
        sig = json.loads(SIG_FILE.read_text(encoding='utf-8'))
        for series_id, value in sorted(sig.get('values', {}).items()):
            if value is None:
                continue
            label, unit = METRIC_META.get(series_id, (series_id, ''))
            metrics.append({
                'series_id': series_id,
                'label': label,
                'value': value,
                'unit': unit,
            })
    return {'month': month, 'obs_date': run_date, 'metrics': metrics}


def archive_month():
    """Upsert this calendar month's archive directory. Never raises."""
    try:
        now = datetime.datetime.utcnow()
        month = now.strftime('%Y-%m')
        run_date = now.strftime('%Y-%m-%d')
        month_dir = ARCHIVE_DIR / month
        month_dir.mkdir(parents=True, exist_ok=True)

        sources = [RAW_FILE, STATE_FILE, HTML_FILE]
        copied, sizes = [], {}
        for src in sources:
            if src.exists():
                dest = month_dir / src.name
                shutil.copy2(src, dest)
                copied.append(src.name)
                sizes[src.name] = src.stat().st_size

        metrics = _build_metrics_json(month, run_date)
        (month_dir / 'metrics.json').write_text(
            json.dumps(metrics, indent=2), encoding='utf-8')
        copied.append('metrics.json')
        sizes['metrics.json'] = (month_dir / 'metrics.json').stat().st_size

        manifest = {
            'schema_version': SCHEMA_VERSION,
            'month': month,
            'source_run_date': run_date,
            'archived_at': now.isoformat() + 'Z',
            'git_sha': _git_sha(),
            'branch': _git_branch(),
            'files': copied,
            'sizes': sizes,
            'sha256': {name: _sha256(month_dir / name) for name in copied},
        }

        if VAL_FILE.exists():
            try:
                val = json.loads(VAL_FILE.read_text(encoding='utf-8'))
                manifest['validation_status'] = val.get('status', 'unknown')
                manifest['validation_summary'] = val.get('summary', {})
            except Exception:
                pass

        if CEO_FILE.exists():
            try:
                ceo = json.loads(CEO_FILE.read_text(encoding='utf-8'))
                manifest['ceo_grade_verdict'] = ceo.get('overall', 'unknown')
            except Exception:
                pass

        (month_dir / 'manifest.json').write_text(
            json.dumps(manifest, indent=2), encoding='utf-8')

        total_kb = sum(sizes.values()) / 1024
        print(f'[Monthly Archive] Upserted {month} '
              f'({total_kb:.0f} KB across {len(copied) + 1} file(s), '
              f'{len(metrics["metrics"])} metrics) — run {run_date}')

        # How many months are archived so far (informational only — never pruned).
        n_months = len([d for d in ARCHIVE_DIR.iterdir() if d.is_dir()]) if ARCHIVE_DIR.exists() else 0
        print(f'[Monthly Archive] {n_months} month(s) on record (permanent — no pruning)')

    except Exception as e:
        # Archiving must never take down the pipeline.
        print(f'[Monthly Archive] WARNING — archive step failed non-fatally: {e}')


if __name__ == '__main__':
    archive_month()
    sys.exit(0)
