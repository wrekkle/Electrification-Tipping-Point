# R2-E：π2 预测共享重设 × 饱和分层的规则对照实验

任务：第二轮的 π2 预测共享重设（预测对象可配置、闸门扣除本次油车占用、保护窗口与油车
占用协调）与“饱和程度 × p_EV × 需求放大”分层实验。生产仿真 simulation.py / config.py
本轮不在写权限内，实验通过研究用子类注入可见离场估计与 π2 选项；规则判定全部在
rules.py 内。默认选项下子类与生产仿真的行为一致（决策、交付、指标），仅审计 detail 因
注入离场统计而多字段；自检见 [summary.json](outputs/summary.json) 的 parity_check =
identical_behavior。

## 1. 复现与产物

命令（仓库根目录，退出码 0，本次 492.6 s / 5226 次仿真）：

    python research/round2_20261031/rules_v2/run_rules_v2.py

- 种子 1031/1032；α=0.05（附 α=0.10）；k 粗网格步长 2、上限 48、首过点补 ±1。
- 训练/验证切分：阈值与窗口只在 training 情景选择，validation 不重调。
- 源文件 sha256：rules.py 012ced77…、prediction.py 559d1eed…、test_type_rules.py
  1d729244…、harness.py 41f3cb00…、run_rules_v2.py 530aba23…；完整哈希写入各 JSON meta。
- 产物：[scenarios.json](outputs/scenarios.json)（情景/车流哈希/分层/自检）、
  [k_sweep.json](outputs/k_sweep.json)（曲线与 k_α）、[thresholds.json](outputs/thresholds.json)
  （预测对象×窗口×余量，仅训练集）、[fixed_k_validation.json](outputs/fixed_k_validation.json)
  （固定 k 验证）、[reselect_k_validation.json](outputs/reselect_k_validation.json)
  （每规则重选 k）、[summary.json](outputs/summary.json)（汇总）、
  [run_log.txt](outputs/run_log.txt)（运行输出）。

## 2. 情景与实测分层

情景按来源分开标注：observed_calibrated（实测拟合流量）、amplified_calibrated（同流量
放大到访/充电需求，保持 p_EV×q_need 乘积）、synthetic_range（稳态强度网格）、
synthetic_stress（纯合成压力）。普通位压力用 π0 在参考 k 处的实测占用率分层（<0.60 不
饱和 / 0.60–0.85 临界 / ≥0.85 高饱和），覆盖表：

| 情景族 | 不饱和 | 临界 | 高饱和 |
|---|---|---|---|
| observed_calibrated | TPE0610, TPE0008 | TPE0401, TPE1380 | — |
| amplified_calibrated | — | TPE0008×2/×3 | TPE0401×1.5, TPE1380×1.3 |
| synthetic_range | 2 个训练情景 | 2 训练 + 1 验证 | 4 个验证情景 |
| synthetic_stress | — | — | 1 个验证情景 |

**2026-10-31 第三轮更正**：实测（observed_calibrated）情景没有 0.93–0.98 的普通位占用；
最高 0.799（临界），0.93–0.98 的 4 个情景全部是 synthetic_range（另 synthetic_stress=0.980），
均已标注为合成。原句“实测高饱和…39–61”作废；合成/压力情景参考 k 下 π2 放行为 48–82。
以下为原文（保留证据）：

实测高饱和情景（普通位占用 0.93–0.98）里 π2 闸门被真实触发（每次运行 39–61 辆 ICE 被
放行进充电区）；实测临界情景 val_obs_TPE0401/TPE1380 的 shared=0，这些情景的“三规则
相同”不能作为预测有效性的证据（闸门未触发）。

## 3. 实现口径（rules.py / prediction.py）

- 预测对象 PREDICTION_OBJECTS = charge_arrivals（默认）/ ev_arrivals / connector_load；
  三者单位不同，不是同一系数的替换：前两者是窗口内到达数，connector_load 是 Little 律
  的并发带枪位占用位数（= 到达强度 × p_ev × 已观察每 EV 平均占带枪位分钟；缺估计时退回
  charge_arrivals 并在 detail 标注 fallback）。
- π2 闸门：可用 = 空闲充电位 − 1（本次这辆油车）− pending_shared_bays，
  可用 − 预测需求 ≥ safety_margin 才放行；detail 记录 usable_after_this_ice。
- 保护窗口：有效窗口 = max(window_min, 已观察油车平均占用分钟)（coordinate_window 开）。
- 离场估计 prediction.ObservableOccupancy 只用已发生离场，在场车辆右删失不计入。
- 隐藏信息测试加强（test_type_rules.py，30 条通过）：同可观察前缀同决策/同预测；预测
  只有在观察到充电开始后才允许变化；无可观察后果的 needs_charge 真值不改变预测；闸门
  扣除贪心反例；预测对象单位/回退/窗口协调单测。

