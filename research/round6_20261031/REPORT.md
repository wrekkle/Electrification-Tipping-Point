# 第六轮研究与稿件整合报告（Q1–Q3、信息条件、论文新工作稿与二阶段结论一致性收紧）

类型: 研究证据与阶段报告
状态: 生效（研究完成；论文为工作稿，不升级投稿）
负责人: lead（集成）；sim-a、mech-b、paper-c 执行
日期: 2026-10-31
边界: 不启动 RL、不扩城、不跑大网格；冻结主稿/旧 Word/旧原始数据/已有交付 JSON/前五轮证据未改；采集器未动；新证据仅在 research/round6_20261031/；论文新稿仅在 paper/draft/。

## 0 结论速览

| 问题 | 实际得到 | 状态 |
|---|---|---|
| Q1 非单调性机制 | 3 个事件级最小反例：k→k+1 把最小号普通位改为带枪位，ICE 失 1 辆、恢复 2 辆，净失败 −1；同时 EV 自身失败上升。strict_pi0/车位反序/dwell−20% 使下降消失；dwell+20%/初始占用/同刻部分保留。二阶段把受限命题 P1 的证明改为容量差耦合（严格无回落、A1–A6；失败集合 fail(k)⊆fail(k+1) 且失败数/率单调不减），并指出早期“镜像同址”证明的缺口；无条件单调性引理仍被 16 反例否定 | 完成（模拟机制，非真实场站规律） |
| Q2 充电意愿信息价值 | I1 仅多知当次 needs_charge，analysis_only；656 次仿真：Δk_info 8/8 为负（−2…−17，中位 −9.5），但同 k 四类 both143/only_I0 26/only_I1 61/neither98；k_min(I0) 处 2/8 单元仅 I0 可行。只能称算法比较/信息上界示例 | 完成（非全局最优） |
| Q3 可行配置集合 | 660 组完整 k=0..40：非空 K 全为连续整数区间（0 断裂）；inclusive 空 124/strict 空 139（15 组零需求 N/A）；437 组含 k=40 截断；REF A/B 四类 72/3/0/15。二阶段配对级复核（Table 4）：840 配对 both 677/仅首 7/仅次 4/neither 152；restored 4、smaller 2 全部来自 B|D、C|D（同一 TPE1376 seed10），专用-共享行 second-only=0、smaller=0；5 disjoint 全来自 A 行。省设备只在共享-共享规则间、且只此一组两配对 | 完成（有限枚举，非普遍证明；区间性限定 0..40） |
| 语义与接口 | 五态语义入口（valid/N/A零需求/censored无离场样本/missing/illegal）；I0/I1 隔离授权；四约束五态 66、旧口径 310、严格 51（310→51 为口径差，非修复）；默认规则数值不变 | 完成，测试 388 OK |
| 论文工作稿 | rev3（英文）与补充材料 S1–S6 已另存 paper/draft/，含三问题实际结果、边界与二阶段收紧；未升级投稿、旧稿未改 | 见 §7、§11 |

## 1 语义入口与信息条件（A）

- `apps/parking_lab/workbench/service_semantics.py`：五态 `classify_rate` + `constraint_status/judge/feasible/minimal_feasible`。仅 valid 可判满足；零需求 N/A 记录并跳过；`censored_no_departure` 不判成功；missing/illegal 不判 achieved；前格不可判定不确认最小 k。未改 `analyze_round3.joint_k`。
- 59 条既有曲线 31,975 行/975 单元五态计数与第五轮 `none_semantics_4way.json` 逐项一致：容量 valid 31,360 / N/A 615；离场能量 valid 22,895 / N/A 615 / **censored 8,465**；全部 missing=0、illegal=0。
- 联合判定：三约束 N/A 跳过 780/975、严格 765；四约束五态 66、旧“零分母全跳过”口径 310、严格 51。**310→51 是口径差，不是修复效果**；能量约束在删失条件下只作辅助结果。
- `apps/parking_lab/workbench/info_regimes.py`：I0 直接用未改 Simulation；I1 为 `RegimeSimulation` 子类 + `AnalysisGrant`，仅多当次 `needs_charge`，越权抛 `PermissionError`；`MimicI0Policy` 逐车等同 I0。simulation.py/rules.py/config.py 零修改（mtime 与固定输入哈希 e407f5a1… 均可核）。
- 输出行级 `information_regime/analysis_only/policy_kind`，JSON 顶层含授权、可见/隐藏字段与拒绝类型。

