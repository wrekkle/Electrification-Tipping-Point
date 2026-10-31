# -*- coding: utf-8 -*-
"""Emit calibration_report.md from fitted parameters and verification output."""
import io
import json
import math
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
P = json.loads((HERE / "fitted_parameters.json").read_text(encoding="utf-8"))
V = json.loads((HERE / "outputs" / "verify_report.json").read_text(encoding="utf-8"))
tr = P["traffic_fit"]["train"]
ch = P["charging"]
ev = P["ev"]
en = P["energy"]
val = P["validation"]
pool = V["pooled"]
fit = tr["fit_quality"]
dwell = tr["dwell"]
cons = {r["lot_id"]: r for r in P["consistency"]["rows"]}
lots = P["per_lot"]
split = P["split"]
BT = chr(96)

def pct(x):
    return "n/a" if x is None else "%.1f%%" % (100.0 * x)

rows = []
for e in lots:
    c = cons.get(e["lot_id"], {})
    rows.append("| %s | %s | %d | %s | %.2f | %.2f | %.0f | %s | %d | %s |" % (
        e["lot_id"], e["fit_split"], int(e["n_spaces"]),
        "" if c.get("status") == "ok" else "UNUSABLE",
        e["mean_occupancy_vehicles"], e["lambda_bar_veh_per_hour"],
        c.get("mean_dwell_little_min") or 0.0, pct(c.get("relative_error")),
        e["n_charge_sessions_observed"], e["charge_session_rate_source"]))
table = "\n".join(rows)

lot_rates = []
for e in lots:
    lot_rates.append("- %s: sessions=%d mean=%s rate/h=%.2f product=%.4f" % (
        e["lot_id"], e["n_charge_sessions_observed"],
        ("%.1f" % e["charge_duration_dist"]["mean_min"]) if e["charge_duration_dist"] else "n/a",
        e["charge_session_rate_mean_hour"] or 0.0,
        (e["charge_session_rate_mean_hour"] or 0.0) / e["lambda_bar_veh_per_hour"]
        if e["lambda_bar_veh_per_hour"] else 0.0))
lot_rates_txt = "\n".join(lot_rates)

q30 = ev["q_need_by_p_ev"].get("0.30")
if q30 is None and ev.get("product_required_mean"):
    q30 = ev["product_required_mean"] / 0.30
