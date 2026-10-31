"""POST 表單並落盤（cost-data，2026-10-31）。用法：python fetch_post.py <url> <out_subpath> <purpose> <k=v> [k=v ...]"""
import hashlib, json, os, sys, urllib.request, urllib.parse, urllib.error, datetime

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(BASE, "social_cost", "raw")
LOG = os.path.join(BASE, "logs", "social_cost_requests.jsonl")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

def next_seq():
    n = 0
    if os.path.exists(LOG):
        with open(LOG, "r", encoding="utf-8") as f:
            n = len([ln for ln in f if ln.strip()])
    return n + 1

def log(rec):
    rec = dict({"seq": next_seq(), "t_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, **rec)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("LOG", rec["seq"], "POST", rec.get("status"), rec.get("url", "")[:110])

def main():
    url, out_sub, purpose = sys.argv[1], sys.argv[2], sys.argv[3]
    pairs = [a.split("=", 1) for a in sys.argv[4:]]
    body = urllib.parse.urlencode({k: v for k, v in pairs}).encode()
    out_path = os.path.join(RAW, out_sub)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json, */*", "Referer": "https://www2.moeaea.gov.tw/oil111/Gasoline/RetailPrice"})
    status, data, err, ctype = None, b"", None, None
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            status = resp.status; ctype = resp.headers.get("Content-Type"); data = resp.read()
    except urllib.error.HTTPError as e:
        status = e.code; data = e.read() if e.fp else b""; err = "HTTPError: %s" % e
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
    sha = hashlib.sha256(data).hexdigest() if data else None
    saved = None
    if data:
        open(out_path, "wb").write(data)
        saved = os.path.relpath(out_path, os.path.abspath(os.path.join(BASE, "..", "..", ".."))).replace("\\", "/")
    log({"method": "POST", "url": url, "purpose": purpose, "status": status, "bytes": len(data), "sha256": sha, "saved_path": saved, "error": err, "content_type": ctype, "post_body": body.decode()})
    print("RESULT", status, len(data), ctype, saved)
    print("HEAD", data[:400].decode("utf-8", "replace").replace("\n", " "))
    return 0

if __name__ == "__main__":
    sys.exit(main())
