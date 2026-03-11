"""
update_dashboard.py
───────────────────
Monthly data refresh for macro_dashboard_v6.html.

Fetches from:
  BLS  — Jobs, CPI, Wages, Unemployment
  BEA  — GDP, PCE, Personal Income
  FRED — Fed Funds Rate, Mortgage Rate, HPI, Credit
  EIA  — WTI oil price, Brent

Then patches the JS data constants directly in the HTML file.
"""

import os, re, json, requests
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

# ── Config ──────────────────────────────────────────────────────────────────

HTML_FILE   = "macro_dashboard_v6.html"
STATUS_FILE = "data/last_update.json"

BLS_KEY  = os.environ.get("BLS_API_KEY",  "")
BEA_KEY  = os.environ.get("BEA_API_KEY",  "")
FRED_KEY = os.environ.get("FRED_API_KEY", "")
EIA_KEY  = os.environ.get("EIA_API_KEY",  "")

TODAY      = date.today()
THIS_YEAR  = TODAY.year
THIS_MONTH = TODAY.month
LAST_MONTH = (TODAY - relativedelta(months=1))

log_lines = []

def log(msg):
    print(msg)
    log_lines.append(msg)

# ── Helpers ──────────────────────────────────────────────────────────────────

def bls_series(series_ids, start_year, end_year):
    if not BLS_KEY:
        log("  ⚠️  BLS_API_KEY not set — skipping BLS fetch")
        return {}
    url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    payload = {
        "seriesid":   series_ids,
        "startyear":  str(start_year),
        "endyear":    str(end_year),
        "registrationkey": BLS_KEY
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "REQUEST_SUCCEEDED":
            log(f"  ⚠️  BLS error: {data.get('message', 'unknown')}")
            return {}
        result = {}
        for series in data["Results"]["series"]:
            sid = series["seriesID"]
            result[sid] = [(int(d["year"]), d["period"], float(d["value"]))
                          for d in series["data"]]
        return result
    except Exception as e:
        log(f"  ❌ BLS fetch failed: {e}")
        return {}

def fred_series(series_id, frequency="a"):
    if not FRED_KEY:
        log(f"  ⚠️  FRED_API_KEY not set — skipping {series_id}")
        return []
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id":     series_id,
        "api_key":       FRED_KEY,
        "file_type":     "json",
        "frequency":     frequency,
        "observation_start": f"{THIS_YEAR - 10}-01-01",
    }
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        return [(o["date"], float(o["value"])) for o in obs if o["value"] != "."]
    except Exception as e:
        log(f"  ❌ FRED {series_id} failed: {e}")
        return []

def eia_series(series_id):
    if not EIA_KEY:
        log(f"  ⚠️  EIA_API_KEY not set — skipping {series_id}")
        return []
    url = f"https://api.eia.gov/v2/seriesid/{series_id}"
    params = {"api_key": EIA_KEY, "frequency": "annual", "length": 15}
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json().get("response", {}).get("data", [])
        return [(int(d["period"]), float(d["value"])) for d in data]
    except Exception as e:
        log(f"  ❌ EIA {series_id} failed: {e}")
        return []

def patch_js_const(html, const_name, new_value_str):
    pattern = rf'(const {re.escape(const_name)}\s*=\s*)(\[[\s\S]*?\]|\{{[\s\S]*?\}}|`[\s\S]*?`|"[^"]*"|\'[^\']*\'|\d[\d.]*)\s*;'
    replacement = rf'\g<1>{new_value_str};'
    new_html, n = re.subn(pattern, replacement, html, count=1)
    if n == 0:
        log(f"  ⚠️  Could not find const {const_name} — skipping patch")
        return html
    log(f"  ✅ Patched {const_name}")
    return new_html

def to_js(obj):
    return json.dumps(obj, separators=(',', ':'))

# ── Fetch ────────────────────────────────────────────────────────────────────

