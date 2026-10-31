# 第五轮研究实现报告（复现一致性、MATLAB 验证、可靠性补测与证据收束）

状态: 生效
日期: 2026-10-31
范围: P0 跨轮需求哈希、REF 配置与成本、MATLAB 实际验证、并发/中断可靠性、M18 全文对照、最小重算。
边界: 未启动 RL；未改 Word；未投稿；未扩实验网格；未重启/替换/回填采集器；前三/四轮证据与冻结 JSON 未覆盖。
新证据目录: `research/round5_20261031/`。执行者：lead / matlab / safety / verifier（互斥写范围，见 TODO 与各子报告）。

## 0 结论摘要

| # | 交付 | 结论 |
|---|---|---|
| 1 | 3 个 demand_hash 异常 | **与版本升级相关（第 2 类），非完整根因**；车辆级第一处差异 UNVERIFIED；非配置不同、非同版本不确定、非仅哈希定义变化；仅影响 3 条旧流，决策指标零变化 |
| 2 | MATLAB 实际验证 | R2026a 实跑，许可可用；静态工程 441 行/18 列与 Python 参考对齐（max abs 4.5e-12），独立核对 145/145 通过 |
| 3 | 必要重算 | 未改变主线结论；统一 feeder=336 与 120 的需求/服务/成本 1025 行完全一致 |
| 4 | M18 全文 | 已入库、已通读 p1–p15 并与 M06/M07 六轴对照；38 条页码/式号引用逐条核对；证明在在线附录，仍 UNVERIFIED |
| 5 | 安全可靠性 | 3 个新缺陷修复（F12 高、F14/F15 中、F16 低）；362 测试通过；并发/中断/恢复实测 |
| 6 | 可用于论文 | 主问题与边界见 §6；负面结果表述固定为“已测试模型与情景下未观察到” |

## 1 P0：三个需求哈希异常的根因

**分类：与版本升级相关（第 2 类），但不是完整根因——证据只到哈希/时间线/复现层面，车辆级差异未验证。** 证据链：

1. 两轮同 (lot,seed) 的 p_EV=0.10、q_need=0.36、horizon=1440、start_hour=11.5、规则/seed 相同；feeder 120 vs 336 不进入需求生成。
2. 时间线：第三轮结果 13:26:25 → `traffic_gen.py` 14:07:52 → 第四轮 REF 14:14:15；两轮结果 meta 的 `source_sha256` 显示 `traffic_gen.py`（8c47f55f…→d29baf51…）与 `run_cost_curve.py`（47e4fedb…→3b2241c2…）变化。
3. 当前代码（traffic_gen-2.1.0）同命令重复、独立进程、workers=1 与 8 全部同哈希；**25/25 复现第四轮 REF**，只复现第三轮 22/25，恰为 TPE0330/s2、TPE0401/s2、TPE0695/s3。
4. 对当前原始记录做按时间/按 EV/按 dwell/倒序/重编号置换均不能得到旧哈希 → 不是“记录相同、仅顺序或哈希定义变化”；旧记录值本身不同。
5. **影响量化（41 个 k 全比对）**：3 条流在 k=0..40 的 cost_total、facility_cost、unserved_charge_events/energy、ev/ice rejected、cost_complete **全部相同**，仅 `mean_occupancy_rate`（1e-9~1e-7 量级）与两个 hash 不同。
6. **第一条车辆级差异无法给出**：旧版源码与旧原始车辆记录未被保留（无 git 提交、无快照；round2 v1.1.0 快照哈希也不等于第三轮值）。该点保持 **UNVERIFIED**，未用“重算一次哈希通过”掩盖。

传播路径：`generate_for_lot`（旧 8c47…）→ arrivals 记录 → runner demand_hash / Simulation.traffic_hash → 3 条旧流；14:07 更新版本（d29b…）后同流采样值改变 → 第四轮 REF 新哈希；其余 22 条流两版本同哈希。

处理：3 条旧流不删除、不与第四轮配对比较；当前版本 + 显式参数即新基线，第四轮 REF 已包含这 3 条流的现行版本 k 曲线，无需重跑；若需第三轮 90 流基线，用当前代码重跑另存。
证据：`repro/REPORT.md`、`repro/repro_hash_diff.json`、`repro/verify_repro.py`（EXIT 0）。

