# R2-A 成本与占位修复报告（cost-eng，2026-10-31）

类型: 研究记录（工作流交付）
状态: 完成（本工作流）；仓库全量测试因其他并行工作流暂时红，见 §5
负责人: cost-eng（子代理）
工作流: R2-A（CONTRACT.md §1、§8）
写范围: `apps/parking_lab/workbench/costs.py`、`apps/parking_lab/workbench/tests/test_costs.py`、`research/round2_20261031/cost_outcomes/`

## 1 缺陷清单

| 编号 | 缺陷 | 影响 |
| --- | --- | --- |
| R2-D1a | `CostLedger.summary` 的 `operator_capital_depreciation` 只乘天数、不乘 `equipped_bays` | k=0 仍计 31.997978 TWD/日；k>1 资本按 1 套设备计，少乘 k 倍 |
| R2-D1b | 设施成本公式散落在账本、runner（`run_cost_curve.facility_cost_per_period`）、分析脚本三处 | 不是唯一权威入口；站级固定成本无法单列、易重复相乘 |
| R2-D2 | `occupancy_minutes.no_charging_demand` 把 `is_ev=False` 的油车占带枪位也并入 | π1/π2 共享放行时"非充电电车占枪"偏高，三类占位口径失真（旧报告 §6.5 已登记） |

接口缺口（本次一并补）：缺站级固定成本 `facility_fixed_cost_per_day` 入口；`operator_capital_depreciation` 无折算日口径。

## 2 修复前反例与失败证据（先失败，后修复）

最小反例脚本（可执行，修复前 1/10 PASS、9 FAIL，EXIT=1）：
`research/round2_20261031/cost_outcomes/repro_counterexamples.py`
失败输出留证：`before_failures.txt`（EXIT_CODE=1）、`before_failures_unittest.txt`（19 个新测试：failures=1, errors=24，EXIT=1）。

| 反例 | 断言（修复后） | 修复前实际值 |
| --- | --- | --- |
| C1 k=0 资本 | 0.0 | **31.997978082**（仍按日计） |
| C2a π1 油车占枪 | `ice_blocking_connector`=10.0，与 rules 台账一致 | 键不存在；油车 10 min 在 `no_charging_demand` |
| C2b π1 `no_charging_demand` | 0.0（仅 EV） | **10.0**（混入油车） |
| C3 k=2、12h 窗口 | 31.997978（整日 k=2 的一半） | **15.998989**（少乘 k） |
| C4 k=2、24h 窗口 | 63.995956（2×设备日成本） | **31.997978**（少乘 k） |
| C5–C8 `facility_cost` | 存在；k=0 → 0.0+not_applicable；1 设备日=75.297677；站级固定 288×0.25=72 | 函数不存在（AttributeError） |

n=1 的 12h 窗口（C3b）修复前也通过：窗口换算 `days=elapsed/1440` 本来正确，D1 的错在漏乘设备数。

## 3 根因

1. `summary` 只调用 `depreciation_daily`（单套设备日成本）再乘 days，维护项则单独乘了 `equipped_bays`——同一"设备资本"在每个调用处各算一遍，资本漏乘设备数，且没有任何单一口径。
2. `occupancy_minutes` 只按 `needs_charge` 二分：`needs_charge=False` 一律记 `no_charging_demand`，未检查 `is_ev`；油车与"无充电需求电车"共用一键。

## 4 补丁（只改契约写范围内两个源码文件）

### 4.1 `costs.facility_cost(k, cost_params, *, days)`（唯一权威入口）

    {"value": float|None, "items": {"device_capital", "device_maintenance", "facility_fixed"},
     "missing": [...], "not_applicable": [...]}

- `device_capital = k × (depreciation_capex/depreciation_life_years) × days`；给 `depreciation_annual` 时 = `k × annual/365 × days`（与 capex 互斥，复用 `depreciation_daily`）。
- `device_maintenance = k × maintenance_per_bay_day × days`。
- `facility_fixed = facility_fixed_cost_per_day × days`，站级、与设备数无关、单列。
- `k=0`：资本/维护 0.0 且进 `not_applicable`，`missing` 为空（零设备不是未知）；缺参 → 该项 None、`value` None、参数名进 `missing`。
- 未提供 `facility_fixed_cost_per_day` 键 = 本次核算不含站级固定成本（旧成本曲线口径），0.0 且不进 missing；**显式 None 才是未知**。
- 设备数与天数只在本函数乘一次。

### 4.2 `CostLedger.summary`

- `operator_capital_depreciation = facility_cost(...)["items"]["device_capital"]`（已乘 k 与 days）；`operator_maintenance = 按 kWh 维护 + device_maintenance`（不再二次乘 k）。
- 新增 item `operator_facility_fixed`（COST_ITEMS 追加；未配置站级固定成本时为 0.0）。
- 新增 `daily_equivalent`（折算日口径）：`operator_capital_depreciation_per_day`、`operator_maintenance_per_day`、`operator_facility_fixed_per_day`、`elapsed_min/elapsed_days`，并注明"窗口值 = 折算日值 × days，设备数只乘一次"。
- 新增 `facility_cost` façade 块：`{"source": "costs.facility_cost", "k", "days", "items", "missing", "not_applicable", "facility_fixed_included"}`，账本与 runner 可追溯同一入口。

