# 共享数据契约与分工（2026-10-31，Lead 维护 v1）

所有 subagent 动手前先读完本文件。冲突时：用户本次指令 > 项目 AGENTS.md > 本文件。

## 0 总原则
- 一切「已完成/已取得/已运行」必须有工具结果；无来源数值一律 null，禁止填 0、禁止套演示默认值、禁止为跑通补数。
- 事实三态：确定 / UNVERIFIED: 具体疑问 / 先查再答。报错原样贴出，不改写成成功。
- 不预设 PPR 人为搜索区间，不预设全覆盖或电气化拐点成立。
- 冻结 `main_paper/`、`paper/draft/` 已登记工作稿、历史 `research/`/`plan/`/`metadata/` 记录：只读，不改不删。
- 不干扰运行中的台北 372 场采集器：`research/collection/taipei_372_polling_20261030/` 只读（data/ 下 jsonl 很大，必须流式读取），不重启、不改 poller、不删批次。
- 文献索引（`literature/INDEX.md`、`literature/index.json`、`literature/reading-log.json`）、统一参数文件、最终报告由 Lead 汇总；subagent 只写自己名下新文件。
- 不新建重复的管理类报告；subagent 的阶段报告写在自己目录，最终综合报告由 Lead 合并到 `docs/reports/`。
- 每个 subagent 结束前运行自己范围内的测试；不得引入失败测试。测试若因契约改动必须调整，回执中逐条列出原因。

## 1 目录所有权（越界写即冲突）

| 路径 | 所有者 | 说明 |
|---|---|---|
| `research/official_data_20261031/contract/` | Lead | 本契约 |
| `research/official_data_20261031/ev_behavior/` | ev-data | 原始下载、清单、哈希、数据字典、清洗记录 |
| `research/official_data_20261031/traffic_resources/` | ev-data | 场站规模/枪/功率/故障/到访结构的官方或已采数据整理（只读消费台北已保存数据） |
| `research/official_data_20261031/social_cost/` | cost-data | 社会成本与基础设施官方数据 |
| `research/official_data_20261031/logs/ev_behavior_requests.jsonl` | ev-data | 请求日志 |
| `research/official_data_20261031/logs/social_cost_requests.jsonl` | cost-data | 请求日志 |
| `research/calibration/charging_probability_20261030/model_20261031.json`（及同目录 `model_20261031_*`） | ev-data | 充电概率模型/情景（不改 evidence.json / rates.json） |
| `research/cost_model_20261030/parameter_candidates_20261031.json` | cost-data | 参数候选（不改 parameters.json） |
| `apps/parking_lab/workbench/traffic_gen.py`、`tests/test_traffic_gen.py`、`__main__.py`（仅新增子命令）、`research/traffic_generation_20261031/` | traffic-gen | 车流生成器与校准 |
| `apps/parking_lab/workbench/simulation.py`、`config.py`、`prediction.py`、`rules.py`(新)、`tests/test_type_rules.py`(新)、`research/sim_rules_20261031/` | sim-rules | 规则引擎与隐藏信息边界 |
| `apps/parking_lab/workbench/allocation.py`(新)、`tests/test_allocation.py`(新) | qwen-local | 整数配桩与排队数学工具 |
| `apps/parking_lab/workbench/parameter_registry.py`(新)、`tests/test_parameter_registry.py`(新)、`research/integer_allocation_20261031/`、`docs/reports/2026-10-31-*`、`research/parameters/` | Lead | 参数契约实现、整数配桩实验、综合报告 |

## 2 参数记录 schema v3（统一参数契约）
每个参数至少携带下列字段（JSON 对象；缺省写 null 并说明原因）：

    param_id, name_zh, definition, probability_object, numerator, denominator, denominator_definition,
    unit, region, period, vehicle_scope, scenario_scope, price_year, value, source_ids[], source_class,
    locator, estimation_method, uncertainty{low,high,type}, limitations[], is_scenario(bool),
    admitted_use[], status, source_file_sha256

- `probability_object` ∈ {q_use, q_need, q_day, q_location_share, device_time_utilization, potential_demand, null}；分母不同不得平均、不得互相替代。
- `admitted_use` ∈ {traffic_fit, charging_prob, energy_power_dwell, social_cost, validation, sensitivity_only}。
- `status` ∈ {available(已取得且可入模), transferable(仅有可迁移参考值), unidentified(不可识别), rejected(审查后排除)}。
- `source_class` ∈ {official(政府/公共机构/官方统计/正式调查/公开采购), peer_reviewed, institutional_report, scenario(情景假设，无外部来源), derived(由本项目计算)}。
- 价格年份、地域、时期、车型/场景不一致时必须写明换算依据；不能把国外时间价值按汇率直接当本地值。

## 3 来源记录 schema（manifest/evidence）

    source_id, title, org, url, retrieved_at_utc, http_status, local_path, sha256, bytes, official(bool),
    source_class, region, period, unit_notes, sample_filter, revision, what_it_supports[], limitations[]

- 只留搜索链接不算取得证据；必须落盘原始文件（PDF/HTML/CSV/ZIP）+ sha256 + 下载时间。
- 同一数据集的多篇论文要标 `same_dataset_as`，不得当作独立样本计数。

## 4 采集日志与预算
- 每次 HTTP 请求（含诊断/探测）追加一行 JSONL 到自己的 logs 文件：
  {seq, t_utc, method, url, purpose, status, bytes, sha256, saved_path, error}。
