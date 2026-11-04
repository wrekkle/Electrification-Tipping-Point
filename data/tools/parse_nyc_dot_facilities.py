"""Parse the NYC DOT municipal parking facility list into facilities.jsonl.

Source page: https://www.nyc.gov/html/dot/html/motorist/parkinglist.shtml
Snapshot stored at data/charger_sites/nyc_v3/raw/nyc_dot_parkinglist_20261102.html
(sha256 in sources.md).  The page is the only public listing that gives, for the
same facility, the number of total spaces, the number of EV charging spaces by
class, the posted opening hours and the parking/EV tariff.

Usage:
    python data/tools/parse_nyc_dot_facilities.py
    python data/tools/parse_nyc_dot_facilities.py --html <path> --out <jsonl>

The script only writes the files named on the command line; it does not touch
the v1/v2 site panels.
"""
from __future__ import annotations

import argparse
import html as H
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_HTML = os.path.join(ROOT, "data", "charger_sites", "nyc_v3", "raw",
                            "nyc_dot_parkinglist_20261102.html")
DEFAULT_OUT = os.path.join(ROOT, "data", "charger_sites", "nyc_v3", "facilities.jsonl")
DEFAULT_MAP = os.path.join(ROOT, "data", "charger_sites", "nyc_v3", "site_mapping.json")

SOURCE_URL = "https://www.nyc.gov/html/dot/html/motorist/parkinglist.shtml"
FETCHED = "2026-11-02"

# site_id -> exact facility heading on the DOT page (normalised, see norm()).
# The mapping is by full facility name, not by a fuzzy substring: the page also
# lists facilities with similar names (e.g. "Steinway #1" vs "Steinway #2",
# "Queens Family Court Municipal Parking Garage" vs "... Garage" legacy text).
SITE_TO_FACILITY = {
    "nyc-bri": "Bay Ridge Municipal Parking Garage",
    "nyc-cpo": "College Point Municipal Parking Field",
    "nyc-csq": "Court Square Municipal Parking Garage",
    "nyc-des": "Delancey and Essex Municipal Parking Garage",
    "nyc-hpo": "Hunts Point Municipal Parking Field",
    "nyc-jgu": "Jerome-Gun Hill Road Municipal Parking Garage",
    "nyc-jon": "Jerome - 190th Street Municipal Parking Garage",
    "nyc-qbo": "Borough Hall Municipal Parking Garage",
    "nyc-qfa": "Queens Family Court Municipal Parking Garage",
    "nyc-sge": "Staten Island Courthouse Garage and Outdoor Lot",
    "nyc-stw": "Steinway #2 Municipal Parking Field",
    "nyc-wpl": "White Plains Road Municipal Parking Field",
}

# Facilities that share an address with a sample site but are physically
# different (kept for the record, never merged into the sample site).
RELATED = {
    "nyc-qbo": ["Queensboro Hall Municipal Parking Field"],
}

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
             "twelve": 12}


def norm(s: str) -> str:
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u2019", "'")
    s = s.replace("&amp;", "&")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def strip_tags(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"</p>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    fragment = H.unescape(fragment)
    fragment = fragment.replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in fragment.split("\n")]
    return "\n".join([ln for ln in lines if ln])


def first_int(pattern: str, text: str):
    m = re.search(pattern, text, flags=re.I)
    return int(m.group(1)) if m else None


def clean_name(raw: str) -> str:
    name = strip_tags(raw)
    name = re.sub(r"^\*\s*Opening [^:]+:\s*", "", name, flags=re.I)
    name = re.sub(r"\s*-?\s*With EV\s+Charging\s+Spaces\s*$", "", name, flags=re.I)
    name = re.sub(r"\s*-\s*$", "", name).strip()
    return re.sub(r"\s+", " ", name)


