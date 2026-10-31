# -*- coding: utf-8 -*-
import json, os
ROOT = r"C:\Projects\停车场充电桩优化方案"
R3 = os.path.join(ROOT, "research", "round3_20261031", "results")
for rule, fn in {"A":"main_A_pi0_ref_s10.json","B":"main_B_pi1_ref_s10.json","C":"main_C_quota_ref_s10.json","D":"main_D_pi2_ref_s10.json"}.items():
    meta = json.load(open(os.path.join(R3, fn), encoding="utf-8")).get("meta") or {}
    print(rule, json.dumps({k: meta.get(k) for k in ("rule","description","info_regime","information_regime","uses_needs_charge","predictor","scenario")}, ensure_ascii=False))
