# R8 Phase 2 独立验收报告（R8-D / task-4）

类型: 验收报告
状态: 生效（Phase 2 已在可用机器产物上完成；图表/稿件/SI/复现包尚不可验，单列 UNVERIFIED）
负责人: R8-D（独立验收者）
日期: 2026-10-31
写入域: research/round8_20261031/acceptance/**

## 0 快照与边界

- 验证时间：2026-10-31T19:16–19:36 +08:00（11:16–11:36Z）。Phase 1 复验（19:14–19:15）另见 PHASE1_ACCEPTANCE.md。
- 契约：`public_parking_events.json`，sha256 `38b1422bb95d4122565d4de70a5ef4faf35e41600019068c9c077a295ee6bdf6`，185,550 events，10 sites（与 Phase 1 相同快照）。
- 机器输出：`experiments/`（E1–E7、M，全部 mode=real_data，manifest 输入 sha=`38b1422b…`，generated 11:10–11:18Z）；`experiments_main22/`（11:16Z，含 constraint_thresholds.csv/json）；run_meta 记录 split=523 calibration/302 test、preregistered_k=1、计算预算子样本（非样本量）。
- 独立复算脚本与原始输出（本报告数字全部来自这些脚本的实际运行）：
  `acceptance/evidence/phase2_checks_a.py/.out`（E1/E2/E3）、`phase2_checks_b.py/.out`（E4/E6/M2/统计/main22/论文与图件状态）、`phase2_checks_c.py` + `phase2_summary.json`（汇总与文件哈希快照）。
- 未改动任何非 `acceptance/**` 文件；只登记问题、不修复。
- 未宣称：图表与稿件一致性、复现包完整性、Word/PDF 渲染、main22 的 M1/M3 “可判定”声称——这些目前无产物或产物为骨架，列为 UNVERIFIED。

## 1 E1 独立复算（任务要求：fit/holdout 与 coverage 789 complete site-days）

| ID | 检查项 | 结论 | 证据与观测 |
|---|---|---|---|
| X1 | coverage 与 complete_days 复算 | PASS | 从契约独立复算：10/10 场站 complete_days 与 contract.coverage 全等（总计 **789**，=E1 criteria P3 value 789）；`coverage.csv` 逐行复算一致（events、site_days、n_spaces、charging_bays=round(0.20·n_spaces)、connectors）；`fit_params.json` n_sites=10、n_days=85、n_site_days=825、n_events=185,550；criteria P2/P3/P4=pass，charge_fields=missing_data（诚实标注）。 |
| X2 | dwell/arrival fit 与 holdout 复算 | PASS | 用契约 + 同一 split 独立重算：dwell n_cal=107,852 / n_test=77,698；KS all=0.0329702448、ev=0.0314479571、ice=0.0333837784（与 fit_metrics 逐位一致）；均值/分位数在 ≤0.01 min 内一致（模型 p50/p90 用 nearest-lower-index 取次序统计量，我用线性插值，属分位定义差异，非错误）。arrival n_cal=107,329/n_test=77,396、KS=0.0487914432、mean gap=4.286005/3.219858（完全一致）。 |
| X3 | 切分合法性 | PASS | split 825=523+302，测试块规则（2 个留出场站全部日 + 17 个留出整日）零违规、与训练块无交集；E4/E2 等只读 test 块。 |

## 2 E2 k—服务率曲线与不确定性

| ID | 检查项 | 结论 | 证据与观测 |
|---|---|---|---|
| X4 | bootstrap 单位/方法/可复现 | PASS | 按相同分组顺序、`n_boot=1000, seed=20261031, percentile` 独立重算 34 个 (policy,k) 单元 × 5 指标：与 `curve_E2_summary.csv` **最大绝对差 0.0**（逐位复现）；单位=独立流（场站-日），bootstrap 次数不作为样本量。 |
| X5 | 非“重复计数幻觉” | PASS | 486 行 = 24 流 × 2 策略 × k 网格；`(stream_id,policy,k)` 无重复；每流每 k 一行；均值为流级非加权平均（CI 逐位复现即证据）；无快照行。 |
| X6 | 跨 k 可比性（固定流集合？） | **FAIL** | n_streams 随 k 递减（A 与 D 相同）：k=0–3 → 24；k=4 → 22；k=5–7 → 20；k=8 → 11；k=9–12 → 10；k=13–14 → 5；k=15–16 → **2**。原因：k 超过场站 charging_bays 的流被排除。因此高 k 点来自 2–11 条流，与低 k 点不是同一配对流集合，跨 k 差分/斜率不能解释为固定样本下的容量效应。论文/F2 必须声明该构成变化或改用固定流子集重画。 |

## 3 E3 最小性五分类

| ID | 检查项 | 结论 | 证据与观测 |
|---|---|---|---|
| X7 | 五类判定与搜索穷尽性 | PASS | 8 实例：6 physically_infeasible（k=0..物理边界全 infeasible、连续无缺口、stop=exhausted_physical_bound），2 budget_not_covered（k=0..8 全 infeasible 但 k_max=8 < 物理边界 16/14、stop=budget_cap）；0 confirmed_minimal / 0 minimality_unconfirmed / 0 missing_data。逐实例从 `search_E3.csv` per_k 行独立重放判定，8/8 与 `classes.json` 一致。 |
| X8 | 无“未穷尽即声称 confirmed_minimal” | PASS | confirmed_minimal=0，k_star 全 null；classes.json 只给声明模型内结论并注明“不是物理下界”。实例为“每场站最大充电需求 ≤20 到达连续窗口”的声明子样本（run_meta.e3_instance_construction 明示），结论适用范围限于该子样本。 |

## 4 E4 基线与信息公平

| ID | 检查项 | 结论 | 证据与观测 |
|---|---|---|---|
| X9 | 留出/配对/信息公平 | PASS | 20 条 test 流（302 留出块的计算预算子样本），7 策略 × 20 全配对、k=1（训练集预注册）；140 行全部 split=test 且 site/day 属留出规则；information=online_observable；B0/B1/B2 的 baseline_meta 定义只用可见状态（与 Phase 1 T5.1 的代码审查一致）；n_events==n_visits 全部 140 行（事件级、非快照抽样）。 |
| X10 | B1/B2 相同是否被解释 | **FAIL（未找到解释）** | 20 组中 18 组 B1/B2 的 admitted/rejected/parking/energy 完全相同；其余 2 组仅差 ICE 拒绝（B2 多拒 1 与 7 台，能量结果仍相同）；M2 中 A vs B1 与 A vs B2 的点估计/CI 完全相同。仓库内（experiments manifests、engine/README、paper/README、figures manifests）grep 未见任何说明二者等价或差异来源的书面解释。需 engine-b 明确：为何 B2 的借用门在 k=1 下 18/20 退化为 B1，否则“文献基线”贡献不可解释。 |
| X11 | 能量分母与被拒请求 | PASS | `energy_ledger.py:203-207`：被拒充电请求按 delivered=0、demand=energy 计入 including_rejected 分母；E4 中 9 行 rejected>0 全部为 ICE（EV parking failure=0），故 incl==excl 合理；E6 示例 Jolimont:2014-02-19 有 rejected=4 且 incl 分母=154.864 kWh。 |
| X12 | M2 点估计/CI 复算 | PASS | 用 E4 逐流配对差（B0−A 与代码一致）重算 ⋯bootstrap(1000, seed=20261031)：7kW 下 point=+0.1338580006、low=+0.0774695、high=+0.1929512，与存储值绝对值完全一致（见 X13 的方向问题）。 |
| X13 | M2 方向标注 | **FAIL** | `runner.py:842` 的 `diffs.append(second - first)`（first=A，second=基线）实际计算 **基线−A**，但输出标签写成 “A vs B0_FCFS”。7kW 存储 point=−0.133858 实际含义是 A 比 FCFS **高** 13.4pp；若按 “A vs 基线” 惯例读会变成 A 更差。必须在正文/SI 明确方向或改标签/符号。 |

## 5 E6 能量台账与 7 kW 不可行原因

| ID | 检查项 | 结论 | 证据与观测 |
|---|---|---|---|
| X14 | 台账恒等式与分列 | PASS | E4 140 行：delivered+gap=demand、incl 同样恒等、rate=delivered/demand；E6 24 行=6 流 ×（7/11 kW）×（feeder 1.0/0.5），offline 状态 20 infeasible/window_too_short + 4 feasible/no_charge_demand；能量分母=den_departed_requested_kwh，被拒/零需求/删失分列。 |
| X15 | 7 kW 不可行原因独立确认 | PASS | 直接从契约事件复算：对 5 条有充电需求的 E6 流，7 kW 下 required_min=energy/7*60 > dwell 的车辆数分别为 10/13、12/14、10/10、12/12、13/14；11 kW 下仍为 8/13、11/14、9/10、10/12、12/14。即 window_too_short 属实，且不只是 7 kW 问题（11 kW 也不够）。E6 的 feasible 行恰为 no_charge_demand 的流。 |

## 6 M1/M3 与统计单位

| ID | 检查项 | 结论 | 证据与观测 |
|---|---|---|---|
| X16 | M1/M3 缺数据是否诚实 | PASS | M1：10 条留出流全部 k_A=k_B=null（k=0..charging_bays 三约束无可行 k），status=missing_data、pairs_total=10、n_pairs=0；M3：8/8 离线实例不可行，status=missing_data；E5 `k_min_feasible` 全空一致。未伪造数字。 |
| X17 | 统计单位/配对/非快照 | PASS | 确认性 E4 n=20 独立留出流、同流配对重放（同 stream_id 的 stream_hash 在 7 策略间一致）；E2 n≤24、E5 n=10、E6 n=6（均声明为计算预算子样本，不是样本量）；bootstrap n_boot=1000 未当作 n；E4 n_events==n_visits。 |

## 7 main22（22 kW 情景）

| ID | 检查项 | 结论 | 证据与观测 |
|---|---|---|---|
| X18 | 22 kW 情景与“可判定 M1/M3” | **FAIL** | `experiments_main22/` 已生成（11:16Z，manifest 输入 sha=`38b1422b…`）：E1/E3/E5/E7 与 7 kW 版本逐字节相同（合理，硬件无关）；E2/E4/M 有差异；**E6 与 7 kW 版本仅差 3 个元数据列**（capacity_source/scenario_layer/scenario_label），`connector_kw/feeder_kw` 仍为 7/11 kW、offline_status 与全部数值完全相同 → E6 实际未在 22 kW 下重跑；M1/M3 仍为 missing_data（不是“可判定”）；新增 `constraint_thresholds.csv/json`（A：parking_service_k=0 的流 23/24；charging/energy/three_constraints 23/24 no_k）但未整合进 M 汇总。结论：22 kW 机制目前只改了仿真侧（E2/E4/M2），E6/M1/M3 未落实；不得宣称“22 kW 下 M1/M3 可判定”。 |

## 8 图表、稿件、SI、复现包（尚不可验）

| ID | 检查项 | 结论 | 证据与观测 |
|---|---|---|---|
| X19 | F1–F7 与机器结果一致 | **UNVERIFIED** | 仅有 `figures/_demo/F1–F7.png`（status=demo，10:49Z）；无真实图 PNG、无 `figures/FIGURES.json`（--real 构建前置缺失），故无法核图↔机器文件。 |
| X20 | 稿件/SI 与机器输出对应 | **UNVERIFIED** | 现有 `*_rev5.docx` 为 **skeleton 构建**（manifest mode=skeleton）：正文含 26 个 SKELETON、14 个 [UNRESOLVED]、7 个 “NOT EMBEDDED”，`evidence_rev5_main.json` records=[] 且有 13 条 “missing experiment output”；构建时间 18:55Z 早于最终机器输出（19:10–19:15Z）。不可作为结果一致性证据。 |
| X21 | 复现包 | **UNVERIFIED** | `research/round8_20261031/repro/` 不存在；engine/experiments 可运行但无打包/一键复现清单。 |
| X22 | Word/PDF 渲染 | **UNVERIFIED** | 只有 `rev5_main_skeleton.pdf`、`rev5_si_skeleton.pdf`；无真实稿 PDF/页数/版式核验。 |

## 9 最高优先级问题（3 项）

**P2-1 E2 曲线跨 k 流集合漂移（方法/图件风险）**
- 事实：n_streams 24→22→20→11→10→5→2（k=0→16）；k≥8 的点基于 ≤11 条流，k=15/16 仅 2 条；bootstrap 与均值本身方法正确（逐位复现），但**跨 k 比较不是固定样本配对**。
- 影响：F2 曲线/论文中“服务率随 k 变化”的斜率、平台位置可能被流构成变化混淆；高 k 点 CI 也基于极少流。
- 建议：改用固定流子集（如 charging_bays≥16 的站点集）重画，或显式标注每个 k 的 n 与构成；不要用高 k 点做强结论。

**P2-2 M2 方向标注与 B1≈B2 未解释（数字解释风险）**
- 事实：M2 代码 `second - first` 实际是基线−A，标签却是 “A vs B0_FCFS”；7kW 存储 −0.1339 真实含义为 A 优于 FCFS 13.4pp。另：B1/B2 在 18/20 组完全相同、能量 20/20 相同，M2 中 A-B1 与 A-B2 的 CI 完全一致；仓库无书面解释。
- 影响：正文若按标签方向写会结论反号；B2 作为“文献基线”的独立贡献无法说明。
- 建议：M2 明确写出 “baseline − A”，或统一改为 A−baseline；engine-b 补 B1/B2 等价性分析（为何 k=1 下借用门 18/20 不触发）。

**P2-3 main22 “22 kW / 可判定 M1/M3” 未落实（声称与产物不符）**
- 事实：main22/E6 仍为 7/11 kW 网格与相同数值（仅元数据列改 22 kW 标签）；M1/M3 仍 status=missing_data；constraint_thresholds.csv/json 新增但未进入 M 汇总。
- 影响：若按 Lead 计划把 main22 作为“22 kW 决策性结果”，当前产物不支持；投稿会构成声称-证据不匹配。
- 建议：E6 用 connector_kw=22 重跑并重算 M3；把 constraint_thresholds 明确为 M1/M3 的替代口径并写进 manifest/正文，或撤回“可判定”表述。

## 10 未覆盖 / 局限

- Phase 2 的图表/稿件/SI/复现包/Word-PDF 为 UNVERIFIED：等 figure-c 产出真实图与 --real 构建后重验（本报告已记录当前状态与缺失前置）。
- E2/E4/E6 的独立复算使用 engine 的 split/仿真输出为输入；我独立复算了统计与判定逻辑，但没有重跑 workbench 仿真本身（除 E1 分池与 E6 窗口判定为直接由契约重算）。
- E3 为 ≤20 到达的声明子样本；其“物理不可行”结论仅限声明模型与子样本，不代表完整场站-日。
- M1/M3/M2 的 missing_data 是如实结果；不等于数据缺失或结论无效，但不能写成正向发现。

## 附录：证据文件

| 文件 | 内容 |
|---|---|
| `acceptance/evidence/phase2_checks_a.py / .out` | E1 复算、split 校验、E2 bootstrap 逐位复现、E3 分类重放 |
| `acceptance/evidence/phase2_checks_b.py / .out` | E4 留出/B1B2/分母、M2 复算、E6 窗口检查、统计与 main22/论文图件状态 |
| `acceptance/evidence/phase2_checks_c.py` | 汇总脚本（生成 phase2_summary.json） |
| `acceptance/evidence/phase2_summary.json` | 关键数字、文件 sha256 快照、main22/论文/图件状态 |
| `acceptance/acceptance_phase2.json` | 逐条机器可读结论（id/结论/证据命令/证据路径/时间） |
