# 元数据实际调用路径核查（第五轮追加审稿）

状态: 生效
日期: 2026-10-31
范围: 只读核对 `research/round4_20261031/` 与 `apps/parking_lab/workbench/` 的元数据写入点；不执行仿真、不改实现。
核对对象: `data_trace.py` / `data_trace.json` / `WIRING.md` / `run_scenarios.py` / `charge_sources.py` / `run_cost_curve.py` / `simulation.py` / `rules.py` / `mechanism/`。
证据基线: `data_trace.json`（`generated_utc=2026-10-31T06:43:57Z`，命令 `python research/round4_20261031/data_trace.py`，20 项：19 pass / 1 unverified / 0 fail）。本轮未重跑该脚本，只读既有 JSON。

## 0 结论速览

| 核对项 | 结论 | 缺口 |
|---|---|---|
| (a) 纯合成入口保留 synthetic 标识 | **部分通过**：工作台/API 入口保留；正式研究入口的结果行不保留 | M1 |
| (b) 观测校准 + 情景需求两部分来源分别标明 | **部分通过**：情景侧 provenance 完整；观测校准侧只有 path+sha | M2、M3 |
| (c) 隐藏真值/反事实只标为分析性机制分解、未当可执行政策 | **原则上通过**：代码与注释明确“只作计量/归因、正式规则不读”；缺机器可读标签 | M4 |

## 1 (a) 纯合成入口的 synthetic 标识

**有标识的入口（工作台/API）**

| 文件:行 | 标识/文本 |
|---|---|
| `apps/parking_lab/workbench/experiments.py:25` | `"data_source": "synthetic; not calibrated to observed parking data"` |
| `apps/parking_lab/workbench/server.py:203` | 健康检查返回 `{"ok": True, "version": VERSION, "synthetic": True, ...}` |
| `apps/parking_lab/workbench/continuous.py:276-288` | `start_replay(source="synthetic")`，标签 `回放 replay`、`source=synthetic_ledger`；非 synthetic/taipei 报错 |
| `apps/parking_lab/workbench/simulation.py:501-504` | snapshot 的 `assumptions` 明写“合成车流……needs_charge/能量/真实离场时间/未来到达对控制器不可见” |
| `apps/parking_lab/workbench/costs.py:681` | 成本报告带 `"synthetic": True` |

**正式研究入口**

- `research/integer_allocation_20261031/run_cost_curve.py:230-290` 构造结果行，字段中**没有** `synthetic` / `data_source` / `assumptions`。
- 只读检索：`synthetic|assumptions` 在 `research/integer_allocation_20261031` 下 **0 命中**（grep 工具；本轮未执行仿真）。
- `research/round3_20261031/results/main_A_pi0_ref_s10.json` 的行字段集合同样无该类字段；文档 `meta` 只有 `params_path`、`params_sha256`、`source_sha256` 等，不写“合成/校准”类别。

**缺口 M1**：正式结果只能靠 `params_path`/`params_sha256` + `run_manifest` 命令 + `data_trace` 文字追溯“这是合成车流”；而且该需求本身是**两段式**（观测校准的到达/停留/期初 + 情景 p_EV/q_need），单一 `synthetic` 位也不准确。建议（本轮不实施）：在结果行/meta 写 `demand_source_parts=[observed_calibrated, scenario_input]` 与 `synthetic=true` 两个独立字段。

## 2 (b) 观测校准与情景需求的两来源

**情景侧（已分别标明）**

| 文件:行 | 写入内容 |
|---|---|
| `run_cost_curve.py:182-186` | `generate_for_lot(..., p_ev=..., q_need=..., charge_provenance=...)`，p_EV 与 q_need 作为独立入参 |
| `run_cost_curve.py:255-259` | 行字段 `p_ev_source`、`q_need_source`、`charge_scenario_id`、`charge_provenance`、`demand_calibration_status` |
| `run_cost_curve.py:396` | `base["charge_provenance"] = charge_payload["provenance"] if charge_payload else None` |
| `run_cost_curve.py:430` | 文档 meta 写入 `charge_scenario`（完整 provenance） |
| `apps/parking_lab/workbench/charge_sources.py:9-17` | 硬规则：p_EV/q_need 分开、q_need 不由乘积反推、q_use 只能以 hypothetical_transfer 情景使用、拒绝 q_location_share 等 |
| `charge_sources.py:62-99` | 必填字段校验 + `q_use` 必须 `transfer.type=hypothetical_transfer` 且 statement 非空；`:111 load_catalog` |
| `WIRING.md:12-15` | 入口、catalog sha256、每条结果行带 `charge_scenario_id/charge_provenance`、meta 同时记录 |
| `WIRING.md:31-35` | q_use≠q_need、分母/地区/年份不同、p_EV=0.10 无目标识别证据、禁止平均 |
| `data_trace.py:151-161, 187-192, 210-215, 229-232` | C01 catalog 可解析、C02 6 情景 q_need 与 rates 一致且 p_EV 全 0.10、C03 迁移标签、C04 必填来源字段非空（均 pass） |
| `data_trace.py:371-396` | C11/C12：正式 manager 用独立 p_EV/q_need、分段与成本/删失口径一致（pass） |

