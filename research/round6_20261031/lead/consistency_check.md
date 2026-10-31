# 第六轮二阶段：结论一致性核对与收紧依据（Lead）

日期: 2026-10-31　状态: 供 paper-c 执行修订用；本文件不是论文正文。

## 1 Q3 两个“省设备”案例定位（结论：表述需修正，但“专用 vs 共享无正 Δk”本身成立）

**同一组**: 场景 REF、场站 TPE1376、seed 10；两条共享规则配对 B|D 与 C|D（不是两个组，是两个配对比较）。四规则同一外生车流、同一配置生成；规则只改准入，不改到达/停留。

| 项 | 值 |
|---|---|
| A（dedicated_by_type, π0） | K = 2–5，min 2，无截断 |
| B（full_open_ice_first, π1） | K = 24–40，min 24，k=40 截断 |
| C（protected_quota, π3） | K = 24–40，min 24，k=40 截断 |
| D（predictive_shared_ice_first, π2） | K = 2–40，min 2，k=40 截断 |

- 两案例：B vs D、C vs D，D 在 k=2 可行而 B/C 需 24。**A vs D 同为 min 2，无节省**；所有 A（专用）对共享规则的行（A|B、A|C、A|D）second-only=0、smaller k=0。因此“专用规则 vs 共享规则没有正 Δk”不变；不需要改“无正 Δk”结论。
- 机制与口径：k=2 时 B/C 的 capacity_only_unmet_rate=0.5（2 个充电请求只服务 1 个，>α），D=0.0；ICE 失败率 B/C=0.0267、D=0.0400（均 ≤α）；EV 失败率均 0。k=24 时 B/C 的 cap=0.0。D 用**历史充电开始/离场估计的可见预测**决定是否放 ICE 进充电区（rules.py π2；不读 needs_charge），因此这是**同信息条件下两种共享规则的放行次序/预测门控差异**，不是“共享比专用省设备”，也不是充电意愿信息（I1）效应。
- N/A 语义：该组三条率的分母均非零（charge_requests=2、exogenous_ev_visits=5、exogenous_ice_visits=75），四个 K 在 inclusive/strict 下相同；两案例与 N/A/删失无关。约束为三约束（容量未服务、EV 失败、ICE 失败），α=0.05；能量第四约束不参与。
- 需要修正的是**论文把表 4 全部写成“first rule 是 dedicated”与“shared rule restores/lowers”**：Table 4 的 B vs C / B vs D / C vs D 三行是 shared-vs-shared；4 个 restored、2 个 smaller 全部来自 B|D 与 C|D；5 个 disjoint 全部来自 A 行。正文/摘要必须限定，不能读成共享省设备。

**Table 4 建议改法**（行标签明确配对类型）：
- 行改为 A vs B（dedicated vs shared）、A vs C（dedicated vs shared）、A vs D（dedicated vs shared）、B vs C（shared vs shared）、B vs D（shared vs shared）、C vs D（shared vs shared）。
- Note 改为：Only the A rows compare the dedicated rule with a shared rule. The B/C/D rows compare two shared rules under the same information condition; their restored/smaller-k cells are allocation-order effects, not device savings from sharing. The two smaller counts in B vs D and C vs D come from the same lot-seed group (TPE1376 seed 10), where the forecast-gated shared rule needs 2 equipped bays while the other shared rules need 24.
- 正文 §2.9 相应改成：A vs shared 行 second-only 0、smaller 0；restored 4、smaller 2 只在 B|D、C|D；据此不能写“shared rule restores/lowers”作为一般句。并明确“the two smaller counts are two pairwise comparisons on one group, not two independent groups”。

## 2 Q2 统一措辞：具体信息感知启发式，不是“最优信息价值”

- 策略是 AnalysisHeuristicPolicy：需要充电的当次 EV 优先带枪位、不充电 EV 优先普通位，ICE 沿用基础规则；I1 只多当次 needs_charge；I0 用未改 Simulation。它是**一个实现的启发式**，不是 I0/I1 的最优策略。
- 应统一写：a specific signal-aware heuristic / the tested heuristic that sees the current arrival's charging intention；结论是“该启发式在 8/8 单元把最小可行 k 降低（中位 9.5），但不是全占优；同 k 四类 143/26/61/98，k_min(I0) 处 2 个单元只有 I0 可行”。禁止“the value of information is negative / information saves equipment / information improves all rates / optimal”。
- 建议替换：§2.8 末句改为 “This is an algorithmic comparison of two implemented policies, not an estimate of the value of information: the I1 policy is one heuristic, and the reduction shows what it extracts from the signal under the tested rules.” Discussion §115 首句改为 “The second result concerns what a specific signal-aware heuristic delivers.” 并补 “We do not interpret the selected-count reduction as the value of information, which would require optima under both conditions.”

