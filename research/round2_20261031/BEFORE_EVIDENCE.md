# 修复前证据（Lead 复算，2026-10-31）

类型: 研究记录
状态: 生效
负责人: tho25
日期: 2026-10-31

本文件只用**已冻结的旧 JSON 与旧源码/旧报告**取证，不依赖任何正在修改的代码。用于第二轮修复的"修复前失败"证据。

## 证据 1：k=0 仍有设备资本成本（R2-D1）

旧曲线 research/integer_allocation_20261031/outputs/cost_curve_pi0_k40.json 中，共 **54 行** k=0 且
cost_items.operator_capital_depreciation = 31.99797808219178 TWD/窗口（例：TPE0003/TPE0610 seed1/2 k=0）。
k=0 不应有任何设备资本；该值是 rerun 的"整日折旧"未乘设备数。旧报告 §9 已把它记为 U16。

## 证据 2：未达标被伪装成推荐 k（R2-D5）

旧 analysis_pi0.json 中，α=5% 报告 k5=40，但 k=40 时未服务事件占 k=0 基线的比例仍远大于 5%：

| 场站 | k=0 U | k=40 U | U40/U0 | 旧报告 k5 |
| --- | ---: | ---: | ---: | ---: |
| TPE0003 | 21.0 | 8.67 | 0.413 | 40 |
| TPE0110 | 28.33 | 12.0 | 0.424 | 40 |
| TPE0330 | 11.0 | 7.33 | 0.667 | 40 |
| TPE0401 | 12.0 | 0.67 | 0.056 | 40 |
| TPE0575 | 16.33 | 5.67 | 0.347 | 40 |
| TPE1171 | 6.67 | 0.67 | 0.100 | 40 |

共 6 个场站把"枚举上限内不可达"写成了 k5=40，且这 6 个值参与了 §6.2 的中位数与公式拟合。

## 证据 3：请求能量被提前削减（R2-D3）

旧 traffic_gen.py（基线哈希 52dabaad74a6d89b…）_charge_energy 内：
wanted 由需求分布算出后，usable = min(wanted, dwell)，再把 usable 转成 Arrival.energy_kwh。
即"充不完的需求"在进入仿真前已被删掉，后续任何缺口统计都不可能恢复。14 kWh / 7 kW / 停 60 min 的车辆
会被生成为 7 kWh 需求，而不是保留 14 kWh 需求 + 7 kWh 缺口。

## 证据 4：暖启动剩余寿命有偏（R2-D4）

旧口径"从普通停留分布抽 D，再 U(0,D) 取剩余"。两点分布 {1, 9} 等权时：
普通抽样均值 5 min，剩余均值 2.5 min；平稳在场抽样的正确值为 E[D²]/(2E[D]) = (1+81)/(2×5) = 4.1 min。
偏差 39%。旧 traffic_gen 的暖启动（full_dwell + residual）与 runner.warm_start_arrivals 两套实现均有此问题。

## 证据 5：解析占位负荷与仿真语义冲突（R2-D6）

旧 allocation.mean_connector_load：mean_connector_minutes = q_need·mean_charge + (1−q_need)·mean_dwell，
即"有充电需求的 EV 只占枪一个充电时长"。但仿真中充满后不释放带枪位（直到离场），且 π0 下不充电 EV 也占枪。
同一组参数 q_need=0.45、mean_charge=148.5、mean_dwell=952 时两种口径为 510.8 vs 952 分钟，Erlang 负荷差约 1.9 倍。
另外 0.0364 只能用于"全部 EV 占枪"的占位负荷，不能与按充电负荷的公式混用。

## 证据 6：文档手算错误（R2-D7）

旧主报告 §10 写"手算 Erlang-B B(a=1,c=1)=1/3"，模块 allocation.erlang_b(load=1,servers=1)=0.5；
1/3 对应 B(load=0.5, servers=1)。文档与模块不一致，需更正并改用闭式求和独立验证。

## 证据 7：识别边界表述过强（R2-D8）

旧 model_20261031.json 把 0.0364 放在"可识别乘积/identification bounds"语境；
field p_EV_arrival.status = "unidentified"，但模型仍用 0.02 ≤ p_EV ≤ 0.20 网格并给出 q_need = z/p_EV，
其中 p_EV=0.02 时 q_need=1.82 > 1，属于概率上不可行的组合，不应作为"同一乘积"情景参与比较。

## 证据 8：数据只有两日（T31 边界）

research/collection/taipei_372_polling_20261030/data/ 现有目录只有 2026-10-30、2026-10-31 两天；
因此本轮**不能**声称真实多日观测。多窗口实验只能用同一观测段内的不同窗口切分，并标注为"窗口重采样"。
