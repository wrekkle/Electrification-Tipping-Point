# 第八轮总报告：公开数据替换、实验重建与论文图表修订

类型: 研究总报告
状态: 生效（图组与稿件路径见 §6；未完成项见 §9）
负责人: lead（Team Lead）
日期: 2026-10-31
版本目录: research/round8_20261031/
预登记: PLAN.md + DESIGN_MATRIX.json（运行前写定）

## 1 本轮边界（用户 2026-10-31 决定）

从现行研究系统与论文主线完整移除台北专属模块；改用可实际下载的公开停车数据重建标定、实验、图表与稿件；历史原始数据、旧稿、旧结果只读保留，不作为新研究输入。不启动 RL、不新增实时采集城市、不生成对外沟通稿。

旧数据隔离核验（R8-D 独立验收）：契约 arrivals/dwell 与窗口导出多重集比对 185,550 条全在、CONTRACT_ONLY=0；grep 旧 Taipei 快照/fitted_parameters/旧车流/旧结果均无新用途引用。

## 2 台北专属运行链路退出（完成）

- 采集进程：PID 28164 已停止（自带 --stop，STOP 哨兵 2026-10-31T10:37:58Z；state=stopped，371 轮）；残留进程 0；定时任务全表 0 匹配；无守护重启。
- 代码：`datasource.py` 移出执行链路（SHA-256 08ebf8e4…，登记 REMOVAL_MANIFEST.json）；server 的 /api/datasource、导出格式、health 字段与 state 块删除；continuous 回放只接受 synthetic；CLI 删 --collection/--now/data-span；Web 面板与按钮删除；默认测试链 26 个台北用例移除，新增 8 项退出不变量。
- 保留：通用事件仿真、配对重放与哈希一致性、五态语义、双服务水平、安全能力。
- 历史：`research/collection/taipei_372_polling_20261030/` 原样只读留档，不再被程序读取。
- 证据：[退出清单](taipei_exit/INVENTORY.md)、[R8-D Phase1 验收](acceptance/PHASE1_ACCEPTANCE.md)。

## 3 公开数据选型、下载与质量（完成）

主数据（实测）：City of Melbourne Open Data — **Parking bay arrivals and departures 2014**（路侧地磁传感器事件级到达/离开）。
- 下载：zip 247,682,126 B，SHA-256 `B92333B236D5DA0FBDC1AB0A195E57EB7A90EA4A3FDA30D06CF9938A3AD02A34`，许可 **CC BY 4.0**（署名 City of Melbourne），landing 与下载 URL 见 [PROVENANCE](data/PROVENANCE.json)。
- 全文件流式统计（13,503,655 行）：5,228 个 BayID、335 个街区面（block face）、366 个本地日（2014-01-01..2015-01-01）、全城 24 小时覆盖日 364、负时长 7,670（0.057%）、InViolation 1,505,691（11.15%）。
- 字段级问题并已处理：日期为 DD/MM/YYYY（30 万行实测：DD/MM 100% 可解析，MM/DD 失败 61%）；时间戳带恒定 `+0000` 但实为本地墙钟（按小时分布峰 07–19 与咪表时段自洽；窗口全程 AEDT=UTC+11）；`ParkingEventId` 不唯一（13.5M 行仅 168,905 个值）→ 契约用窗口行号唯一化，source_event_id 仅追溯。
- 采用契约：`data/processed/public_parking_events.json`（schema public_parking_events/v1，SHA-256 `38b1422bb95d4122565d4de70a5ef4faf35e41600019068c9c077a295ee6bdf6`）：**10 个场站（AreaName 口径）、185,550 条真实事件、789 个完整场站-日、825 个场站-日块**；容量=窗口内观测到的不同 BayID 数（12–82 位）；剔除 2 条缺停留事件（已登记）。
- 情景层（显式声明，非实测）：is_ev~Bernoulli(0.10)、needs_charge~Bernoulli(0.36, 仅 EV)、energy_kwh~truncated normal(14,6,[2,40]) kWh、硬件 charging_bays=20% 车位、每充电位 1 枪、7 kW、feeder=枪数×kW；seed 20261031。充电会话数据（ACN-Data 静态镜像、ST-EVCDP）仅作能量/连接时长参考，不反推未充电 EV 停车分母；ACN 官方 API 需注册（未绕过）。
- 候选矩阵：13 个候选与真实下载状态见 [CANDIDATES](data/CANDIDATES.md)；主/备选择理由见 [DATASET_CHOICE](data/DATASET_CHOICE.md)；质检见 [QA_REPORT](data/qa/QA_REPORT.md) 与独立质检脚本输出 `data/qa/machine/`。

