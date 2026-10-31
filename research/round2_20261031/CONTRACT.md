# 第二轮接口契约与文件边界（Lead 统一口径，2026-10-31）

类型: 规范
状态: 生效
负责人: tho25
日期: 2026-10-31

本文件冻结第二轮各工作流的接口、口径和写文件范围。任何跨范围改动先在这里改，再通知 Lead。

## 1 权威成本入口（R2-D1/D2）

1. costs.py 提供**唯一**设施成本函数：

       facility_cost(k, cost_params, *, days) -> {
           "value": float|None,          # 设备资本 + 设备维护 + 站级固定（可算时）
           "items": {"device_capital":..., "device_maintenance":..., "facility_fixed":...},
           "missing": [...],             # 缺参 -> value 为 None
           "not_applicable": [...],      # k=0 时不适用而非缺失，值为 0.0
       }

   口径：device_capital = k × (depreciation_capex / depreciation_life_years) × days；
   device_maintenance = k × maintenance_per_bay_day × days；站级固定成本来自
   cost_params["facility_fixed_cost_per_day"]（有来源才可填），与设备成本分列。
2. CostLedger.summary 的 operator_capital_depreciation 必须乘 equipped_bays；经营区间按
   days = elapsed_min / 1440 精确换算，报告同时给"窗口口径"与"折算日口径"。
3. occupancy_minutes(sim) 三类严格分列：no_charging_demand（仅 EV 且无充电需求占带枪位）、
   overstay_after_complete（充完仍占）、ice_blocking_connector（油车占带枪位）。旧字段
   no_charging_demand 不再混入油车；旧键保留为 deprecated 并写迁移说明。
4. runner/分析脚本不再自算设施成本，统一调用 costs.facility_cost；runner 的旧字段
   facility_cost 保留同值输出并加 source="costs.facility_cost"。
5. 零设备与缺参分开：k=0 的资本/维护为 0.0 且进 not_applicable；缺参才是 None。

## 2 车流与需求能量（R2-D3/D4）

1. traffic_gen 生成的是**真实需求**能量：Arrival.energy_kwh = 该次停车真实需要的 kWh，
   不得用 min(需求, 可交付) 截断；理论所需时间 required_min = energy_kwh / (charger_kw×efficiency)。
2. meta 必须分列：demand_energy_kwh_total、theoretical_service_min_total、initial_occupancy_n、
   warm_start_method、length_biased=True/False。
3. 暖启动统一为平稳长度偏置：先按长度偏置抽样 D（P(D)∝D·f(D)；混合分布按各分量均值加权），
   再抽 age~U(0,D)，remaining = D−age。校验：两点分布{1,9}等权 -> E[剩余]=E[D²]/(2E[D])=4.1 min。
4. 期初车辆不是 t=0 新到达：meta 标记 initial_occupancy_n；runner 不得把期初车计入窗口内新需求。
5. 长停允许跨窗口；期末在场的剩余需求单列 pending，不算最终失败。
6. 修改后必须固定外生需求：改变 k/额定功率/馈线功率时，原始需求能量哈希不变。

## 3 整数搜索状态（R2-D5）

allocation.service_level_k(by_k, alpha, *, key="unmet_no_connector_events") 返回：

    {"status": "achieved"|"no_demand"|"budget_exhausted"|"infeasible_upper_bound"|"missing_data",
     "k": int|None, "alpha": alpha, "evaluated_max": int, "baseline": float|None,
     "note": str}

规则：无 k 达标且检查已到硬上限 -> infeasible_upper_bound（k=None，不进均值/MAE/拟合）；
搜索预算用尽但未到硬上限 -> budget_exhausted（k=None）并给出 evaluated_max；
U(0)=0 -> no_demand；缺 k=0 或缺行 -> missing_data；恰在边界达标 -> achieved 且 k=上限（标注 boundary=True）。
另提供 budgeted_service_search(evaluate, alpha, k_initial_max, k_hard_max) 分批扩展枚举。
floor/round/ceil 只作为候选集，最终仍用整数枚举验证非凸目标。

## 4 解析近似（R2-D6/D7）

1. mean_connector_load 默认 occupancy_model="dwell"：connector 占位 = 全部 EV 的停留时长
   （含不充电 EV、充后滞留）；"charge" 模型仅作历史对照并标注不一致。
2. Erlang-B 只作为"稳态、Poisson 到达、无排队、服务时长独立同分布"的近似；报告须写适用条件。
3. 与仿真同 α 对照；预算截断/不可达样本剔除后重算误差；无最低工程约束时允许 k=0。
4. 手算校验用闭式求和（不照抄递推），文档与模块必须一致。

## 5 识别边界（R2-D8/T28）

1. 0.0364 = **观测使用比率代理**（observed charging session ratio），不是"可识别的 p_EV·q_need 真值"；
   字段名改为 observed_charging_session_ratio_v1，status="usage_proxy"，旧名保留 deprecated 映射。
2. 只有 p_EV ≥ z、q = z/p_EV、且 q ≤ 1 的组合才满足乘积约束；q>1 的组合标记 incompatible 并拒绝，
   不截断后参与比较。
3. 官方保有量/新车份额/场站 EV 到访份额分别登记，不混为一谈；存量资料只能作假设性迁移参考。
4. 数据机制限制必须写明：到达为净变化下界、枪状态跳变≠车辆停车事件、准入/功率/重启/缺失/采样影响。

## 6 规则与预测（R2-D9, T29）

1. 观测接口不变：ObservableState 无 needs_charge/能量/真实离场/未来到达。
2. π2 的预测对象可配置 candidates：charge_arrivals | ev_arrivals | connector_load；默认保留
   charge_arrivals 行为，新增对照必须同训练/验证切分，验证集不调参。
3. π2 闸门必须扣除本次已放入的油车占用（空闲位 − 预计 + 已占用），窗口与油车平均占用协调。
4. 隐藏信息测试：可观测历史前缀相同 -> 决策相同；只有发生可观察充电开始/离场后，后续决策才可变。
5. 三规则各自独立重算 k；固定 k 与重选 k 分开报告。

## 7 目录与版本

- 新结果目录：research/round2_20261031/{cost_outcomes,traffic_fix,search_status,rules_v2,multi_window}/；
  每份 JSON 带 meta：源码哈希、参数哈希、git-free 版本标签、运行命令、seed。
- 旧 JSON 不覆盖；新拟合/新模型用 _v2 后缀另存。
- 报告：Lead 统一写 docs/reports/2026-10-31-第二轮修复与复算.md，并给主报告追加更正段。

## 8 工作流归属

| 工作流 | 负责人 | 写范围（只在此内改） |
| --- | --- | --- |
| R2-A 成本与占位 | cost-eng | costs.py、tests/test_costs.py（新建/扩容）、research/round2_20261031/cost_outcomes/ |
| R2-B 车流/能量/暖启动 | traffic-eng | traffic_gen.py、tests/test_traffic_gen.py、research/round2_20261031/traffic_fix/、traffic_generation_20261031/*_v2 |
| R2-C 搜索状态/解析负荷 | search-eng | allocation.py、tests/test_allocation.py、research/round2_20261031/search_status/ |
| R2-D 识别边界/T28 | ident-eng | research/calibration/charging_probability_20261030/*_v2、research/official_data_20261031/identification_20261031/、literature/notes/ 新增笔记 |
| R2-E 规则/预测 | rules-eng | rules.py、prediction.py、tests/test_type_rules.py、research/round2_20261031/rules_v2/ |
| 集成/实验/验收 | Lead | simulation.py/config.py/server.py（如需）、integer_allocation 脚本、报告、TODO/PROGRESS |
