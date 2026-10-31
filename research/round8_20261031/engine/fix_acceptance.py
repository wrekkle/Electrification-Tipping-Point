"""R8-D 验收修复：只重跑受影响家族（E2 固定流、M2 方向/说明、main22 E6 22kW），并写 CHANGELOG。

- 7kW: experiments/ 只重写 E2、M（E2 固定流设计；M2 方向标签）；其它文件不动。
- main22: experiments_main22/ 重写 E2、M（含 constraint_thresholds 集成）、E6（22 kW）；
  M1/M3 仍为 missing_data（诚实）。
"""
from __future__ import annotations
import csv, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENGINE = Path(__file__).resolve().parent
for p in (str(ROOT), str(ENGINE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import runner
from apps.parking_lab.workbench import publicdata

CONTRACT = ROOT / "research/round8_20261031/data/processed/public_parking_events.json"
SEED = 20261031
REGIMES = (
    ("7kW", ROOT / "research/round8_20261031/experiments", None,
     "scenario_charging_layer_not_observed"),
    ("main22", ROOT / "research/round8_20261031/experiments_main22",
     {"connector_kw": 22.0, "feeder_kw_per_connector": 22.0},
     "scenario_charging_layer_main22_22kW_not_observed"),
)
NUMERIC = ("energy_service_rate_incl_rejected", "num_ice_parking_failures",
           "den_exogenous_ice_visits", "k", "k_min_feasible")


def read_csv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def to_num(row):
    out = dict(row)
    for key in NUMERIC:
        if key in out and out[key] not in ("", None):
            try:
                out[key] = float(out[key])
            except (TypeError, ValueError):
                out[key] = None
    return out


def load_old_m(outdir):
    payload = json.loads((outdir / "M" / "m_summaries.json").read_text(encoding="utf-8"))
    return payload["comparisons"] if isinstance(payload, dict) else payload


def build_m(outdir):
    old = load_old_m(outdir)
    old_m1 = next((row for row in old if row.get("comparison") == "M1"), {})
    old_m3 = next((row for row in old if row.get("comparison") == "M3"), {})
    pairs_total = int(old_m1.get("pairs_total") or old_m1.get("n_pairs") or 0)
    m1_data = [{"stream_id": "stream_%d" % i, "k_A": None, "k_B": None,
                "delta_k": None, "reason": old_m1.get("reason")} for i in range(pairs_total)]
    e4 = [to_num(row) for row in read_csv(outdir / "E4" / "test_E4.csv")]
    m3 = (json.loads((outdir / "run_meta.json").read_text(encoding="utf-8")).get("m3_pairs")
          or [])
    return runner.m_summaries(m1_pairs_data=m1_data, e4_rows_data=e4, m3_pairs_data=m3)


def write_manifest(outdir, family, files, notes, extra=None):
    path = outdir / family / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    manifest.update({"family": family, "status": "ok", "mode": "real_data",
                     "dataset_id": manifest.get("dataset_id"),
                     "seed": SEED, "outputs": [{"path": Path(item).name,
                                                "sha256": runner.sha256_file(item)}
                                               for item in files]})
    manifest["notes"] = list(manifest.get("notes") or [])[:0] + notes
    if extra:
        manifest.update(extra)
    runner.write_json(path, manifest)
    return manifest


def main():
    report = publicdata.load_contract(CONTRACT, strict=False)["normalised"]
    blocks = publicdata.site_day_blocks(report)
    changes = []
    for name, outdir, force, label in REGIMES:
        runner.SCENARIO_FORCE.clear()
        runner.set_scenario_label(label)
        if force:
            runner.set_scenario_force(**force)
        split = runner.build_dataset(blocks, seed=SEED)
        meta = json.loads((outdir / "run_meta.json").read_text(encoding="utf-8"))
        # ---- E2：固定流设计 ----
        e2_rows, design = runner.e2_fixed_rows(split["test"], seed=SEED)
        e2_files = [runner.write_csv(outdir / "E2" / "curve_E2.csv", e2_rows)]
        summary_rows = runner.e2_summary(e2_rows)
        e2_files += [runner.write_csv(outdir / "E2" / "curve_E2_summary.csv", summary_rows)]
        runner.write_json(outdir / "E2" / "curve_E2_summary.json",
                          {"design": design, "n_boot": 1000, "seed": SEED,
                           "unit": "independent stream (site-day)",
                           "metrics": ["service_capacity_unmet_rate",
                                       "service_ev_parking_failure_rate",
                                       "service_ice_parking_failure_rate",
                                       "charging_access_rate", "energy_service_rate"],
                           "note": "固定流设计：每个 k 的 n_streams 相同；bootstrap 单位=独立场站-日；"
                                   "描述性曲线，不作确认性比较"})
        write_manifest(outdir, "E2", e2_files,
                       ["固定流设计（R8-D F2）：charging_bays>=8 站点抽样 24 条流，k=0..8 全覆盖；"
                        "curve_E2.csv 含 n_streams_at_k 列，n_streams 逐 k 恒定",
                        "k 全整数枚举（无单调性证明不二分）；曲线含 A/D 规则",
                        "bootstrap 单位=独立场站-日"],
                       extra={"fixed_stream_design": design})
        meta["families"]["E2"] = {"files": [str(p) for p in e2_files],
                                  "rows": len(e2_rows), "design": design}
        meta["budget"]["E2"] = design["budget"]
        changes.append({"family": "E2", "fix": "R8-D F2",
                        "old": "n_streams 随 k 漂移 24→22→20→11→10→5→2；非固定配对样本",
                        "new": "固定流设计：%d 条流（%s），k=0..8，每 k n_streams=%d；"
                               "curve_E2.csv 新增 n_streams_at_k"
                               % (design["n_streams"], ",".join(design["eligible_sites"]),
                                  design["n_streams"]),
                        "reason": "高 k 点曾只由大场站构成，曲线形状可能受组成驱动"})
        # ---- M：M1/M3 保留（缺数据），M2 用新方向与说明重算 ----
        m_rows = build_m(outdir)
        m_dir = outdir / "M"
        csv_files = [runner.write_csv(m_dir / "m_summaries.csv", m_rows)]
        if name == "main22":
            thresholds = json.loads((outdir / "constraint_thresholds.json")
                                    .read_text(encoding="utf-8"))
            payload = {"comparisons": m_rows, "constraint_thresholds": thresholds}
            json_files = [runner.write_json(m_dir / "m_summaries.json", payload)]
            notes = ["M1/M3 仍为 missing_data（三约束标准在 0..charging_bays 内可达性问题），如实保留",
                     "M2 方向：baseline − A（负值=A 更好）；B1/B2 恒等原因已写入 note",
                     "constraint_thresholds.csv/json 已集成到本文件 constraint_thresholds 字段",
                     "bootstrap 单位=场站-日；不显著不等于无效"]
        else:
            json_files = [runner.write_json(m_dir / "m_summaries.json",
                                            {"comparisons": m_rows})]
            notes = ["M2 方向：baseline − A（负值=A 更好）；B1/B2 恒等原因已写入 note",
                     "M1/M3 missing_data 如实保留",
                     "bootstrap 单位=场站-日；不显著不等于无效"]
        write_manifest(outdir, "M", csv_files + json_files, notes,
                       extra={"b1_b2_note": next((row.get("note") for row in m_rows
                                                  if row.get("pair") == "B1_QUOTA - A"), None)})
        meta["m2"] = [row for row in m_rows if row.get("comparison") == "M2"]
        changes.append({"family": "M", "fix": "R8-D F1",
                        "old": "pair 标签写作 'A vs B0_FCFS'，实际数值是 baseline − A；B1=B2 无解释",
                        "new": "pair 改为 'B0_FCFS - A' 等，新增 direction 字段与 note；"
                               "B1/B2 恒等原因写入 note（ICE 失败 0/4643，借位门控未改变决策）",
                        "reason": "方向标签反转会导致正文解释相反"})
        # ---- main22 E6：22 kW 重跑 ----
        if name == "main22":
            prereg = meta.get("preregistered_k")
            e6_test, _ = runner.sample_blocks(split["test"], runner.BUDGET_CAPS["E6_streams"],
                                              SEED, salt=4)
            e6_rows = runner.e6_rows(e6_test, seed=SEED, k_values=[prereg],
                                     power_values=(22.0,), feeder_shares=(1.0,))
            for row in e6_rows:
                row["family"] = "E6"
                row["k_source"] = "preregistered_k"
                row["e6_mode"] = "regime_forced_power"
            e6_files = [runner.write_csv(outdir / "E6" / "energy_E6.csv", e6_rows)]
            write_manifest(outdir, "E6", e6_files,
                           ["22 kW 情景重跑（R8-D F3）：connector_kw=22, feeder_share=1.0 → feeder=k*22",
                            "能量服务条目含分子/分母/适用条件；被拒请求计入缺口口径",
                            "不假设离场后免费补能；censored/initial 分列"],
                           extra={"e6_mode": "regime_forced_power", "power_values": [22.0],
                                  "feeder_shares": [1.0]})
            meta["families"]["E6"] = {"files": [str(p) for p in e6_files],
                                      "rows": len(e6_rows), "mode": "regime_forced_power",
                                      "power_values": [22.0], "feeder_shares": [1.0]}
            changes.append({"family": "E6", "fix": "R8-D F3",
                            "old": "main22 的 E6 与 7kW 完全相同（connector_kw 仍 7/11），元数据却称 22kW",
                            "new": "E6 在 22 kW、feeder_share=1.0（feeder=k*22）下重跑；"
                                   "connector_kw=22, feeder_share=1.0；manifest 更新",
                            "reason": "避免元数据与内容不一致"})
        meta.setdefault("changelog", [])
        meta["changelog"] = meta["changelog"] + changes
        runner.write_json(outdir / "run_meta.json", meta)
        print(json.dumps({"regime": name, "E2_design": design,
                          "m2": [row.get("pair") for row in m_rows
                                 if row.get("comparison") == "M2"]}, ensure_ascii=True))
        changes = []  # 每个 regime 独立记录其 changelog
    print("DONE")


if __name__ == "__main__":
    main()