### 4.3 `occupancy_minutes`

- `needs_charge=False` 分支拆为：`is_ev=False` 且 `bay < chargers` → `ice_blocking_connector`；`is_ev=True` 且 `bay < chargers` → `no_charging_demand`。
- `OCCUPANCY_REASONS` 扩为 6 类（插入 `ice_blocking_connector`），配对反事实的 `released_minutes_by_reason` 自动覆盖。
- 旧键迁移：`DEPRECATED_OCCUPANCY_KEY_MAP = {"no_charging_demand": {deprecated, old_meaning, replacement=(no_charging_demand, ice_blocking_connector), migration}}`，并新增 `legacy_no_charging_demand(minutes)` 还原旧值；`occupancy_minutes` docstring 写明迁移说明。

### 4.4 其他

- `cost_report.assumptions` 增 `facility_cost_entry`、`facility_fixed_cost_per_day`、`occupancy_attribution` 三条口径说明。
- `COST_MODEL_VERSION` **未改**（契约未要求；测试断言精确字符串），是否升版由 Lead 决定（见 §9）。

## 5 修复后验证（命令 + 退出码）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `python research/round2_20261031/cost_outcomes/repro_counterexamples.py` | 0 | 10/10 PASS（输出见 `after_validation_stdout.txt` 之前；修复后重跑已并入 verify） |
| `python research/round2_20261031/cost_outcomes/verify_fix.py research/round2_20261031/cost_outcomes/after_validation.json` | 0 | **43/43 PASS**；覆盖 k=0/1/2 × 12h/24h/36h、缺参、站级固定、折算日口径、不重复相乘、π0/π1 三类占位、挪车释放、deprecated 映射、cost_report 块 |
| `python -m unittest apps.parking_lab.workbench.tests.test_costs` | 0 | Ran 63 tests, OK（含 19 个新增 R2-A 测试；修复前 19 个新测试 EXIT=1） |
| `python -m unittest discover -s apps/parking_lab/workbench/tests` | **1** | Ran 267 tests, failures=3 errors=1，**全部在其他并行工作流文件**：`test_type_rules`（π2 闸门/观测字段，rules-eng）3 条、`test_traffic_gen`（能量上界，traffic-eng）1 条；本工作流文件 63/63 通过。完整输出 `full_suite_after.txt` |
| `python scripts/check_all.py` | **1** | 错误 0；文档与链接检查通过、文献索引通过；仅"稿件字数与章节一致性"因缺 python-docx（BASELINE 既有问题）。BASELINE 记录的 DSH docx 解释器路径 `C:\Users\tho25\.dsh\dsh-runtimes\dsh-primary-runtime\...` 本机已不存在，该检查未复跑，见 `check_all_after.txt` |

独立反例先失败、修复后通过；不只依赖原测试。

## 6 文件哈希（SHA-256）

| 文件 | 修复前（BASELINE/新建前） | 修复后 |
| --- | --- | --- |
| apps/parking_lab/workbench/costs.py | 9a727717eb62316c…（38,766 B） | `4843662CD6516DBBE8E36C7327B3885179638917B83B0F2682A28974CC0F5599`（47,152 B） |
| apps/parking_lab/workbench/tests/test_costs.py | 既有文件（扩容前） | `2A689E0D93FAFD20239E4E09F34EE7135DDDCFD62546967F30A89A0487E510B9`（43,716 B） |
| research/round2_20261031/cost_outcomes/repro_counterexamples.py | — | `ABA904F94044A0BACB283B1AD0A098235C0CF894CA3A5599765269060A410B02` |
| research/round2_20261031/cost_outcomes/verify_fix.py | — | `836443E4E79FC09D25C2AEBDF4DCC1D7BFB4E1FCAEC9F2355E4EBAC26DA4EEBB` |

修复后源码哈希也写入 `after_validation.json.source_sha256`。未覆盖任何已交付 JSON、未改 docs/TODO.md、docs/PROGRESS.md、旧报告、runner。

## 7 接口/导出字段变化

1. `costs.facility_cost` 新函数（导出）；`FACILITY_FIXED_PARAMETER`、`FACILITY_COST_ITEMS`、`DEPRECATED_OCCUPANCY_KEY_MAP`、`legacy_no_charging_demand` 新导出。
2. `COST_ITEMS` 追加 `operator_facility_fixed`（未配置站级固定成本时值为 0.0，旧总成本数值不变）。
3. `occupancy_minutes` / `metrics["occupancy_minutes"]` / `attribution.occupancy_minutes_by_reason`：新增 `ice_blocking_connector`；`no_charging_demand` 变为 EV-only（π1/π2 数值会下降，下降量转入 `ice_blocking_connector`）。
4. `cost_report`/`CostLedger.summary` 新增 `daily_equivalent`、`facility_cost` 块；`items.operator_capital_depreciation` 口径变为 k×设备日成本×days。
5. `attrs`/server/experiments 无需改代码：`server.py` cost_csv 按 `items` 迭代自动多一行；`experiments.compare` 只用 `total_cost`（站级固定未配置时不变）。
6. `COST_MODEL_VERSION` 仍为 `v2-2026-10-30`。

