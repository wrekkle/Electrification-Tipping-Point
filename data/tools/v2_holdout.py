#!/usr/bin/env python3
"""V2 out-of-sample calibration, full panel (P1).

Design
- 12 sites x 2 W_d conventions x 2 schemes x 3 rho.
  Convention D (primary): calendar-day peak, m = observed days (>=1 session);
  convention S adds zero-filled span days as a sensitivity; A is the arrival-day
  peak sensitivity.
  Convention A (sensitivity): arrival-day peak, event days only.
- Schemes: chronological half (first half train / second half test) and K=3
  contiguous blocks, each block tested once against the other two.
- Certificate (Prop.10, one-sided Massart) is issued on the training days of the
  fold: d+ = sqrt(log(1/alpha)/(2*m_train)) and n = min{n : min(1,T_hat(n)+d+) <= rho}.
- Held-out test: overload rate = share of held-out days with W_d > n; the
  one-sided binomial p-value P(X>=x | Bin(m_test, rho)) is descriptive.
- n >= n_obs is CENSORED, not a pass: W_d <= n_obs holds by construction (M4), so
  the held-out rate is 0 for structural reasons and carries no evidence.
- no_cert: no n certifies on the training days.

Outputs
- data/demand/v2_holdout.json (row level)
- docs/reports/2026-11-02-V2-样本外校准.md

Not a proof of coverage: cells share sites and days, so the p-values are
descriptive and the joint 95% statement is across cells, not across the study.
"""
import json, math, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALPHA = 0.05
RHOS = (0.10, 0.15, 0.20)
KFOLD = 3
CONVENTIONS = {"D": "peak_overlap_values", "A": "peak_overlap_values_arrival_day",
               "S": "peak_overlap_values_span"}
CONV_NOTE = {
    "D": "calendar-day peak; m = observed days (days with >=1 session, no zero fill; primary)",
    "A": "arrival-day peak, observed days only (sensitivity)",
    "S": "calendar-day peak over span days, zero-session days filled as W=0 (sensitivity)",
}
SITES = os.path.join(ROOT, "data", "charger_sites", "nyc_v1", "sites.jsonl")
DEMAND = os.path.join(ROOT, "data", "demand")
OUT_MD = os.path.join(ROOT, "docs", "reports", "2026-11-02-V2-样本外校准.md")
OUT_JSON = os.path.join(ROOT, "data", "demand", "v2_holdout.json")


def radius(m):
    return math.sqrt(math.log(1.0 / ALPHA) / (2 * m))


def tail(vals, n):
    return sum(1 for w in vals if w > n) / len(vals)


def certify(vals, rho):
    m = len(vals)
    d = radius(m)
    hi = max(vals) if vals else 0
    for n in range(0, hi + 1):
        if min(1.0, tail(vals, n) + d) <= rho + 1e-12:
            return n, d
    return None, d


