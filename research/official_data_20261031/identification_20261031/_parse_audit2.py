
import fitz, re, os, hashlib
base = os.path.join(r"C:\Projects\停车场充电桩优化方案","research","official_data_20261031","identification_20261031")
raw=os.path.join(base,"raw"); txt=os.path.join(base,"raw_text")
for fn in os.listdir(raw):
    if not fn.startswith("t28_audit_ev_market_share"): continue
    p=os.path.join(raw,fn); doc=fitz.open(p)
    t="".join("\n===== PDF PAGE %d =====\n"%i+x.get_text() for i,x in enumerate(doc))
    open(os.path.join(txt,"t28_audit_ev_market_share.txt"),"w",encoding="utf-8").write(t)
    print("PAGES",doc.page_count,"BYTES",os.path.getsize(p),"SHA",hashlib.sha256(open(p,"rb").read()).hexdigest()[:16])
    for kw in ["市售比","電動小客車","負成長","達成率"]:
        for m in list(re.finditer(kw,t))[:4]:
            print(" ",kw,"|",t[max(0,m.start()-160):m.start()+240].replace("\n"," / ")[:400])
