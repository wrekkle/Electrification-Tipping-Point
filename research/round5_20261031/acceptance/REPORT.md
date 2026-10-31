# 第五轮独立验收报告（task-3，验收者 verifier）

- 日期：2026-10-31
- 角色：独立验收者（不采信执行者自述；关键结论均用自跑命令或原始文件复算）
- 共享任务：task-3（claim 于 revision 1 → in_progress；完成后 complete）
- 写范围：本目录 research/round5_20261031/acceptance/**。未改他人产物、未改 research 既有文件、未碰 research/collection、未改 Word。
- 唯一例外（已披露）：按任务要求原样复跑 MATLAB 两个脚本与文献核验脚本，会重写其固定输出位置（matlab/static_run、matlab/indep/out、matlab/logs、lit/citations_m18_m06_m07.json）；复跑前后语义一致，见 §4、§3。

## 0 判定总表

| # | 验收项 | 判定 | 一句话依据 |
|---|---|---|---|
| 1 | P0 哈希解释 | **PASS**（结论）；文字数值有误；旧流真实差异 UNVERIFIED | 自跑 25 流 workers=1/8：确定性、25/25 复现第四轮、22/25 复现第三轮、差异恰 3 条；排序/重编号不能复现；旧源码/旧原始记录未保留 |
| 2 | REF 配置可比与成本 | **PASS** | 1025 行 demand_hash 全同、5 项服务/成本指标全同、仅 8 行 peak 不同；成本差 0.00272% 与 32.0+15804.4/365 精确复算一致 |
| 3 | 文献引用 | **PASS** | 38/38 PASS；另抽 10 条上下文核对全部成立；M18 关键词扫描 kW/kWh/charging power/queue/waiting time/service level 命中 0 |
| 4 | MATLAB 与可靠性 | **PASS** | MATLAB static_verify ×4、indep_verify ×3 全 exit 0，145/145；unittest 17/17 与 362/362 全 OK |
| 5 | 风险与冻结 | **PASS**（冻结/PDF/Word）；**FAIL**（docs 未收口） | 5 个冻结哈希全同、冻结后无新增 PDF/Word；docs/TODO.md 与 PROGRESS.md 仍写“M18 阅读摘要级、逐节对照未做”，与第五轮交付矛盾 |
| 6 | 机制最小反例 | **PASS** | 独立实现复现 16 个单调性反例；取最小 2 例固定轨迹重放，与执行者实现逐 k 相等；判定为**真实路径依赖反例，不是实现错误** |

## 1 P0：第三/四轮 3 条 demand_hash 差异

### 1.1 执行者脚本与我自跑

| 命令 | exit | 要点 |
|---|---|---|
| C:\anaconda\python.exe research/round5_20261031/repro/verify_repro.py | 0 | streams 25；deterministic true；worker_invariant true；r4_match 25；r3_match 22；stale 恰 3；changed_sources 2 |
| 我自写并运行 25 流复跑（不是读执行者 JSON）：run_cost_curve.py --lots TPE0008,TPE0401,TPE0610,TPE0695,TPE0330 --seeds 1-5 --fixed-k 0 --rule dedicated_by_type --p-ev 0.1 --q-need 0.36 --scenario-model independent --feeder-kw 120 --cost-file ... --workers 1 与 8；--out acceptance/indep_rerun_w1.json / indep_rerun_w8.json | 0/0 | 25 行/次；w1 与 w8 全同；与执行者 repro_r3params_s5_k0.json 全同；对第四轮 25/25、第三轮 22/25；差异集合 {TPE0330/s2, TPE0401/s2, TPE0695/s3} |

证据：acceptance/verify_repro.log、acceptance/indep_rerun_w1.json、acceptance/indep_rerun_w8.json、acceptance/independent_repro_check.py、acceptance/independent_repro_check.log。
说明：verify_repro.py 本身只比对已有 JSON，不执行生成；我的复跑补齐了“真跑生成器”这一环，结论不依赖执行者产出的 JSON。

### 1.2 版本与时间线（独立读 meta/mtime）

- 两份结果 meta 的 source_sha256 只有两项变化：traffic_gen.py 8c47f55f… → d29baf51…，run_cost_curve.py 47e4fedb… → 3b2241c2…；其余 6 个源文件两轮相同。
- 当前文件实测哈希 = 第四轮 meta 值（d29b…、3b22…）。
- mtime（本地）：第三轮 main_A_pi0_ref_s10.json 13:26:25 → traffic_gen.py/run_cost_curve.py 14:07:52 → 第四轮 scenario_REF_A_s5.json 14:14:15，与报告叙述一致。
- 两轮同 (lot,seed) 的 p_ev/q_need/horizon/start_hour/rule 相同；feeder 120 vs 336 不进入需求生成（见 §2）。
- 3 条差异流逐字段核对：仅 demand_hash、traffic_hash、mean_occupancy_rate 不同；arrivals、ev_arrivals、initial_occupancy_n、demand_energy_kwh_total 等全部相同；其余 22 条流所有字段全同。

### 1.3 排序/重编号不可复现、旧证据未保留

- 自写探针（acceptance/independent_stale_probe.py，exit 0）：对 3 条流各试 22 种排序/重编号变体（含时间/ID/EV/停留/能量/复合键、正倒序、规范化重编号、200 次随机置换），0 命中第三轮哈希；当前记录列表本身已是按 (time,id) 规范化顺序（multiset 哈希 = as_generated 哈希）。
- 旧版源码：全仓库只有一个 traffic_gen.py（d29b…）；git 有仓库但**无任何提交**（git log 报 “does not have any commits yet”），故旧版源码未保留；round2 的 pre-fix 快照文件 SHA-256=52dabaad…，不等于第三轮 8c47…。
- 旧原始车辆记录：旧哈希 c922d50ed5db 只出现在 round3 的若干结果 JSON（派生哈希），未发现旧版原始 arrivals 记录文件；无法重建第一条车辆级差异。
- 因此“旧版源码与原始记录未保留、第一条实际差异 UNVERIFIED”的表述与证据一致。

### 1.4 发现（不影响结论，但文字需更正）

- research/round5_20261031/repro/REPORT.md §1 写 mean_occupancy_rate 差 “1.8e-9~7.3e-7（相对约 1e-9~1e-6）”。实测三条流绝对差 7.3439e-7、2.9079e-6、1.7938e-6；相对差 1.0669e-6、3.4090e-6、8.7483e-6。**报告的绝对/相对区间都写错（低估约 4 倍）**；差异仅 3 个字段、结论“浮点/顺序层面等价”不变。
- 无法从现有证据判定三条旧流的具体车辆级差异（旧源码/旧记录未保留）→ 该项保持 UNVERIFIED，符合执行者自我标注，不据此扣 PASS。

## 2 REF 配置可比性与成本

| 命令 | exit | 要点 |
|---|---|---|
| python research/round5_20261031/config/verify_config.py | 0 | rows 1025；service_metric_diffs []；peak120 120.0；peak336 140.0；cost_func 75.29767671232877 |
| 自写 acceptance/independent_config_check.py | 0 | 独立复算见下 |

- 1025 行（5 场站×5 seed×41 k）键完全对应；demand_hash 1025/1025 相同。
- 服务/成本五项（unserved_charge_events、unserved_charge_energy_kwh、facility_cost、unmet_no_connector_events、mean_occupancy_rate）1025 行 0 差异。
- 功率：仅 8 行 peak_power_kw 不同，全部为 TPE0330 k=36–40（s2/s3/s5）；feeder=120 侧 8 行峰值恰为 120.0（被截），feeder=336 侧最高 140.0（<336，对已验证集合非约束）。“8/1025、峰值 140、120 为紧约束”与 config REPORT 一致。
- 成本：costs.facility_cost(1, days=1) = 75.29767671232877 = 116792.62/10/365 + 43.29969863013699；文档值 75.29972602739726；差 0.00204931506849，相对 2.7216e-5 = 0.0027216%（报告中 0.0027% 成立）。文档值精确等于 32.0 + 15804.4/365；对应旧取整口径（capex≈116800、维护年额 15804.4），非公式/寿命/天数错误。
- 代码质量小问题：verify_config.py 输出字段 feeder120_vs_336_demand_identical 写成 not failures or True（恒真，无判别力）；该字段不作为我的验收证据，我用独立脚本复算。

## 3 文献与索引

| 命令 | exit | 结果 |
|---|---|---|
| python research/round5_20261031/lit/verify_lit_citations.py | 0 | verified 38，failed 0（M18 14 / M06 12 / M07 12） |
| 自写 acceptance/lit_spotcheck.py | 0 | 10 条引用上下文全部命中；M18 关键词扫描 0 命中 |

- 脚本只做“needle 是否在该页文本”的机械核对，不判断语义支持；我另取 10 条读上下文：
  - M18 p15 “No data was used…”（无实证数据）、p5 建桩成本系数 k、p4 双寡头差异化运营商、p6 GNB 议价；
  - M06 p24 “without incorporating factors such as charging power and grid load”（明确排除功率/电网）、p7 Rule 1/2 准入规则、p1 80.31% 节时（作者报告，B 级）；
  - M07 p8 Pm 作为请求功率属性、p11 冲突概率阈值 ρmax、p15 杭州与 36 RMB、p8/10 D-DRA/R-DRA。
  全部与对照文档论断一致。
- M18 独立关键词扫描（全文 17 页）：kW=0、kWh=0、charging power=0、queue=0、waiting time=0、service level=0；“capacity”仅 1 次在 p3 文献综述；“energy”4 次为引言/参考文献，非建模变量。支持“M18 无功率/服务约束、无实证数据”。
- reading-log：M18 read_status=全文略读，证据为 notes/M18 笔记 + 本轮 fulltext_comparison（两文件均存在）；笔记首段亦写 p1–p15 全文略读。一致。
- 索引：literature/index.json 与 INDEX.md 均含 M18（read_status 全文略读、sha256 与 PDF 一致、read_evidence 两文件 exists=true）；mtime（15:26:57）晚于 reading-log（15:26:57.5），可认定索引已重建。
- 运行 verify_lit_citations.py 会重写 lit/citations_m18_m06_m07.json（当前 38 条，SHA-256 f37e20a5…），属脚本固定输出，非我另写内容。

## 4 MATLAB 与可靠性

### 4.1 MATLAB：自跑复现（不是只读报告）

| 命令（均 -batch） | 次数/exit | 复跑结果 |
|---|---|---|
| matlab.exe -batch "addpath('.../matlab/scripts'); static_verify" | ×4，均 0 | ALL STATIC CHECKS PASSED；comparison_summary all_pass=true；441×18、0 失配、max_abs 4.547e-12、max_rel 2.133e-12 |
| matlab.exe -batch "addpath('.../matlab/scripts'); indep_verify" | ×3，均 0 | 145 pass, 0 fail；indep_checks.csv 145 行 pass=1 |

- 环境：MATLAB 26.1.0.3203278 (R2026a)，license=1（日志/摘要实测）。
- 确定性：indep_checks.csv、raw_cost_matrix*.csv、*_diff_by_column.csv 跨次哈希完全相同；comparison_summary.json、legacy/corrected summary.json、indep_summary.json 仅 generated/时间戳字段不同（忽略时间键后逐字段相等，runA 与复跑对照：legacy=true、corrected=true）。
- REPORT 自称的边界（只对齐静态 PREI、B 组是契约级公式重写、未跑 Simulation 类）与脚本内容一致；平台标签硬编码 “octave”（REPORT §2.5 已披露），平台证据应以 logs 的 version/license 行为准。
- 证据：acceptance/matlab_static_verify_console*.log、acceptance/matlab_indep_verify_console*.log、acceptance/matlab_outputs_run1.sha256、acceptance/matlab_outputs_run2.sha256、acceptance/runA_legacy_summary.json、acceptance/runA_corrected_summary.json。
- 写范围说明：复跑会重建 matlab/static_run/**、matlab/indep/out/**、matlab/logs/*（脚本设计如此）；内容语义未变，哈希变化仅来自时间戳。

### 4.2 可靠性（unittest）

| 命令 | exit | 结果 |
|---|---|---|
| python -m unittest apps.parking_lab.workbench.tests.test_round5_safety -v | 0 | Ran 17 tests，OK |
| python -m unittest discover -s apps/parking_lab/workbench/tests -p "test_*.py" -t . | 0 | Ran 362 tests，OK（与 safety REPORT 的 345+17=362 一致） |

- apps/parking_lab/workbench/experiments.py 当前 SHA-256=a7aff1d4…（REPORT 修复后值），before 快照=9158d0e4…（与 REPORT 一致）；inspect_output/fingerprint_output/write_output(force=) 均在源码中，测试文件存在。
- 未复跑 safety 的 probe_concurrency/probe_crash_retry/probe_manifest 三项探针（任务未要求；其“修复前 exit 1 是探针自身口径”一说我未独立验证 → UNVERIFIED）。固定输入 compare 的 equal=true 亦未复跑。

## 5 风险与冻结

- 冻结文件 5/5 哈希与 lit/frozen_sha256_before.txt 当前完全一致（见 acceptance/frozen_and_safety_check.json）：M18/M06/M07 三个 PDF、round4 comparison.md、投稿版 docx。
- 冻结快照 mtime 15:14:19；papers/、main_paper/、paper/ 下无任何 PDF/docx 晚于该时刻。今天被改动的 PDF 只有 M18（14:56:55，早于冻结），属用户提供入库，不是冻结后修改。
- Word 稿件 mtime 2026-10-29 09:49:27、SHA-256 04bda311… 与冻结值一致，未改。
- **docs 一致性 FAIL（缺失，待 Lead 收口）**：
  - docs/TODO.md 第 38 行 U20（2026-10-31 更新）仍写“M18…阅读仍摘要级，逐节模型对照未做”；docs/PROGRESS.md 第 31 行写“仅核首页/摘要/末页，阅读仍摘要级，逐节模型对照未完成”。这与第五轮 lit 的 38 条全文对照、reading-log 全文略读、M18 笔记直接矛盾。
  - TODO 中没有第五轮验收/交付条目（仅第三/四轮记录）；PROGRESS 的“N1/M18 全文未取得”仍是第四轮状态。
  - 判定：不是研究文件错误，而是管理入口未同步。若 Lead 不在本轮更新，读者会得到错误阅读状态。

## 6 机制最小反例（只读核对，不改机制实现）

来源与记录位置：

- 实现：research/round4_20261031/mechanism/shared_capacity_mechanism.py 的 monotonicity_check()（第 179–193 行）统计“π0 的 ICE 停车失败率随 k 增大而下降”的实例。
- 记录：shared_capacity_mechanism.json#summary.monotonicity_pi0_ice = {instances_checked:3456, non_monotone_instances:16}；文档：shared_capacity_mechanism.md 第 55 行。**原记录只有计数，没有 16 个实例的身份列表**，这是记录缺口。

我的独立核对（只读导入模块网格 + 自写模拟器，输出 acceptance/mechanism_counterexamples.json）：

- 独立实现按文档规则重跑 3456 实例，得到 **16** 个违反单调性的实例，与存储计数一致；完整 16 条身份已由我落盘（原 JSON 无此列表）。
- 取最小/最简单 2 例（N=6、dwell 5/5、rate 1.6、offsets EV 早/ICE 晚、seed=1；q_need=0.1 与 0.3）：
  - k=0 → k=1：普通位 6→5，ICE 失败 8/24 → 7/24（率 0.3333→0.2917），EV 回流普通位次数 8→2；
  - 我的独立模拟器与 scm.simulate 在全部 k 上逐值相等（两例均 true）；
  - 交换同刻事件 tie-break（EV 优先）后，k=0→1 的下降仍存在（同样 8→7），排除 tie-break 假象。
  - 固定轨迹原文见 acceptance/mechanism_counterexamples.json 的 picked_two[].trajectory；复算脚本 acceptance/mechanism_recheck.py，exit 0。
- **判定：真实路径依赖/反例成立，不是实现错误。** 机理：k 增大时带枪位增加，EV 回流普通位从 8 次降到 2 次，腾出的普通位多于普通位减少 1 个的损失，ICE 失败反而少 1 次；这是“EV 可回落普通位 + 1 桩=1 枪=1 带枪位 + 离散占位/拒绝顺序”共同造成的非单调，不是浮点或代码 bug。
- 准确条件表述：**在 π0 允许“无空带枪位的 EV 回落普通位”、ICE 仅能停普通位、k 增大同时使普通位 N−k 减少的离散模型中，π0 的 ICE 失败率不必随 k 单调不减**（最小反例 N=6、EV 份额 0.4、q_need=0.1、dwell 5、rate 1.6/slot、EV 提前/ICE 延后、seed=1，k=0 与 k=1）。因此该引理不成立，“共享不省枪”不能经该引理升级为定理；与 md 第 55 行“只能写枚举全支持、不能写已证明”的结论一致，不构成对第三轮枚举结果的否定。
- 未验证：16 个实例与执行者“未逐一人工核验”的自述一致，我只逐例复算了其中 2 个；其余 14 个仅由我的独立实现计数命中，未逐一给轨迹证据。原记录无身份列表，无法与执行者逐例对照 → 该身份对照标 UNVERIFIED。

## 7 未通过 / 不能验收清单

1. **docs/TODO.md、docs/PROGRESS.md 未同步第五轮事实（FAIL，管理入口）**：M18 仍写“摘要级/逐节对照未做”，与 lit 交付矛盾；TODO 无第五轮条目。需 Lead 更新后才算收口。
2. **repro/REPORT.md 的 occupancy 差异区间写错（文字错误，不影响结论）**：应为 abs 7.34e-7~2.91e-6、rel 1.07e-6~8.75e-6。
3. **旧流第一条车辆级差异不可重建（UNVERIFIED，执行者已标注）**：旧 traffic_gen 源码与旧原始记录未保留，git 无提交。
4. **全排列空间未穷举（UNVERIFIED）**：只验证 22 类排序/重编号 + 200 随机置换无命中；但当前记录序已是规范化序，结论方向可靠。
5. **verify_config.py 恒真字段（代码质量）**：feeder120_vs_336_demand_identical: not failures or True，无判别力；不影响 exit 0 与我的独立复算。
6. **safety 探针（probe_concurrency 修复前 exit 1 归因、test_http 0/60）未由我复跑（UNVERIFIED）**：我只复跑了 unittest 17+362；探针自述未独立验证。
7. **MATLAB 未运行 Simulation 类（执行者自述边界）**：本轮 MATLAB 只做静态 PREI 与契约级公式/轨迹核对，不构成对事件仿真类的运行期对照；我未补跑。

## 8 复跑命令汇总（全部在仓库根目录）

| 命令 | exit |
|---|---|
| C:\anaconda\python.exe research/round5_20261031/repro/verify_repro.py | 0 |
| C:\anaconda\python.exe research/round5_20261031/config/verify_config.py | 0 |
| C:\anaconda\python.exe research/round5_20261031/lit/verify_lit_citations.py | 0 |
| C:\anaconda\python.exe research/round5_20261031/acceptance/independent_repro_check.py | 0 |
| .../run_cost_curve.py ... --workers 1 --out acceptance/indep_rerun_w1.json | 0 |
| .../run_cost_curve.py ... --workers 8 --out acceptance/indep_rerun_w8.json | 0 |
| C:\anaconda\python.exe research/round5_20261031/acceptance/independent_stale_probe.py | 0 |
| C:\anaconda\python.exe research/round5_20261031/acceptance/independent_config_check.py | 0 |
| C:\anaconda\python.exe research/round5_20261031/acceptance/lit_spotcheck.py | 0 |
| C:\anaconda\python.exe research/round5_20261031/acceptance/mechanism_recheck.py | 0 |
| C:\Users\tho25\.dsh\...\python.exe -m unittest ...test_round5_safety -v | 0（17 OK） |
| ... -m unittest discover -s apps/parking_lab/workbench/tests -p "test_*.py" -t . | 0（362 OK） |
| matlab.exe -batch "... static_verify" ×4 | 均 0 |
| matlab.exe -batch "... indep_verify" ×3 | 均 0 |

解释器：验收主用 C:\anaconda\python.exe 3.12.3 + PyMuPDF 1.28.2；unittest 用 DSH 运行时 Python 3.12.14。MATLAB 26.1.0.3203278 (R2026a)。

## 9 产物索引（本目录）

- verify_repro.log、verify_config.log、verify_lit.log：执行者三脚本原样输出。
- indep_rerun_w1.json / indep_rerun_w8.json + .log：我自跑 25 流复跑与对照数据。
- independent_repro_check.py/.log：与执行者 JSON、第三/四轮的全量对照。
- independent_stale_probe.py/.log：排序/重编号不可复现探针。
- independent_config_check.py/.log：1025 行服务/功率/成本独立复算。
- lit_spotcheck.py/.log/.json：10 条引用上下文与 M18 关键词扫描原文。
- frozen_and_safety_check.json：冻结哈希、PDF/Word 时间、experiments.py 状态。
- unittest_round5_safety.log、unittest_full_regression.log。
- matlab_static_verify_console*.log、matlab_indep_verify_console*.log、matlab_outputs_run1/2.sha256、runA_*_summary.json。
- mechanism_recheck.py/.log、mechanism_counterexamples.json（16 条身份 + 2 条固定轨迹 + 逐 k 复算）。
