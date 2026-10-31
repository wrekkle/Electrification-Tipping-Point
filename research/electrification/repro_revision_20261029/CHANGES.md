# 后端修订说明（2026-10-29，R1–R7）

类型: 研究代码修订
状态: 生效
负责人: tho25
日期: 2026-10-29

本目录是 `research/electrification/repro/` 的**修订副本**，用于落实
[审查报告](../../../docs/reports/2026-10-29-新增文献与仓库审查.md) 的 R1–R6 与 T8 的场地/能量口径核查（R7）。
原目录保持只读，未改动；本目录只含源码、配置、测试与说明，**不含** `outputs/`、`__pycache__/` 与任何缓存。

- 复制来源、时间、原文件 SHA-256：`PROVENANCE.json`
- 修复前回归结果（对未修订副本运行同一套测试）：`before_regressions.log`
- 修复后单元测试：`after_unittest.log`
- 统计方法合成实验：`reports/stat_experiment.json`（`tools/stat_experiment.py`）
- 重算基线：`baseline_run1.log`、`baseline_run2.log`、`outputs_revision/`
- 修复前后数值（R1–R6 每项）：`reports/before_after_r1_r6.json`（`tools/before_after_probe.py` 生成）
- 机器可读汇总：`reports/backend_fix_evidence.json`（`tools/build_evidence.py` 生成）

## 0. 代码拆分与强化（2026-10-29 本轮，行为不变）

起因：`src/prei/evaluate.py` 43,998 字符、`stats.py` 24,978、`run_all.py` 28,462、回归测试 44,307 字符，超过 `repo-discipline.json` 的 24,000 字符软线；单文件混合需求层、静态层、v2 层与输出层，改动传播面大。

处理（函数体逐字节搬移，未改写逻辑；门面保留原公共导入面）：

| 原文件 | 拆分后 |
|---|---|
| `src/prei/evaluate.py` | `evaluate.py`（门面）+ `evaluate_base.py` + `evaluate_v2.py` + `evaluate_outputs.py` |
| `src/prei/stats.py` | `stats.py`（门面）+ `stats_bootstrap.py` |
| `run_all.py` | `run_all.py`（入口）+ `run_blocks.py`（各层实现） |
| `tests/test_prei.py` | `test_core.py` + `test_stats_sim.py` + `test_v2_outputs.py` |
| `tests/test_review_regressions.py` | `test_regressions_r.py` + `test_regressions_f01.py` + `test_regressions_f09.py` |

新增 `tests/test_module_layout.py`（5 条：导入成功、36 个 evaluate 名与 6 个 stats 名的重导出、分层无环、`src/prei/*.py` 均 < 24,000 字符）。

验证（2026-10-29 实测）：

- `python -X utf8 -m unittest discover -s tests`：`Ran 102 tests`、`OK`（拆分前 97 条全部保留，新增 5 条边界测试）。
- `run_all.py --mode static --out <临时目录> --no-canonical`：exit 0、6 s、17 个文件。
- `run_all.py --mode v2 ...`：exit 0、184.69 s；与 `outputs_revision/baseline/20261029-174509-seed42` 对比，`v2_best.csv`/`v2_designs.csv`/`v2_regions.csv`/`v2_service_accounting.csv` 共有数值列逐行一致，`v2_g_curve.csv` 仅 `g_coverage_scope` 说明文本不同（该字段为后续修订扩写，非本次改动）。
- `run_validation_t14.py`：`REGRESSIONS 12 / 12`，输出 JSON 与拆分前 `results_t14/results_20261029_T14_bounds.json` 逐字段一致（去掉 `output` 路径字段）。

未改动：`repro/` 原目录（只读契约）、`code/_t14b_backup_20261029/`（备份快照），二者仍报源码软线警告。

注：`research/measurement/validation_20261029/code/run_validation_t14.py` 在本轮拆分后被另一并行会话的 T14c 修订重写（恢复为单文件、42,792 字符），本目录的拆分不涉及该文件；为避免与并行改动冲突不再动它，后续拆分另行排期。

## 1. 时间单位契约（R1）

v2 事件层只有**一种**时间单位：**开盘后分钟数**。接口与字段：

