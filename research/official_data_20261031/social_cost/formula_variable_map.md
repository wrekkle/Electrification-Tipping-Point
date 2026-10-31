# 成本公式项 → 变量 → 数据来源 → 可识别程度 → 后端字段映射

类型: 研究数据映射（阶段一 C+D+E）
状态: 草案（本轮官方采集后更新）
负责人: cost-data
日期: 2026-10-31
公式唯一口径: docs/methods/COST-MODEL-V2.md（v2-2026-10-30）
后端字段唯一口径: apps/parking_lab/workbench/costs.py 的 COST_ITEMS / COST_PARAMETER_NAMES（26 项）
本文件不重复公式推导；它只回答「每个公式项由哪些变量构成、变量能否用官方数据识别、落到后端哪个字段」。

## 1 一句话结论

- 后端 11 个成本项由 26 个可配置参数驱动；本轮为其中 5 组补到可核对的官方来源：时间价值（運研所手冊 + CPI 鏈式換算）、95 無鉛油價（能源署/中油歷史牌價）、台電電動車充換電設施電價與低壓電力電價、車用汽油 CO2 係數（69,300 kg/TJ）、法定碳費（沿用既有已核值）。
- 5 组参数仍缺「本地實測」：搜尋/繞行/步行時間、繞行距離、行駛油耗（L/km）、EV 電耗（kWh/km）、EVSE 建置與維護成本；另有 2 项需先定充電時段結構（電價單值）或官方低位熱值（kg CO2/L）。
- 因此完整社会成本（complete=true）本轮仍不可算：任一必要项 null ⇒ 该项 null、total null、complete=false（COST-MODEL-V2 §7；costs.py 的 None 传播）。
- 转移支付（停车费、充电费、罚金、补贴）不进 social_total；设施 capex 与折旧只能取其一（COST-MODEL-V2 §6）。

## 2 后端字段映射总表

