import sys, pymupdf
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = pymupdf.open(sys.argv[1])
for p in [int(x) for x in sys.argv[2].split(",")]:
    print(f"===== PAGE {p} =====")
    print(d[p-1].get_text()[:3000])