## 2 Q1：非单调性的机制（B）

**最小反例（workbench Simulation 与 round4 机制模型全 k 逐值相等）**

| 例 | 参数 | k→k+1 | ICE 失败 | EV 失败 | EV 停普通位 | 差异车辆 |
|---|---|---|---|---|---|---|
| E1 | seed1 n6 ev0.4 q0.1 dwell5/5 rate1.6 | 0→1 | 8/24→7/24 | 5→7 | 8→2 | 11 辆 |
| E2 | seed1 n8 ev0.6 q0.1 dwell5/2 | 5→6 | 6/15→5/15 | 1→1 | 3→0 | 9 辆 |
| E3 | seed3 n8 ev0.4 q0.5 dwell5/5 | 2→3 | 9/21→8/21 | — | 9→5 | 12 辆 |

**逐事件机制**：k→k+1 把最小号普通位改成带枪位。一名 EV（不充电也会先占）被吸到带枪位，普通位空出；一名 ICE 在某个到达时刻失去原普通位（失败 +1），后续两名 ICE 因普通位前移获准入（失败 −2），净 −1。EV 自身因带枪位被占而失败上升（E1 5→7）。下降来自离散占位/释放的时序替换，不是“EV 回落变少所以 ICE 自动变好”。

**控制变量（各 1 组，3 例）**：strict_pi0（禁止 EV 回落）3/3 不再下降且失败率反升；车位选择反序 3/3 不保留；dwell−20% 3/3 不保留；dwell+20% 仅 E1 保留；初始占用 E1/E3 保留、E2 不保留；同刻 EV 优先 3/3 保留但精确同刻到达为 0，未真正触发 tie-break。

**受限命题 P1（A1–A6，有证明）**：总车位 N 固定；strict no-fallback（EV 只用带枪位、ICE 只用普通位，无车型转换）；纯损失制（不排队/不挪车/不抢占，找不到兼容空位即失败）；同一到达序列（时刻/车型/dwell 相同，能量不影响普通位占用）；准入只取决于兼容空位是否存在（不要求最小号优先）；失败率分母为全部 ICE 到达数。则同一到达序列上 ICE 失败集合 fail(k)⊆fail(k+1)，失败数与失败率单调不减。证明用**容量差耦合**：设 S_k、S_{k+1} 的普通位数为 m、m−1，a、b 为两系统当前 ICEV 数；用 0≤a−b≤1 的计数不变式（离场三类、到达三类）推出 S_{k+1} 准入时必有 a<m，故 S_k 也准入。二阶段独立核对发现：B 原“镜像同址”证明的同址假设有反例（n=4、k=0→1、两辆 ICE 时 bay1 在 k=0 空、k=1 占），Lead 早先的“排序占位支配”也不成立（m=5、A 占 {0,1,2}、B 占 {1,3} 时最小空位 3 vs 2），故 SI S2 改用上述容量差证明；主稿只留命题+假设+“proof in Supplementary Note S2”。3456 网格与 12,000 随机序列 0 违反仅作支持，不代替证明。**无条件“更多枪改善 ICE 准入”不成立**，16 反例依赖 EV 回落。

**边界**：这是合成机制模型，不是真实停车场实测规律；EV 回落的出现是反例的必要背景但非充分条件（E2 回落 3→0 仍净减 1）。

## 3 Q2：充电意愿信息的价值（A）