## 2 REF 配置与成本

- 两轮显式配置（p_EV/q_need/horizon/start_hour/规则/seeds/lots/charger/accounting 相同；feeder 336 vs 120；workers 8 vs 4）已写入 `config/REPORT.md`，不靠默认值。
- 1025 行配对：feeder 120 vs 336 的 `demand_hash` 全同；服务/成本指标全同；仅 8/1025 行 `peak_power_kw` 不同（120 峰值被截为 120，336 最高 140）。**336 对该 REF 集合非约束（max 140<336），120 对 8 行紧约束但不改变服务/成本指标**；不能推广为“336 对所有情景非约束”，扫描 k 未同步增加 feeder。
- 成本：唯一入口 `costs.facility_cost` 复算 k=1,days=1 = **75.29767671232877**；文档 75.29972602739726，差 0.00204931506849（0.0027%）。分解：文档 = 32.0000000000 + 15804.4/365，与旧取整中间值一致（capex≈116800、维护年额 15804.4）；当前字段给出 31.99797808219178 + 43.29969863013699。差异成因未证，如实保留；**不调参追平**；旧 JSON/旧说明保留，`config/REPORT.md` 为 2026-10-31 更正说明，结果使用函数值。
- 证据：`config/verify_config.py`（EXIT 0）、`repro/ref_feeder336.json`。

## 3 MATLAB 实际验证（R2026a）

- 环境：`C:\Program Files\MATLAB\R2026a\bin\matlab.exe`，`-batch` 运行；`version` = 26.1.0.3203278 (R2026a)，`license('test','MATLAB')` = 1，exit code 0；未重装、未开交互窗口。旧 `matlab/prei/runs` 的 run_metadata 明确记录 2026-10-29 那次是 Octave（is_octave=true, matlab_tested=false），本轮才是首次真实 MATLAB 运行。
- **A 静态 PREI 对齐**：全新 `matlab/static_run/`，legacy 与 corrected 各 441 行×18 列；config/fixture SHA 与 Python 参考一致；并列最优 21/21 一致、best set/每日最优/拒绝量一致；max abs diff 4.5e-12、max rel 2.1e-12（容差 abs 1e-6/rel 1e-9）；ETP 窗口与目标一致；manifest 11 项 0 不匹配。legacy vs corrected 差异只在 ratio=1 列（历史口径），与旧记录一致。
- **B 固定轨迹独立核对**：自写 CSV/MATLAB 脚本（不读 Python 汇总），145/145 通过：设施成本 k=0/1/2 与半日/整日、14kWh/7kW/60min 交付与缺口、Erlang-B 与零负荷、有限 k 表服务约束与整数搜索、A/B/D 轨迹的占位/释放/拒绝/服务、期初/同刻/窗口末 pending。
- **未验证**：不能据此声称冻结原稿已完整复现或当前事件仿真已验证；静态成本含历史口径不能混入当前成本模型；在线附录/命题证明仍未核；静态 `run_metadata` 的平台标签（octave / matlab_tested=false）为源码硬编码，执行者未把它当作运行证据，也未改既有代码。
- 证据：`matlab/static_run/comparison_summary.json`、`matlab/indep/out/indep_summary.json`、`matlab/logs/*.log`。

## 4 安全可靠性补测

- 先复跑第四轮安全回归 345/345 OK；修复后 **362/362 OK**（新增 `tests/test_round5_safety.py` 17 条）。check_all.py EXIT 0。
- 修复：**F12（高）** 进程硬中断后残留 `.result-*.tmp`/空目录导致同一路径永久 FileExistsError、不可重试 → `inspect_output` 状态判定 + 默认明确拒绝并列出残留、`force` 只清自身临时文件后恢复；**F14/F15（中）** 无显式 force、残缺 result.json 只报泛化错误 → `write_output(force=False)` 原子覆盖，corrupt 抛 RuntimeError 明确“不能当成功证据”；**F16（低）** round4 manifest 无结果 sha256/cwd、skipped_existing 只证明文件存在 → 只读审计未改旧文件，本轮 harness manifest 补 cwd/sha256/bytes 并按 fingerprint 核对。
- 实测：同名输出并发 3/3 双进程均“1 成功 + 1 拒绝”；硬中断后无 result.json、残缺 .tmp 判 incomplete；完整结果默认拒绝覆盖、force 原子替换；固定输入修复前后数值完全一致；test_http 顺序 30/30 + 6 并发×5 轮 30/30（0/60 失败，未复现，port=0 排除固定端口冲突）。
- 边界：仅文件 fsync，无目录 fsync（不断电持久性）；恢复假设无并发写者，force 并发为 last-writer-wins；CLI 无 `--force`（F17 未修）。
- 证据：`safety/REPORT.md`、`safety/IMPACT.md`、`safety/before/`（快照+diff）。

