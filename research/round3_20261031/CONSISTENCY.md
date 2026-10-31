# 第二轮一致性审计（R3-E）

类型: 审计证据
状态: 生效
负责人: ev-data
日期: 2026-10-31

命令：python research/round3_20261031/audit_round2.py（只读；本文件由脚本生成）
机器结果：audit_round2.json。k5 定义与 analyze_v2/compare_v2 一致（alpha=0.05，hard_max=min(n_spaces, 最大 k)）。

## 1 逐条对照

| 编号 | 原表述 | 机器结果 | 判定 |
|---|---|---|---|
| R2-A-9OF9 | p_EV=0.20 时 9/9 达 k_5 | 至少一个 seed 达 8/9；两 seed 都达 7/9；TPE0330 未达；TPE0401 仅 1/2 seed | corrected |
| R2-B-SEEDSPREAD | p_EV=0.30 时 5/9，seed 摆幅 2-6 | 至少一个 seed 达 5/9；三个 seed 全达 4/9；摆幅 TPE0008=11、TPE0610=4、TPE0695=22、TPE1376=7；TPE1171 仅 1/3 seed | corrected |
| R2-C-OBS-HIGHSAT | 实测高饱和 0.93-0.98 触发闸门 39-61 | observed 无高饱和（最高 0.799）；0.93-0.98 全属 synthetic_range/stress；参考 k 放行 48-82；observed 临界 gate=0 | corrected |
| R2-D-TPE1171 | 报告文字列 3 个验证可用 | fitted/报告均 4 个可用 validation；TPE1171 rel_err=-21.4%（<25%）；3 个来自旧 cal.log（-25.6%） | partially_unsupported |
| R2-E-CAPITAL | 资本公式年->日正确 | 两条公式分支正确；1440/720 的 facility=75.2997/37.6499；k=0=0 | confirmed |

## 2 更正后结论

### R2-A-9OF9（corrected）

- 原表述：报告 §14.3（docs/reports/2026-10-31-整数配桩规则与仿真验证.md 第 250 行）：p_EV=0.20 时 9/9 达 k_5（TPE0401=39 为边界）
- 更正：改为：p_EV=0.20 时 8/9 场站至少一个 seed 达 k5；7/9 两个 seed 都达。TPE0330 两 seed 均 infeasible_upper_bound（k<=40 未达）；TPE0401=39 仅 seed1 达、seed2 未达（39 距上限 40 仅 1，属边界但非两 seed 一致）。原文 9/9 与自身列出的 8 个数（TPE0330 缺失）矛盾。

### R2-B-SEEDSPREAD（corrected）

- 原表述：报告第 239 行与《第二轮修复与复算》第 15 行：p_EV=0.30、α=5%、上限 40 下 9 个可用场站中 5 个达到 k5（TPE0008=14、TPE0610=3、TPE0695=15、TPE1376=19、TPE1171=39；seed 间摆幅 2-6）
- 更正：改为：p_EV=0.30 时 5/9 场站至少一个 seed 达 k5；仅 4/9（TPE0008/TPE0610/TPE0695/TPE1376）三个 seed 全达；TPE1171 只有 1/3 seed 达（39），中位数 39 由单 seed 得出。seed 摆幅不是 2-6：TPE0008 11（5-16）、TPE0610 4（2-6）、TPE0695 22（10-32）、TPE1376 7（18-25）；TPE1171 无可比摆幅。

### R2-C-OBS-HIGHSAT（corrected）

- 原表述：rules_v2.md §2：实测高饱和情景（普通位占用 0.93-0.98）里 π2 闸门被真实触发（每次运行 39-61 辆 ICE 被放行）；同文覆盖表把 observed_calibrated 的高饱和标为 —
- 更正：更正：覆盖表正确——observed_calibrated 无高饱和（0.197/0.347 不饱和，0.769/0.799 临界，最高 0.799）。0.93-0.98 的 4 个情景（0.933/0.950/0.953/0.942）全部是 synthetic_range，另 synthetic_stress=0.980 也高饱和；都不是实测。observed 临界情景参考 k 下 π2 放行=0，不能作预测有效性证据；这 5 个合成/压力情景在 π2 selected(10min,0) 参考 k 的放行数为 48-82，不是 39-61。

### R2-D-TPE1171（partially_unsupported）

- 原表述：报告第 39 行：traffic-gen 报告文字列 3 个验证可用，差异在 TPE1171，以 fitted_parameters.json 的 usable 字段为准
- 更正：结论：fitted_parameters.json 的 usable=True 与当前 calibration_report 一致（可用 validation 4 个，含 TPE1171；rel_err -21.4% 在 25% 阈值内）。3 个的来源是更早的 _scratch/cal.log（rel=-25.6% -> UNUSABLE）旧快照，不是当前报告文字；主报告第 39 行应改为“当前 4 个可用验证场站，TPE1171 仅 3 次会话，样本极少”。

### R2-E-CAPITAL（confirmed）

- 原表述：设施资本公式年->日在代码中正确（年度折旧/365 或 capex/寿命/365；k 与天数只乘一次）
- 更正：确认：device_capital = k*(capex/寿命/365)*days 与 annual/365 两条分支都正确；成本曲线 1440min 与 720min 的 facility_cost 成 2:1（75.2997 vs 37.6499），说明天数按 elapsed_min/1440 换算且未重复乘；k=0 为 0。

## 3 p_EV=0.20 逐场站 k5（curve: cost_curve_v2_pev020_usable.json）