- 设计：同一外生车流重放 I0/I1；I1 只额外可见当次 needs_charge；所有车辆仍停车，到达/停留/需求/能量不变；I1 可模仿 I0（逐车等同）。
- 规模：TPE0008/TPE0401 × seeds 1–2 × 规则 A/B × k=0..40 × {I0,I1} = **656 次仿真，0 失败**；手算 k=0（capacity 率 1.0、两条件均不可行）16/16 一致。
- 可行集合（三约束、α=0.05、N/A 跳过）：16/16 为连续闭区间。Δk_info=min k(I0)−min k(I1) **8/8 为负**（−2…−17，中位 −9.5）。
- 同 k 四类（328 个 unit-k 格）：both 143、only_I0 26、only_I1 61、neither 98、undecidable 0。k_ref=k_min(I0) 处：both 6、only_I0 2（TPE0401/规则 A，I1 的 ICE 停车失败率 0.0769/0.1782 > α）、其余 0。
- 解释：启发式把不充电 EV 挪到普通位、为要充电的车保留连接器，低 k 降低容量未服务率；高 k 挤占普通位使 ICE 失败上升，故 I1 并非全面占优。
- 可写/不可写：写“该网格、该启发式下的算法比较/信息上界示例”；不写“信息必然改善”“I0/I1 全局最优”“必然省枪”。 “更多信息不降低最优值”只在策略集合包含意义下成立，属基础性质，不包装为创新。

## 4 Q3：可行配置集合的形状与边界（B）

- 660 组完整 k=0..40：round3 main 4 规则×90 + round4 场景 12 条×25。missing=0、illegal=0、undecidable=0；N/A 仅 15 组（M08-ALL-AWAY-REF 零充电需求）。
- 形状：非空 K **全部为连续整数区间（536 组，0 断裂）**；inclusive 空集 124、strict 空集 139（15 组 N/A 按契约不判 achieved）；437 组 K 含 k=40（truncated_at_kmax）。
- 跨规则 REF：A/B 四类 both 72、only A 3、only B 0、neither 15；A/D 74/1/0/15；B/D 72/0/2/16；无“部分重叠”。双方可行但 K 不相交：A-B 2 组（TPE1376 s10：A=[2..5]、B=[24..40]；TPE1380 s3：A=[23..25]、B=[27..40]），A-D、B-D 各 1 组。
- 组级（B 报告口径）：恢复可行性 2 组（B 空、D 非空：TPE1376 s2、TPE1380 s7）；省设备 1 组（D 的 min k=2 < B 的 24，TPE1376 s10）；同 k 服务改善 2 组（A→B）；共享本身（A vs B）省设备 0 组。
- **配对级（Table 4，Lead 独立复算）**：840 配对 both 677、仅首 7、仅次 4、neither 152；restored 4、smaller 2 全部来自 B|D、C|D 两行；A|B、A|C、A|D 的 second-only=0、smaller=0；5 个 disjoint 全在 A 行。两个 smaller 都来自同一 REF/TPE1376/seed10（D min 2，B、C min 24；A min 2，故 A vs D 无节省）。这是同信息条件下两条共享规则的分配次序/预测门控差异，不是共享省设备；论文 Table 4 note 与正文已据此限定。
- TPE0330：0..40 仅 seed3 可行（[32..40]，truncated）；扩展 41..200 首可行 52–84；k>40 与 >200 均标预算截断，不并入 [0,40]。Lead 独立复算 Table 4 六行逐项与 B 机器 JSON 一致；smaller groups 仅 REF|TPE1376|10 的 B|D、C|D 两次配对。
- 边界：有限轨迹完整枚举 ≠ 随机总体可行域；不能只报双方可行样本；未对“双方可行但不相交”单元重跑新轨迹（0 条新轨迹，按预算上限）。

## 5 Lead 独立复核