## 5 文献：M18 全文与 M06/M07 对照

- M18（TR-D 144 (2025) 104773，17 页，SHA 944b4d2a…）已通读 p1–p15，与 M06、M07 完成六轴对照（决策变量、信息集、共享含义、容量与功率、目标、验证范围），每条带页码/式号与 A/B/C 证据等级；38 条锚点由 `verify_lit_citations.py` 逐条核对（EXIT 0）。
- 要点：M18 是**供应链产权/共建共享**（P/D/C、桩数 n、固定支付 F、Nash 议价 [p4–p6]），全文**无 kW/能量/时长/排队/服务水平约束**（p15 “No data was used”），验证为解析命题 + 数值敏感性图，证明在在线附录（未取得）；M06 是车位匹配准入（p7, p24 排除功率），M07 是预约滚动共享（p8/p11 有功率与冲突约束）。三篇都不做“服务率约束下整数最小 k”的配对比较。
- 写作边界：不能称联合运营/桩共享空白；可写的差异是整数最小 k + 三项服务率联合约束 + 同流配对 + 识别边界；供应链定价/补贴结论不得借用。
- 状态变更：`reading-log.json` M18 由“摘要级”→“全文略读”；笔记与索引已更新（`lit_index.py --write` EXIT 0）。**无需用户再下载 M18**；仍未获取的是 N3（403）/N4（元数据未核），与 M18 无关。
- 证据：`lit/M18_M06_M07_fulltext_comparison.md`、`lit/citations_m18_m06_m07.json`。

## 6 可用于论文的主问题、结论边界与图表证据

- 主问题：在同一条外生车辆流与三项服务率联合约束下，共享/开放规则是否降低所需整数带枪设备数 k（相对专用配置），以及该结论对 p_EV/q_need 情景与规则语义的依赖。
- 边界表述（固定）：**“在已测试模型与情景下未观察到共享减少最小设备数”**；不得写“共享在所有情况下无效/不改变任何设备数”。设备增加（最多 +62）、恢复可行性（2 格）、同 k 服务改善（B/C 容量未服务 6.49% vs 5.02% 等）分别报告。
- 来源情景：M08-BEV/COMBINED/M10 绝对 k 中位 0 变化；all-away 中位 −3 **仅属该情景**，不可概括为“所有来源少 3–5 枪”。
- 可用图表证据：①三异常流哈希/版本证据表（本报告 §1 + `repro/repro_hash_diff.json`）；②feeder 120/336 峰值功率对照（§2）；③成本分解（§2）；④MATLAB 145/145 与静态 4.5e-12 对齐表（§3）；⑤安全修复前后对照（§4）；⑥来源情景 Δk 分布与 π1/π2 区间（第三/四轮报告，未变）。
- 机制最小反例（第四轮 16 个）：独立验收者用独立实现复现 16/16；最小 2 例固定轨迹逐 k 重放相等，交换并列处理规则后仍成立 → **真实路径依赖，不是实现错误**。π0 允许 EV 回落普通位时，k=0→1 使 EV 回流 8→2、ICE 失败率 8/24→7/24，故“ICE 失败率随 k 单调不减”的引理不成立；改变规则语义（strict_pi0）时正 Δk 在机制网格出现 641 格，说明结论只能是条件性否定、不能写成定理；准确条件与轨迹见 `acceptance/REPORT.md` §6。

## 6.1 独立验收（verifier）

