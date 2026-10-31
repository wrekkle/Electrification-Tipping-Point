"""Probe: dump PDF keyword lines (page-numbered) for source verification.
Only writes to stdout / temp; not part of deliverable.
"""
import re
import sys

import fitz

kw = re.compile(r"(time|cost|value|\$|kWh|hour|minute|detour|price|utility|penalt|tariff|discount|dollar)", re.I)


def probe(path: str, max_hits: int = 22) -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    d = fitz.open(path)
    print("FILE:", path)
    print("PAGES:", d.page_count)
    for i in range(d.page_count):
        t = d[i].get_text()
        lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
        hits = [ln for ln in lines if kw.search(ln)]
        print(f"=== PAGE {i+1} chars={len(t)} lines={len(lines)}")
        for h in hits[:max_hits]:
            print("   ", h[:170])


if __name__ == "__main__":
    probe(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 22)