## 3 Q3 区间性限定：完整枚举的 0..40，边界截断单独标

- 660 组 = lot-seed-rule-scenario 组；K 在**完整枚举的 0..40** 内全为连续整数区间，0 断裂。437 组在 k=40 仍可行（截断）；124（inclusive）/139（strict）空集；15 组差异来自零需求 N/A 约定。
- 不能写“admissible sets are intervals”作为无范围的一般命题；应写 “within the enumerated range 0–40 … every non-empty set is a contiguous interval; 437 sets are truncated at 40, so the interval statement is a statement about the enumerated range, not about larger k.” 摘要/§2.9/§4/结论/局限统一此限定。
- 另注：k_max=40 是按规则的枚举上限；TPE0330 的 52–84 扩展只作边界示例，不并入 660 组。

## 4 P1 独立核对（发现 B 的证明表述有缺口；命题可修，但必须写全假设）

**B 原证明的问题**：其归纳假设写“k 与 k+1 中同一普通位 b 在同一时刻占用/空闲相同”，这不成立。反例（n=4, k=0→1，两辆 ICE 先后到达、dwell 10）：k=0 第一辆停 bay0、第二辆停 bay1；k=1 第一辆停 bay1、第二辆停 bay2。t=1 时 bay1 在 k=0 空闲、在 k=1 被占。故“镜像同址”耦合不能作为证明；B 的 3456 枚举 0 违反只能作为支持性检查，不能称作证明（B 报告自己也写了未做机器证明，但 §4 的证明文字需要修）。

**修正后的证明（支配/序保持耦合）**：
假设：(A1) N 固定，k→k+1≤N，bay k 由普通位改为带枪位；普通位 O_k={k..N−1}，带枪位 C_k={0..k−1}。(A2) strict no-fallback：EV 只用 C_k，ICE 只用 O_k；无车型转换；充电 EV 不占普通位。(A3) 纯损失制：不排队、不挪车、不预留、不抢占；找不到可兼容空位即离场记失败。(A4) 同一外生到达序列：到达时刻、车型、dwell 相同，离场=到达+dwell；充电能量/功率不影响普通位占用。(A5) 同一组内取编号最小的空位；同刻事件顺序在两系统中相同。(A6) 失败率分母=全部 ICE 到达数（与 k 无关），命题是逐轨迹而非分布。
命题：对同一到达序列，ICE 失败集合 fail(k) ⊆ fail(k+1)，失败数与失败率单调不减。
证明（容量差耦合）：EV 不进入普通位，故只比较 ICE 单类损失系统：S_k 有 m=N−k 个普通位，S_{k+1} 有 m−1 个。令 a、b 为事件前两系统普通位上的 ICEV 数，断言 0≤a−b≤1 恒成立。初始 0。离场按 A4：同一车两边都准入则两边各减一；只在 S_k 准入的车只减 a；不存在只在 S_{k+1} 准入的车（下证）。到达时 S_k 准入 iff a<m，S_{k+1} 准入 iff b<m−1。两边都准入或都拒绝则差值不变；若 S_k 准入而 S_{k+1} 拒绝，则 b=m−1，由 a−b≤1 得 a≤m，而准入要求 a<m，故 a=m−1，差变为 1；若 S_k 拒绝而 S_{k+1} 准入，则 a=m，由 a−b≤1 得 b≥m−1，又 b≤m−1，故 b=m−1，S_{k+1} 已满，矛盾。因此差值始终在 {0,1}，且不存在 S_{k+1} 单独准入。于是只要 S_{k+1} 准入（b≤m−2），就有 a≤b+1≤m−1<m，S_k 也准入。故 fail(k)⊆fail(k+1)；由 A6 分母固定，失败数与失败率单调不减。∎
- 该证明不使用最小号优先或车位编号匹配：只要求两类车互不占对方位、损失制、到达/停留相同、失败为即时拒绝。因此比模型假设更强，也更便于检查。
- 先前两个论证都不成立：B 的“镜像同址”假设有同址反例；本报告早先的“排序占位支配”也不成立（m=5、A 占 {0,1,2}、B 占 {1,3} 时 B 的 min free=2、A 的 min free=3，α≤β 失败）。SI S2 采用上面的容量差证明。
- 独立检查（只作支持，不代替证明）：Lead 自己的 strict 实现，3456 网格 0 违反；另 12,000 组随机小规模序列 0 违反；并复现了“同址占用”反例。B 的 base/回落模型仍可有 16 个下降反例，P1 只适用于 strict no-fallback 且 A1–A6。
- 论文写法：Results 只留命题+假设一句+“proof in Supplementary Note S2”；不能写“枚举证明”；不能宣称普适定理或新颖性；控制变量与逐事件轨迹移 SI S3。