- 语义五态手算反例：zero_demand→N/A、有需求+零离场→censored、分母>0+None→missing、1.5→illegal；judge 对 censored/missing/illegal 均 achieved=false，valid 0.01→achieved=true。
- 59 曲线复算：缺失 0/非法 0；联合 780/765、66/310/51 与 A 报告一致。
- Q3 独立复算（round3 main ref s10）：A/B 四类 72/3/0/15、双方可行但不相交 {TPE1376 s10, TPE1380 s3}、非区间 0 —— 与 B 报告逐项一致；另用 Lead 全库扫描（119 文件、连续采样单元）得非空 K 均为整数区间、断裂 0。
- Q1 独立重放（自写事件循环）：E1 k=0/1 ICE 8→7、EV 停普通位 8→2、EV 失败 5→7，与 B/机制模型一致。
- 二阶段 P1 证明逐步核对：发现 B“镜像同址”假设有反例（n=4,k=0→1 两辆 ICE，bay1 在 k=0 空、k=1 占）；Lead 早先“排序占位支配”也不成立（m=5, A 占 {0,1,2}, B 占 {1,3}，最小空位 3 vs 2）。改用容量差耦合（a−b∈{0,1}；A1–A6），SI S2 已重写；3456 网格+12,000 随机序列 0 违反只作支持。
- 二阶段 Q3 复核：Lead 独立复算 Table 4 六行（both/first-only/second-only/neither/restored/smaller/disjoint）与机器 JSON 逐项一致；两个 smaller 只在 REF|TPE1376|10 的 B|D、C|D；A|D 同为 min 2。
- 默认行为不变：固定输入 86 辆到达的逐车哈希 e407f5a1…、demand_hash a2baa0b5…、率值与回归脚本一致；simulation.py/rules.py/config.py mtime 未变（13:11–13:13，第五轮）。
- 冻结检查：361 个冻结文件哈希与轮前一致（0 变更、0 缺失）。

## 6 测试、检查与安全

- 新测试：test_round6_semantics + test_round6_info 26 tests OK；unittest discover 388 tests OK（第五轮 362 → 新增 26）。
- `scripts/check_all.py`（DSH Python）EXIT 0：0 错误、8 条既有历史警告。
- 固定输入回归 `a_info/fixed_input_regression.py` EXIT 0（哈希与指标固定）。
- 论文侧（rev3）：paper_stats EXIT 0（17,418 词、76 文献、56 段/65 整体公式）；引用双向 76/76；Word 导出 61 页；61 页全页栅格 0 空白、0 文字越界，6 张数据表题注同页且单页（p19/21/22/24/39/51）；Lead 抽查 p24/p39 版式正常。
- check_all（DSH Python）EXIT 0；旧 rev2/rev1/投稿版 SHA 与 mtime 未变。
- 未另起全面安全扫描；信息泄漏验收在 a_info/REPORT.md §2。

## 7 论文新工作稿（rev3）与补充材料

- 主稿：`paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx`，SHA-256 06906f34…；289 段、14 表（6 数据表 + 8 公式表）、8 图、76 文献（双向 76/76）、56 段/65 整体公式、Word 导出 61 页；paper_stats EXIT 0，总 17,418 词、题注 11、未归类 0。构建脚本 `build_paper_v3_round6_rev3.py`/`paper_v3_round6_rev3_content.py`；证据 `c_paper/build_manifest_rev3.json`、tables、`paper_stats_rev3.json`、`round6_rev3_draft.pdf`、RUNLOG §10。
- 补充材料：`paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx`，SHA-256 2ebc9e83…；58 段、7 表、7 页；S1 语义、S2 P1 全假设+容量差证明+早期证明反例、S3 逐事件/控制、S4 Q2 八单元、S5 全配对/边界、S6 审计。主稿引用 Supplementary Notes S1–S6。
- 二阶段修订：题名去掉 information 的价值暗示，改为 charging-intention signal；摘要/结果/讨论/结论统一 Q2 为“specific signal-aware heuristic 的算法比较，非信息价值”；Q3 所有 interval 断言限定 within the enumerated range 0–40，保留 437 截断/124/139/15；Table 4 行标签区分 dedicated vs shared 与 shared vs shared，Note 与正文明确 4 restored、2 smaller 只在 B|D、C|D 且同一 TPE1376 seed10；P1 改 count-difference 证明；旧方法段 global optimum 改为“网格内被评估点中的最好点”，旧讨论 socially preferable 加 under the submitted cost model / not socially optimal；详细证明/轨迹/审计移 SI S2/S3/S6。
- 检查：引用 76/76 双向、无悬空；pending strings=0；61 页全页栅格 0 空白、0 文字越界；6 张数据表题注与表同页（p19/21/22/24/39/51）且单页不跨页；旧 rev2（b2d36e2d…）、rev1（fc1320b7…）、投稿版（04bda311…）SHA/mtime 未变；期刊模板像素级比对未做（UNVERIFIED）。

