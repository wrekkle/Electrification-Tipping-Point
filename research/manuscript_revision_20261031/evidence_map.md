# Round7 A：证据映射与独立评价状态（只读核对）

状态: 生效
日期: 2026-10-31
范围: Q2 8 单元、Q3 六行配对、Round4 fixed-k 独立评价、M06/M07/M18/M08/M10 引用、旧 ETP 编号 37–40/54/70–71。
只读声明: 未改论文/SI/文献索引/原始 JSON；本文件 `research/manuscript_revision_20261031/evidence_map.md` 是唯一写入。
标签: **已核实**=有文件、页码或可复算证据；**UNVERIFIED**=未取得或本轮未重核。

## 0 结论速览

| 项 | 结论 |
|---|---|
| Q2 | 8 单元 = 4 条 lot-seed 流 × 2 条规则；同一流 A/B 的 k 完全相同；Δk=k_I1−k_I0 全负（−2…−17）。I1 是 analysis-only 启发式，seeds 1–2 落在选择种子里，**属同一批种子的探索性算法比较，不是独立评价**；同 k 下 6/8 可行，2 个仅 I0 可行、0 个仅 I1。 |
| Q3 | dedicated-vs-shared 与 shared-vs-shared 分开：只有 shared-vs-shared（B\|D、C\|D）出现 restoration=2、device_saving=1、same_k_worse=3；两个 device_saving 是**同一组 REF/TPE1376/seed10**，不是两个独立案例。 |
| 独立评价 | 只有 Round4 fixed-k 是独立种子评价（选择 1–4，评价 5–10；40 文件、每规则 48 单元）。Q2 探索性；Q1 单实例确定性复算；Q3 既有曲线有限枚举。 |
| 文献 | M18、M10 首页已核；M06/M07/M08/M10 实际支持内容见 §4。M18 在线附录未取得，不能当证明。M10 修订稿文字仍称“仅有检索索引转写”，与已取得全文不符（**需改文，未改**）。 |
| 旧 ETP | 37–40、54、70–71 仍只被旧 Results/Optimization Framework/Costs 段引用；54=P22、70=P36、71=P37；37–40 不在 literature/index.json。只有保留明确标注的“历史模型”段落才能保留这些引用。 |

## 1 Q2：信息条件 I0/I1 的 8 个单元

来源: `research/round6_20261031/a_info/q2_info_regimes.json`（schema `round6/a_info/q2_info_regimes/v1`，`generated_utc=2026-10-31T08:27:13Z`，命令 `C:/anaconda/python.exe research/round6_20261031/a_info/run_q2.py`，exit 0）。

| lot | seed | 规则 | k_I0 | k_I1 | Δk（I1−I0） |
|---|---:|---|---:|---:|---:|
| TPE0008 | 1 | A | 9 | 4 | −5 |
| TPE0008 | 1 | B | 9 | 4 | −5 |
| TPE0008 | 2 | A | 7 | 5 | −2 |
| TPE0008 | 2 | B | 7 | 5 | −2 |
| TPE0401 | 1 | A | 20 | 6 | −14 |
| TPE0401 | 1 | B | 20 | 6 | −14 |
| TPE0401 | 2 | A | 25 | 8 | −17 |
| TPE0401 | 2 | B | 25 | 8 | −17 |

- **已核实**：8 单元不是 8 个独立样本；是 TPE0008/TPE0401 × seeds 1/2 共 4 条外生流，每条流分别跑规则 A/B，所以每流 A/B 的 k_I0、k_I1 与 Δk 完全相同。源码定义 `delta_k_info = k1 - k0`（`run_q2.py:191-202`）；JSON 的 `delta_k_info.summary` 为 8/8 negative、中位 −9.5、min −17、max −2。
- **已核实**：I0 是 `real_rule`（`analysis_only=false`），I1 是 `analysis_heuristic`（`analysis_only=true`，只额外允许读 `needs_charge`，授权块 `authorization` 明确 forbidden fields）；同 k 对比（以 I0 的最小可行 k 为 k_ref）：6 个 `both`、2 个 `only_I0`（TPE0401/seeds 1、2/规则 A，k_ref=20、25），0 个 `only_I1`；三项服务率格子里 I1 相对 I0 为 0 更好、2 更差、22 相同。即 Δk 的改善不伴随同 k 服务改善，且两个单元同 k 不可行。
- **结论**：Q2 是同一批车流上的探索性算法比较，不是独立评价。依据：`a_info/REPORT.md:11-12,101`（2 场站、seeds 1–2、A/B、未跑验证场站与 seeds 3–10）；Round4 的选择种子是 1–4（`eval_fixed_k.py:31`），Q2 用的 1–2 全部落在选择种子里，没有 held-out 分割。
- **UNVERIFIED**：I1 若作为可执行政策需要准入权限与部署假设；本轮只核了分析授权，不评估政策可实施性。

