# 阶段四规则实现与三规则同流对比（sim-rules）

类型: 研究报告（阶段四规则部分）
状态: 生效
负责人: tho25
日期: 2026-10-31

本文件记录阶段四"按车型准入三条规则 + 隐藏信息边界"的实现、口径与合成对比结果。
范围只含规则与计量，不含配桩整数优化、不含社会成本结论。合同口径见
[CONTRACT §7](../official_data_20261031/contract/CONTRACT.md)、成本口径见
[COST-MODEL-V2](../../docs/methods/COST-MODEL-V2.md)、方案背景见
[2026-10-30 方案 §4-5](../../docs/reports/2026-10-30-充电率证据与后端实施方案.md)。

## 1 结论摘要

1. 三条正式规则已实现于 [rules.py](../../apps/parking_lab/workbench/rules.py)：控制器只接收
   `is_ev`、当前占用与资源、历史统计与短期预测；`needs_charge`/能量/真实离场时间/未来到达
   在接口签名里就不存在。旧 `strict` 保留在 [simulation.py](../../apps/parking_lab/workbench/simulation.py)
   的 legacy 分支，标签改为"严格分区（legacy，按隐藏意愿分区，仅历史复现）"。
2. 隐藏信息泄漏已修：[prediction.py](../../apps/parking_lab/workbench/prediction.py) 的
   `Learner` 不再 `observe needs_charge`，改为在**首次实际交付电量（开始充电）**时记录
   `observe_charging_start()`，仍是先发布后更新。
3. 泄漏反例测试通过：同一可观测输入、两个不同 `needs_charge` 真值的车流，π0/π1/π2 分配的
   车位序列完全相同（只有交付电量与占用后果不同）；legacy `strict` 的车位序列不同，
   证明旧实现确实按隐藏意愿分区。
4. 三类占位分钟单独计量并进 `snapshot/export/metrics`，逐车与逐事件区间可导出；
   同外生流不同 k 重放 `traffic_hash` 一致（见 `tests/test_type_rules.py`）。
5. 固定 k 同流对比（合成，3 seeds）：π1 少拒车但多占带枪位、交付电量更低；
   π2 默认参数下接近 π0（本轮 173 次充电请求中仅 4 次油车按预测放行），
   放宽窗口/余量后接近 π1——参数决定 π2 落在 π0 与 π1 之间。**缺参成本为 null，
   不给货币结论，也不据此定 k\***。

## 2 三条正式规则

虚拟车位编号：带枪位 `[0, chargers)`；充电预留位 `[chargers, charging_bays)`；
普通位 `[charging_bays, n_spaces)`。规则只决定"这辆车能停哪个位"，不读充电意愿。

| 规则 | 车辆 | 候选车位顺序（取第一个空闲） | 拒绝条件 |
|---|---|---|---|
| π0 `dedicated_by_type` | 电车（含本次不充电） | 带枪位 → 充电预留位 → 普通位（保总容量不变） | 全车位满 |
| π0 | 油车 | 普通位 | 无空闲普通位（充电位空着也不放行） |
| π1 `full_open_ice_first` | 电车 | 同 π0 | 全车位满 |
| π1 | 油车 | 普通位 → 带枪位 → 充电预留位 | 全车位满 |
| π2 `predictive_shared_ice_first` | 电车 | 同 π0 | 全车位满 |
| π2 | 油车 | 普通位有空 ⇒ 普通位；否则按预测闸门：`空闲充电位 − 预计充电到达 ≥ 余量` 时放行到充电位（带枪位→预留位），否则拒绝 | 闸门不满足 / 全车位满 |

π2 闸门的算式（全部来自可见历史）：

```
预计充电到达 = 到达强度(辆/分) × p_ev × p_charge_given_ev × 预测窗口(分)
放行条件     = 空闲充电位数 − 预计充电到达 ≥ 余量(车位)
```

`p_charge_given_ev` 只由**已发生的充电开始**估计（见 §4），不是需求真值；预测窗口与余量可配置。

## 3 可观测信息边界

| 控制器可见 | 控制器不可见（也不得进入学习器） |
|---|---|
| 时钟；`is_ev`（按车型，含本次不充电的电车） | `needs_charge` 本次是否要充电 |
| 当前占用：空闲车位编号、带枪位/充电位/总位数量 | SOC/电池容量/`energy_kwh` |
| 历史统计：到达强度、EV 份额、已发生的充电开始比例 | 真实离场时间/计划停留时长 |
| 短期预测：窗口内预计充电到达数 | 未来到达车辆 |

- [rules.py](../../apps/parking_lab/workbench/rules.py) 的 `ObservableState` 没有隐藏字段；
  传入 `needs_charge=True` 直接 `TypeError`（测试覆盖）。
- [simulation.py](../../apps/parking_lab/workbench/simulation.py) 的 `_arrive` 在打分与分配决策
  之后才 `learner.observe(a.is_ev)`；`powers()`、`completion`、占位计量使用隐藏真值，
  那是**物理结算与结果计量**，已与准入决策分离并在导出中标注 `measurement_only`。

