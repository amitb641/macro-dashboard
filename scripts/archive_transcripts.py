#!/usr/bin/env python3
"""One-off archiver for already-reported quarters.

Agent 9 skips banks where status=='reported', so when a quarter's
bank_earnings.json was hand-populated without an Agent 9 fetch pass,
the on-disk transcripts at data/transcripts/<Quarter>/<TICKER>.txt
are missing and the validator's verbatim gate stays off.

This script bypasses the skip logic and re-archives transcripts for
EVERY reported bank in the current bank_earnings.json. Uses the same
fetch_transcript helper Agent 9 uses (no new code paths). After
archive, runs the same _norm_for_match comparison the validator
uses so the operator gets an immediate per-bank pass/fail report.

Usage:
    python scripts/archive_transcripts.py              # archive all reported banks
    python scripts/archive_transcripts.py --dry-run    # just print what would happen
    python scripts/archive_transcripts.py --bank JPM   # single bank
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

# Reuse the existing fetch + save helpers verbatim.
from earnings_agent import fetch_transcript, save_transcript  # type: ignore


_QUOTED_FIELDS = ('quote', 'economy', 'lending', 'cards_loans',
                  'macro', 'tech_ai', 'credit', 'outlook')


def _norm_for_match(s):
    """Mirror of validator._norm_for_match — keep in sync with validator.py."""
    s = s.replace('\u201c', '"').replace('\u201d', '"')
    s = s.replace('\u2018', "'").replace('\u2019', "'")
    s = s.replace('\u2014', '--').replace('\u2013', '-')
    return ' '.join(s.split())


def _verbatim_match(quoted_span, transcript_norm):
    """Mirror of validator._verbatim_match — keep in sync. Ellipsis
    inside quotes is a segment-split wildcard; trailing 3+ periods
    are stripped."""
    span = _norm_for_match(quoted_span)
    span = re.sub(r'\.{3,}$', '', span).strip()
    if not span:
        return True
    segments = [seg.strip() for seg in re.split(r'\.{3,}', span) if seg.strip()]
    cursor = 0
    for seg in segments:
        idx = transcript_norm.find(seg, cursor)
        if idx < 0:
            return False
        cursor = idx + len(seg)
    return True


def _verify(bank, transcript_text):
    """Replicate validator's verbatim-quote check; return list of misses."""
    quoted_re = re.compile(r'"([^"]{15,})"')
    norm = _norm_for_match(transcript_text)
    misses = []
    for field in _QUOTED_FIELDS:
        val = bank.get(field) or ''
        for quoted in quoted_re.findall(val):
            if not _verbatim_match(quoted, norm):
                misses.append({'field': field, 'snippet': quoted[:90]})
    return misses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--bank', help='Limit to a single ticker')
    args = ap.parse_args()

    earnings = json.loads((ROOT / 'data' / 'bank_earnings.json')
                          .read_text(encoding='utf-8'))
    quarter = earnings.get('quarter', 'Unknown')
    banks = [b for b in earnings.get('banks', [])
             if (b.get('status') or '').lower() == 'reported']
    if args.bank:
        banks = [b for b in banks if b['ticker'] == args.bank.upper()]

    if not banks:
        print(f'No reported banks to archive (quarter={quarter}).')
        return 0

    print(f'Archiving {len(banks)} bank(s) for {quarter}...')
    summary = {'fetched': 0, 'failed': 0, 'verified': 0, 'mismatched': 0}
    for b in banks:
        ticker = b['ticker']
        print(f'\n== {ticker} ({b.get("actual_report_date","-")}) ==')

        urls = []
        if b.get('transcript_url'):
            urls.append(b['transcript_url'])
        urls.extend(b.get('transcript_url_candidates') or [])
        urls = [u for u in urls if u]
        if not urls:
            print(f'  [skip] no transcript URLs configured')
            summary['failed'] += 1
            continue

        if args.dry_run:
            print(f'  [dry-run] would fetch from {len(urls)} URL(s):')
            for u in urls:
                print(f'    - {u}')
            continue

        text, src = fetch_transcript(urls)
        if not text:
            print(f'  [fail] no URL returned a usable transcript body')
            summary['failed'] += 1
            continue
        path = save_transcript(quarter, ticker, text)
        print(f'  [archived] {len(text):,} chars from {src[:80]} -> {path}')
        summary['fetched'] += 1

        misses = _verify(b, text)
        if misses:
            print(f'  [WARN] {len(misses)} quoted span(s) not found verbatim:')
            for m in misses[:5]:
                print(f'    [{m["field"]}] "{m["snippet"]}..."')
            if len(misses) > 5:
                print(f'    ... and {len(misses)-5} more')
            summary['mismatched'] += 1
        else:
            n_quoted = sum(1 for f in _QUOTED_FIELDS
                           for _ in re.findall(r'"([^"]{15,})"', b.get(f) or ''))
            print(f'  [OK] all {n_quoted} quoted span(s) match the archived transcript')
            summary['verified'] += 1

    print(f'\n=== Summary ===')
    print(f'  fetched:    {summary["fetched"]}')
    print(f'  failed:     {summary["failed"]}')
    print(f'  verified:   {summary["verified"]}')
    print(f'  mismatched: {summary["mismatched"]}')
    return 0 if summary['failed'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
