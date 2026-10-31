"""Dump regex hits from a saved text/HTML/JSON file (stdout only)."""
import re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
path, pat = sys.argv[1], sys.argv[2]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 40
enc = sys.argv[4] if len(sys.argv) > 4 else "utf-8"
t = open(path, "rb").read().decode(enc, "replace")
print("### FILE", path, "chars", len(t))
lines = t.splitlines()
hits = [(i + 1, ln.strip()) for i, ln in enumerate(lines) if re.search(pat, ln, re.I)]
print("hits", len(hits))
for i, ln in hits[:limit]:
    print(i, ln[:220])