- 预算：每个数据 agent ≤ 60 次请求、≤ 200 MB 落盘、≤ 45 分钟。失败留痕，不重复探测凑数；到上限即停。
- 只使用公开可下载来源；遇到 403/付费墙/登录墙，记录限制并换源，不伪造数据。

## 5 充电概率契约
- 必须同时保留 q_use（受实际可用性与规则影响的充电发生率）与 q_need（进入资源和准入限制前的潜在需求概率）。
- 目标场景：台北式公共停车场（路外停车场，5 分钟级余位与逐枪状态可观测）。本阶段不声称已对任一真实停车场校准 q。
- 禁止用台北「枪使用次数/停车车次/全市电车保有量比例」间接反推值作为核心充电率。
- 无法识别 q_need 时，给出来源标注的情景网格与识别边界（如下界 q_use、供给侧观测可给的上界），并写明最终推荐依赖这些条件。

## 6 车流生成契约
- 参数文件 `research/traffic_generation_20261031/fitted_parameters.json`：每项含值、来源（本地数据/文献编号）、拟合方法、样本切分、不确定性。
- 生成器 `apps/parking_lab/workbench/traffic_gen.py` 输出规范化 JSON：
  meta{seed, params_hash, generator_version, split, horizon_min, n_spaces} + arrivals[{vehicle_id,time_min,is_ev,needs_charge,dwell_min,energy_kwh}]
- 车流哈希 = 与 `workbench.demand.stream_hash` 相同的规范化 SHA-256（排序键、紧凑分隔符）。Lead 会独立复算并重放。
- 隐藏真值（needs_charge、energy_kwh、真实离场时间）不得进入任何控制器可见接口；模型侧只能看到 is_ev 与已发生的充电开始。
- 校准数据：台北 372 场 `parking_slots.jsonl`（5 分钟净占用）+ `connector_status_long.jsonl`（逐枪状态）；拟合/验证按整天或场站隔离，禁止泄漏。
- 必须写明：余位快照只恢复净占用变化，不恢复逐车到达；枪待机不等于空位或充满未走。

## 7 规则契约（阶段四）
控制器可见：车辆类型 is_ev（按车辆类型判断，含不充电电车）、当前占用与资源状态、历史统计与短期预测。
控制器不可见：needs_charge、SOC/电池容量/能量、真实离场时间、未来到达车辆。

| 规则 | 语义 |
|---|---|
| π0 `dedicated_by_type` | 电车（含本次不充电的电车）可用带枪位与充电预留位；油车只能普通位。EV 无带枪位时允许停普通位，以保持总容量不变；三条规则统一此细节。 |
| π1 `full_open_ice_first` | 油车优先普通位，普通位不足时可用带枪位；电车同 π0。用于分离共享本身收益。 |
| π2 `predictive_shared_ice_first` | 油车优先普通位；普通位不足时用当时可得的电车到达/充电预测决定是否放行；不得读隐藏意愿。用于分离预测收益。 |

- 旧 `strict`（按 needs_charge 分区）标 legacy，仅供历史复现，不得改名冒充 π0；正式对照必须用新规则。
- 无充电需求电车占位、充电完成仍占位、油车占充电位分别记录（分钟与车次数）。

## 8 整数配桩契约（阶段四）
- `C(k;π0)=设施分摊成本(k)+E[用户额外社会成本(k;π0)]+运行资源成本(k;π0)`，k 为整数带枪位数量。
- 一桩/一枪/带枪车位的关系由配置给出并写明；PPR 分子用带枪车位数，不得混用枪数与桩数。
- 可行集：k ∈ [0, min(总车位, 工程上限)]，不预设比例区间；空间/供电约束由配置给。
- 必须区分：量纲检查（平均负荷）、解析近似、经验预测公式、完整随机成本模型；不得把平均需求四舍五入当最优。
- 必须输出：全部 k 的成本与物理指标、ΔC(k)、并列最优、floor/round/ceil 复算、边际成本单调性检查、样本外后悔值、参数不确定性下的 k* 分布。
- 缺参时：输出可计算分项与 null + missing_parameters，不得编造完整社会成本或唯一最优桩数；完整社会成本不可算时用「条件化情景成本」并显式标注。

## 9 allocation.py 接口（qwen-local 单，Lead 已定）
见该单派活正文。纯标准库、不得 import 其他 workbench 模块、不得修改其他文件。

## 10 验收与回执
- 自己范围内测试：`python -m unittest discover -s apps/parking_lab/workbench/tests -v`（不得新增失败）。
- 有文件改动后运行 `python scripts/check_all.py`；当前基线 EXIT=1，原因是缺少 python-docx 导致「稿件字数与章节一致性」失败（原有问题，不是本轮引入）。
- 回执 ≤40 行：产出路径、实际命令与退出码、实测数字、未完成/限制、UNVERIFIED 项。不要贴大段代码或长表格。
- 超时（数据 45 分钟、代码 60 分钟）先交可运行子集 + 限制清单，不静默拖延。

## 11 研究判断（Lead 已定，供各单统一口径）
- 场站可观测：净占用曲线、逐枪状态与充电会话；可识别「充电需求到达率 λ_c」与「占用时长分布」，但不能单独识别 q_need 与 EV 到访比例 p_EV。
- 配桩物理负荷用乘积 λ_charge=λ_arrival·p_EV·q_need；q_need 单独由文献情景给出，并用「文献 q_need × 合理 p_EV 是否与实测 λ_c 相容」做一致性检查。
- 社会成本中「真实场景效果」「解析近似」「模拟条件最优」分别表述，不把模拟条件最优写成真实效果或证明。
