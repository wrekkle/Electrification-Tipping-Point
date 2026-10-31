# -*- coding: utf-8 -*-
import json, math
ROOT = r"C:\Projects\停车场充电桩优化方案"
b = json.load(open(ROOT + r"\research\round6_20261031\b_feasible\q3_feasible_sets.json", encoding="utf-8"))
sets = b["sets"]
print("SAMPLE SET RECORD:", json.dumps(sets["REF|B|TPE0008|1"], ensure_ascii=False)[:400])
def K(rule, lot, seed):
    return sets.get("REF|%s|%s|%s" % (rule, lot, seed), {})
for r1, r2 in (("B","D"), ("C","D")):
    print("==", r1, "vs", r2)
    for key in sorted(sets):
        parts = key.split("|")
        if len(parts) != 4 or parts[0] != "REF": continue
        _, rule, lot, seed = parts
        if rule != r1: continue
        a = K(r1, lot, seed); c = K(r2, lot, seed)
        Ka, Kb = a.get("K") or [], c.get("K") or []
        if Ka and Kb and min(Kb) < min(Ka):
            print(" ", lot, seed, r1, "min", min(Ka), "K", Ka[:6], "...", "|", r2, "min", min(Kb), "K", Kb[:6], "...")
        if Ka and Kb and min(Ka) < min(Kb):
            print("  (reverse)", lot, seed, r1, "min", min(Ka), Kb[:4], r2, "min", min(Kb))