| 场站 | n_spaces | k5 各 seed | 状态 | 达到数 | 范围 |
|---|---|---|---|---|---|
| TPE0008 | 76 | 12/5 | achieved/achieved | 2/2 | 7 |
| TPE0330 | 851 | None/None | infeasible_upper_bound/infeasible_upper_bound | 0/2 | None |
| TPE0401 | 205 | 39/None | achieved/infeasible_upper_bound | 1/2 | None |
| TPE0610 | 43 | 1/5 | achieved/achieved | 2/2 | 4 |
| TPE0695 | 146 | 19/10 | achieved/achieved | 2/2 | 9 |
| TPE0930 | 175 | 26/33 | achieved/achieved | 2/2 | 7 |
| TPE1171 | 231 | 32/40 | achieved/achieved | 2/2 | 8 |
| TPE1376 | 73 | 15/14 | achieved/achieved | 2/2 | 1 |
| TPE1380 | 170 | 36/30 | achieved/achieved | 2/2 | 6 |

## 4 p_EV=0.30 逐场站 k5（curve: cost_curve_v2_pev030_seeds123.json，仅 9 个可用场站）

| 场站 | n_spaces | k5 各 seed | 状态 | 达到数 | 范围 |
|---|---|---|---|---|---|
| TPE0008 | 76 | 14/5/16 | achieved/achieved/achieved | 3/3 | 11 |
| TPE0330 | 851 | None/None/None | infeasible_upper_bound/infeasible_upper_bound/infeasible_upper_bound | 0/3 | None |
| TPE0401 | 205 | None/None/None | infeasible_upper_bound/infeasible_upper_bound/infeasible_upper_bound | 0/3 | None |
| TPE0610 | 43 | 6/2/3 | achieved/achieved/achieved | 3/3 | 4 |
| TPE0695 | 146 | 15/10/32 | achieved/achieved/achieved | 3/3 | 22 |
| TPE0930 | 175 | None/None/None | infeasible_upper_bound/infeasible_upper_bound/infeasible_upper_bound | 0/3 | None |
| TPE1171 | 231 | 39/None/None | achieved/infeasible_upper_bound/infeasible_upper_bound | 1/3 | None |
| TPE1376 | 73 | 18/25/19 | achieved/achieved/achieved | 3/3 | 7 |
| TPE1380 | 170 | None/None/None | infeasible_upper_bound/infeasible_upper_bound/infeasible_upper_bound | 0/3 | None |

## 5 rules_v2 分层与闸门（机器复算）

| 情景 | 族 | 普通位占用 | 分层 | 参考 k | π2 selected 放行(各 seed) |
|---|---|---|---|---|---|
| train_amp_TPE0008_x2.0 | amplified_calibrated | 0.722 | critical | 34 | [] |
| val_amp_TPE0008_x3.0 | amplified_calibrated | 0.794 | critical | 47 | [64, 71] |
| val_amp_TPE0401_x1.5 | amplified_calibrated | 0.910 | high_saturation | 48 | [0, 0] |
| val_amp_TPE1380_x1.3 | amplified_calibrated | 0.909 | high_saturation | 46 | [0, 0] |
| train_obs_TPE0008 | observed_calibrated | 0.347 | unsaturated | 13 | [] |
| train_obs_TPE0610 | observed_calibrated | 0.197 | unsaturated | 5 | [] |
| val_obs_TPE0401 | observed_calibrated | 0.769 | critical | 48 | [0, 0] |
| val_obs_TPE1380 | observed_calibrated | 0.799 | critical | 27 | [0, 0] |
| train_syn_crit_pe20 | synthetic_range | 0.724 | critical | 14 | [] |
| train_syn_crit_pe40 | synthetic_range | 0.689 | critical | 22 | [] |
| train_syn_unsat_pe20 | synthetic_range | 0.215 | unsaturated | 8 | [] |
| train_syn_unsat_pe40 | synthetic_range | 0.175 | unsaturated | 11 | [] |
| val_syn_amp_crit_pe40 | synthetic_range | 0.953 | high_saturation | 39 | [59, 73] |
| val_syn_high_pe20 | synthetic_range | 0.933 | high_saturation | 20 | [79, 65] |
| val_syn_high_pe40 | synthetic_range | 0.950 | high_saturation | 38 | [58, 66] |
| val_syn_lowev_amp_pe08 | synthetic_range | 0.942 | high_saturation | 11 | [82, 78] |
| val_syn_lowev_pe08 | synthetic_range | 0.726 | critical | 7 | [0, 7] |
| val_syn_stress_pe40 | synthetic_stress | 0.980 | high_saturation | 48 | [54, 48] |

## 6 TPE1171 与资本公式

- TPE1171：usable=True；n_charge_sessions=3；rel_err 行=['231', '', '111.00', '9.88', '674', '-21.4%', '3']；可用 validation=['TPE1376', 'TPE0930', 'TPE1380', 'TPE1171']。
- calibrate.py 判据：unusable = ((rel_err is not None and abs(rel_err)；rel_err = (e_dwell_dep - mean_dwell_little) / mean_dwell_little
- 旧快照：[]
- 资本：k=1/day=75.29767671232877；k=0=0.0；k=1/半日=37.64883835616438；annual=3650 -> 10.0；cost_scenario 目标=75.29972602739726。
- 曲线 facility_cost：1440min k=1 -> 75.29767671232877；720min k=1 -> 37.64883835616438。

## 7 未审计/边界

- 本审计只复算数值与文字一致性，不重跑 5226 次规则仿真；种子/轨迹哈希未重算。
- p_EV 本身不可识别（见 research/round2_20261031/CONTRACT.md §5 与 model_20261031_v2.json），以上均为情景解。
- 未改动任何历史 JSON/报告；发现的问题只在本目录登记。
