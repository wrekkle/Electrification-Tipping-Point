# 第二轮 R2-C：搜索状态与解析负荷占位口径（search-eng 交付，2026-10-31）

类型: 研究报告
状态: 生效
负责人: search-eng（Lead 统一验收）
日期: 2026-10-31
工作流: R2-C（CONTRACT.md §3/§4；BASELINE.md R2-D5/D6/D7）
写范围: apps/parking_lab/workbench/allocation.py、apps/parking_lab/workbench/tests/test_allocation.py、
research/round2_20261031/search_status/。未改 docs/TODO.md、docs/PROGRESS.md、旧报告、旧 JSON 与
research/integer_allocation_20261031/（analyze_run.py 属 Lead 集成范围，仍为旧实现）。

## 1 结论

1. **R2-D5 已修**：新增 `allocation.service_level_k` 与 `allocation.budgeted_service_search`，
   返回状态字典（achieved / no_demand / budget_exhausted / infeasible_upper_bound / missing_data）。
   无 k 达标时 k=None，**不再返回 max(by_k) 冒充推荐**；恰在硬上限达标标 boundary=True。
2. **R2-D6 已修**：`mean_connector_load` 默认 `occupancy_model="dwell"`，connector 占位=全部 EV 停留
   （含不充电 EV 与充后滞留，即"充满不释放枪"）；旧公式仅作 `occupancy_model="charge"` legacy 对照，
   结果标 `legacy=True`。10 EV/h、q_need=0.2、充电 30 min、停留 90 min 的例子：
   占位时长 90→旧 78 min，负荷 15.0→13.0 Erlang，k(α=5%) 20→18（旧口径低估 13.3%）。
3. **R2-D7 已修**：新增 `allocation.erlang_b_closed_form`（独立闭式、log 空间），测试用**整数阶乘
   直接求和**（第三条路径）对照；B(0.5,1)=0.333333、B(1,1)=0.500000、B(2,2)=0.400000、
   B(5,3)=0.529661（6 位小数，4 位 0.5297）。旧报告 §10 "B(a=1,c=1)=1/3" 错误，应为 0.5。
4. Erlang-B 的适用条件（稳态、Poisson 到达、无排队、服务时长独立同分布）写入模块 docstring；
   解析 k 与整数服务水平搜索在**同一 α**下对照一致（6 组 16 对，见 verification.json）。
5. 修复前反例可执行、留失败输出：`repro_pre_fix.log`（EXIT=1，7 项失败）→ 修复后
   `repro_post_fix.log`（EXIT=0，7/7 通过）。

## 2 缺陷清单与根因

| 编号 | 位置（修复前） | 现象 | 根因 |
| --- | --- | --- | --- |
| R2-D5 | `research/integer_allocation_20261031/analyze_run.py:68-80` 的 `service_level_k` | 全部 k 未达标时 `return max(by_k)`；baseline 缺失返回 None、baseline≤0 返回 0，无状态/硬上限/边界概念 | 把"无解"和"搜索被截断"压成同一个整数返回值，调用方无法分辨"达标 40"与"只算到 40" |
| R2-D6 | `allocation.mean_connector_load:58-79` | 占位时长 `q_need*charge+(1-q_need)*dwell`，对需充电 EV 用充电时长 | 口径假设"充完立即释放枪"，与仿真/规则语义（充满不释放枪）冲突，系统性低估占位负荷与解析 k |
| R2-D7 | 旧报告 `docs/reports/2026-10-31-整数配桩规则与仿真验证.md` §10 | 手算 `B(a=1,c=1)=1/3` | 张冠李戴：1/3 是 B(0.5,1)，B(1,1)=0.5；且未写 Erlang 稳态/Poisson/无排队/iid 条件 |

## 3 修复前失败的最小反例

