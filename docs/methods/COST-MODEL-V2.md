# 成本模型 v2（论文工作稿与后端统一口径）

状态: 生效

适用：\`paper/draft/\` 工作稿成本章节；\`apps/parking_lab/workbench/\` 成本计算、配置、导出、界面。
不适用：\`main_paper/\`（冻结稿）、\`experiments/prei/\`、\`research/electrification/\`（v1 历史证据，只读）。
下列公式是结合文献提出的建模框架，非某篇论文的公式；引用只支撑机制与适用条件。

## 1 符号与单位

$v_i$ 时间价值（TWD/h）；$\Delta t_i$ 相对基准的额外耗时（内部小时，可分钟输入）。
$\Delta C_{\text{行驶与补能资源},i}$ 额外行驶能耗与替代补能；$\Delta C_{\text{外部影响},i}$ 额外排放/拥堵外部性；$L_{\text{剩余行程损失},i}$ 剩余行程无法完成的损失。
$\Delta t_{\text{搜索}}/\Delta t_{\text{绕行}}/\Delta t_{\text{步行}}$ 各段耗时；$\Delta C_{\text{车辆运行},i}$ 绕行/怠速油耗；$L_{\text{活动损失},i}$ 活动机会损失。

## 2 电车无法获得所需充电服务

$$c_i^{EV}=v_i\Delta t_i+\Delta C_{\text{行驶与补能资源},i}+\Delta C_{\text{外部影响},i}+L_{\text{剩余行程损失},i}$$

## 3 油车无法停车

$$c_i^{ICE}=v_i(\Delta t_{\text{搜索},i}+\Delta t_{\text{绕行},i}+\Delta t_{\text{步行},i})+\Delta C_{\text{车辆运行},i}+\Delta C_{\text{外部影响},i}+L_{\text{活动损失},i}$$

## 4 基准与重复计费

正常服务基准 = 有可用车位、电车按额定功率充到所需电量、无额外搜索/绕行/步行；基准不计入 $\Delta$。
搜索与绕行重叠只计一次（区间并集），不得相加。
电车停车失败也有停车损失，已计入 $c_i^{EV}$ 的 Δt 不得再单列；充电失败用 \`ev_residual_trip_loss\`，停车失败活动损失单列 \`ev_activity_loss\`（同 \`ice_activity_loss\` 参数）。同一用户同一时段只允许一条失败行（重复抛错）。
被拒车辆不得凭空消失，须落到绕行离开/替代位/放弃出行之一。

## 5 占桩影响：配对反事实

$$\Delta C_{\text{占桩影响}}=C_{\text{允许该段占位}}-C_{\text{及时释放充电资源}}$$

两侧外生输入完全相同、除干预段外规则相同；须比对 \`traffic_hash\`，哈希不等即拒绝差值，仅同 seed 不算证据。
原因 6 类：\`no_charging_demand\`、\`overstay_after_complete\`、\`dispatch_defer\`、\`insufficient_power\`、\`equipment_failure\`、\`ice_blocking_connector\`（2026-10-31 第三轮更正）。
资源分开记：\`power_released\`(kW)、\`connector_released\`(枪口)、\`charged_bay_released\`(带枪位)、\`ordinary_bay_released\`(普通位)。
挪车须先有空闲普通位并保留原定离场时间；无普通位返回“无法计算”。挪车代价无依据即 null（分项与完整成本差都为 null 并进缺失清单），不得假设零成本。
占桩差值只作归因展示，存 \`attribution\` 不进 \`total\`；后续等待/绕行/未满足损失已入总成本时不得再加罚金。
2026-10-31：油车占枪单列 ice_blocking_connector；no_charging_demand 仅 EV 无需求。

## 6 成本边界

用户资源成本（时间、额外能耗、外部影响、活动损失）与运营成本（折旧分摊、购电、维护）进 \`social_total\`；capex 与折旧只能取其一。
\`maintenance_per_bay_day\` 的"位"=带枪设备位（chargers 数量），计算须乘设备数；若为全场总额须改名，不得两口径混用。
2026-10-31：facility_cost 为唯一入口；k=0→0.0/not_applicable；站级成本单列。
资本/维护 = 设备数 k × 单位日成本 × 天数；单位日资本 = 年折旧/365 或 capex/寿命年/365；天数 = elapsed_min/1440（严禁漏乘 k 或漏除 365）。
收费（停车费、充电费）与罚金/补贴归 \`transfers\`，占桩影响归 \`attribution\`，三者都不进 \`social_total\`。

## 7 未知值传播（硬规则）

缺参一律 \`null\`：禁止填 0、禁止套演示默认值、禁止为跑通补数。
任一必要参数 null ⇒ 该项 null、\`complete=false\`、总成本显示"无法完整计算"，并输出可计算分项与 \`missing_parameters\`。
实时累计（占用、费用）只算到当前仿真时刻，预计最终值单列为预测；离场仍缺电车辆的后续时间与绕行未知，不得隐含为零。
界面显示"未知／待校准"；JSON 保 null、CSV 留空并附口径列。
按辆固定拒绝费与按缺电量罚价属 v1 演示默认值，须重核来源；核对不到即 null。缺电损失不得用售电价代替。

## 8 时间与状态语义

停车余位变化只反映**净占用变化**，不等于到达或离场；同一间隔可同时有进有出，不得反推逐车标签。
逐枪"待机"不等于空位、无充电需求或充完未走；到达率、停车时长、车型比例、充电意愿、拒绝需求未识别即 unknown。
合成实验须标 \`synthetic\`；期末仍在场待交付电量 ≠ 离场失败；无充电需求的电车不产生充电失败损失。

## 9 版本

\`COST_MODEL_VERSION="v2-2026-10-30"\`；旧结果保留原字段并标 \`v1-legacy\`，不批量改写。导出与界面必须显示版本。

## 10 词表与接口

三组名单以 \`apps/parking_lab/workbench/costs.py\` 的 \`COST_ITEMS/ATTRIBUTION_ITEMS/TRANSFER_ITEMS\` 为准（含 \`ev_activity_loss\`）。
\`occupancy_impact\` 归因不进 total；\`parking_fee/charging_fee/fines/subsidies\` 转移支付不进 total。
入口：\`traffic_hash(exogenous_events)\`、\`paired_occupancy_counterfactual(base_run, interrupt)\`。

## 11 算例要求

可手算算例：给定 $v_i$、Δt、能耗与排放系数、替代补能价差，人工算分项并测试断言；覆盖重复计费拒绝、充完未走、无竞争需求、零功率、期末未离场、占桩反事实（哈希等/不等）。
