# R2-B 修复报告：真实需求能量与平稳长度偏置暖启动（traffic-eng）

类型: 研究报告
状态: 交付（待 Lead 独立验收）
负责人: traffic-eng（第二轮 subagent；Lead 统一验收）
日期: 2026-10-31
写范围: apps/parking_lab/workbench/traffic_gen.py、apps/parking_lab/workbench/tests/test_traffic_gen.py、
research/round2_20261031/traffic_fix/、research/traffic_generation_20261031/verify_v2.py（仅新增 *_v2）
生成器版本: traffic_gen-1.1.0 -> traffic_gen-2.0.0
冻结输入: research/traffic_generation_20261031/fitted_parameters.json 未改动（sha256 前缀 1dfc14a2a29e204d，与 BASELINE.md 一致）

## 1 结论

1. R2-D3 已修复：Arrival.energy_kwh 现在是真实需求能量，由 energy 块的真实需求分布
   （deficit_mean_kwh=49.0168, sd=8.0, clip=[4,55] kWh，is_scenario=true）抽样，
   不再出现 min(需求, 功率×停留) 的提前削减。分列账：真实需求 / 理论所需时间 /
   停留内可交付 / 离场缺口 / 期末待交付 / 删失标记。
2. R2-D4 已修复：暖启动改为平稳长度偏置（先按 P(D)∝D·f(D) 抽 D，再 age~U(0,D)，
   remaining=D-age），并提供公开 API warm_start_arrivals(lot_info, n, rng, dwell_dist, ...)；
   旧的“普通分布抽 D 再 U(0,D)”实现已删除（迁移见 §4.5）。
3. 固定外生需求后，改变 k / 额定功率 / 馈线功率不改变任何车辆的原始需求能量
   （生成器层与仿真层都逐车+哈希验证通过）。
4. 删失（窗口截断）已标记：censored_charge_sessions 单列，pending 单列；
   charge_shortfall_sessions 只统计“窗口内离场且真实需求 > 停留内可交付”的事件，删失不计失败。
5. 修复前反例 8/8 失败（退出码 1），修复后 8/8 通过（退出码 0）；
   tests/test_traffic_gen.py 18/18 OK；verify_v2.py 8/8 检查通过；
   Lead 的 verify_round2.check_stationary_residual 通过（期望 14.612、实测 14.132、n=150）。

## 2 缺陷清单

| 编号 | 现象 | 根因 | 状态 |
| --- | --- | --- | --- |
| R2-D3 | 14 kWh / 7 kW / 停 60 min 的车辆被生成为 7 kWh 需求；更短的停留削得更狠 | `_charge_energy` 先把“想要的充电时长”与 dwell 取 min，再把可用时长换回能量；需求在进入仿真前已丢失 | 已修 |
| R2-D3b（新发现） | 逐场站能量由“观测充电时长 × 情景功率”换算：params.energy.charger_power_kw 11→7 时所有需求能量同比例缩小；且完全绕过 deficit_clip_kwh [4,55] 与电池 60 kWh——旧口径 TPE0330 平均每会话 191.9 kWh（> 电池容量） | 能量被定义为“可交付量”，不是需求；功率同时是需求和供给参数 | 已修 |
| R2-D4 | 两点停留 {1,9} 等权时暖启动剩余均值 2.489 min（理论 4.1，偏差 −39%） | “普通分布抽 D + U(0,D)”得到的是新到车辆的剩余寿命，不是 t=0 平稳在场车辆的剩余寿命；且生成器与 runner 各有一套实现 | 已修 |
| R2-D4b（新发现） | `charge_shortfall_sessions` 无法与真实缺口对应：旧实现把“时长被停留截断”的会话计数，但窗口期末仍在场的车也计入；没有缺电量、没有删失字段；`_finalise` 的兜底 `n_short` 判据 `energy < cap*dwell` 写反（仅因 meta 已有键未暴露） | 没有分列需求账；删失与失败混为一谈 | 已修 |

## 3 修复前失败证据（最小反例，先失败后修）

反例脚本：research/round2_20261031/traffic_fix/repro_defects.py
修复前用冻结旧源码快照运行（不改工作区实现）：

    $env:TRAFFIC_GEN_SNAPSHOT="research/round2_20261031/traffic_fix/pre_fix_traffic_gen_snapshot.py"
    python research/round2_20261031/traffic_fix/repro_defects.py --out research/round2_20261031/traffic_fix/before_fix_failures.txt

