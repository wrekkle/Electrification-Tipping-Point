# R8 Phase 3 独立验收报告（R8-D / 分析产物、情景账本、统计口径）

类型: 验收报告
状态: 生效（结论只覆盖本轮实际读到的文件；未建成的 rev6 稿件不验）
负责人: R8-D（独立验收者）
日期: 2026-10-31
写入域: research/round8_20261031/acceptance/**

## 0 快照与方法

- 验证时间：2026-10-31T19:4x–19:58 +08:00。证据快照 captured_local=2026-10-31T19:56:07，见 phase3_results.json → snapshot（31 个文件 sha256/bytes/mtime）。
- 输入：契约 sha256 = 38b1422bb95d4122565d4de70a5ef4faf35e41600019068c9c077a295ee6bdf6（185,550 events / 10 sites）；窗口导出 sha256 = c22f559928fe2f1ee674da2c77b941a38e90136542e3cd81e3f2c8ab3aa29ecf（236,819 行）。
- 独立复算脚本（本报告全部数字来自其实际运行，输出落 acceptance/evidence/）：
  - phase3_checks.py → phase3_checks.out + phase3_results.json：窗口对账、扫描线占用、22 kW 理想上界、需求-停留表、面积选择、情景能力探针、M2 流 bootstrap、站点簇 bootstrap、B1/B2 逐列比较、脚本编译检查。
- 只写 acceptance/**；未运行 analysis/ 脚本本体（会覆盖非验收文件），改为在内存中独立重算并用 compile() 检查三个脚本语法。
- 未验：rev6 稿件（未构建，按要求不验）；experiments_declared22/ 仅作旁证引用，未作为独立验收对象展开。

## 1 analysis/ 产物

### 1.1 窗口导出 → 契约对账（任务 1a）

| ID | 检查 | 结论 | 证据与观测 |
|---|---|---|---|
| A1 | 236,819 − 24→10 面积选择 − 2 条 1900-01-01 离场 = 185,550 | **PASS** | 独立重算：窗口 236,819 行 / 24 个 AreaName；选中 10 区 **185,552** 行；其中 2 行缺离场时刻（dep_local=1900-01-01T00:00:00、dwell_min 空）→ 185,550 = 契约事件数 = 唯一 event_id 数；逐场站差额仅 Victoria Market 1、Hyatt 1，其余 0；未选 14 区 51,267 行。两条坏行：Victoria Market 2014-03-14T09:40:32（bay "4,182"）、Hyatt 2014-01-15T18:37:13（bay "690"）。证据：phase3_checks.out A 段；phase3_results.json → A_reconcile。 |
| A2 | 10 场站扫描线：任一时刻同时占用 ≤ n_spaces，超容量分钟 = 0 | **PASS**（实质口径） | 干净扫描线（按同一时间戳成组、净增减）10/10 场站 max ≤ n_spaces，超容量分钟 0.0：Queensberry 67/82、Jolimont 49/58、Victoria Market 35/35、Southbank 63/72、University 40/40、Hyatt 15/15、Drummond 33/33、Princes 12/12、Titles 17/17、West Melbourne 18/18。 |
| A3 | site_audit.csv 的并发列与 FIT_FOR_MODEL §2 举例自洽 | **FAIL（产物自相矛盾）** | site_audit.csv 的 max_concurrency/peak_over_capacity 用“同时间戳先处理到达、后处理离场”的事件排序，产生瞬时虚高：Victoria Market 40>35、Hyatt 18>15、Drummond 34>33、Princes 15>12、Titles 18>17（而 minutes_above_capacity 全部 0.0，内部矛盾）。该虚高不是 FIT §2 所称“1 条缺离场记录造成的假象”：剔除 2 条 1900 离场行后，瞬时法仍得 40；正确区间占用只有 35 且超容量 0 分钟。另 site_audit.events 仍按窗口行计数（VM 24,892、Hyatt 14,296），比契约多算 2 条已剔除坏行（契约 24,891/14,295）。 |

### 1.2 22 kW 理想上界（任务 1c）

| ID | 检查 | 结论 | 证据与观测 |
|---|---|---|---|
| A4 | P=22 下 min(E, P·T) 在 E4 20 条留出流复现 991.891 kWh 与 80/137 | **PASS（逐位）** | 独立从契约事件重算：20 流、137 个充电请求、需求 1,891.028 kWh、理想交付 **991.891 kWh**、会话失败 **80/137**；与 ideal_bound_streams.csv 20/20 行一致（每流 delivered/demand/fail/n_requests 全等，容差≤0.001），与 evidence_at_n_spaces.csv 的 A 策略 20/20 行一致，JSON 汇总 991.9 kWh / 1891.0 / 80 一致；20 条流的事件数与 E4 n_events 20/20 相等；证据 A/B 两策略逐行相同且 rejected_at_gate=0。 |

### 1.3 需求-停留表与面积选择（任务 1d/1e）

| ID | 检查 | 结论 | 证据与观测 |
|---|---|---|---|
| A5 | demand_dwell_matching.csv 复算 | **PASS** | 7 个 E0 档（2/4/6/8/10/14/20 kWh）全部复现：n=6,588；需求=档位×6588；理想交付、失败数与 5% 标准判定完全一致（CSV 保留 1 位小数，按此容差比较；例如 14 kWh：delivered 52,716.7、失败 4,017/6,588）。 |
| A6 | FIT_FOR_MODEL §4 “bays≥12 且 events≥4,000” 唯一给出 10 站，且与 area_ranking.csv 一致 | **PASS（规则可由数据复现；注意其为“共同特征”而非形式化选择证明）** | 从窗口导出独立按区计数：恰好 **10** 个区满足 bays≥12 且 events≥4,000，与契约 10 站集合完全相同；边界值：Princes Theatre 12/13,115 入选、West Melbourne 18/4,538 入选、Courtney 14/3,021 未入选、Rialto 7、RACV 6 未入选。area_ranking.csv 24 行与独立复算 events/bays 全等；10 站占窗口事件 78.35%（185,550/236,819，与 §4 的 78% 一致）。另：更宽松的旧规则（bays≥8 & events≥1,500 再取事件前 10）也给出同一 10 站，说明该判定并非唯一可能规则；PROVENANCE.json 中无形式化 site_selection_rule 字段（null），FIT §4 只是描述共同特征。 |
| A7 | analysis 脚本语法/可执行性 | **PASS（仅静态）** | fit_for_model.py、audit2.py、audit3.py 全部 compile 通过；未执行（会写 analysis/ 输出，超出验收写入域）。 |

## 2 SCENARIO_LEDGER §1 声明 vs 实际运行（任务 2）

| ID | 检查 | 结论 | 证据与观测 |
|---|---|---|---|
| B1 | “7 kW 与 main22 运行实际使用 charging_bay_share=0.1 / max_connectors_per_site=4 / feeder_share=0.5，而不是契约 20% / connectors=bays / feeder=bays×kW” | **FAIL（声明被证据反驳）** | run_meta 的 parameters 确实写着 0.1/4/0.5（7kW 与 main22 同；main22 另有 forced_overrides={connector_kw:22, feeder_kw_per_connector:22}），但**这些默认值未被应用**：runner.site_capability 只在站点缺字段时使用默认值，契约 10 站四字段齐全 → 实测能力 derived_fields=[]、charging_bays=16、connectors=16、feeder=112（7 kW）；即使显式 set_scenario(share=0.1,max=4,feeder=0.5) 仍是 16/16/112；仅当删除契约字段才得到 8 床/4 枪/14 kW。输出侧同证：E3 physical_bound = 契约充电位数（Queensberry 16、Southbank 14、University 8…，若 0.1 份额应为 8/7/4）；E2 University 在 k=8 仍有逐流结果（0.1 份额下 University 仅 4 个充电位，不可能 k=8）。engine 自己的 experiments_declared22/hardware_audit.json 结论原文：“7 kW 与 main22 运行并未应用 charging_bay_share=0.1/max_connectors_per_site=4/feeder_share=0.5；…main22 只强制了 connector_kw=22 与 feeder=connectors*22”。结论：SCENARIO_LEDGER §1 的“实际 0.10 / 4 封顶 / 0.5 馈线”不成立；run_meta 的参数块记录的是未被采用的默认值（元数据误导）。 |
| B2 | main22 的强制 22 kW / feeder=connectors×22 是否真实生效 | **PASS** | experiments_main22/E6/energy_E6.csv 现为 6 行、connector_kw=22.0、feeder_kw=22.0、e6_mode=regime_forced_power（对照 7 kW 的 24 行 7/11 kW×feeder 1.0/0.5 网格）；main22 E4/E2 scenario_label 均为 scenario_charging_layer_main22_22kW_not_observed，M2 幅度也与 7 kW 不同（见 C1）。 |

### 2.1 论文文本中的 20% 与硬件描述

| ID | 检查 | 结论 | 证据与观测 |
|---|---|---|---|
| B3 | content_rev5.py / rev5 docx 是否出现 20% | **PASS（出现：是）** | content_rev5.py 8 处：行 24、147、201、268、275、339、449、555；rev5 docx 正文出现 7 次“20%”（如“Under the declared 20% charging-bay scenario at 22 kW…”）。声明 20% 份额与契约站点数一致（charging_bays=round(0.20·n_spaces)）。 |
| B4 | 论文对“实际使用硬件”的描述是否与运行一致 | **FAIL** | rev5 py 行 270–272 与 docx 同句称：“The two declared layers used in this paper are 7 kW and 22 kW per connector at 50% feeder share and at most four connectors per site”；实际运行既无 4 枪封顶也无 50% 馈线（feeder=connectors×7 或 ×22，connectors=charging_bays 最大 16）。论文行 448–450 又称“0.1 字符串与 20% 冲突、评价网格按契约计数”——“按契约计数”与实际一致，但“0.1 份额”只是未采用的默认字符串，不是实际硬件；两处叙述合起来仍会误导读者。该错误与 SCENARIO_LEDGER §1 同源。 |

## 3 统计声明（任务 3）

| ID | 检查 | 结论 | 证据与观测 |
|---|---|---|---|
| C1 | M2 流 bootstrap：seed=20261031、1000 次，复现存储 CI | **PASS（6/6 逐位）** | 按 E4 文件顺序构造 baseline−A 逐流配对差，random.Random(20261031)、1000 次重抽样、线性插值分位：7 kW B0−A point −0.1338580006 [−0.1929512134, −0.0774694734]；B1/B2 0.0030313722 [−0.0002565338, 0.0094741668]；main22 B0−A −0.2276386265 [−0.3217065148, −0.1421155447]；B1/B2 0.0076656118 [0.0, 0.0223707707]。与 m_summaries.json 6 项全部 abs diff < 1e-12。 |
| C2 | 站点簇 bootstrap（9 簇）对 B0_FCFS−A 仍排除 0 | **PASS** | 20 条流分布在 9 个 site 簇；按簇有放回重抽、池化簇内流差：7 kW point −0.133858，CI [−0.176477, −0.071889]；main22 point −0.227639，CI [−0.297179, −0.133224]；两者均同号且不含 0（负值 = A 更好）。 |
| C3 | B1 与 B2 在 20/20 流上能量与容量指标完全相同 | **PASS（能量/容量指标成立；但解释注有误）** | 能量指标 7 个（energy_service_rate_incl_rejected、delivered/demand/gap 及其 incl 版本、energy_service_rate）20/20 相同；容量指标 6 个（capacity_only_unmet_rate、capacity_unmet_rate、num_capacity_unmet_requests、service_capacity_unmet_rate、feasible_3constraints/raw）20/20 相同；7 kW 与 main22 两个 regime 均如此。**但** M2 note 与 B1/B2 解释称“ICE 停车失败均 0/4643”不符：B2 在 2 条流上有 8 次 ICE 停车失败（B1 为 0，分母均 4,643），admitted/rejected/energy_cat_rejected/parking_service_rate 也在这 2 条流不同；能量与容量指标不受影响。 |

## 4 结论与优先级

- 任务 1 的独立复算几乎全部通过：窗口对账 A1、扫描线超容量 A2、22 kW 理想上界 A4（991.891 kWh、80/137 逐位复现）、需求-停留 A5、面积选择 A6、脚本静态 A7。
- 唯一任务 1 FAIL：**A3** site_audit.csv 的 max_concurrency/peak_over_capacity 列与“超容量分钟 0”矛盾；FIT_FOR_MODEL §2 把 Victoria Market 40>35 归因于 1 条缺离场记录，该归因被复算否定（剔除后瞬时法仍 40；正确区间扫描 35/0）。site_audit.events 还多计 2 条已剔坏行。
- 任务 2 **整体 FAIL**：SCENARIO_LEDGER §1 的“实际用了 0.1/4/0.5”被 runner 能力解析、E3 physical_bound、E2 University k=8、engine 自带 hardware_audit 四处独立证据反驳；run_meta 参数块与论文行 270–272 同源错误。main22 强制 22 kW/feeder 22 确为真（B2）。
- 任务 3 全部 **PASS**：M2 流 bootstrap 6/6 逐位复现；9 站点簇 bootstrap 两个 regime 均排除 0；B1/B2 能量与容量指标 20/20 相同（但“ICE 失败均 0”的注是错的，B2 有 8 次）。
- 未验证：rev6 稿件未构建（按要求不验）；experiments_declared22/ 只作旁证，未独立验收其全部数字。

## 附录：证据

| 文件 | 内容 |
|---|---|
| acceptance/evidence/phase3_checks.py | 本报告全部复算/探针（窗口对账、扫描线、理想上界、需求-停留、面积选择、能力探针、bootstrap、B1/B2 列比较、脚本编译） |
| acceptance/evidence/phase3_checks.out | 上述脚本原始输出 |
| acceptance/evidence/phase3_results.json | 逐项结果 + 31 个文件 sha256/bytes/mtime 快照（contract 与 window sha 亦在 snapshot） |
| acceptance/acceptance_phase3.json | 机器可读逐项结论（id/verdict/command/observed/evidence） |
