#!/usr/bin/env python3
"""P4: pointwise dependence sensitivity for the V2 cells with nominal p<0.05.

This is NOT a coverage repair.  It answers one narrower question: if the
certificate radius is replaced by a moving-block bootstrap quantile (block
length 7/14 days) and the held-out p-value is recomputed with a Newey-West
effective sample size, do the same cells still look significant?  The answer is
reported as a sensitivity, not as a 95% simultaneous guarantee.

Shared resampling indices: for each cell and block length, B moving-block
resamples are drawn ONCE and reused for every candidate n.  The previous
implementation used seed+n per n, so the n_corr path was not a single
resampling surface.

All-zero boundary (kept as a counterexample): with m=50 and true tail
probability .02, P(all 50 observations are zero) = .98**50 = 36.42%; a bootstrap
that sees only zeros returns bound=0.  Any n_corr that lands on p_hat=0 is
therefore not a 95% upper bound, no matter how the blocks are drawn.

Outputs
- data/demand_v2/p4_dependence.json (versioned)
- docs/reports/2026-11-03-P4-依赖敏感性-v2.md
Run via data/tools/rebuild_nyc_v2.py; standalone defaults still point at v1.
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from block_bootstrap import vif_newey_west, mbb_tail_bound, mbb_tail_bounds, mbb_rate_ci  # noqa: E402
from v2_holdout import CONVENTIONS, ALPHA, folds_for, binom_sf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
B = 2000
BLOCKS = (7, 14)
SITES = os.path.join(ROOT, "data", "charger_sites", "nyc_v1", "sites.jsonl")
DEMAND = os.path.join(ROOT, "data", "demand")
V2_JSON = os.path.join(ROOT, "data", "demand", "v2_holdout.json")
OUT_JSON = os.path.join(ROOT, "data", "demand", "p4_dependence.json")
OUT_MD = os.path.join(ROOT, "docs", "reports", "2026-11-02-P4-依赖修正.md")


def tail(vals, n):
    return sum(1 for w in vals if w > n) / len(vals)


def iid_radius(m):
    return math.sqrt(math.log(1.0 / ALPHA) / (2 * m))


def corrected_capacity(tr_vals, rho, L, seed):
    """Pointwise block-bootstrap n_corr with ONE set of indices for all n."""
    hi = max(tr_vals)
    bounds = mbb_tail_bounds(tr_vals, list(range(hi + 1)), L, B, ALPHA, seed)
    d_iid = iid_radius(len(tr_vals))
    for n in range(hi + 1):
        if bounds[n]["bound"] <= rho + 1e-12:
            return n, bounds, d_iid
    return None, bounds, d_iid


def main(sites_path=None, v2_json=None, demand_dir=None, out_json=None, out_md=None, version="v1"):
    sites_path = sites_path or SITES
    v2_json = v2_json or V2_JSON
    demand_dir = demand_dir or DEMAND
    out_json = out_json or OUT_JSON
    out_md = out_md or OUT_MD
    sites = {json.loads(l)["site_id"]: json.loads(l) for l in open(sites_path, encoding="utf-8") if l.strip()}
    v2 = json.load(open(v2_json, encoding="utf-8"))
    sig = [r for r in v2["rows"]
           if r["status"] == "tested" and r["p_value"] is not None and r["p_value"] < ALPHA]
    out = []
    for idx, cell in enumerate(sig):
        sid, conv, scheme, fold, rho, n = (cell["site_id"], cell["convention"], cell["scheme"],
                                           cell["fold"], cell["rho"], cell["n"])
        q = json.load(open(os.path.join(demand_dir, sid, "quality.json"), encoding="utf-8"))
        pv = {k: int(v) for k, v in q[CONVENTIONS[conv]].items()}
        days = sorted(pv)
        train = test = None
        for label, tr, te in folds_for(days):
            if label == fold:
                train, test = tr, te
        if train is None:
            print("SKIP no fold", sid, scheme, fold)
            continue
        tr_vals = [pv[d] for d in train]
        te_vals = [pv[d] for d in test]
        n_obs = sites[sid]["service_points"]
        ind = [1 if w > n else 0 for w in te_vals]
        vif_te = vif_newey_west(ind, max_lag=28)
        # Deflate the count, not the denominator: x_eff = rate * n_eff.
        n_eff = max(1, round(len(test) / vif_te))
        x_eff = int(round(cell["x"] * n_eff / len(test)))
        p_adj = binom_sf(x_eff, n_eff, rho)
        row = {"site_id": sid, "convention": conv, "scheme": scheme, "fold": fold, "rho": rho,
               "n_iid": n, "n_obs": n_obs, "train_m": len(train), "test_m": len(test),
               "x": cell["x"], "rate": cell["rate"], "p_nominal": cell["p_value"],
               "vif_train": round(vif_newey_west(tr_vals, max_lag=28), 4),
               "vif_test": round(vif_te, 4),
               "n_eff_test": n_eff, "x_eff": x_eff,
               "p_adj": round(p_adj, 6), "blocks": {}}
        bounds_by_L = {}
        for L in BLOCKS:
            n_corr, bounds, d_iid = corrected_capacity(tr_vals, rho, L, seed=1000 * L + idx)
            bounds_by_L[L] = bounds
            ci = mbb_rate_ci(te_vals, n, L, B, ALPHA, seed=7000 * L + idx)
            tb = bounds[n_corr if n_corr is not None else n]
            row["blocks"][str(L)] = {
                "d_plus_iid": round(d_iid, 6), "d_plus_block": round(tb["q"], 6),
                "bound_at_n_iid": round(bounds[n]["bound"], 6),
                "n_corr": n_corr, "censored_corr": (n_corr is None or n_corr >= n_obs),
                "rate_ci_lo": round(ci["lo"], 6), "rate_ci_hi": round(ci["hi"], 6),
                "ci_covers_rho": (ci["lo"] <= rho <= ci["hi"]),
            }
        row["same_n_still_certifies_L14"] = bool(bounds_by_L[14][n]["bound"] <= rho + 1e-12)
        lo14 = row["blocks"]["14"]["rate_ci_lo"]
        row["significant_after_correction"] = bool(p_adj < ALPHA and lo14 > rho)
        out.append(row)
        print(f"{sid:9s} {conv} {scheme:6s} {fold:6s} rho={rho:.2f} n={n:2d} rate={row['rate']:.4f} "
              f"p={row['p_nominal']:.4f} vif_te={vif_te:.2f} n_eff={row['n_eff_test']} p_adj={p_adj:.4f} "
              f"n_corr7={row['blocks']['7']['n_corr']} n_corr14={row['blocks']['14']['n_corr']} "
              f"CI14=[{lo14:.3f},{row['blocks']['14']['rate_ci_hi']:.3f}] "
              f"survives={row['significant_after_correction']}")

    zero_bound = mbb_tail_bound([0] * 50, 0, 7, B, ALPHA, seed=1)["bound"]
    zero_true = 0.98 ** 50
    json.dump({"alpha": ALPHA, "B": B, "blocks": list(BLOCKS), "version": version,
               "label": "pointwise dependence sensitivity; not a simultaneous coverage certificate",
               "shared_indices_across_thresholds": True,
               "all_zero_counterexample": {"m": 50, "true_tail": 0.02,
                                            "prob_all_zero": round(zero_true, 6),
                                            "bootstrap_bound": zero_bound},
               "definition": {"d_plus_block": "moving-block bootstrap (1-alpha) quantile of the bias of T_hat(n), circular blocks, one shared index set per cell/block length",
                              "p_adj": "one-sided binomial with n_eff = m_test / Newey-West VIF of 1{W_d>n}; approximate diagnostic",
                              "n_corr": "min n with min(1, T_hat(n) + d+_block(n)) <= rho; pointwise sensitivity"},
               "cells": out},
              open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    lines = ["# P4 依赖敏感性（点态，不是覆盖修复）", "",
             "类型: 研究报告", "状态: 生效", "负责人: tho25", "日期: 2026-11-03",
             "生成命令: 由 data/tools/rebuild_nyc_v2.py 调用 p4_dependence.main（version=%s）" % version, "",
             "## 0 一句话", ""]
    if not out:
        lines += ["v2_holdout 中没有任何 p<0.05 的可检验单元，无需做敏感性重算。", ""]
    else:
        surv = [r for r in out if r["significant_after_correction"]]
        uniq = sorted({(r["site_id"], r["rho"]) for r in out})
        uniq_surv = sorted({(r["site_id"], r["rho"]) for r in surv})
        lines += [f"对 V2 的 {len(out)} 个名义显著单元做移动块自助（L=7/14，B={B}）与有效样本量重算，"
                  f"敏感性判定下仍显著 {len(surv)} 个。qbo 的 D/S 峰值序列相同，6 个单元去重后是 "
                  f"{len(uniq)} 个 (site,rho)，仍显著 {len(uniq_surv)} 个。该数字是点态敏感性，"
                  "不是全阈值同时覆盖，也不能反过来说未显著的单元就一定来自块相关。", ""]
    lines += ["## 1 方法", "",
              "- 证书侧：d+_block(n) = q_{1-α}(T̂*(n) − T̂(n))，Q(n)=min(1, T̂(n)+d+_block(n))，"
              "n_corr = min{n : Q(n) ≤ ρ}。每个单元/块长只抽一组 B 个重采样索引，所有 n 共用。",
              "- 检验侧：对 1{W_d>n} 做 Newey-West 方差膨胀，n_eff = m_test/vif，"
              "用 n_eff 重算单侧二项 p（近似诊断），并给留出过载率的移动块 CI。",
              f"- 参数：B={B}，块长 7/14 天，α={ALPHA}，环形块；共享索引的 seed 由块长与单元序号决定。",
              "- d+_block 是偏差分布的 95% 分位，不是 Massart 那样的有限样本上界；"
              "n_corr 可能小于 n_iid，不能把较小值解读为更保守。",
              "",
              "### 全零边界反例（保留）", "",
              f"m=50、真实尾概率 .02 时，P(全零)=.98^50={zero_true:.4f}（约 {100*zero_true:.2f}%）；"
              f"bootstrap 在只看到零的样本上返回 bound={zero_bound:.1f}。因此任何 p_hat=0 处的 n_corr "
              "都不是 95% 有限样本上界；共享索引也不能修复这个边界。",
              "", "## 2 逐单元", "",
              "| site | conv | scheme | fold | rho | n(i.i.d.) | rate | p | vif(test) | x_eff/n_eff | p_adj | n_corr L7 | n_corr L14 | MBB 95% CI (L14) | 敏感性判定 |",
              "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for r in out:
        b7, b14 = r["blocks"]["7"], r["blocks"]["14"]
        lines.append(f"| {r['site_id']} | {r['convention']} | {r['scheme']} | {r['fold']} | {r['rho']:.2f} | "
                     f"{r['n_iid']} | {100*r['rate']:.1f}% | {r['p_nominal']:.4f} | {r['vif_test']:.2f} | "
                     f"{r['x_eff']}/{r['n_eff_test']} | {r['p_adj']:.4f} | {b7['n_corr']} | {b14['n_corr']} | "
                     f"[{100*b14['rate_ci_lo']:.1f}%, {100*b14['rate_ci_hi']:.1f}%] | "
                     f"{'仍显著' if r['significant_after_correction'] else '不显著'} |")
    lines += ["", "## 3 读数", ""]
    for r in out:
        b14 = r["blocks"]["14"]
        verdict = ("敏感性判定仍显著：块自助下界仍高于 ρ，且有效样本量下 p_adj < .05；"
                   "这只是该点态构造下的结果。"
                   if r["significant_after_correction"] else
                   "敏感性判定不显著：p_adj ≥ .05 或块 CI 覆盖 ρ；不能据此断言周周期就是原因。")
        lines.append(f"- {r['site_id']} {r['convention']} 口径 {r['scheme']}/{r['fold']}/ρ={r['rho']:.2f}："
                     f"i.i.d. 半径 d+={b14['d_plus_iid']:.4f}，块自助 d+={b14['d_plus_block']:.4f}"
                     f"（{b14['d_plus_block']/b14['d_plus_iid']:.2f}×），"
                     f"同 n={r['n_iid']} 的块上界{'仍 ≤ ρ' if r['same_n_still_certifies_L14'] else '> ρ'}，"
                     f"n_corr(L=14)={b14['n_corr']}；留出率 {100*r['rate']:.1f}%，"
                     f"p {r['p_nominal']:.4f}→{r['p_adj']:.4f}（x_eff/n_eff {r['x_eff']}/{r['n_eff_test']}）。{verdict}")
    lines += ["", "## 4 产物与限制", "",
              "- 逐单元 JSON：%s（d+、n_corr、CI、p_adj；含全零反例）。" % os.path.relpath(out_json, ROOT),
              "- 限制：d+_block/Q(n) 是点态敏感性构造，不是有限样本覆盖保证；"
              "块自助只修正二阶结构（自相关），不处理非平稳（季节趋势）；"
              "n_corr 在 n ≥ n_obs 时仍应记为删失，不得当成通过；"
              "p_adj 是近似诊断，不是精确 p 值；本报告不提供同时覆盖保证。",
              ""]
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    open(out_md, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("cells", len(out), "survive", sum(1 for r in out if r["significant_after_correction"]),
          "zero_bound", zero_bound, "zero_true", round(zero_true, 4))


if __name__ == "__main__":
    main()
