# 第六轮 A：指标语义入口（service_semantics）与 59 条曲线兼容性

状态: 生效
日期: 2026-10-31
负责人: sim-a（执行）；接口契约见 [CONTRACT.md](../CONTRACT.md) §1
范围: 只读既有 59 条曲线复算语义计数；不重跑仿真、不改 analyze_round3、不改任何旧结果。

## 0 结论

- 新增 [service_semantics.py](../../../apps/parking_lab/workbench/service_semantics.py)：五态分类 + 三/四约束判定 + 最小可行 k/集合形状，作为第六轮唯一语义入口。
- 在 59 条既有曲线（31,975 行、975 个 lot-seed-rule 单元）上复算，四项率的五态计数与第五轮 `none_semantics_4way.json` **逐项一致**（真实缺失 0、非法 0）。
- 联合约束：三约束按 N/A 跳过 achieved **780/975**、严格 765/975；四约束（五态语义）66/975、严格 51/975；旧“零分母一律跳过”口径可复现 **310/975**，证明 review 的 310→51 是口径差，不是修复效果。
- 旧 `research/round3_20261031/analyze_round3.py` 未修改；新分析必须调用本入口。

## 1 交付物

| 文件 | 作用 |
|---|---|
| [service_semantics.py](../../../apps/parking_lab/workbench/service_semantics.py) | 五态 `classify_rate`、`constraint_status`、`judge`、`feasible`、`minimal_feasible` |
| [test_round6_semantics.py](../../../apps/parking_lab/workbench/tests/test_round6_semantics.py) | 五态、N/A/删失/缺失/非法不判成功、三/四约束、集合形状 |
| [recompute_59_curves.py](recompute_59_curves.py) | 59 条曲线只读复算脚本 |
| [recompute_59_curves.json](recompute_59_curves.json) | 计数、联合达成、逐单元 k、输入/源码哈希 |

## 2 五态与分母（与 service_metrics.py 一致）

| 状态 | 判定 | 是否可判“约束满足” |
|---|---|---|
| valid | 值有限且在 [0,1]，分母>0 | 是（且 ≤α） |
| not_applicable_zero_demand | 分母=0 且对应需求计数=0 | 否；记录并跳过 |
| censored_no_departure | 仅离场能量率：departed_requested_kwh=0 但 exogenous_charge_requests>0 | 否；删失，不判成功 |
| missing | rate=None（分母>0），或分母缺失 | 否；不得跳过判 achieved |
| illegal | 非有限、越界、类型错、分母为负 | 否；不得跳过判 achieved |

分母：capacity=`charge_requests`；EV=`exogenous_ev_visits`；ICE=`exogenous_ice_visits`；离场能量=`departed_requested_kwh`（其需求计数=`exogenous_charge_requests`）。

## 3 兼容性结果（第五轮锚点）

| 率 | valid | 零需求 N/A | 尚无离场样本 | 真实缺失 | 非法 |
|---|---|---|---|---|---|
| capacity_only_unmet_rate | 31,360 | 615 | 0 | 0 | 0 |
| ev_parking_failure_rate | 31,975 | 0 | 0 | 0 | 0 |
| ice_parking_failure_rate | 31,975 | 0 | 0 | 0 | 0 |
| departed_shortfall_energy_rate | 22,895 | 615 | 8,465 | 0 | 0 |

| 联合约束口径 | 本轮 | 第五轮锚点 |
|---|---|---|
| 三约束，N/A 跳过 | 780/975 | 780/975（joint_k_none_audit） |
| 三约束，严格（全部 valid） | 765/975 | 765/975 |
| 四约束，censored 不判成功（五态） | 66/975 | 4way 语义下的结果；见下 |
| 四约束，旧口径（零分母一律当 N/A 跳过） | 310/975 | 310/975 |
| 四约束，严格 | 51/975 | 51/975 |

310 与 66 的差异不是数据变化：旧审计把 `departed_requested_kwh=0` 全部当 N/A 跳过，而 `none_semantics_4way.json` 明确把“有需求但无离场样本”单列为删失；本入口按后者不判成功。脚本同时复现 310 与 66，两者都可审计。

## 4 判定函数语义

- `judge(row, CONSTRAINTS_3|CONSTRAINTS_4, alpha=0.05, na_policy="skip"|"strict")`：`skip` 时零需求 N/A 记录并跳过；censored/missing/illegal 一律不判成功。`strict` 只允许全部 satisfied。
- 返回 `achieved`、`status`、逐约束 `constraints`、`satisfied/violated/not_applicable/censored/missing/illegal/undecidable`，以及 `vacuous`（全 N/A 的空洞达成标记）。
- `minimal_feasible(by_k)` 输出 `min_known_feasible`、`confirmed_minimal`、`is_interval`、`truncated_at_kmax`、`empty_set`、`undecidable_ks`；前一个 k 不可判定时不得确认最小。
- `analyze_round3.joint_k` 保持原样；不采用 strict 作为主口径。

## 5 运行记录

| 项 | 值 |
|---|---|
| 命令 | `C:/anaconda/python.exe research/round6_20261031/a_semantics/recompute_59_curves.py` |
| 解释器 | C:/anaconda/python.exe（Python 3.12.3） |
| 退出码 | 0（`match=true`，mismatches=[]） |
| 范围 | 59 条曲线、31,975 行、975 单元；只读，不重跑 |
| 输出哈希 | `recompute_59_curves.json` sha256 `e2b3579e9427ceba31ecfbbb9afcb107d27184b6921408255d157bf56ce8436a` |
| 模块哈希 | `service_semantics.py` sha256 `02506b8c48228f8d0c46eb641e000712642e0908fa4f527fb19c6e8c78f11831` |
| 输入哈希 | 59 个曲线文件的 sha256 全部写入 JSON 的 `input_sha256` |

## 6 测试与检查

| 命令 | 退出码 | 结果 |
|---|---|---|
| `python -m unittest apps.parking_lab.workbench.tests.test_round6_semantics apps.parking_lab.workbench.tests.test_round6_info` | 0 | 26 tests OK（语义 14 条 + 信息条件 12 条） |
| `python -m unittest discover -s apps/parking_lab/workbench/tests -p "test_*.py" -t .` | 0 | 388 tests OK |
| DSH Python `scripts/check_all.py` | 0 | 0 错误、8 条既有历史警告 |

## 7 限制与 UNVERIFIED

- 未重跑仿真，也未重算第三/四轮结果；只验证既有曲线上的语义计数与联合达成。
- 四约束中的离场能量率仍是删失条件下的辅助结果；不据此写“不可行证书”。
- strict 口径不采用（本报告只把它作为对照；主口径是 N/A 跳过）。
- 310 与 66 的差异已用同一脚本同时复现，属于语义口径；若后续数据源出现真实 missing/illegal，需先按五态显式判定再重算。
- UNVERIFIED：未检验新数据源（不同版本/新场站）上的五态分布；未对 59 条曲线以外的结果外推。

## 8 复现命令

```text
C:/anaconda/python.exe research/round6_20261031/a_semantics/recompute_59_curves.py
```