## 4 预测的信息边界修正

| 项目 | 修正前 | 修正后 |
|---|---|---|
| 观测接口 | `Learner.observe(is_ev, needs_charge)` | `Learner.observe(is_ev)` + `observe_charging_start()` |
| 充电比例分母 | 需要充电的 EV 到达数（隐藏真值） | 已观察到的 EV 到达数 |
| 充电比例分子 | 需求为真的 EV 数（隐藏真值） | 已发生的充电开始数（首次实际交付电量） |
| 更新时机 | 到达时立即用真值更新 | 先发布预测；充电开始真正发生时再更新 |

`forecast()` 中的 `p_charge_given_ev`、`expected_charge_arrivals` 保留原字段名（界面/导出兼容），
新增 `observed_charging_starts` 与 `charging_start_basis` 说明口径。仿真把`charge_start_min`
写进逐车记录，`assert_invariants` 校验"充电开始必须有实际交付电量且是带枪位上的电车"。

## 5 三类占位分钟（逐车/逐事件）

计量函数 `rules.type_occupancy_ledger(visits, config, cut_min)`，实时累计到 `cut_min`
（缺省 `sim.time`；期末仍在场按删失处理，不计未发生的未来停留）。

| 指标 | 定义 | 发生在 |
|---|---|---|
| `no_charging_demand_bay_min` | 无充电需求电车占用带枪位的分钟 | π0/π1/π2 均可能（电车可进充电位） |
| `overstay_after_complete_min` | 充满后仍占带枪位的分钟：`completion_min` 到释放/离场 | 完成充电后未及时离开 |
| `ice_blocking_connector_min` | 油车占用带枪位的分钟 | π1/π2 共享放行时；π0 应为 0 |

导出位置：`snapshot()["metrics"]` 与 `snapshot()["type_occupancy"]`、
`export()["type_occupancy"]`（`metrics`/`by_visit`/`events`/`definitions`）、
`export()["visits"][i]` 的逐车三字段。逐事件记录形如
`{vehicle_id, reason, bay, start_min, end_min, minutes}`。

**口径提醒（供 Lead 复核 costs.py，本轮不改该文件）**：`costs.occupancy_minutes` 的
`no_charging_demand` 归因在实现上同时包含"油车占带枪位"（其分支只判 `bay < chargers`，
未判 `is_ev`）。本轮新指标把油车部分单列为 `ice_blocking_connector_min`；π1 结果中
`costs` 的 `no_charging_demand`（3216.5 min）与类型口径（2034.4 min）差值 1182.1 min
正是油车占带枪位。成本归因若要按车型拆分，需要在 costs.py 侧另开字段，不属于本单改动范围。

## 6 配置与兼容

[config.py](../../apps/parking_lab/workbench/config.py)：

- `RULE_POLICIES`（正式规则，默认 `dedicated_by_type`）与 `LEGACY_POLICIES`（历史四策略）
  都进 `Config.parse` 校验；旧配置（含 `policy="strict"`、不含新字段）仍可解析。
- 新字段及其默认值：`ice_share_forecast_window_min=30`（分钟，π2 预测窗口）、
  `ice_share_free_bay_margin=1`（车位，π2 放行余量）；越界即报错。
- `POLICIES` 仍是历史四策略集合，`experiments.compare` 与 server 元数据沿用（旧对比口径不变）；
  正式对照用 `RULE_POLICIES`（本轮脚本即如此）。

legacy 四策略保留原准入实现（strict 按 `needs_charge` 分区）；它们的学习器观测也改为可见事件，
因此 `adaptive` 的保留数可能与历史归档有细微差异（历史归档结果保留原字段，不批量改写）。

## 7 复现与输出

```text
python research/sim_rules_20261031/run_rule_comparison.py
python -m unittest discover -s apps/parking_lab/workbench/tests -v
```

- 输出：[outputs/rule_comparison.json](outputs/rule_comparison.json)（脚本生成，首屏带 `生成命令`）。
- 数据：`workbench.demand.generate` 合成车流（**synthetic**，未对任何真实停车场校准）；
  seeds 11/12/13，每 seed 生成一次车流，三规则与不同 k 复用同一 `arrivals`。
- 固定 k：`n_spaces=60, charging_bays=18, chargers=12`，12 小时、peaks 情景、到达 35 辆/小时、
  EV 份额 0.4、充电概率 0.65。每 seed 车流 594/639/642 辆（`demand_hash` 见 JSON `flows`）。
- 同 seed 三规则 `traffic_hash` 全等，且等于 `traffic_hash(arrivals)`（脚本内断言，不符即退出）。

## 8 对比结果（3 seeds 均值，合成）

