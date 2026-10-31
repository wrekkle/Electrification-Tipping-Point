# -*- coding: utf-8 -*-
import json, os, re
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
R3 = os.path.join(ROOT, "research", "round3_20261031", "results")
files = {"A": "main_A_pi0_ref_s10.json", "B": "main_B_pi1_ref_s10.json",
         "C": "main_C_quota_ref_s10.json", "D": "main_D_pi2_ref_s10.json"}
for rule, fn in files.items():
    d = json.load(open(os.path.join(R3, fn), encoding="utf-8"))
    rows = [r for r in d["rows"] if r.get("lot_id") == "TPE1376" and r.get("seed") == 10]
    rows.sort(key=lambda r: r["k"])
    print("==", rule, "nrows", len(rows), "kmax", max(r["k"] for r in rows))
    for r in rows:
        if r["k"] not in (0, 1, 2, 3, 5, 10, 20, 23, 24, 25): continue
        sm = r.get("service_metrics") or {}
        rates = sm.get("rates") or {}
        dens = sm.get("denominators") or {}
        print("  k=%2d cap=%s den=%s | ev=%s den=%s | ice=%s den=%s" % (
            r["k"], r.get("capacity_only_unmet_rate"), r.get("charge_requests"),
            rates.get("ev_parking_failure_rate"), dens.get("exogenous_ev_visits"),
            rates.get("ice_parking_failure_rate"), dens.get("exogenous_ice_visits")))
meta = json.load(open(os.path.join(R3, files["D"]), encoding="utf-8")).get("meta") or {}
print("META_D:", json.dumps({k: meta.get(k) for k in ("rule", "scenario_model", "p_ev_override", "q_need_override", "feeder_kw", "charger_kw", "horizon_min")}, ensure_ascii=False))
doc = Document(os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6.docx"))
paras = [p.text.strip() for p in doc.paragraphs]
keys = ["positive change", "device", "smaller", "saving", "information", "value of information",
        "interval", "truncated", "k=40", "0 to 40", "no positive", "never", "optimal"]
for kw in keys:
    hits = [(i, t) for i, t in enumerate(paras) if kw.lower() in t.lower()]
    print("KW[%s]: %d" % (kw, len(hits)))
    for i, t in hits[:5]:
        print("   %d | %s" % (i, t[:260]))
