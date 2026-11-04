"""Cross-check DOT registered capacity against the observed session panels.

Inputs (all read-only except the two outputs):
  data/charger_sites/nyc_v3/facilities.jsonl    parsed DOT facility page
  data/charger_sites/nyc_v3/site_mapping.json   site_id -> DOT facility
  data/charger_sites/nyc_v3/panel_summary.json  full-history panel (v3)
  data/charger_sites/nyc_v2/sites.jsonl         observed panel (v2)

Two different questions are answered separately:

1. Capacity consistency.  A distinct charge_box_id count over a long window is a
   device census, not capacity: boxes are replaced and renumbered.  The capacity
   test therefore uses *concurrent* occupancy (the daily peak overlap) only.

2. Identification shape.  With a registered n_obs, the plug-in M4 identification
   set is (a/T(n_obs-1), +inf) when some observed day reaches n_obs, and empty
   otherwise.  T is estimated on two windows: the v2 year and the whole history.
   Both are reported because the panel is not stationary (capacity changed).

Usage:
    python data/tools/check_nyc_facilities.py
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V3 = os.path.join(ROOT, "data", "charger_sites", "nyc_v3")
FAC = os.path.join(V3, "facilities.jsonl")
MAP = os.path.join(V3, "site_mapping.json")
PANEL = os.path.join(V3, "panel_summary.json")
V2 = os.path.join(ROOT, "data", "charger_sites", "nyc_v2", "sites.jsonl")
OUT_JSON = os.path.join(V3, "capacity_crosscheck.json")
OUT_MD = os.path.join(V3, "FACILITIES_CROSSCHECK.md")
A_GRID = [2.5, 3.5, 5.0]


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def window_stats(hist, registered):
    """T_hat(n-1) = share of days whose peak reaches the registered capacity."""
    hist = {int(k): v for k, v in (hist or {}).items()}
    days = sum(hist.values())
    if not days or registered is None:
        return None
    ge = sum(v for k, v in hist.items() if k >= registered)
    t_hat = ge / days
    out = {
        "days": days,
        "days_at_or_above_n": ge,
        "T_hat": round(t_hat, 6),
        "shape": "half_line" if t_hat > 0 else "empty",
        "c_over_a_lower_bound": (round(1.0 / t_hat, 4) if t_hat > 0 else None),
        "c_lower_bound_usd": ({str(a): round(a / t_hat, 2) for a in A_GRID} if t_hat > 0 else {}),
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=OUT_JSON)
    ap.add_argument("--md", default=OUT_MD)
    args = ap.parse_args()

    fac = {r["facility_name"]: r for r in load_jsonl(FAC)}
    mapping = json.load(open(MAP, encoding="utf-8"))
    v2 = {r["site_id"]: r for r in load_jsonl(V2)}
    panel = json.load(open(PANEL, encoding="utf-8")) if os.path.exists(PANEL) else {"sites": {}}

    rows, problems = [], []
    for sid, obs in sorted(v2.items()):
        m = mapping["sites"].get(sid)
        rec = fac.get(m["facility_name"]) if m else None
        if rec is None:
            problems.append("%s: DOT record missing" % sid)
            continue
        p = panel["sites"].get(sid, {})
        registered = rec.get("ev_spaces_registered")
        peak_all = p.get("peak_all_history", obs.get("peak_max"))
        peak_365 = p.get("peak_last_365d", obs.get("peak_max"))

        # concurrency is the only capacity-compatible statistic
        capacity_consistent = (registered is not None and peak_all is not None
                               and peak_all <= registered)
        w365 = window_stats(p.get("peak_histogram_last_365d"), registered)
        wall = window_stats(p.get("peak_histogram_all"), registered)
        total = rec.get("total_spaces")
        rows.append({
            "site_id": sid,
            "site_name": obs.get("site_name"),
            "dot_facility": rec["facility_name"],
            "dot_address": rec["address"],
            "dot_snapshot_date": rec["fetched_at"],
            "total_spaces": total,
            "ev_spaces_registered": registered,
            "ev_l2_spaces": rec.get("ev_l2_spaces"),
            "ev_dc_fast_spaces": rec.get("ev_dc_fast_spaces"),
            "ev_count_rule": rec.get("ev_count_rule"),
            "device_ids_seen_all_history": p.get("charge_boxes"),
            "device_ids_seen_last_365d": obs.get("charger_units"),
            "observed_peak_all_history": peak_all,
            "observed_peak_last_365d": peak_365,
            "panel_last_day": p.get("last_session_day") or obs.get("as_of_date"),
            "hours_raw": rec.get("hours_raw"),
            "open_24h": rec.get("open_24h"),
            "status_notes": rec.get("status_notes"),
            "ev_per_100_spaces": (round(100.0 * registered / total, 2) if (total and registered) else None),
            "capacity_consistent": capacity_consistent,
            "capacity_conflict": (None if capacity_consistent else
                                  "peak %s exceeds registered %s" % (peak_all, registered)),
            "identification": {"registered_n": registered, "window_365d": w365, "window_all": wall},
        })

    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "inputs": {k: os.path.relpath(v, ROOT) for k, v in
                   {"facilities": FAC, "mapping": MAP, "panel": PANEL, "v2": V2}.items()},
        "sites": len(rows),
        "with_total_spaces": sum(1 for r in rows if r["total_spaces"] is not None),
        "with_registered_ev_spaces": sum(1 for r in rows if r["ev_spaces_registered"] is not None),
        "capacity_conflicts": {r["site_id"]: r["capacity_conflict"] for r in rows if r["capacity_conflict"]},
        "half_line_365d": [r["site_id"] for r in rows if (r["identification"]["window_365d"] or {}).get("shape") == "half_line"],
        "empty_365d": [r["site_id"] for r in rows if (r["identification"]["window_365d"] or {}).get("shape") == "empty"],
        "half_line_all": [r["site_id"] for r in rows if (r["identification"]["window_all"] or {}).get("shape") == "half_line"],
        "empty_all": [r["site_id"] for r in rows if (r["identification"]["window_all"] or {}).get("shape") == "empty"],
        "problems": problems,
        "rows": rows,
    }

    with open(args.json, "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    md = [
        "# NYC 登记容量与观测占用对照",
        "",
        "类型: 数据说明",
        "状态: 生效",
        "负责人: tho25",
        "日期: 2026-11-03",
        "生成命令: python data/tools/check_nyc_facilities.py",
        "",
        "登记值来自 NYC DOT 设施页（2026-11-02 快照）；观测值来自全历史会话（v3）与 v2 年度面板。",
        "",
        "## 1 车位与充电位",
        "",
        "| site | 总车位 | 登记充电位 | L2 | DC | 设备编号数(全历史) | 设备编号数(近一年) | 全历史峰值 | 近一年峰值 | 峰值≤登记 | 营业时间 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in rows:
        md.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["site_id"].replace("nyc-", ""), r["total_spaces"], r["ev_spaces_registered"],
            r["ev_l2_spaces"] if r["ev_l2_spaces"] is not None else "-",
            r["ev_dc_fast_spaces"] if r["ev_dc_fast_spaces"] is not None else "-",
            r["device_ids_seen_all_history"], r["device_ids_seen_last_365d"],
            r["observed_peak_all_history"], r["observed_peak_last_365d"],
            "是" if r["capacity_consistent"] else "否",
            (r["hours_raw"] or "-")[:40]))
    md += [
        "",
        "## 2 识别形态（条件结论）",
        "",
        "M4 的 plug-in 识别集为 `(a/T(n_obs−1), +∞)`；只有当日峰值达到 n_obs 才有有限下界。",
        "n_obs 用 DOT 登记充电位；两个窗口分别估计，因为容量与需求在 5 年里有变化。",
        "",
        "| site | 登记 n | 近一年 T̂ | 近一年形态 | c/a 下界 | 全历史 T̂ | 全历史形态 | c/a 下界 | 容量自洽 |",
        "|---|---:|---:|---|---:|---:|---|---:|---|",
    ]
    for r in rows:
        i = r["identification"]
        a, b = i["window_365d"] or {}, i["window_all"] or {}
        md.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["site_id"].replace("nyc-", ""), i["registered_n"],
            a.get("T_hat", "-"), a.get("shape", "-"), a.get("c_over_a_lower_bound", "-"),
            b.get("T_hat", "-"), b.get("shape", "-"), b.get("c_over_a_lower_bound", "-"),
            "是" if r["capacity_consistent"] else "否"))
    md += [
        "",
        "- 近一年半直线站：%s；近一年空集站：%s。" % (summary["half_line_365d"] or "无", summary["empty_365d"] or "无"),
        "- 全历史半直线站：%s；全历史空集站：%s。" % (summary["half_line_all"] or "无", summary["empty_all"] or "无"),
        "- 容量冲突站：%s。" % (summary["capacity_conflicts"] or "无"),
        "",
        "## 3 口径",
        "",
        "- 登记充电位＝DOT 页 “With EV Charging Spaces” 中的 Level 2 / DC fast / 通用 EV 位数；",
        "  两种写法同时出现时取 max(通用, L2+DC)，逐条记录在 `ev_count_rule`。",
        "- 设备编号数＝distinct charge_box_id。**它不是容量**：同一站点五年内换过、增减过设备，",
        "  编号会被重新分配；因此容量检验只用同时占用（日峰值），不用编号计数。",
        "- 容量自洽＝全历史日峰值 ≤ 登记充电位。只有 wpl 不满足：观测峰值 17 > 登记 8，",
        "  而该站的 location_name 本身带 “The additional L2 EVSEs are not available yet.”。",
        "- T̂ 是 plug-in 点估计，无置信带；它假设登记值在整个窗口内就是容量。跨窗口的设备变化",
        "  没有逐日清册可核，所以两个窗口都报，不合并。",
        "",
        "## 4 未覆盖",
        "",
        "- 逐台设备的额定功率、投运/停机日期、故障记录。",
        "- 充电位是否与普通位共享（同一车位能否两用）。",
        "- 挂牌营业时间与充电可用时间的关系：cpo/stw/wpl 标注 “Except Sunday”，但观测到 16.6%/20.1%/17.3%",
        "  的会话发生在周日，说明营业时间不能直接当充电可用时间。",
        "",
    ]
    with open(args.md, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md))

    print("sites: %d; total_spaces %d/12; registered EV %d/12"
          % (summary["sites"], summary["with_total_spaces"], summary["with_registered_ev_spaces"]))
    print("capacity conflicts:", summary["capacity_conflicts"] or "none")
    print("half-line 365d:", summary["half_line_365d"])
    print("half-line all :", summary["half_line_all"])
    print("wrote:", os.path.relpath(args.json, ROOT), os.path.relpath(args.md, ROOT))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