def fetch_all():
    updates = {}
    start = THIS_YEAR - 9

    log("\n📊 Fetching CPI from BLS...")
    bls = bls_series(["CUUR0000SA0"], start, THIS_YEAR)
    if "CUUR0000SA0" in bls:
        raw = bls["CUUR0000SA0"]
        dec_vals = {yr: val for yr, per, val in raw if per == "M12"}
        if len(dec_vals) >= 2:
            years = sorted(dec_vals)
            cpi_yoy = {}
            for i in range(1, len(years)):
                yr = years[i]
                cpi_yoy[yr] = round((dec_vals[yr] - dec_vals[years[i-1]]) / dec_vals[years[i-1]] * 100, 1)
            updates["CPI_ANNUAL"] = {"labels": [str(y) for y in sorted(cpi_yoy)], "data": [cpi_yoy[y] for y in sorted(cpi_yoy)]}

    log("\n👷 Fetching Unemployment from BLS...")
    from collections import defaultdict
    bls_u = bls_series(["LNS14000000"], start, THIS_YEAR)
    if "LNS14000000" in bls_u:
        yr_vals = defaultdict(list)
        for yr, per, val in bls_u["LNS14000000"]:
            if per.startswith("M"):
                yr_vals[yr].append(val)
        annual_u = {yr: round(sum(v)/len(v), 1) for yr, v in yr_vals.items() if len(v) >= 10}
        if annual_u:
            updates["U_ANNUAL"] = {"labels": [str(y) for y in sorted(annual_u)], "data": [annual_u[y] for y in sorted(annual_u)]}

    log("\n💼 Fetching Jobs from BLS...")
    bls_j = bls_series(["CES0000000001"], start, THIS_YEAR)
    if "CES0000000001" in bls_j:
        dec_vals = {yr: val for yr, per, val in bls_j["CES0000000001"] if per == "M12"}
        if len(dec_vals) >= 2:
            years = sorted(dec_vals)
            jobs_net = {years[i]: round(dec_vals[years[i]] - dec_vals[years[i-1]]) for i in range(1, len(years))}
            updates["JOBS_ANNUAL"] = {"labels": [str(y) for y in sorted(jobs_net)], "data": [jobs_net[y] for y in sorted(jobs_net)]}

    log("\n💵 Fetching Wages from BLS...")
    bls_w = bls_series(["CES0500000003"], start, THIS_YEAR)
    if "CES0500000003" in bls_w:
        dec_vals = {yr: val for yr, per, val in bls_w["CES0500000003"] if per == "M12"}
        if len(dec_vals) >= 2:
            years = sorted(dec_vals)
            wage_nominal = {years[i]: round((dec_vals[years[i]] - dec_vals[years[i-1]]) / dec_vals[years[i-1]] * 100, 1) for i in range(1, len(years))}
            cpi_map = dict(zip(updates.get("CPI_ANNUAL", {}).get("labels", []), updates.get("CPI_ANNUAL", {}).get("data", [])))
            wage_real = {yr: round(wage_nominal[yr] - cpi_map.get(str(yr), 0), 1) for yr in wage_nominal if str(yr) in cpi_map}
            updates["WAGE_ANNUAL"] = {"labels": [str(y) for y in sorted(wage_nominal)], "nominal": [wage_nominal[y] for y in sorted(wage_nominal)], "real": [wage_real.get(y) for y in sorted(wage_nominal)]}

    log("\n🏦 Fetching Fed Funds Rate from FRED...")
    fred_ffr = fred_series("FEDFUNDS", frequency="m")
    if fred_ffr:
        yr_vals = defaultdict(list)
        for dt, val in fred_ffr:
            yr_vals[int(dt[:4])].append(val)
        ffr_annual = {yr: round(sum(v)/len(v), 2) for yr, v in yr_vals.items()}
        updates["FFR_ANNUAL"] = {"labels": [str(y) for y in sorted(ffr_annual)], "data": [ffr_annual[y] for y in sorted(ffr_annual)]}

    log("\n🏠 Fetching Mortgage Rate from FRED...")
    fred_mort = fred_series("MORTGAGE30US", frequency="a")
    if fred_mort:
        mort = {int(dt[:4]): round(val, 2) for dt, val in fred_mort}
        updates["MORTGAGE_ANNUAL"] = {"labels": [str(y) for y in sorted(mort)], "data": [mort[y] for y in sorted(mort)]}

    log("\n🏡 Fetching HPI from FRED...")
    fred_hpi = fred_series("USSTHPI", frequency="a")
    if fred_hpi:
        hpi_vals = sorted([(int(dt[:4]), val) for dt, val in fred_hpi])
        if len(hpi_vals) >= 2:
            hpi_yoy = {hpi_vals[i][0]: round((hpi_vals[i][1] - hpi_vals[i-1][1]) / hpi_vals[i-1][1] * 100, 1) for i in range(1, len(hpi_vals))}
            updates["HPI_YOY"] = {"labels": [str(y) for y in sorted(hpi_yoy)], "data": [hpi_yoy[y] for y in sorted(hpi_yoy)]}

    log("\n⛽ Fetching WTI Oil from EIA...")
    eia_wti = eia_series("PET.RWTC.A")
    if eia_wti:
        wti = {yr: round(val, 1) for yr, val in sorted(eia_wti)}
        updates["OIL_ANNUAL_NEW"] = {"labels": [str(y) for y in sorted(wti)], "wti": [wti[y] for y in sorted(wti)]}

    return updates

