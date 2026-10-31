
"""Sequential HTTP fetch with request log, sha256, byte accounting. Owner: ev-data."""
import json, hashlib, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(os.path.dirname(ROOT), "logs", "ev_behavior_requests.jsonl")
MAX_REQ, MAX_BYTES = 60, 200 * 1024 * 1024

def read_log():
    if not os.path.exists(LOG):
        return []
    with open(LOG, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

def main(spec_path):
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    rows = read_log()
    used_bytes = sum(int(r.get("bytes") or 0) for r in rows)
    seq = len(rows)
    outdir = os.path.join(ROOT, "raw")
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    results = []
    for job in spec["jobs"]:
        if seq >= MAX_REQ:
            results.append({"url": job["url"], "error": "REQUEST_BUDGET_EXCEEDED"}); break
        hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
                "Accept": "*/*", "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"}
        hdrs.update(job.get("headers") or {})
        req = urllib.request.Request(job["url"], headers=hdrs)
        t = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status = None; data = b""; err = None
        try:
            try:
                import requests as _rq
                _r = _rq.get(job["url"], headers=hdrs, timeout=90, allow_redirects=True)
                status = _r.status_code
                data = _r.content
            except ImportError:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    status = resp.status
                    data = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code; err = f"HTTPError {e.code} {e.reason}"
            try: data = e.read()
            except Exception: data = b""
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        saved = None; sha = None; nbytes = 0
        if status == 200 and data:
            fname = job.get("filename") or os.path.basename(job["url"].split("?")[0]) or "download.bin"
            fname = fname.replace("/", "_").replace("\\\\", "_")
            p = os.path.join(outdir, fname)
            with open(p, "wb") as f:
                f.write(data)
            saved = os.path.relpath(p, os.path.dirname(ROOT)).replace("\\", "/")
            sha = hashlib.sha256(data).hexdigest()
            nbytes = len(data)
            used_bytes += nbytes
        seq += 1
        row = {"seq": seq, "t_utc": t, "method": "GET", "url": job["url"], "purpose": job["purpose"],
               "status": status, "bytes": nbytes, "sha256": sha, "saved_path": saved, "error": err}
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        results.append(row)
        print(json.dumps({"seq": seq, "status": status, "bytes": nbytes, "saved": saved, "url": job["url"], "err": err}, ensure_ascii=False))
        if used_bytes > MAX_BYTES:
            if seq < MAX_REQ: print("BYTE_BUDGET_EXCEEDED"); break
    print(json.dumps({"requests_used": seq, "bytes_used": used_bytes, "results": len(results)}))

if __name__ == "__main__":
    main(sys.argv[1])
