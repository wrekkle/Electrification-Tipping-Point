# R3-F 成本口径独立复核（cost-eng，2026-10-31）

类型: 研究记录（第三轮独立复核）
状态: 完成
负责人: cost-eng
范围: 只读复核 apps/parking_lab/workbench/costs.py 的 depreciation_daily / facility_cost 与 docs/methods/COST-MODEL-V2.md 口径写法；不改源码、不改 docs。写权限内仅本文件与 cost_audit.py。
任务: task-11（R3-F 成本口径独立复核）。

## 1 结论

- **数值核对 95/95 PASS，EXIT=0**：depreciation_daily 两条路径（annual/365、capex/寿命/365）与 facility_cost 的分项拆分、k=0 归 not_applicable、缺参 None 传播，均与独立手算逐项一致；**未发现数值差异或口径实现错误**。
- **文档缺口 5 项**（见 §4）：COST-MODEL-V2.md 未写明"年折旧/365"、capex/寿命/365、days=elapsed_min/1440 换算，且 §5 仍写"原因 5 类"而代码为 6 类（含 ice_blocking_connector）。这些是文档缺口，不是代码缺陷；更正建议见 §4，属 Lead 文档范围。
- 审计脚本自身出过一次手算错误（把 k=3×days=1.5 误算成 9 而非 4.5），已修正重跑；这正好说明期望值确实由独立算术构造，而不是照抄实现。

## 2 复核方法与命令

期望值不用被测模块的算术：全部用 Python fractions.Fraction 按定义式直接构造，再与 costs 的 float 输出比较；判定 isclose(rel_tol=1e-12, abs_tol=1e-12)。

    python research/round3_20261031/cost_audit.py
    -> EXIT=0；输出"数值核对: 95/95 PASS, 0 FAIL"；DOC_GAPS: 5

覆盖：
1. depreciation_daily：annual=365000 / annual=146000.5 / capex=3650000+life=10 / capex=116792.62+life=10；只给 capex 缺 life；两者都不给；annual 与 capex 同给（ValueError）。
2. facility_cost：capex 路径整数天；annual 路径小数天 0.375；capex 路径跨日 2.75 天 + 站级固定 100/日；annual 路径 1.5 天 + 站级固定显式 None；k=0（参数齐全 / 参数全缺 / 给了站级固定）；k>0 缺维护 / 缺资本；items 键集合；输入边界（k=-1、k=1.0、k=True、days<0、nan、inf、字符串）。
3. 账本交叉核对：elapsed_min=1440/720/900/2160 四种窗口，summary 的资本=2000×days、按位维护=40×days，且与 facility_cost 同值（确认唯一入口）。
4. 文档写法扫描（§4）。

## 3 关键对照表（完整 95 行由脚本输出）

| 类别 | 检查项 | 独立手算 | costs 实际 | 结论 |
| --- | --- | --- | --- | --- |
| dep | annual=365000 → 日成本 | 365000/365 = 1000.0 | 1000.0 | PASS |
| dep | annual=146000.5 → 日成本 | 146000.5/365 = 400.001369863014 | 400.001369863014 | PASS |
| dep | capex=3650000, life=10 → 日成本 | 3650000/10/365 = 1000.0 | 1000.0 | PASS |
| dep | capex=116792.62, life=10 → 日成本 | 116792.62/10/365 = 31.997978082192 | 31.997978082192 | PASS |
| dep | 只给 capex 缺 life | None + missing=[depreciation_life_years] | 同左 | PASS |
| dep | annual 与 capex 同给 | ValueError | ValueError | PASS |
| facility | capex 路径, k=2, days=1 | capital 2000 / maint 40 / fixed 0 / value 2040 | 2000 / 40 / 0 / 2040 | PASS |
| facility | annual 路径, k=1, days=0.375 | capital 750 / maint 4.6875 / value 754.6875 | 750 / 4.6875 / 754.6875 | PASS |
| facility | capex 路径, k=4, days=2.75, 固定100/日 | capital 351.977758904110 / maint 476.296684931507 / fixed 275 / value 1103.274443835616 | 同左 | PASS |
| facility | annual 路径, k=3, days=1.5, 固定显式 None | capital 1800 / maint 22.5 / fixed None / value None + missing | 同左 | PASS |
| facility | k=0, 参数齐全 | capital 0 / maint 0 / fixed 0 / value 0; not_applicable=[device_capital, device_maintenance] | 同左 | PASS |
| facility | k=0, 参数全缺 | value 0.0，missing=[]（零设备不是未知） | 同左 | PASS |
| facility | k=0, 固定成本=100/日, days=0.25 | 设备 0；fixed=25；value=25（站级与 k 无关） | 同左 | PASS |
| facility | k>0 缺维护 / 缺资本 | 对应项 None、value None、missing 列名 | 同左 | PASS |
| ledger | elapsed=1440/720/900/2160, k=2 | 资本 2000/1000/1250/3000，维护 40/20/25/60 | 同左，且与 facility_cost 同值 | PASS |