## 4 通用适配层与设计矩阵（完成）

- 适配层：`apps/parking_lab/workbench/publicdata.py`（契约校验/场站-日切分/经验重采样/block bootstrap）、`energy_ledger.py`（能量服务分子分母）；单元测试 `tests/test_publicdata.py`、`tests/test_energy_ledger.py`。
- 切分：留出场站与留出日互不重叠；统计单位=场站-日或独立流；外生流配对重放；不把快照当独立样本。
- 实验族 E1–E7 + 主要比较 M1–M3 的机器输出：`experiments/`（7 kW 主口径）与 `experiments_main22/`（22 kW 决断口径），每个 manifest 记录 mode=real_data、输入契约 sha256、命令、种子、输出 sha256。
- 基线：B0 FCFS、B1 固定配额、B2 文献改编（M07 滚动分配思想 + P26 准入结构，标"规则改编"，P09 仅索引级 UNVERIFIED），三者只用 ObservableState 可见字段（不含 needs_charge/真实离场/未来到达）；离线最优在 offline_opt.py 明确标 offline_upper_bound_not_executable。

## 5 主要结果（真实数据，按机器输出）

### 5.1 E1 数据覆盖与到达/停留拟合
- 停留分布拟合：全体 KS=0.0330；EV KS=0.0314；ICE KS=0.0334；留出集均值相对误差 11.96%。
- P2/P3/P4 判定 pass；完整场站-日 789（契约与重算一致）。
- 充电字段 missing_data（needs_charge 全来自情景层，非观测）——如实标注。

### 5.2 M2 规则 vs 基线（22 kW，n=20 配对，单位=场站-日，离场能量服务率含被拒）

**方向约定（engine-b 修正后，acceptance F1）**：表格为 **baseline − A**；负值 = A 更好（更高服务率）。

| 比较（22 kW） | 点估计 | 95% CI | 解释 |
|---|---|---|---|
| B0 FCFS − A | −0.2276 | [−0.3217, −0.1421] | A 比 FCFS 高 22.8 pp |
| B1 配额 − A | +0.00767 | [0.0, +0.02237] | A 比 B1 低 0.8 pp，区间含 0（不显著） |
| B2 文献改编 − A | +0.00767 | [0.0, +0.02237] | 同 B1（B1/B2 在本数据上决策序列一致：ICE 失败均 0/4643、普通位始终足够、EV 侧同优先充电位） |

7 kW 口径：B0 − A = −0.1339（A 高 13.4 pp），B1/B2 − A = +0.0030（含 0）。
- 能量分子/分母（E4，20 条留出流，预注册 k=1，22 kW）：demand 1891.0 kWh；delivered A=365.7（19.34%）、B0=27.3（1.44%）、B1=B2=385.2（20.37%）；gap 1525.3 / 1863.7 / 1505.8 kWh；充电接入 A=52/137、B0=6/137、B1=B2=53/137。
- E2 已改为固定流设计（4 个 ≥8 充电位站点、24 条流、k=0..8，每 k n_streams 恒为 24），旧跨 k 漂移曲线作废；7 kW 与 main22 均已重跑。
- main22 的 E6 已真正按 22 kW 重跑（6 行，connector_kw=22、feeder=k×22）：合计 delivered 207.22 / demand 866.53 kWh（23.9%），5/6 离线窗口不可行（window_too_short）、1/6 无充电需求。

