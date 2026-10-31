import sys, pymupdf, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = pymupdf.open("research/official_data_20261031/social_cost/raw/pdf/dgbas_price_monthly.pdf")
t = d[50].get_text()
lines = [l.strip() for l in t.splitlines()]
# print rows containing 民國 98/107/113/114 and the YEARLY index context
for i, l in enumerate(lines):
    if re.search(r"民國\s*(98|107|108|113|114)\s*年", l) or re.match(r"^(19|20)\d\d$", l):
        print(i, l, "|", " ".join(lines[max(0,i-2):i+1])[:120])
print("---- raw tail ----")
print(t[-2500:])
