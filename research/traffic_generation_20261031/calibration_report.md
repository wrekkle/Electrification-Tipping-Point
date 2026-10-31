# 车流生成器校准报告（阶段三，2026-10-31）

类型: 研究报告
状态: 生效
负责人: traffic-gen
日期: 2026-10-31
数据窗口: None – None（本机时区 UTC+08:00）
校准脚本: `calibrate.py`（重跑: `python research/traffic_generation_20261031/calibrate.py`）
生成器: `apps/parking_lab/workbench/traffic_gen.py`（纯标准库，traffic_gen-1.0.0）

本报告只覆盖自己名下产物：`research/traffic_generation_20261031/`、`apps/parking_lab/workbench/traffic_gen.py`、`apps/parking_lab/workbench/tests/test_traffic_gen.py`、`apps/parking_lab/workbench/__main__.py`（仅新增 traffic 子命令）。

## 1 M07 §5.1 观测 / 拟合 / 假设核对

本地 PDF 文本抽取（pymupdf，文本见 `_scratch/M07.txt`）：§5.1「Demand and supply」位于印刷页 15–16 / PDF 页 15–16（M07.txt 第 1249 行起）；Table 1「Parameters of park and charge demand distribution」位于印刷页 14 / PDF 页 14（第 1185–1206 行）。与 Lead 独立核对一致。

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
- 电价/服务费 Table 3；停车时长上限 β=450 min；δ=90 min；ρmax=0.1 推出 15 min buffer；权重 α1=α2=α3=1；步行系数 5、冲突单价 5；C_res=1 RMB/user、C_park=1.5 RMB/15min、C_park^max=36 RMB；Pm∈{60,7} kWh/h。

**可迁移到本项目**：真实停车数据 → 分时到达 + 时长分布 → 按时段分组；停车与充电数据分开拟合；用离场/到达时间戳拟合时长。
**不可照搬**：停车:充电需求比例与 charging ratio=1；快慢充 15/85、20/80 分配；杭州电价/服务费/冲突罚价/停车费；私人运营商 4 万条快充记录的任何具体数值；Table 1 的停车时长四类均值（杭州通勤/月租结构与负时长问题）；β=450 min、δ=90 min、ρmax=0.1 等鲁棒优化参数。

## 2 数据与校准方法

只读流式读取台北 372 场采集（未修改采集器）：
- `research/collection/taipei_372_polling_20261030/data/2026-10-30|31/parking_slots.jsonl`：净占用 O = baseline_totalcar - availablecar。
- 同目录 `connector_status_long.jsonl`：逐枪状态只有「待機中」「充電中」。

窗口：按槽统计有效场站比例，剔除整槽 request_failed，两端裁到有效率 ≥90% 的连续段。本次窗口 **None – None**，共 None 槽 × 5 min，horizon 1440 min。

**分时到达强度 λ(t)**：5 分钟净增计数 Σ max(0,ΔO)，归一到辆/100 车位/小时，按时钟小时分箱（本机时区；共 25 箱，含被窗口边界切开的同一钟点，生成时按观测分钟数加权合并成 24 个钟点）。这是到达数的**下界**：同槽到达与离场相抵、场站饱和（TPE0007/TPE0151 白天占用 0.97–1.00）时不可见。不使用 O(t)=∫λS 反演作主估计（实测该反演在单日窗口退化）。

**停车时长**：只有净占用，无法恢复逐车轨迹。用两条信号：
1. Little 恒等式 E[dwell] = 平均在场车辆数 / λ̄（逐场站，分钟）；
2. 夜间低到达段（00:00–03:00 起 5 个锚点、τ≤300 min）的占用衰减给出短停形状，夜间 01–06 时占用均值 = 过夜长停车辆数。
两成分混合：arrival-share 权重 w_long = λ_long/λ̄，λ_long = 夜间核心车数 × 60 / 720 min；长停均值 720 min 为**情景值**，短停均值由均值恒等式反解。当夜间核心反解出的长停份额 ≥0.90 或均值恒等式给出不会理的短停均值时，改用**单成分均值匹配 lognormal**（`single_component_mean_matched`，quality_notes 有标记）：只有均值是数据驱动的，形状是情景。所有场站的混合均值都等于 Little 均值（verify_report.json 里有逐场站 dwell 校验）。

