# 第七轮结论一致性与论文精简报告（2026-10-31）

类型: 研究修订报告
状态: 已完成本轮修订与检查；未投稿、未升级为投稿定稿
负责人: lead（Team Lead）
日期: 2026-10-31

## 1 版本与结论

- 主稿：`paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx`；SHA-256 `5b4056db55ad3d42c9ff49fdb3d84fff545e1a8d868f7cb309b9cdd0e7c08a24`；36 页，178 段，1 图，5 张数据表，76 条参考文献。
- 补充材料：`paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round7.docx`；SHA-256 `c0260430d02babaa18e5cb45d65581527258fc08537031bdb0337748ad33b321`；9 页，S1–S7。
- 原稿、旧 Word（rev1/rev2/rev3、round6 SI）、原始数据与既有交付 JSON 未覆盖；旧稿完整版本保留。修订只改工作稿与补充材料，未做投稿、未生成对外沟通材料。
- 本轮主问题：在联合服务约束下，资源兼容规则与充电意向信号如何改变最小整数配置、可行集与服务权衡。Q1/Q2/Q3 被写成同一问题的三个相互关联结果；旧 v1 ETP/成本模型退出主结果与结论，只作为明确标注的历史模型保留。

## 2 实际改动

### 2.1 结构与精简

- 主文删除旧 v1 Results 五节（原 rev3 约 2,007 词）与旧 v1 Optimization Framework、Evaluation protocol、Costs of unmet service、Occupied charging bay 四节（原 rev3 约 4,000 词）；这些内容不再承载摘要、主结果或结论。
- 旧 v1 的成本/ETP 说明压缩为主文 Discussion 的“Relation to the earlier v1 model”短段（约 80 词，引用编号 37–40、54、70–71），完整历史说明放入 SI S7；旧数值、旧图和旧表不在新主文中重估或重述。
- 主文 Methods 保留并围绕新问题重写：资源/需求类别/准入规则、数据与情景、到达/占用/事件时间线、充电容量/功率/能量可行性、服务约束与整数配置、信息条件；删除旧 v1 目标函数与成本核算。
- Discussion 删除旧 v1 的 PPR/ETP 政策叙事与重复免责声明，改为三结果综合解读、历史 v1 关系、未使用方法说明、证据状态与限制。
- 加入“证据状态”段：固定 k 共享规则比较是唯一有独立留出种子的评价；Q2 是探索性算法比较；Q1 是确定性机制复现；Q3 是有限枚举。

### 2.2 Q2 符号与八单元核对

- 定义统一为 `Delta k = k(I1) - k(I0)`；负值表示 I1 在相同外生流下达到标准所需的最少带枪位更少，不再使用“负值意味着省枪/更多枪”的含糊解释。主文表 3 表头已改为 `Delta k`，表题、表注、结果段、讨论和 SI S4 均按同一方向表述。
- 逐项重算 8 个 lot-seed-rule 单元（4 条 lot-seed 流 × 规则 A/B）：

| lot | seed | rule | k(I0) | k(I1) | Delta k | category at k(I0) |
|---|---:|---|---:|---:|---:|---|
| TPE0008 | 1 | A | 9 | 4 | -5 | both |
| TPE0008 | 1 | B | 9 | 4 | -5 | both |
| TPE0008 | 2 | A | 7 | 5 | -2 | both |
| TPE0008 | 2 | B | 7 | 5 | -2 | both |
| TPE0401 | 1 | A | 20 | 6 | -14 | only_I0 |
| TPE0401 | 1 | B | 20 | 6 | -14 | both |
| TPE0401 | 2 | A | 25 | 8 | -17 | only_I0 |
| TPE0401 | 2 | B | 25 | 8 | -17 | both |

- 实际设备变化：I1 在这 4 条流上分别少 5、2、14、17 个带枪位；但其收益不是无条件的：在 TPE0401 两条流的规则 A 下，按 I0 选出的 k 在 I1 下不再可行（ICEV 停车失败率 7.69%/17.82%）。所以主文只写“该具体启发式降低所选计数”，不写“信息普遍改善服务”。
- A/B 两条规则在同一 lot-seed 流上给出相同的 k(I0)/k(I1)，8 个单元实际只有 4 条独立流；主文表 3 表题、表注和结果段已写明这一点，避免把 8 个单元当 8 次独立评价。

### 2.3 P1 适用范围

- 主文明确写出：P1 只适用于 strict no-fallback、A1–A6 的受限变体；不适用于主实验允许 EV 回落到普通位的 pi0。原文的“the decrease depends on the fallback”之外，新增一句“does not apply to the pi0 rule used in the main comparison ... and the paper does not export it to that model”。
- SI S2 同步声明：命题不适用于 pi0 回落模型；主文反例说明回落会反转方向。P1 的“差值计数耦合”证明、3,456 网格与 12,000 随机流只作为一致性支持，不当作证明或新颖性。

### 2.4 Q3 配对类型、边界与截断