| 位置 | 字段 | 单位 |
|---|---|---|
| 需求层 `demand.simulate_day_arrivals` | `times_min` | 分钟（内部按小时抽 NHPP，出口处换算一次） |
| 同上 | `window_min` / `time_unit` | 分钟 / `"minute"` |
| 日记录 `day["dwell_min"]` | 停留时长 | 分钟 |
| 日记录 `day["energy_req"]` | 能量请求 | kWh |
| 设计 `power_kw` / `feeder_kw` | 额定功率 / 馈线 | kW |
| 设计 `reposition_min` | 移动换位耗时 | 分钟 |
| 事件行 `t_a` / `t_c` / `t_d` / `t_r` | 到达/连接开始/充电结束/离场 | 分钟 |
| 指标 `metrics["time_unit"]` | 单位声明 | `"minute"` |

连接时长不再硬编码 60，而由功率—能量关系导出：`duration_min = energy_kwh / power_kw * 60`。
`simulator.simulate_day` 对缺少 `times_min` 的日记录直接 `ValueError`，不接受用 `times` 猜单位。

修复前（原副本，`times=[11.5]`、停留 60 分钟、20 kWh）：
`t_a=11.5, t_c=11.5, t_d=35.5, t_r=71.5`，即小时与分钟相加。
修复后：`t_a=690.0, t_c=690.0, t_d=714.0, t_r=750.0`（分钟），`t_d-t_c=24 min` 与 20 kWh/50 kW 一致。

## 2. R2：g 区间的配对与广播

`stats.g_interval` 的两条臂用**同一个** bootstrap 索引矩阵重采样，并先把两条臂压成一维再相减；
修复前 `(B,1) - (B,)` 广播成 `(B,B)`，区间退化为二维外积分位数。

| 算例（每场景固定差 10，单一部分方案） | 修复前 | 修复后 |
|---|---|---|
| `g_hat / g_lo / g_hi` | 10.0 / 1.7029 / 18.2971 | 10.0 / 10.0 / 10.0 |

保留并输出的诊断：`best_partial_index`、`n_partial`、`paired=True`、`g_method`。
**限制**：最小值是 winner's curse；`reports/stat_experiment.json` 的 `a_paired_g_interval` 显示
6 个部分方案同真均值时 `g_hat` 平均比固定配对高 0.257（区间宽 0.884），真值覆盖率仅 0.655。
该 0.655 对应**百分位自举**；T14 已把它降级为诊断口径，默认改为配对同时 max-t（见 §11）。
配对 bootstrap 修的是配对，不是选优偏差——不能据此宣称统计有效性。

## 3. R3：置信集合

- `method="max-t"` 现在真的用单步 max-t 同时 p 值：`p_j=(1+#{b:max_k T_bk >= T_j})/(B+1)`，
  比较族为**该单元全部候选设计**（`family_size`）；不再用逐列 bootstrap p 值冒充。
- 零标准误显式处理：与最优列完全相同的列 p=1 且保留；确定被支配的零方差列 p=0 且排除。
- `method="holm"` 保留但标注为 Holm（正态边际 p + 逐步校正），与 max-t 不是同一族。
- 输出新增 `family_size`、`zero_se_count`、`method`。

| 算例（列 3 与列 0 完全相同） | 修复前 | 修复后 |
|---|---|---|
| `included` | [0] | [0, 3] |
| 并列列 p 值 | 0.001996 | 1.0 |

**限制**：这是条件于模拟样本的近似集合，**不是 M03 定理实现**，不继承其集合覆盖保证。
`reports/stat_experiment.json`：真最优覆盖率 1.00、误排率 0.00、平均集合大小 2.28（max-t）/2.10（Holm）；
近并列设置平均集合 5.69（并列必须保留，因此集合变大是正确行为）；明显更差候选（≥6 个标准误）纳入率 0.00。

## 4. R4：调度时钟

删除全局 `clock`。连接开始时刻只取决于：到达时刻、该设备的已排定释放时刻、重叠换位时间；
馈线约束改为在**整个拟充电区间**上校核（`_peak_power_over`），必要时顺延到已排定释放时刻。
没有把"未来另一设备的开始时刻"当作本设备的等待原因。