## 8 未验证与限制

- Q1 只提取 3/16 反例的事件轨迹；其余 13 例仅有身份与总计数；控制变量各 1 组、初始占用取值未扫描；P1 是手写容量差论证（A1–A6，非机器证明），3456+12,000 枚举只作支持；机制为合成模型，真实停车场是否出现同类非单调 UNVERIFIED。
- Q2 只覆盖 A/B、2 场站、seeds 1–2、k≤40；I1 仅一种启发式，不是信息价值上界证明；方向不可外推到其它规则/场站/种子。
- Q3 只含三项约束、不含能量约束；K 来自既有曲线，未重跑“双方可行但不相交”单元；fixedk 只有 6 个 k/组，不构成 K；区间性只对完整枚举 0..40 成立，437 组在 k=40 截断。
- 论文：rev3 已做 61 页全页栅格（0 空白/0 越界、题注同页），但未做期刊模板像素级比对；M10 作者名单、M18 在线附录证明仍 UNVERIFIED；旧 ETP 结果保留且未复算；未升级投稿。
- 能量约束仍为删失辅助结果；p_EV/q_need 仍是情景输入（0.0364 仅 usage proxy）；旧问题边界见第五轮报告 §14。

## 9 证据与复现

| 内容 | 路径/命令 |
|---|---|
| 契约/计划 | research/round6_20261031/CONTRACT.md、PLAN.md |
| A 语义/信息 | apps/parking_lab/workbench/service_semantics.py、info_regimes.py；a_semantics/、a_info/ |
| B 机制/可行域 | b_mechanism/、b_feasible/（REPORT + JSON + 日志 + run_record） |
| Lead 复核 | lead/verify_indep.py、q1_indep.py、q3_indep.py、q3_scan.py、frozen_sha256_before.txt |
| 二阶段核对 | lead/consistency_check.md、p1_indep.py/json、q3_pair_verify.py/json、pdf_headers.py | Q3 两案例/Table 4 六行复算、P1 容量差证明核对、渲染/表头检查 |
| 论文 | paper/draft/…_round6_rev3.docx、…_supplementary_2026-10-31_round6.docx；research/round6_20261031/c_paper/（build_manifest_rev3、tables、paper_stats_rev3、round6_rev3_draft.pdf、RUNLOG） |
| 全页渲染 | research/round6_20261031/lead/render_rev3/（61 页 PNG）、render_rev2/ | 0 空白、0 文字越界；题注同页 |

## 10 交付清单与接口边界

| 交付 | 路径 | 说明 |
|---|---|---|
| 语义入口 | `apps/parking_lab/workbench/service_semantics.py` | 五态 `classify_rate`、`constraint_status`、`judge`、`feasible`、`minimal_feasible`；仅 valid 可判满足，N/A 记录跳过，censored 不判成功，missing/illegal 不判 achieved；默认规则零修改 |
| 信息条件 | `apps/parking_lab/workbench/info_regimes.py` | I0 用未改 Simulation；I1 子类 + `AnalysisGrant`，仅多当次 `needs_charge`；`MimicI0Policy` 可等同 I0；行级 `information_regime/analysis_only/policy_kind` |
| 测试 | `apps/parking_lab/workbench/tests/test_round6_semantics.py`、`test_round6_info.py` | 26 条；全量 discover 388 条 EXIT 0 |
| Q1 证据 | `research/round6_20261031/b_mechanism/` | 3 条最小轨迹、控制变量、3456 格枚举、受限命题 P1 与证明梗概 |
| Q2 证据 | `research/round6_20261031/a_info/` | 656 行 JSON、可行区间表、四类计数、授权与 mimic 验收 |
| Q3 证据 | `research/round6_20261031/b_feasible/` + `lead/q3_*.py` | 660 组 K 集合、形状/截断/四类配对；Lead 独立扫描与四类复算 |
| 论文工作稿 | `paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx`（SHA-256 06906f34…）+ 补充材料（2ebc9e83…） | 289 段、76 文献、6 数据表 + 8 公式表、8 图、61 页；SI S1–S6 7 页；构建脚本 rev3；旧 rev1/rev2/投稿版未覆盖 |
| 规则与边界 | PLAN.md、CONTRACT.md、本报告 | 不启动 RL、不扩城、不跑大网格；不覆盖冻结对象；论文不升级投稿；采集器未动 |

