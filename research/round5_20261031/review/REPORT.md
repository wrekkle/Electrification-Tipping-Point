# 第五轮追加审稿问题核查报告

状态: 生效
日期: 2026-10-31
范围: joint_k None 语义审计、alpha 与第四约束重分析、四类可行性、元数据实际调用路径、结论边界草稿。
边界: 只读既有曲线与既有第四轮产物；未重跑仿真、未扩网格、未改机制实现、未改 Word、未碰 `research/collection`；不新增 RL/排队/挪车/枚举扩张。
写范围: `research/round5_20261031/review/**`；其余只读。
执行者: review（委派子代理）；共享任务 `task-4`。

## 0 结论摘要

| # | 任务 | 结论 |
|---|---|---|
| 1 | joint_k None 审计 | 127900 个四项率单元中：valid 118205、零分母 9695、**真实缺失 0、非法 0**。A 集（原三条）当前与严格语义只差 15 个单元，全部是 M08-ALL-AWAY-REF 的 `charge_requests=0` 空分母，当前判 k=0 achieved、严格判无解；B 集（加第四条）差异 259 个单元。**15 个 A 集单元与 259 个 B 集单元不得确认为全域最小。** |
| 2 | alpha/第四约束重分析 | 6 个曲线块、735 条曲线单元、4410 个 (alpha,约束集) 组合。alpha=0.05/A 下 B/C/D 的 Δk 中位全为 0、正 Δ 全为 0、负 Δ 各 2/2/1；四类中“仅共享可行”全为 0。加第四条后达成单元从 780/975 降到 310/975（严格 51）；中位 Δk 仍 0，未观察到排序翻转。 |
| 3 | 四类可行性 | fixed-k 独立种子同 k：B 双方/仅专用/仅共享/均不可行 = 34/2/0/12；D = 35/1/0/12。同 k 下双方可行单元的容量未服务率与 EV 停车失败率为 0，离场缺电率均值 0.508（36/69 有定义）。 |
| 4 | 元数据路径 | 工作台 synthetic 标识保留；**正式结果行不保留**（M1）。情景侧 provenance 完整，观测校准侧只有 path+sha（M2）；`data_trace` C13 只覆盖第三轮（M3）。隐藏真值只做计量/归因、正式规则不读，但机制输出无机器可读 analysis-only 标签（M4）。 |
| 5 | 结论边界 | 接入、能量、设施成本、完整社会福利分开表述；共享不预设省枪；有限枚举不写成定理。见 `review/boundaries.md`。 |

## 1 执行与产物

| 产物 | 生成命令 | 解释器 | 退出码 |
|---|---|---|---|
| `review/joint_k_none_audit.json` | `python research/round5_20261031/review/audit_joint_k.py` | `C:\anaconda\python.exe` / Python 3.12.3 | 0 |
| `review/reanalysis_alpha_constraints.json` | `python research/round5_20261031/review/reanalysis_alpha_constraints.py` | 同上 | 0 |
| `review/four_categories.json` | `python research/round5_20261031/review/four_categories.py` | 同上 | 0 |
| `review/run_manifest.json` | `python research/round5_20261031/review/run_all.py` | 同上 | 0（三脚本全 0，含输出 sha256） |
| `review/metadata_paths.md` | 只读静态核查 | 无代码执行 | - |
| `review/boundaries.md` | 只读重分析结论整理 | 无代码执行 | - |

整仓检查：`python scripts/check_all.py` 用 `C:\anaconda\python.exe` 退出码 1（缺 python-docx，无法解析 docx）；改用 DSH 运行时 Python（带 python-docx）首次退出码 0，三项检查通过。收尾复跑时文档检查报 1 个错误：`docs/PROGRESS.md` 长度 3333 超过上限 3200（该文件在本次写范围外，收尾期间被其他执行者更新，非 review 产物导致）；稿件字数与文献索引仍通过。本轮未改 Word/正文。

重分析只读以下既有结果：`research/round3_20261031/results/main_{A_pi0,B_pi1,C_quota,D_pi2}_ref_s10.json`、`expand_A_pi0_TPE0330_s10.json`、`research/round4_20261031/results/scenario_*_s5.json`、`results/fixedk/*.json`、`mechanism/shared_capacity_mechanism.json`。

## 2 joint_k None 审计

### 2.1 四项率分类计数