- PASS：P0 哈希（自跑 workers=1/8 各 25 流；排序/重编号 22 变体 + 200 随机置换 0 命中）；配置/成本（1025 行需求与 5 项服务/成本全同，仅 8 行 peak 差；成本差 0.00272% 精确分解）；文献 38/38 + 抽 10 条上下文成立；MATLAB `static_verify`×4、`indep_verify`×3 全 exit 0（145/145，max abs 4.547e-12）；可靠性 17/17 + 362/362；冻结 5/5 哈希未变、无新增 PDF、Word 未改；机制 16/16。
- 唯一 FAIL 已收口：TODO/PROGRESS 的 M18“摘要级/对照未做”旧陈述已更新（本轮改）。
- 已修正验收指出的两处文字/实现问题：`repro/REPORT.md` occupancy 差异区间（abs 7.34e-7~2.91e-6、rel 1.07e-6~8.75e-6）；`config/verify_config.py` 恒真字段改为真实比较。
- 验收未覆盖（UNVERIFIED）：旧流第一条车辆级差异、safety 三个探针未复跑、MATLAB 未跑 `apps/parking_lab` 的 Simulation 事件类。

## 11 追加审稿问题核查（2026-10-31 追加）

### 11.1 joint_k 的 None 语义审计

- 范围：59 条既有曲线、975 个 (lot,seed,rule)、127,900 个速率单元。四类细分（`review/none_semantics_4way.json`）：容量率 valid 31,360 / 零需求 N/A 615 / 尚无离场样本 0 / **真实缺失 0** / **非法 0**；EV 率、ICE 率 valid 31,975，其余四类均为 0；离场缺电量率 valid 22,895 / 零需求 N/A 615 / **尚无离场样本 8,465** / **真实缺失 0** / **非法 0**。受影响单元：容量未服务 15；离场缺电量 320（305 个单元存在“有充电需求但窗口内无离场样本”格，15 个单元为零需求）。
- 语义与影响：现实现遇 None 即“跳过”，无法区分零需求 N/A、尚无离场样本与真实缺失。按预登记，零需求 N/A 视为不适用并记录；**尚无离场样本不是 achieved，也不是 N/A，必须作为删失条件下的辅助结果单列**。三约束下当前 achieved 780/975 与预登记一致，推荐零变化；四约束的 310→51 是口径变化（见 §11.2），不是修复结果。真实缺失=0，故本轮无实际影响，但代码风险仍在：新增数据若出现真实缺失会被静默跳过。
- 低位 k 标记：A3 有 15 个、B4 有 259 个单元的首个 None 出现在“≤推荐 k”处，其推荐依赖 N/A 口径；这些单元不得被表述为“全域最小”，只能写“网格内最小/按预登记 N/A 处理”。
- 处理：不调参、不改预登记；审计与计数器已落盘（`review/joint_k_none_audit.json`）。若后续增加数据源，应先加“N/A/缺失/非法”三态显式判定再重算受影响单元。

### 11.2 α 与第四约束的重分析（只读既有曲线）

- 口径：α∈{2%,5%,10%} 作用于原三约束（集合 A）；集合 B 再加“离场缺电量率 ≤5%”（固定）。feeder/功率/需求/删失按块记录（第三轮 336、第四轮 120；不合并推断）。
- 集合 A：规则 B 的 Δk 中位 0、Q1=Q3=0、**正 Δk=0**（α=2% 负 1、5% 负 2、10% 负 2，min −22）；四类计数：双方可行 172–175、仅专用可行 11–13、**仅共享可行 0**、均未达成 27–32（每 α 215 对）。规则 D 同向（详见 JSON）。
- 集合 B：第四约束把可达成单元压到 59–60/215（α=5% 时），**均未达成 149**；Δk 仍在 0 附近且正值为 0。含义：在 k≤40 内“离场缺电量率≤5%”对多数单元不能同时满足，不能据此称 k 不可行，只能写“网格内未达成”；该约束的可行性边界需另做专门标定（本轮不做）。**口径更正：review 报的 4 约束达成 310→51，是把零分母一律当失败（严格）与预登记 N/A 口径的差，属口径变化，不是修复结果；按预登记仍为 310。** 能量约束若要进主结论，必须同时固定：①到达群体（独立情景、既定 lot/seed 与种子）；②拒绝需求（capacity unmet=未服务，不等于离场缺电）；③离场随访（离场后补能行为在本仿真无观测，`costs.py:718` 保持 null）。三者不齐时只作删失条件下的辅助结果。
- 四类可行性（fixed-k 独立种子，seeds 5–10，同 k=k_A）：B 规则 34/2/0/12、D 规则 35/1/0/12（双方可行/仅专用/仅共享/均不可行），汇总 96 cell：双方可行 69、仅专用 3、仅共享 0、均不可行 24；双方可行单元离场缺电量率均值 0.508（69 中 36 有定义）。服务指标按四类分别报告（`review/four_categories.json`）；区间只描述既定情景，不宣称总体显著性。
- 与基线 k 的变化：集合 A 在 0.05/0.02/0.10 下分别 0/4/27 个单元改 k；集合 B 分别 268/272/277（共 520 单元）——第四约束主导变化，但 Δk 排序未翻转，正 Δk 仍为 0。
- 未补算：第四轮情景块缺 C_quota 曲线（只覆盖 B/D），已记录为“未补算”；未扩网格。

