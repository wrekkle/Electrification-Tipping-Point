"""Download the full NYC EV charging session dataset (kj7g-u4gp) page by page.

Why this exists: the dataset's CSV export endpoint drops the connection on this
network for large extracts, and the earlier 2025-09..2026-09 snapshot kept only
12 * 365 days through a name-pattern filter that missed two naming regimes.  This
tool downloads every row with SoQL pagination and keeps the page-level evidence.

Usage:
    python data/tools/fetch_nyc_sessions.py --out tmp/raw/kj7g-u4gp_all.jsonl

Writes <out> plus <out>.manifest.json.  No existing data file is overwritten
unless --force is given.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

import requests

HOST = "https://data.cityofnewyork.us"
RID = "kj7g-u4gp"
PAGE = 50000


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count(session: requests.Session, where: str | None = None) -> int:
    params = {"$select": "count(*) as n"}
    if where:
        params["$where"] = where
    r = session.get(f"{HOST}/resource/{RID}.json", params=params, timeout=120)
    r.raise_for_status()
    return int(r.json()[0]["n"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("tmp", "raw", "kj7g-u4gp_all.jsonl"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--where", default=None,
                    help="optional SoQL $where filter, e.g. \"date >= '2025-10-15'\"")
    args = ap.parse_args()
    if os.path.exists(args.out) and not args.force:
        print("refusing to overwrite %s (use --force)" % args.out)
        return 2

    s = requests.Session()
    s.headers["User-Agent"] = "research-datacheck/1.0"
    total = count(s, args.where)
    print("dataset rows reported by API:", total)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    tmp = args.out + ".part"
    n, pages, offset, t0 = 0, 0, 0, time.time()
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        while offset < total and pages < args.max_pages:
            params = {"$limit": PAGE, "$offset": offset, "$order": ":id"}
            if args.where:
                params["$where"] = args.where
            for attempt in range(4):
                try:
                    r = s.get(f"{HOST}/resource/{RID}.json", params=params, timeout=300)
                    r.raise_for_status()
                    rows = r.json()
                    break
                except Exception as exc:  # noqa: BLE001 - retry on transport errors
                    print("  page offset=%d attempt=%d error=%s" % (offset, attempt + 1, exc))
                    time.sleep(2 + attempt * 3)
            else:
                print("failed at offset %d" % offset)
                return 1
            if not rows:
                break
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            n += len(rows)
            pages += 1
            print("  page %d: offset=%d rows=%d cumulative=%d" % (pages, offset, len(rows), n))
            offset += PAGE

    os.replace(tmp, args.out)
    manifest = {
        "dataset": f"{HOST}/d/{RID}",
        "api_endpoint": f"{HOST}/resource/{RID}.json",
        "query": {"limit": PAGE, "offset": "0..%d" % (offset - PAGE), "order": ":id", "where": args.where},
        "rows_reported_by_api": total,
        "rows_downloaded": n,
        "bytes": os.path.getsize(args.out),
        "sha256": sha256(args.out),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "seconds": round(time.time() - t0, 1),
        "command": "python data/tools/fetch_nyc_sessions.py --out %s" % args.out,
        "fields": sorted(json.loads(open(args.out, encoding="utf-8").readline()).keys()),
    }
    with open(args.out + ".manifest.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print("downloaded %d/%d rows -> %s (%.1f MB, %.0fs)"
          % (n, total, args.out, manifest["bytes"] / 1e6, manifest["seconds"]))
    return 0 if n == total else 1


if __name__ == "__main__":
    sys.exit(main())
