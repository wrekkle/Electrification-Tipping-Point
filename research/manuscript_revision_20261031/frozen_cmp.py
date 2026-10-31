# -*- coding: utf-8 -*-
import os,hashlib
ROOT="C:/Projects/停车场充电桩优化方案"
man="research/round6_20261031/lead/frozen_sha256_after_round6b.txt"
changed=[]; missing=[]; n=0
for line in open(os.path.join(ROOT,man),encoding="utf-8"):
    line=line.rstrip("\n")
    if not line.strip(): continue
    h,_,rel=line.partition("  ")
    rel=rel.strip()
    p=os.path.join(ROOT,rel)
    n+=1
    if not os.path.exists(p): missing.append(rel); continue
    cur=hashlib.sha256(open(p,"rb").read()).hexdigest()
    if cur.lower()!=h.lower(): changed.append((rel,h.lower(),cur))
print("N",n,"CHANGED",len(changed),"MISSING",len(missing))
for x in changed: print("CHANGED",x[0],x[1][:12],x[2][:12])
for x in missing: print("MISSING",x)
