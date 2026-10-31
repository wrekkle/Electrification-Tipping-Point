# T36 数据接线审计（第四轮）

- 生成时间（UTC）：2026-10-31T06:43:57Z
- 命令：python research/round4_20261031/data_trace.py
- 范围：原始来源 → 派生量 → 参数文件 → 运行入口 → 结果字段；只读审计，不改数据/代码
- 情景目录：research/round4_20261031/charge_probability_sources.json（sha256 331caf842ebfe60a）

## 1. 结论摘要

- 正式读取链完整：台北停车/充电桩面板 → fitted_parameters → traffic_gen → Simulation → main_A 结果；p_EV=0.10、q_need=0.36 是 argument 情景输入，不从数据反推。
- M08/M10 只到 rates.json/model v1/v2 与情景目录，未进第三轮正式 manifest；属已下载未接线。runner 已支持 --charge-catalog，正式结果尚未使用。
- M14 仅背景参考（0.4 是 q_location_share 地点份额，不是 q_use）；M15 只有研究页、无数据集；M16 有 44,225 条会话，无 parking event 分母 → 均未接线。
- 成本为官方 VOT/油/电 + P26 迁移 capex/维护 + 10 年寿命情景混合；损失参数缺失，cost_complete=false。
- 哈希链：model v1 的 evidence_file_sha256 对应 evidence.json 文件 sha256（4da1a545…），已闭合；rates.json 自身不含 evidence_sha256。

## 2. 分项核对（20 项：19 pass / 1 unverified / 0 fail）

