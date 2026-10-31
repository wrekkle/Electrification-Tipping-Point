"""T28 evidence fetch: log every request, save raw, hash. Owner: ev-data (write scope: identification_20261031/)."""
import hashlib, json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw"); LOG = os.path.join(BASE, "t28_requests.jsonl")
MAX_REQ, MAX_BYTES = 20, 60 * 1024 * 1024
os.makedirs(RAW, exist_ok=True)
rows = [json.loads(l) for l in open(LOG, encoding="utf-8")] if os.path.exists(LOG) else []
spec = json.load(open(sys.argv[1], encoding="utf-8"))
seq = len(rows); used = sum(int(r.get("bytes") or 0) for r in rows)
for job in spec["jobs"]:
    if seq >= MAX_REQ: print("BUDGET"); break
    t = datetime.now(timezone.utc).isoformat(timespec="seconds")
    req = urllib.request.Request(job["url"], headers={"User-Agent":"Mozilla/5.0 ev-data-t28/1.0","Accept":"*/*","Accept-Language":"zh-TW,zh;q=0.9,en;q=0.8"})
    status=None; data=b""; err=None
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            status=resp.status; data=resp.read()
    except urllib.error.HTTPError as e:
        status=e.code; err=f"HTTPError {e.code} {e.reason}"
        try: data=e.read()
        except Exception: data=b""
    except Exception as e:
        err=f"{type(e).__name__}: {e}"
    saved=None; sha=None; n=0
    if status==200 and data:
        fn=job["filename"]; p=os.path.join(RAW,fn)
        open(p,"wb").write(data)
        saved="research/official_data_20261031/identification_20261031/raw/"+fn
        sha=hashlib.sha256(data).hexdigest(); n=len(data); used+=n
    seq+=1
    row={"seq":seq,"t_utc":t,"method":"GET","url":job["url"],"purpose":job["purpose"],"status":status,"bytes":n,"sha256":sha,"saved_path":saved,"error":err}
    with open(LOG,"a",encoding="utf-8") as fh: fh.write(json.dumps(row, ensure_ascii=False)+"\n")
    print(json.dumps({"seq":seq,"status":status,"bytes":n,"saved":saved,"err":err}, ensure_ascii=False))
print(json.dumps({"requests":seq,"bytes":used}))
