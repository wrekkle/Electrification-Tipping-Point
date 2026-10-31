# REF 配置可比性与成本算术（第五轮）

状态: 生效
日期: 2026-10-31
冻结: 第三/四轮结果与旧成本 JSON 未改动；新证据在本目录与 `repro/`。

## 1 REF 两轮实际配置（从结果 meta 读取，不靠默认值）

| 参数 | 第三轮 main_A | 第四轮 REF | 是否影响需求 |
|---|---|---|---|
| p_EV / q_need | 0.10 / 0.36 | 0.10 / 0.36（来源目录 REF，scenario 值） | 是，相同 |
| horizon_min / start_hour | 1440 / 11.5 | 1440 / 11.5 | 是，相同 |
| 规则 / seeds / lots | A / 1–5 / 5 场站 | A / 1–5 / 5 场站 | 相同 |
| charger_kw / 核算期 | 7.0 / per_day | 7.0 / per_day | 相同 |
| **feeder_kw** | **336** | **120** | 否（不进入需求生成） |
| workers | 8 | 4 | 否（已验证） |
| traffic_gen.py / run_cost_curve.py SHA | 8c47… / 47e4… | d29b… / 3b22… | 版本不同（见 P0） |

## 2 可比性判定（容量与能量分别判断）

- **需求外生**：feeder 120 vs 336 的 1025 行 `demand_hash` 完全相同（0 差异）；差异只在功率上限。
- **服务/成本指标**：1025 行中 `unserved_charge_events`、`unserved_charge_energy_kwh`、`facility_cost`、`unmet_no_connector_events`、`mean_occupancy_rate` 全部相同（复跑 `ref_feeder336.json` 对照第四轮 REF）。
- **功率指标**：8/1025 行的 `peak_power_kw` 不同；feeder=120 运行时峰值被截到 120，feeder=336 时最高 140。即 120 对 8 行是**约束紧的**，336 对该 REF 5 场站 × 5 seed 集合非约束（max 140 < 336）。
- **结论**：两批实验在“需求 + 服务/成本”层面可比；但 **不能把 336 统称为所有情景的非约束馈线**——它只对已验证的 REF 集合非约束，长 k/更多并发充电的场站可能超过 336（k=40×7kW=280 已接近上限，且峰值随占用组合变化）。扫描 k 时未同步增加 feeder（runner 中 feeder 为整轮常量），符合“只增加设备数”的解释前提。
- **写作要求**：引用容量/服务指标时以第四轮 REF（120）或本轮 336 配对重跑为准，不可混用两轮文件；如需强调功率不敏感，须同时给 `peak_power_kw` 证据。

## 3 成本差异 0.0027% 的复算

实际加载（唯一入口 `costs.facility_cost`，`cost_scenario.json#cost`）：

- 资本：116792.62 TWD/枪 ÷ 10 年 ÷ 365 = **31.99797808219178** TWD/枪·日
- 维护：**43.29969863013699** TWD/枪·日
- 合计：**75.29767671232877** TWD/枪·日（k=1, days=1，含站级固定 0）

文档 `cost_scenario.json#facility_cost.per_connector_day_TWD` = **75.29972602739726**，差 **+0.00204931506849** TWD/枪·日 = **0.00272%**。

差异可精确分解为旧口径的取整中间值：
- 文档值 = 32.0000000000 + 15804.4/365 = 32.0 + 43.29972602739726；
- 而当前字段给出资本 31.99797808219178、维护年额 43.29969863013699×365 = 15804.39；
- 即文档用了 **capital≈32.00（capex≈116800）与维护年额 15804.4** 的旧取整值，未随最终字段更新；不是公式系数、寿命或天数错误，也不是把维护重复计入。

处理：**不调参数追平文档**；结果统一使用 `facility_cost` 的计算值（75.29767671232877）。旧文档与旧 JSON 保留，本报告即日期为 2026-10-31 的更正说明：文档值应视为旧快照，正确口径为 `k × (depreciation_capex/life/365 + maintenance_per_bay_day) × days`（站级固定成本单列）。

## 4 复算

    python research/round5_20261031/config/verify_config.py   # 期望 EXIT 0

解释器：C:\anaconda\python.exe 3.12.3。数据：`research/round5_20261031/repro/ref_feeder336.json`。