**充电会话（重算口径）**：dedupe by (parking_id, spot_abrv, slot_start_utc) keeping the non-duplicate_batch row; sort each connector by slot; merge 充電中 slots separated by <=5 missing/non-charging slots (25 min) into one session; duration = (last-first)+5 min span (internal gaps count as charging); sessions touching either window edge are flagged left/right censored but still counted in the session rate; duration mean/p50/p90 use all sessions, mean_complete_min uses internal-only ones

统计得到：非验证场站 2800 次会话、1620 次两端完整会话；平均 span 时长 297.1 min（内部完整会话 172.7 min），p50 125 min、p90 925 min；枪可用率上界 0.674，枪充电占用比 0.326。

**不可识别**：p_EV 与 q_need 只能识别乘积（0.0364，见 §4）；「充满未走」滞留不可识别（待機 ≠ 车位空闲，也可能是有车）。`charging.post_charge_lingering` 无点估计。

**能量/物理一致**：功率 11 kW、效率 0.9 为情景；平均需求电量 = 功率 × 平均充电时长 = 49.0 kWh（功率情景 3.5/7/22/60 kW → {'3.5kW': 17.329166666666666, '7.0kW': 34.65833333333333, '11.0kW': 54.463095238095235, '22.0kW': 108.92619047619047, '60.0kW': 297.07142857142856}）。生成器直接按观测 span 时长分布抽样充电时长（`charge_duration_hist_5min`），能量 = 功率 × 效率 × min(抽样时长, 在场时长)，因此 energy ≤ 功率×效率×dwell 恒成立；窗口不足者计入 shortfall。

## 3 拟合结果（train 场站等权）

| 量 | 值 |
|---|---|
| 分时 λ（辆/100 车位/h，24 小时序 [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]） | [7.05, 8.68, 5.85, 5.19, 6.91, 3.98, 7.27, 13.31, 14.43, 7.08, 0.2, 1.04, 0.47, 0.78, 0.12, 0.16, 2.37, 0.0, 1.16, 1.43, 4.19, 4.76, 10.11, 13.09, 12.56] |
| 平均占用 | 47.45 辆/100 车位 |
| E[dwell]（Little） | 940.9 min（two_component_mixture，w_long=0.075） |
| 充电会话率 | 2800 次 / 窗口（非验证场站） |
| 平均充电时长 | 297.1 min（p50 125，p90 925） |
| 枪可用率上界 / 充电占用比 | 0.674 / 0.326 |
| p_EV×q_need | 0.0364（p_EV=0.30 → q_need=0.121） |
| 需求电量 | 49.0 kWh（11 kW 情景） |

小时级拟合优度（train 场站时钟小时聚合，每 100 车位）：RMSE 17.72、r=0.087、峰值 70.5 vs 72.5、均值 46.7 vs 52.6。均值接近，但小时形状相关性弱：可用 train 场站仅 5 个且高度异质（E[dwell] 161–2334 min），日均曲线被长停场站主导。未做平滑或调参掩盖。

## 4 场站隔离、一致性与样本外验证

容量三分位各取 6 个候选：前 4 训练、后 2 验证（共 18）；共享参数只用**可用 train 场站**估计，验证场站不进入任何估计。一致性检查用 λ̄×E[dwell] 换算在场车辆，与实测平均在场比较（阈值 25%），并用离场计数反算 E[dwell] 作独立校验；不合格场站标 UNUSABLE 并排除。

可用 train: ['TPE0008', 'TPE0610', 'TPE0401', 'TPE0695', 'TPE0330']
可用 validation: ['TPE1376', 'TPE0930', 'TPE1380', 'TPE1171']
UNUSABLE: ['TPE0140', 'TPE0304', 'TPE0007', 'TPE0151', 'TPE0003', 'TPE0110', 'TPE0575', 'TPE1011', 'TPE0827']

