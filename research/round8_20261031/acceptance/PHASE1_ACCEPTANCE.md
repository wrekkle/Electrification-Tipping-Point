# R8 Phase 1 独立验收报告（R8-D / task-4）

类型: 验收报告
状态: 生效（仅 Phase 1；Phase 2 未开始）
负责人: R8-D（独立验收者）
日期: 2026-10-31
写入域: research/round8_20261031/acceptance/**

## 0 快照、环境与边界

- 验证时间窗：2026-10-31T19:03–19:12 +08:00（11:03–11:12Z）。
- 复验时间：2026-10-31T19:14–19:15 +08:00（T1.8/T1.9 复验通过；T4.2 同步复验）。首次验证的失败证据与复验证据均保留在 `acceptance/evidence/`。
- Python：C:\Users\tho25\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe，3.12.14。
- 契约快照（第 3、4 节结论以此为准）：
  - path `research/round8_20261031/data/processed/public_parking_events.json`
  - bytes `46,525,880`，SHA-256 `38b1422bb95d4122565d4de70a5ef4faf35e41600019068c9c077a295ee6bdf6`，mtime `2026-10-31T19:05:27+08:00`
  - schema `public_parking_events/v1`，dataset_id `melbourne_parking_bay_events_2014`
- 原始 zip 快照：bytes `247,682,126`，SHA-256 `B92333B236D5DA0FBDC1AB0A195E57EB7A90EA4A3FDA30D06CF9938A3AD02A34`。
- **并发重建风险（重要）**：验证期间 Lead 仍在重建数据产物。同一契约路径先后出现 35,052,295 B（185,552 事件、2 条 blocking 缺 dwell、141,680 条 `duplicate_id_rekeyed` 警告）→ 46,525,880 B（185,550 事件、0 错误）；E1 manifest 记录输入哈希由 `ac29ac4a…` 变为 `38b1422b…`；`publicdata.py` mtime 19:02:32 仍在变。本报告所有数字绑定最终快照；产物冻结后需一次性复跑复核。
- 只读边界：未修改任何 `acceptance/**` 之外的文件；发现缺陷只登记、不修复。
- **Phase 2 未做**：E1–E7 机器输出正确性、图表与机器结果一致、稿件/SI/复现包对应、能量分母与 k 最小性、统计单位与重采样、Word/PDF 渲染均未验收，不宣称完成。

## 1 台北专属模块退出（任务第 1 项）

| ID | 检查项 | 结论 | 证据（命令 / 路径 / 观测值） |
|---|---|---|---|
| T1.1 | 采集进程确已停止、无残留 | PASS | `Get-CimInstance Win32_Process` 过滤 `poller\.py|372_polling` → 0 命中；仅 2 个与本项目无关的 python.exe（模拟投资大赛 pip install）。`runtime/state.json`：`status=stopped`，last_success 2026-10-31T10:35Z，total_rounds=371。`runtime/STOP` 内容 `2026-10-31T10:37:58.630205+00:00`。证据：`research/collection/taipei_372_polling_20261030/runtime/{state.json,STOP}`、`acceptance/evidence/taipei_process_state.txt` |
| T1.2 | 无定时任务/守护重启 | PASS | `Get-ScheduledTask` 全表 211 条，Execute/Arguments 匹配 `poller|taipei|parking_lab|372_polling` 为 0；启动文件夹 3 项均无关（LocalQwenKeepAlive.vbs、Ollama.lnk.disabled、OpenClaw Gateway Supervisor.vbs.disabled）；仓库仅 `collection/polling/daemon.py` 进程内 supervise 循环，随进程停止。 |
| T1.3 | workbench 无 `datasource.py` | PASS | `Test-Path apps/parking_lab/workbench/datasource.py` = False；`import apps.parking_lab.workbench.datasource` 抛 ModuleNotFoundError（test_round8_exit 该用例通过）。残留 `__pycache__/datasource.cpython-312.pyc`（无源不可 import，建议清理；非 FAIL）。证据：`acceptance/evidence/code_surface_grep.txt` |
| T1.4 | `server.py` 无 `/api/datasource` 与导出格式 | PASS | `Select-String server.py -Pattern datasource` 0 命中；路由仅 health/presets/state/export/validate/compare/create/close/step/run/reset/advance/mode/speed/pause/resume/replay*；导出仅 `/api/export → parking-run.json`（EXPORT_SCHEMA_VERSION=2）。 |
| T1.5 | `continuous` 只接受 synthetic 回放 | PASS | `continuous.py:275-281`：source != "synthetic" 时 `raise ContinuousError("回放源必须为 synthetic（通用合成账本回放）")`；`replay_step` 返回 `source="synthetic_ledger"`。 |
| T1.6 | `__main__` 无 `--collection` / `data-span` | PASS | `__main__.py` argparse 仅 `--port/--config/--seeds/--out/--params/--seed/--split`，命令 serve/run/compare/traffic；grep 0 命中。 |
| T1.7 | web 无台北面板/按钮 | PASS | `index.html`、`app.js` grep `datasource|taipei|replay-taipei|ds-badge|ds-refresh` 0 命中；仅 `replay-synthetic` 与通用 `/api/*` 调用。 |
| T1.8 | 工作台测试实际运行结果（计数/exit code） | **PASS（复验）** | `python -m unittest discover -s apps/parking_lab/workbench/tests -p "test_*.py"` → **Ran 414 tests, OK, exit 0**（2026-10-31T19:14:43 复验）。修复：`test_round8_exit.py:17-18` 的 `HIST_MARKS` 扩为含 "不读/禁止/不得/not read"，`publicdata.py:12` 的禁止性描述不再误伤；`INVENTORY.md` §5 已更新为 414；残留 `__pycache__/datasource.cpython-312.pyc` 已删除。证据：`acceptance/evidence/unittest_recheck_20261031_1915.log`（首验失败证据保留在 `unittest_final_20261031_1909.log`） |
| T1.9 | `python scripts/check_all.py` 错误/警告数 | **PASS（复验）** | exit **0**（2026-10-31T19:14:43 复验）：文档与链接检查 **错误 0，警告 174**；文献索引 **错误 0，警告 8**；汇总三项全部 **通过**。修复：`docs/reports/2026-10-31-R8数据选型与质检.md` 状态行改为 `状态: 生效`。证据：`acceptance/evidence/check_all_recheck_20261031_1915.log`（首验 exit 1 证据保留在 `check_all_20261031_1908.log`） |

## 2 数据许可与版本（任务第 2 项）

| ID | 检查项 | 结论 | 证据 |
|---|---|---|---|
| T2.1 | City of Melbourne 数据集页/许可 | PASS | `web_fetch https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/parking-bay-arrivals-and-departures-2014` → `license: "CC BY"`，`license_url: https://creativecommons.org/licenses/by/4.0/legalcode`，`modified: 2020-08-05T00:00:00+00:00`，下载链接 `https://opendatasoft-s3.s3.amazonaws.com/downloads/archive/mq3i-cbxd.zip`，描述 "247.7MB, 13.5 million rows"，`records_count: 0`（与 CANDIDATES §0/§2.5 "门户 rows=0" 一致）。与 `data/PROVENANCE.json` 的 CC BY 4.0 声明一致。 |
| T2.2 | raw zip 实际 SHA-256 / 字节数 | PASS | `Get-FileHash … -Algorithm SHA256` → `B92333B236D5DA0FBDC1AB0A195E57EB7A90EA4A3FDA30D06CF9938A3AD02A34`；`Length=247,682,126`；与 `data/PROVENANCE.json` `archive_sha256`/`archive_bytes` 完全一致。证据：`acceptance/evidence/raw_zip_hash.txt` |
| T2.3 | timezone 声明与数据自洽 | PASS | 从契约 185,550 事件按 `arrival_ts` 本地小时统计：07–19 时 11,315/11,876/17,420/18,398/18,693/19,272/16,988/15,504/13,851/12,749/13,991/9,177/3,534；00–05 时 242/79/51/62/120/135。高峰在本地白天（07:30–19:30 咪表时段），与"存的是 Melbourne 本地墙钟、`+0000` 非真实偏移"的声明自洽。窗口 2014-01-06..03-31 全程 AEDT=UTC+11（DST 切换 2014-04-06 在窗口外），契约时间戳带 `+11:00`。局限：无第二个独立 UTC 来源，只能证明自洽（PROVENANCE 亦标 unresolved）。 |

## 3 契约合法性（任务第 3 项）

| ID | 检查项 | 结论 | 证据 |
|---|---|---|---|
| T3.1 | `load_contract` / `validate_contract` 实跑 | PASS（绑定快照） | 快照 sha `38b1422b…`：`validate_contract` → `ok=True, blocking_errors=0, sites=10, events_declared=185,550, events_accepted=185,550, events_rejected=0, errors=0, warnings=0, missing_needs_charge=0, missing_energy_kwh=178,962`；strict `load_contract` 成功（10 sites / 185,550 events）。证据：`acceptance/evidence/contract_validate.json`。注：早期 35 MB 快照曾 `ok=False`（2 条 `missing_field` 缺 dwell）+ 141,680 条 `duplicate_id_rekeyed` 警告，最终重建已修复；故本条结论只对上述快照成立。 |
| T3.2 | `is_ev/needs_charge/energy_kwh` 明确标 scenario 而非 observed | PASS | `provenance.observed_fields=[event_id/window_row, site_id, arrival_ts, dwell_min]`；`provenance.scenario_fields` 明示 `is_ev=Bernoulli(0.10) … NOT observed`、`needs_charge=Bernoulli(0.36) among EV only, scenario assumption`、`energy_kwh=truncated normal(14,6,[2,40]) … not measured`、`hardware=… scenario assumptions, not observed`。实测计数：is_ev=True 18,566（10.0%）、needs_charge=True 6,588（EV 的 35.5%）、energy_kwh 非空 6,588（与 needs 对齐）。 |
| T3.3 | 10 场站容量/窗口事件数/complete_days 复核 | PASS | 契约 `n_spaces` 与 `_window_events.csv`（236,819 行、24 个 area）按 `area` 去重 `bay_id` 完全一致：82/58/35/72/40/15/33/12/17/18。事件数逐场站与窗口一致，除 2 条例外（Victoria Market 24,891 vs 24,892；Hyatt 14,295 vs 14,296），由 `provenance.event_level_exclusions.dropped_missing_or_nonpositive_dwell=2` 解释。complete_days 按当前定义（"local day with arrivals in >=6 distinct two-hour buckets (>=12 h operating window)"）抽 5 场站复算全部相等：Queensberry 85=85、Jolimont 85=85、Drummond 61=61、West Melbourne 72=72、University 61=61。 |

## 4 旧数据隔离（任务第 4 项）

| ID | 检查项 | 结论 | 证据 |
|---|---|---|---|
| T4.1 | 引用台北快照/旧 fitted_parameters/旧 traffic JSON/旧结果 | PASS | 全树 grep `taipei|fitted_parameters|traffic.*json|datasource` 仅命中：`PLAN.md §1` 禁止性说明、`DESIGN_MATRIX.json forbidden_inputs`、`taipei_exit/INVENTORY.md`、`REMOVAL_MANIFEST.json`、`removed/datasource.py`（冻结副本）、`traffic_gen.py` 首行 HISTORICAL 标注；`engine/` grep 旧路径 **NO MATCH**；`experiments/*/manifest.json` 的 `inputs` 只有契约路径。 |
| T4.2 | manifest 输入路径/哈希抽查 | **PASS（复验）** | 2026-10-31T19:15 复验：E1–E7、M 全部 `manifest.json` 的 `inputs[*].sha256` = 当前契约 `38b1422b…`（`E2–E7/M` 已按最终契约重跑），所有声明的 outputs 均存在，`missing_data.json` 空壳已清理（0 个）。首验时 E2–E7/M 记录 `ac29ac4a…` 的不一致已修复。 |
| T4.3 | contract arrivals/dwell 无合成痕迹 | PASS | 以 `(site_id, arrival_ts[:19], dwell_min)` 多重集比对：契约 185,550 事件 vs `_window_events.csv` 10 场站口径 → IN_BOTH=185,550、CONTRACT_ONLY=0、WINDOW_ONLY=2（恰为两条缺 dwell 被剔除行）。`is_ev/needs_charge/energy_kwh` 不在窗口 CSV 中，属构建期加入且已在 provenance 声明。 |

## 5 信息公平预检（任务第 5 项）

| ID | 检查项 | 结论 | 证据 |
|---|---|---|---|
| T5.1 | B0/B1/B2 只用可观测字段 | PASS | `rules.ObservableState`（rules.py:94-113）为冻结 dataclass，docstring 明示"不含 needs_charge/能量/真实离场时间/未来到达"，字段仅 time_min/is_ev/free_bays/n_spaces/charging_bays/chargers/arrival_rate_per_hour/p_ev/p_charge_given_ev/已观察离场统计/ice_charging_bays。`engine/baselines.py`：B0 类型盲 FCFS、B1 复用 `protected_quota`（训练集预注册 m）、B2 EV 优先 + ICE 借用门（只用可见统计与短期预测）；`BASELINE_META` 三基线均 `information="online_observable"`；B2 `literature_status="规则改编"`，P09 标 UNVERIFIED（仅索引层，未复现定价定理）。未发现"用未来信息却标在线可执行"的基线。披露提醒：B2 使用的 `p_charge_given_ev=0.36` 是情景假设参数，论文须标为情景输入。 |
| T5.2 | offline_opt 明确标注离线上界 | PASS | `offline_opt.py` 模块 docstring 与 `min_connectors`/`check_feasible` 返回字段：`information="offline_upper_bound_not_executable"`、`uses_future_information=True`、`model="offline_uniform_power_minute_grid"`；明确 0..K_max 逐整数完整枚举、禁二分/跳点、禁 peak×mean×safety 伪上界；E3 输出含 `evidence_model`/`information` 列。 |

## 6 复验后的问题状态（2026-10-31T19:15）

**已修复并复验通过**
- P1（首验 FAIL，已关闭）：工作台测试 414 tests OK / exit 0；`check_all.py` exit 0、错误 0（文档警告 174 + 文献警告 8 通过）。修复与证据见 T1.8 / T1.9。
- P2（首验 FAIL，已关闭）：E2–E7/M 已按当前契约 `38b1422b…` 重跑，manifest 输入哈希一致、`missing_data.json` 空壳已清理。见 T4.2。

**仍开放（Phase 2 期间跟踪）**
- P3：`data/PROVENANCE.json` 仍引用不存在的 `data/processed/unified_events.csv`、`contract_columns` 与实际契约字段不符；`data/qa/QA_REPORT.md` §4 窗口写 "2014-01-06..03-30" 而 `coverage.window.end=2014-03-31`，§3 仍把"场站级完整日"列为 UNVERIFIED（契约已提供 `complete_days`=789）。→ 不阻塞 Phase 1，但投稿前必须由数据 owner 统一。
- P4（风险）：验证期间产物并发重建（契约 35.0MB→46.5MB，sha 变化；publicdata.py 19:02 仍改）。Phase 2 期间如再重建，需重新绑定快照。

## 7 未覆盖 / UNVERIFIED

- Phase 2 全部未做（见 §0）。
- 时区原始标注的独立确认：**UNVERIFIED**（无第二独立 UTC 来源；只证明数据与声明自洽）。
- E2–E7/M 输出与当前契约的一致性：**UNVERIFIED**（manifest 哈希不一致，需重跑）。
- 未重跑实验、未核图表/稿件/SI/复现包/Word/PDF。
- 未验证 `_window_events.csv` 的 `arrival_utc` 列（全空，0/236,819 非空）是否应使用；当前契约用 `arrival_ts`（本地 +11:00 偏移）不依赖该列。

## 附录：证据文件

| 文件 | 内容 |
|---|---|
| `acceptance/evidence/contract_validate.json` | 契约快照元数据 + validate/load 报告 + 观测计数 |
| `acceptance/evidence/raw_zip_hash.txt` | raw zip 字节数与 SHA-256 |
| `acceptance/evidence/taipei_process_state.txt` | 进程/计划任务/runtime state 快照 |
| `acceptance/evidence/code_surface_grep.txt` | server/web/CLI/replay/datasource 残留检查 |
| `acceptance/evidence/check_all_20261031_1908.log` | check_all 完整输出（错误 1，警告 174+8） |
| `acceptance/evidence/unittest_final_20261031_1909.log` | unittest 最终输出（414 tests / 1 failure） |
| `acceptance/evidence/unittest_recheck_20261031_1915.log` | T1.8 复验：414 tests OK / exit 0 |
| `acceptance/evidence/check_all_recheck_20261031_1915.log` | T1.9 复验：exit 0 / 错误 0 / 三节全通过 |
| `acceptance/acceptance_phase1.json` | 逐条机器可读结论（id/结论/证据命令/证据路径/时间） |