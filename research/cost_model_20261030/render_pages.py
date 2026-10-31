"""Render selected PDF pages to PNG for visual reading (scanned sources)."""
import sys

import pymupdf


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path, pages, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    dpi = int(sys.argv[4]) if len(sys.argv) > 4 else 120
    doc = pymupdf.open(path)
    for p in [int(x) for x in pages.split(",")]:
        pix = doc[p - 1].get_pixmap(dpi=dpi)
        out = f"{outdir}/page{p:02d}.png"
        pix.save(out)
        print("WROTE", out, pix.width, "x", pix.height)


if __name__ == "__main__":
    main()
