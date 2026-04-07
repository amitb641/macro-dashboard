#!/usr/bin/env python3
"""
API Contract Tests — Verify data source APIs return expected response formats.
Runs weekly (Tuesday) to catch breaking changes before the Friday pipeline.
Requires live API keys (FRED_API_KEY, BLS_API_KEY, EIA_API_KEY).

Usage: python tests/test_api_contracts.py
"""

import os, sys, json

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

FRED_KEY = os.environ.get('FRED_API_KEY', '')
BLS_KEY  = os.environ.get('BLS_API_KEY', '')
EIA_KEY  = os.environ.get('EIA_API_KEY', '')

PASS = 0
FAIL = 0
SKIP = 0
ERRORS = []


def _test(name, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f'  PASS  {name}')
    else:
        FAIL += 1
        ERRORS.append(f'{name}: {detail}')
        print(f'  FAIL  {name} — {detail}')


def _skip(name, reason):
    global SKIP
    SKIP += 1
    print(f'  SKIP  {name} — {reason}')


# ═══════════════════════════════════════════════════════════════════════
# FRED API
# ═══════════════════════════════════════════════════════════════════════

def test_fred():
    print('\n── FRED API ──')
    if not FRED_KEY:
        _skip('FRED', 'FRED_API_KEY not set')
        return

    # Test observations endpoint with UNRATE
    try:
        r = requests.get('https://api.stlouisfed.org/fred/series/observations',
                         params={'series_id': 'UNRATE', 'api_key': FRED_KEY,
                                 'file_type': 'json', 'sort_order': 'desc', 'limit': 2},
                         timeout=15)
        _test('FRED HTTP status', r.status_code == 200, f'got {r.status_code}')

        data = r.json()
        _test('FRED has observations key', 'observations' in data,
              f'keys: {list(data.keys())}')

        obs = data.get('observations', [])
        _test('FRED returns observations', len(obs) > 0, 'empty observations')

        if obs:
            o = obs[0]
            _test('FRED obs has date', 'date' in o, f'keys: {list(o.keys())}')
            _test('FRED obs has value', 'value' in o, f'keys: {list(o.keys())}')
            _test('FRED date format YYYY-MM-DD', len(o.get('date', '')) == 10,
                  f'got: {o.get("date")}')
            _test('FRED value is numeric string', o['value'].replace('.', '').replace('-', '').isdigit(),
                  f'got: {o["value"]}')

    except requests.exceptions.Timeout:
        _test('FRED reachable', False, 'timeout after 15s')
    except Exception as e:
        _test('FRED request', False, str(e))

    # Test single-value endpoint (DGS10 — daily, may return '.')
    try:
        r = requests.get('https://api.stlouisfed.org/fred/series/observations',
                         params={'series_id': 'DGS10', 'api_key': FRED_KEY,
                                 'file_type': 'json', 'sort_order': 'desc', 'limit': 5},
                         timeout=15)
        data = r.json()
        obs = [o for o in data.get('observations', []) if o['value'] != '.']
        _test('FRED DGS10 has valid obs', len(obs) > 0, 'all values are "."')

    except Exception as e:
        _test('FRED DGS10', False, str(e))


# ═══════════════════════════════════════════════════════════════════════
# BLS API
# ═══════════════════════════════════════════════════════════════════════

def test_bls():
    print('\n── BLS API ──')
    if not BLS_KEY:
        _skip('BLS', 'BLS_API_KEY not set')
        return

    import datetime
    yr = datetime.date.today().year

    try:
        r = requests.post('https://api.bls.gov/publicAPI/v2/timeseries/data/',
                          json={'seriesid': ['CES0000000001'],
                                'startyear': str(yr - 1), 'endyear': str(yr),
                                'registrationkey': BLS_KEY},
                          timeout=20)
        _test('BLS HTTP status', r.status_code == 200, f'got {r.status_code}')

        data = r.json()
        _test('BLS has status', 'status' in data, f'keys: {list(data.keys())}')
        _test('BLS status=REQUEST_SUCCEEDED', data.get('status') == 'REQUEST_SUCCEEDED',
              f'got: {data.get("status")}')

        _test('BLS has Results', 'Results' in data, f'keys: {list(data.keys())}')
        results = data.get('Results', {})
        _test('BLS has series', 'series' in results, f'keys: {list(results.keys())}')

        series = results.get('series', [])
        _test('BLS series non-empty', len(series) > 0, 'empty series')

        if series:
            s = series[0]
            _test('BLS series has seriesID', 'seriesID' in s, f'keys: {list(s.keys())}')
            _test('BLS series has data', 'data' in s, f'keys: {list(s.keys())}')

            points = s.get('data', [])
            _test('BLS data non-empty', len(points) > 0, 'empty data')

            if points:
                p = points[0]
                _test('BLS point has year', 'year' in p, f'keys: {list(p.keys())}')
                _test('BLS point has period', 'period' in p, f'keys: {list(p.keys())}')
                _test('BLS point has value', 'value' in p, f'keys: {list(p.keys())}')
                _test('BLS period format M##', p['period'].startswith('M'),
                      f'got: {p["period"]}')
                # Value should be numeric string (may have decimals)
                _test('BLS value is numeric', p['value'].replace('.', '').replace('-', '').isdigit(),
                      f'got: {p["value"]}')

    except requests.exceptions.Timeout:
        _test('BLS reachable', False, 'timeout after 20s')
    except Exception as e:
        _test('BLS request', False, str(e))


# ═══════════════════════════════════════════════════════════════════════
# EIA API
# ═══════════════════════════════════════════════════════════════════════

def test_eia():
    print('\n── EIA API ──')
    if not EIA_KEY:
        _skip('EIA', 'EIA_API_KEY not set')
        return

    try:
        url = (f'https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key={EIA_KEY}'
               f'&frequency=daily&data[0]=value&facets[series][]=RWTC'
               f'&sort[0][column]=period&sort[0][direction]=desc&length=5')
        r = requests.get(url, timeout=15)
        _test('EIA HTTP status', r.status_code == 200, f'got {r.status_code}')

        data = r.json()
        _test('EIA has response key', 'response' in data, f'keys: {list(data.keys())}')

        resp = data.get('response', {})
        _test('EIA response has data', 'data' in resp, f'keys: {list(resp.keys())}')

        points = resp.get('data', [])
        _test('EIA data non-empty', len(points) > 0, 'empty data')

        if points:
            p = points[0]
            _test('EIA point has period', 'period' in p, f'keys: {list(p.keys())}')
            _test('EIA point has value', 'value' in p, f'keys: {list(p.keys())}')
            _test('EIA period format YYYY-MM-DD', len(str(p.get('period', ''))) == 10,
                  f'got: {p.get("period")}')

    except requests.exceptions.Timeout:
        _test('EIA reachable', False, 'timeout after 15s')
    except Exception as e:
        _test('EIA request', False, str(e))


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    print('=' * 60)
    print('API CONTRACT TESTS')
    print('=' * 60)

    test_fred()
    test_bls()
    test_eia()

    total = PASS + FAIL
    print(f'\n{"=" * 60}')
    print(f'API CONTRACTS: {PASS}/{total} passed, {FAIL} failed, {SKIP} skipped')
    if ERRORS:
        print(f'\nFailures:')
        for e in ERRORS:
            print(f'  - {e}')
    print(f'{"=" * 60}')

    return FAIL == 0


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