### 11.3 元数据实际调用路径核对

- (a) 纯合成标识：工作台/API 入口保留 `synthetic`（`experiments.py:25`、`server.py:203`、`continuous.py:276-288`、`costs.py:681`），但**正式研究结果行不保留** `synthetic/data_source/assumptions`（`run_cost_curve.py` 行字段无此三项）→ 缺口 M1。
- (b) 两来源分列：情景侧 provenance 完整（catalog/record 哈希、p/q、迁移声明）；观测校准侧只有 path+sha256，缺“哪一部分是观测校准、哪一部分是情景输入”的机器可读字段 → M2/M3。
- (c) 隐藏真值/反事实：代码与注释明确“只作计量/归因，正式规则不读”，未见被当可执行政策；缺机器可读标签 → M4。处理：本轮不改实现，建议下轮在结果行加 `demand_source_parts=[observed_calibrated, scenario_input]` 与 `synthetic` 两个独立字段后重算受影响输出（只影响元数据，不影响数值）。

### 11.4 贡献可行性检查（详见 `contribution/contribution_check.md`）

- 候选 A：**仅支持“同一乘积 z 下的分解敏感性”**。z=p_EV·q_need=0.036 固定时，三种分解 (0.06,0.60)/(0.10,0.36)/(0.18,0.20) 在 15 个 lot-seed 单元上的联合 k* 相差 2–20 档（TPE0330/s2 甚至出现可行/不可行翻转）。**未证明观测分布等价**，也没有证明一般性的不可识别；这是有限样本敏感性证据，放方法与局限，不作定理或独立贡献。用途：报告需以分解为条件、0.0364 只是 usage proxy。
- 候选 B：**未形成新贡献**。能量下界是基础守恒条件，本身成立；但不足以构成必要条件/不可行证书（停车/接入依赖离散事件规则，只有 k≤40 网格观察），也谈不上创新——不称“基础守恒条件不成立”。
- 对照 M18 全文：M18 为确定性供应链博弈，无识别与情景分解，A 的问题不被其覆盖；但 A 的论证初等，写作中放方法与局限，不列为独立贡献。

### 11.5 追加核查的校验

- review 三脚本（audit_joint_k / reanalysis_alpha_constraints / four_categories）命令、解释器、退出码 0 均写入 `review/run_manifest.json`；joint_k 审计 59 条曲线/975 单元/127,900 率格，真实缺失 0、非法 0。
- `check_all.py`（DSH Python）在追加核查后重新运行：3/3 通过、EXIT 0；期间一次因 PROGRESS 长度超限失败，已压缩后通过（非研究结论变化）。

## 12 重算影响

- 3 条异常流：现行版本已由第四轮 REF 重算（含全部 k），且与第三轮旧值在全部决策指标上相同 → 对主结论（Δk 中位 0、无正 Δk、π1/π2 区间）**无影响**。
- 统一配置：feeder 336 配对重跑 1025 行，需求/服务/成本指标与第四轮 120 完全一致 → 不需要重算第四轮情景曲线。
- 结论：**本轮最小重算未改变任何主线结论**；变化仅在哈希与描述性占用率（1e-9 级）。

## 13 验收命令与退出码