旧快照 pre_fix_traffic_gen_snapshot.py：17,611 字节，
sha256 = 52dabaad74a6d89bccc84d97011d1b138fcc9016f17b740a46fd1e6f3fd2f6f6，
与 BASELINE.md 冻结的旧 traffic_gen.py 哈希逐字节一致；退出码 1，输出 0/8 通过。

| 反例 | 修复前（退出码 1） | 修复后（退出码 0） |
| --- | --- | --- |
| C1 真实需求不被削减：14 kWh/7 kW/停 60 min | n_need=22，全部 energy≈6.99999 kWh | n_need=22，全部 energy=14.0 kWh |
| C2 需求能量不随额定功率改变（7/3.5/50 kW 同 seed） | 平均需求 7.0/3.5/14.0 kWh，哈希不同 | 平均需求 14.0/14.0/14.0 kWh，哈希相同 |
| C3 meta 分列五项需求账 | 5 个键全部缺失 | 键齐全，需求=308.0 kWh，恒等式成立 |
| C4 暖启动平稳长度偏置 {1,9} | 剩余均值 2.4891 min | 剩余均值 4.1173 min（理论 4.1） |
| C5 warm_start_method / length_biased | None / None | "length_biased_stationary" / True |
| C6 删失标记且不算失败（窗口 120 min、停留≈720 min） | censored/pending/shortfall_energy/demand_total 均缺失 | censored=12，pending=577.295 kWh，demand=720.0 kWh，离场失败=0 |
| C7 公开 API warm_start_arrivals | 不存在 | 存在，前 4 参为 (lot_info, n, rng, dwell_dist) |
| C8 不把每辆都削到停留可交付上限 | 20 辆中 12 辆被削减（8 辆恰好压在上限） | 20 辆全部保留真实需求 |

证据文件：before_fix_failures.txt（1,378 B）、after_fix_verify.txt（1,262 B），均为 UTF-8。

## 4 补丁（traffic_gen.py）

### 4.1 真实需求能量

- 新增 `_demand_block` / `_sample_demand_kwh`：从 energy.deficit_mean_kwh / sd / clip 抽真实需求，
  只依赖 energy 分布，不读 charger_power_kw / dwell。
- 删除 `_charge_energy`（旧实现 core）、`_duration_sampler`（旧逐场站时长→能量换算）、`_energy_block`。
- 理论所需时间在账本中计算：required_min = demand / (charger_kw×efficiency) × 60；
  功率只影响“所需时间/可交付量”，不再影响需求。
- generate() 与 generate_for_lot() 的所有到店车辆、期初车辆都走同一需求抽样。

### 4.2 平稳长度偏置暖启动（公开 API）

    warm_start_arrivals(lot_info, n, rng, dwell_dist, *, p_ev=None, q_need=None,
                        energy=None, mean_energy_kwh=None, min_dwell_min=1.0,
                        max_dwell_min=1440.0, vehicle_id_start=0) -> tuple[Arrival]

- 分量选择概率 ∝ weight_i × E[D_i]；对数正态分量内抽 mu+sigma^2（长度偏置对数正态）；
  无参数回退按指数分布长度偏置（均值×2）。
- 再 age~U(0,D)，remaining=D-age，time_min=0；这些是期初在场车辆，不是 t=0 新到达。
- 新增 `stationary_residual_mean(dwell_dist, max_dwell=None)`：闭式 E[D²]/(2E[D])，
  带生成器上限时给 E[min(D,1440)]/2，供 meta 与验收对照。
- generate_for_lot 的暖启动行直接调用该 API（不再有第二份实现）。

### 4.3 meta 与逐车分列账

meta 新增（generate 与 generate_for_lot 都有）：

    demand_energy_kwh_total, theoretical_service_min_total, deliverable_energy_kwh_total,
    departed_shortfall_kwh, pending_energy_kwh, censored_charge_sessions,
    charge_shortfall_sessions, charge_shortfall_energy_kwh, n_charge_sessions,
    initial_occupancy_demand_kwh, new_arrival_demand_kwh, charger_power_kw, efficiency,
    warm_start_method, length_biased, n_new_arrivals, energy_accounting_method；
    generate_for_lot 另有 expected_warm_residual_mean_min、warm_start_note。
