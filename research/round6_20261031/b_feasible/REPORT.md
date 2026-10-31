# 第六轮 B：Q3 可行配置集合 K_(π)

类型: 研究证据（既有曲线重分析）
状态: 完成（660 组完整 k=0..40；0 条新仿真轨迹）
日期: 2026-10-31
负责人: mech-b（叶子执行者）
写范围: 仅 research/round6_20261031/b_feasible/；只读 round3/round4 结果 JSON。

## 0 结论摘要（先分三态）

**确定**
1. 660 个 (情景, 规则, lot, seed) 组，全部有完整 k=0..40：round3 main 4 规则×90 组 + round4 scenario（REF/M08-NEAR-BEV/M08-NEAR-COMBINED/M10-OUT-OF-HOME/M08-ALL-AWAY-REF）×A/B/D×25 组。
2. 按“三项均 valid 且 ≤0.05”的 strict 语义：非空集合 **全部是连续整数区间（536 组；0 断裂）**，空集 139 组；按“零需求 N/A 视为不违反”的 inclusive 语义：非空 536 组、空集 124 组、断裂仍 0。15 组差异全部来自 M08-ALL-AWAY-REF（零充电需求，capacity 约束 N/A）；按契约 N/A 不判 achieved，故 strict 为空，不把这类组报成“可行”。
3. 437/660 组的 K 含 k=40（truncated_at_kmax，无法排除 k>40 仍可行）；124 组在 0..40 为空，对 k>40 标 unknown_beyond_kmax（TPE0330 另有 41..200 扩展，见 §4）。
4. 跨规则不互相包含：REF 下 A（π0）与 B（π1）有 2 组“双方均非空但 K 交集为空”（TPE1376 seed10：A=[2..5]、B=[24..40]；TPE1380 seed3：A=[23..25]、B=[27..40]）；A 与 D、B 与 D 也各有 1 组双方可行但不相交。A/B 还有 3 组“只有 A 可行、B 为空”；无“只有 B 可行”的组。
5. 四类配对全保留（REF A/B）：双方可行 72、仅 A 3、仅 B 0、双方不可行 15；A/D：74/1/0/15；B/D：72/0/2/16。没有“部分重叠”（partial_overlap=0）。
6. 区分三类收益：**恢复可行性** 2 组（B 空、D 非空：TPE1376 seed2、TPE1380 seed7）；**省设备** 1 组（同 k 口径下 D 的最小可行 k=2 < B 的 24，TPE1376 seed10）；**同 k 服务改善** 2 组（TPE0401 seed2 k=25 worst 0.0198→0.0099；seed6 k=28 0.018→0.009，A→B）。共享本身（A vs B）**没有**省设备：0 组。
7. TPE0330：A(π0) 在 0..40 仅 seed3 可行（K=[32..40]，truncated）；其余 9 个 seed 在 0..40 为空。既有扩展文件（k=41..200）给出首可行 k=52–84（逐 seed），到 200 仍未截断出“必可行”，**k>40 与 >200 都按预算截断标记**，不并入 [0,40] 的 K。

**UNVERIFIED**
- 未跑任何新轨迹（0 条；任务上限 2 条）。K 只来自既有曲线，未对“双方可行但不相交”“D 恢复”等单元独立重跑。
- 只算三项约束（capacity_only_unmet_rate、EV/ICE parking_failure_rate），不含能量约束；语义入口 A 的 service_semantics.py 本轮尚未就绪，用 round5 none_semantics_4way 的等价实现（见 §1），未与 A 实现做逐行对拍。
- fixedk 文件只有 6 个 k/组，不能构成 K，本报告未用于 K 形状；场景扩展（M08/M10）是既有情景迁移，不是真实场站实测。

## 1 语义与输入

- 语义入口：A 的 apps/parking_lab/workbench/service_semantics.py 尚未就绪；本脚本按 round5 review/none_semantics_4way（及 audit_joint_k.rate_cell）等价实现：
  - capacity_only_unmet_rate：row.capacity_only_unmet_rate / row.charge_requests；分母=0 且 charge_requests=0 → N/A；
  - ev/ice_parking_failure_rate：row.service_metrics.rates.* / denominators.exogenous_ev_visits|exogenous_ice_visits；分母=0 → N/A；
  - rate=None 且分母>0 → missing；非有限/越界 → illegal；missing/illegal 不跳过判 achieved。