四请求反例（`overhead, m=2, coverage=2`，两侧车位/设备独立）：

| 请求（到达分钟） | 修复前 `t_c` | 修复后 `t_c` |
|---|---|---|
| #1 (0) | 0 | 0 |
| #2 (0) | 0 | 0 |
| #3 (1，等设备 0) | 96 | 96 |
| #4 (3，设备 1 空闲) | 96（被 #3 的时钟推后） | **3** |

**限制**：仍不是完整事件调度器（不重排已接纳的等待车辆、不预知未来到达、馈线只按已排定承诺校核）。
设备/馈线不超限只是可行性，不保证服务时间安排最优。

## 5. R5：分数尾部 CVaR

`stats.empirical_cvar` 用精确分数尾部权重
`CVaR = (1/w)·(完整尾部和 + w 的小数部分 × 边界值)`，`w=(1-alpha)·n`，
并与 Rockafellar–Uryasev 辅助式 `eta + E[(X-eta)^+/(1-alpha)]` 对照（辅助式只在尾部邻域求最小值，代价线性）。

| 算例（损失 0–23 与 100，alpha=.95，n=25） | 修复前 | 修复后 |
|---|---|---|
| `cvar` | 61.5 | **84.6** |
| `cvar_aux` | 84.6 | 84.6（差 <5e-14） |

补充：整数尾部（n=100, alpha=.95）仍为 98.0；并列 [10]×95+[100]×5 仍为 100；常量样本、alpha=.5 的四点样本均通过。
`reports/stat_experiment.json` 的 `c_cvar`：多组 n/alpha 下 `max|cvar-cvar_aux|=4.3e-14`；
n=50 万正态样本 0.95-CVaR 与解析值 2.0627 的相对差 0.35%（仅大样本 sanity check，不是证明）。

## 6. R6：持续 ETP 搜索

`stats.etp_from_g` 改为：取**最后一个非负/缺失点之后**的网格点，即从最晚一次"不便宜"起算的持续负后缀；
`g_hat==0` 不算便宜、NaN 不算便宜、重复 r 报错、输入自动排序。

| 符号 −,+,−,−（r=.2,.4,.6,.8） | 修复前 | 修复后 |
|---|---|---|
| 返回 | None | **0.6** |

`reports/stat_experiment.json` 的 `d_etp_grid`：4 点网格的全部 81 种符号组合与暴力后缀定义逐一比对，0 处不一致。
**限制**：只声称离散网格结果；不外推连续单调性，也不因 r=1.0 为正就否定更早的持续区间。

## 7. R7：场地参数、候选集与能量分母

- **场地标签**：新增 `evaluate.v2_lot_arrival_scale`，用静态层的 manuscript 口径
  （pnc 空置率 0.37、plc 到达/容量比 1.05）缩放 v2 小时到达强度 → pnc 0.6、plc 1.0。
  这样 pnc/plc 不再只差随机种子。**仍为假设**：原稿没有给出分场地小时曲线，停留/能量表两场地共用。
  配置 `v2.lot_arrival_calibration: static_layer_ratio`，置 `seed_only` 可恢复旧行为。
- **候选集**：`v2.include_m0: true`，候选集加入 m=0（固定式、无充电桩）方案，式 (12) 的 m0 有了真正的
  零桩参考；候选仍是配置声明的分数网格（0, 0.2, …, 1.0 × N），不是全部整数 m。
- **比较范围**：`g(r)`/ETP/置信集仍只在 fixed 模式候选内计算（`candidate_scope=fixed_mode_only`，
  输出 `candidate_count`），移动充电（overhead）只在 `v2_designs.csv`/`v2_best.csv` 中单独报告。
- **能量分母**：`energy_requested_admitted_kwh`（已接纳）与 `energy_requested_all_kwh`（全部请求）分开，
  新增 `rejected_ev_charge`、`rejected_energy_kwh`、`unserved_energy_kwh`、`unserved_rate_all`；
  `shortfall_kwh/shortfall_rate` 明确为"已接纳车辆的缺口"。恒等式
  `unserved = shortfall + rejected_energy` 在回归测试中断言。

