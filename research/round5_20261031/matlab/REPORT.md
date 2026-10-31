# 第五轮 MATLAB R2026a 独立验证报告

- 任务：共享任务 task-1（MATLAB R2026a 独立验证：静态 PREI 对齐 + 固定轨迹独立核对）
- 执行者：teammate matlab；日期：2026-10-31（本地时间，日志首行为准）
- 写入范围：仅 research/round5_20261031/matlab/**。未改 matlab/prei、experiments/prei、apps、research 既有文件，未碰 research/collection（采集器运行中），未改 Word。
- 结论先说：
  1. **A 静态 PREI 对齐通过**：MATLAB 原样运行 run_prei（legacy 与 corrected 两套固定配置/fixture），与 Python 参考 experiments/prei/runs/run2_v1_* 的配置/输入哈希、441×18 成本矩阵、拒绝量、并列最优集合、ETP、manifest 口径全部一致；最大绝对差 4.547e-12 RMB/day，最大相对差 2.133e-12。prei_self_test 在 MATLAB 下也通过。
  2. **B 固定轨迹独立验证通过**：自写 CSV 与自写 MATLAB 公式实现，对设施成本 k=0/1/2×半日/整日、14 kWh/7 kW/60 min 交付与缺口、Erlang-B（含零负荷）、服务约束小表与整数搜索、A/B/D 三条规则确定性轨迹的占位/释放/拒绝/服务指标，共 145 项检查全部在给定容差内通过。
  3. **边界**：A 只说明“静态口径对齐”，**不等于冻结原稿复现**，也**不等于当前事件仿真已验证**；B 只验证源码契约级公式与三条准入规则的小轨迹，未运行 apps/parking_lab 的 Simulation 类，也未重跑 Python 参考。详见第 4 节。

## 1 环境、许可与命令

C:/Program Files/MATLAB/R2026a/bin/matlab.exe 批处理运行，未安装任何东西、无交互。

| 项 | 实测值 | 证据 |
|---|---|---|
| version | 26.1.0.3203278 (R2026a) | logs/version_check.log 第 1 行；logs/static_verify.log |
| matlabRelease.Release | R2026a | 同上 |
| license('test','MATLAB') | 1（通过） | logs/version_check.log |
| 已装产品 | 111 个（ver 全量），含 MATLAB 26.1、Optimization/Statistics 等 | logs/version_check.log、logs/static_verify.log |
| 依赖工具箱 | 验证代码只用 base MATLAB + Java（SHA-256 MessageDigest，prei_hash_text 原有实现），无额外工具箱依赖 | scripts/*.m |

版本差异记录：任务说明写的是 26.1.0.3089807，实际 version() 返回 26.1.0.3203278。以实测为准；未做静默替换，原样记录。

命令全文（三条均以 EXITCODE= 行把 $LASTEXITCODE 追加到对应日志）：

1) 版本/许可探测（logs/version_check.log，EXITCODE=0）

    $log='C:/Projects/停车场充电桩优化方案/research/round5_20261031/matlab/logs/version_check.log'
    $m='C:/Program Files/MATLAB/R2026a/bin/matlab.exe'
    & $m -batch "disp(version); fprintf('RELEASE=%s\n', matlabRelease.Release); fprintf('LICENSE_MATLAB=%d\n', license('test','MATLAB')); v=ver; for i=1:numel(v), fprintf('PRODUCT|%s|%s\n', v(i).Name, v(i).Version); end" *> $log
    "EXITCODE=$LASTEXITCODE" | Out-File -Append -Encoding utf8 $log

2) A 组静态对齐（logs/static_verify_console.log，EXITCODE=0；diary 日志 logs/static_verify.log）

    & 'C:/Program Files/MATLAB/R2026a/bin/matlab.exe' -batch "addpath('C:/Projects/停车场充电桩优化方案/research/round5_20261031/matlab/scripts'); static_verify" *> 'C:/Projects/停车场充电桩优化方案/research/round5_20261031/matlab/logs/static_verify_console.log'
    "EXITCODE=$LASTEXITCODE" | Out-File -Append -Encoding utf8 '.../logs/static_verify_console.log'

3) B 组独立核对（logs/indep_verify_console.log，EXITCODE=0；diary 日志 logs/indep_verify.log）

    & 'C:/Program Files/MATLAB/R2026a/bin/matlab.exe' -batch "addpath('C:/Projects/停车场充电桩优化方案/research/round5_20261031/matlab/scripts'); indep_verify" *> 'C:/Projects/停车场充电桩优化方案/research/round5_20261031/matlab/logs/indep_verify_console.log'
    "EXITCODE=$LASTEXITCODE" | Out-File -Append -Encoding utf8 '.../logs/indep_verify_console.log'

两脚本可重跑：static_verify 会先清空 static_run/legacy|corrected 内的既有文件再调用 run_prei（run_prei 本身拒绝非空目录）；indep_verify 重写 indep/out/。日志用 UTF-8 保存；MATLAB 控制台把中文工程路径显示为乱码（系统代码页），文件内路径与写入均正常，不影响结果。

## 2 A 组：静态 PREI 对齐（legacy 与 corrected）

### 2.1 输入、参考与哈希

| 项 | legacy | corrected |
|---|---|---|
| 配置 | experiments/prei/configs/final_tvr_n40_legacy.json | ..._corrected.json |
| 配置 SHA-256（实测原始字节） | 73cbc094…68a9e4c | de4b5db2…f65ad94 |
| Python 参考记录 | 同值，匹配 | 同值，匹配 |
| fixture | experiments/prei/fixtures/deterministic_24h/fixture.csv | 同一文件 |
| fixture SHA-256 | 9cd87ec5…d0b2b4ad，与参考记录一致 | 同左 |
| 参考运行 | experiments/prei/runs/run2_v1_legacy | run2_v1_corrected |

- run2_v1_* 与 ref_v1_* 的 raw_cost_matrix.csv/daily_optimal.csv 逐字节相同（PowerShell Get-FileHash 比对，已在计划阶段记录）；本次用 run2_v1_*。
- 输出目录均为全新：static_run/legacy/、static_run/corrected/；各 12 个文件（含 manifest.csv）。
- 数据形态：21 个 scenario-day（scenario_id 均为 final_tvr_det，target 0…1），21 个 pile_ratio，共 441 行 × 18 列。

### 2.2 逐项比对结果（static_run/comparison_summary.json）

| 检查项 | legacy | corrected |
|---|---|---|
| 行/列对齐 | 441/441 行、18/18 列，键唯一且一一对应 | 同左 |
| 配置/输入哈希 | 匹配 | 匹配 |
| config_used.json 与源配置逐字节相同 | 是 | 是 |
| 成本矩阵全部数值列最大绝对差 | 4.547e-12 RMB/day | 4.547e-12 RMB/day |
| 成本矩阵最大相对差 | 2.133e-12（delta_candidate_minus_full） | 3.057e-14 |
| 拒绝量（ev/ice refused） | 441 行交叉核对 0 差异 | 同左 |
| 并列最优 | 两方案各 21 个最优单元（每天 1 个），is_optimal 位 0 差异；best_candidates.csv 集合与 Python 完全一致 | 同左 |
| Python daily_optimal.csv | 21 行，内容与“该天并列最优中最小 pile_ratio 行”的 8 个 fixture 列逐项一致 | 同左 |
| ETP | 窗口 1 个（索引 21..21，target 1），has_etp=true，ETP=1.0；与从 Python 矩阵复算结果一致 | 同左 |
| manifest | 11 个文件，按 MATLAB 声明口径（prei_hash_text(fileread)）复核 0 失配 | 同左 |
| 判定阈值 | abs ≤ 1e-6 且 rel ≤ 1e-9，全部通过 | 同左 |

补充事实：两套配置下每天的并列最优唯一，最优 pile_ratio 恰等于该天 ev_share_target（0, 0.05, …, 1）。ETP 为后缀准则下的 1.0（全装机只在 target=1.0 处进入最优集且其后无 target），不是对 0.70 的特判。

### 2.3 差异定位

- 所有数值差 ≤ 4.6e-12 RMB/day，来自求和/乘法顺序不同（MATLAB 对逐时拒绝量先按天 sum 后乘费率；Python 逐时累加拒绝量再乘费率），不是模型口径差异；量级在双精度舍入范围内，远低于 1e-6 相对/1e-9 相对阈值。
- 逐列最大差见 static_run/legacy_diff_by_column.csv 与 static_run/corrected_diff_by_column.csv（含最差单元的 day|target|ratio 键）。

### 2.4 legacy 与 corrected 的差（MATLAB 输出之间）

- 主成本列共 40 个单元不同：ev_complaint_cost 与 total_daily_cost 各 20 个，**全部位于 pile_ratio=1**；最大差 46.2 RMB/day。
  机制与源码一致：legacy_reference 在 r=1 的全装机分支省略 EV 投诉成本（experiments/prei/reference.py 的 legacy 分支、matlab/prei/src/cost/prei_cost.m 同规则）；corrected 计入。
- 派生列 820 个单元随之不同（g_full_minus_best_partial 每天 21 行、delta_candidate_minus_full 的 partial 行），属定义使然。
- 21 天的最优/并列集合两方案完全相同（days_with_different_ties=0）：省略 46.2 RMB/day 未改变最优候选。

### 2.5 A 组发现（证据标签与哈希口径，不影响数值）

1. run_metadata.json/summary.json 中的 actual_tested_platforms 固定写为 octave、matlab_tested=false、note 写“MATLAB was not run”，即使本次是在 MATLAB R2026a 下运行。这是 run_prei.m/prei_summarize.m 的硬编码遗留（原为 Octave 交付），**不能把这两个字段当作平台证据**；本次平台证据用 logs/*.log 的 version()/license 行。
2. manifest 的 sha256 由 prei_hash_text(fileread(file))（UTF-16 char 的 uint8）计算，不是原始 UTF-8 字节哈希。summary.json 与 run_metadata.json 含非 ASCII 文本（环境用户/计算机字段与中文工程路径），因此其 manifest 值与原始字节 SHA-256 不同（11 个文件中 2 个）；配置文件与 fixture 为纯 ASCII，故与 Python 的字节哈希一致。本次把“manifest 自洽”和“与原始字节一致”分开记录，未混为一谈。
3. prei_self_test 打印 “Octave only”，但在 MATLAB R2026a 下执行并通过（logs/static_verify.log）。

### 2.6 A 组不证明什么

- 不证明冻结原稿（main_paper/ 或旧稿）可复现：legacy_reference 按参考文档是 diagnostic-only，且不是原始随机流的重跑（reference.py 文档串明示）。
- 不证明当前事件仿真、随机抽样、服务指标或策略结论成立：静态口径只覆盖固定 fixture 下的逐日成本枚举。
- 只覆盖本次两套配置（n_spaces=40、h=0、full_install_open_to_all=true）。partial_shared_fraction>0 的共享分支与 closed-full 分支、v2_n10786 配置/fixture 未在本次运行。

## 3 B 组：固定轨迹独立验证

### 3.1 方法与公式来源

- 输入全部自写：indep/inputs/*.csv（设施成本 8 例、能量 4 车×2 效率、Erlang 9 例、最小连接器 4 例、服务搜索 6 情景、整数推荐 4 情景、A/B/D 轨迹 6 车 + 8 条分配期望）。
- 期望值全部手算后写入 *_expected*.csv；**没有读取任何 Python 汇总结果作为输入**，脚本也不 import 任何 Python 产物。
- 公式按源码契约在 scripts/indep_verify.m 独立重写（不是调用源码）：
  - apps/parking_lab/workbench/costs.py：facility_cost（设备资本 k×日折旧×days、维护 k×maintenance×days、站级固定 fixed×days；k=0 时资本/维护为 0 且列 not_applicable）
  - apps/parking_lab/workbench/traffic_gen.py：demand_ledger（需求/必需时间/可交付/缺口/窗口右删失 pending）
  - apps/parking_lab/workbench/allocation.py：erlang_b 递推、闭式对照、min_servers_for_blocking、service_level_k 状态机、integer_recommendation
  - apps/parking_lab/workbench/rules.py：π0 dedicated_by_type（A）、π1 full_open_ice_first（B）、π2 predictive_shared_ice_first（D，charge_arrivals 预测、window=30、margin=1）
  - apps/parking_lab/workbench/service_metrics.py：summarise（外生分母、期初车辆排除、pending 只计窗口内已入园会话）
- 容差：金额 abs 1e-4 / rel 1e-6；概率 abs 1e-12；能量 abs 1e-9 / rel 1e-12；计数与状态精确。**145/145 通过**（indep/out/indep_checks.csv、indep/out/indep_summary.json）。

### 3.2 六项逐项结果

**(1) 设施成本 k=0/1/2 × 半日/整日**（TWD；capex 分支 36500/10/365=10/日·位，维护 5，站级 12）

| 用例 | 期望 | MATLAB | 结果 |
|---|---:|---:|---|
| k=0, 0.5 日 / 1 日 | 6 / 12 | 6 / 12 | 通过 |
| k=1, 0.5 日 / 1 日 | 13.5 / 27 | 13.5 / 27 | 通过 |
| k=2, 0.5 日 / 1 日 | 21 / 42 | 21 / 42 | 通过 |
| k=1, 1 日（annual=1000/年） | 19.73972602739726 | 同值 | 通过 |
| k=2, 1 日（annual） | 27.47945205479452 | 同值 | 通过 |

k=0 时设备资本与维护均为 0、站级固定成本照计（12 / 6），单独 4 项检查通过。

**(2) 14 kWh 需求、7 kW、60 min**

| 指标 | 期望 | MATLAB |
|---|---:|---:|
| 必需时间 | 120 min | 120 |
| 可交付（60 min 停留） | 7 kWh | 7 |
| 离场缺口 | 7 kWh | 7 |
| 窗口右删失（第 2 车：t=100，60 min，窗口 120） | censored=1，pending=11.6666666666667 kWh，缺口 0 | 同值 |
| 4 车合计 | 需求 38、必需 325.714285714286 min、可交付 19.3333333333333 kWh、缺口 7、pending 11.6666666666667、充电 3、删失 2、缺口会话 1 | 同值 |
| 效率 0.9 | 第 1 车可交付 6.3、缺口 7.7、必需 133.333333333333 min，合计可交付 18.4 | 同值 |

**(3) Erlang-B（含零负荷）**

| a=2, k | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|
| B（递推，期望=实际） | 0.666666666666667 | 0.4 | 0.210526315789474 | 0.0952380952380952 | 0.0366972477064220 | 0.0120845921450151 |

- a=0, k=1/3/6 均为 0；闭式（log 空间）与递推 9 例差 0，全部 ≤ 1e-12。
- min_servers_for_blocking：零负荷 → 0（不是 1）；a=2、target=0.05 → 5；target=0.5 → 2；k≤3 内达不到 0.001 → None。

**(4) 小表服务约束与整数搜索**

服务指标表 U(k)=[10,8,4,2,0]（k=0…4），手算基准：

| 情景 | 期望状态/推荐 | MATLAB |
|---|---|---|
| alpha=0.5 | achieved，k=2（阈值 5） | 同 |
| alpha=0.5, search_max=2 | achieved，k=2，boundary=1 | 同 |
| alpha=0.1, search_max=3 | infeasible_upper_bound，k=None | 同 |
| alpha=0.1，缺 k=3 行 | missing_data，k=None | 同 |
| U(0)=0 | no_demand，k=0 | 同 |
| alpha=0.1, budget_max=2 | budget_exhausted，evaluated_max=2 | 同 |

整数推荐：[3,4,5]→median 4、q90 5、k=4、ok；[3,4,5,6]→median 4.5、q90 6、k=5、statistical_summary_not_installable；含 None→lower_bound、k=None；空→missing_data。

**(5)(6) A/B/D 确定性轨迹、期初/同刻/窗口末**

自写轨迹（indep/inputs/trajectory.csv）：3 车位（1 个带枪位 bay0、2 个普通位）、7 kW、窗口 120 min；6 车：

| 车 | 时刻 | 停留 | 类型/充电 | 能量 | 备注 |
|---|---:|---:|---|---:|---|
| 1 | 0 | 120 | ICE | 0 | 期初 |
| 2 | 0 | 120 | ICE | 0 | 期初（与 1、3 同刻） |
| 3 | 0 | 20 | EV 充电 | 7 | 同刻事件 |
| 4 | 25 | 30 | ICE | 0 | 普通位满时到达 |
| 5 | 30 | 30 | EV 充电 | 14 | 带枪位被占时到达 |
| 6 | 100 | 60 | EV 充电 | 14 | 窗口末 pending |

事件顺序假设：按 (time_min, vehicle_id) 排序；在到达时刻 t 先释放 departure_min ≤ t 的已入园车辆，再处理 t 时刻到达；departure_min > horizon 记为右删失，只有已入园且需充电的删失会话计 pending。

| 指标 | A（π0） | B（π1） | D（π2） |
|---|---:|---:|---:|
| 拒绝数 | 1（车 4） | 1（车 5） | 1（车 4） |
| 峰值占位 | 3 | 3 | 3 |
| 窗口内释放数 | 4 | 4 | 4 |
| 总车位分钟 | 310 | 310 | 310 |
| 带枪位占用分钟 | 70 | 70 | 70 |
| 油车占带枪位分钟 | 0 | 30 | 0 |
| 交付能量 kWh | 8.16666666666667 | 4.66666666666667 | 8.16666666666667 |
| EV 停车失败率 | 0 | 1/3 | 0 |
| ICE 停车失败率 | 1 | 0 | 1 |
| 容量未服务率 | 2/3 | 2/3 | 2/3 |
| 离场缺电率 | 0.722222222222222 | 0.666666666666667 | 0.722222222222222 |
| pending 会话/能量 | 1 / 11.6666666666667 kWh | 同左 | 同左 |

分配断言也逐条通过：A 车 4 拒绝、车 3/5 入 bay0；B 车 4 入 bay0、车 5 拒绝；D 车 4 拒绝（预测余量 1−1−0.9=−0.9 < margin 1）、车 5 入 bay0。期初车辆（1、2）不计入外生 EV/ICE 失败率分母；同刻 3 车在 t=0 均按下标顺序处理（t0 批量检查 3/3）。

### 3.3 构建期失败项与定位（保留记录，未掩盖）

最终两脚本均 0 失败，但构建期出现过 6 类失败，全部定位为**验证脚手架自身缺陷**，与 Python 模型无关，修正后重跑通过：

1. daily_optimal.csv 无 pile_ratio 列（Python RESULT_COLUMNS 契约），比较器原假设有该列 → 改为与“当天最小并列最优行”的 8 个 fixture 列逐项比对，并在 comparison_summary.json 的 notes 中写明该限制。
2. 天键只用 scenario_id：21 天共用同一 scenario_id，导致键碰撞（refusals 690 处假失配、daily-optimal 假失败）→ 键改为 scenario_id|target|ratio 后 0 失配。
3. manifest 用原始字节哈希校验 → 与 MATLAB 文本哈希口径不同（2 个非 ASCII 文件）；改为同口径校验并把原始字节差异单列记录。
4. prei_hash_text/prei_etp 在 run_prei 返回后被 prei_path_init 的 onCleanup 移出路径 → 在比较函数与 ETP 手算检查内重新 prei_path_init。
5. MATLAB strsplit 默认 CollapseDelimiters=true，把 "10;8;4;;0" 的缺行吞掉 → 改 'CollapseDelimiters', false。
6. None 期望用 -1 哨兵与 MATLAB NaN 不一致 → 统一为 NaN（isequaln 判等）。

## 4 未验证与限制清单

- **未运行** apps/parking_lab 的 Simulation 事件仿真类，也未重跑 Python 参考或 experiments/prei 测试；B 组是“按源码契约重写公式 + 手算基准”的独立实现验证，不是对 Python 实现的运行期对照。
- B 组轨迹只覆盖 6 车、3 车位、单带枪位、固定预测参数（arrival_rate_per_hour=6, p_ev=0.5, p_charge_given_ev=0.6）；不覆盖 feeder 功率约束、排队、挪车反事实、预测学习器、随机到达流。
- B 组交付能量按 min(需求, 7 kW×效率×停留) 计，未叠加馈线/共享功率约束；这与 demand_ledger 的静态口径一致，但**不等于** Simulation 的实际交付口径。
- in_window 采用 0 ≤ time_min < horizon 的约定（本轨迹无边界歧义：车 6 在 100 分钟、窗口 120）；未覆盖到达恰在 horizon 的边界。
- A 组只覆盖 n_spaces=40 的 deterministic fixture 两套配置；共享分支 partial_shared_fraction>0、closed-full、v2_n10786 配置未跑。
- A 组 ETP 是“从 Python 矩阵复算定义”层面的核对（不是 Python 独立实现的 ETP），另加了一个与 fixture 无关的手算 ETP 小例（两个窗口/后缀场景）。
- prei_hash_text 对非 ASCII 文本不是原始字节哈希；run_metadata/summary 的平台标签硬编码为 Octave。两者已记录，不据此下“MATLAB 已验证/未验证”的结论。
- MATLAB 控制台对中文路径显示乱码（系统代码页），日志按 UTF-8 落盘；未影响文件路径解析与数值结果。
- 本报告不评价论文结论、不把静态成本口径写成策略建议；legacy 仍为 diagnostic-only。

## 5 产物与复跑

| 路径 | 内容 |
|---|---|
| research/round5_20261031/matlab/scripts/static_verify.m | A 组入口：运行 run_prei、全部比对、ETP 手算例、写 summary |
| research/round5_20261031/matlab/scripts/indep_verify.m | B 组入口：5 类公式重写 + 145 项检查 |
| research/round5_20261031/matlab/static_run/legacy/、corrected/ | MATLAB 原始输出（各 12 文件） |
| research/round5_20261031/matlab/static_run/comparison_summary.json | A 组机器可读比对结论 |
| research/round5_20261031/matlab/static_run/*_diff_by_column.csv | 逐列最大差与最差单元键 |
| research/round5_20261031/matlab/indep/inputs/*.csv | 自写输入与手算期望（13 个文件） |
| research/round5_20261031/matlab/indep/out/indep_checks.csv | 145 项逐项结果 |
| research/round5_20261031/matlab/indep/out/trajectory_visits.csv | A/B/D 逐车分配/交付明细 |
| research/round5_20261031/matlab/indep/out/indep_summary.json | B 组汇总 |
| research/round5_20261031/matlab/logs/ | version_check、static_verify、indep_verify 及其 console 日志，含 EXITCODE= 行 |

复跑：第 1 节命令 2、3 原样执行即可；两脚本幂等清理各自输出目录，不触碰 matlab/prei、experiments/prei 与 research/collection。
