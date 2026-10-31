"""Dump selected PDF pages as plain text (verification aid, not a deliverable)."""
import sys

import pymupdf


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = sys.argv[1]
    pages = [int(x) for x in sys.argv[2].split(",")]
    doc = pymupdf.open(path)
    for p in pages:
        print(f"\n########## PAGE {p} ##########")
        print(doc[p - 1].get_text())


if __name__ == "__main__":
    main()