| 命令 | 退出码 | 说明 |
|---|---|---|
| `python research/round5_20261031/repro/verify_repro.py` | 0 | 25 流确定性/worker 不变性/25 复现第四轮/22 复现第三轮 |
| `python research/round5_20261031/config/verify_config.py` | 0 | feeder 120/336 一致性 + 成本算术 |
| `python research/round5_20261031/lit/verify_lit_citations.py` | 0 | 38 条引用逐条核对 |
| `matlab.exe -batch ...static_verify` | 0 | 静态 PREI 对齐，441 行，max abs 4.5e-12 |
| `matlab.exe -batch ...indep_verify` | 0 | 145/145 独立核对 |
| `python -m unittest discover -s apps/parking_lab/workbench/tests` | 0 | 362 tests OK |
| `python scripts/check_all.py`（DSH Python） | 0 | 0 错误；8 条既有历史警告 |
| `python scripts/lit_index.py --write` | 0 | 索引重建 |

解释器：C:\anaconda\python.exe 3.12.3 + PyMuPDF 1.28.2（抽取/复算）；C:\Users\tho25\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe 3.12.14 + python-docx（check_all）。

## 14 冻结与未验证清单

- 冻结：`lit/frozen_sha256_before.txt` 记录 5 项哈希，收尾复算一致；未新增 PDF、未改 Word、未覆盖前三/四轮结果与旧交付 JSON（核验见 `acceptance/`）。
- UNVERIFIED：①3 条旧流的车辆级第一处差异（旧源码/旧原始记录未保留）；②M18 在线附录证明与命题条件、图 2–7 具体数值；③M18 建桩数是否隐含整数约束（正文未见，按连续模型）；④M06/M07 报告数值未复算；⑤断电持久性（仅文件 fsync）；⑥机制最小反例复核（acceptance 已完成，见其 §6）；⑦review 收尾未执行：第四轮情景缺 C 曲线、seeds 6–10、feeder=336 版、validation 4 场站、B/C/D 的 TPE0330 扩展；⑧data_trace C20 文档成本差 0.0027% 未对账（与旧取整中间值一致，成因未证，不追平）；⑨机制 strict_pi0 下正 Δk 出现 641 格，只作机制分解，未定理化。

## 16 研究收口（2026-10-31，低消耗）

本节只整理既有结果与表述口径：不新增 RL/大网格/理论路线，不改 Word，不覆盖旧结果；唯一新增核对是四类语义结算（只读 59 条既有曲线，不重跑仿真）。

### 16.1 四类语义与结论口径

| 率 | valid | 零需求 N/A | 尚无离场样本 | 真实缺失 | 非法 |
|---|---|---|---|---|---|
| capacity_only_unmet_rate | 31,360 | 615 | 0 | 0 | 0 |
| ev_parking_failure_rate | 31,975 | 0 | 0 | 0 | 0 |
| ice_parking_failure_rate | 31,975 | 0 | 0 | 0 | 0 |
| departed_shortfall_energy_rate | 22,895 | 615 | 8,465 | 0 | 0 |

- **零需求 N/A**：分母=0 且该情景无对应需求（无 EV 到访/无充电请求）；按预登记跳过并记录，不是 achieved、不是缺失。
- **尚无离场样本**：有充电请求但窗口内无离场记录（departed_requested_kwh=0），属删失/随访不足，不是 N/A，也不是失败；305 个单元存在该情形，全部集中在离场能量率。
- **真实缺失/非法**：本轮均为 0；代码对 None 仍无显式三态，新增数据源前必须补判。
- **310→51 不是修复结果**：它是“零分母一律当失败”的严格口径与预登记 N/A 口径之差；按预登记四约束仍达成 310。
- **能量约束定位**：只有同时固定到达群体（独立情景、既定 lot/seed/种子）、拒绝需求口径（capacity unmet=未服务，不等于离场缺电）和离场随访（离场后补能行为无观测，`costs.py:718` 保持 null），才可进主结论；否则只作删失条件下的辅助结果。

### 16.2 贡献表述（收窄后）

