# 第六轮 A：Q2 信息条件 I0/I1 算法比较（有限启发式，非全局最优）

状态: 生效（分析结果，非现实场站实测）
日期: 2026-10-31
负责人: sim-a（执行）；接口契约见 [CONTRACT.md](../CONTRACT.md) §2、[PLAN.md](../PLAN.md) §4

## 0 结论

- I0 直接使用未修改的 `Simulation` 与正式规则；I1 用 `Simulation` 子类 + analysis-only 授权上下文，只额外可见当次到访 `needs_charge`。未修改 `simulation.py` / `rules.py` / `config.py`。
- 固定输入回归：默认规则逐车哈希 `e407f5a1...` 在改动后仍一致（`test_round6_info` 固化）；I1 选择 `MimicI0Policy` 时逐车结果与 I0 完全相同。
- 656 次仿真（2 场站 × seeds 1–2 × 规则 A/B × k=0..40 × {I0,I1}），0 失败，8 workers，4.4 s。
- 8 个 (lot, seed, rule) 单元中 Δk_info 全部为负（−2 至 −17，中位 −9.5）：在本启发式下 I1 用更少的带枪位满足三约束。
- 但 I1 不是全面占优：同 k 四类计数 both 143 / only_I0 26 / only_I1 61 / neither 98 / undecidable 0；在 k_min(I0) 处 2/8 单元只有 I0 可行（TPE0401/规则 A，ICE 停车失败率 0.0769、0.1782 > α）。因此只能写“算法比较/信息上界示例”，不能写“信息必然改善”或“全局最优”。
- k=0 手算核对：16/16 行 capacity_only_unmet_rate=1.0、I0/I1 均不可行；EV 停车失败率 0；ICE 停车失败率 0–0.0099（由总车位 N 是否够用决定）。

## 1 实现与兼容边界

| 对象 | 做法 |
|---|---|
| I0 | 现有 `Simulation(config, arrivals)` + 正式规则；行为与数值不变 |
| I1 | [info_regimes.py](../../../apps/parking_lab/workbench/info_regimes.py) 的 `RegimeSimulation` 子类覆写 `choose_bay`；事件、到达、停留、能量、离场逻辑全部继承 |
| 授权 | `AnalysisGrant`（只允许 needs_charge）；`RealRuleContext` 读取 needs_charge 抛 `PermissionError`；`AnalysisContext` 必须持有同一 `ANALYSIS_GRANT` |
| 策略 | `AnalysisHeuristicPolicy`（需要充电 EV 优先带枪位；不需要充电 EV 优先普通位；ICE 沿用基础规则）；`MimicI0Policy`（完全模仿 I0） |
| 元数据 | 行级 `information_regime/analysis_only/policy_kind`；JSON 顶层另有授权与可见/不可见字段说明 |

默认数值不变的证据：固定输入（Config 与 86 辆到达）下，`Simulation` 的 `demand_hash`、逐车 `(id,time,is_ev,needs_charge,admitted,bay,delivered)` 哈希、指标与率在实现前后一致（硬编码于测试）。

## 2 信息泄漏验收

- 现实规则上下文：`allowed_fields=()`，`needs_charge`/`energy_kwh`/`departure_min` 访问均抛 `PermissionError`；`rules.ObservableState` 字段表中不含 `needs_charge`、`energy_kwh`。
- I1 上下文：`allowed_fields=('needs_charge',)`，只比现实上下文多该字段；`AnalysisGrant` 增加字段、`analysis_only=False`、伪造授权对象均抛错。
- 策略越权：把 `RealRuleContext` 传给 I1 策略抛 `PermissionError`（两个策略都测）。
- 输出标注：每行与导出都有 `information_regime`、`analysis_only`、`policy_kind`；JSON 顶层 `authorization` 记录 grant、可见字段、禁止字段与越权异常类型。

## 3 实验设计与手算

- 场站 TPE0008、TPE0401；seeds 1–2；规则 A=`dedicated_by_type`、B=`full_open_ice_first`；k=0..40 完整枚举。
- 参数：p_EV=0.10、q_need=0.36、charger 7 kW、feeder 336 kW、horizon 1440 min、start_hour 11.5；独立情景模式。
- 同一 (lot, seed, rule) 只生成一次外生车流，在同一车流上重放 I0/I1；每车流 `demand_hash` 写入 JSON。
- 手算：k=0 无带枪位 ⇒ 所有充电请求都没有连接器，capacity_only_unmet_rate=1.0 > 0.05，I0/I1 均应不可行；EV/ICE 停车失败率只由总车位 N 决定。运行结果与手算一致。

## 4 结果

可行集合（三约束、α=0.05、N/A 跳过；区间为闭区间，括号内为可行 k 数；T=在 k=40 截断）：

