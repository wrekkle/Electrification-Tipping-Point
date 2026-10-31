# -*- coding: utf-8 -*-
"""Lead 独立复核（扩展）：扫描第三/四轮全部可用完整 k 曲线，统计可行集合 K 的形状与边界。
不导入 A 模块；只读既有 JSON。输出 research/round6_20261031/lead/q3_scan.json"""
from __future__ import annotations
import glob, json, math, re
from pathlib import Path

ROOT = Path(r"C:\Projects\停车场充电桩优化方案")
OUT = ROOT / "research/round6_20261031/lead/q3_scan.json"
ALPHA, EPS = 0.05, 1e-12
CONSTRAINTS = ("capacity_only_unmet_rate", "ev_parking_failure_rate", "ice_parking_failure_rate")


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def st(value, den):
    if not num(den):
        return "missing"
    if float(den) <= 0.0:
        return "not_applicable_zero_demand"
    if value is None:
        return "missing"
    if not num(value) or not (-EPS <= float(value) <= 1.0 + EPS):
        return "illegal"
    return "valid"


def cells(row):
    out = []
    out.append(st(row.get("capacity_only_unmet_rate"), row.get("charge_requests")))
    sm = row.get("service_metrics") or {}
    rates, dens = sm.get("rates") or {}, sm.get("denominators") or {}
    out.append(st(rates.get("ev_parking_failure_rate"), dens.get("exogenous_ev_visits")))
    out.append(st(rates.get("ice_parking_failure_rate"), dens.get("exogenous_ice_visits")))
    return out


def ok(row):
    states = cells(row)
    for i, name in enumerate(CONSTRAINTS):
        s = states[i]
        if s == "valid":
            v = row.get(name) if i == 0 else (row.get("service_metrics") or {}).get("rates", {}).get(name)
            if float(v) > ALPHA + EPS:
                return False, states
        elif s == "not_applicable_zero_demand":
            continue
        else:
            return False, states
    return True, states


RULE_RE = re.compile(r"(?:^|_)([ABCD])(?:_|$)")
EXTRA = [(re.compile(r"pi0"), "A"), (re.compile(r"pi1"), "B"), (re.compile(r"pi2"), "D"), (re.compile(r"quota"), "C")]


def rule_of(path):
    name = Path(path).stem
    m = RULE_RE.search(name)
    if m:
        return m.group(1)
    for rx, r in EXTRA:
        if rx.search(name):
            return r
    return "?"


def scan(paths):
    out = {"files": [], "shape": {}, "gaps": [], "kmax_asym": []}
    for p in sorted(paths):
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        rows = doc.get("rows") or []
        if not rows or "k" not in rows[0]:
            continue
        rule = rule_of(p)
        groups = {}
        for row in rows:
            groups.setdefault((row.get("lot_id"), row.get("seed")), {})[int(row["k"])] = row
        rec = {"file": str(Path(p).relative_to(ROOT)), "rule": rule, "units": 0,
               "empty": 0, "intervals": 0, "gaps": 0, "maxk": 0, "min_kmax": None}
        for key, by_k in groups.items():
            ks = sorted(by_k)
            consecutive = all(b - a == 1 for a, b in zip(ks, ks[1:]))
            K = [k for k in ks if ok(by_k[k])[0]]
            kmax = max(ks)
            rec["units"] += 1
            rec["maxk"] = max(rec["maxk"], kmax)
            rec["min_kmax"] = kmax if rec["min_kmax"] is None else min(rec["min_kmax"], kmax)
            if not consecutive:
                rec["step_sampled"] = rec.get("step_sampled", 0) + 1
                if K and K != [k for k in ks if K[0] <= k <= K[-1]]:
                    rec["step_irregular"] = rec.get("step_irregular", 0) + 1
                continue
            if not K:
                rec["empty"] += 1
            elif K == list(range(K[0], K[-1] + 1)):
                rec["intervals"] += 1
            else:
                rec["gaps"] += 1
                if len(out["gaps"]) < 15:
                    out["gaps"].append({"file": rec["file"], "lot": key[0], "seed": key[1],
                                        "K": K, "kmax": kmax})
        out["files"].append(rec)
        s = out["shape"].setdefault(rule, {"files": 0, "units": 0, "empty": 0, "intervals": 0, "gaps": 0,
                                           "step_sampled": 0, "step_irregular": 0})
        s["files"] += 1
        for k in ("units", "empty", "intervals", "gaps", "step_sampled", "step_irregular"):
            s[k] += rec.get(k, 0)
    # 同 lot,seed 跨文件 kmax 不一致提示（A 扩展 vs B/C/D 40）
    return out


def main():
    r3 = [p for p in glob.glob(str(ROOT / "research/round3_20261031/results/*.json"))]
    r4 = [p for p in glob.glob(str(ROOT / "research/round4_20261031/results/*.json"))]
    r4 += [p for p in glob.glob(str(ROOT / "research/round4_20261031/results/fixedk/*.json"))]
    out = scan(r3 + r4)
    out["schema"] = "round6/lead_q3_scan/v1"
    out["alpha"] = ALPHA
    out["note"] = "只统计含 rows 与 k 的曲线文件；K 定义为三约束满足（N/A 跳过、missing/illegal 不满足）。kmax 不一致文件不合并推断。"
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"shape": out["shape"], "n_files": len(out["files"]),
                      "gaps": out["gaps"][:3]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