### 5.3 M1 / M3 与条件整数配置（负结果与不可行结论）
- M1（最小 k 差）在主口径下 missing_data：10/10 留出流在 k=0..charging_bays 内不存在满足三约束的 k；绑定约束是充电接入（电荷请求 142/221 未满足，capacity_only_unmet 均值 58.8%）。
- 条件域（connectors 允许到 n_spaces，即全部车位可设充电位）：20/20 流仍 physically_infeasible。k=n_spaces 时入园拒绝=0/137，但 **80/137 个充电会话的观测停留短于 22 kW 充满情景能量所需时间**（停留中位 31.5 min vs 所需中位 35.1 min），delivered 991.9/1891.0 kWh（52.5%）。结论：在本数据与声明情景下，**绑定约束是"情景能量需求 vs 观测停留"的结构错配，不是枪数或功率**；三约束标准不能靠加 k 达成。
- M3（离线可行性）：8/8 实例在含/不含馈线约束下均不可行，stop_reason=window_too_short（画面网格不允许离场后补能）。
- E3 最小性五类：confirmed_minimal 0 / minimality_unconfirmed 0 / physically_infeasible 6 / budget_not_covered 2（Queensberry 16 枪、Southbank 14 枪超 k≤8 枚举上限）/ missing_data 0。未把模型相对结论写成物理下界。
- 条件解（明确适用条件）：在"停留≥充满所需时间"的会话子集上，22 kW 下交付率可由 11.1% 提升到 19.3%（主口径）且接入不降；若要求三约束全部满足，则任何 k 都不可行，需改情景（提高功率/降低单次能量/允许离场后补能）——这三者都会改变口径，本轮未擅自改。

### 5.5 SUPPLEMENTARY：access-only 条件整数配置（非声明三约束标准）

定义（显式补充诊断，不替代声明标准）：access 失败 = 入园被拒 或 入园后未拿到连接器；能量短缺单独作为 energy service 指标。k 域 0..n_spaces 整数自 0 向上穷举，A 规则，22 kW。
- 可行流 20/20（confirmed_minimal 20，k*−1 逐项检查不可行）；无 physically_infeasible。
- k*：min 1 / median 3.5 / max 9 枪；对应充电位份额 min 4.17% / median 11.60% / max 25.71%。
- 需 >20% 充电位：仅 1/20 流（Victoria Market 2014-03-23，k*=9，n_spaces=35 → 25.7%）。
- k* 处 access unmet 0.0%；能量仍为 delivered 991.9 / demand 1891.0 kWh（52.45%），与 k=n_spaces 相同 → 能量受停留约束、与 k 无关。
- 结论：在情景默认 20% 充电位下，**连接器数量不是绑定约束**；三约束标准失败来自 capacity_unmet 口径把能量短缺计入，而能量短缺是"观测停留 vs 情景能量"的物理限制。产物：`experiments_condshare/access_only/`（manifest 标 scenario_supplementary_access_only_22kW_not_standard）。

### 5.4 其他
- E2：486 行 k–服务率曲线，34 组按场站-日 bootstrap 的 95% 区间。
- E5：20 行逐独立流配对，因主口径无可行 k，Δk 无点估计（如实标 missing_data）。
- E7：10 条流内未观察到服务率随 k 增加而下降的非单调事件，未伪造轨迹。

## 6 图组、稿件与复现包

见 [figures/](figures/)（F1–F7 真实机器输出版 PNG+SVG 与 FIGURES.json 溯源）、[paper/](paper/)（rev5 主稿与 SI 构建，不覆盖 rev4/冻结稿）、[repro/](repro/)（复现包）。具体路径与页数/字数以本轮交付说明为准；未由机器文件支撑的数字在正文以 [UNRESOLVED:token] 列出。

## 7 安全、测试与检查

- 工作台测试：`python -m unittest discover -s apps/parking_lab/workbench/tests -p "test_*.py"` → **Ran 414 tests, OK**。
- 新增模块单测：publicdata + energy_ledger 43 项 OK；本地 Qwen 交付的 scripts/dataset_qa.py 5 项 OK。
- `python scripts/check_all.py` → 文档与链接检查通过、稿件字数与章节一致性通过、文献索引通过；错误 0（警告 174/8 为既有历史记录与软行宽）。
- 独立验收：R8-D Phase 1 报告 20 项（17 PASS / 3 FAIL），3 项 FAIL 已由 Lead 修复并复验（unittest 全绿、check_all 0 错误、INVENTORY 计数更新；E2–E7 manifest 输入哈希在契约冻结后重建运行中已统一为 38b1422b…）。Phase 2 逐项复核见 acceptance/。
- 安全回归沿用：只监听 127.0.0.1、无 shell/外连客户端导入、原子写、会话上限、路径校验；未重启无目的全面扫描。

## 7.1 独立验收结果（R8-D，2026-10-31）