曲线范围：第三轮 4 条主曲线（含 expand）+ 第四轮 15 条情景曲线 + 40 个 fixed-k 结果，共 59 个文件、975 个 (曲线,lot,seed,rule) 单元。

| 率 | valid[0,1] | 零分母 not_applicable | 真实缺失 | 非法 |
|---|---:|---:|---:|---:|
| capacity_only_unmet_rate | 31360 | 615 | 0 | 0 |
| ev_parking_failure_rate | 31975 | 0 | 0 | 0 |
| ice_parking_failure_rate | 31975 | 0 | 0 | 0 |
| departed_shortfall_energy_rate | 22895 | 9080 | 0 | 0 |
| **合计** | **118205** | **9695** | **0** | **0** |

- 零分母判定证据：`apps/parking_lab/workbench/service_metrics.py:20,64-72`（分母缺失/≤EPS 时比值一律 None，不写 0）；`research/integer_allocation_20261031/run_cost_curve.py:225-226`（`capacity_only_unmet_rate` 分母为 `charge_requests`，=0 时 None）；预登记语义 `research/round3_20261031/PREREGISTRATION.json:61`（零分母标 not_applicable，约束跳过并记录）。
- 当前 `analyze_round3.py:65-89` 对所有 None 一律 `continue`（缺失跳过），不区分零分母与真实缺失。

### 2.2 受影响单元与最小 k

- 受影响单元 320 个：`departed_shortfall_energy_rate` 320 个（9080 个单元-率格子）、`capacity_only_unmet_rate` 15 个（615 格）；EV/ICE 停车失败率 0 个；四项率出现缺失的最小 k 均为 0。
- 15 个容量率空分母单元全部在 `scenario_M08-ALL-AWAY-REF_{A,B,D}_s5`，seeds 1 与 4：全部 41 个 k 上 `charge_requests=0`，当前 joint_k 跳过容量约束后判 **k=0 achieved**；这是空约束通过，不是接入达标。
- 第三轮 main REF 曲线的容量/EV/ICE 率没有缺失；A 集下当前与严格语义的差异全部来自第四轮该情景。

### 2.3 当前 joint_k 与严格语义的推荐差异（alpha=0.05）

| 约束集 | 当前/预登记达成 | 严格达成 | k 或状态变化单元 | 说明 |
|---|---:|---:|---:|---|
| A = 原三条 | 780 / 780 | 765 | 15 | 15 个 M08-ALL-AWAY-REF 单元由 k=0 achieved 变为无解 |
| B = 原三条 + 离场缺电率≤0.05 | 310 | 51 | 259 | 259 个达成单元的第四条在 achieved k 处分母=0（约束空缺） |

- A 集：当前与“仅零分母跳过”的预登记语义完全一致（0 变化）；与“任何缺失都不算 achieved”的严格语义差 15 个单元。
- B 集：310 个 prereg 达成中 259 个在 achieved k 处 `departed_requested_kwh=0`；另有 160 个单元在低于 achieved k 的位置已有第四个率缺失。
- “上界内未达成”不等于物理不可行：现有 `infeasible_upper_bound` 只表示 0..k_max 内没有满足的 k。

### 2.4 不得确认全域最小的单元

- A 集：**15 个**（M08-ALL-AWAY-REF A/B/D × seeds 1/4；k=0 空分母）。这些单元不得写成“最小枪数 0”或“接入达标”。
- B 集：**259 个**（k 处第四条为空或缺分母）。这些单元的“B 集推荐 k”依赖跳过第四条，不得确认为 B 集全域最小。
- 输出字段：`summary.low_k_flags`、`summary.vacuous_at_achieved_k`、`low_k_flag_units`。

## 3 alpha 与第四约束重分析

### 3.1 口径（块间不合并推断）

| 块 | 规则 | 场站 | seeds | k 上限 | charger | feeder | q_need |
|---|---|---|---|---|---:|---:|---:|
| round3_REF | A/B/C/D | 9 | 1–10 | A 的 TPE0330 到 200，其余 40 | 7 kW | 336 kW | 0.36 |
| round4 情景 ×5 | A/B/D | 5（仅 train） | 1–5 | 40 | 7 kW | **120 kW** | 0.0713–0.2857 |