- 实际分类：660 组中 **missing=0、illegal=0、undecidable=0**；N/A 只出现在 15 个 M08-ALL-AWAY-REF 组（capacity 分母=0）。
- 输入：research/round3_20261031/results/main_{A_pi0,B_pi1,C_quota,D_pi2}_ref_s10.json；research/round4_20261031/results/scenario_*_s5.json（12 条）；扩展 research/round3_20261031/results/expand_A_pi0_TPE0330_s10.json（只作 §4，不并入 K_40）。
- 命令：C:/anaconda/python.exe research/round6_20261031/b_feasible/feasible_sets.py（exit 0）；解释器 Python 3.12.3（C:/anaconda/python.exe）。
- 输出：q3_feasible_sets.json、q3_run.log、本报告；输入/输出哈希见 run_record.json。

## 2 集合形状（按情景×规则）

| 情景 | 规则 | 组 | 空集(incl/strict) | 连续区间 | 断裂 | K 含 40 | min k 中位/范围 |
|---|---|---|---|---|---|---|---|
| REF | A | 90 | 15 / 15 | 75 | 0 | 29 | 10 / [1,29] |
| REF | B | 90 | 18 / 18 | 72 | 0 | 72 | 10 / [1,29] |
| REF | C | 90 | 18 / 18 | 72 | 0 | 72 | 10 / [1,29] |
| REF | D | 90 | 16 / 16 | 74 | 0 | 73 | 10 / [1,29] |
| M08-NEAR-BEV | A | 25 | 5 / 5 | 20 | 0 | 7 | 9 / [1,24] |
| M08-NEAR-BEV | B/D | 各 25 | 5 / 5 | 20 | 0 | 20 | 9 / [1,24] |
| M08-NEAR-COMBINED | A | 25 | 5 / 5 | 20 | 0 | 7 | 7 / [1,24] |
| M08-NEAR-COMBINED | B/D | 各 25 | 5 / 5 | 20 | 0 | 20 | 7 / [1,24] |
| M10-OUT-OF-HOME | A | 25 | 5 / 5 | 20 | 0 | 7 | 7 / [1,22] |
| M10-OUT-OF-HOME | B/D | 各 25 | 5 / 5 | 20 | 0 | 20 | 7 / [1,22] |
| M08-ALL-AWAY-REF | A/B/D | 各 25 | 4 / 9 | 21 | 0 | 8/21/21 | 4 / [0,32] |

（空集列第一个数是 inclusive，第二个是 strict；后者多出的 5 组/规则 ×3 规则 = 15 组全部在 M08-ALL-AWAY-REF：容量约束分母=0 属 N/A，按契约不判 achieved，故 strict 为空、inclusive 仅作形状记录。全部非空集合均为单一连续区间，没有“中间断裂”。）

- min_known_feasible 与 confirmed_minimal 分开记录：本轮所有非空组都因完整枚举 0..40 且 k_min−1 不可行而 confirmed_minimal=true（k_min=0 的 15 组也确认下界）；k=40 仍可行时另记 truncated_at_kmax=true。空集组 confirmed_minimal=false、unknown_beyond_kmax=true。
- 437 组 K 含 40：B/C/D 明显多于 A（B 153/190、D 154/190、A 58/190），说明“在 40 枪内仍满足三约束”的组在共享规则下更多，但这**不等于**共享省设备（见 §3）。

## 3 跨规则关系与四类可行性

### 3.1 REF 主曲线（同到达/同 seed，仅规则不同）

| 对 | 双方可行 | 仅前者 | 仅后者 | 双方不可行 | 双方可行但不相交 | 互有重叠但互不包含 | 恢复(前空/后非空) | 省设备(后 min<前) | 同 k 改善 |
|---|---|---|---|---|---|---|---|---|---|
| A vs B | 72 | 3 | 0 | 15 | 2 | 0 | 0 | 0 | 2（B 更优） |
| A vs C | 72 | 3 | 0 | 15 | 2 | 0 | 0 | 0 | 2（C 更优） |
| A vs D | 74 | 1 | 0 | 15 | 1 | 0 | 0 | 0 | 0 |
| B vs C | 72 | 0 | 0 | 18 | 0 | 0 | 0 | 0 | 0 |
| B vs D | 72 | 0 | 2 | 16 | 0 | 0 | 2 | 1 | 0（同 k 更差 3） |
| C vs D | 72 | 0 | 2 | 16 | 0 | 0 | 2 | 1 | 0（同 k 更差 3） |

