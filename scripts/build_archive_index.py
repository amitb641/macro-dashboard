#!/usr/bin/env python3
"""
Monthly Archive Index Builder — rebuilds a queryable SQLite index from
data/monthly_archive/*/manifest.json + metrics.json.

This database is a DERIVED artifact, not a source of truth, and is
deliberately NOT committed to git (see .gitignore) — the plain JSON/HTML
files under data/monthly_archive/ are the durable record; this is just a
fast query layer rebuilt on demand. Full rebuild is a full DROP+recreate
every run (not an incremental upsert) — at this volume (tens to a few
hundred months, ever) a full rebuild is milliseconds, so there's no
reason to carry the complexity of incremental-update logic or worry about
the index drifting out of sync with the source files.

Schema (see SCHEMA_SQL below):
  monthly_snapshots — one row per archived month (metadata)
  monthly_metrics   — long/tidy format, one row per (month, series_id)
  schema_meta       — key/value bookkeeping (schema version, build time)

Example queries once built:
  sqlite3 data/monthly_archive.db \
    "SELECT month, value FROM monthly_metrics WHERE series_id='unrate' ORDER BY month;"

  sqlite3 data/monthly_archive.db \
    "SELECT month, validation_status, ceo_grade_verdict FROM monthly_snapshots ORDER BY month DESC LIMIT 12;"

Usage: python scripts/build_archive_index.py [--db-path PATH]
"""

import argparse, json, sqlite3, sys, datetime
from pathlib import Path

ROOT        = Path(__file__).parent.parent
ARCHIVE_DIR = ROOT / 'data' / 'monthly_archive'
DB_PATH     = ROOT / 'data' / 'monthly_archive.db'

SCHEMA_SQL = """
CREATE TABLE monthly_snapshots (
  month                 TEXT PRIMARY KEY,   -- 'YYYY-MM'
  source_run_date       TEXT NOT NULL,      -- 'YYYY-MM-DD' run that produced this record
  archived_at           TEXT NOT NULL,      -- ISO timestamp
  git_sha               TEXT,
  branch                TEXT,
  validation_status     TEXT,
  ceo_grade_verdict     TEXT,
  critical_divergences  INTEGER,
  html_sha256           TEXT,
  html_path             TEXT,               -- relative to repo root
  raw_data_sha256       TEXT,
  schema_version        INTEGER NOT NULL
);

CREATE TABLE monthly_metrics (
  month      TEXT NOT NULL,
  series_id  TEXT NOT NULL,
  label      TEXT,
  value      REAL,
  unit       TEXT,
  PRIMARY KEY (month, series_id),
  FOREIGN KEY (month) REFERENCES monthly_snapshots(month)
);
CREATE INDEX idx_metrics_series ON monthly_metrics(series_id);

CREATE TABLE schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""


def build(db_path: Path = DB_PATH) -> int:
    """Full rebuild. Returns the number of months indexed."""
    if not ARCHIVE_DIR.exists():
        print(f'[Archive Index] {ARCHIVE_DIR} does not exist yet — nothing to index')
        return 0

    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)

    n = 0
    for month_dir in sorted(d for d in ARCHIVE_DIR.iterdir() if d.is_dir()):
        manifest_path = month_dir / 'manifest.json'
        if not manifest_path.exists():
            print(f'[Archive Index] Skipping {month_dir.name} — no manifest.json')
            continue
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        month = manifest.get('month', month_dir.name)
        val_summary = manifest.get('validation_summary', {}) or {}

        conn.execute(
            """INSERT INTO monthly_snapshots
               (month, source_run_date, archived_at, git_sha, branch,
                validation_status, ceo_grade_verdict, critical_divergences,
                html_sha256, html_path, raw_data_sha256, schema_version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                month,
                manifest.get('source_run_date'),
                manifest.get('archived_at'),
                manifest.get('git_sha'),
                manifest.get('branch'),
                manifest.get('validation_status'),
                manifest.get('ceo_grade_verdict'),
                val_summary.get('critical_divergences'),
                manifest.get('sha256', {}).get('index.html'),
                f'data/monthly_archive/{month_dir.name}/index.html',
                manifest.get('sha256', {}).get('raw_data.json'),
                manifest.get('schema_version', 1),
            ),
        )

        metrics_path = month_dir / 'metrics.json'
        if metrics_path.exists():
            metrics = json.loads(metrics_path.read_text(encoding='utf-8'))
            for m in metrics.get('metrics', []):
                conn.execute(
                    """INSERT OR REPLACE INTO monthly_metrics
                       (month, series_id, label, value, unit) VALUES (?,?,?,?,?)""",
                    (month, m['series_id'], m.get('label'), m.get('value'), m.get('unit')),
                )
        n += 1

    conn.execute("INSERT INTO schema_meta (key, value) VALUES ('version', '1')")
    conn.execute(
        "INSERT INTO schema_meta (key, value) VALUES ('built_at', ?)",
        (datetime.datetime.utcnow().isoformat() + 'Z',),
    )
    conn.commit()
    conn.close()

    print(f'[Archive Index] Rebuilt {db_path} — {n} month(s) indexed')
    return n


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db-path', type=Path, default=DB_PATH)
    args = p.parse_args()
    build(args.db_path)