def binom_sf(k, n, p):
    """P(X >= k) for X ~ Bin(n, p); k=0 -> 1."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    s = 0.0
    for i in range(k, n + 1):
        s += math.comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i))
    return min(1.0, s)


def fold_rows(sid, conv, pv, n_obs, scheme, folds):
    rows = []
    for label, train, test in folds:
        if len(train) < 2 or not test:
            continue
        tr_vals = [pv[d] for d in train]
        te_vals = [pv[d] for d in test]
        for rho in RHOS:
            n, d = certify(tr_vals, rho)
            row = {"site_id": sid, "convention": conv, "scheme": scheme, "fold": label,
                   "rho": rho, "n_obs": n_obs, "train_m": len(train), "test_m": len(test),
                   "d_plus": round(d, 6), "n": n, "x": None, "rate": None,
                   "p_value": None, "status": None}
            if n is None:
                row["status"] = "no_cert"
            elif n >= n_obs:
                row["status"] = "censored"
                row["x"] = 0
                row["rate"] = 0.0
            else:
                x = sum(1 for w in te_vals if w > n)
                row["status"] = "tested"
                row["x"] = x
                row["rate"] = x / len(te_vals)
                row["p_value"] = binom_sf(x, len(te_vals), rho)
            rows.append(row)
    return rows


def summarize(rows, conv, scheme):
    out = []
    for rho in RHOS:
        rs = [r for r in rows if r["convention"] == conv and r["scheme"] == scheme and r["rho"] == rho]
        tested = [r for r in rs if r["status"] == "tested"]
        viol = [r for r in tested if r["rate"] > rho + 1e-12]
        sig = [r for r in tested if r["p_value"] is not None and r["p_value"] < 0.05]
        x_tot = sum(r["x"] for r in tested)
        m_tot = sum(r["test_m"] for r in tested)
        out.append({
            "rho": rho, "cells": len(rs),
            "no_cert": sum(1 for r in rs if r["status"] == "no_cert"),
            "censored": sum(1 for r in rs if r["status"] == "censored"),
            "tested": len(tested), "viol": len(viol), "sig": len(sig),
            "pooled_x": x_tot, "pooled_m": m_tot,
            "pooled_rate": (x_tot / m_tot) if m_tot else None,
            "pass_naive": (len(tested) - len(viol)) / len(tested) if tested else None,
        })
    return out


def pct(x):
    return "-" if x is None else f"{100.0 * x:.1f}%"


def folds_for(days):
    out = []
    m = len(days)
    if m >= 4:
        cut = m // 2
        out.append(("half", days[:cut], days[cut:]))
    if m >= KFOLD * 2:
        base, rem = divmod(m, KFOLD)
        start = 0
        kf = []
        for f in range(KFOLD):
            size = base + (1 if f < rem else 0)
            test = days[start:start + size]
            start += size
            train = [d for d in days if d not in set(test)]
            kf.append((f"fold{f}", train, test))
        out += kf
    return out


def main(sites_path=None, demand_dir=None, out_json=None, out_md=None, version="v1"):
    sites_path = sites_path or SITES
    demand_dir = demand_dir or DEMAND
    out_json = out_json or OUT_JSON
    out_md = out_md or OUT_MD
    sites = [json.loads(l) for l in open(sites_path, encoding="utf-8") if l.strip()]
    rows, site_meta = [], {}
    for s in sites:
        sid = s["site_id"]
        qp = os.path.join(demand_dir, sid, "quality.json")
        if not os.path.exists(qp):
            continue
        q = json.load(open(qp, encoding="utf-8"))
        for conv, key in CONVENTIONS.items():
            pv = {k: int(v) for k, v in q.get(key, {}).items()}
            if not pv:
                continue
            days = sorted(pv)
            site_meta.setdefault(sid, {})["m_" + conv] = len(days)
            site_meta[sid]["n_obs"] = s["service_points"]
            folds = folds_for(days)
            half = [f for f in folds if f[0] == "half"]
            kf = [f for f in folds if f[0] != "half"]
            if half:
                rows += fold_rows(sid, conv, pv, s["service_points"], "half", half)
            if kf:
                rows += fold_rows(sid, conv, pv, s["service_points"], "kfold", kf)

    summary = {c: {sc: summarize(rows, c, sc) for sc in ("kfold", "half")} for c in CONVENTIONS}
    json.dump({"alpha": ALPHA, "rhos": RHOS, "kfold": KFOLD, "version": version,
               "conventions": {c: CONV_NOTE[c] for c in CONVENTIONS},
               "rows": rows, "summary": summary, "site_meta": site_meta},
              open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def agg_table(conv, scheme, title):
        lines = [f"### {title}", "",
                 "| rho | cells | no_cert | censored | tested | rate>rho | p<0.05 | pooled test rate | pass (naive) |",
                 "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for a in summary[conv][scheme]:
            lines.append(f"| {a['rho']:.2f} | {a['cells']} | {a['no_cert']} | {a['censored']} | "
                         f"{a['tested']} | {a['viol']} | {a['sig']} | {pct(a['pooled_rate'])} | "
                         f"{pct(a['pass_naive'])} |")
        return lines

    def reliability_table(conv, scheme):
        lines = ["| rho (nominal) | tested cells | pooled overload rate | observed/nominal | p<0.05 | 95% flag |",
                 "|---:|---:|---:|---:|---:|---|"]
        for a in summary[conv][scheme]:
            ratio = (a["pooled_rate"] / a["rho"]) if a["pooled_rate"] is not None else None
            flag = "OK" if (a["pooled_rate"] is not None and a["pooled_rate"] <= a["rho"]) else "OVER"
            lines.append(f"| {a['rho']:.2f} | {a['tested']} | {pct(a['pooled_rate'])} | "
                         f"{'-' if ratio is None else format(ratio, '.3f')} | {a['sig']} | {flag} |")
        return lines

    tested = [r for r in rows if r["status"] == "tested"]
    viol = [r for r in tested if r["rate"] > r["rho"] + 1e-12]
    sig = [r for r in tested if r["p_value"] is not None and r["p_value"] < 0.05]
    cens = [r for r in rows if r["status"] == "censored"]
    noc = [r for r in rows if r["status"] == "no_cert"]
    sig_d = [r for r in sig if r["convention"] == "D"]
    sig_a = [r for r in sig if r["convention"] == "A"]
    kfD = summary["D"]["kfold"]
    kfA = summary["A"]["kfold"]
    d_tested = sum(a["tested"] for a in kfD)
    d_viol = sum(a["viol"] for a in kfD)
    a_tested = sum(a["tested"] for a in kfA)
    a_viol = sum(a["viol"] for a in kfA)

    lines = [
        "# V2 样本外校准（完整面板，%s；D 主口径 + A/S 敏感性）" % version,
        "",
        "类型: 研究报告",
        "状态: 生效",
        "负责人: tho25",
        "日期: 2026-11-03",
        "生成命令: 由 data/tools/rebuild_nyc_v2.py 调用 v2_holdout.main（version=%s）" % version,
        "",
        "## 0 一句话",
        "",
        f"设计 = 12 站 × {len(CONVENTIONS)} 口径 ×（前后半 1 + 连续 3 折）× 3 ρ = {len(CONVENTIONS) * 4 * len(RHOS) * 12} 个格子，"
        f"实际产出 {len(rows)} 行（hpo 只有 1 天，不生成任何折）："
        f"{len(cens)} 个删失（n ≥ n_obs，M4 使其无检验力，不算通过）、{len(noc)} 个未发证、{len(tested)} 个可检验；"
        f"可检验单元中 {len(viol)} 个实测过载率 > ρ，{len(sig)} 个单侧二项 p<0.05"
        f"（D 口径 {len(sig_d)} 个，A 口径 {len(sig_a)} 个，S 口径 {len([r for r in sig if r['convention']=='S'])} 个；"
        "qbo 的 D/S 峰值序列相同，显著单元重复计数）。",
        "",
        "**本报告取代 2026-11-02 的 V2 完整面板（264 行：84 删失/59 未发证/121 可检验/10 违例/4 显著，D 3 + A 1）"
        "与更早的 pilot（132 单元，A 口径）。**",
        "旧数字保留在 2026-11-02 的两份报告与[复核报告](2026-11-02-数学证明方案复核与修复.md) §5 作为历史记录；"
        "旧口径是 m=span 与 A/D 对照，本报告改为 m_obs 主口径 + D/A/S，不可混用。",
        "",
        "## 1 口径",
        "",
        "- W_d 口径：D（主口径）= 日历日峰值，跨日会话裁剪进两天，m = 有会话的观测日（不把无会话日当 0 填充）；"
        "S（敏感性）= 同一峰值序列但把跨度内无会话日填 0；A（敏感性）= 到达日峰值，只含观测日。",
        "- 证书：Prop.10 单侧 Massart，d+ = sqrt(ln(1/α)/(2 m_train))，α=.05；取最小 n 使 min(1, p̂_n + d+) ≤ ρ。",
        "- 检验：留出天中 W_d > n 的比例；单侧二项 p 值 P(X≥x | Bin(m_test, ρ)) 只是近似诊断（天不独立，且同一站点折间重叠），不作覆盖保证。",
        "- 删失：n ≥ n_obs 时 W_d ≤ n_obs 恒成立，留出过载率必为 0；这是 M4 的结构性零，不是通过。",
        "- 切分：half = 前半训练/后半检验；kfold = 3 个连续块，轮流留出一块。连续块是对时间依赖的压力测试。",
        "- 站点：12 站全报（不做 cherry-picking）；hpo 只有 1 天，wpl 为 24 个观测日/38 天跨度，"
        "格子会大量 no_cert/删失。",
        "",
        "## 2 汇总（主结果：3 折连续块）",
        "",
    ]
    lines += agg_table("D", "kfold", "D 口径（主口径）")
    lines += [""] + agg_table("A", "kfold", "A 口径（敏感性）")
    lines += [""] + agg_table("S", "kfold", "S 口径（零填充敏感性）")
    lines += ["", "### 前后半（plan 的原始口径）", ""]
    lines += agg_table("D", "half", "D 口径（主口径）")
    lines += [""] + agg_table("A", "half", "A 口径（敏感性）")

    lines += ["", "## 3 可靠性表（实测过载率 vs 名义 ρ）", "",
              "池化 = 同口径同 ρ 下所有可检验单元的 x 之和 / 留出天数之和；OVER 表示池化过载率超过名义 ρ。",
              "", "### D 口径（默认），3 折", ""]
    lines += reliability_table("D", "kfold")
    lines += ["", "### A 口径，3 折", ""]
    lines += reliability_table("A", "kfold")

    lines += ["", "## 4 逐站（3 折，D 口径）", "",
              "| site | m(D) | m(A) | m(S) | n_obs | tested | censored | no_cert | rate>rho | p<0.05 | max test rate |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in sites:
        sid = s["site_id"]
        meta = site_meta.get(sid, {})
        rs = [r for r in rows if r["site_id"] == sid and r["scheme"] == "kfold" and r["convention"] == "D"]
        t = [r for r in rs if r["status"] == "tested"]
        lines.append(f"| {sid} | {meta.get('m_D', '-')} | {meta.get('m_A', '-')} | {meta.get('m_S', '-')} | {s['service_points']} | "
                     f"{len(t)} | {sum(1 for r in rs if r['status']=='censored')} | "
                     f"{sum(1 for r in rs if r['status']=='no_cert')} | "
                     f"{sum(1 for r in t if r['rate']>r['rho']+1e-12)} | "
                     f"{sum(1 for r in t if r['p_value'] is not None and r['p_value']<0.05)} | "
                     f"{pct(max((r['rate'] for r in t), default=None))} |")
    lines += ["", "## 5 违例与显著单元明细（全部口径）", "",
              "| site | conv | scheme | fold | rho | n | n_obs | test days | overloads | rate | p |",
              "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in sorted([x for x in tested if x["rate"] > x["rho"] + 1e-12],
                    key=lambda z: (z["convention"], z["site_id"], z["rho"])):
        lines.append(f"| {r['site_id']} | {r['convention']} | {r['scheme']} | {r['fold']} | {r['rho']:.2f} | "
                     f"{r['n']} | {r['n_obs']} | {r['test_m']} | {r['x']} | {pct(r['rate'])} | "
                     f"{format(r['p_value'], '.4f')} |")
    lines += ["", "### p<0.05 但未超过 ρ 的单元（方向性告警）", "",
              "| site | conv | scheme | fold | rho | rate | p |", "|---|---|---|---|---:|---:|---:|"]
    odd = [r for r in sig if r["rate"] <= r["rho"] + 1e-12]
    if odd:
        for r in odd:
            lines.append(f"| {r['site_id']} | {r['convention']} | {r['scheme']} | {r['fold']} | "
                         f"{r['rho']:.2f} | {pct(r['rate'])} | {format(r['p_value'], '.4f')} |")
    else:
        lines.append("| - | - | - | - | - | - | - |")

    d_sig_desc = "；".join(f"{r['site_id']}/{r['scheme']}/{r['fold']}/ρ={r['rho']:.2f} "
                          f"（{r['x']}/{r['test_m']}={pct(r['rate'])}，p={r['p_value']:.4f}）" for r in sig_d)
    lines += ["", "## 6 读数（描述性）", "",
              f"- 主结果（D 口径、3 折）：{d_tested} 个可检验单元中 {d_viol} 个过载率 > ρ；"
              f"A 口径同设计 {a_tested} 个可检验单元中 {a_viol} 个。",
              f"- 删失合计 {len(cens)}/{len(rows)}（D 口径 {sum(1 for r in cens if r['convention']=='D')}，"
              f"A 口径 {sum(1 for r in cens if r['convention']=='A')}）：这些单元即使过载率 0 也不提供证据，"
              "报告必须与通过率分开列。",
              f"- D 口径有 {len(sig_d)} 个 p<0.05 单元" + (f"：{d_sig_desc}。" if sig_d else "：无。") +
              " p<0.05 的数量本身不能证明独立性成立或失效：在 121 个近似独立的检验下，"
              "α=.05 的期望假阳性约 6.05，少量显著与“少于期望”都不构成方向性结论。",
              "- P4 的块自助/有效样本量只作点态敏感性（见 data/tools/p4_dependence.py），"
              "不是全阈值同时覆盖，也不修复全零边界；本报告不据此断言周周期解释了偏差。",
              "- 这里的 p 值是近似诊断：同一站点的折之间有重叠，跨站不同源，不能当成一项独立检验的族。",
              "",
              "## 7 产物",
              "",
              f"- 行级结果：`{os.path.relpath(out_json, ROOT)}`（{len(rows)} 行，含 convention 字段）。",
              "- 复跑：`python data/tools/rebuild_nyc_v2.py`（version=%s）；独立 v1 路径仍可用旧入口。" % version,
              ""]
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    open(out_md, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("rows", len(rows), "tested", len(tested), "viol", len(viol), "sig", len(sig),
          "censored", len(cens), "no_cert", len(noc), "sig_D", len(sig_d), "sig_A", len(sig_a))
    for conv in CONVENTIONS:
        for scheme in ("kfold", "half"):
            print(conv, scheme, [(a["rho"], a["tested"], a["viol"], a["sig"]) for a in summary[conv][scheme]])
    for r in sig:
        print("SIG", r["site_id"], r["convention"], r["scheme"], r["fold"], r["rho"], r["n"], r["x"],
              r["test_m"], round(r["rate"], 4), round(r["p_value"], 4))


if __name__ == "__main__":
    main()