| 场站 | split | 位数 | 标记 | 实测平均在场 | λ̄(辆/h) | E[dwell](min) | 相对误差 | 充电会话数 | 会话率来源 |
|---|---|---|---|---|---|---|---|---|---|
| TPE0008 | train | 76 |  | 29.29 | 5.14 | 342 | 18.9% | 2 | pooled_scaled |
| TPE0140 | train | 61 | UNUSABLE | 35.92 | 4.00 | 539 | 0.0% | 5 | pooled_scaled |
| TPE0304 | train | 88 | UNUSABLE | 28.61 | 2.24 | 765 | -51.3% | 1 | pooled_scaled |
| TPE0610 | train | 43 |  | 9.04 | 3.43 | 158 | 3.7% | 1 | pooled_scaled |
| TPE0007 | train | 105 | UNUSABLE | 85.27 | 5.63 | 908 | -0.7% | 6 | pooled_scaled |
| TPE0151 | train | 151 | UNUSABLE | 100.32 | 5.80 | 1039 | -2.7% | 12 | observed |
| TPE0401 | train | 205 |  | 177.83 | 4.57 | 2334 | 23.1% | 12 | observed |
| TPE0695 | train | 146 |  | 29.20 | 7.92 | 221 | 10.2% | 1 | pooled_scaled |
| TPE0003 | train | 457 | UNUSABLE | 328.99 | 8.45 | 2336 | 55.6% | 21 | observed |
| TPE0110 | train | 973 | UNUSABLE | 689.43 | 8.82 | 4692 | -31.2% | 30 | observed |
| TPE0330 | train | 851 |  | 603.68 | 21.96 | 1649 | -15.4% | 13 | observed |
| TPE0575 | train | 297 | UNUSABLE | 248.77 | 7.22 | 2066 | -3.3% | 15 | observed |
| TPE1011 | validation | 36 | UNUSABLE | 19.15 | 0.73 | 1564 | -41.9% | 0 | pooled_scaled |
| TPE1376 | validation | 73 |  | 59.08 | 3.35 | 1059 | 15.5% | 2 | pooled_scaled |
| TPE0930 | validation | 175 |  | 159.97 | 4.29 | 2240 | 5.0% | 4 | pooled_scaled |
| TPE1380 | validation | 170 |  | 158.00 | 3.43 | 2765 | -2.3% | 4 | pooled_scaled |
| TPE0827 | validation | 400 | UNUSABLE | 104.23 | 4.41 | 1419 | -50.5% | 18 | observed |
| TPE1171 | validation | 231 |  | 111.00 | 9.88 | 674 | -21.4% | 3 | pooled_scaled |

验证（只用 train 参数预测）：4 个验证场站，相对 RMSE 均值 0.553、r=0.227。代表性差，说明单一日均 λ 曲线 + 单一 dwell 混合不足以预测异质场站；这是限制而非可隐藏的误差。

观测乘积 p_EV×q_need = 会话率 / λ̄，逐场站如下（Lead 独立核算 TPE0151 = 12/140 ≈ 0.086，与本口径一致）：

- TPE0008: sessions=2 mean=297.1 rate/h=0.12 product=0.0228
- TPE0140: sessions=5 mean=171.0 rate/h=0.09 product=0.0235
- TPE0304: sessions=1 mean=297.1 rate/h=0.14 product=0.0604
- TPE0610: sessions=1 mean=297.1 rate/h=0.07 product=0.0193
- TPE0007: sessions=6 mean=120.8 rate/h=0.16 product=0.0287
- TPE0151: sessions=12 mean=272.9 rate/h=0.50 product=0.0863
- TPE0401: sessions=12 mean=166.7 rate/h=0.50 product=0.1094
- TPE0695: sessions=1 mean=297.1 rate/h=0.23 product=0.0284
- TPE0003: sessions=21 mean=156.2 rate/h=0.88 product=0.1036
- TPE0110: sessions=30 mean=856.3 rate/h=1.25 product=0.1418
- TPE0330: sessions=13 mean=1425.0 rate/h=0.54 product=0.0247
- TPE0575: sessions=15 mean=143.3 rate/h=0.62 product=0.0865
- TPE1011: sessions=0 mean=297.1 rate/h=0.06 product=0.0755
- TPE1376: sessions=2 mean=297.1 rate/h=0.11 product=0.0336
- TPE0930: sessions=4 mean=297.1 rate/h=0.27 product=0.0629
- TPE1380: sessions=4 mean=297.1 rate/h=0.26 product=0.0764
- TPE0827: sessions=18 mean=149.4 rate/h=0.75 product=0.1701
- TPE1171: sessions=3 mean=297.1 rate/h=0.36 product=0.0360

## 5 生成器（暖启动 + 情景接口）

