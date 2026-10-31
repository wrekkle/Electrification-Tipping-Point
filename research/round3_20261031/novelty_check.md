# R3 定向查新（novelty check）

类型: 查新记录
状态: 生效
负责人: ev-data
日期: 2026-10-31
检索工具: web_search + web_fetch（未绕过任何访问控制；ScienceDirect 返回 403 时不重试、不伪造摘要）

## 1 查询（4 条，原样记录）

1. shared EV charging infrastructure instead of adding chargers parking joint operation
2. parking and EV charging joint investment business model parking operator
3. electric vehicle charging station siting robust optimization demand uncertainty
4. charging pile allocation parameter uncertainty simulation parking demand

## 2 命中与相关性

| # | 题名 | 作者/机构 | 出处（年） | DOI/URL | 获取状态 | 相关性 |
|---|---|---|---|---|---|---|
| N1 | Joint operation strategy of parking and charging infrastructure | Chen F., Pavlov V., Zhao S., Feng J., Xu S.X. | Transportation Research Part D, 144, 104773 (2025-07) | https://doi.org/10.1016/j.trd.2025.104773 | 机构库（BIT）页 + 摘要已读 | 高：充电桩共享改变供应链，停车运营商三种建桩策略（第三方代建 P / 自建 D / 共建共享 C），博弈与议价 → 直接压"共享运营替代增桩"的新颖性 |
| N2 | Electric vehicles shared charging and parking: A reservation-based dynamic rolling allocation framework considering unpunctuality | 未取得（ScienceDirect 403） | Transportation Research Part C (2025) | https://www.sciencedirect.com/science/article/abs/pii/S0968090X25002633 | 仅题录；摘要未取得（UNVERIFIED） | 高：共享充电+停车、预约与不准时下的动态分配 |
| N3 | Two-stage distributionally robust optimization of EV charging stations under demand and disruption uncertainties | 未取得（ScienceDirect 403） | Socio-Economic Planning Sciences (2026) | https://www.sciencedirect.com/science/article/abs/pii/S003801212600176X | 仅题录；摘要未取得（UNVERIFIED） | 中高：需求与中断不确定性下的两阶段分布鲁棒配置 |
| N4 | Robust Electric Vehicle Charging Station Planning Factoring Traffic Congestion Dynamics Adapting to Steady and Surging Charging Demand Increase | TRID 记录（作者未核） | TRID 2696172；期刊/年/卷期未核（UNVERIFIED） | https://trid.trb.org/View/2696172 | 摘要部分可读（TRID） | 中：稳健规划、拥堵传播与需求激增 |

另：中文招标公告"开平市城区公共区域停车泊位与新能源汽车充电基础设施建设项目运营"仅说明联合运营实践存在，非学术来源，不登记；专利 US11488474（共享充电相关）未核，不登记。

## 3 对论文新颖性的影响（必须处理）

- **"共享运营/共建共享替代增桩"不能声称空白**：N1 已给出三种建桩策略（P/D/C）与博弈分析，且明确"charging pile sharing transforms the structure of the supply chain"。本项目需引用 N1 并写清差异：本项目是**离散/整数配桩 + 服务水平规则 + p_EV 不可识别下的情景仿真**，不是供应链定价/议价模型；不能把 N1 的结论当作本项目贡献。
- **"停车-充电联合投资/运营"已被 N1 覆盖**（标题即 joint operation）；N2 进一步覆盖"共享充电+停车预约分配"，本项目若提"共享停车位与共享充电桩协同"必须引用并区分。
- **"参数不确定性下的配置"已有 N3（DRO）与 N4（稳健规划）**：本项目的 p_EV 不可识别 + 可行域敏感性只能表述为"情景分析/识别边界"，不能表述为"首次处理不确定性"；需引用 N3/N4，并说明本项目没有鲁棒优化保证。
- 结论：本轮查新把"首次/空白"类表述全部降级为"需引用并区分"；论文贡献应落在**观测识别边界（0.0364 只是 usage proxy）+ 可复算的整数配桩/规则仿真 + 多日数据审计**，而不是共享运营本身的新颖性。

## 4 待登记文献（本轮未写 literature/）

| 建议编号 | 文献 | 可写笔记? |
|---|---|---|
| M18 | N1 Chen et al. 2025, TR-D 144:104773 | 摘要已读，可写摘要级笔记 |
| M19 | N2 shared charging & parking (TR-C 2025) | 需先取得摘要（当前 403，UNVERIFIED） |
| M20 | N3 DRO 2026 (SEPS) | 需先取得摘要（当前 403，UNVERIFIED） |
| — | N4 TRID 2696172 | 期刊/年/DOI 未核，暂缓 |

**未登记原因**：本轮写权限仅 research/round3_20261031/，不能改 literature/notes、reading-log.json、index.json/INDEX.md；按 literature 流程应由 Lead/授权人补笔记并跑 python scripts/lit_index.py --write。

## 5 未验证与访问限制

- ScienceDirect 两篇（N2/N3）返回 HTTP 403，仅拿到题录 URL，摘要与作者未核 → UNVERIFIED。
- N4 的期刊、卷期、年份、DOI 未核（TRID 页只给记录号）→ UNVERIFIED。
- N1 的摘要来自 BIT 机构库页（非出版社 PDF）；引用前建议核出版社版本页码/式号。
- 检索只覆盖公开 Web（无 Scopus/Web of Science 账号），不能据此宣称"穷尽检索"。