| 场站 | seed | 规则 | I0 可行区间 | I1 可行区间 | Δk_info |
|---|---|---|---|---|---|
| TPE0008 | 1 | A | 9–31（23） | 4–26（23） | −5 |
| TPE0008 | 1 | B | 9–40（32）T | 4–40（37）T | −5 |
| TPE0008 | 2 | A | 7–33（27） | 5–28（24） | −2 |
| TPE0008 | 2 | B | 7–40（34）T | 5–40（36）T | −2 |
| TPE0401 | 1 | A | 20–30（11） | 6–17（12） | −14 |
| TPE0401 | 1 | B | 20–40（21）T | 6–40（35）T | −14 |
| TPE0401 | 2 | A | 25–29（5） | 8–11（4） | −17 |
| TPE0401 | 2 | B | 25–40（16）T | 8–40（33）T | −17 |

所有 16 个集合均为连续区间；`confirmed_minimal=True`（k_min−1 已评估且不可行）。A 规则在高 k 因充电位挤占普通位、ICE 停车失败率上升而不可行；B 规则允许 ICE 进入充电区，故在 k=40 仍可行，标为截断。

同 k 四类可行性（328 个 unit-k 格）：

| both | only_I0 | only_I1 | neither | undecidable |
|---|---|---|---|---|
| 143 | 26 | 61 | 98 | 0 |

在 k_ref=k_min(I0) 处：both 6、only_I0 2（均为 TPE0401/规则 A，I1 的 ICE 停车失败率 0.0769/0.1782 超 α）、only_I1 0、neither 0、undecidable 0。

各单元在自身最小可行 k 处的三项率均 ≤0.05（多数为 0）；TPE0401 seed 2 规则 A 的 ICE 率为 0.0198（两条件同）。

## 5 解释与可写/不可写

- I1 启发式把“不充电的电车”从带枪位挪到普通位，为要充电的车保留连接器；在低 k（连接器稀缺）降低容量未服务率，因此最小可行 k 下降。
- 同一机制在高 k 会挤占普通位，使 ICE 停车失败；所以 I1 在部分 k 上不可行。这是策略权衡，不是“信息提高所有指标”。
- “更多信息不降低最优值”只在策略集合包含意义下成立，是基础性质，不作为创新。
- 可写：本网格、本策略下的算法比较/信息上界示例；I1 可模仿 I0。不可写：I0/I1 全局最优、必然省枪、现实场站实测规律、对未测场站/种子的推广。

## 6 运行记录

| 项 | 值 |
|---|---|
| 命令 | `C:/anaconda/python.exe research/round6_20261031/a_info/run_q2.py --workers 8 --out research/round6_20261031/a_info/q2_info_regimes.json` |
| 解释器 | C:/anaconda/python.exe（Python 3.12.3） |
| 退出码 | 0（failures=0） |
| workers | 8 |
| 规模 | 656 行（2×2×2×41×2），16 个可行集合，8 组 Δk |
| JSON 哈希 | `q2_info_regimes.json` sha256 `d878703f5f156d78da0a382433d7674f5da44bdd862e174f024be8357f805ef1` |
| 运行器哈希 | `run_q2.py` sha256 `c1fb7730ec3f2f77690b3e7c8f393d9db40bd44c2c2a3b8d58d9a8872922d54a` |
| 模块哈希 | `info_regimes.py` sha256 `f068c28d1ee67b8b55251156b028aa56b30e1e8f1dbf1b778ceeb13ca090ea50` |
| 输入哈希 | `fitted_parameters.json` 与各源码 sha256 见 JSON `input_sha256` / `source_sha256` |

## 7 测试与检查

| 命令 | 退出码 | 结果 |
|---|---|---|
| `python -m unittest apps.parking_lab.workbench.tests.test_round6_semantics apps.parking_lab.workbench.tests.test_round6_info` | 0 | 26 tests OK |
| `python -m unittest discover -s apps/parking_lab/workbench/tests -p "test_*.py" -t .` | 0 | 388 tests OK |
| DSH Python `scripts/check_all.py` | 0 | 0 错误、8 条既有历史警告 |
| `C:/anaconda/python.exe research/round6_20261031/a_info/fixed_input_regression.py` | 0 | 固定输入基准（哈希/指标） |

## 8 限制与 UNVERIFIED

- 只覆盖 2 场站、seeds 1–2、规则 A/B；未跑规则 C/D、验证场站、seeds 3–10、k>40。
- I1 只实现一种启发式，不是最优策略；Δk_info 是“该策略所需最小 k 之差”，不是信息价值的上界证明。
- I1 改变分配次序后，后续准入会随占用结构变化（ICE 可能被挤到普通位之外）；所有到访仍显式记录决策，无车辆消失。
- 模拟情景结果不是现实场站实测规律；p_EV/q_need 是情景输入，不是识别值。
- B 规则在 k=40 处可行但网格截断，只能写“网格内未找到不可行上界”，不能写“任意 k 可行”。
- UNVERIFIED：I1 对其它规则/场站/种子的方向；更大 k 的可行边界；与真实充电意愿数据的对应关系。

## 9 复现命令

```text
C:/anaconda/python.exe research/round6_20261031/a_info/run_q2.py --workers 8 \
  --out research/round6_20261031/a_info/q2_info_regimes.json
C:/anaconda/python.exe research/round6_20261031/a_info/fixed_input_regression.py
```