# ── Patch HTML ────────────────────────────────────────────────────────────────

def patch_html(updates):
    log(f"\n📝 Patching {HTML_FILE}...")
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    if "CPI_ANNUAL" in updates:
        d = updates["CPI_ANNUAL"]
        html = patch_js_const(html, "CPI_ANNUAL", f'{{"labels":{to_js(d["labels"])},"data":{to_js(d["data"])}}}')

    if "U_ANNUAL" in updates:
        d = updates["U_ANNUAL"]
        html = patch_js_const(html, "U_ANNUAL", f'{{"labels":{to_js(d["labels"])},"data":{to_js(d["data"])}}}')

    if "JOBS_ANNUAL" in updates:
        d = updates["JOBS_ANNUAL"]
        html = patch_js_const(html, "JOBS_ANNUAL", f'{{"labels":{to_js(d["labels"])},"data":{to_js(d["data"])}}}')

    if "WAGE_ANNUAL" in updates:
        d = updates["WAGE_ANNUAL"]
        html = patch_js_const(html, "WAGE_ANNUAL", f'{{"labels":{to_js(d["labels"])},"nominal":{to_js(d["nominal"])},"real":{to_js(d["real"])}}}')

    if "OIL_ANNUAL_NEW" in updates:
        d = updates["OIL_ANNUAL_NEW"]
        html = patch_js_const(html, "OIL_ANNUAL", f'{{"labels":{to_js(d["labels"])},"wti":{to_js(d["wti"])}}}')

    month_str = TODAY.strftime("%B %Y")
    html = re.sub(r'(Data as of\s*)[A-Za-z]+ \d{4}', rf'\g<1>{month_str}', html)
    log(f"  ✅ Updated timestamp to {month_str}")

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"  ✅ Saved {HTML_FILE}")

# ── Status ────────────────────────────────────────────────────────────────────

def write_status(updates):
    os.makedirs("data", exist_ok=True)
    with open(STATUS_FILE, "w") as f:
        json.dump({"last_updated": TODAY.isoformat(), "updated_at_utc": datetime.utcnow().isoformat()+"Z", "series_updated": list(updates.keys()), "log": log_lines}, f, indent=2)
    log(f"✅ Status written to {STATUS_FILE}")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log(f"🚀 Dashboard update starting — {TODAY.isoformat()}")
    log(f"   BLS: {'✅' if BLS_KEY else '❌'} | BEA: {'✅' if BEA_KEY else '❌'} | FRED: {'✅' if FRED_KEY else '❌'} | EIA: {'✅' if EIA_KEY else '❌'}")
    updates = fetch_all()
    if updates:
        patch_html(updates)
    else:
        log("⚠️  No data fetched — HTML not modified")
    write_status(updates)
    log("✅ Done.")