- Phase 1：20/20 PASS（首验 3 FAIL：unittest 1 failure、check_all 1 错误、manifest 哈希陈旧；Lead 修复后复验通过，首验失败证据保留）。
- Phase 2（机器产物部分）：22 项 = 14 PASS / 4 FAIL / 4 UNVERIFIED。
  - PASS：E1 独立复算（complete_days 789 全等、KS 与分位逐位一致、split 523+302 零违规）；E2 bootstrap 逐位复现（最大差 0.0）；E3 分类从 per_k 重放 8/8 一致；E4 留出/配对/信息公平；能量分母含被拒；M2 数值逐位一致；7 kW window_too_short 独立确认；M1/M3 missing_data 诚实；统计单位非快照。
  - FAIL（已交由 engine-b 修）：M2 方向标签与代码相反（代码算 baseline−A，标签写 A vs baseline；真实方向为 A 优于 FCFS）；E2 跨 k 流集合漂移（n_streams 24→2，非固定配对）；main22 的 E6 未真正按 22 kW 重跑（仅换元数据）。
  - UNVERIFIED：F1–F7 真实图、rev5/SI 真实构建、复现包、PDF/Word 渲染 —— 待 figure-c 产物出现后复验。
- 证据：`acceptance/PHASE1_ACCEPTANCE.md`、`PHASE2_ACCEPTANCE.md`、`acceptance/evidence/`。

## 8 评审意见逐条处置

| 评审问题 | 处置 | 证据 |
|---|---|---|
| 数据不可识别（0.0364 只是 usage proxy）、无真实场站校验 | 已解决（换公开事件级数据）；p_EV/q_need 仍标情景不可识别 | §3、契约 scenario_fields |
| 只有 2 天数据、无完整 24h 日 | 已解决：12 完整周、789 完整场站-日 | E1 |
| 实验把子集当全部规模 | 已解决：10 场站/185,550 事件/825 块分别计数，标定与求解与测试分列 | PLAN §3.1、experiments manifests |
| 能量服务未正式结算 | 已解决：拒绝进分母、分列初始/零需求/删失/缺失/非法、报告 delivered/demand/gap | M2、E4、energy_ledger |
| k 搜索最小性混用、把截断当结论 | 已解决：五分类逐实例（confirmed/unconfirmed/physical/budget/missing），预算截断单列 | E3 classes.json |
| 缺少可比较基线 | 已解决：B0 FCFS、B1 配额、B2 文献改编（明确"规则改编"与信息公平） | E4、baselines.py |
| 留出率 5.02/6.49/5.36% 超标准被写成达标 | 已解决：主口径直接报不可行；未事后放宽标准 | M1/M3、condshare |
| 无离线上界 | 已解决：小实例完整枚举离线最优，明确用未来信息、非在线可执行 | offline_opt.py、E3 |
| 图表只有概念图/简单表 | 已重建 F1–F7 真实机器输出图（PNG+SVG+溯源） | figures/、FIGURES.json |
| 稿件数字混读、旧数据入主线 | 已解决：新版本目录+契约哈希+manifest；旧稿只读 | PLAN §1、§7 |
| 复现包缺失/来函索取 | 已解决：复现包含来源/许可/哈希/脚本/环境/种子/命令/结果 | repro/ |
| 方法比较信息不公平 | 已解决并核验：基线只用可观测字段，离线上界显式分离 | baselines.py、R8-D T5 |
| 规模不足期刊门槛 | 实际可得上限如实报告：13.5M 行全量源、185,550 条采用事件；不编造规模 | §3 |
| EV/充电字段缺失 | 受限：情景层设定并披露，未冒充实测；跨来源组合明示 | §3、DATASET_CHOICE |
| 非单调性/等待行为等无证据结论 | 已删除或标 missing_data，未编造 | E7、§5.4 |

## 9 剩余限制与未完成

1. 单一年份（2014）单城（Melbourne CBD 路侧），外部效度有限；2018/2019 同族数据可作敏感性但本轮未下载。
2. EV 标签、充电需求、能量、硬件全部为情景层；q_need 未识别；跨来源（充电会话）只能给能量/连接参数。
3. 三约束服务标准在声明情景下不可达；条件整数配置 k* 需改情景口径，本轮给出不可行结论而非 k*。
4. 非单调轨迹未观察到（E7 missing_data）；等待/巡航行为没有模型，未给改善结论。
5. 成本/收益未作新计算（旧成本参数全部未识别，沿用只读历史对照）。
6. 图组/稿件/SI/复现包的最终页数与字数以交付说明为准；未由机器输出支撑的数字以 [UNRESOLVED] 标注。