`apps/parking_lab/workbench/traffic_gen.py`（纯标准库）：
- `generate(params, seed) -> (Arrival 元组, meta)`：参考场站整日车流。
- `generate_for_lot(params, lot_id, seed, horizon_min=None, p_ev=None, q_need=None, demand_scale=None) -> (Arrival 元组, meta)`：单场站车流，含**暖启动**。
- `save_traffic` / `load_traffic`（读写时用 `stream_hash` 校验）。
- CLI: `python -m apps.parking_lab.workbench traffic --params <fitted_parameters.json> --out <file> --seed 42 --split train`

**暖启动**：t=0 时已有 round(mean_occupancy_vehicles) 辆车在场，其剩余停留抽自「完整停留 D ~ 拟合混合分布，残余 U(0,D)」（随机到访者的剩余寿命分布）。`meta.initial_occupancy_n / initial_occupancy_vehicles` 回显；因此 t=0 占用 ≈ 实测平均值（逐场站平均相对误差 0.27%）。TPE0151 实测（seed=1）：暖启动 100 辆、t=0 占用 100、24h 平均占用 99.7、实测 100.32。

**p_EV / q_need 情景**：只识别乘积。默认 `demand_scale=1` 复现实测充电会话到达率（目标次数 = 观测会话率 × horizon）；给定 `p_ev` 时 `q_need = 观测乘积 / p_ev`，超过 1 截断为 1 并置 `meta.identification_conflict=true`；也可给 `demand_scale`（1/2/5）做需求增长情景。meta 回显 `p_ev`、`q_need`、`p_ev_times_q_need_used`、`observed_product_p_ev_q_need`、`observed_sessions_per_day`、`observed_charge_session_per_hour`、`demand_scale`、`identification_conflict`。

**同 seed 跨进程哈希一致**：本进程与两个独立子进程均得到 `8d1e990a546b8616f423074f16d89a8cc8d2d55f764fe12dd9b8c0f5e83e55e3`（见 outputs/verify_report.json）。

## 6 验证数字（verify.py，seed=42，9 个可用场站）

- 分时到达（排除暖启动车辆）：小时 r=0.931，RMSE=2.34 辆/h；
- 占用曲线：每 100 车位 RMSE=15.8，相对 RMSE=0.247，r=0.703；
- 暖启动：t=0 占用与实测均值平均相对误差 0.27%；
- 充电时长：与 2800 个实测会话的两样本 KS=0.228（模拟侧 52 个会话）；
- 物理检查：{'arrivals_sorted': True, 'energy_within_power_window': True, 'needs_charge_implies_ev': True, 'dwell_mixture_mean_matches_little_by_lot': True}。

## 7 限制（本阶段不声称）

1. 只观测净占用：λ 是到达数下界，饱和场站到达不可见。
2. 停车时长分布不能唯一识别：短停/长停分享 λ 不可分离；长停均值是 720 min 情景，部分场站退化为单成分均值匹配。
3. 两态枪状态：待機 ≠ 空位，「充满未走」滞留与 p_EV/q_need 各自不可识别。
4. 充电功率不可观测（11 kW/0.9 为情景）；span 时长含内部间隙，个别 span 超过单次电池容量，能量按功率×时长计算（不额外截断到电池容量）。
5. 单一连续观测段（None 起约 24.0 h），无周末/季节变化；场站间异质性大，共享参数外推能力弱（验证相对 RMSE 0.55）。
6. p_ev 情景网格中 p_ev=0.02 时 q_need>1，说明该情景与实测会话率不相容，已在 `ev.q_need_by_p_ev` 保留原值。
7. UNVERIFIED: M07 Fig.5(c) 四类时长占比为图形内容，未数字化。

## 8 产物

- 参数：`fitted_parameters.json`（per_lot 18 条、consistency.rows、charging/ev/energy、bins、split）
- 数据：`data/panel_selected_lots.json`、`data/charge_sessions_summary.json`、`data/fit_diagnostics.json`
- 验证：`verify.py`、`outputs/verify_report.json`、`outputs/sample_traffic_seed42.json`
- 代码：`apps/parking_lab/workbench/traffic_gen.py`、`apps/parking_lab/workbench/tests/test_traffic_gen.py`、`__main__.py`
- 校准脚本：`calibrate.py`
