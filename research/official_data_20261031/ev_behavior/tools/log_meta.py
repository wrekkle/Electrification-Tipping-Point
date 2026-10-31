
import json, os, sys
base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log = os.path.join(os.path.dirname(base), "logs", "ev_behavior_requests.jsonl")
os.makedirs(os.path.dirname(log), exist_ok=True)
rows = []
if os.path.exists(log):
    rows = [json.loads(l) for l in open(log, encoding="utf-8") if l.strip()]
meta = json.load(open(sys.argv[1], encoding="utf-8"))
maxseq = max([r["seq"] for r in rows if isinstance(r.get("seq"), int)] or [0])
with open(log, "a", encoding="utf-8") as f:
    for m in meta:
        maxseq += 1
        m["seq"] = maxseq
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("logged", len(meta), "rows; next seq", maxseq + 1)