脚本：`research/round2_20261031/search_status/repro_contract.py`（只断言契约，不改被测代码）。
修复前运行 `python research/round2_20261031/search_status/repro_contract.py` → **EXIT=1**，7 项失败
（日志 `repro_pre_fix.log`），关键证据原文：

    [D5 证据] 旧 analyze_run.service_level_k -> 2（即 max(by_k)=2，未达标也返回 2）
    FAIL D5 全部 k 未达标不得返回 max(by_k): AttributeError: ... has no attribute 'service_level_k'
    [D6 修复前行为] 默认口径 mean_connector_minutes=78.0 offered_load_erlang=13.0
    FAIL D6 默认占位=dwell（全部 EV 停留）: AssertionError: {... 'mean_connector_minutes': 78.0 ...}
    FAIL D7 Erlang-B 独立闭式求和与 6 位手算值: AttributeError: ... 'erlang_b_closed_form'

即：旧函数对 {U(0)=10, U(1)=8, U(2)=5}、α=5% 返回 2（假推荐）；旧模块对上述占位例子返回 78.0
而非 90.0。修复后同脚本 **EXIT=0**（`repro_post_fix.log`）。
说明：修复后脚本把该行标签改为 `[D6 当前默认口径]`；修复前日志用的是旧标签，数值证据不受影响。

## 4 补丁（allocation.py）

1. **状态化服务水平搜索**
   - `service_level_k(by_k, alpha, *, key="unmet_no_connector_events", k_hard_max=None)`
     返回 `{"status","k","alpha","evaluated_max","baseline","note","boundary"}`。
     `by_k` 接受 `{int k: 记录 dict}`（取 `row[key]`）或 `{int k: 数值}` 简写。
     规则：缺 k=0/基线 None → `missing_data`（baseline=None）；U(0)=0 → `no_demand`（k=0）；
     `k_alpha = min{k≥1: U(k) ≤ α·U(0)}`（含 1e-12 量级容差，恰好等于阈值算达标）；
     缺中间行/行值为 None → `missing_data`；无 k 达标时，若 `evaluated_max ≥ k_hard_max`
     → `infeasible_upper_bound`、否则 `budget_exhausted`（k 均为 None）；达标且 k==硬上限
     → `boundary=True`。`k_hard_max` 缺省 None 时把"by_k 已评估到的最大 k"视为硬上限
     （兼容 analyze_run 全 k 枚举曲线）；要区分"预算截断"必须显式传硬上限。
   - `budgeted_service_search(evaluate, alpha, k_initial_max, k_hard_max)`：先评估 0..k_initial_max，
     未达标则批次上限翻倍（至少 +1、封顶 k_hard_max）继续，返回同一状态结构；
     `evaluate(k)` 返回数值或含默认键的记录或 None（None 行按缺行处理）。
   - 常量 `SERVICE_LEVEL_KEY`、`SERVICE_LEVEL_STATUSES` 供调用方/验收引用。
2. **占位口径**：`mean_connector_load(..., *, occupancy_model="dwell")`；
   dwell 时 `mean_connector_minutes=mean_dwell_min` 且 `offered_load_erlang=λ_ev·dwell/60`；
   `"charge"` 为 legacy 旧公式，结果 `legacy=True`、`occupancy_model` 回显；未知模型抛 ValueError。
3. **Erlang-B 独立校验**：`erlang_b_closed_form(offered_load, servers)`，`B=(a^c/c!)/Σ_{n=0..c}a^n/n!`
   用 `lgamma` log 空间实现（大负荷不溢出），a=0 返回 0.0。
4. 模块 docstring 写明：dwell/charge 口径、Erlang-B 稳态/Poisson 到达/无排队/服务时长 iid/
   同质连接器/负荷=到达率×平均占位时长等适用条件，以及"无 k 达标不得用 max(by_k) 冒充推荐"。

接口兼容：`mean_connector_load` 旧 4 个派生键仍在，新增 `occupancy_model`/`legacy` 两个键；
旧数值仅在 `occupancy_model="charge"` 下可复现（迁移说明见 §8）；其余旧函数（erlang_b、
min_servers_for_blocking、evaluate_integer_costs、compare_rounding、regret）签名与语义未变。

## 5 修复后验证（命令 + 退出码 + 证据文件）