- alpha ∈ {0.02,0.05,0.10} 只作用于前三条；第四条固定 ≤0.05。
- 删失/待定：窗口 1440 min；期末 pending 与右删失不算失败、不进离场能量比。
- 零分母按预登记跳过；真实缺失记 not achieved；k=None 一律解释为搜索上界内未达成。
- **feeder 336 vs 120 是口径差异**：块内 Δk 可比，跨块汇总只作描述，不作为统一功率口径的结论。

### 3.2 Δk 汇总（alpha=0.05，原三条；两处块合并的 735 条曲线单元）

| 规则 | 配对数 | 有定义 Δ | 中位 | Q1 | Q3 | 正 Δ | 负 Δ | 零 | 双方可行 | 仅专用 | 仅共享 | 均未达成 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B | 215 | 173 | 0 | 0 | 0 | 0 | 2 | 171 | 173 | 13 | 0 | 29 |
| C | 90 | 72 | 0 | 0 | 0 | 0 | 2 | 70 | 72 | 13 | 0 | 5 |
| D | 215 | 175 | 0 | 0 | 0 | 0 | 1 | 174 | 175 | 11 | 0 | 29 |

- 第三轮 REF 单块（更贴近主口径）：B/C/D 有定义 Δ = 72/72/74，中位全 0，正 Δ 0，负 Δ 2/2/1，仅共享 0，仅专用 13/13/11，均未达成 5/5/5。
- 负 Δ 的含义是共享规则需要比专用更大的 k（最大差 22），不是“共享省枪”。

### 3.3 alpha 敏感性与第四约束

- 六个 (alpha,约束集) 组合中，正 Δ 全部为 0；B/C/D 的负 Δ 均只有 1–2 个；仅共享可行始终为 0。
- 加第四条后（alpha=0.05，prereg 语义）：B/C/D 双方可行从 173/72/175 降到 60/31/61；均未达成从 29/5/29 升到 146/50/144；Δ 中位仍 0、正 Δ 仍 0。说明第四条主要缩小可行域，没有翻转共享排序。
- 与基线（alpha=0.05/A）比较，520 个共享规则单元中 k 变化数：

| (alpha, 约束集) | k 变化单元 / 520 |
|---|---:|
| 0.02 / A | 4 |
| 0.02 / B | 272 |
| 0.05 / A | 0（基线） |
| 0.05 / B | 268 |
| 0.10 / A | 27 |
| 0.10 / B | 277 |

### 3.4 缺曲线与最小补算清单（先报告，未擅自跑）

1. round4 五个情景块缺 C_quota 曲线（缺 5 条文件），C 只能引用第三轮 REF 块。
2. round4 情景块只有 seeds 1–5，缺 seeds 6–10 的 15 条曲线。
3. B/C/D 的 TPE0330 未扩展到 k>40（A 已扩展），上界不对称；本轮把不对称对计入 `n_excluded_asymmetric_kmax`（实测 0 对），不进入中位/四分位。
4. feeder 口径不一致：round4 情景块是 120 kW，round3 REF 是 336 kW；要统一需按 336 重跑 15 条曲线。
5. round4 情景块只含 5 个训练场站，无 validation 4 场站。

## 4 四类可行性（fixed-k 独立种子）

范围：A 的训练中位 k 在 seeds 5–10 上的评价；B/D 用 A 的同一个 k（`fixedk_common_*`）；8 场站（TPE0330 的 A 训练期未达成，按第四轮设计不进入）× 6 seeds × 2 规则 = 96 单元。

| 规则 | 双方可行 | 仅专用可行 | 仅共享可行 | 双方不可行 |
|---|---:|---:|---:|---:|
| B | 34 | 2 | 0 | 12 |
| D | 35 | 1 | 0 | 12 |

| 类别（合并 B/D） | 单元 | 专用规则：容量未服务 / EV 停车失败 / ICE 停车失败 | 共享规则：同三项 | 离场缺电率（专用/共享） |
|---|---:|---|---|---|
| 双方可行 | 69 | 0 / 0 / 0.0009 | 0 / 0 / 0.0006 | 0.508 / 0.508（36/69 有定义） |
| 仅专用可行 | 3 | 0 / 0 / 0.0332 | 0.1667 / 0.0256 / 0.0154 | 无定义 |
| 仅共享可行 | 0 | - | - | - |
| 双方不可行 | 24 | 0.2007 / 0.0076 / 0.0332 | 0.2267 / 0.0143 / 0.0284 | 0.2638 / 0.2638（18/24 有定义） |