## 4. 固定 k 结果（validation，k_ref = π0 的 k_α；相对 π0 的每次运行均值）

| 规则 | Δunmet_no_connector | ΔICE 有闲置枪位仍被拒 | Δ交付 kWh | Δ被拒总数 |
|---|---|---|---|---|
| π1 | +47.5 | 0 | −451.4 | −38.4 |
| π2 默认（charge_arrivals, 10 min, 0） | +4.8 | +177.0 | −53.3 | −18.0 |
| π2 selected ev_arrivals | +1.0 | +205.6 | −12.2 | −3.6 |
| π2 selected connector_load | +1.5 | +204.9 | −17.4 | −3.0 |

解读：高饱和时 π1 让油车占满充电区，充电未满足事件与交付电量显著恶化；π2 的放行
（合成/压力情景为 48–82 辆/次；原文“39–61”为错标）换来被拒总数下降，但预测保护导致“ICE 被拒而枪位空置”的计数上升（该指标
衡量保护预留成本，不是简单空置浪费），unmet 也略高于 π0。实测临界情景三规则差异为 0
（闸门未触发），不作有效性证据。

## 5. 预测对象差异与阈值选择（仅训练集）

训练集等权目标 = mean(unmet_no_connector) + mean(ICE 有闲置枪位仍被拒)：

| 对象 | 选中窗口/余量 | 训练目标 | 训练 unmet | 训练闲置拒绝 |
|---|---|---|---|---|
| charge_arrivals | 10 min / 0 | 6.64 | 2.57 | 4.07 |
| ev_arrivals | 10 min / 0 | 13.29 | 2.14 | 11.14 |
| connector_load | 10 min / 0 | 13.43 | 2.07 | 11.36 |

三者都落在网格边界（10 min、0 余量）：训练目标被“少拒绝油车”主导，是本次情景/目标下的
角点解，不能外推成“10 分钟窗口最优”。验证集上 ev_arrivals/connector_load 的未满足事件
增量更小（+1.0/+1.5 vs charge_arrivals +7.0），代价是保护性拒绝更多；三种对象的差异不
能解释为“某个公式更正确”（单位不可通约，且依赖训练情景的饱和结构）。

## 6. 每规则重选 k（validation）

π0 的 α=0.05 k_α 有 14/18 个情景可达；π1 8/18、π2 默认 12/18；不可达的 4 个情景普通位
占用 0.93–0.98（总需求超过容量，任何 k≤48 都达不到 α 服务目标），按契约
infeasible_upper_bound 报告，并用 α=0.10 与最小 unmet 参考 k 做固定 k 对照（basis 写入
scenarios.json）。重选 k 相对 π0 参考 k：π2 默认平均 +5.3（个别情景 +3…+17）、
selected_charge_arrivals +5.0、ev_arrivals 0、connector_load +0.5；同一规则在 k_α 与 k_ref
之间的容量效应（delta_vs_same_rule_at_fixed_k）为 −5.6…+0.3 件未满足事件。重选 k 同时
改变普通位容量（n_spaces 固定、charging_bays=k），必须与固定 k 结果分开解读，不能把
重选后的差异全部归因于规则。

## 7. 不能声称的结论与限制

- 实测情景的充电需求来自 p_EV 情景假设（p_EV×q_need 只在乘积上可识别），不是观测到的
  充电意愿；“实测”仅指停车到访/停留的拟合。
- 只有 2 个种子；阈值网格角点解；馈线功率按 7 kW×k 设为不约束，功率共享成本不在本轮。
- 闸门未触发情景（实测临界/低饱和）不能证明预测有效性；本报告未宣称预测带来普遍收益。
- 第一轮 research/sim_rules_20261031/outputs/rule_comparison.json 为历史结果，未覆盖；
  本轮 π2 闸门已改为扣除本次油车占用，数值不可与历史文件直接对比。

## 8. 交接 TODO

1. ~~把 prediction_object / coordinate_window / pending_shared_bays 接进 config.py 与
   simulation.py~~ 已于 2026-10-31 第三轮接线（config 字段 + Simulation 可见离场统计 +
   同批次 pending）；研究子类不再是必需，默认仍为 charge_arrivals。
2. 实测情景需要 p_EV 敏感性（不可识别），以及重选 k 的容量效应专门实验。
3. ~~costs.occupancy_minutes.no_charging_demand 仍混入油车占位~~ 已于第二轮修复：油车占枪
   单列 `ice_blocking_connector`，三类占位可加总（2026-10-31 第三轮复核确认；原文为第二轮
   写作时的过时说明）。
4. 多情景多种子扩展（≥10）后再判断预测对象优劣与窗口最优值。