| # | COST_ITEMS 成本项 | 公式（COST-MODEL-V2） | 构成变量 | 后端参数字段（costs.py COST_PARAMETER_NAMES） | 本轮官方来源与状态 | 可识别程度 | 进 social_total |
|---|---|---|---|---|---|---|---|
| 1 | user_time（EV/ICE 共用） | v_i·Δt（Δt 为区间并集，勿相加） | v_i；Δt_搜索/绕行/步行 | vot_per_hour；search_min、detour_min、walking_min | v：運研所手冊 表5-6 + 主計總處 CPI（**available**）；Δt：台北无一官方实测（**unidentified**） | v 可识别（需物价年调整）；Δt 不可识别 | 是 |
| 2 | ev_detour_energy | (绕行km × EV电耗 × 电价) + 缺电量 × 替代价差 | detour_km_per_failure、ev_kwh_per_km、ev_energy_price_per_kwh、alternative_charging_delta_per_kwh | 同名参数 | 电价：台電電動車充換電設施電價（**available，费率表**；单值需时段结构）；电耗、价差：未取得（**unidentified**） | 不可完整识别 | 是 |
| 3 | ev_external | 绕行km × 每公里排放成本 | detour_km_per_failure、emission_cost_per_km | 同名参数 | CO2 系数 69,300 kg/TJ **及 2.263132872 kg/L**（available）、低位热值反推 32.657 MJ/L；仍缺每公里排放系数或 L/km/kWh·km → null | 部分可识别，未连通 | 是 |
| 4 | ev_residual_trip_loss | 缺电量 × 单位缺电损失 | shortfall_kwh、residual_trip_loss_per_kwh | 同名参数 | 无官方值；不得以售电价代替（COST-MODEL-V2 §7） | 不可识别 | 是 |
| 5 | ice_vehicle_operating | 绕行km × 油耗L/km × 油价 | detour_km_per_failure、fuel_l_per_km、fuel_price_per_l | 同名参数 | 油价：95無鉛 2026 初至 9 月底 31.7385 TWD/L（**available**）；行驶油耗 L/km 未取得（能源署油耗指南 403 WAF；手册动态能耗系数附表未含于 PDF；怠速 0.82 L/h 已有） | 部分可识别 | 是 |
| 6 | ice_external | 绕行km × 每公里排放成本 | detour_km_per_failure、emission_cost_per_km | 同名参数 | 同 #3（CO2 kg/L 已有；缺 L/km 与污染物分项） | 部分可识别 | 是 |
| 7 | ice_activity_loss / ev_activity_loss | 放弃活动时的一次性机会损失 | activity_loss_per_failure | 同名参数 | 无官方值；触发条件为「放弃活动」（COST-MODEL-V2 §4） | 不可识别 | 是 |
| 8 | operator_capital_depreciation | 年金/365 或 capex/寿命/365（二者取一） | depreciation_annual 或 depreciation_capex + depreciation_life_years | 同名参数 | **Lead 追加后**：官方额度锚点（慢充 8 万元/枪、快充 200 万元/枪，available/sensitivity_only）+ P26 可追溯换算 `evse_annual_cost_TWD_per_connector_2026_transferable`=27,483.40 TWD/枪·年（transferable/scenario，非台北实测）；寿命/折现率仍无官方值 | 可条件化识别（非本地实测） | 是（按 transferable/scenario 使用） |
| 9 | operator_energy | 充电量 kWh × 电价 | electricity_price_per_kwh | 同名参数 | 台電费率表已取得；单值取决于充电时段结构（**unidentified as scalar**） | 费率可识别、单值不可识别 | 是 |
| 10 | operator_maintenance | 按枪·日 或 按 kWh | maintenance_per_bay_day、maintenance_per_kwh | 同名参数 | 无官方值（**unidentified**） | 不可识别 | 是（「位」=带枪设备位，见 §6） |
| 11 | occupancy_impact（attribution） | 配对反事实差值 | 同流两跑的 ΔC；不乘罚价 | 无单一价格参数；依赖 #1–#10 + relocation_cost_per_move | 无需新价格，但依赖上面未识别项；挪车代价 null | 归因可定义、数值不可算 | **否**（只进 attribution） |
| 12 | transfers：parking_fee / charging_fee / fines / subsidies | 收费/罚金/补贴 | parking_fee_per_hour、charging_fee_per_kwh、fine_per_event、subsidy_per_session | 同名参数 | 停车费：台北市费率页未取得（**unidentified**）；充电费：官方费率页未取得（**unidentified**） | 转移支付，不阻塞社会成本 | **否** |
| 13 | relocation（挪车代价） | 移车人力/时间/风险 | relocation_cost_per_move、relocation_km_per_move | 同名参数 | 无官方值；缺参时整项 null，禁止假设 0 | 不可识别 | 是（若触发挪车） |

补充：emission_cost_per_km 不是「价格」，而是 (CO2 kg/km × 碳价) 与空气污染物单位损害之和；本轮只补齐了 CO2 系数（kg/TJ）与法定碳费（仅可作敏感性），未补齐污染物系数与 kg/L 换算。

## 3 十二项 null 的逐项处置（对应 parameters.json 的 missing_parameters）