## 7b. 额外发现并修复：manifest / config 哈希口径

原 `run_all.py` 用 `io.content_hash(path)` 记录 `manifest.json` 的文件哈希与
`config_sha256`——它哈希的是"路径字符串"的规范 JSON，不是文件字节，所以每个文件的
`sha256` 随本次运行目录名（含时间戳）变化，无法用于核对产物。新增 `io.file_sha256`
按字节计算，`run_all.py` 两处改用它；回归测试 `test_file_sha256_is_content_hash` 覆盖。
修复后两次运行 `manifest.json` 除 `params.json`/`summary.json`（内嵌时间戳）的哈希外一致。

## 8. 复跑

    python -m unittest discover -s tests -v
    python run_all.py --mode all --seed 42 --out outputs_revision --no-canonical
    python tools/stat_experiment.py --out reports/stat_experiment.json

实测（2026-10-29 本副本）：默认 Python 3.12.3 / numpy 1.26.4 下 `Ran 73 tests ... OK`，
工作区捆绑 Python 3.12.14 / numpy 2.3.5 下同样 73 条 OK；基线 `--mode all --seed 42` 用时 242.2 s。
两次独立重算：23/23 个 CSV 逐字节一致，`params/summary/etp_points` 剔除时间戳后一致。
解释器、依赖版本、耗时、种子、命令、文件哈希写入 `reports/backend_fix_evidence.json`；
剔除 `timestamp/run_id/runtime_seconds/timings` 后的确定性比较见该文件 `determinism` 段。

## 9. 剩余风险

1. 原稿参数（补充材料、MATLAB 程序）仍缺失：所有 `source=assumption` 的参数没有实测依据，
   本轮只核对口径、不调参追近原文数字；**实现修好不等于原稿数值复现**。
2. 统计层是条件于模拟样本的近似：max-t/Holm 与 g 的区间都不继承 M03 定理；选优偏差已量化但未消除。
3. 调度器仍是"到达即定车位、按已排定承诺排队"，不重排、不预知；馈线只在已排定会话上校核。
4. 分场地校准只调到达强度，停留/能量/成本结构仍两场地共用；q 仍固定扫描，不是估计量。
5. 损失函数仍只对"已接纳缺口"计价，被拒请求只作为分母/指标分报，未进入成本——这会低估拒绝的代价，
   属于模型口径限制，本轮未改（改动会改变所有成本的比较基准）。

## 10. 重算结果概览（与修复前 canonical 对照）

| 项 | 修复前 canonical | 本副本重算 |
|---|---|---|
| v2 统计格数 | 44 | 36（g 不再变号，无加密点） |
| 三区标签 | full_dominant 4 / partial_dominant 27 / undetermined 13 | partial_dominant 36 |
| v2 g 为负的格数 | 11 | 0 |
| v2 g 范围（RMB） | −873,272 … 4,243,399 | 4,794,233 … 4,800,000 |
| 置信集大小 | 1–3 | 1–2 |
| 服务台账行数 | 704 | 648（含 m=0 设计，行数随候选与 r 加密变化） |
| 能量分母列 | 仅已接纳 | 已接纳 / 全部请求 / 拒绝分列 |
| 静态层 ETP | plc/beta 0.2、plc/binomial 1.0 | 不变（静态层未改） |

**读数**：修复前 r≈0.72–0.9 的 full_dominant 窗口随单位修复消失，说明该窗口来自"小时+分钟"混用造成的
虚假拥堵，而不是需求—容量关系。v2 的 ETP 仍为 null，但理由从"首次变负后回正"变成"全网格 g>0、无持续负后缀"。
这些是**自建模型的实现结果**，不是原稿数值的复现，也不能据此回填正文。

## 11. T14：F01 调度边界/移动时间、F09 g 区间覆盖

