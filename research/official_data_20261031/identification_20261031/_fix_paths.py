
import os, json, hashlib
base = os.path.join(r"C:\Projects\停车场充电桩优化方案","research","official_data_20261031")
ident = os.path.join(base,"identification_20261031")
wrong_log = os.path.join(base,"t28_requests.jsonl")
right_log = os.path.join(ident,"t28_requests.jsonl")
wrong_raw = os.path.join(base,"raw"); right_raw = os.path.join(ident,"raw")
os.makedirs(right_raw, exist_ok=True)
rows=[json.loads(l) for l in open(wrong_log,encoding="utf-8")]
for r in rows:
    if r.get("saved_path"):
        fn=os.path.basename(r["saved_path"]); src=os.path.join(wrong_raw,fn); dst=os.path.join(right_raw,fn)
        if os.path.exists(src): os.replace(src,dst)
        r["saved_path"]="research/official_data_20261031/identification_20261031/raw/"+fn
        r["sha256"]=hashlib.sha256(open(dst,"rb").read()).hexdigest(); r["bytes"]=os.path.getsize(dst)
with open(right_log,"w",encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r,ensure_ascii=False)+"\n")
os.remove(wrong_log)
try: os.rmdir(wrong_raw)
except OSError: print("raw dir not empty:", os.listdir(wrong_raw))
print(json.dumps([{"seq":r["seq"],"file":os.path.basename(r["saved_path"]) if r.get("saved_path") else None,"status":r["status"],"bytes":r["bytes"],"sha256":(r["sha256"] or "")[:16]} for r in rows], ensure_ascii=False, indent=1))