| parameters.json 项 | 本轮官方采集结果 | 新状态 | 进入完整社会成本? |
|---|---|---|---|
| gasoline_retail_price_TWD_per_liter | 能源署/中油「汽柴油參考零售價」API，2025-01-06～2026-09-28 共 91 笔周价；95無鉛 2026 年初至 9 月底均值 31.7385 TWD/L（2025 全年 29.1577；近12月 30.9212） | **available** | 是（还缺 fuel_l_per_km） |
| electricity_price_TWD_per_kWh | 台電《簡要電價表》電動車充換電設施電價：離峰 2.90（非夏月）/3.05（夏月）元/度；尖峰 12.14/12.47；低壓電力非時間電價 3.87/4.08 | **available（费率表）/ unidentified（单值）** | 否（单值需时段结构），费率可作敏感性 |
| ev_energy_consumption_kWh_per_km | 未取得机型别能耗测试值 | **unidentified** | 否 |
| co2_emission_factor_gasoline_kg_per_liter | 環境部 113-02-05 公告「溫室氣體排放係數」附表一：車用汽油（移動燃燒）CO2 = 69,300 kg/TJ；文件中无 kg/L 与低位热值 | kg/TJ **available**；kg/L **unidentified** | kg/L 不可用前，排放成本不通 |
| parking_search_time_minutes（台北） | 交通部統計查詢網「自用小客車在居家附近之尋找停車位時間及停車費」页已落盘，但数值在查询表单/图表接口，本轮未取到台北数值；Shoup 8.1 分钟为外地路边停车，不可当台北值 | **unidentified** | 否 |
| detour_distance_km | 无官方实测；任务禁止以直线距离替代 | **unidentified** | 否 |
| substitute_parking_walk_time_minutes | 无官方统计 | **unidentified** | 否 |
| substitute_charging_price_delta_TWD_per_kWh | 依赖替代站与目标站单价，两端均未取得 | **unidentified** | 否 |
| relocation_cost_TWD_per_event | 无官方值 | **unidentified** | 否（缺参时该项 null） |
| parking_fee_rate_TWD_per_hour | data.taipei 费率资源返回 0 字节；pma.taipei.gov.tw 前轮已连不上 | **unidentified**（转移支付） | 不阻塞 |
| evse_capex_TWD_per_connector | 政府電子採購網/補助要點本轮未取得可核对的单枪决标价 | **unidentified** | 否 |
| depreciation_annual_per_connector | 缺 capex、寿命、折现率三项输入 | **unidentified** | 否 |

## 4 三类分级（交付判定口径）

**A. 可进入完整社会成本（有官方来源且已连通到后端参数）**
- vot_per_hour（2026 年幣值，主值 6.7771 TWD/(車·分) = 406.63 TWD/h；下端 CPI 鏈 4.5282 = 271.69 TWD/h；城際 8.6629）。
- fuel_price_per_l（95無鉛，2026 年初至 9 月底均值 31.7385 TWD/L）。
- electricity 费率表（電動車充換電設施電價，离峰/尖峰分时）——可用于按实际充电时刻结算，但不给出单一均價。
- CO2 排放系数 69,300 kg/TJ 与 2.263132872 kg/L（含低位热值反推 32.657 MJ/L，Lead 追加后已可进 per-liter 成本）。
- carbon_fee（300 TWD/tCO2e）——来源已核，但按研究判断只能作敏感性（法定碳費≠边际社会碳成本）。

**B. 仅能敏感性 / 情景（既有官方结构但缺本地情景参数，或来源只支持机制）**
- 电价单值（需先声明充电时段结构；本轮给「非夏月离峰 2.90」仅为 scenario，is_scenario=true）。
- 碳费用于车辆排放（建模类比，只能敏感性）。
- 油车怠速油耗 0.82 L/h（官方，但只覆盖停等，不覆盖绕行行驶）。
- P26/Biswas 的美金成本与罚金（外地情景，禁止汇率搬用）。

**C. 不可识别（本轮判 null，并列候选来源）**
- 台北寻找/绕行/步行时间、绕行距离、行驶油耗 L/km、EV 电耗 kWh/km、替代补能价差、缺电损失、活动损失、挪车代价、EVSE 本地采购价（现值换算为 LA 论文的 transferable/scenario）、停车费与充电费（转移支付，不阻塞社会成本）、空气污染物单位损害。
- 注：EVSE 年化成本（27,483.40 TWD/枪·年）属 transferable/scenario，不是本地实测识别值；官方额度锚点为慢充 8 万元/枪、快充 200 万元/枪（2022 币值）。

## 5 missing_parameters 如何导致「完整社会成本不可算」

