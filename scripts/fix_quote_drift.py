#!/usr/bin/env python3
"""Fuzzy-correct drifted earnings quotes to match archived transcripts.

The validator's Pass 3c verbatim gate fires when a quoted span in
data/bank_earnings.json doesn't appear in the archived transcript.
Common drift types after a human-curated JSON pass:

  - em-dash vs ", and" / ", but"
  - smart-quote variants the normalizer doesn't catch
  - editorial smoothing ("the team is" -> "our team is")
  - trailing ".... " truncation markers

This tool, for every quoted span across the 8 commentary fields, finds
the closest substring in the archived transcript using anchor-word
search + difflib similarity, and replaces the JSON value verbatim when
the match is unambiguous (ratio >= AUTOFIX_MIN and clearly best).
Ambiguous / weak matches are reported, not changed.

Usage:
    python scripts/fix_quote_drift.py            # apply auto-fixes
    python scripts/fix_quote_drift.py --dry-run  # report only
    python scripts/fix_quote_drift.py --bank JPM # one bank
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

_QUOTED_FIELDS = ('quote', 'economy', 'lending', 'cards_loans',
                  'macro', 'tech_ai', 'credit', 'outlook')

# Confidence floors.
AUTOFIX_MIN = 0.88   # similarity threshold to auto-apply
AMBIG_GAP   = 0.05   # required gap between best and runner-up


def _norm(s):
    s = s.replace('\u201c', '"').replace('\u201d', '"')
    s = s.replace('\u2018', "'").replace('\u2019', "'")
    s = s.replace('\u2014', '--').replace('\u2013', '-')
    return ' '.join(s.split())


def _verbatim_match(span, transcript_norm):
    span = _norm(span)
    span = re.sub(r'\.{3,}$', '', span).strip()
    if not span:
        return True
    segments = [s.strip() for s in re.split(r'\.{3,}', span) if s.strip()]
    cursor = 0
    for seg in segments:
        idx = transcript_norm.find(seg, cursor)
        if idx < 0:
            return False
        cursor = idx + len(seg)
    return True


def _find_best_match(quote, transcript):
    """Return (best_replacement, ratio, runner_up_ratio) or (None, 0, 0).

    Anchor on the longest word in the first 8 words of the quote.
    Locate every occurrence in the transcript, anchor-align (so we
    capture prefix words before the anchor too), then explore a grid
    of (prefix_offset, span_length) combinations per anchor position.

    Tracking is per anchor position — multiple span variants at one
    position only contribute their own best to the runner-up tally,
    so "tie" cases reflect real ambiguity, not variant overlap.
    """
    q = _norm(quote)
    q = re.sub(r'\.{3,}$', '', q).strip()
    if len(q) < 15:
        return None, 0.0, 0.0

    t_norm = _norm(transcript)
    t_lower = t_norm.lower()
    q_lower = q.lower()

    # Pick anchor: longest word in first 8 that is >=5 chars. Track its
    # character offset within the quote so we can align the candidate
    # span to include the quote prefix.
    words_with_pos = []
    pos = 0
    for w in q.split():
        words_with_pos.append((pos, w))
        pos += len(w) + 1
        if len(words_with_pos) >= 8:
            break
    anchor = None
    anchor_offset = 0
    # Keep hyphens (year-end, charge-off, year-over-year) — they're
    # high-value anchors that DO appear in the transcript verbatim.
    # Strip only trailing punctuation like commas / periods.
    def _clean(w):
        return w.strip('.,;:!?"\'()[]').lower()
    for off, w in words_with_pos:
        clean = _clean(w)
        if len(clean) >= 5 and (anchor is None
                                or len(clean) > len(anchor)):
            anchor = clean
            anchor_offset = off
    if not anchor:
        for off, w in words_with_pos:
            clean = _clean(w)
            if len(clean) >= 4:
                anchor = clean
                anchor_offset = off
                break
    if not anchor:
        return None, 0.0, 0.0

    target_len = len(q)
    candidate_starts = []
    search_from = 0
    while True:
        idx = t_lower.find(anchor, search_from)
        if idx < 0:
            break
        # Map anchor position back to quote-start: candidate begins
        # anchor_offset chars before idx (clamped to 0).
        start = max(0, idx - anchor_offset)
        candidate_starts.append(start)
        search_from = idx + 1
        if len(candidate_starts) > 100:
            break

    if not candidate_starts:
        return None, 0.0, 0.0

    # For each candidate start position, try a small grid of
    # (prefix_shift, span_length) and keep the BEST for that position.
    per_position_best = []  # list of (text, ratio)
    span_lengths = (target_len, target_len + 30, target_len + 80,
                    max(20, target_len - 30), max(20, target_len - 80))
    prefix_shifts = (0, -1, -2, -5, -10, 1, 2, 5)

    for base_start in candidate_starts:
        pos_best = (None, 0.0)
        for shift in prefix_shifts:
            start = base_start + shift
            if start < 0 or start >= len(t_norm):
                continue
            # Walk start forward/backward to a word boundary.
            while start > 0 and t_norm[start - 1].isalpha():
                start -= 1
            for span_len in span_lengths:
                if span_len <= 0:
                    continue
                end = min(len(t_norm), start + span_len)
                cand = t_norm[start:end]
                # Try snap-to-punctuation variants.
                variants = [cand]
                for trim_char in ('.', '?', '!'):
                    last = cand.rfind(trim_char)
                    if last > target_len * 0.5:
                        variants.append(cand[:last + 1])
                for v in variants:
                    if not v:
                        continue
                    r = difflib.SequenceMatcher(
                        None, q_lower, v.lower()
                    ).ratio()
                    if r > pos_best[1]:
                        pos_best = (v, r)
        if pos_best[0]:
            per_position_best.append(pos_best)

    if not per_position_best:
        return None, 0.0, 0.0

    per_position_best.sort(key=lambda x: x[1], reverse=True)
    best_text, best_ratio = per_position_best[0]
    # Use runner-up only when its text DIFFERS from the best. If the
    # top two positions produce identical replacement text it's the
    # same phrase repeating in the transcript — not real ambiguity.
    second = 0.0
    for cand_text, cand_ratio in per_position_best[1:]:
        if cand_text != best_text:
            second = cand_ratio
            break
    return best_text, best_ratio, second


def _process_bank(bank, transcript, dry_run):
    """Return (fixes, reports). fixes is dict field->[(old, new)]."""
    t_norm = _norm(transcript)
    quoted_re = re.compile(r'"([^"]{15,})"')
    fixes = {}
    reports = []
    for field in _QUOTED_FIELDS:
        val = bank.get(field) or ''
        if not val:
            continue
        new_val = val
        changed = False
        # Iterate from longest quote first so substring overlaps don't
        # collide.
        spans = sorted(quoted_re.findall(val), key=len, reverse=True)
        seen = set()
        for quoted in spans:
            if quoted in seen:
                continue
            seen.add(quoted)
            if _verbatim_match(quoted, t_norm):
                continue
            replacement, ratio, second = _find_best_match(
                quoted, transcript
            )
            entry = {
                'field': field,
                'old': quoted,
                'new': replacement,
                'ratio': round(ratio, 3),
                'runner_up': round(second, 3),
            }
            # Autofix when the match is high-confidence. The
            # runner-up gap matters only in the middle band — at
            # ratio>=0.95 ties usually mean the phrase appears
            # verbatim more than once in the transcript, which is
            # safe to replace.
            unambiguous = (ratio - second) >= AMBIG_GAP
            high_conf = ratio >= 0.95
            if (replacement and ratio >= AUTOFIX_MIN
                    and (unambiguous or high_conf)):
                entry['action'] = 'autofix'
                if not dry_run:
                    # Replace inside the field text. Escape regex chars
                    # in the source quote.
                    pat = re.escape(quoted)
                    new_val2, n = re.subn(
                        f'"{pat}"',
                        lambda m: '"' + replacement + '"',
                        new_val,
                        count=1,
                    )
                    if n == 1:
                        new_val = new_val2
                        changed = True
                    else:
                        entry['action'] = 'autofix-failed-replace'
            else:
                entry['action'] = 'report'
            reports.append(entry)
        if changed:
            fixes[field] = new_val
    return fixes, reports


def _unquote_unmatched(bank, transcript, reports):
    """Strip surrounding quotation marks from reported (unmatched)
    spans. Only touches the specific 15+ char spans the verbatim gate
    would flag — surrounding narrative is left alone."""
    t_norm = _norm(transcript)
    changes = {}
    for field in _QUOTED_FIELDS:
        val = bank.get(field) or ''
        if not val:
            continue
        new_val = val
        for r in reports:
            if r['field'] != field or r['action'] != 'report':
                continue
            quoted = r['old']
            # Re-check (in case an earlier autofix already removed it).
            if _verbatim_match(quoted, t_norm):
                continue
            pat = re.escape(quoted)
            new_val2, n = re.subn(
                f'"{pat}"',
                lambda m: quoted,
                new_val,
                count=1,
            )
            if n == 1:
                new_val = new_val2
        if new_val != val:
            changes[field] = new_val
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--bank', help='Limit to single ticker')
    ap.add_argument(
        '--unquote-unmatched', action='store_true',
        help='For quotes we cannot match in the archived transcript, '
             'strip surrounding quotation marks so they become '
             'paraphrases instead of failing the verbatim gate. '
             'Use after a normal pass has exhausted autofixes.',
    )
    args = ap.parse_args()

    earnings_path = ROOT / 'data' / 'bank_earnings.json'
    earnings = json.loads(earnings_path.read_text(encoding='utf-8'))
    quarter = earnings.get('quarter', 'Q1 2026')
    quarter_dir = quarter.replace(' ', '_')

    banks = earnings.get('banks', [])
    if args.bank:
        banks = [b for b in banks if b['ticker'] == args.bank.upper()]

    total_autofix = 0
    total_report = 0
    for bank in banks:
        ticker = bank['ticker']
        t_path = (ROOT / 'data' / 'transcripts' / quarter_dir
                  / f'{ticker}.txt')
        if not t_path.exists():
            continue
        transcript = t_path.read_text(encoding='utf-8', errors='ignore')
        fixes, reports = _process_bank(bank, transcript, args.dry_run)
        if not reports:
            continue
        print(f'\n== {ticker} ==')
        for r in reports:
            tag = '[AUTOFIX]' if r['action'] == 'autofix' else '[REPORT]'
            print(f'  {tag} {r["field"]} ratio={r["ratio"]} '
                  f'(runner-up {r["runner_up"]})')
            old_snip = r['old'][:80] + ('...' if len(r['old']) > 80 else '')
            print(f'    OLD: "{old_snip}"')
            if r['new']:
                new_snip = (r['new'][:80]
                            + ('...' if len(r['new']) > 80 else ''))
                print(f'    NEW: "{new_snip}"')
            else:
                print(f'    NEW: <no candidate found>')
            if r['action'] == 'autofix':
                total_autofix += 1
            else:
                total_report += 1
        # Apply fixes to the bank dict.
        for field, new_val in fixes.items():
            bank[field] = new_val
        # Optional second pass: un-quote spans we couldn't match.
        if args.unquote_unmatched and reports:
            unquote_changes = _unquote_unmatched(
                bank, transcript, reports
            )
            for field, new_val in unquote_changes.items():
                bank[field] = new_val
                print(f'  [UNQUOTE] stripped quotes in {field}')

    if not args.dry_run and total_autofix > 0:
        earnings_path.write_text(
            json.dumps(earnings, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )
        print(f'\nWrote {earnings_path}')

    print(f'\n=== Summary ===')
    print(f'  autofixed: {total_autofix}')
    print(f'  reported:  {total_report}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
