#!/usr/bin/env python3
"""
ROLLOVER CALENDAR HELPER (rollover_calendar.py)

One-shot helper that drafts next quarter's `data/earnings_calendar.json`
by rolling each bank's expected report date forward ~91 days and
substituting quarter tokens in the transcript URL candidates.

USAGE
─────
  # Auto-detect: current calendar's quarter + 1
  python scripts/rollover_calendar.py

  # Target a specific quarter (useful for skipping or seeding)
  python scripts/rollover_calendar.py --next "Q3 2026"

  # Custom output path (default: data/earnings_calendar.next.json)
  python scripts/rollover_calendar.py --out path/to/draft.json

  # Overwrite earnings_calendar.json in place (only after you've eyeballed)
  python scripts/rollover_calendar.py --in-place

WORKFLOW (each quarter, ~5 min)
────────────────────────────────
  1. Run the script → produces a draft JSON
  2. Open each bank's IR calendar page (linked in script output) to
     spot-check the rolled date against the officially-announced date.
     Adjust dates that are off by 1-3 days.
  3. Open the transcript_url_candidates list; a few URL patterns won't
     roll cleanly (marked TODO) — replace by hand.
  4. Rename draft → earnings_calendar.json, git commit + push.
  5. Agent 9's next scheduled run picks up the new calendar.

NEVER modifies earnings_calendar.json directly unless --in-place is given.

ROLLOVER RULES
──────────────
- Dates: new_date = old_date + 91 days; if Sat → Fri (−1 day); if Sun → Mon (+1 day)
- URL tokens substituted (case-insensitive where safe):
    q1 → q2 in slug segments         (fool.com/.../jpm-q1-2026-...)
    1st-quarter → 2nd-quarter        (JPM IR)
    1q26 → 2q26                      (JPM IR internal)
    /YYYY/MM/DD/ date segments       (rewritten to new expected date)
    "Q1 2026" → "Q2 2026" literals
- Unrecognized URLs kept as-is with "[TODO: verify]" comment so they
  surface in a diff — you'll see them in the PR/commit review.

This is deliberately a dumb transform. The IR-calendar eyeball step is
the source of truth. 80–90% of dates and URLs will roll cleanly; the
remaining 10-20% is the reason we keep a human in the loop.
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent
CAL = ROOT / 'data' / 'earnings_calendar.json'
DEFAULT_OUT = ROOT / 'data' / 'earnings_calendar.next.json'

# Map Q# → ordinal word + month range for URL substitutions
_QUARTER_MONTHS = {1: 'january', 2: 'april', 3: 'july', 4: 'october'}
_QUARTER_ORDINALS = {1: '1st', 2: '2nd', 3: '3rd', 4: '4th'}


def parse_quarter(s):
    """'Q2 2026' → (2, 2026). Case-insensitive, tolerant of whitespace."""
    m = re.match(r'\s*Q?(\d)\s+(\d{4})\s*', s, re.IGNORECASE)
    if not m:
        raise ValueError(f'Unparseable quarter: {s!r} (expected "Q2 2026")')
    q, y = int(m.group(1)), int(m.group(2))
    if q not in (1, 2, 3, 4):
        raise ValueError(f'Quarter must be 1-4, got {q}')
    return q, y


def next_quarter(q, y):
    """(1, 2026) → (2, 2026); (4, 2026) → (1, 2027)."""
    return (1, y + 1) if q == 4 else (q + 1, y)


def roll_date(iso_date, days=91):
    """Shift ISO date forward N days, snap off weekends (Sat→Fri, Sun→Mon)."""
    d = datetime.date.fromisoformat(iso_date) + datetime.timedelta(days=days)
    if d.weekday() == 5:   # Saturday
        d -= datetime.timedelta(days=1)
    elif d.weekday() == 6:  # Sunday
        d += datetime.timedelta(days=1)
    return d.isoformat()


def roll_url(url, old_q, old_y, new_q, new_y, new_iso_date):
    """Best-effort URL rewrite. Returns (new_url, confident: bool).

    `confident=False` means no known pattern matched — you should manually
    verify the output.
    """
    before = url
    u = url
    confident = False

    # 1. Lowercase qN in slug segments: -q1-, _q1_, /q1- etc.
    # Match only where a word boundary precedes qN to avoid random matches.
    pattern = re.compile(rf'(?<![A-Za-z0-9])q{old_q}(?![A-Za-z0-9])', re.IGNORECASE)
    def _repl_q(m):
        return m.group(0).replace(str(old_q), str(new_q))
    u2 = pattern.sub(_repl_q, u)
    if u2 != u:
        confident = True
        u = u2

    # 2. Ordinal variants: "1st-quarter" → "2nd-quarter"
    for variant in (_QUARTER_ORDINALS[old_q] + '-quarter',
                    _QUARTER_ORDINALS[old_q] + '_quarter'):
        target = variant.replace(_QUARTER_ORDINALS[old_q], _QUARTER_ORDINALS[new_q])
        u2 = re.sub(re.escape(variant), target, u, flags=re.IGNORECASE)
        if u2 != u:
            confident = True
            u = u2

    # 3. JPM-style "1q26" → "2q27" (note: year shifts too if crossing year boundary)
    jpm_pattern = re.compile(rf'{old_q}q{old_y % 100:02d}', re.IGNORECASE)
    u2 = jpm_pattern.sub(f'{new_q}q{new_y % 100:02d}', u)
    if u2 != u:
        confident = True
        u = u2

    # 4. Literal "Q1 2026" → "Q2 2026"
    literal = re.compile(rf'Q{old_q}\s+{old_y}', re.IGNORECASE)
    u2 = literal.sub(f'Q{new_q} {new_y}', u)
    if u2 != u:
        confident = True
        u = u2

    # 5. Date path segments /YYYY/MM/DD/ → /NEW_YYYY/NEW_MM/NEW_DD/
    new_y_s, new_m_s, new_d_s = new_iso_date.split('-')
    # Find /YYYY/MM/DD/ patterns (common on fool.com etc.)
    date_pattern = re.compile(rf'/{old_y}/\d{{2}}/\d{{2}}/')
    u2 = date_pattern.sub(f'/{new_y_s}/{new_m_s}/{new_d_s}/', u)
    if u2 != u:
        confident = True
        u = u2

    return u, confident


def rollover_bank(bank, old_q, old_y, new_q, new_y):
    """Returns the bank dict for the new calendar + a list of warning strings."""
    warnings = []

    # Date rollover — prefer actual_report_date if present, else expected
    src_date = bank.get('actual_report_date') or bank.get('expected_report_date')
    if not src_date:
        warnings.append(f'{bank["ticker"]}: no source date; leaving expected blank')
        new_date = ''
    else:
        new_date = roll_date(src_date, 91)

    # URL candidate rollover
    new_urls = []
    for url in bank.get('transcript_url_candidates', []):
        new_url, confident = roll_url(url, old_q, old_y, new_q, new_y, new_date or src_date)
        if not confident:
            warnings.append(f'{bank["ticker"]}: URL unchanged (no pattern matched): {url[:80]}')
            # Mark with TODO so it's obvious in the diff
            new_urls.append(f'TODO-verify::{new_url}')
        else:
            new_urls.append(new_url)

    return {
        'ticker': bank['ticker'],
        'bank': bank['bank'],
        'ceo': bank.get('ceo', ''),
        'color': bank.get('color', '#666'),
        'expected_report_date': new_date,
        'transcript_url_candidates': new_urls,
    }, warnings


def build_season(banks):
    """Derive season.start / season.end from the min/max expected_report_date."""
    dates = [b['expected_report_date'] for b in banks if b.get('expected_report_date')]
    if not dates:
        return {'start': '', 'end': ''}
    start = min(dates)
    end_date = datetime.date.fromisoformat(max(dates)) + datetime.timedelta(days=5)
    return {'start': start, 'end': end_date.isoformat()}


IR_CALENDARS = {
    'JPM': 'https://www.jpmorganchase.com/ir/news-events/events-and-presentations',
    'BAC': 'https://investor.bankofamerica.com/quarterly-earnings',
    'WFC': 'https://www.wellsfargo.com/about/investor-relations/quarterly-earnings/',
    'C':   'https://www.citigroup.com/global/investors/quarterly-earnings',
    'GS':  'https://www.goldmansachs.com/investor-relations/financials/',
    'USB': 'https://ir.usbank.com/financials/quarterly-results',
    'COF': 'https://investor.capitalone.com/earnings-releases',
    'SYF': 'https://investors.synchrony.com/financials/quarterly-earnings/',
    'AXP': 'https://ir.americanexpress.com/financial-reports/quarterly-earnings',
    'BCS': 'https://home.barclays/investor-relations/results-and-reports/',
}


def main():
    ap = argparse.ArgumentParser(description='Roll earnings_calendar.json forward one quarter.')
    ap.add_argument('--next', dest='next_q', help='Target quarter, e.g. "Q3 2026" (default: auto-detect)')
    ap.add_argument('--out', default=str(DEFAULT_OUT), help='Output path (default: data/earnings_calendar.next.json)')
    ap.add_argument('--in-place', action='store_true', help='Overwrite earnings_calendar.json in place (dangerous — use only after review)')
    args = ap.parse_args()

    if not CAL.exists():
        print(f'ERROR: {CAL} missing', file=sys.stderr)
        sys.exit(2)

    cur = json.loads(CAL.read_text(encoding='utf-8'))
    old_q, old_y = parse_quarter(cur['quarter'])

    if args.next_q:
        new_q, new_y = parse_quarter(args.next_q)
    else:
        new_q, new_y = next_quarter(old_q, old_y)

    print(f'Rolling {cur["quarter"]} → Q{new_q} {new_y}')

    new_banks = []
    all_warnings = []
    for bank in cur.get('banks', []):
        new_bank, warnings = rollover_bank(bank, old_q, old_y, new_q, new_y)
        new_banks.append(new_bank)
        all_warnings.extend(warnings)

    draft = {
        'quarter': f'Q{new_q} {new_y}',
        'season': build_season(new_banks),
        'maintained_by': 'human-in-the-loop',
        'notes': (cur.get('notes') or 'Update each quarter: set expected_report_date per IR calendar, '
                  'swap transcript_url_candidates to the new quarter\'s URL patterns. '
                  'Agent 9 reads this file on every scheduled run and never mutates it.'),
        'banks': new_banks,
    }

    out_path = CAL if args.in_place else Path(args.out)
    out_path.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    # Summary for human review
    print()
    print('=' * 64)
    print(f'Wrote {out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path}')
    print('=' * 64)
    print()
    print('Per-bank rollover:')
    print(f'  {"TICKER":<6} {"OLD DATE":<12} → {"NEW DATE":<12}  IR calendar to verify')
    for old_bank, new_bank in zip(cur['banks'], new_banks):
        old_d = old_bank.get('actual_report_date') or old_bank.get('expected_report_date') or '?'
        new_d = new_bank.get('expected_report_date') or '?'
        ir = IR_CALENDARS.get(new_bank['ticker'], '?')
        print(f'  {new_bank["ticker"]:<6} {old_d:<12} → {new_d:<12}  {ir}')

    if all_warnings:
        print()
        print('Warnings (review these before committing):')
        for w in all_warnings:
            print(f'  ⚠  {w}')

    print()
    print('Next steps:')
    print('  1. Open each bank\'s IR calendar page above and cross-check dates.')
    print('     Edit the draft file wherever the rolled date is off by 1–3 days.')
    print('  2. Search for "TODO-verify::" prefixes in transcript_url_candidates')
    print('     and rewrite those by hand.')
    if not args.in_place:
        print(f'  3. Rename {out_path.name} → earnings_calendar.json when ready.')
    print('  4. git commit + push. Agent 9 picks it up on next scheduled run.')


if __name__ == '__main__':
    main()