关键例子：
- 双方可行但不相交：TPE1376 seed10 A K=[2,3,4,5]、B K=[24..40]；TPE1380 seed3 A=[23,24,25]、B=[27..40]。**不能把“共享可行集更大”写成普遍关系。**
- 仅 A 可行：TPE0930 seed6（A=[15..25]）、TPE1376 seed2（A=[4..12]）、TPE1380 seed7（A=[19]）。
- B/D 恢复：TPE1376 seed2（B 空、D=[4..40]）、TPE1380 seed7（B 空、D=[19]）；D 省设备：TPE1376 seed10（D min=2，B min=24）。
- 同 k 改善（A→B）：TPE0401 seed2 k=25、seed6 k=28；但 B 在这两组的 K 延伸到 40，因此“同 k 改善”和“集合包含”是两种不同陈述，分开记录。
- 若在 B 的最小可行 k 处比较 B/D，D 反而更差的 3 组（TPE0401 seed2/6、TPE1376 seed10）：D 的收益在别的 k 上，不能写成“D 处处更好”。

### 3.2 round4 情景（A/B/D）

5 个情景×25 组中，A/B/D 的可行集在每组内均为“相等（5 组）或 B/D ⊇ A（20 组）”，无空集差异之外的跨规则类别；M08-ALL-AWAY-REF 的 4 个“双方不可行”组是三约束在 40 枪内仍不满足（零充电需求下，k 增大使普通位收缩，ICE 失败升到 5% 以上），不是 N/A 误判。

## 4 TPE0330 的预算截断（不并入 K_40）

- main A(π0) 0..40：seed3 K=[32..40]（truncated_at_kmax）；其余 9 seed 空。
- 既有扩展 expand_A_pi0_TPE0330_s10.json（k=41..200，与 main 同一来源参数、但为独立扩展脚本输出）：首可行 k = seed1 70、s2 75、s3 73、s4 64、s5 64、s6 77、s7 61、s8 84、s9 52、s10 70；k_max_tested=200，**>200 仍标预算截断**，不能写“必可行”或“最小 k=…”。
- 因此对 TPE0330：0..40 的结论与 41..200 的扩展分开；任何全城/全局最小 k 断言都不成立。

## 5 三类收益与集合证据的分界（避免混称）

1. **恢复可行性**：仅由 B 空、D 非空定义（2 组）。它说明“换规则后集合从空变非空”，不是“共享本身恢复”。
2. **省设备**：仅由双方 K 的 min_k 比较定义（B/D 1 组）；A/B 为 0，故“共享省设备”在本数据不成立（与第三/四轮 Δk 结论一致）。
3. **同 k 服务改善**：固定同一 k 比较三率最差值（A→B 2 组）；它可以在集合不扩张甚至不相交时发生，故不能替代 K 的包含关系。
4. 四类配对（both/only first/only second/neither）全部保留并计数，不只报双方可行样本；每类例子见 JSON 的 pairs[*].examples。

## 6 边界与未验证

- 未跑新轨迹：本轮 K 全部来自既有完整曲线；任务允许 ≤2 条验证轨迹，但既有曲线已由第三/四轮交付与第五轮 1025 行配置复核，新跑不会改变集合形状结论；如需独立重跑“双方可行但不相交”的 2 组，应在下一轮用 runner 做 2 条验证轨迹。
- 语义入口未与 A 的新实现逐行对拍；若 A 实现改变 N/A/missing 处理，15 个零需求组的 strict/inclusive 差异需重算。
- 不含能量约束、不含真实场站外推；fixedk 文件仅 6 个 k/组，本报告未用于 K。
- 扩展文件与 main 的来源一致性：两者 meta 参数相同、脚本不同；本报告按既有记录引用，未复跑核对（UNVERIFIED）。

## 7 证据文件

- q3_feasible_sets.json：660 组逐 k 判定、K/K_strict、形状字段、跨规则 pairs、TPE0330 扩展。
- q3_run.log：脚本原始输出（exit 0）。
- feasible_sets.py：只读重分析脚本（可复跑）。