**观测校准侧（只有指纹，没有来源分层）**

- `params_path`/`params_sha256` 记录在结果 meta（`data_trace.py:112-140` 的路径表与 C07/C08 复算），但不写观测窗口、`source_class`、拟合限制。
- `data_trace.py:262-275`（C07）与 `data_trace.py:644`：观测链是 279 槽/372 场/18 场参数；`data_trace.py:648-661` 的 G6 明写数据窗口只有两日（307 槽/25.75h）。这些限制**不进入结果行**。
- `demand_calibration_status=scenario_not_identified` 覆盖 p_EV/q_need，但不覆盖“到达/停留/期初来自观测校准”的那一半。

**缺口 M2**：结果行把“观测校准”压缩成 path+sha，无法在行级回答“哪部分来自观测、哪部分来自情景假设”；需要在 meta 增加 `observed_calibration={params_path, params_sha256, window, fit_split}` 与 `scenario_input={p_ev_source, q_need_source, identification_status}` 两个命名块。

**缺口 M3**：`data_trace.py:398-411`（C13）的“M08/M10 观测率未被正式运行入口读取（已转录未接线）”只扫描第三轮运行时目录与第三轮 manifest；第四轮 `scenario_manifest.json` 未被该检查扫描，且 `WIRING.md:10` 已限定“C11/C13 的未接线仅指第三轮”。单独引用 C13 会误读为第四轮仍未接线。

## 3 (c) 隐藏真值/反事实的边界

| 文件:行 | 文本 | 含义 |
|---|---|---|
| `apps/parking_lab/workbench/rules.py:75-76` | `"measurement_only": "这三项是用隐藏真值做的结果计量，只用于研究与成本归因；不得反馈进任何准入决策（决策只看 ObservableState）"` | 隐藏真值只做计量 |
| `apps/parking_lab/workbench/rules.py:446` | 占位分钟“用隐藏真值做结果计量，不反馈进决策” | 同上 |
| `apps/parking_lab/workbench/simulation.py:150-153` | 反事实开关“故意使用隐藏真值，只用于结果归因反事实，不是准入规则；正式规则不读它”，`detail["counterfactual"]="exclude_no_charging_demand"` | 反事实只在归因路径 |
| `apps/parking_lab/workbench/simulation.py:182` | 反事实 B 释放 connector，不改变准入 | 同上 |
| `apps/parking_lab/workbench/costs.py:1-6` | 占桩影响是反事实归因，只进 attribution，不进 total | 成本隔离 |
| `research/round4_20261031/run_scenarios.py:5-6` | “No hidden-willingness inputs are added.” | 情景运行不引入隐藏意愿 |
| `research/round4_20261031/mechanism/README.md:16` | “机制显微镜，不是 workbench 仿真复现；第三轮数据结论仍以其 results/ 为准” | 机制算例定位 |
| `mechanism/shared_capacity_mechanism.md:24` | “未建模：能量/功率、排队、绕行、挪车、预约、π2 预测规则、真实数据。模型是‘机制显微镜’，不能当第三轮数据结论。” | 不能外推 |

**缺口 M4**：`mechanism/shared_capacity_mechanism.json` 顶层只有 `summary`/`results`，没有机器可读的 `analysis_only`/`not_executable_policy` 字段；“不是政策”只写在 README/md 与注释里。另，隐藏真值反事实开关只写入 `detail["counterfactual"]`（`simulation.py:153`），不进入研究结果行，因此同一行的“政策运行”与“反事实运行”在行级不可区分。

## 4 UNVERIFIED 与未做

- UNVERIFIED: `data_trace.json` C20——文档 `per_connector_day=75.299726027397` 与函数值 `75.297676712329` 差 0.002049315068（0.0027%），文档未统一到函数口径；本轮不追平、不改文档。
- 未重跑 `data_trace.py`（只读既有 JSON）；其结论对应 2026-10-31T06:43:57Z 的仓库状态。
- 未新增任何仿真/政策运行；C13 的“未接线”判定只覆盖第三轮，第四轮接线以 `WIRING.md` 与 `scenario_manifest.json` 为准。