def parse_block(name_raw: str, block_html: str, borough: str) -> dict:
    text = strip_tags(block_html)
    lines = text.split("\n")
    name = clean_name(name_raw)
    address = lines[0] if lines else ""

    spaces_line = ""
    for i, ln in enumerate(lines):
        if re.match(r"^\d+\s+spaces?\b", ln, flags=re.I):
            spaces_line = ln
            # the "(including ...)" clause is often broken over several <br /> lines
            j = i
            while (spaces_line.count("(") > spaces_line.count(")")) and j + 1 < len(lines):
                j += 1
                spaces_line += " " + lines[j]
            break

    def ev(pat):
        m = re.search(pat, spaces_line, flags=re.I)
        return int(m.group(1)) if m else None

    total = None
    m = re.match(r"^(\d+)\s+spaces?\b", spaces_line, flags=re.I)
    if m:
        total = int(m.group(1))
    ada = first_int(r"(\d+)\s+ADA accessible spaces?", spaces_line)
    ev_generic = ev(r"(\d+)\s+Electric Vehicle charging spaces?")
    l2 = ev(r"(\d+)\s+Level[-\s]?2 charging spaces?")
    dc = ev(r"(\d+)\s+DC fast[-\s]?charging spaces?")
    carshare = first_int(r"(\d+)\s+spaces for carshare", spaces_line)

    hours_lines = []
    tail = text
    m_rates = re.search(r"\bRates\b", text)
    head = text[:m_rates.start()] if m_rates else text
    for ln in head.split("\n")[1:]:
        if re.search(r"\b(AM|PM|Midnight|noon|24 hours|24-hour)\b", ln, flags=re.I):
            hours_lines.append(ln)
    hours_raw = " | ".join(hours_lines)

    rates = ""
    m = re.search(r"Rates\s*\n(.*?)(?:\n(?:EV Charging Rates|Permits|Carshare|PARKNYC|BIKE RACK|Open |Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b|\Z)",
                  text, flags=re.S)
    if m:
        rates = re.sub(r"\s+", " ", m.group(1)).strip()[:400]
    ev_rates = ""
    m = re.search(r"EV Charging Rates\s*\n(.*?)(?:\n(?:Permits|Rates|Carshare|PARKNYC|BIKE RACK)\b|\Z)",
                  text, flags=re.S)
    if m:
        ev_rates = re.sub(r"\s+", " ", m.group(1)).strip()[:300]
    permits = ""
    m = re.search(r"Permits\s*\n(.*?)(?:\n(?:Rates|EV Charging Rates|Carshare)\b|\Z)", text, flags=re.S)
    if m:
        permits = re.sub(r"\s+", " ", m.group(1)).strip()[:300]

    status_notes = []
    for pat, label in [
        (r"closed to the public beginning ([^.]+)\.", "closure_notice"),
        (r"Opening ([A-Z][a-z]+ \d{1,2}, \d{4})", "opening_notice"),
        (r"(partially closed[^.]*\.)", "partial_closure"),
        (r"(Closed for construction[^.]*)", "closed_for_construction"),
        (r"(Closing Permanently[^.]*)", "permanent_closure"),
    ]:
        mm = re.search(pat, text)
        if mm:
            status_notes.append({"type": label, "text": mm.group(0)[:200]})

    open_24 = bool(re.search(r"Open 24 hours|24 hours a day|24 hours,\s*Except|24-hour access", text, flags=re.I))

    if ev_generic is not None and (l2 is not None or dc is not None):
        ev_total = max(ev_generic, (l2 or 0) + (dc or 0))
        ev_rule = "max(generic, l2+dc) because both phrasings appear"
    elif ev_generic is not None:
        ev_total = ev_generic
        ev_rule = "generic count"
    else:
        ev_total = (l2 or 0) + (dc or 0) if (l2 is not None or dc is not None) else None
        ev_rule = "l2+dc" if ev_total is not None else "no EV count on page"

    return {
        "facility_name": name,
        "facility_key": norm(name),
        "borough": borough,
        "address": address,
        "total_spaces": total,
        "ada_spaces": ada,
        "ev_charging_spaces_total": ev_generic,
        "ev_l2_spaces": l2,
        "ev_dc_fast_spaces": dc,
        "ev_spaces_registered": ev_total,
        "ev_count_rule": ev_rule,
        "carshare_spaces": carshare,
        "hours_raw": hours_raw,
        "open_24h": open_24,
        "status_notes": status_notes,
        "rates_raw": rates,
        "ev_rates_raw": ev_rates,
        "permits_raw": permits,
        "spaces_line_raw": spaces_line,
        "source_url": SOURCE_URL,
        "fetched_at": FETCHED,
        "source_snapshot": os.path.basename(DEFAULT_HTML),
    }


def parse(html: str) -> list:
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    heads = [(m.start(), m.end(), "h2", m.group(1)) for m in re.finditer(r"<h2[^>]*>(.*?)</h2>", html, flags=re.S)]
    heads += [(m.start(), m.end(), "h3", m.group(1)) for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", html, flags=re.S)]
    heads.sort()
    out, borough = [], ""
    for i, (s, e, tag, raw) in enumerate(heads):
        if tag == "h2":
            borough = strip_tags(raw)
            continue
        end = heads[i + 1][0] if i + 1 < len(heads) else len(html)
        block = html[e:end]
        if re.search(r"^Rates\b", strip_tags(raw)) or "Effective" in strip_tags(raw):
            continue  # rate-table headings, not facilities
        out.append(parse_block(raw, block, borough))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default=DEFAULT_HTML)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--mapping", default=DEFAULT_MAP)
    args = ap.parse_args()

    if not os.path.exists(args.html):
        print("missing snapshot: %s" % args.html)
        return 2
    with open(args.html, encoding="utf-8") as f:
        recs = parse(f.read())

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    by_key = {r["facility_key"]: r for r in recs}
    mapping, problems = {}, []
    for sid, want in SITE_TO_FACILITY.items():
        rec = by_key.get(norm(want))
        if rec is None:
            problems.append("site %s: DOT facility not found: %s" % (sid, want))
            continue
        mapping[sid] = {
            "facility_name": rec["facility_name"],
            "address": rec["address"],
            "borough": rec["borough"],
            "match_basis": "exact facility heading on the official DOT list",
            "source_url": SOURCE_URL,
            "related_facilities": RELATED.get(sid, []),
        }
    with open(args.mapping, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"source": SOURCE_URL, "fetched_at": FETCHED,
                   "snapshot": os.path.basename(DEFAULT_HTML),
                   "sites": mapping, "problems": problems},
                  f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    with_ev = sum(1 for r in recs if (r["ev_l2_spaces"] or 0) + (r["ev_dc_fast_spaces"] or 0) + (r["ev_charging_spaces_total"] or 0) > 0)
    missing_total = [r["facility_name"] for r in recs if r["total_spaces"] is None]
    print("facilities parsed: %d" % len(recs))
    print("facilities with EV charging spaces: %d" % with_ev)
    print("facilities without a parsable total_spaces: %d %s" % (len(missing_total), missing_total[:5]))
    print("sites mapped: %d/%d; problems: %d" % (len(mapping), len(SITE_TO_FACILITY), len(problems)))
    for p in problems:
        print("  " + p)
    print("wrote: %s\n       %s" % (args.out, args.mapping))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