## 2 Q3：六行配对（不跨类聚合）

来源: `research/round6_20261031/b_feasible/q3_feasible_sets.json`（`q3_feasible_sets/v1`，exit 0）与 `research/round6_20261031/lead/q3_pair_verify.json`（`all_match=true`，独立复算表 4 的 6 行全部匹配）。

**2.1 dedicated-vs-shared**（A 在前）

| 对 | pairs | restoration | device_saving | same_k_improvement | same_k_worse | both_disjoint |
|---|---:|---:|---:|---:|---:|---:|
| A\|B | 190 | 0 | 0 | 2 | 0 | 2 |
| A\|C | 90 | 0 | 0 | 2 | 0 | 2 |
| A\|D | 190 | 0 | 0 | 0 | 0 | 1 |

**2.2 shared-vs-shared**

| 对 | pairs | restoration | device_saving | same_k_improvement | same_k_worse | both_disjoint |
|---|---:|---:|---:|---:|---:|---:|
| B\|C | 90 | 0 | 0 | 0 | 0 | 0 |
| B\|D | 190 | 2 | 1 | 0 | 3 | 0 |
| C\|D | 90 | 2 | 1 | 0 | 3 | 0 |

- **已核实**：两个 `device_saving` 都来自 `scenario=REF, group=TPE1376|10`（`q3_pair_verify.json` 的 `smaller_groups`，B\|D 与 C\|D 各列同一组；K_B/K_C=24..40，K_D=2..40）。它们不是两个独立案例，而是同一 lot-seed 在两条配对行中各计一次。
- **已核实**：B\|D 与 C\|D 的 `restoration=2` 也来自同一对组：REF/TPE1376/seed2 与 REF/TPE1380/seed7（B/C 空集、D 非空）。B\|D 的 `same_k_worse=3` 同样与 C\|D 重叠，不能当独立证据累加。
- **不要加总**：dedicated-vs-shared 与 shared-vs-shared 的 counts 不可相加；B\|D 与 C\|D 共享同一批 D 轨迹，重复计数会夸大“共享有效”的样本量。
- **评价状态**：Q3 是对既有 19 条曲线（round3 main 4 + round4 scenario 15，共 660 组；另含 TPE0330 的 A 扩展到 200）在 k=0..40 的**有限枚举/描述性**分析；`b_feasible/REPORT.md:21,94-96` 明确“未跑任何新轨迹”，K 全部来自既有曲线，不是独立种子评价。
- **UNVERIFIED**：`both_disjoint` 的 A\|B 2 组、A\|C 2 组、A\|D 1 组未用新轨迹独立重跑（REPORT §6 也把“独立重跑 2 组”列为下一轮工作）。

## 3 独立评价状态（四种结论分开标注）