- 主文与 SI S5 把三类比较分开：dedicated-vs-shared（A|B、A|C、A|D）、shared-vs-shared（B|C、B|D、C|D）、以及 Q2 的信息条件比较；不把三类数字加总，也不做跨类解释。
- 840 个 rule pairs（五个情景合并）中：

| 比较类型 | pairs | restoration | device saving | same-k improve | same-k worse | both disjoint |
|---|---:|---:|---:|---:|---:|---:|
| A|B dedicated-vs-shared | 190 | 0 | 0 | 2 | 0 | 2 |
| A|C dedicated-vs-shared | 90 | 0 | 0 | 2 | 0 | 2 |
| A|D dedicated-vs-shared | 190 | 0 | 0 | 0 | 0 | 1 |
| B|C shared-vs-shared | 90 | 0 | 0 | 0 | 0 | 0 |
| B|D shared-vs-shared | 190 | 2 | 1 | 0 | 3 | 0 |
| C|D shared-vs-shared | 90 | 2 | 1 | 0 | 3 | 0 |

- 两类小计：dedicated-vs-shared 470 对，restoration 0、device saving 0、same-k improve 4、same-k worse 0、disjoint 5；shared-vs-shared 370 对，restoration 4、device saving 2、same-k improve 0、same-k worse 6、disjoint 0。
- 两个 smaller 不是两个独立案例：均来自同一 REF 组 TPE1376/seed10 的 B|D 与 C|D；该组中 forecast-gated 共享规则从 k=2 可行、另两个共享规则需 k=24，专用规则也从 k=2 可行。它们是共享规则之间的分配顺序效应，不是共享相对专用的设备节省。
- 区间结论限定在完整枚举 0–40：660 组中非空集全为连续区间、0 断裂；严格空集 139/660，inclusive 空集 124/660（15 组由零需求约定决定）；437 组触及 40 边界，属边界截断，不外推更大 k。旧“全局区间”写法已删除。

### 2.5 五态语义

- 主文 Methods 与 SI S1 统一使用 valid / not_applicable_zero_demand / censored_no_departure / missing / illegal 五态：只有 valid 可满足约束；N/A 记录并在 inclusive 约定下跳过、strict 约定下不算满足；censored 能量只作辅助；missing/illegal 不静默跳过。
- 主文 Q3 段给出 780/765/66 与旧 310/严格 51 的口径对照，明确这些是 convention 差异，不是“修复前/修复后”。

## 3 独立评价状态

| 结论 | 设计 | 独立评价状态 |
|---|---|---|
| 既有共享规则（固定 k，A/B/D） | seeds 1–4 选 k，seeds 5–10 评价；40 runs、48 lot-rule cells | 独立留出评价；容量未服务 A 5.02%、B 6.49%、D 5.36%（EV 0.19/0.69/0.19；ICE 0.99/0.70/0.90）。方向在测试计数上得到留出支持，但仍限于一个情景/期间 |
| Q2 I0/I1 启发式 | 2 lots×2 seeds×2 rules，656 次；seeds 1–2 属 Round4 选择种子 1–4 内 | 无独立留出；同一批种子的探索性算法比较，不是独立评价 |
| Q1 机制与 P1 | 3 个最小事件级反例；3,456 网格 + 12,000 随机流 | 确定性复现/一致支持；不是统计评价，不能外推真实场站 |
| Q3 可行集与配对 | 660 组、840 对，完整 0–40 枚举 | 有限轨迹的完整枚举/描述性结果；437 组截断，不能外推到 0–40 以上或真实总体 |

- 旧共享规则结论有独立留出评价；不能笼统写“split-half 从未做过”。新 Q2 没有独立留出；不能拿旧规则验证为新策略背书。

## 4 旧 ETP/成本结果与引用处理

- 旧 v1 ETP/成本结果已撤出摘要、主结果和结论；主文只在明确标注的历史段提及其对象，完整说明在 SI S7。旧 ETP 数值不进入新主文，也不被限定词升级为新证据。
- 旧 v1 结果与其成本核算仍在 rev3 原文件中完整保留（旧稿未改），供溯源；本轮不重算、不调参、不改旧数值。
- 历史段只引用编号 37–40、54、70–71：37–40 为旧 ETP/成本相关来源，54 为 CVaR 来源，70/71 为旧成本项来源；这些编号在文献索引中没有对应 M 编号的，仅通过明确标注的历史模型段保留，不再作为新结果证据。
- M18：首页已核作者 Feng Chen、Valery Pavlov、Sitao Zhao、Jianghong Feng、Su Xiu Xu；TR-D 144 (2025) 104773；DOI 10.1016/j.trd.2025.104773；只引模型/信息集/目标形式，未取得的在线附录证明不作为证明。
- M10：首页已核 Kim, Rasouli, Timmermans, Yang (2022)，Transportmetrica B 10(1):340–367；主文参考文献 76 已补齐作者；文献索引 M10 版本更新为 TU/e fulltext 已取得、首页与 Table 3 已核。
- M06/M07：主文参考文献已补全作者；M06=Hou/Guo/Li (2026, ESWA 308:131133)，M07=Zhang/Gong/Tang/Mei/Feng (2025, TR-C 179:105259)；M08 保持 Idaho National Laboratory (2015, INL/EXT-15-36315)。
- 引用检查：76/76 双向，无越界/未引用/未解析；pending strings 0。索引重建 `scripts/lit_index.py --write` EXIT 0，0 错误、8 条历史警告。