## 10 R8-F 收口阶段：数据适配、理想上界与声明硬件复核（2026-10-31 夜）

1. **分析单元与容量**：场站=AreaName 聚合（3–17 个 street×side 面、12–82 个泊位）；容量=窗口内不同 BayID 数；
   扫描线核验任一时刻占用 ≤ n_spaces（超容量 0 分钟）。窗口 236,819 行 / 24 区 → 10 区 185,552 行 → 剔除 2 条
   纪元缺离场 → 185,550 契约事件，逐站差额 0。源数据 366 个本地日的成因=2014-01-01 与 2015-01-01 两端点均有记录。
2. **观察层 ≠ 潜在需求**：只观测到已停车车辆，无法识别被拒需求；重放是"以观测停车事件构建的条件请求流"，
   EV/补能/能量为情景层，未混入模拟未观测需求。
3. **理想交付上界**（min(E, P·T)，忽略连接器/共享/馈线）：全部 6,588 请求、需求 92,366 kWh，22 kW 下理想交付
   50,891 kWh（55.1%）、会话失败 3,940（59.8%）；功率敏感性 30.3/40.4/55.1/69.3%。留出 20 流子集：1,891.028 kWh、
   991.891 kWh（52.45%）、80/137 —— 与条件域 k=n_spaces 实测（991.9、80/137）逐位一致，证明该实验已达理想上界。
4. **需求—停留错配**：14 kWh@22 kW 需 38.2 min；各站充电会话停留中位 12.7–42.5 min，低于所需比例 46.7–72.7%；
   声明能量 2/4/6/8/10/14/20 kWh 的会话失败率 25.6/37.3/44.1/49.3/53.9/61.0/70.2%，**没有任何能量水平满足 5%**。
   ⇒ 三约束标准在"本次停车必须充满"口径下由设备不可达；改变只能来自会话语义（部分补能）、最小停留预留或放宽容差。
5. **情景/硬件更正（重要）**：此前"运行器用了 0.10 份额 + 4 枪上限"的判断是**错的**——SCENARIO_DEFAULTS 只在站点
   缺字段时生效，契约四字段齐全故未生效；7 kW 与 main22 用的就是 20% 声明硬件。已由 engine-b 的 hardware_audit.json
   与我复核的 k 网格（达到声明 charging_bays，最大 16）确认，正文 §4.3 与 SCENARIO_LEDGER.md 均已更正。
6. **declared22 复核运行**：k=1 接入 52/137（37.96%）/ 交付 365.7 kWh；k=声明充电位数接入 136/137（99.3%）/
   交付 984.2 kWh（52.05%）/ 短会话 80/137；三约束仍不可行，M2 在 k=1 与 R8 原值逐位一致（B0−A -0.2276
   [-0.3217,-0.1421]），declared max k 下 B0−A -0.3190 [-0.3956,-0.2445]、B1−A -0.00356 [-0.01068,0]、B2−A 0。
   ⇒ **access 不是硬件层绑定约束；绑定约束是停留内交付声明能量。** 低接入只属于 k=1 人为保守设计点。
7. **统计**：20 条留出流来自 9 个站点、17 个日期（Victoria Market 占 8 条）；流级 bootstrap 复现存档 CI，站点聚类
   bootstrap（9 簇）下 B0−A [-0.2972,-0.1333] 仍排除 0，B1/B2 仍含 0（不作等价结论）；B1≡B2 于 20/20 流两指标
   （ICE 失败 0/4,643，B2 借用分支未触发，属条件等价而非独立算法证据）。
8. **搜索状态**：confirmed_minimal / 声明域内无可行 k / 理想上界下物理不可行 / 数据不足 四分，不混用；声明域内无解
   不被写成 physical infeasibility。无单调性假设，k 全枚举。
9. **交付**：rev6 主稿 16 页 / 6,335 词（Word 统计）、SI 5 页 / 1,321 词，9 图全部嵌入（F1–F9），0 未解析 token；
   图件 13 条 real 记录（含 F9 PNG+SVG 与脚本/输入哈希）；复现包补入 R8-F 命令与结果清单。
