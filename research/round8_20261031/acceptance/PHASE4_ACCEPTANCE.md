# R8 Phase 4 独立验收报告（R8-G：metrics 分解、需求耦合、停留缩放、11.96% 显示、指标命名）

类型: 验收报告
状态: 生效（rev7 docx/SI/PDF 已存在，稿件项按已构建产物验证）
负责人: R8-D（独立验收者）
日期: 2026-10-31
写入域: research/round8_20261031/acceptance/**

## 0 快照与范围

- 验证时间：2026-10-31T20:05–20:15 +08:00；快照见 acceptance/evidence/phase4_results.json → snapshot（contract sha256 38b1422b…；含 metrics_v2、demand_coupling、dwell_scaling、per_stream_declared22、fit_metrics、content/build rev7 等 13 个文件 sha256）。
- 独立复算脚本：acceptance/evidence/phase4_checks.py → phase4_checks.out + phase4_results.json。只写 acceptance/**；未改被验文件。
- rev7 构建产物已出现并检查：paper/Electrification_tipping_point_v2_draft_rev7.docx（2,618,009 B）、…_supplementary_rev7.docx（1,504,527 B）、rev7_main.pdf、rev7_si.pdf；故任务 4/5 的稿件项不再 UNVERIFIED。

## 1 metrics_v2 分解与身份（任务 1）

| ID | 检查 | 结论 | 证据与观测 |
|---|---|---|---|
| METRIC-1 | declared max k 的身份与数字：charge_requests 137、gate+no_connector 1、shortfall 80、delivered 984.22、demand 1891.03、capacity_only_unmet 均值 58.35% | PASS | 从 per_stream_declared22.csv 独立重算：cr 137；gate 0 + no_connector 1；shortfall 80；delivered 984.221；demand 1,891.028；逐流 capacity_only_unmet 均值 0.583521（58.35%）；E4 declared22 policy A @ max-k 20 行同值（cap_unmet 和 80、capmean 0.583521、EV 失败 0/452、ICE 34/4,643）。身份：capacity_only_unmet =（admission 被拒 + 离场能量短缺会话）/charge_requests（service_metrics.py:186-201）；逐流 20/20 恒等 (gate+shortfall)/cr，无 no_connector 项。VM 2014-03-23 行：gate 0、noco 1、short 6、cr 10 → cap rate 0.6（=6/10，明确排除 no_connector）。 |
| METRIC-2 | “pooled 59.12%” 是否为 capacity_only_unmet 的池化值 | FAIL | 正确池化值 =（gate 0 + shortfall 80）/137 = 58.39%；59.12% 只有把 1 个 never-connected（no_connector=1，access/连接失败）也加进分子才成立（81/137）——与“capacity_only_unmet 由 gate 拒绝+能量短缺组成、不含 access failure”的定义矛盾。rev7 主稿正文确实写 “pooled value is 59.12%”（1 处），而同稿 Table 6 的 departed shortfall 行写 80/137=58.39%，SI S10 写 “80/137 = 58.4%” —— 三处互相矛盾。 |

补充：metrics_v2.py 有两个独立缺陷（见 NAME-3）：never_connected_rate 列公式写成 1 − admitted/charge_requests（admitted 是全部停车准入数，非充电请求准入数），20/20 行输出负值（−20.9、−55.0 等）；其身份校验代码用字符串 k 的 max() 比较且把差值对比 censored_sessions，实际未验证身份。

## 2 需求耦合（任务 2）

| ID | 检查 | 结论 | 证据与观测 |
|---|---|---|---|
| COUPLE-1 | 场景 B 保持请求数 6,588、EV 数、能量多重集 | PASS | 按 demand_coupling.py 同算法（seed=20261031，T 中位数/1 SD logistic 权重）独立重实现：A/B 均 n=6,588；契约 EV 总数 18,566（两者都是其子集）；sorted(E_A)==sorted(E_B)；需求总和 92,366.361 相等；B 请求集合与 A 不同。 |
| COUPLE-2 | A/B 的 22 kW 理想上界在 f∈{1,0.75,0.5,0.25} 复现 | PASS | 独立重算 8 个 A/B 值全部匹配 CSV：f=1 A 0.5509718/0.5980571，B 0.7092626/0.4209168；f=0.75 A 0.4535/0.5335，B 0.5640/0.3543；f=0.5 A 0.3365/0.4507，B 0.4016/0.2846；f=0.25 A 0.1944/0.3321，B 0.2179/0.1922（rounding 一致）。 |
| COUPLE-3 | 需求生成未被 P·T 截断、未删除请求 | PASS | 需求为 sum(E) 原值，理想上界只对交付量取 min(need, P·T)；全部 6,588 请求保留；DEMAND_COUPLING_PLAN §2 明文禁止 E=min(E,P*T) 生成与删除难服务请求。 |
| COUPLE-4 | dwell-conditioned 机制标注为 post-hoc、非本数据识别 | PASS | DEMAND_COUPLING_PLAN.md 标题性质：“在看到 R8 结果后制定的后续分析（不是原始预登记）”；C 机制“本轮未启用”；rev7 正文 “second demand mechanism as a post-hoc analysis, planned and dated before it was run”“a scenario, not a parameter identified from this data”。 |

## 3 停留缩放（任务 3）

| ID | 检查 | 结论 | 证据与观测 |
|---|---|---|---|
| DWELL-1 | dwell_scaling.csv 数值复算 | PASS | 12 行（scale 0.88/1.0/1.12 × A/B × f=1/0.5）全部按同一算法重算，4 位小数 0 处不符：A f=1：0.88→0.5255/0.6321、1.0→0.5510/0.5981、1.12→0.5726/0.5707；B f=1：0.6872/0.4575、0.7093/0.4209、0.7271/0.3936。 |
| DWELL-2 | ±12% 标注为压力测试而非 CI | PASS | 三处一致：demand_coupling.py 注释 “stress test, not CI”；PLAN §3.4“作为压力诊断（不是自动成立的置信区间）”；rev7 正文 “Scaling dwell by plus or minus 12% as a stress test … diagnostic range, not a confidence interval”。 |

## 4 11.96% 显示（任务 4）

| ID | 检查 | 结论 | 证据与观测 |
|---|---|---|---|
| REL-1 | {{rel_all}} 应显示 11.96% | PASS | 独立复算 split（seed=20261031）：cal mean 51.0631180692、test mean 44.9584131767；rel=(cal−test)/cal=0.1195521371→11.96%。E1/fit_metrics.csv dwell all 行 holdout_mean_rel_error=0.1195521371、mean_cal=51.063118、mean_test=44.958413（与 fit 一致）；content_rev7.py 将 rel_all 的 NUMBER_SPECS scale 设为 100、fmt {:.2f}，rev7 docx 显示 11.96%。 |
| REL-2 | 已构建 rev7 docx/SI 无 0.12% 残留 | PASS | rev7 draft 与 SI 文本：0.12% 各 0 次；11.96% 各 3 次；花括号 token/UNRESOLVED/SKELETON 各 0。SI 版本说明中有 1 处 “printed 0.12 where the value is 11.96%” 的有意更正叙述（无百分号，非显示值）；SI 表中仍写 “hold-out mean relative error 11.96%”（值正确）。 |
| REL-3 | 语义：hold-out vs calibration 均值差，不是预测误差；KS 不是均值一致的证据 | PASS（有 1 处措辞未落地，不构成错误断言） | 主稿：“hold-out-to-calibration mean dwell difference of 11.96%”“reported as a bias, not as an error of a predictive model”；SI：“descriptive comparisons between two blocks … not an out-of-sample …”；未发现把 KS 当作均值相等证据的断言。content_rev7 源码中 “KS statistic describes a distributional difference rather than an equality of means” 的目标段落属于 SI 文本替换（MAIN 里无匹配），rev7 docx MAIN 未出现该整句（0 次）——建议补入，但当前语义无误导。 |

## 5 指标命名/公式一致性（任务 5）

| ID | 检查 | 结论 | 证据与观测 |
|---|---|---|---|
| NAME-1 | rev7 不得把 capacity_only_unmet 叫 access 或 charging success；指标名 vs 公式 | PASS（除 METRIC-2 的 pooled 值） | rev7 主稿 “charging success” 0 次；指标分离明确：never-connected 1/137=0.73%、EV parking failure 0/452、ICEV 34/4,643=0.73%、departed shortfall 80/137=58.39%、energy shortfall 47.95%、capacity-only unmet mean 58.35%；SI 明写 “not an access measure”；未发现把 capacity-only 叫 access 的正面断言。pooled 59.12% 见 METRIC-2 FAIL。 |
| NAME-2 | 文中硬编码事实 vs 数据公式 | PASS | content_rev7._FACTS 全部由数据复算一致：cr 137、gate+noco 1、short 80、dlv 984.221、dem 1891.028、capmean 0.583521、EV 0/452、ICEV 34/4,643、conc n=792/median 2/p90 4/max 9（无 mismatch）。 |
| NAME-3 | metrics_v2.py 列名与公式一致 | FAIL | never_connected_rate = 1 − admitted/charge_requests：admitted 是全部停车准入数（约 158–221/流），charge_requests 是 2–11/流，故 20/20 行给出负“率”（−20.9、−55.0 等）。按 rev7/Table 6 定义 never-connected = (gate+no_connector)/charge_requests（0.73%）。该列输出错误，且 metrics_v2.py 的身份校验代码（k 字符串 max、implied_short vs censored）实际不验证任何东西。 |

## 6 结论

- 12 项 PASS：METRIC-1、COUPLE-1/2/3/4、DWELL-1/2、REL-1/2/3、NAME-1/2。
- 2 项 FAIL：METRIC-2（rev7 主稿 pooled 59.12% 把 1 个 never-connected/access 请求混入 capacity_only_unmet 分子；正确池化 58.39%，与自身 Table 6/SI 矛盾）、NAME-3（metrics_v2.py 的 never_connected_rate 公式错误、身份校验失效）。
- 建议：rev7 主稿 “pooled value is 59.12%” 改为 58.39%（或删除 pooled 句，保留 58.35% mean + 80/137=58.39%）；metrics_v2.py 改为 (gate+no_connector)/charge_requests 并做逐行恒等校验；修正后重跑/重建 rev7。

## 附录：证据

| 文件 | 内容 |
|---|---|
| acceptance/evidence/phase4_checks.py | 全部独立复算（metrics 身份、需求 A/B 重实现、dwell 缩放、11.96% split、rev7 docx 扫描、命名/事实核对） |
| acceptance/evidence/phase4_checks.out | 运行原始输出 |
| acceptance/evidence/phase4_results.json | 逐项结果 + 13 文件 sha256/mtime 快照 |
| acceptance/acceptance_phase4.json | 机器可读逐项结论 |