## 5 字数与版式

统计口径：`scripts/paper_stats.py` 的英文词，不含表格/题注；正文为非参考文献段落。

| 范围 | rev3 | rev4 | 变化 |
|---|---:|---:|---:|
| 全部段落 | 17,418 | 10,768 | -6,650 (-38.2%) |
| 参考文献 | 1,643 | 1,660 | +17 |
| 正文（非 refs） | 15,775 | 9,108 | -6,667 (-42.3%) |
| 题注 | 352 | 281 | -71 |
| 表内文字 | 462 | 228 | -234 |
| 图/数据表 | 8 / 14 | 1 / 5 | 旧 v1 图 2–5、表 6 等退出主文 |

- 分节：Introduction 2,132（不变）；Results 4,409→2,665；Discussion 2,327→1,493；Methods 6,457→2,350；References 1,643→1,660。
- 主文 36 页；5 张数据表均单页且题注同页（Table 1 p10、Table 2 p12、Table 3 p13、Table 4 p15、Table 5 p23）；Fig. 1 p4。全页栅格 0 空白、0 文字越界。
- SI 9 页；S1/S3a/S3b/S4/S5a/S5b/S6 表分别 p1/p4/p4/p5/p6/p6/p8；0 空白、0 越界。

## 6 检查与版本快照

- `scripts/check_all.py`（DSH Python，含 python-docx）最终 EXIT 0；文档/字数/文献三项通过；历史警告保留，未改历史记录。
- `scripts/paper_stats.py` 工作稿统计 EXIT 0；报告 `paper_stats_rev3_recheck.md`、`paper_stats_rev4.md`。
- `scripts/lit_index.py --write` EXIT 0；`literature/index.json`、`literature/INDEX.md` 为本次生成式重建，旧索引备份哈希见 manifest；其余 359/361 冻结文件未变（2 个索引文件为有意重建）。
- 旧稿哈希：投稿版 `04bda311…`、rev3 `06906f34…`、rev2 `b2d36e2d…`、rev1 `fc1320b7…`、round6 SI `2ebc9e83…`，均与第六轮验收记录一致；旧稿 mtime/字节未改。
- Git：仓库无提交身份（user.name/email 为空），本轮不提交、不 `git add .`、不 push；版本快照采用任务目录复制 + SHA-256 清单：`research/manuscript_revision_20261031/snapshot/`，清单 `snapshot/MANIFEST.sha256`。

## 7 剩余限制（UNVERIFIED）

- 未做期刊模板像素级比对；仅对主文 36 页和 SI 9 页做全页栅格、题注页码、表格单页与关键页视觉检查。目标期刊未定，不编造投稿限制。
- M18 在线附录证明未取得，未作为证明；M10 的 Table 3 本轮未逐格重核（沿用既有笔记的核对记录，标 UNVERIFIED）。
- Q2 无独立留出评价；Q3 的 5 个 both-disjoint 组未重跑；Q1 的真实场站非单调性未验证。
- 旧 v1 ETP/成本结果未重算；其历史数值只保留在 rev3 与 SI S7 说明中，不作为新证据。

## 8 复现命令与解释器

- 主稿结构删减与文字修订：`build_rev4_stage1.py` → `build_rev4_stage2.py` → `polish_rev4.py` → `polish_table4.py` → `polish_table4b.py` → `unify_q2_delta.py`（均 EXIT 0；产物即上述 rev4）。
- SI：`build_si_round7.py` → `polish_si.py` → `polish_si2.py` → `update_si_hash.py`（均 EXIT 0）。
- Q2/Q3 只读重算：`q2_delta.py`、`q2_cells.py`、`q3_samek2.py`；原始 JSON 未改。
- 检查：DSH Python（3.12.14，含 python-docx）`scripts/check_all.py` EXIT 0；conda Python（3.12.3，PyMuPDF）`research/round6_20261031/lead/paper_render_check.py`；Word 16.0 COM `ExportAsFixedFormat(..., 17)`。
- 字数：`scripts/paper_stats.py` 对 rev3/rev4 分别输出 `paper_stats_rev3_recheck.md`、`paper_stats_rev4.md`。
- 快照：`make_snapshot.py` 复制主稿/SI/报告/统计/PDF 并生成 `snapshot/MANIFEST.sha256`；旧稿哈希同表。

## 9 产物索引

- 主稿：`paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx`
- SI：`paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round7.docx`
- 证据映射：`research/manuscript_revision_20261031/evidence_map.md`
- 渲染：`research/manuscript_revision_20261031/render/main_rev4.pdf`、`si_round7.pdf` 与 `main_pages/`、`si_pages/`
- 统计：`paper_stats_rev3_recheck.md`、`paper_stats_rev4.md`
- 版本快照：`snapshot/`（含主稿/SI 副本与 MANIFEST.sha256）