## 4 文档缺口与更正建议（COST-MODEL-V2.md，Lead 范围，本单未改）

| # | 缺口（实测） | 建议更正 |
| --- | --- | --- |
| 1 | 未出现 365：全文没有"年折旧/365"或"每年÷365"的日摊规则 | §6 补：annual 是每年折旧额，日折旧 = annual/365 |
| 2 | 未写 capex/寿命年/365 公式（仅写"折旧分摊"） | §6 补：device_capital = k × (depreciation_capex / depreciation_life_years / 365) × days |
| 3 | 未写 annual/365 的另一条路径及二者互斥的表述落到公式层 | §6 补：device_capital 亦可用 k × (depreciation_annual/365) × days；annual 与 capex 只能取其一 |
| 4 | 未写 days = elapsed_min/1440 的窗口→日换算（§1 只列 accounting_period 枚举） | §6 补：days = elapsed_min / 1440；per_hour 报表另除 24，不得重复乘 |
| 5 | §5 写"原因 5 类"，代码 OCCUPANCY_REASONS 为 6 类（R2-D2 起含 ice_blocking_connector；§5 第 41 行只补了一句说明） | §5 把清单改为 6 类并写明 no_charging_demand 仅 EV、ice_blocking_connector 为油车占带枪位 |

建议在 §6 直接增加一段（公式用文字或行内公式均可）：

    device_capital = k × (depreciation_capex / depreciation_life_years) × days
                  或 k × (depreciation_annual / 365) × days     （二者互斥）
    device_maintenance = k × maintenance_per_bay_day × days
    facility_fixed = facility_fixed_cost_per_day × days          （站级，不乘 k）
    value = 三者之和；k = chargers；days = elapsed_min / 1440
    k = 0 → 设备资本/维护为 0.0 且 not_applicable；缺参 → 该项 None、value None
    未提供 facility_fixed_cost_per_day = 不纳入本次核算（0.0）；显式 None = 缺参

另建议在 §10 接口段写明 facility_cost 为唯一设施成本入口，账本/runner/分析脚本不得再乘设备数或天数（保证单一入口可审计）。

## 5 边界观察（非缺陷，建议文档或调用方知悉）

1. depreciation_daily 在 life=0 直调时抛 ZeroDivisionError（非 ValueError）；Config.parse 已拒绝 life<=0，正常链路不可达，故不作为缺陷。若要防御式错误信息，可在函数内先校验。
2. depreciation_daily/facility_cost 不校验负数（负 annual/capex/life/maintenance 会算出负成本）；当前由 Config 的 COST_BOUNDS 承担校验，直接传原始 dict 的调用方需自知。
3. k=0 且给了站级固定成本时 value = facility_fixed × days（>0）：这是"站级成本与设备数无关"的设计结果，与"零设备零成本"并不矛盾，建议文档写清以免误读。

## 6 未验证项（UNVERIFIED）

- 未运行全量业务测试（unittest discover），未验证 UI/cost_csv 导出字段与本口径的展示一致性（任务范围外）。
- 未人工逐位复算浮点末位 bit：判定依赖 isclose(1e-12)，脚本 stdout 为唯一证据。
- docs/methods/COST-MODEL-V2.md 未改（Lead 范围）；§4 只是建议文本，未提交文档改动。
- 未核对 COST_MODEL_VERSION 是否应因口径写清而升版（Lead 决定）。

## 7 产物与哈希

- 本目录 cost_audit.py：可重复运行，EXIT=0 即 95/95 通过；sha256 前16 = fff492cd67f3bdca（完整值见回报消息）。
- cost_audit.md（本文件）的 sha256 前16 见回报消息（文件无法自包含自身哈希）。
- 只读依赖：apps/parking_lab/workbench/costs.py（未改，当前 sha256 前16 见回报）、docs/methods/COST-MODEL-V2.md（未改）。
