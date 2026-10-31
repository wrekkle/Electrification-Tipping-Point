"""PDF keyword probe (only stdout; not a deliverable)."""
import re, sys
import fitz
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
kw = re.compile(sys.argv[2] if len(sys.argv) > 2 else r"(時間價值|油價|電價|費率|係數|CO2|充電|元/|度|每度|車|停車)")
d = fitz.open(sys.argv[1])
print("FILE:", sys.argv[1], "PAGES:", d.page_count)
for i in range(d.page_count):
    t = d[i].get_text()
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    hits = [ln for ln in lines if kw.search(ln)]
    if hits:
        print(f"=== PAGE {i+1}")
        for h in hits[:25]:
            print("   ", h[:180])