旧键 warm_start、initial_occupancy_n、initial_occupancy_vehicles、mean_energy_kwh 保留。
逐车列由 `demand_ledger(arrivals, *, charger_kw, efficiency, horizon_min,
initial_occupancy_n=0, include_vehicles=False)` 提供（需求/理论时长/可交付/离场缺口/
期末待交付/censored/charge_shortfall），口径为“假定一把枪全程可用”的静态可行性上界；
排队/规则拒绝/共享馈线下的真实交付以仿真 metrics 为准。

### 4.4 删失与失败口径

- censored = time_min + dwell_min > horizon_min（窗口截断），单列 censored_charge_sessions。
- charge_shortfall_sessions 只计 non-censored 且 demand−可交付>1e-9 的事件；
  删除 `_finalise` 里写反的 n_short 兜底判据。
- 恒等式（逐场站验证误差 ≤1e-6）：demand = deliverable + departed_shortfall + pending。

### 4.5 旧实现删除与迁移说明

- 旧“普通分布抽 D 再 U(0,D)”暖启动实现**已删除**，没有保留开关（避免再次误用）；
  需要复现旧结果时只能用冻结 JSON 与旧源码快照 pre_fix_traffic_gen_snapshot.py。
- 旧逐场站“时长×功率”能量路径已删除；fitted_parameters.json 中的 charge_duration_hist_5min
  现在只作观测诊断，不再驱动能量。
- GENERATOR_VERSION 1.1.0 -> 2.0.0；Arrival 仍为 6 字段，stream_hash/demand.stream_hash 算法不变，
  save_traffic/load_traffic 不变，参数 schema 不变（traffic_gen_params/v1）。
- **runner 迁移**：research/integer_allocation_20261031/run_cost_curve.py 自带的 warm_start_arrivals
  仍是旧口径（普通分布 + U(0,D)）。Lead/集成侧应改为调用
  traffic_gen.warm_start_arrivals(lot_info, n, rng, lot_info["dwell_dist"], p_ev=..., q_need=...,
  energy=params["energy"], min_dwell_min=..., max_dwell_min=...)，并在 p_ev/q_need 覆盖情景下
  同步重建期初车辆类型（该文件不在本单写范围）。

## 5 修复后验证

| 验证 | 命令 | 退出码 | 结果 |
| --- | --- | --- | --- |
| 反例/回归 8 项 | `python research/round2_20261031/traffic_fix/repro_defects.py --out .../after_fix_verify.txt` | 0 | 8/8 PASS |
| v2 独立校验 | `python research/traffic_generation_20261031/verify_v2.py` | 0 | 8/8 checks true，9 个 usable 场站 |
| traffic_gen 单测 | `python -m unittest apps.parking_lab.workbench.tests.test_traffic_gen` | 0 | Ran 18, OK |
| 全量套件 | `python -m unittest discover -s apps/parking_lab/workbench/tests` | 1（并行 R2-A） | Ran 281：4 failures + 6 errors 全部在 tests/test_costs.py（成本工作流并行编辑中）；本单文件 18/18 通过。04:00Z 同一命令曾 Ran 281 OK |
| CLI 冒烟 | `python -m apps.parking_lab.workbench traffic --params research/traffic_generation_20261031/fitted_parameters.json --seed 42 --out .../cli_smoke_v2.json` | 0 | 329 辆，stream_hash=0f7eb1ea…，产出 cli_smoke_v2.json |
| Lead 验收项 3 | `python -c "...verify_round2.check_stationary_residual()"` | 0 | pass=True，expected=14.6121，observed=14.1323，n=150，method=length_biased_stationary |
| 仓库检查 | `python scripts/check_all.py` | 1 | 文档与链接通过、文献索引通过；“稿件字数与章节一致性”因缺 python-docx（与 BASELINE 相同，非本次改动） |

verify_v2 检查项：需求哈希对功率/效率情景不变；两点暖启动 4.1；9 场站账本恒等式；删失不计失败
（逐场站独立重算一致）；真实需求超过停留可交付（有缺口/待交付）；暖启动合并均值贴近平稳期望；
t=0 占用与实测均值误差 <1%；暖启动剩余均值远离旧均匀残余法。