sys.path.insert(0, str(HERE.parents[1]))
from apps.parking_lab.workbench import traffic_gen as _tg
_p = _tg.load_params(HERE / "fitted_parameters.json")
_arr, _m = _tg.generate_for_lot(_p, "TPE0151", 1)
_grid = [0.0] * 288
for _a in _arr:
    _s = int(_a.time_min // 5)
    _e = int(math.ceil((_a.time_min + _a.dwell_min) / 5))
    for _k in range(max(0, _s), min(288, _e)):
        _grid[_k] += 1.0
_obs151 = next(e["mean_occupancy_vehicles"] for e in _p["per_lot"] if e["lot_id"] == "TPE0151")
warm_txt = "暖启动 %d 辆、t=0 占用 %d、24h 平均占用 %.1f、实测 %.2f" % (
    _m["initial_occupancy_n"], int(round(_grid[0])), sum(_grid) / len(_grid), _obs151)
text = f"""# 车流生成器校准报告（阶段三，2026-10-31）

类型: 研究报告
状态: 生效
负责人: traffic-gen
日期: 2026-10-31
数据窗口: {P["bins"].get("window_local_start")} – {P["bins"].get("window_local_end")}（本机时区 UTC+08:00）
校准脚本: {BT}calibrate.py{BT}（重跑: {BT}python research/traffic_generation_20261031/calibrate.py{BT}）
生成器: {BT}apps/parking_lab/workbench/traffic_gen.py{BT}（纯标准库，{P["generator_version"]}）

本报告只覆盖自己名下产物：{BT}research/traffic_generation_20261031/{BT}、{BT}apps/parking_lab/workbench/traffic_gen.py{BT}、{BT}apps/parking_lab/workbench/tests/test_traffic_gen.py{BT}、{BT}apps/parking_lab/workbench/__main__.py{BT}（仅新增 traffic 子命令）。

## 1 M07 §5.1 观测 / 拟合 / 假设核对

本地 PDF 文本抽取（pymupdf，文本见 {BT}_scratch/M07.txt{BT}）：§5.1「Demand and supply」位于印刷页 15–16 / PDF 页 15–16（M07.txt 第 1249 行起）；Table 1「Parameters of park and charge demand distribution」位于印刷页 14 / PDF 页 14（第 1185–1206 行）。与 Lead 独立核对一致。

**作者观测（不可下载、未公开）**
- 杭州 1400+ 个停车场、3000 万条带到达/离场时间戳记录（§5.1，PDF p.15）。
- 充电数据来自杭州**一家私人运营商** 4 万条快充记录（PDF p.16）。非官方数据，不能当作可下载的公开数据集。

**作者拟合（方法可迁移，具体数值不可照搬到台北）**
- 停车到达/离场时间分布 Fig.5(a)；GMM（Rasmussen 1999）拟合到达，K-means 按到达小时把停车时长分 4 类（Fig.5(c)）。
- Table 1：停车到达 N1(μ=16.38h,σ=3.02,η=0.43)、N2(9.46,2.78,0.56)；停车时长 N_short(91.22,73.27)、N_medium(427.0,99.47)、N_long(743.14,120.55)、N_vlong(1265.3,126.6) 分钟。
- 充电到达 N1(3.50,2.56,0.22)、N2(19.53,2.42,0.38)、N3(11.59,2.13,0.40)；快充时长 N_fast(52.85,37.76) 分钟、慢充 U(120,300) 分钟。
- Fig.5(c) 的四类时长占比只存在于图内，文本未给数值 → **UNVERIFIED: 需图形数字化**，本项目未使用。

**作者情景假设（不是数据）**
- 慢充只占公共充电需求 15%–20%（Table 1 末列：t≤9 时 0.15:0.85，t≤16 时 0.20:0.80，其余 0.15:0.85）。
- 数值实验 4 个停车场、停车位数 = 充电车位数、charging ratio = 1、停车:充电需求 1:1（§5 开头，印刷页 15）。
- 电价/服务费 Table 3；停车时长上限 β=450 min；δ=90 min；ρmax=0.1 推出 15 min buffer；权重 α1=α2=α3=1；步行系数 5、冲突单价 5；C_res=1 RMB/user、C_park=1.5 RMB/15min、C_park^max=36 RMB；Pm∈{{60,7}} kWh/h。

**可迁移到本项目**：真实停车数据 → 分时到达 + 时长分布 → 按时段分组；停车与充电数据分开拟合；用离场/到达时间戳拟合时长。
**不可照搬**：停车:充电需求比例与 charging ratio=1；快慢充 15/85、20/80 分配；杭州电价/服务费/冲突罚价/停车费；私人运营商 4 万条快充记录的任何具体数值；Table 1 的停车时长四类均值（杭州通勤/月租结构与负时长问题）；β=450 min、δ=90 min、ρmax=0.1 等鲁棒优化参数。

## 2 数据与校准方法

只读流式读取台北 372 场采集（未修改采集器）：
- {BT}research/collection/taipei_372_polling_20261030/data/2026-10-30|31/parking_slots.jsonl{BT}：净占用 O = baseline_totalcar - availablecar。
- 同目录 {BT}connector_status_long.jsonl{BT}：逐枪状态只有「待機中」「充電中」。

窗口：按槽统计有效场站比例，剔除整槽 request_failed，两端裁到有效率 ≥90% 的连续段。本次窗口 **{P["bins"].get("window_local_start")} – {P["bins"].get("window_local_end")}**，共 {P["bins"].get("n_slots")} 槽 × 5 min，horizon {P["generator"]["horizon_min"]} min。

**分时到达强度 λ(t)**：5 分钟净增计数 Σ max(0,ΔO)，归一到辆/100 车位/小时，按时钟小时分箱（本机时区；共 {P["bins"]["count"]} 箱，含被窗口边界切开的同一钟点，生成时按观测分钟数加权合并成 24 个钟点）。这是到达数的**下界**：同槽到达与离场相抵、场站饱和（TPE0007/TPE0151 白天占用 0.97–1.00）时不可见。不使用 O(t)=∫λS 反演作主估计（实测该反演在单日窗口退化）。

**停车时长**：只有净占用，无法恢复逐车轨迹。用两条信号：
1. Little 恒等式 E[dwell] = 平均在场车辆数 / λ̄（逐场站，分钟）；
2. 夜间低到达段（00:00–03:00 起 5 个锚点、τ≤300 min）的占用衰减给出短停形状，夜间 01–06 时占用均值 = 过夜长停车辆数。
两成分混合：arrival-share 权重 w_long = λ_long/λ̄，λ_long = 夜间核心车数 × 60 / 720 min；长停均值 720 min 为**情景值**，短停均值由均值恒等式反解。当夜间核心反解出的长停份额 ≥0.90 或均值恒等式给出不会理的短停均值时，改用**单成分均值匹配 lognormal**（{BT}single_component_mean_matched{BT}，quality_notes 有标记）：只有均值是数据驱动的，形状是情景。所有场站的混合均值都等于 Little 均值（verify_report.json 里有逐场站 dwell 校验）。

**充电会话（重算口径）**：{ch["recount_method"]}

统计得到：非验证场站 {ch["n_start_transitions"]} 次会话、{ch["n_complete_sessions"]} 次两端完整会话；平均 span 时长 {ch["mean_charge_duration_min"]:.1f} min（内部完整会话 {ch["mean_complete_charge_duration_min"]:.1f} min），p50 {ch["charge_duration_dist"]["p50_min"]:.0f} min、p90 {ch["charge_duration_dist"]["p90_min"]:.0f} min；枪可用率上界 {ch["connector_availability_upper_bound"]:.3f}，枪充电占用比 {ch["connector_share_charging"]:.3f}。

**不可识别**：p_EV 与 q_need 只能识别乘积（{ev["product_required_mean"]:.4f}，见 §4）；「充满未走」滞留不可识别（待機 ≠ 车位空闲，也可能是有车）。{BT}charging.post_charge_lingering{BT} 无点估计。

**能量/物理一致**：功率 11 kW、效率 0.9 为情景；平均需求电量 = 功率 × 平均充电时长 = {en["deficit_mean_kwh"]:.1f} kWh（功率情景 3.5/7/22/60 kW → {en["implied_energy_by_power_kwh"]}）。生成器直接按观测 span 时长分布抽样充电时长（{BT}charge_duration_hist_5min{BT}），能量 = 功率 × 效率 × min(抽样时长, 在场时长)，因此 energy ≤ 功率×效率×dwell 恒成立；窗口不足者计入 shortfall。

## 3 拟合结果（train 场站等权）

| 量 | 值 |
|---|---|
| 分时 λ（辆/100 车位/h，24 小时序 {P["bins"]["local_hour"]}） | {[round(v, 2) for v in tr["arrival_rate_per_100_spaces_hour"]]} |
| 平均占用 | {tr["mean_occupancy_veh_per_100"]:.2f} 辆/100 车位 |
| E[dwell]（Little） | {dwell["mean_min"]:.1f} min（{dwell["family"]}，w_long={dwell.get("long_stay_arrival_share", 0):.3f}） |
| 充电会话率 | {ch["n_start_transitions"]} 次 / 窗口（非验证场站） |
| 平均充电时长 | {ch["mean_charge_duration_min"]:.1f} min（p50 {ch["charge_duration_dist"]["p50_min"]:.0f}，p90 {ch["charge_duration_dist"]["p90_min"]:.0f}） |
| 枪可用率上界 / 充电占用比 | {ch["connector_availability_upper_bound"]:.3f} / {ch["connector_share_charging"]:.3f} |
| p_EV×q_need | {ev["product_required_mean"]:.4f}（p_EV=0.30 → q_need={q30:.3f}） |
| 需求电量 | {en["deficit_mean_kwh"]:.1f} kWh（11 kW 情景） |

小时级拟合优度（train 场站时钟小时聚合，每 100 车位）：RMSE {fit["rmse_veh_per_100_spaces"]:.2f}、r={fit["pearson_r"]:.3f}、峰值 {fit["peak_obs"]:.1f} vs {fit["peak_pred"]:.1f}、均值 {fit["mean_obs"]:.1f} vs {fit["mean_pred"]:.1f}。均值接近，但小时形状相关性弱：可用 train 场站仅 5 个且高度异质（E[dwell] 161–2334 min），日均曲线被长停场站主导。未做平滑或调参掩盖。

## 4 场站隔离、一致性与样本外验证

容量三分位各取 6 个候选：前 4 训练、后 2 验证（共 18）；共享参数只用**可用 train 场站**估计，验证场站不进入任何估计。一致性检查用 λ̄×E[dwell] 换算在场车辆，与实测平均在场比较（阈值 25%），并用离场计数反算 E[dwell] 作独立校验；不合格场站标 UNUSABLE 并排除。

可用 train: {split["usable_train_lots"]}
可用 validation: {split["usable_validation_lots"]}
UNUSABLE: {split["unusable_lots"]}

| 场站 | split | 位数 | 标记 | 实测平均在场 | λ̄(辆/h) | E[dwell](min) | 相对误差 | 充电会话数 | 会话率来源 |
|---|---|---|---|---|---|---|---|---|---|
{table}

验证（只用 train 参数预测）：{val["n_lots"]} 个验证场站，相对 RMSE 均值 {val["mean_relative_rmse"]:.3f}、r={val["mean_pearson_r"]:.3f}。代表性差，说明单一日均 λ 曲线 + 单一 dwell 混合不足以预测异质场站；这是限制而非可隐藏的误差。

观测乘积 p_EV×q_need = 会话率 / λ̄，逐场站如下（Lead 独立核算 TPE0151 = 12/140 ≈ 0.086，与本口径一致）：

{lot_rates_txt}

## 5 生成器（暖启动 + 情景接口）

{BT}apps/parking_lab/workbench/traffic_gen.py{BT}（纯标准库）：
- {BT}generate(params, seed) -> (Arrival 元组, meta){BT}：参考场站整日车流。
- {BT}generate_for_lot(params, lot_id, seed, horizon_min=None, p_ev=None, q_need=None, demand_scale=None) -> (Arrival 元组, meta){BT}：单场站车流，含**暖启动**。
- {BT}save_traffic{BT} / {BT}load_traffic{BT}（读写时用 {BT}stream_hash{BT} 校验）。
- CLI: {BT}python -m apps.parking_lab.workbench traffic --params <fitted_parameters.json> --out <file> --seed 42 --split train{BT}

**暖启动**：t=0 时已有 round(mean_occupancy_vehicles) 辆车在场，其剩余停留抽自「完整停留 D ~ 拟合混合分布，残余 U(0,D)」（随机到访者的剩余寿命分布）。{BT}meta.initial_occupancy_n / initial_occupancy_vehicles{BT} 回显；因此 t=0 占用 ≈ 实测平均值（逐场站平均相对误差 {pool["occupancy_t0_relative_error_mean"]*100:.2f}%）。TPE0151 实测（seed=1）：{warm_txt}。

**p_EV / q_need 情景**：只识别乘积。默认 {BT}demand_scale=1{BT} 复现实测充电会话到达率（目标次数 = 观测会话率 × horizon）；给定 {BT}p_ev{BT} 时 {BT}q_need = 观测乘积 / p_ev{BT}，超过 1 截断为 1 并置 {BT}meta.identification_conflict=true{BT}；也可给 {BT}demand_scale{BT}（1/2/5）做需求增长情景。meta 回显 {BT}p_ev{BT}、{BT}q_need{BT}、{BT}p_ev_times_q_need_used{BT}、{BT}observed_product_p_ev_q_need{BT}、{BT}observed_sessions_per_day{BT}、{BT}observed_charge_session_per_hour{BT}、{BT}demand_scale{BT}、{BT}identification_conflict{BT}。

**同 seed 跨进程哈希一致**：本进程与两个独立子进程均得到 {BT}{V["hash_check"]["in_process"]}{BT}（见 outputs/verify_report.json）。

## 6 验证数字（verify.py，seed={V["seed"]}，{V["n_lots_verified"]} 个可用场站）

- 分时到达（排除暖启动车辆）：小时 r={pool["hourly_arrival_r_mean"]:.3f}，RMSE={pool["hourly_arrival_rmse_mean"]:.2f} 辆/h；
- 占用曲线：每 100 车位 RMSE={pool["occupancy_rmse_veh_per_100_mean"]:.1f}，相对 RMSE={pool["occupancy_relative_rmse_mean"]:.3f}，r={pool["occupancy_r_mean"]:.3f}；
- 暖启动：t=0 占用与实测均值平均相对误差 {pool["occupancy_t0_relative_error_mean"]*100:.2f}%；
- 充电时长：与 {pool["observed_charge_duration_n"]} 个实测会话的两样本 KS={pool["charge_duration_ks_vs_observed"]:.3f}（模拟侧 {pool["sim_charge_duration_n"]} 个会话）；
- 物理检查：{V["checks"]}。

## 7 限制（本阶段不声称）

1. 只观测净占用：λ 是到达数下界，饱和场站到达不可见。
2. 停车时长分布不能唯一识别：短停/长停分享 λ 不可分离；长停均值是 720 min 情景，部分场站退化为单成分均值匹配。
3. 两态枪状态：待機 ≠ 空位，「充满未走」滞留与 p_EV/q_need 各自不可识别。
4. 充电功率不可观测（11 kW/0.9 为情景）；span 时长含内部间隙，个别 span 超过单次电池容量，能量按功率×时长计算（不额外截断到电池容量）。
5. 单一连续观测段（{P["bins"].get("window_local_start")} 起约 {P["generator"]["horizon_min"] / 60:.1f} h），无周末/季节变化；场站间异质性大，共享参数外推能力弱（验证相对 RMSE {val["mean_relative_rmse"]:.2f}）。
6. p_ev 情景网格中 p_ev=0.02 时 q_need>1，说明该情景与实测会话率不相容，已在 {BT}ev.q_need_by_p_ev{BT} 保留原值。
7. UNVERIFIED: M07 Fig.5(c) 四类时长占比为图形内容，未数字化。

## 8 产物

- 参数：{BT}fitted_parameters.json{BT}（per_lot 18 条、consistency.rows、charging/ev/energy、bins、split）
- 数据：{BT}data/panel_selected_lots.json{BT}、{BT}data/charge_sessions_summary.json{BT}、{BT}data/fit_diagnostics.json{BT}
- 验证：{BT}verify.py{BT}、{BT}outputs/verify_report.json{BT}、{BT}outputs/sample_traffic_seed42.json{BT}
- 代码：{BT}apps/parking_lab/workbench/traffic_gen.py{BT}、{BT}apps/parking_lab/workbench/tests/test_traffic_gen.py{BT}、{BT}__main__.py{BT}
- 校准脚本：{BT}calibrate.py{BT}
"""
(HERE / "calibration_report.md").write_text(text, encoding="utf-8")
print("WROTE calibration_report.md lines", len(text.splitlines()))