## 5 论文修订清单（C 执行，Lead 验收）

1. 题名改为：Minimum integer charging provision in mixed-fleet parking: joint service constraints, an identifiability boundary, and conditional evidence on shared use and a charging-intention signal（不再用 information 暗示信息价值）。
2. 摘要：Q2 句改“a specific signal-aware heuristic … algorithmic comparison, not the value of information”；Q3 句加“within the enumerated range 0–40 … 437 truncated”；Q1 句加“a restricted no-fallback variant admits a proved monotonicity in the opposite direction (Supplementary Note S2)”；不得出现 optimal/social optimum 的肯定用法。
3. Results §2.7：P1 改为“restricted proposition + assumptions + proof in S2”；去掉“枚举支持=证明”的措辞；保留 3 条轨迹的计数表，逐事件表移 S3。
4. Results §2.8：策略名称/动作具体化；把“what the information could be worth”改为“what this heuristic extracts from the signal”；结论句保持算法比较。
5. Results §2.9 + Table 4：按 §1 修正配对类型/Note/正文；明确 4 restored、2 smaller 只在 B|D、C|D，且来自同一 TPE1376 seed10 组；A 行 second-only=0、smaller=0；fixed-k Table 1 的 shared-only=0/dedicated-only=3 可作旁证。
6. Results §2.9/摘要/讨论/结论/局限：所有 interval 断言加“within the enumerated 0–40”；437 截断、空集 124/139、15 组 N/A 差异保留。
7. Discussion §115：按 §2 改写；§116 加区间范围限定；Limitations §118：P1 假设、0..40、437、两案例仅为同一组两配对。
8. Conclusion §93：把“shared rule did not systematically reduce…”改为“no dedicated-vs-shared pair reduced the minimal count; the only two smaller counts arose between two shared rules on one group”，并加“within 0–40”。
9. 可复现段/证据等级段：把脚本、哈希、审计细节移 SI S6，正文只留一句指针；M18 仅引模型/信息集、M10 provisional 不变。
10. 正文引用 “Supplementary Notes S1–S6（separate file）”；SI 文件另建，不改正文论证。

## 6 补充材料结构（新 docx）

S1 语义与五态口径（valid/N/A/censored/missing/illegal；780/765、66、310/51；三约束/四约束；N/A 计数）。
S2 P1 命题、全部假设（A1–A6）、修正证明、B 原证明缺口反例；枚举只作支持；无普遍性宣称。
S3 三条最小轨迹的逐事件表（E1/E2/E3，来自 b_mechanism §3）、控制变量表、16 反例身份与边界。
S4 Q2 每单元 8 行（K_I0/K_I1/Δk/四类计数/2 个 only-I0 单元）、I1 策略定义、mimic/授权/泄漏验收。
S5 Q3 完整 K 集合/空集/截断/REF A–D 四类口径、表 4 全配对行、TPE1376 seed10 两案例细节。
S6 审计：冻结哈希、命令/解释器/退出码/输入哈希、旧稿/主稿未覆盖、引用核对、渲染检查记录。

## 7 构建、引用、渲染与验收（C 提交证据）

- 新稿另存：paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx；旧 _round6.docx 不得覆盖；构建脚本另存 rev2，输出/manifest/统计另存 c_paper/（旧 build_manifest 保留）。
- 新 SI：paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx。
- 引用：76/76 双向；无悬空编号；M06/M07 作者数值与本地复算分开；M18 只引模型/信息集；M10 provisional。
- 渲染：Word COM 导出 PDF；逐页渲染 PNG 检查（空白页、题注同页、表跨页、文字越界、页脚/页眉）；报告页数与异常；C 无 LibreOffice 时用 Word COM + PyMuPDF。
- 回传：新 docx SHA-256、段/表/图/文献/公式/页数、paper_stats、PDF 页数、逐页检查摘要、旧稿 SHA/mtime 未变、build manifest。
