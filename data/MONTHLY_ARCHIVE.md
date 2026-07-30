# Monthly Archive — Schema, Pipeline, and Operating Recommendations

Added 2026-07-30. This is the durable historical record of the dashboard —
distinct from `scripts/snapshot.py`'s rolling backups, which are capped
and exist purely for operational rollback. This document is the source
of truth for how the archive works; `CLAUDE.md` only points here.

## Why this exists

Before this, nothing in the pipeline survived past its retention cap:
`snapshot.py` keeps 3 (main) or 52 (dev) runs, `pipeline_version.json`
keeps 4, `kpis_history.json` keeps 104. All of them are keyed by *pipeline
run date*, not calendar month, and all of them prune. There was no
permanent, queryable record of "what did the dashboard say in a given
month" beyond those windows.

## Architecture: source of truth vs. query layer

Two separate things, deliberately not merged into one:

1. **`data/monthly_archive/YYYY-MM/`** — plain files, committed to git,
   **never pruned**. This is the durable source of truth. Git itself is
   the backup/replication mechanism: every clone of the repo is a full
   copy of the entire archive, for free, with no separate backup system
   to run or pay for.
2. **`data/monthly_archive.db`** (SQLite) — a *derived, rebuildable* query
   index, **not committed** (see `.gitignore`). Rebuilt from the plain
   files in under a second by `scripts/build_archive_index.py`. This
   exists purely so you can run SQL instead of parsing dozens of JSON
   files by hand.

**Why SQLite and not a hosted database (Postgres/MySQL/etc.)**: this
archive grows at ~12 rows/year. Even a decade of history is a few hundred
rows and well under 50 MB. A client-server RDBMS would mean provisioning,
patching, and paying for a server that sits mostly idle, for a workload
SQLite handles instantly from a single file — and it would break this
project's fully-static deployment model (GitHub Pages + Vercel serverless
functions, no persistent backend). Reach for a real server-based DB only
if query volume, concurrent-writer count, or data size actually change by
orders of magnitude from what a monthly macro dashboard produces.

**Why the SQLite file isn't committed**: binary files can't be diffed by
git, so committing a `.db` file that gets rebuilt every run means every
commit carries a full undiffable blob for zero benefit — pure repo bloat.
Since the plain JSON manifests are the real source of truth and the
rebuild is near-instant, there is no reason to persist the derived index;
treat it like a `.pyc` file.

## Directory layout

```
data/monthly_archive/
  2026-07/
    manifest.json   — run metadata (see schema below)
    metrics.json     — tidy long-format economic scalars for this month
    raw_data.json     — full API pull (same shape snapshot.py captures)
    state.json        — Tier-1 chart payload (dev branch only; absent on main)
    index.html         — the full rendered dashboard as of this month
  2026-08/
    ...
```

### `manifest.json` schema

```json
{
  "schema_version": 1,
  "month": "2026-07",
  "source_run_date": "2026-07-30",
  "archived_at": "2026-07-30T04:17:06Z",
  "git_sha": "eec663e",
  "branch": "dev/multi-expert-improvements",
  "files": ["raw_data.json", "state.json", "index.html", "metrics.json"],
  "sizes": {"raw_data.json": 2238676, "...": "..."},
  "sha256": {"raw_data.json": "d159b63f...", "...": "..."},
  "validation_status": "PASS",
  "validation_summary": {"total_checks": 665, "passed": 665, "failed": 0, "skipped": 1, "critical_divergences": 0},
  "ceo_grade_verdict": "PASS"
}
```

`ceo_grade_verdict` is only present on branches whose pipeline produces
`data/ceo_grade_verdict.json` (dev today; main does not run that gate —
see `CLAUDE.md`). The field is simply absent on main's manifests, not
null — code reading this should treat missing and null the same way.

### `metrics.json` schema

Tidy long format — one row per economic series, sourced from
`signals.json`'s `values` dict (the already-normalized scalars the
dashboard's own KPI tiles read from, not raw FRED/BLS series arrays):

```json
{
  "month": "2026-07",
  "obs_date": "2026-07-30",
  "metrics": [
    {"series_id": "unrate", "label": "Unemployment Rate", "value": 4.2, "unit": "%"},
    {"series_id": "wti", "label": "WTI Crude", "value": 84.25, "unit": "$/bbl"},
    "... ~30 rows total"
  ]
}
```

`series_id` matches the key names in `signals.json`'s `values` dict
(`scripts/monthly_archive.py`'s `METRIC_META` dict supplies the
label/unit — see that file if you add a new signal upstream and want it
to carry a readable label here instead of falling back to the raw key).

## SQLite index schema

Built by `scripts/build_archive_index.py`, always a full rebuild (drop +
recreate) from every `manifest.json`/`metrics.json` under
`data/monthly_archive/`:

```sql
CREATE TABLE monthly_snapshots (
  month                 TEXT PRIMARY KEY,   -- 'YYYY-MM'
  source_run_date       TEXT NOT NULL,
  archived_at           TEXT NOT NULL,
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

CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT);
```

### Example queries

```bash
python scripts/build_archive_index.py   # rebuild data/monthly_archive.db first

sqlite3 data/monthly_archive.db \
  "SELECT month, value FROM monthly_metrics WHERE series_id='unrate' ORDER BY month;"

sqlite3 data/monthly_archive.db \
  "SELECT month, validation_status, ceo_grade_verdict, critical_divergences
   FROM monthly_snapshots ORDER BY month DESC LIMIT 12;"

# Every metric for a given month, human-readable:
sqlite3 data/monthly_archive.db \
  "SELECT label, value, unit FROM monthly_metrics WHERE month='2026-07' ORDER BY label;"
```

## Pipeline behavior — how a month gets archived

`scripts/monthly_archive.py` runs on **every** pipeline execution (added
as a CI step right after the existing Snapshot step in both
`briefing.yml` and `briefing-dev.yml`). It computes the current calendar
month and **upserts** `data/monthly_archive/<month>/` in place — no
special "is this the first or last run of the month" trigger logic
exists or is needed. Because it always overwrites the *current* month's
directory, whatever the **last successful run within a month** wrote is
what survives once the next month's directory gets created. That gives
clean "end of month" semantics for free.

**This step must never fail the pipeline.** `archive_month()` wraps all
its I/O in a single try/except and always exits 0 on error, printing a
warning instead of raising. The CI step also sets `continue-on-error:
true` as a second layer of defense. Historical archiving is valuable but
is explicitly not worth blocking a live publish over — if this reasoning
ever needs to change (e.g. the archive becomes load-bearing for something
downstream), revisit deliberately, don't let it silently become
blocking by accident.

## Operating recommendations

1. **Never add a retention cap here.** At ~2-3 MB/month this grows to
   roughly 30-35 MB/year — a decade of history is a non-problem for a
   git repo. This directory's entire reason to exist is being the
   un-pruned counterpart to `snapshot.py`; don't let scope creep turn it
   into a second rolling-window mechanism.
2. **If repo size ever does become a real concern**, the first lever to
   pull is dropping `raw_data.json` from future months' archives (keep
   `metrics.json` + `manifest.json` + `index.html` only) — `metrics.json`
   already carries the normalized scalars most queries actually want, and
   full-fidelity raw series can be re-fetched from FRED/BLS if truly
   needed. Don't reach for this preemptively; it's a real fidelity loss
   should be a deliberate call when the cost is actually being felt, not
   before.
3. **This archive is not a substitute for FRED's ALFRED vintage system.**
   `monthly_archive` records what the dashboard *displayed*, which is
   whatever FRED/BLS returned at fetch time — it does not track later
   revisions to that same historical month. If you need "what did BLS
   originally report for April, before revision," that's ALFRED's job
   (already used elsewhere in this codebase for GDP/CPI/wage annual
   charts — see `METHODOLOGY.md`), not this archive's.
4. **Treat the SQLite DB as fully disposable.** Never write application
   logic that depends on `data/monthly_archive.db` existing or being
   fresh — always be prepared to run `build_archive_index.py` first. If
   you want the index available without a manual rebuild step (e.g. for
   a dashboard feature that queries archive history), rebuild it as part
   of that feature's own CI step or at request time, don't assume a
   stale committed copy would have been safe to rely on.
5. **Schema versioning is already wired in** (`schema_version` in every
   manifest and in the DB's `monthly_snapshots` table) even though there
   is only version 1 today. If the manifest shape ever needs to change,
   bump `SCHEMA_VERSION` in `monthly_archive.py`, and have
   `build_archive_index.py` branch on `manifest.get('schema_version')`
   rather than assuming every historical manifest matches the latest
   shape — old months' manifests will never be rewritten retroactively.
6. **Checksums exist for a reason — use them.** Every archived file has a
   SHA256 in its month's manifest. Before trusting an old `index.html` or
   `raw_data.json` pulled from the archive (e.g. for an audit or a
   dispute about what the dashboard showed on a given date), verify the
   hash first; git history theoretically protects against tampering but
   a cheap local checksum check costs nothing and catches accidental
   corruption too.
7. **Keep this out of the critical path.** If you ever add something that
   *reads* the monthly archive as part of a live pipeline decision (not
   just historical reporting), think hard before doing so — the whole
   design assumes this is a side archive that can lag or occasionally
   fail without affecting publish. Making anything depend on it changes
   that contract.