依据 [下级 Agent 交付复验](../../../docs/reports/2026-10-29-下级Agent交付复验.md) 的 F01、F09 两项。
改动前 7 个源文件已备份并记账 SHA-256：`../../../tmp/t14_backend_20261029/backup_manifest.json`
（备份体在 `src_backup/`）；原 `research/electrification/repro/`、历史输出、`docs/reports/` 与两份 Word 未动。
回归断言先写后改：同一套新测试在备份源码上 `FAILED (failures=5, errors=4)`，修复后全绿
（`tmp/t14_backend_20261029/before_f01_f09_failing.log` 与 `tests_after_f01_f09.log`）。

### 11.1 F01a：半开区间与同刻事件顺序

复验反例成立：`[0,10)`、`[10,20)` 两条 50 kW 会话加一条 `[0,20)` 的 50 kW 请求，真实峰值 100 kW，
旧 `_peak_power_over` 按 `(时刻, -功率)` 排序，同一时刻**先加后减**，算成 150 kW，并把本可在 0 开始的
请求推迟到 10。现按 `(时刻, ±功率)` 排序（同一时刻先处理结束），峰值 100 kW，跨越请求 `t_c=0`、
充电 48 min。回归：`TestF01HalfOpenIntervals`（含逆序会话，防"输入顺序偶然正确"）。

### 11.2 F01b：移动时间不得用到达前的空等抵扣

旧逻辑把 `t_ready = device_free(设备释放)` 再加移动耗时，再与到达取大；设备早释、车辆晚到时会**少付**
移动时间（复验反例：设备 0.96 min 释放、车辆 100 min 到达，旧解从 100 开始，应为 110）。
现在显式区分：`t_move_start = max(t_a, device_free[best])`（目标车位到达后才确定），
`t_move_end = t_move_start + reposition_min`，`t_c >= t_move_end` 且满足馈线余量。
时间线新增 `t_move_start`/`t_move_end`；设备初始位置成为显式假设
`configs/v2.yaml: v2.device_initial_position = home_berth`（设备 d 初始停在自己车位，换位才计移动；
`depot` 复现旧行为），并写入 `metrics["device_initial_position"]` 以便追溯。
回归：`TestF01RepositionTiming`（移动发生/不发生两种情形）。

### 11.3 F09：g 区间改为配对同时 max-t

定义不变：`g = V(full) − min_k V(partial_k) = max_k E[d_k]`，`d_k` 为同一模拟日上的配对差。
旧的"重采样后对 K 个候选取 min"的百分位区间**不是**覆盖区间：选择偏差抬高点估计，区间宽度不随 K 增大，
近并列/精确并列时覆盖不足。现默认方法：

1. 每个对比学生化 `T_k = (d̄_k − μ_k)/se_k`，同一次自举（同一日索引）给出
   `c = q_{1−α}(max_k |T*_k|)`；
2. 同时界 `L_k = d̄_k − c·se_k`、`U_k = d̄_k + c·se_k`；
3. 按 max 传播 `g ∈ [max_k L_k, max_k U_k]`。由于 `g = max_k μ_k`，
   "所有 μ_k 同时落入各自区间"蕴含两个方向，故覆盖 ≥ 1−α，且不含选优声明。
零方差列（`se_k=0`）取 `L_k=U_k=d̄_k` 精确；K=1 时退化为普通两侧 t 区间。

**固定种子覆盖实验**（设计在看数之前固定：400 组，种子 `20261101+i`，S=120，n_boot=500，α=0.05，
`tmp/t14_backend_20261029/f09_coverage_study.py` → `f09_coverage.json`）：

| 场景 | K | 同时 max-t 覆盖（±MC 标准误） | 均值宽度 | 百分位诊断覆盖 |
|---|---|---|---|---|
| 单候选 | 1 | 0.943 ± 0.012 | 1.41 | — |
| 精确并列 | 6 | 0.958 ± 0.010 | 1.32 | 0.720 |
| 近并列（δ≤0.4） | 6 | 0.985 ± 0.006 | 1.32 | 0.828 |
| 相关部分方案（共享因子） | 6 | 0.990 ± 0.005 | 1.96 | 0.662 |
| 日间 AR(1) + block_len=8 | 6 | 0.825 ± 0.019（**不作名义声称**） | 5.67 | 0.785 |