兼容边界：新接口都是增量文件，默认运行路径（正式规则、runner、旧分析脚本）行为与数值不变；I1 只用于分析、不得作为可实施政策；paper 构建只读既有数据和 round6 JSON，不改旧稿。

## 11 二阶段：结论一致性核对与新稿收紧

1. **Q3 两个省设备案例**：同一组 REF / TPE1376 / seed10 的 B vs D、C vs D。A（专用）K=2–5，min 2；B、C（共享）K=24–40，min 24；D（预测门控共享）K=2–40，min 2。k=2 时 B/C 的 capacity_only_unmet_rate=0.5（2 个充电请求只服务 1 个，>0.05），D=0.0；ICE 失败率 B/C=0.0267、D=0.0400（均 ≤α）；EV 失败率均 0；三条率分母 2/5/75 均非零，N/A/删失不参与；三约束、α=0.05；四规则均在 I0（D 只用历史可见预测，不读 needs_charge）。因此“专用 vs 共享无正 Δk”成立**不需要改**；要改的是旧 Table 4 Note 把每行首规则都写成 dedicated，以及正文/摘要把 4 restored、2 smaller 泛称“shared rule”。已改为行标签 A/B/C/D 的 dedicated-vs-shared 与 shared-vs-shared，Note 明确两 smaller 只在 B|D、C|D 的同一组两配对，A|D 同为 min 2；正文与结论同步。
2. **Q2 措辞**：统一写“一个具体信号感知启发式（充电到达优先带枪位、非充电到达优先普通位、ICEV 沿用原规则）的算法比较”。8/8 单元 Δk 为负（−2…−17，中位 −9.5），同 k 四类 143/26/61/98，k_min(I0) 处 2/8 仅 I0 可行；不写信息价值、全局最优或信息必然改善。
3. **Q3 区间**：660 组 K 在完整枚举 0..40 内全为连续整数区间、0 断裂；437 组 k=40 仍可行（截断）；inclusive 空 124/strict 空 139（15 组零需求 N/A）；所有 interval 断言已加 within the enumerated range 0–40，明确不覆盖更大 k。
4. **P1 证明**：独立逐步核对发现 B 原“镜像同址”假设有反例（n=4、k=0→1、两辆 ICE，bay1 在 k=0 空、k=1 占）；Lead 早先的“排序占位支配”也不成立（m=5、A 占 {0,1,2}、B 占 {1,3}，最小空位 3 vs 2）。改用容量差耦合：设两系统普通位数 m、m−1，当前 ICEV 数 a、b，用 0≤a−b≤1 的计数不变式（离场三类、到达三类）得 S_{k+1} 准入 ⇒ a<m ⇒ S_k 也准入，故 fail(k)⊆fail(k+1)；A1–A6 已列全（strict no-fallback、损失制、同一到达流、准入仅取决于兼容空位、分母固定）。主稿改“count-difference coupling”，SI S2 重写；3456+12,000 枚举仅作支持，不称证明、不称新颖。
5. **论文统一与收紧**：题名改为“…conditional evidence on shared use and a charging-intention signal”；摘要/结果/讨论/结论统一 Q2/Q3 口径与限定；正文聚焦主线，证明/轨迹/审计移 SI S2/S3/S6；Table 4、Q2、Q3 表述已落实；旧方法段“guarantees global optimum / invaluable / profound insights”改为“枚举只在有限网格取被评估点中的最好点、不对网格外断言最优”；旧讨论“socially preferable”加 under the submitted cost model / not socially optimal。
6. **验收**：rev3 SHA 06906f34…、SI SHA 2ebc9e83…；76/76 引用；61 页全页栅格 0 空白/0 越界、6 表题注同页且单页；旧 rev2/rev1/投稿版未覆盖；check_all EXIT 0。仍 UNVERIFIED：期刊模板像素比对、M10 作者名单、M18 附录证明；旧 ETP 结果未复算。
