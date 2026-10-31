import json, os
OUT = r"C:/Projects/停车场充电桩优化方案/research/integer_allocation_20261031/outputs"
ft = json.load(open(os.path.join(OUT, "final_tables.json"), encoding="utf-8"))
print("ANALYTIC rows:")
for r in ft["formula_benchmark"]["connector_occupancy_rule"]["rows_alpha_0.05"]:
    print(" ", r["lot"], "A_conn=%.2f" % r["offered_load_erlang"], "k_analytic", r["k_analytic"], "k_sim5", r["k_sim_5"], "usable", r["usable"], r["split"])
rc = json.load(open(os.path.join(OUT, "rule_comparison_real_traffic.json"), encoding="utf-8"))
print("RULE type occupancy:", json.dumps(rc["type_occupancy_mean_by_rule"], ensure_ascii=False))
for name in ("pi1_minus_pi0","pi2_minus_pi0","pi2_minus_pi1"):
    print(name)
    for metric, val in rc["comparisons"][name].items():
        print("   %-32s %10.4f  [%.4f, %.4f] n=%d" % (metric, val["mean_diff"], val["ci_low"] or 0, val["ci_high"] or 0, val["n"]))
rcp = json.load(open(os.path.join(OUT, "pev_sensitivity.json"), encoding="utf-8"))
print("PEV median k5:")
for pev, per in rcp["by_pev"].items():
    vals = sorted(v["k_5"] for v in per.values() if v["k_5"] is not None)
    med = vals[len(vals)//2] if vals else None
    print(" ", pev, "k5", [v["k_5"] for v in per.values()], "median", med)
an = json.load(open(os.path.join(OUT, "analysis_pi0.json"), encoding="utf-8"))
print("BREAK-EVEN L* per lot (k->k+1):")
for lot, rec in an["lots"].items():
    be = rec["break_even_loss_per_unserved"]
    items = sorted(((int(k), v) for k, v in be.items() if v is not None), key=lambda kv: kv[0])[:4]
    print(" ", lot, rec.get("usable"), [(k, round(v,1)) for k, v in items])
print("LOSS k* (usable lots):")
for loss in ("10.0","50.0","100.0","200.0","500.0"):
    vals = [(lot, rec["k_star_by_loss"].get(loss)) for lot, rec in an["lots"].items() if rec.get("usable")]
    print(" ", loss, vals)