costs.py 的实现与 COST-MODEL-V2 §7 一致：_param() 对 null 返回 None；任一乘数/加数为 None ⇒ 该成本项为 None；cost_report 汇总时 total=None；同时把缺失参数名放进 missing_parameters，complete=false，界面显示「无法完整计算／待校准」。

本轮补齐后仍必然为 null 的项：user_time（Δt 缺）、ev_detour_energy、ev_external、ev_residual_trip_loss、ice_vehicle_operating（油耗缺）、ice_external、两种 activity_loss、operator_capital_depreciation、operator_energy（单值缺）、operator_maintenance。也就是 11 个 COST_ITEMS 中没有任何一项可以独立算成完整数值；即使把已取得的官方值全部代入，total 仍为 null。可计算的只有「给定 Δt/距离/能耗等情景输入的参数化结果」，必须标注为条件化情景（CONTRACT §8、§11）。

## 6 与配桩公式 C(k;π0) 的关系

C(k;π0)=设施分摊成本(k)+E[用户额外社会成本(k;π0)]+运行资源成本(k;π0)（CONTRACT §8）。
- 设施分摊成本 ⇐ operator_capital_depreciation（缺 EVSE capex/寿命/折现率）+ operator_maintenance（缺）。
- 用户额外社会成本期望 ⇐ #1–#7、#11-#13，全部依赖 Δt/距离/油耗/电耗/排放终端参数。
- 运行资源成本 ⇐ operator_energy（电价费率有、单值缺）+ 功率/枪资源约束（不属于价格参数）。
结论：k* 与 PPR 本轮只能给「条件化情景最优」，不能宣称完整社会成本最优桩数（COST-MODEL-V2 §7；CONTRACT §8、§11）。

## 8 六项不可识别参数：一句话结论与阻塞项（Lead 2026-10-31 追加）

| 参数 | 结论（是否存在该类量/为何未取得/可用的敏感性区间类型） | 阻塞哪一项完整社会成本 |
|---|---|---|
| parking_search_time_minutes | 部分存在：交通部「自用小客車使用狀況調查」有寻找停车位时间题项（Seq=810 页已落盘），但数值在互动接口未取得；敏感性只能用「外地文献均值类」作上界/对照，不得当台北实测。 | user_time |
| detour_distance_km | 部分存在：无台北官方统计；只能用「路网系数假设类」（需来源）或 GPS 实测类，任务禁止以直线距离替代。 | ev_detour_energy、ev_external、ice_vehicle_operating、ice_external |
| substitute_parking_walk_time_minutes | 部分存在：无官方调查值，需先界定替代场选择行为；敏感性用「距离/步速推算类」（需先有距离来源）。 | user_time（步行段） |
| residual_trip_loss_per_kWh | 不存在：无官方/共识文献值，COST-MODEL-V2 明示不得用售电价代替；只能用 WTP 调查类或行程重排成本类作情景。 | ev_residual_trip_loss |
| activity_loss_per_failure | 不存在：无官方值，需旅次目的与活动价值资料；敏感性用「旅次目的价值推算类（工资率×时长）」或问卷 WTP 类。 | ice_activity_loss、ev_activity_loss |
| relocation_cost_TWD_per_event | 不存在：无官方值；敏感性用「营运人力成本推算类」或代客移车服务价类；无依据时禁止假设零成本。 | occupancy_impact 的挪车分支（不可行时该分支回「无法计算」） |

区间类型只说明「可用哪一类证据」，本文件与 candidates JSON 都**不给数值区间**；任何数值进入模型前必须另立带来源的 scenario 参数。

## 7 维护约定

- 参数值、来源与状态以 research/cost_model_20261030/parameter_candidates_20261031.json 为准；本文件只维护映射关系。
- 新增官方来源后：先落盘 + sha256 + manifest，再改 candidates 的 value/status，最后更新本表「本轮状态」列。
- 不改 parameters.json（历史冻结）；后者由 Lead 的 parameter_registry 合并 candidates。