## 6 关键数字（fitted_parameters.json，9 个 usable 场站，seed=42）

| 指标 | 修复前口径 | 修复后（本次实测） |
| --- | --- | --- |
| 每会话需求能量 | 旧“时长×功率”均值 20.03–191.9 kWh（逐场站，部分超电池 60 kWh；未受 clip 约束） | 39.9–47.2 kWh/会话；9 场站合计 108 会话、4,874.3 kWh，均值 45.13 kWh |
| 若按旧规则 min(需求,可交付) 再削一次 | 会静默丢掉真实需求的 10.2%（合计 437.7 kWh；单场站最高 49.7%，TPE0695） | 0%（需求不再削减；缺口单列） |
| 暖启动剩余停留（9 场站 × seed1–5 合并 n=6,685） | 旧 U(0,D) 法 883.3 min | 1,149.75 min；平稳（含 1440 上限）期望 1,123.44 min，偏差 +2.34% |
| 两点 {1,9} 暖启动剩余均值 | 2.5 min | 4.1173 min（理论 4.1） |
| t=0 占用相对实测均值误差（9 场站平均） | 0.266% | 0.266%（期初车辆数不变，方法只改剩余停留分布） |
| 24h 占用相对 RMSE（同脚本同面板 seed=42，均值） | 0.2474（旧 verify_report.json pooled） | 0.1914 |
| 离场缺口 / 期末待交付 | 无字段（被提前削减掩盖） | 496.9 kWh / 176.1 kWh，合计占真实需求 13.8% |
| 删失 / 离场失败会话 | 无区分，期末在场可能被算作失败 | 50 删失（单列，不算失败）/ 23 个离场缺口事件 |

## 7 对旧结论的影响

1. **旧报告 docs/reports/2026-10-31-整数配桩规则与仿真验证.md 的 §6–§8、§10 数字全部基于旧车流**
   （需求被削减 + 暖启动有偏），不能作为 v2 结论引用；整数曲线 / 三规则对照 / p_EV 敏感性必须由
   Lead 用 traffic_gen-2.0.0 重跑后再更新。旧曲线 JSON 保持冻结，仅作 v1 证据。
2. 方向性影响（未重跑不宣称数值）：每会话真实需求由“可交付量”提高到 ~45 kWh 量级，功率/停留型
   缺口与未满足能量上升；充电会话数口径（target_charge_arrivals、p_EV·q_need）未变，因此
   容量型未服务事件 U(k) 的计数口径不变，但 k 相关的能量型指标会变，k_α 需重算，旧 k 值不能平移。
3. 暖启动变长使 24h 占用整体抬高：同一脚本同一面板上占用相对 RMSE 0.2474→0.1914（改善），
   说明旧报告“占用验证”结论方向仍成立但数值需更新；t=0 占用 0.27% 的结论仍成立（期初车辆数固定）。
   旧报告 §12 中 0.553 的验证 RMSE 属另一口径，需按 v2 重测后引用。
4. 旧 charge_shortfall_sessions 数字（verify_report.json 中 0/1/3/13 等）语义已变，不可直接对比；
   新字段排除删失并只计窗口内离场缺口。
5. 旧报告 §11 的 `python research/traffic_generation_20261031/verify.py` 对新语义必然红
   （其断言 energy<=power*dwell 正是被修掉的缺陷），应改指向 verify_v2.py；
   calibration_report.md 与 report_gen.py 中的暖启动描述（U(0,D)）需更正（Lead 报告任务）。
6. old cli_smoke.json / sample_traffic_seed42.json / verify_report.json 冻结保留，但 stream_hash
   与 v2 不可比；不要用旧 JSON 对照新流。

## 8 需登记 docs/TODO.md 的新问题（本单不改 TODO）

1. research/integer_allocation_20261031/run_cost_curve.py 的 warm_start_arrivals 仍是旧
   “普通分布+U(0,D)”，且 p_ev/q_need 覆盖路径用 meta.mean_energy_kwh 常数近似；集成侧需改为复用
   traffic_gen.warm_start_arrivals（本单不越界修改）。
2. 能量分布改为全局 deficit 情景后，逐场站观测充电时长不再进入能量抽样：是否重标定“逐场站需求
   能量分布”或把全局情景写进论文假设，待定；charge_duration_hist_5min 目前只剩诊断用途。