| # | 命令 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | `python research/round2_20261031/search_status/repro_contract.py` | 修复前 EXIT=1（7 失败）→ 修复后 **EXIT=0**（7/7） | repro_pre_fix.log / repro_post_fix.log |
| 2 | `python -m unittest apps.parking_lab.workbench.tests.test_allocation` | **Ran 69 tests, OK, EXIT=0**（原 37 项扩容至 69） | allocation_tests.log |
| 3 | `python research/round2_20261031/search_status/verify_round2.py` | **6/6 项通过, EXIT=0**，写 verification.json | verify_round2.log / verification.json |
| 4 | `python -m unittest discover -s apps/parking_lab/workbench/tests` | Ran 267 tests, **EXIT=1**：failures=3/errors=24 全部来自其他并行工作流（见下），test_allocation 无失败 | full_tests.log |
| 5 | `python scripts/check_all.py` | EXIT=1：仅"稿件字数与章节一致性"缺 python-docx（基线 §2 预存）；文档与链接段错误 0/警告 92（含本单 tests/test_allocation.py 28,593 字符超 24,000 软线 1 条，其余为既有源码软线与失效链接提醒），文献索引段错误 0/警告 7（历史计数） | check_all_plain.log |
| 6 | DSH 自带 python（含 python-docx）`scripts/check_all.py` | **EXIT=0**（三项全通过） | check_all_docx_python.log |

全量测试红项归属（非本单文件；并行工作流仍在改）：`test_costs` 24 errors（costs.py 尚无
`facility_cost`，R2-A 在途）、`test_traffic_gen` 1 fail（能量上限 ≤ 可交付，R2-B 在途）、
`test_type_rules` 1 fail（ObservableState 字段集变动，R2-E 在途）。本单对 test_allocation 的
69 项负责且全绿；不把全量 EXIT=1 写成"全部通过"。

## 6 手算与闭式校验（verification.json 摘要）

| a | c | erlang_b（递推） | 独立闭式（整数阶乘求和） | erlang_b_closed_form（lgamma） | 6 位 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.5 | 1 | 0.333333333333 | 0.333333333333 | 0.333333333333 | 0.333333 |
| 1 | 1 | 0.500000000000 | 0.500000000000 | 0.500000000000 | 0.500000 |
| 2 | 2 | 0.400000000000 | 0.400000000000 | 0.400000000000 | 0.400000 |
| 5 | 3 | 0.529661016949 | 0.529661016949 | 0.529661016949 | 0.529661 |

网格 7×21 点三条路径最大绝对差 <1e-12；大负荷 40/120/250 不溢出且与递推一致（places=12）。
解析/整数同 α 对照：a∈{0.4,2.0,8.7,24.0} × α∈{2%,5%,10%,20%}，`service_level_k` 的 k 与
`min_servers_for_blocking` 全部相等（16/16）；截断不可达时均为 infeasible_upper_bound/k=None。

## 7 文件哈希（SHA-256）

修复前（与 BASELINE §3 一致）：

| 文件 | 字节 | sha256 |
| --- | ---: | --- |
| allocation.py | 9,534 | 8f17ecb287a302de68119b3463c53154ad84ef74486bb2ece1709cdf8e56f26a |
| tests/test_allocation.py | — | 5991083d9768988e0b7d869cb589aea14300f065ba8de21d7da05fe0fce2eb03 |

修复后：

| 文件 | sha256 |
| --- | --- |
| apps/parking_lab/workbench/allocation.py | 89d8a1862b0b5e4d65d6028510eb5dd35f7e7c94deb9ea608e679a883afe86c9 |
| apps/parking_lab/workbench/tests/test_allocation.py | 361d6fb103e0b90fa6d8399b7c0d60f5b8b5d695ccc16fb841ce14d1175c8833 |
| research/round2_20261031/search_status/repro_contract.py | 6064936d9cd01231d1e7221235922b66254f468d22145aef45045540a3d4b942 |
| research/round2_20261031/search_status/verify_round2.py | b441c35fd0477f4799a0f43bede2727d9b99d6205b9357cb1d66288d12d2e3d0 |
| research/round2_20261031/search_status/verification.json | fa26fcbb1e04f149ed3ad51317d4c486ed348833614b434f4b228860814aa676 |

版本标签 `round2-search-status-20261031`（git-free；仓库无提交历史）；解释器 C:\anaconda\python.exe
3.12.3；确定性检查，seed=None。verification.json 的 meta.source_sha256 为运行时读取的源码哈希。

## 8 对旧结论的影响（需 Lead 在统一报告追加更正）