复验的 65% 反例被原样复现（精确并列下百分位 0.720，项目自带 `a_paired_g_interval` 为 0.655），
同时区间把它修到名义水平；`reports/stat_experiment.json` 已按新方法重生成（含两种口径对照）。

**适用条件（本轮据此限定声称范围）**：配对/CRN 场景；场景需独立（`block_len=1`）才声称名义覆盖，
`block_len>1` 时学生化仍按 iid 标准误，只有近似，故 AR(1) 场景只报数不声称；候选集事前确定；
覆盖是渐近的（自举校准 max-t），有限样本由上面的固定种子实验检验，不是定理；不继承 M03 定理，
也不对 argmin 方案作集合覆盖声明。

### 11.4 g 的结构：主导窗口 vs 持续负后缀 vs 规则是否同时改变

新增 `stats.g_structure` 与输出表 `v2_g_structure.csv`：在每个 (lot, ev_mode) 网格上区分
`full_dominant_windows`（连续 `g_hi<0`）、`partial_dominant_windows`（连续 `g_lo>0`）、
`negative_islands`（`g_hat<0` 但不属于持续后缀的孤立区段）与 `etp_sustained_suffix`
（该 r 起及之后全部 `g_hat<0`，严格小于 0，NaN 不算更便宜）。窗口按离散网格给出，不插值。
`v2_g_curve.csv` 新增 `full_rule/best_partial_rule/rule_changed_vs_full/partial_rule_count/
n_partial_rule_fixed/g_hat_rule_fixed/g_lo_rule_fixed/g_hi_rule_fixed`：最优部分方案若换了准入规则，
`g` 同时含容量与规则两种效应；`g_*_rule_fixed` 在固定全安装规则的部分候选中重算，用于隔离容量效应。

### 11.5 重算与读数（`--mode all --seed 42`，运行目录 `outputs_revision/t14_run1|t14_run2`）

- `Ran 83 tests ... OK`（73 + T14 新增 10），默认 Python 与工作区捆绑 Python 均通过（`tests_after_f01_f09.log`、`tests_after_f01_f09_bundled.log`）。
- 两次独立重算：`--mode all` 分别 241.68 s / 241.91 s，24 个 CSV 逐字节一致（见 evidence `determinism`）。
- v2 统计格 36 个，区间全部 `simultaneous-max-t`；三区标签 36/36 `partial_dominant`，与修复前基线相比
  **无标签翻转**；平均区间宽度 578.2 → 1122.9 RMB（同时区间更宽，这是应有的代价，未做调参压缩）。
- 36/36 格的最优部分方案都换了准入规则（`best_partial_rule=pi_S`）；固定规则后
  `g_hat_rule_fixed` 仍全为正（4.59×10^6 … 4.80×10^6），说明容量效应本身存在，不依赖规则变化。
- 结构表：各网格 `etp_sustained_suffix` 为空、无 `negative_islands`、无 `full_dominant_windows`，
  `partial_dominant_windows` 覆盖 0.20–1.00；即"全网格部分占优"，ETP 仍为 null，理由是**没有可持续负后缀**。

**限制**：F01 的初始位置假设（home_berth）是建模假设，不是实测；移动时间只在"已知目标车位"后有定义，
若未来允许预知/预约换位需另建模。F09 的覆盖保证仅限 11.3 列出的适用条件；同时区间在并列时偏保守，
换更窄的方法需要有覆盖证明，本轮不做。synthetic 实验能验证实现性质，不能验证真实数据的真值。

`python -m unittest discover -s tests -v`（T14 时 83 OK，T12 后 84 OK）；重算命令同上 §8，输出另存
`outputs_revision/t14_run1`、`outputs_revision/t14_run2`；机器证据 `tmp/t14_backend_20261029/t14_evidence.json`。

## 12. T12：q 分母、M06/M07 与规则/g 口径（2026-10-29）

只增指标口径与输出字段，不改需求、调度、成本或随机流。

- **q 分母**：配置的 q 是 P(充电请求 / EV 到达)，不是 q_need，也不是 q_plug。新增
  `ev_arrivals`、`ev_charge_requests`、`q_request_realized`、`q_plug_realized`，q 的分母明确为
  EV 到达，不把 q 写成全体到达的比例。重算样例：q_request≈0.597（设定 .6），q_plug≈0.582–0.587。