3. verify.py / report_gen.py / calibration_report.md 的旧口径描述需更正并指向 verify_v2.py。
4. 需求能量均值 49 kWh 由 11 kW/0.9 情景从观测平均充电时长换算（is_scenario=true）；若论文采用
   7 kW 情景，需求不变但理论所需时间与功率/停留缺口增大，报告必须两口径分列。
5. 建议给 runner 集成加回归测试：同一 (场站, seed) 的暖启动剩余分布与 traffic_gen API 逐车一致。

## 9 文件与哈希（SHA-256）

| 文件 | 字节 | sha256 |
| --- | ---: | --- |
| apps/parking_lab/workbench/traffic_gen.py | 30,368 | 63f06d98c9bb3f5d453c9ca9b93f87026e274299a8c6b53c33e06066a6c99404 |
| apps/parking_lab/workbench/tests/test_traffic_gen.py | 22,168 | 84379a715eef0b781d951a9e62a602f7a1ba1fb411aa89a4f16d237326a9f9ef |
| research/traffic_generation_20261031/verify_v2.py（新增） | 15,139 | b9a93fa285c4f5d8d0fb048106d3f2bf45162e8a8bf0d571d6e26b2fc35acffe |
| research/traffic_generation_20261031/fitted_parameters.json（未改） | 187,613 | 1dfc14a2a29e204d81db0cecd38b8d4f94ecb6e700280f1e70d1ab66275f6229 |
| research/round2_20261031/traffic_fix/repro_defects.py | 12,920 | dcd8f23ebe4841312fec1b07c7a2cfac9257385a5a70ca090ce59b6c48b8d407 |
| research/round2_20261031/traffic_fix/pre_fix_traffic_gen_snapshot.py | 17,611 | 52dabaad74a6d89bccc84d97011d1b138fcc9016f17b740a46fd1e6f3fd2f6f6 |
| research/round2_20261031/traffic_fix/before_fix_failures.txt | 1,378 | b4c319597d21cb8711aa6547a5e3ae6ec27cb84d09bf59343ef36f87f86e8045 |
| research/round2_20261031/traffic_fix/after_fix_verify.txt | 1,262 | f45b5b112747c6ae10ed393b1e5b0aaeedb97fa38d5813bd249f427b81b37611 |
| research/round2_20261031/traffic_fix/traffic_fix_verify.json | 13,723 | 2a1f3bb8c3dd44fe60f6599aa2ef695f1629f2b7b437057c814d6da5fd04c0c8 |
| research/round2_20261031/traffic_fix/cli_smoke_v2.json | 54,180 | bc26e7113524c9ea6dc3ad7ed9a8b96b958e2965259b3ecf714690b1fa176450 |
| research/round2_20261031/traffic_fix/traffic_gen_tests_run.txt | 504 | 37eb5a56032fcf44af51fe424711a2921efd8771f255a19e41ad33b9851bde17 |
| research/round2_20261031/traffic_fix/test_suite_run.txt | 8,137 | acdd3d33d32affd5a6bffac74aa1c870900dae9bf15263fc72b25722435abae8 |

时间戳（UTC）：traffic_gen.py 04:02:02；反例 03:58:38（修复前）/04:05:43（修复后）；
verify_v2.py 与 traffic_fix_verify.json 04:05:44；全量套件 04:08:20。
本报告自身哈希不列（自引用）；Lead 复算命令：Get-FileHash <路径> -Algorithm SHA256。

## 10 限制

1. 真实需求分布是全局情景（is_scenario=true，由观测平均充电时长按 11 kW/0.9 换算），不是逐场站
   识别值；样本外/情景外推仍不可证。
2. 生成器层账本是“一把枪全程可用”的静态可行性上界，不建模排队、规则拒绝与馈线共享；
   真实交付以仿真 metrics 为准。
3. 只处理右删失（窗口截断）；期初车辆用平稳分布建模，不是真实逐车状态（旧限制不变）。
4. 未重跑整数曲线/三规则对照（Lead 范围），因此本报告只给方法修复与可复算数字，不给新的 k 结论。
5. 全量套件当前因 R2-A（costs.py 并行编辑）为红，与本单文件无关；Lead 合并后需复跑全量。
