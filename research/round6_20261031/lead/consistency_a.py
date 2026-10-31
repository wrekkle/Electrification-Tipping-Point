# -*- coding: utf-8 -*-
import json, math, re
ROOT = r"C:\Projects\停车场充电桩优化方案"
b = json.load(open(ROOT + r"\research\round6_20261031\b_feasible\q3_feasible_sets.json", encoding="utf-8"))
print("PAIR KEYS:", len(b["pairs"]))
for key, v in b["pairs"].items():
    if v.get("device_saving") or v.get("restoration"):
        print("PAIR", key, "pairs", v.get("pairs"), "restoration", v.get("restoration"),
              "device_saving", v.get("device_saving"), "same_k_imp", v.get("same_k_improvement"),
              "same_k_worse", v.get("same_k_worse"), "disjoint", v.get("both_disjoint"))
        for ex in v.get("examples", [])[:6]:
            if ex.get("category") in ("only_second", "both") or ex.get("inclusion") not in ("equal",):
                print("   EX:", {k: ex.get(k) for k in ("scenario","lot","seed","a","b","K_a","K_b","inclusion","category")})
# find exact saving examples with K differences
print("SAVING DETAIL:")
for key, v in b["pairs"].items():
    if v.get("device_saving"):
        for ex in v.get("examples", []):
            print(" ", key, "|", ex.get("scenario"), ex.get("lot"), ex.get("seed"), ex.get("a"), ex.get("b"),
                  "K_a", ex.get("K_a"), "K_b", ex.get("K_b"), "cat", ex.get("category"), "incl", ex.get("inclusion"))