| 结论/实验 | 种子与选择 | 规模/数值 | 评价状态 |
|---|---|---|---|
| 现有共享规则（Round4 fixed-k） | 选择 seeds 1–4（取中位 k）；评价 seeds 5–10，不相交（`eval_fixed_k.py:31-32,40-52,75-83`） | 40 个运行文件（own A/B/D=24、common B/D=16），每规则 48 单元；A/B/D 可行 36/34/35；容量未服务 5.02/6.49/5.36%；EV 0.19/0.69/0.19%；ICE 0.99/0.70/0.90%（`FINAL_ACCEPTANCE.md:36`） | **独立种子评价（唯一）**；本轮从 fixedk JSON 复算均值与可行数，与验收记录逐项一致（已核实） |
| Round4 情景曲线 | seeds 1–5，无 held-out 分割 | 5 情景 × A/B/D × 5 train 场站 × k 0..40；feeder 120 | 情景块描述，不是独立评价；跨第三轮 feeder 336 不可合并 |
| Q2 I1 | seeds 1–2（全部落在选择 seeds 1–4 内）、2 场站、A/B | 656 次仿真，8 单元，Δk 全负 | **探索性算法比较**；I1 是 analysis-only，不是可执行政策 |
| Q1 确定性反例 | 单个机制实例（seed=1，n=6，37 arrivals）；k=0 vs k=1 | ICE fail 8→7，同时 EV fail 5→7、EV ordinary 8→2；Lead 独立实现逐事件重放 `q1_indep.py` | **单实例确定性复算**；不是统计评价；Round5 16 例中只提取 3 条轨迹，其余 13 例仅总计数（`b_mechanism/REPORT.md:20,109`） |
| Q3 有限枚举 | 既有 19 条曲线（4+15）全部 (scenario, lot, seed, rule) | k=0..40；660 组；6 对配对 | **有限枚举/描述性**；pair_verify 只复核计数，不是独立种子评价 |

- **已核实**：`fixedk_manifest.json` 的 `selection_seeds=[1,2,3,4]`、`evaluation_seeds=[5,6,7,8,9,10]`、40 runs、全部 exit 0；每规则 8 场站×6 seeds=48 单元。
- **已核实**：Q1 的“反例”是机制层面的非单调性（k 0→1 ICE 失败下降但 EV 回落普通位下降、EV 失败上升），不是真实场站规律；无回落模型的单调命题 P1 只在该受限模型内成立（`b_mechanism/REPORT.md:86-90`）。**UNVERIFIED**：真实停车场是否出现同类非单调。

## 4 文献引用核对（M06/M07/M18/M08/M10）

### 4.1 首页/版本（已核实）

| 文献 | 首页核对结果 | 本地来源 |
|---|---|---|
| M18 | Feng Chen, Valery Pavlov, Sitao Zhao, Jianghong Feng, Su Xiu Xu（通讯）；*Joint operation strategy of parking and charging infrastructure*；Transportation Research Part D 144 (2025) 104773；DOI 10.1016/j.trd.2025.104773；online 7 May 2025；17 页；首页尾注含 Elsevier 版权与 DOI；SHA-256 `944b4d2a…b34ed69` 与笔记一致 | `papers/electrification-math/M18_joint-operation-parking-charging_TRD2025.pdf` |
| M10 | Seheon Kim, Soora Rasouli, Harry J. P. Timmermans, Dujuan Yang（2022）；*A scenario-based stochastic programming approach for the public charging station location problem*；Transportmetrica B: Transport Dynamics 10(1), 340–367；DOI 10.1080/21680566.2021.1997672；首页为 TU/e 机构库版本 | `research/official_data_20261031/ev_behavior/raw/M10_TUE_fulltext.pdf` |

### 4.2 在修订稿中的引用与实际支持内容

修订稿编号（rev3 docx References 共 81 条）：M06=72、M07=73、M18=74、M08=75、M10=76；正文只在 Related work 段落 20–22 引用。

