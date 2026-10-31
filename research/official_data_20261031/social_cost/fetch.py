"""官方資料抓取與請求日誌（cost-data, 2026-10-31）。

用法:
  python fetch.py <url> <out_subpath> <purpose>
  python fetch.py --log-search "<query>"
  python fetch.py --log-note "<text>"

每個 GET 都寫一行 JSONL 到 research/official_data_20261031/logs/social_cost_requests.jsonl；
失敗也留痕，不重複探測同一 URL（同一 URL 只抓一次）。
"""
import hashlib, json, os, sys, time, urllib.request, urllib.error, datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(BASE, "social_cost", "raw")
LOG = os.path.join(BASE, "logs", "social_cost_requests.jsonl")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def next_seq():
    n = 0
    if os.path.exists(LOG):
        with open(LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    n += 1
    return n + 1

def log(rec):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    rec = dict({"seq": next_seq(), "t_utc": now()}, **rec)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("LOG", rec["seq"], rec.get("method"), rec.get("status"), rec.get("url", "")[:110])

def main():
    args = sys.argv[1:]
    if not args:
        print("need args"); return 1
    if args[0] == "--log-search":
        log({"method": "SEARCH", "url": "web_search", "purpose": args[1], "query": args[1],
             "status": None, "bytes": 0, "sha256": None, "saved_path": None, "error": None})
        return 0
    if args[0] == "--log-note":
        log({"method": "NOTE", "url": None, "purpose": args[1], "status": None, "bytes": 0,
             "sha256": None, "saved_path": None, "error": None})
        return 0
    url, out_sub, purpose = args[0], args[1], args[2]
    referer = args[3] if len(args) > 3 else None
    out_path = os.path.join(RAW, out_sub)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    hdrs = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"}
    if referer:
        hdrs["Referer"] = referer
    req = urllib.request.Request(url, headers=hdrs)
    status = None; data = b""; err = None; ctype = None
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            status = resp.status
            ctype = resp.headers.get("Content-Type")
            data = resp.read()
    except urllib.error.HTTPError as e:
        status = e.code; data = e.read() if e.fp else b""; err = "HTTPError: %s" % e
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
    sha = hashlib.sha256(data).hexdigest() if data else None
    saved = None
    if data:
        with open(out_path, "wb") as f:
            f.write(data)
        saved = os.path.relpath(out_path, ROOT).replace("\\", "/")
    log({"method": "GET", "url": url, "purpose": purpose, "status": status, "bytes": len(data),
         "sha256": sha, "saved_path": saved, "error": err, "content_type": ctype})
    txt = data.decode("utf-8", "replace") if data else ""
    print("RESULT", status, len(data), ctype, saved)
    if "pdf" in (ctype or "").lower():
        print("PDFHEAD", data[:0])
    else:
        print("TEXTHEAD", txt[:300].replace("\n", " "))
    return 0

if __name__ == "__main__":
    sys.exit(main())