## 8 对旧结论的影响

- **不受影响**：旧报告盈亏平衡 `L*_k = Δfacility/ΔU` 与设施成本 75.2977 TWD/连接器·日——它们来自 runner 的 `k × 单连接器日成本`；`facility_cost(k, 既有 cost_scenario 参数, days)` 与旧值逐位相同（无站级固定成本时）。三类占位在 π0 下不变；π2−π0=0 的结论不变。
- **需要重算/重读**：① 旧 JSON 的 `cost_items.operator_capital_depreciation` 在 k=0 时错误地非 0、k>1 时少乘 k；任何直接引用该 item 或 `total_cost` 的表须用新代码重跑，旧 JSON 保留不覆盖。② π1 下旧的 `occupancy_minutes.no_charging_demand` 含油车（旧报告"π1 油车占枪 26.3 分钟"目前藏在 `no_charging_demand` 里），新口径须改用 `ice_blocking_connector`；跨版本比较用 `legacy_no_charging_demand()` 还原。③ `final_tables.py`/`analyze_run.py` 若曾按 `no_charging_demand` 报"非充电电车占枪"，π1 数值口径变化。
- 旧报告"costs.py 折旧不乘设备数、k=0 仍计 31.998"的注释（`verify_lead.py` `why_not_usable`、主报告 §6.5）已过时，Lead 重跑后应更正。

## 9 需要 Lead 改的 runner / 分析脚本 / 配置（本单按要求不改）

1. **runner** `research/integer_allocation_20261031/run_cost_curve.py`：
   - 删除 `facility_cost_per_period`（L40–66），改调 `costs.facility_cost(k, cost_params, days=duration_hours*60/1440)`；
   - row 保持 `facility_cost=facility["value"]`（既有参数下数值不变）、`facility_cost_missing=facility["missing"]`，并加 `"facility_cost_source": "costs.facility_cost"` 与 `not_applicable`；
   - 若要纳入站级固定成本，在 `cost_scenario.json` 增加 `facility_fixed_cost_per_day` 来源后再填。
2. **config.py（Lead 范围）**：把 `facility_fixed_cost_per_day` 注册进 `CostConfig` 字段 + `COST_BOUNDS` + `sources` 白名单；同时在 `costs.COST_PARAMETER_NAMES` 追加该名（本单未加，避免 `CostConfig.params()` getattr 报错；Lead 加字段时我方可配合改 costs.py 这一行）。未注册前，站级固定成本只能通过直接传 `CostLedger(params)` 使用（测试即如此）。
3. **分析脚本** `analyze.py / analyze_run.py / final_tables.py / sens_analyze.py / verify_lead.py`：重跑旧 JSON 而非混读；读取 `occupancy_minutes_by_reason` 时区分 `no_charging_demand`（EV）与 `ice_blocking_connector`；`verify_lead.py` 中"costs.py 不可用"的说明需删除/改写。
4. **文档（Lead 范围）**：`docs/methods/COST-MODEL-V2.md` §5 原因5类 → 增 `ice_blocking_connector`；§6 增 `facility_fixed_cost_per_day` 与 `facility_cost()` 入口；主报告更正段引用本报告。
5. **版本**：是否把 `COST_MODEL_VERSION` 升为 `v2-2026-10-31`（schema 增字段、资本口径变），请 Lead 决定；本单未改以免打断其他并行工作流。

## 10 未做/限制

- 未改 runner/config/分析脚本/文档（非本单写范围），§9 已列清单。
- 站级固定成本尚无来源，故 `cost_scenario.json` 未填；数值 0.0 仅表示"未纳入核算"，不是"已核实为 0"。
- 全量测试 EXIT=1 来自并行工作流（test_type_rules / test_traffic_gen），本单未越界修改。
- 未重新生成成本曲线 JSON（属 Lead 集成步骤），旧 JSON 原样保留。

## 11 产物清单（本目录）

- `repro_counterexamples.py`、`before_failures.txt`、`before_failures_unittest.txt`：修复前失败证据
- `verify_fix.py`、`after_validation.json`、`after_validation_stdout.txt`：修复后 43/43 独立验证（含源码哈希与 case 明细）
- `test_costs_after.txt`：`test_costs` 63/63 通过
- `full_suite_after.txt`：全量 267 测试输出（4 条并行工作流失败）
- `check_all_after.txt`：`scripts/check_all.py` 输出（EXIT=1，仅缺 python-docx）