- **M06/M07**：`shortfall_rate` 是 M06（已接纳缺口/已接纳需求）；新增 `refused_rate_all` 是
  M07（拒绝需求/全部请求能量）；原 `unserved_rate_all` 是两者合并，不能当 M07。聚合口径另给
  `shortfall_rate_aggregate`、`unserved_rate_all_aggregate`，避免“日比值再平均”的加权偏差。
- **规则**：π_S≈R1、π_F≈R2、π_θ≈R4（A 全天保护，D 高峰窗保护），A 无 R3 对应；跨库只报
  规则族差异，不把 π 与 R 的效应相加。
- **g 范围**：主结果保留“政策包 g”（部分方案可换规则）；`g_hat_rule_fixed` 固定 π_F，只解释
  容量效应。T12 重算 36 格：g=4,794,233–4,800,000，全正；固定规则 g=4,568,579–4,800,000；
  规则效应 0–231,421 RMB（0–4.82%）；两种口径都无持续负后缀，v2 ETP 全 null。
- **拒绝能量成本**：基线仍只罚已接纳缺口，不静默补价；c_ref=3 元/kWh 的敏感性使政策包 g 最大
  变化 0.78 RMB/日（1.6e−7），固定规则 g 最大 44.28 RMB/日（9.7e−6），不改变符号。

新增回归 `test_t12_q_denominator_and_m07_split`：一个已接纳但电量不足、三个被拒的日例，断言
q 分母、M06/M07 分离且合并率不等于 M07。`Ran 84 tests ... OK`；`--mode all --seed 42` 用时
183.03 s，v2 36 格/648 设计，ETP 全 null，g 与三区标签未翻转。

## 13. T14 第二轮：区间元数据、下游口径、非有限值与失败移动记录（2026-10-29）

依据复验报告 §6 的四项剩余问题。改动前 7 个文件备份并记账 SHA-256：
`tmp/t14_backend_20261029/r2/backup_manifest.json`（备份体在 `r2/src_backup/`）；
原后端、历史输出、论文与 Word 未动。新增 12 条回归先红后绿：在备份源码上
`FAILED (failures=3, errors=9)`（`r2/before_f01c_f09b_failing.log`），修复后
`Ran 96 tests ... OK`（`tests_after_f01c_f09b.log`）。

### 13.1 区间元数据按适用条件给出（F09）

`stats.g_interval` 机器标记不再与方法名绑定：新增 `independent_scenarios`（默认由
`block_len==1` 推断）与统一元数据构造函数，返回 `nominal_coverage`、
`diagnostic_only`、`coverage_scope`、`interval_scope="per_r_pointwise"`、
`joint_across_r=False`。`block_len=8` 时 `nominal_coverage=False` 且
`coverage_scope` 明写"iid 学生化不成立，不得引用为 95% 区间"；显式传
`independent_scenarios=False` 可覆盖默认。百分位口径保持诊断。第一轮覆盖实验的条件结论不变
（独立场景名义覆盖达标；AR(1)+block8 经验覆盖 0.825，只作诊断）。

### 13.2 下游传递不得把诊断区间解释为名义水平（F09）

`evaluate.v2_cell_stats` 的 `g`/`regions` 行新增 `g_diagnostic_only`、
`g_interval_scope`、`g_joint_across_r`、`region_confidence`（nominal/diagnostic）、
`region_scope`；`v2_g_structure` 增补 `interval_scope`、`joint_across_r`、
`rows_nominal/rows_diagnostic/all_rows_nominal`、`suffix_basis`、
`full_dominant_basis`、`partial_dominant_basis`、`n_non_finite`、
`n_inconsistent_sign_rows`。`run_all.py` 摘要写入 `v2_interval_scope` 并加一条
notes 说明，服务表带移动计数。**口径边界写死**：g 区间是逐 r 点式区间；三区标签、占优窗口、
ETP 都沿用点式口径，不构成跨 r 联合保证（本轮不做跨 r 多重性校正）；`block_len>1` 的行
`region_confidence` 为 diagnostic。本轮 36 格均为 `block_len=1`，故
`region_confidence=nominal`、`all_rows_nominal=True`。