| 文献 | 稿件引用点与页码/式号 | 实际支持内容 | 不支持/不能写的内容 | 证据等级 |
|---|---|---|---|---|
| M06 | Related work 段：车辆-车位匹配 + ALR；页码 p7 Rule 1–2、p9 式(5)、p10 式(15)、p24 | 共享私人车位（含充电位）的分配算法；决策是 x_ij，不新建、不定 k；作者报告 CPLEX gap≈1.72%、节时 80.31%（p18 表9） | 不能支持“决定枪数/服务水平约束”；作者数值未本地复算 | 页码/式号 **已核实**（笔记/对照文档）；数值为作者报告（B） |
| M07 | Related work 段：预约制滚动分配 + 不准时；p8–p9 共享机制、p11 式(42)–(48)、p15–16 数据、p22 表8、p25–26 | 混合车场预约/滚动分配；充电功率是请求属性；杭州 1400+ 场约 3000 万条记录拟合后仿真；表 8 仍有非零 MIP gap | 不能支持“最小枪数/社会成本”；作者数值未复算 | 页码/式号 **已核实**；数值作者报告（B） |
| M18 | Related work 段：供应链博弈（P/D/C、n、F、Nash 议价）；p4–p6 式(1)–(14)、p10 式(16)(17)、p13 式(19)–(21)、p15 “No data was used” | 联合运营/共建共享的产权模型；桩数 n 为投资变量（凸成本），无 kW/kWh/排队/服务水平约束；解析命题+图 2–7 | 不能支持本项目“整数 k + 服务率约束”；**在线附录证明未取得（p2 声明）→ 不能当证明**；图值未读数 | 模型结构 **已核实**；命题/附录 **UNVERIFIED** |
| M08 | Related work 段：San Diego 停车事件→充电记录；表1（PDF p5=印刷 p3）：BEV 1,421/4,974、PHEV 705/3,095、合计 2,126/8,069；表2 全部离家 16,557/232,083 | 观测使用率的停车事件分母；300 英尺内停车≠进入带枪位；无停留时长 | 不能当“潜在充电意愿”；分母与表1不同，不能混用；旧样本/两车型/美国 | 计数 **已核实**（笔记/PDF）；比率为本地复算 |
| M10 | Related work 段：训练/验证样本的可比充电率；Table 3 在 PDF p13 | 作者报告的训练 1,486/6,187、验证 469/2,062、合计 1,955/8,249=23.70%（本地比值复算）；用于 q_use 情景迁移 | 不是目标场景 q_need；自报、2017 荷兰、混合地点；不能当目标识别值 | 首页/版本 **已核实**；Table 3 数值据 M10 笔记已逐格核对，本轮未逐格重核；比率本地复算 |

- **已核实**：M18 修订稿文字明确“proofs sit in an online appendix that we did not obtain, so we cite the model structure and not its propositions”——与附录未取得一致，**不得**把 M18 命题当证明或当功率/服务约束依据。
- **发现（未改稿）**：M10 修订稿文字仍写“transcription ... provisional because only a search-index version was available”，但 `M10_TUE_fulltext.pdf` 已取得且 M10 笔记 2026-10-31 补记 Table 3 已逐格核对；该句已过时。另 `REFS` 中 M10 条目缺作者名单（“[author list to be completed from the publisher record]”），M06/M07 只有 “Hou et al.”/“Zhang et al.”，均需按出版商记录补全。
- **作者报告值 vs 本地重算 vs 模型假设**：M06/M07 的 gap/节时/仿真结果、M18 的命题与图值均为作者报告（后者证明未取得）；M08/M10 的分母计数为作者报告、比率为本地复算；`q_use→q_need`、`p_EV=0.10`、把观测使用率当潜在需求均为**模型假设**，必须带标签。

## 5 旧 ETP 编号 37–40、54、70–71

编号取自 rev3 docx 参考文献段（81 条）。当前 rev3 工作稿仍保留旧 Results/Methods 段（“Optimal PPR…”“Optimization Framework”“Evaluation protocol…”“Costs of unmet…”），因此这些编号目前不是孤引；若按修订计划删除旧结果/成本方法，它们将只剩这些旧段落引用。

