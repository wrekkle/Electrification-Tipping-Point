"""Inspect a PDF: page count, sha256, page-1 head, and keyword line hits by page."""
import hashlib
import re
import sys

import pymupdf


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = sys.argv[1]
    pattern = sys.argv[2] if len(sys.argv) > 2 else r"(minute|minutes|fuel|mile|km|search|time value|\$)"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    raw = open(path, "rb").read()
    print("PATH:", path)
    print("BYTES:", len(raw))
    print("SHA256:", hashlib.sha256(raw).hexdigest())
    doc = pymupdf.open(path)
    print("PAGES:", doc.page_count)
    head = doc[0].get_text()
    print("--- PAGE1 HEAD ---")
    print(head[:1200])
    kw = re.compile(pattern, re.I)
    print("--- KEYWORD HITS (page: line) ---")
    per_page = 0
    for i in range(doc.page_count):
        hits = [ln.strip() for ln in doc[i].get_text().splitlines() if kw.search(ln)]
        if hits:
            print(f"[p{i+1}] hits={len(hits)}")
            for h in hits[:limit]:
                print("   ", h[:190])
            per_page += 1
        if per_page >= 12:
            print("....(more pages truncated)")
            break


if __name__ == "__main__":
    main()