### 13.3 g_structure 不把缺失/非有限值当负值

旧实现对 `g_hat=NaN` 用 `not (NaN >= 0)` 判负，NaN 被并入负岛（复验反例：
`[[0.2,0.8]]`）。现所有窗口/孤岛/后缀判定都先过 `_finite_number`：非有限值不参与
任何"负/正"判定、会打断连续区段，也**不能把后缀向左延伸**（缺失点不是"仍为负"的证据）；
后缀只含有限行。第二轮独立反例进一步发现：若一行 `g_hat` 非有限但 `g_lo/g_hi` 有限，
旧实现仍会把该行算进占优窗口；现已要求三个字段同时有限，整行缺失不产生任何窗口/孤岛。

新增 `n_non_finite/non_finite_r` 与 `n_inconsistent_sign_rows`
（`g_hi<0` 但 `g_hat` 不为负等符号不一致）以便下游自检。后缀语义与
`etp_from_g` 的 NaN 约定一致：缺失≈NaN≈"不更便宜"，会打断后缀。

### 13.4 失败请求的移动记录必须区分执行/取消（F01 边界）

旧实现在调度失败（车辆在可连接前离场）时仍把试探移动写进时间线：复验场景中失败请求留下
10–20 的移动，后续请求又从 13 起算移动（同一设备区间重叠、且设备位置被错误承诺）。
现在：试探移动只在真正开始服务时执行；失败则记 `t_move_status="cancelled"`、清空
`t_move_start/t_move_end`、不改 `device_free/device_last_berth`，仅计入取消数。
时间线新增 `t_move_status`（none/executed/cancelled/blocked/no_device）与
`t_move_device`；`capacity.ServiceLedger` 新增 `record_move`、`device_moves`
与 `device_move_conflicts`，`assert_invariants` 现在会拒绝同一设备的移动/供能区间重叠
（含 `t_c ≥ t_move_end` 的边界），回归 `test_same_device_moves_and_sessions_do_not_overlap`。
修复后同一反例：失败请求 `cancelled` 且无移动区间，后续请求移动 13–23、供电自 23 起，
`device_move_conflicts=0`。指标新增 `device_moves_executed/cancelled/planned/conflicts`。

### 13.5 测试与小规模重算

- `Ran 97 tests ... OK`（84 + 第一轮 12 + 混合缺失行 1），默认 Python；新增类 `TestF09bIntervalMetadata`、
  `TestF09bDownstreamScope`、`TestF09bStructureNonFinite`、`TestF01cFailedRequestMove`。
- `--mode v2 --seed 42` 两次（`outputs_revision/t14b_run1|t14b_run2`）：12/12 个 CSV 逐字节一致；
  36 格标签与第一轮**完全一致**（`g_hat/g_lo/region` 36/36 相同，服务能量、峰值相同），
  新增列只有区间元数据；说明本轮只改元数据与失败移动记录，成功服务路径未变。
- 服务表：每格日均 `device_moves_executed≈11.14`、`device_moves_cancelled≈0.22`、
  `device_move_conflicts=0`；时间线样本 61 行含 `t_move_status` 列且无 cancelled 残留区间。
- `python scripts/check_all.py`（工作区捆绑 Python）：exit 0，0 错误、8 条警告（均为未触碰历史文档）。

### 13.6 限制

跨 r 联合覆盖**未建立**：本轮只把口径标注清楚，没有实现跨 r 多重性校正，因此三区/窗口/ETP 不能
当作联合置信陈述；`block_len>1` 或相关场景只有诊断区间（名义标志已被机器拒绝）。取消的移动
按"未执行、设备留在原位"处理，不建模"已出发半途取消"的物理状态；若将来允许预约/预知换位需另建模型。
覆盖实验只支持独立场景下的经验结论，不是有限样本定理。

机器证据：`tmp/t14_backend_20261029/r2/t14b_evidence.json`（备份、红绿测试、元数据、
移动记录、两次重算确定性、check_all）；第一轮覆盖实验在
`tmp/t14_backend_20261029/f09_coverage.json`。