| 指标 | π0 专用 | π1 全开放 | π2 预测共享（默认 30 min / 1 位） |
|---|---|---|---|
| 到达 / 接纳 / 被拒 | 625 / 440.3 / 184.7 | 625 / 447.3 / 177.7 | 625 / 440.7 / 184.3 |
| 被拒电车 / 被拒油车 | 59.7 / 125.0 | 75.0 / 102.7 | 60.7 / 123.7 |
| 被拒充电请求（需充电且被拒） | 39.3 | 51.0 | 39.7 |
| 充电请求 / 完成 | 173.3 / 26.0 | 173.3 / 24.3 | 173.3 / 25.7 |
| 交付电量 kWh | 548.84 | 443.07 | 547.28 |
| 未服务电量 kWh | 1778.54 | 1884.30 | 1780.10 |
| 离场仍缺电 kWh | 1006.91 | 994.23 | 1004.96 |
| 无充电需求电车占带枪位 min | 2090.43 | 2034.42（−56.00） | 2056.82（−33.61） |
| 充满仍占带枪位 min | 1196.41 | 1122.37（−74.04） | 1196.62（+0.20） |
| 油车占带枪位 min | 0 | 1182.09（+1182.09） | 73.06（+73.06） |
| 平均占用率 | 0.8889 | 0.8904 | 0.8896 |

π2 参数敏感性（同 seed 同流，只改窗口/余量）：

| 窗口 min / 余量 位 | 被拒 | 被拒油车 | 油车按预测放行次数 | 未服务 kWh | 油车占带枪位 min |
|---|---|---|---|---|---|
| 30 / 1（默认） | 184.33 | 123.67 | 4 | 1780.10 | 73.06 |
| 10 / 0 | 177.67 | 102.67 | 73 | 1884.30 | 1182.09 |
| 60 / 0 | 184.33 | 123.67 | 4 | 1780.10 | 73.06 |
| 10 / 2 | 184.33 | 123.67 | 4 | 1780.10 | 73.06 |

可读结论（仅限本合成算例与给定 k）：共享（π1）让油车少被拒 7 辆，但把 1182 分钟油车时间
放进带枪位，交付电量下降约 19%、未服务电量上升约 6%；π2 默认闸门在该拥堵算例下几乎不
放行（4 次），行为接近 π0；把窗口收紧到 10 分钟且余量置 0 后 π2 与 π1 的行为一致
（放行 73 次），说明 π2 的"预测收益"完全取决于阈值/窗口，不能默认其优于 π1 或 π0。

## 9 成本分项（缺参不编造）

- 默认成本参数全为 null：`cost_default_null.cost_complete_runs = 0`，`total` 为 `null`；
  可确定为零的分项（`ice_activity_loss`、`ev_activity_loss` 等）保持 0.0。
- 缺失参数 `missing_parameters` 共 16 项（时间价值、绕行时间/里程、能耗价格、替代补能价差、
  剩余行程损失、维护、折旧、电价等），按去向分组的缺参来源见
  `runs[*].cost_missing_by_disposition`（`detour_exit` 与 `admitted_shortfall`）。
- 用 `config.ILLUSTRATIVE_COST` 跑一组标注 `illustrative_not_calibrated` 的算术演示，
  `cost_complete_runs` 仍为 0：已接纳但离场仍缺电的车辆，其后续找桩时间与绕行距离在本仿真
  无观测，按 COST-MODEL-V2 §7 保持 null，不填 0、不编造罚价。
- 因此本轮**不给社会成本比较、不给 k\***；规则差异只用物理与服务指标表述。

## 10 测试覆盖

新增 [tests/test_type_rules.py](../../apps/parking_lab/workbench/tests/test_type_rules.py)（24 例）：

- π0：不充电电车可进带枪位，油车即使带枪位空闲也不得进入且落 `disposition`；
- π1：普通位满时油车进入带枪位，同车流 π0 下被拒；
- π2：放行/拒绝两情形，且用截断到决策时刻的可见统计可复算出同一预测值；
- 泄漏反例：同可观测输入、两种 `needs_charge` 真值 ⇒ π0/π1/π2 车位序列相同、legacy strict 不同；
- 边界：零桩、零充电需求、0 时刻到达/期初无占用、期末删失（滞留只算到窗口末、pending ≠ 离场失败）；
- 同外生流不同 k 重放：`traffic_hash`/`demand_hash` 一致；同流重复运行导出逐字节一致。

完整测试套件（含旧 182 例）：`Ran 206 tests ... OK`（`python -m unittest discover -s apps/parking_lab/workbench/tests -v`）。

## 11 限制与未完成

- 合成车流，未对任何真实停车场校准；`q_need` 未识别，`needs_charge` 只是生成器真值。
- 三条规则只在**给定 k**下比较，不是 k 与规则的联合最优性证明；不声称 π2 一定优于 π1。
- π2 默认参数（30 min / 1 位）未经任何数据校准，是配置默认值而非推荐值。
- `costs.occupancy_minutes` 的 `no_charging_demand` 混含油车占带枪位（§5 已量化），
  本轮未改 `costs.py`；是否拆字段由 Lead 决定。
- 本单未接入 `experiments.compare`/server 元数据的正式规则下拉（二者仍按历史四策略输出，
  见 §6）；正式规则对比由本目录脚本完成。
- 未实现：按车流校准的 π2 阈值、占桩配对反事实在新规则下的运行、`docs/TODO.md` 登记。