| # | 核对项 | 结果 | 证据/数值 |
|---|---|---|---|
| C01 | charge_probability_sources.json 通过 load_catalog/resolve | pass | schema=charge_probability_sources/v1；场景数=6；必需 id 缺失=无；catalog sha256=331caf842ebfe60a27df4b9d3c32823190ae0770dc86c08d9646d0e57b477f1c |
| C02 | 6 个情景 q_need 与 rates.json 一致、p_EV 全部=0.10 | pass | M08-NEAR-BEV: rates 1421/4974=0.285685564938；catalog q_need=0.285685564938；source=M08；M08-NEAR-PHEV: rates 705/3095=0.227786752827；catalog q_need=0.227786752827；source=M08；M08-NEAR-COMBINED: rates 2126/8069=0.263477506506；catalog q_need=0.263477506506；source=M08；M08-ALL-AWAY-REF: rates 16557/232083=0.071340856504；catalog q_need=0.071340856504；source=M08；M10-OUT-OF-HOME: rates 1955/8249=0.236998424 |
| C03 | q_use→q_need 全部显式假设性迁移、REF 标历史参考未识别 | pass | 异常=无；识别标签集合=['historical_reference_not_identified', 'hypothetical_scenario_transfer_not_target_identified'] |
| C04 | 每个情景的分子/分母/事件定义/地区/时期/车型/地点/限制/来源 id 非空 | pass | 缺失字段=无（6 情景 x 8 必填项） |
| C05 | rates.json 7 条记录的转录状态与 v2 识别边界（0.0364 仅为 usage proxy） | pass | 记录数=7；转录状态分布={'local PDF table visually checked; origin': 4, 'publisher/institutional fulltext search-': 3}；v2 value=0.036365830891079 status=usage_proxy；分子 reported=2800 / recount=2198；分母=84622 / ratio=0.025974 |
| C06 | evidence.json 文件 sha256 与 model v1 evidence_file_sha256 是否闭合 | pass | model v1 evidence_file_sha256=4da1a545033304c805d213e986bed234899120f180c424076f01a0afb99ca211；evidence.json 文件 sha256=4da1a545033304c805d213e986bed234899120f180c424076f01a0afb99ca211；rates 自身无 evidence_sha256='4da1a545033304c805d213e986bed234899120f180c424076f01a0afb99ca211'；引用对象是 evidence.json，不是 rates.json。 |
| C07 | 台北 parking/connector 原始面板 → fitted_parameters（279 槽/372 场/18 场参数） | pass | 原始文件存在：parking=True connector=True；fitted.source: slots_used=279, slot_minutes=5, observed_sites=372, window_utc=['2026-10-30T03:30:00+00:00', '2026-10-31T03:25:00+00:00'], occupancy_definition=O = baseline_totalcar - availablecar (net occupancy, not arr, arrival_method=net-increase counting: sum of max(0, delta O) per 5-min slot；per_lot=18 场，usable=9 场，usable_train=5 |
| C08 | per_lot 派生量可复算：λ×停留=占用、观测乘积、充电会话率、期初占用、分布参数 | pass | usable=9 场；max/lambda*dwell/60-occupancy/=1.137e-13；max/rate/lambda-product/=0.000e+00；异常=无；TPE0610: n_spaces=43.0 n_connectors=2 mean_occupancy=9.038 lambda=3.429 dwell_mean=158.159 rate=0.0663 product=0.019332 |
| C09 | 真实调用 traffic_gen.generate_for_lot（TPE0610, seed=1, independent, strict） | pass | arrivals=89；initial_occupancy_n=9（round(mean_occupancy)=9，t=0 期初=9）；p_ev=0.1 q_need=0.36 product=0.036；p_ev_source=argument q_need_source=argument；product_coupled=False；demand_calibration_status=scenario_not_identified；warm_start_method=length_biased_stationary；stream_hash=d6daf3849fa3ab97 |
| C10 | cost_scenario → costs.facility_cost → 结果行 facility_cost 数值闭合 | pass | costs.facility_cost(k=1,days=1)=75.297676712329；结果行 TPE0008/seed1/k1 facility_cost=75.297676712329；cost_scenario 文档 per_connector_day=75.299726027397（文档值与本公式差 0.002049315068，另见 C20）；items={'device_capital': 31.99797808219178, 'device_maintenance': 43.29969863013699, 'facility_fixed': 0.0}；missing=None；row scenario_model=independent p_ev_used=0.1 q_need_used=0.36 |
| C20 | cost_scenario 文档 per_connector_day 与其自身公式复算的差异 | unverified | 文档=75.299726027397；按 cost 字段复算=75.297676712329；差=0.002049315068 TWD/枪·日（相对 2.72e-05，占比 0.0027%）。可能源于 annual maintenance 基数或舍入不同；结果行使用运行公式值，需成本任务确认文档值口径。 |
| C11 | 运行入口 run_experiments.py → run_cost_curve.py；manifest 正式跑用独立 p_ev/q_need 未用 catalog | pass | manifest 记录=64（phase={'pilot': 2, 'tune': 34, 'main': 4, 'pq': 6, 'power': 4, 'legacy': 1, 'validation': 4, 'expand': 1, 'rules_pq': 8}）；main 记录=4，全部含 independent/p_ev 0.1/q_need 0.36/fitted/cost=True；main 命令含 --charge-catalog/--charge-scenario 数=0；非零退出=无；结果 meta 含 charge_catalog/charge_scenario=False；结果行含 charge_scenario_id 的行数=0（历史结果早于接线） |
| C12 | 结果字段含成本/服务/识别口径；期初占用与参数一致 | pass | 缺失字段=无；initial_occupancy_n=29（k=1 行）；service_metrics keys=['denominators', 'levels', 'missing', 'numerators', 'policy', 'rates', 'visit_count', 'window']；observed_ratio_z=0.022779；identification_conflict=False；product_coupled=False；p_ev_source=argument；q_need_source=argument |
| C13 | M08/M10 观测率未被正式运行入口读取（已转录未接线） | pass | 运行时 .py（排除 tests）grep 命中数={'rates.json': 0, 'model_20261031': 3, 'M08': 0, 'M10': 0}；rates.json/M08/M10 命中=0；命中文件={'rates.json': [], 'model_20261031': ['research/integer_allocation_20261031/_inspect_model.py', 'research/round3_20261031/audit_round2.py', 'research/round3_20261031/verify_round3.py'], 'M08': [], 'M10': []}；manifest 正式跑 catalog 使用=0；model_20261031 命中仅审计/校验脚本引用 |
| C14 | M14 仅背景参考：地点份额 0.4 不是 q_use，且运行时未读取 | pass | M14 PDF 存在=True bytes=54335400；运行时 q_location_share 命中=3 文件=['apps/parking_lab/workbench/charge_sources.py', 'apps/parking_lab/workbench/parameter_registry.py']（仅 validator/参数注册的拒绝名单，不读 M14 数据）；10 次中 4 次充電为地点份额（q_location_share），不能当 q_use；家充比例等 UNVERIFIED |
| C15 | M15 仅下载研究页、未取得数据集 → 未接线 | pass | ACN_research.html 存在=True bytes=25335；raw 目录 ACN 数据集文件=无；未下载、未解析、未接线 |
| C16 | M16 已下载交易 CSV，字段质量可用于会话级派生，但无停车事件分母 → 未接线 | pass | 数据行=44225；Operator 非空=860；四个时间戳均非空=856；Total kWh 数值=860；只有充电会话（无 parking event 分母），不可直接算 q_use |
| C17 | 成本参数按官方/可迁移/情景/不可识别分层；设施成本未混入社会损失参数 | pass | VOT 官方 CPI 链=6.7771；capex 官方值=None（不可识别），迁移值=116792.62；maintenance 迁移值=15804.14；寿命=情景 10 年；缺失损失参数=['activity_loss_per_failure', 'residual_trip_loss_per_kWh']；cost_scenario sources 含 FX 30.9 UNVERIFIED=True；结果 cost_complete=False cost_missing_parameters=['alternative_charging_delta_per_kwh', 'detour_km_per_failure', 'detour_min', 'emission_cost_per_km', 'ev_energy_price_per_kwh', 'ev_kwh_per_km', ' |
| C18 | CPI 链与 FX 限制已标注（VOT 保守下界、FX 30.9 UNVERIFIED） | pass | VOT limitations=["手冊明示未來值應以工資上漲率調整；CPI 僅為保守下限（2009→2018 手冊自身由 3.61 修訂至 5.93，+64%，同期 CPI 僅 +9.8%）", "若改用薪資成長率，結果會高於本值；本值為可辯護的下界，不宜宣稱唯一真值", "2026 價格水準為 1-9 月平均代理"]；capex/maintenance FX limitations=["FX 30.9 為 UNVERIFIED（央行年報章節未印平均匯率），須以官方年平均替換", "2 槍 pedestal 攤提假設；1 槍配置會較高", "未含配電擴容、土木與審查費", "與交通部慢充補助額度 8 萬元/槍相比偏高，兩者不宜直接互換（見 evse_subsidy_cap）"]["FX 30.9 為 UNVERIFIED；且『每 pede；VOT 换算式：6.7771x60=406.62 |
| C19 | 缺失不可识别：官方销售份额/公共使用份额/到达份额、p_EV 与 q_need 均无识别证据 | pass | TODO 登记=- U19 外部参数缺口（2026-10-31）：实际市售比/- U20 文献全文缺口（2026-10-31，第四轮更新）/- U21 功率敏感性只有 4 个配置×3 seed，能量约；数据窗口只有两天面板（307 槽/25.75h）无完整日；p_EV/q_need 不可识别，0.0364 仅为 usage proxy；这些缺口未因本目录或接线而消除 |

## 3. 台北数据如何进入到达/停留/初始状态

~~~text
parking_slots.jsonl + connector_status_long.jsonl（2026-10-30|31，279 个 5 分钟有效槽，372 场）
  └─ 校准（traffic_generation_20261031）→ fitted_parameters.json（18 场 per_lot）
       ├─ lambda_hour_by_bin / lambda_bar_veh_per_hour → 到达强度
       ├─ dwell_dist（两成分混合）→ 停留时长
       ├─ mean_occupancy_vehicles（四舍五入）→ 期初占用 n_initial
       └─ charge_session_rate_mean_hour → 观测乘积 rate/λ（≠ q_need）
  └─ run_cost_curve.py --params → traffic_gen.generate_for_lot(...)
       → Simulation(config, arrivals) → rows: facility_cost / service_metrics / initial_occupancy_n
~~~

C09 实测（TPE0610, seed=1, independent, strict）：arrivals=89，initial_occupancy_n=9，t=0 期初 9 辆；p_ev=0.1/q_need=0.36，product=0.036，product_coupled=false，demand_calibration_status=scenario_not_identified。

## 4. 概率情景目录与来源状态

| scenario_id | p_EV | q_need | 来源 | 对象/识别 |
|---|---|---|---|---|
| REF | 0.10 | 0.360000000000 | round3_preregistration/v1 (scenario) | q_need；historical_reference_not_identified |
| M08-NEAR-BEV | 0.10 | 0.285685564938 | M08 (official) | q_use；hypothetical_scenario_transfer_not_target_identified |
| M08-NEAR-PHEV | 0.10 | 0.227786752827 | M08 (official) | q_use；hypothetical_scenario_transfer_not_target_identified |
| M08-NEAR-COMBINED | 0.10 | 0.263477506506 | M08 (official) | q_use；hypothetical_scenario_transfer_not_target_identified |
| M10-OUT-OF-HOME | 0.10 | 0.236998424051 | M10 (peer_reviewed) | q_use；hypothetical_scenario_transfer_not_target_identified |
| M08-ALL-AWAY-REF | 0.10 | 0.071340856504 | M08 (official) | q_use；hypothetical_scenario_transfer_not_target_identified |

所有 q_use 条目均带 transfer.type=hypothetical_transfer，statement 明写假设性迁移；REF 走 historical_reference_not_identified。

## 5. M08/M10/M14/M15/M16 状态

| 编号 | 证据 | 可用变量/数值 | 接线状态 |
|---|---|---|---|
| M08 | papers/electrification-math/M08_INL-parking-event-charging-rate_2015.pdf（355206 B，sha16 afaf43d93c73008b） | near-EVSE q_use：BEV 1421/4974=0.285686，combined 2126/8069=0.263478，all-away 16557/232083=0.071341 | 已下载未接线（仅背景/情景） |
| M10 | research/official_data_20261031/ev_behavior/raw/M10_TUE_fulltext.pdf（4655408 B，sha16 dd1312a74ac08f4a） | out-of-home 1955/8249=0.236998（Table 3，provisional） | 已下载未接线（仅背景/情景） |
| M14 | research/official_data_20261031/ev_behavior/raw/IOT_public_charging_demand_table.pdf（54335400 B，sha16 6c6a0883fdcfaee2） | 10 次中 4 次充電=地点份额 0.4（q_location_share，非 q_use）；每週 1-2 次/家充/SOC 29 percent/時長 72min（部分 UNVERIFIED） | 背景参考，未接线 |
| M15 | research/official_data_20261031/ev_behavior/raw/ACN_research.html（25335 B，sha16 a19f225b2d683f56） | 仅研究页描述；无数值变量 | 已下载未接线（数据集未取得） |
| M16 | research/official_data_20261031/ev_behavior/raw/barnet_cityev_2021Q2.csv（601635 B，sha16 ffe8f53f60459298） | 44225 条会话；Operator 非空 860；四时间戳齐全 856；无 parking event 分母 | 已下载未接线（背景） |

## 6. 成本来源混用与 CPI/FX 限制

| 项目 | 值 | 来源类别 | 限制 |
|---|---|---|---|
| VOT | 406.63 TWD/veh·h | 官方（CPI 链式换算） | 保守下限；手册建议工資上漲率；2026 为 1-9 月平均代理 |
| 汽油/电价 | 31.7385 TWD/L；4.08 TWD/kWh | 官方 | 价格基准时点需按年核对 |
| EVSE capex | 116,792.62 TWD/枪 | 可迁移（P26 3325.5 USD/枪） | FX 30.9 UNVERIFIED；未含配电/土木；2 枪 pedestal 摊提 |
| 维护 | 43.2997 TWD/枪·日 | 可迁移（P26） | FX UNVERIFIED；未区分硬体维修 |
| 寿命 | 10 年 | 情景假设 | 无官方来源 |
| 损失参数 | 缺失 | 缺失不可识别 | residual_trip_loss 等为 null；cost_complete=false |

设施成本（单枪单日）= 75.297676712329 TWD，与 cost_scenario facility_cost.per_connector_day_TWD 一致；结果行 TPE0008/seed1/k1 facility_cost=75.297676712329，未混入社会损失项。

## 7. 缺失与 UNVERIFIED

- **G1 p_EV 与 q_need 的目标识别**（缺失不可识别）：只有 usage proxy 0.0364；需官方销售份额/公共使用份额/到达份额（U19/T28）
- **G2 M08/M10 进入正式概率情景**（已下载未接线）：catalog 已定义且 runner 支持 --charge-catalog；正式 manifest 尚未使用
- **G3 M14/M15/M16 的可用变量**（背景参考/已下载未接线）：M14 仅地点份额；M15 无数据集；M16 无 parking 分母
- **G4 成本参数完整社会成本**（缺失不可识别）：损失参数缺失，cost_complete=false，只有设施成本；capex/maintenance 迁移且 FX UNVERIFIED
- **G5 证据哈希链闭合**（UNVERIFIED）：已核：引用对象是 evidence.json，其文件 sha256 与 model v1 引用一致；rates.json 自身不含该字段
- **G6 数据窗口**（限制）：两日面板（307 槽/25.75h），无完整日；拟合与验证仅此窗口

## 8. 复现

~~~text
python research/round4_20261031/data_trace.py
python apps/parking_lab/workbench/charge_sources.py --catalog research/round4_20261031/charge_probability_sources.json
~~~

本次只写 data_trace.py、data_trace.json、data_trace.md、charge_probability_sources.json；未改 workbench/config/runner/历史 JSON。

> **2026-10-31 补记**：本审计生成时第四轮情景运行尚未执行；其后 15 条 scenario 运行已通过 --charge-catalog/--charge-scenario 正式读取本目录（manifest 见 results/scenario_manifest.json，15/15 exit 0）。因此 §C11/C13/G2 的“未接线”仅指第三轮 64 条正式命令，不是第四轮现状；接线证据与限制见 WIRING.md。