1. **R2-D5 影响旧分析 JSON 与拟合**：旧 `analyze_run.service_level_k` 对"枚举上限内无 k 达标"返回
   max(by_k)=40，与真正在 40 达标无法区分。旧报告的 `≥40` 行是人工标注，但旧 JSON 的
   `service_level_k` 里是整数 40；`fit_sqrt_rule` 的训练点把这类 40 当真实目标（TPE0330/TPE0401/
   TPE1171 等可用场站），因此"充电负荷根式验证 MAE 19.0"的训练目标可能含截断值，需用新状态
   （infeasible_upper_bound 剔除）重算后才能引用。旧结论"k_5 中位数 32、≥40 读作截断"的方向不变，
   但**任何把 40 当精确 k 的汇总（均值/MAE/拟合）都应重算**。
2. **R2-D6 影响解析近似数值**：旧报告 §5.2/§6.3 的 A_conn 与解析 k 用的是 dwell 口径，但修复前模块
   默认 charge 口径；用旧模块重算会得到更小负荷（示例 15.0→13.0 Erlang、k 20→18），无法复现报告
   表中 A_conn=8.79/2.71/… 等值。修复后模块默认与报告口径一致；报告 §6.3 的"7 场比值 0.73–1.20
   （TPE0695 例外 2.46）"结论本身不变。
3. **R2-D7 更正旧报告 §10 一行**：应为 `B(a=1,c=1)=0.5`（1/3 是 B(0.5,1)）；同段 `B(1,2)=0.2`、
   `B(2,3)=0.2105` 正确。另建议在报告解析近似节补 Erlang-B 适用条件（稳态/Poisson/无排队/iid）。
4. 旧 JSON 未覆盖、未改写；新证据全部在 `research/round2_20261031/search_status/`。

## 9 交接给 Lead 的集成点（不在本单写范围）

1. `research/integer_allocation_20261031/analyze_run.py:68-80` 仍用旧实现。建议替换为
   `alloc.service_level_k(by_k, alpha, key=SERVICE_KEY, k_hard_max=min(n_spaces, 枚举上限))`，
   输出改为状态字典并按契约记录；`infeasible_upper_bound`/`budget_exhausted`/`missing_data` 的 k
   不得进均值、MAE、拟合与"推荐 k"汇总；`boundary=True` 的行保留 k 但标"恰在上限达标"。
   注意 analysis JSON schema 会从 `{alpha: int}` 变为 `{alpha: 状态字典}`，下游 final_tables/
   sens_analyze 需同步（或保留旧整数字段加新状态字段，二者都写）。
2. 待登记 docs/TODO.md 的新问题（本单不写 TODO）：
   - analyze_run/下游脚本尚未切换到状态化服务搜索，旧 JSON 中 40 无法区分达标/截断（R2-D5 残留）；
   - 旧报告 §10 Erlang-B 手算错误需更正（R2-D7 文档部分）；
   - `min_servers_for_blocking(load=0,...)` 仍返回 1（旧语义）；契约 §4.3 "无最低工程约束时允许 k=0"
     目前由 `service_level_k` 的 no_demand→k=0 与 analyze_run 的 `load>0 else 0` 分支覆盖，
     是否统一旧函数语义需 Lead 决定；
   - N<40 的场站做 `infeasible_upper_bound` 判定必须传 `min(n_spaces, 枚举上限)` 作为 k_hard_max；
     缺省时把已评估最大 k 当硬上限虽恰好避免误判，但显式集成更稳；
   - `tests/test_allocation.py` 扩到 69 项后 28,593 字符，超过 check_all 源码软线 24,000
     （只提醒不拦）；若要拆分测试文件，需 Lead 分配新文件名（本单写范围只给该文件）。

## 10 局限

- 本单未重跑 2,202 行整数曲线，也未重算解析 MAE/拟合（属 Lead 集成范围）。因此旧报告数值的
  受影响范围只给出定位与机制，未给重算数字。
- 状态化接口的 `budget_exhausted` 依赖调用方显式给 `k_hard_max`；缺省时只能报 infeasible/target 状态。
- 全量测试当前红项来自其他并行工作流（§5），本报告不宣称全绿。