| 对象 | 可写 | 不可写 |
|---|---|---|
| 候选 A | 同一乘积 z 下不同分解的 k* 敏感性（15 单元，差 2–20 档） | 观测分布等价、一般不可识别定理、新模型 |
| 候选 B | 能量下界作为工程 sanity check | 必要条件/不可行证书、新贡献；也不称基础守恒条件不成立 |
| 版本关联 | 与 traffic_gen/runner 版本升级相关，可解释 3 条流差异 | 完整根因、车辆级第一处差异已定位 |
| 成本差 | 与旧取整中间值一致，未调参追平 | 成因已证实为取整 |

### 16.3 论文论证提纲（基于既有结果）

1. 问题：整数建桩 k 在联合停车/接入/能量服务率约束下的最小可行配置；文献缺口只限“停车与充电联合运营、共享分配”（M18/M06/M07），不写空白。
2. 参数来源与迁移：到达/停留由观测校准，p_EV/q_need 为情景输入；q_use→q_need 迁移假设单列，不称识别值。
3. 模型与联合约束：三约束 α + 第四能量约束（辅助）；整数 k、容量/停车/接入规则、删失与 N/A 语义。
4. 固定 k 服务权衡：四类可行性 69/3/0/24；共享规则无正 Δk、仅专用可行 3 单元；区间只描述既定情景。
5. 可行性恢复与规则语义：负 Δk 2/2/1（min −22）；机制 16/16 反例与 strict_pi0 641 格说明路径依赖，只能条件性表述。
6. 识别边界与稳健性：同 z 分解敏感性（A）；p_EV 与 q_need 分列报告；α 2/5/10% 与第四约束重分析。
7. 局限与复现：版本关联非完整根因、成本差成因未证、旧流车辆级差异 UNVERIFIED、网格有限；命令与退出码见 §13。

### 16.4 图表证据表

| 图/表 | 论证点 | 证据产物 | 命令/来源 | 可写边界 |
|---|---|---|---|---|
| T1 参数来源 | 观测校准 + 情景 p/q + q_use→q_need 迁移 | catalog、charge_sources、data_trace | `research/round4_20261031/data_trace.py`（既有） | 情景输入，不是目标场景识别值 |
| T2 联合约束 | 三约束 α、第四约束辅助、N/A/删失语义 | PREREGISTRATION.json:61、joint_k_none_audit、none_semantics_4way | `review/audit_joint_k.py`、`review/none_semantics_4way.py` | 零分母不判失败；310/51 为口径差 |
| T3 固定 k 权衡 | 双方/仅专用/仅共享/均不可行 69/3/0/24 | four_categories.json | `review/four_categories.py` | 同 k、既定 seeds 5–10，不作显著性 |
| T4 可行性恢复 | 负 Δk 2/2/1、min −22；仅专用 3 | reanalysis_alpha_constraints.json | `review/reanalysis_alpha_constraints.py` | 网格内；不写“共享必然省枪” |
| T5 规则语义 | 16/16 机制反例；strict_pi0 641 正 Δk | acceptance/mechanism_counterexamples.json | `acceptance/` | 条件性否定，不是定理 |
| T6 识别边界 | 同 z 三分解 k* 差 2–20 | contribution/samez_decomposition.json | `contribution/`（补算已做） | 有限样本敏感性，不宣称分布等价 |
| T7 复现与版本 | 25/25 复现第四轮、22/25 第三轮；3 流决策零变化 | repro/REPORT.md、verify_repro.py | `python research/round5_20261031/repro/verify_repro.py` | 版本关联，非完整根因 |
| T8 局限 | UNVERIFIED 清单 | §14 | — | 不隐藏 |

### 16.5 收口状态

- 本轮未新开 RL/大网格/理论路线；只新增只读结算脚本 `review/none_semantics_4way.py` 与 JSON；同 z 补算（2 文件×615 行）在上一小节已完成，未再跑仿真。
- TODO 仍登记原任务；后续写作直接从 §16.3/§16.4 取材，不再另起全面审计。

## 17 下一项最小必要动作

1. 若写作需要用第三轮 90 流基线：用当前代码重跑 `main_A`/其余规则并另存 v2 基线（约 1 轮实验，不改参数）。
2. 论文写作前：把 §6 主问题与 §5 边界写入 Introduction/Discussion 草稿；补 N3/N4 文献状态（不阻塞）。
3. 若需强化可靠性：CLI 增加 `--force` 显式开关（F17）并补目录 fsync（声明仍不保证断电）。
