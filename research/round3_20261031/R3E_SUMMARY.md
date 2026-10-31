# round3_20261031（R3-E 审计与查新）

类型: 审计与查新交付
状态: 生效
负责人: ev-data
日期: 2026-10-31

第三轮只读审计，未改旧稿件/第二轮证据/采集器；全部文件在本目录。

## 1 产物与命令

| 文件 | 命令 | 退出码 | sha256[:16] |
|---|---|---|---|
| audit_round2.py | python research/round3_20261031/audit_round2.py | 0 | 见下方 \
| audit_round2.json | 同上（脚本生成） | 0 | |
| CONSISTENCY.md | 同上（脚本生成） | 0 | |
| multiday_audit.py | python research/round3_20261031/multiday_audit.py | 0 | |
| data_audit.json | 同上（脚本生成） | 0 | |
| novelty_check.md | 人工（web_search/web_fetch 记录） | — | |

## 2 关键数字

**第二轮一致性（audit_round2.json）**
- p_EV=0.20：至少一个 seed 达 k5 = **8/9**，两个 seed 都达 = **7/9**；TPE0330 未达（infeasible_upper_bound），TPE0401=39 仅 seed1 达 → "9/9" 不成立。
- p_EV=0.30：至少一个 seed 达 = **5/9**，三个 seed 全达 = **4/9**；k5 摆幅 TPE0008=11、TPE0610=4、TPE0695=22、TPE1376=7，TPE1171 仅 1/3 seed → "seed 摆幅 2-6" 不成立（4-22）。
- rules_v2：observed_calibrated **无高饱和**（0.197/0.347 不饱和，0.769/0.799 临界，最高 0.799）；0.93-0.98 的 4 个情景全属 synthetic_range（0.933/0.950/0.953/0.942），另 synthetic_stress=0.980；"实测高饱和...39-61" 标签错误，参考 k 下 π2 selected 放行为 48-82，observed 临界 gate=0。
- TPE1171：fitted_parameters.json 与当前 calibration_report 一致为 **4 个可用 validation**（含 TPE1171；rel_err=-21.4% 在 25% 阈值内）；"3 个"来自旧 _scratch/cal.log（rel=-25.6% → UNUSABLE）。
- 资本公式：capex/寿命/365 与 annual/365 两条分支正确；facility_cost(1,1日)=**75.2976767**，(0.5日)=**37.6488384**，曲线 1440/720 同值 2:1；k=0 为 0。

**多日数据（data_audit.json，快照读取）**
- 日期目录：2026-10-30（147 批）+ 2026-10-31（160 批），共 307 个 5min 槽，实际跨度 2026-10-30T03:30Z–2026-10-31T05:15Z（25.75h）。
- 372 场覆盖：每批 372 行（min=max=372），两个文件均 372 个 parking_id；无 (slot,lot) 重复行。
- 缺测/重复：data_missing 行 2,214 + 1,746；duplicate_batch 标记行 2,604 + 744；(slot,lot) 重复=0；5min 序列缺 3 槽（10-30T03:35Z、07:10Z、07:15Z）与 2 处断档（10min、15min）。
- 断档/边界：10-30 本地 11:30–23:55（147/150 槽，98%）；10-31 本地 00:00–13:15（160/160 槽，但仅到 13:15）。
- **整日留出：不满足**。无任何完整 24h 本地日；只有两个日期目录、合计 25.75h；需要至少 2 个完整日（576 槽）才能做整日留出。
- 采集器仍在追加（读取时快照），commits=147/160、raw gz=134/157（部分批次无 raw 文件）。

## 3 查新结论

- N1 Chen et al. 2025 TR-D 144:104773（joint operation of parking and charging；三种建桩策略 P/D/C）直接重叠"共享运营/联合投资"，**不能再声称空白**；N2（TR-C 2025 共享充电+停车预约）、N3（SEPS 2026 DRO）题录级、摘要 403 UNVERIFIED；N4 TRID 稳健规划摘要部分可读。
- 建议登记 M18-M20，但本轮写权限不含 literature/，未写笔记/未跑 lit_index；详见 novelty_check.md。

## 4 未验证

- ScienceDirect 两篇摘要 403；N4 期刊/年/DOI 未核；p_EV 不可识别与情景解边界见 model_20261031_v2.json / CONTRACT §5。
- 审计不重跑 5226 次仿真、不重算轨迹哈希；只复算数值与文字一致性。