- 同 k、同 seeds 下“仅共享可行”为 0：本数据没有观察到共享把不可行翻成可行；机制有限枚举里的 restoration（333/3456）不能替代数据结论。
- 双方可行样本的离场缺电率均值约 0.508，说明三条约束达标与能量服务达标是两件事。
- 区间/四分位只描述既定情景与既定 k；不写总体显著性。

机制小算例（只引用，不重跑）：

| 识别变体 | 实例 | 双方可行 | 正 Δk | 零 Δk | 负 Δk | π0 不可行→π1 可行 | π0-only | 双方不可行 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 3456 | 1532 | 0 | 1517 | 15 | 333 | 4 | 1587 |
| strict_pi0 | 3456 | 1328 | 641 | 678 | 9 | 537 | 4 | 1587 |
| fixed_zone | 3456 | 847 | 2 | 845 | 0 | 209 | 6 | 2394 |

正 Δk 的计数随识别变体从 0 变到 641，说明“有限枚举”只能给机制分解，不能给一般命题。

## 5 元数据实际调用路径

| 核对项 | 结论 | 缺口 |
|---|---|---|
| (a) 纯合成入口保留 synthetic 标识 | 工作台/API 有（`experiments.py:25`、`server.py:203`、`continuous.py:276-288`、`simulation.py:501-504`）；正式结果行无 | M1 |
| (b) 观测校准 + 情景需求两来源分列 | 情景侧完整（`run_cost_curve.py:255-259,396,430`、`charge_sources.py:9-17,62-99`、`WIRING.md:12-15,31-35`）；观测侧只有 path+sha | M2 |
| (c) 隐藏真值/反事实只作分析性机制分解 | `rules.py:75-76,446`、`simulation.py:150-153,182`、`costs.py:1-6`、`mechanism/README.md:16` 均明确；无机器可读标签 | M4 |

- M1：正式结果无法行级自证“合成”；建议拆成 `synthetic=true` 与 `demand_source_parts=[observed_calibrated, scenario_input]` 两个字段（本轮不改）。
- M2：观测校准被压缩成 params path+sha；两日窗口/拟合限制不进入行。
- M3：`data_trace.py:398-411` 的 C13“M08/M10 未接线”只扫描第三轮 manifest；第四轮接线以 `WIRING.md:10` 与 `scenario_manifest.json` 为准，单独引用 C13 会误读。
- M4：`shared_capacity_mechanism.json` 顶层无 `analysis_only/not_executable_policy`；隐藏真值反事实开关只进 `detail["counterfactual"]`，不进研究结果行。

详见 `review/metadata_paths.md`（含 file:line 证据与 UNVERIFIED）。

## 6 结论边界

按接入、能量、设施成本、完整社会福利四组分别给出“可写/不可写”，并单列有限枚举与统计边界，见 `review/boundaries.md`。三条固定表述：

1. 共享效果只写“已测试场站/规则/情景下未观察到降低所需枪数；少数单元共享需要更大 k”。
2. 接入 k 不等于能量达标；空分母单元的 k=0 是空约束通过。
3. 只报告设施成本；完整社会福利因缺失 9 项损失参数不可计算；机制结论不写成定理。

## 7 未验证与未做

- **未验证**：`data_trace` C20（文档 facility per_connector_day 75.299726027397 vs 函数 75.297676712329，差 0.0027%）；本报告未追平。
- **未验证**：机制 `fixed_zone` 的 2 个正 Δk 实例（md 自标 UNVERIFIED，重复性不足）。
- 未重跑 split-half、未重跑 fixed-k、未扩枚举、未新增仿真、未改机制实现。
- 未补算：round4 情景块 C 曲线、seeds 6–10、feeder=336 版本、validation 4 场站、B/C/D 的 TPE0330 扩展。
- 未做总体显著性/置信区间：seeds 5/10、场站 5/9、feeder 120/336 的差异不支持。
- 未把“缺失→不 achieved”的严格语义写成预登记口径；它只是本审计的对照语义。
- `infeasible_upper_bound` 是搜索上界内未达成，不是物理不可行。

## 8 复跑

```text
python research/round5_20261031/review/run_all.py
```

该命令依次运行三个脚本，并把命令、解释器、退出码、输出 sha256 写入 `review/run_manifest.json`。