| 编号 | 文献 | rev3 中的引用位置 | literature/index.json | 能否保留 |
|---|---|---|---|---|
| 37 | Chen, L., Huang, X., Zhang, H. & Luo, Y. A study on coordinated optimization of electric vehicle charging and charging pile selection. *Energies* 11, 1350 (2018). | Results“Optimal PPR under various operation modes”段（para 48），支撑 ICEing/建桩方式旧结果 | 未收录 | 若删除旧结果，不能保留；只能随“历史结果（submitted version，未用于修订结论）”段落保留并改写为历史证据 |
| 38 | Hu, Y., Jin, Y. & Zhang, S. Climate, Health Impacts, and Social Costs of Electric Vehicles in China: A Cost-Benefit Analysis. *Beijing Da Xue Xue Bao* 57, 916–926 (2021). | Methods“Optimization Framework”段（para 137），环境成本参数 0.085/0.24 | 未收录 | 可随明确标注的历史成本模型段落保留；需核中文期刊页码/参数口径 |
| 39 | Zhu, Y., Ye, X., Yang, Z., Li, M. & Chang, Y. Research on the Impact of Parking and Parking Behavior on Traffic Flow Based on VISSIM Simulation: Taking the Downtown Area of Ningbo as an Example. *CICTP 2020*, 3039–3050 (2020). | Methods“Optimization Framework”段（para 138），6 分钟寻位时间 | 未收录 | 同上（历史寻位时间参数）；会议论文页码需核 |
| 40 | Foshan Municipal Market Supervision and Administration. Departmental Budget (2024). URL: search.gd.gov.cn/... | Methods“Optimization Framework”段（para 142），巡航车辆数/预算参数 | 未收录 | 灰文献；只能随历史参数段落保留并标 URL/访问日期与不确定性 |
| 54 | Rockafellar, R. T. & Uryasev, S. Optimization of conditional value-at-risk. *Journal of Risk* 2(3), 21–41 (2000). | Methods“Evaluation protocol, statistical reliability, and risk measures”（para 181），0.95 CVaR | **P22**（`research/ev_parking_math_20261029/PDFs/P22_...pdf`） | 可保留为风险度量方法引用（历史评价段或现行评价段均可，若删 CVaR 段则删） |
| 70 | Shoup, D. Cruising for parking. *ACCESS Magazine* No.30 (Spring 2007): 16–22；Transport Policy 13(6):479–486 (2006) 的 reprint；期刊版未取得 | Methods“Costs of unmet parking and charging service”（paras 183, 191），寻位时间成本 | **P36**（ACCESS 30 reprint PDF） | 可随历史成本模型段落保留；必须按 reprint 标注，不能冒充期刊版 |
| 71 | Biswas, A., Gopalakrishnan, R. & Dutta, P. Managing overstaying electric vehicles in park-and-charge facilities. arXiv:1604.05471v2 (2016). | Methods“Costs of unmet parking and charging service”（paras 183, 193），占桩原因 | **P37**（arXiv PDF） | 可随历史成本/占桩段落保留；arXiv 版本需标注，会议版未核 |

- **已核实**：37–40 只出现在旧 Results/Optimization Framework 段，54 只在旧 Evaluation/CVaR 段，70–71 只在旧 Costs 段；均无现行结果依赖。
- **已核实**：54/70/71 在 literature/index.json 中有对应 P22/P36/P37；37–40 不在该索引（51 条中无匹配），只能以稿件参考文献段为准，书目细节 UNVERIFIED。
- **保留条件**：只有在修订稿保留一个**明确标注**的“历史模型/已提交版本，未用于修订结果”的段落，并在该段落内保留原公式与引用时，才能保留 38–40、54、70–71；37 绑定旧实证结果，删结果就应删引用。不得把历史段落的引用移作现行结果的支持证据。

## 6 UNVERIFIED 清单

- Q3 `both_disjoint` 的 5 个组未用新轨迹独立重跑；只核了既有曲线计数。
- Q2 只覆盖 2 场站、seeds 1–2、A/B；I1 是分析启发式，未评估可执行性/部署约束；同 k 下 2 个单元 I1 不可行。
- Q1 的真实停车场非单调性未验证；16 例中 13 例未提取轨迹。
- M18 在线附录证明、命题条件、图 2–7 数值未取得/未读数；不得当证明。
- M06/M07 的作者报告数值（gap、节时、表 8 MIP gap、杭州拟合参数）未复算；M06 作者页 2026 卷期以出版商记录为准。
- M10 的 Table 3 逐格数值来自笔记核对，本轮未重核；修订稿 M10 文字“仅有检索索引版”已过时。
- 37–40 的书目细节（页码/卷期/URL 访问日期）未用原始 PDF 核；40 为灰文献，70 期刊版未取得，71 会议版未核。
