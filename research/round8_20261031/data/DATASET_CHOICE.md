# R8 主/备数据集选择（按 PLAN §2 P1–P5 规则事前判定）

类型: 研究数据选型
状态: 生效（2026-10-31）
负责人: R8-A；processed 导出由 Lead 生成
写入域: `research/round8_20261031/data/**`

## 1 结论

- **主数据集**：City of Melbourne **Parking bay arrivals and departures 2014**（路侧地磁传感器事件级到达/离开）
  - 原始文件：`data/raw/melbourne_parking_bay_arrivals_departures_2014_mq3i-cbxd.zip`
  - 大小 247,682,126 B；SHA-256 `B92333B236D5DA0FBDC1AB0A195E57EB7A90EA4A3FDA30D06CF9938A3AD02A34`
  - 许可：**CC BY**（City of Melbourne，署名要求；license 字段来自 Opendatasoft 元数据）
  - 落地页：https://data.melbourne.vic.gov.au/explore/dataset/parking-bay-arrivals-and-departures-2014/
  - 归档下载：`https://opendatasoft-s3.s3.amazonaws.com/downloads/archive/mq3i-cbxd.zip`
- **备份数据集**：City of Austin **Parking Transactions**（`data.austintexas.gov/5bb2-gtef`，Public Domain，实测 18,943,049 行）
  - 只用做灵敏度/复核：停留=**购买时长**，非实测占用；无容量字段；不进主结果。
- **充电/能量侧**（单独声明，不用于停车分母）：**ACN-Data**（官方 API 需注册 token，实测未授权 401；GitHub 静态镜像 85,877 个会话级时间序列文件，2018–2020）与 **ST-EVCDP/UrbanEV**（深圳，MIT/CC0，站点×5 分钟聚合占用与充电量）。

## 2 P1–P5 判定（主数据集）

| 规则 | 判定 | 证据（本轮真实动作） |
|---|---|---|
| P1 可实际下载 | ✅ 通过 | 已全量下载 zip 247,682,126 B 并计算 SHA-256；zip 内 CSV 2,840,248,423 B、21 列；下载命令与时间见 PROVENANCE.json |
| P2 事件级到达+停留 | ✅ 通过 | 字段 `ArrivalTime/DepartureTime/DurationSeconds/ParkingEventId/BayID`，一行=一次占用事件（到达+离开成对） |
| P3 多场站、多完整周 | ✅ 通过（规模由实测计数回填） | 全城路侧传感器、2014 整年（365 天）；场站=StreetId×SideCode 街道侧段，车位=BayID；实测事件数/场站数/完整日数见 `qa/source_stats.json`（Lead 生成）与导出窗口统计（`PROVENANCE.json` 的 export） |
| P4 标识/容量/时区 | ✅ 通过（容量派生） | BayID、DeviceId、StreetId、SideCode、Area；容量=同街道侧段不同 BayID 数；时间戳本地墙钟时间（后缀 +0000 不可信），处理见 §3 |
| P5 许可清楚可归档 | ✅ 通过 | CC BY（署名 City of Melbourne），原始 zip 永久保留在 `data/raw/`，SHA-256 已记录 |

**可得上限（据实测与门户声明）**：2014 年整年 13.5M 行事件（门户声明；实测总行数以 `qa/source_stats.json` 为准），单泊位传感器约数千个，覆盖墨尔本 CBD 路侧泊位；同一归档另有 2011–2020 年逐年版（2018/2019 版为 30.2M/42.7M 行声明），本轮未下载。

## 3 时区决定（关键）

1. 源字符串形如 `04/02/2014 10:56:29 AM +0000`：日期为**日/月/年**（R8-A 用 400 万行样本验证：按 mm/dd 解析失败 2,437,464 行，按 dd/mm 全部可解析），后缀恒为 `+0000`。
2. 该 `+0000` 不能按字面理解为 UTC：若按 UTC 解释，本地到达高峰会落在 18:00–05:00，与已公布的咪表收费时段（07:30–19:30）矛盾；实际标注小时分布为 **07:00–18:00 高峰、01:00–05:00 低谷**（R8-A 400 万行诊断，见 `qa/QA_REPORT.md` §2）。
3. **处理**：剥离后缀，按 **Australia/Melbourne 本地墙钟时间** 解析，再转 UTC。2014 年规则：AEDT UTC+11（至 2014-04-06 03:00 本地）→ AEST UTC+10（至 2014-10-05 02:00）→ AEDT UTC+11。
4. 导出窗口 **2014-01-06..2014-03-30（84 个本地日 = 12 个完整 ISO 周）全部处于 AEDT（UTC+11）区间**，窗口内无 DST 跳变；全年两个过渡日（04-06 重复 02:00–02:59、10-05 不存在 02:00–02:59）在统计中单列，不参与窗口导出。
5. 未解决：无法用第二来源独立验证该墙钟假设（归档数据无独立 UTC 列），已在 PROVENANCE/QA 报告中标注。

## 4 实际规模（口径与实测）

实测来源：`data/qa/source_stats.json`（Lead 全文件流式统计，2026-10-31 19:02Z 在库）。

- **总行数 = 13,503,655**（与门户声明 13.5M 行一致）；到达时间解析失败 0 行；负时长 7,670 行；零时长 0 行；InViolation 1,505,691 行（**11.15%**）。
- **车位 = 5,228 个不同 BayID**；**街道侧段（block face）= 335 个**；不同本地日 **366**（2014-01-01..2015-01-01，含跨年边界 1 天）。
- **全城完整 24h 日 = 364 天**（口径：当天 24 个小时档均有到达事件）。
- **场站与容量定义以 Lead 产物为准**：Lead 的 `data/processed/public_parking_events.json` 目前用 **AreaName 作 site_id**（如 Victoria Market 35 个车位、Queensberry 82 个车位），`capacity_source` 写的是“2014-01-06..2014-03-31 窗口内观测到的不同 BayID 数”；R8-A 文档中的 StreetId×SideCode 只是备选派生口径。两套口径不得混用。
- **事件唯一键警告**：ParkingEventId 仅 168,905 个不同值，**不是唯一键**；契约 event_id 需配 `source_row` 使用（见 `qa/QA_REPORT.md` §6）。
- 未出现在 Lead 统计中的指标（场站级完整日、缺失日、重叠冲突、右删失、DST 当日事件数）标 UNVERIFIED，不补造。
- **导出契约**：`data/processed/unified_events.csv`（Lead 生成），列固定 `site_id,event_id,arrival_ts_utc,departure_ts_utc,dwell_min,site_capacity,day_local,arrival_local_hour,source_dataset,source_row`；导出窗口与场站规则以 Lead 构建脚本为准。

## 5 EV / 充电数据是否可得

| 问题 | 结论 | 证据 |
|---|---|---|
| 主数据集是否含 EV 标签 | **否** | 21 列字段逐一检查：无 vehicle type / fuel / EV 字段 |
| 主数据集是否含 kWh/功率 | **否** | 无能量字段，只有占用时间 |
| ACN-Data 能否真实下载 | **部分**：官方 API 需注册 token（未注册访问返回 **401**，未绕过）；GitHub 静态镜像可下载会话级 csv.gz（已下载 2 个样本，43,115 B / 22,128 B），全量 85,877 文件、7 个车库、2018–2020；镜像无 LICENSE（UNVERIFIED） | 见 PROVENANCE.json secondary_candidates.acn_data |
| ST-EVCDP/UrbanEV | **可下载**：ST-EVCDP MIT，已下载 stations.csv/occupancy.csv/time.csv；1,706 站点、8,640 个 5 分钟时段（2022-06-19..2022-07-18）；UrbanEV CC0（未下载） | 见 PROVENANCE.json secondary_candidates.st_evcdp |
| 能否用充电数据反推未充电 EV 停车分母 | **不能** | 充电会话只覆盖“来充电的车”，无未充电 EV 的到达/停留观测；计划 §2 明确禁止 |

**跨来源组合声明**：主数据（路侧停车占用，墨尔本）与充电数据（Caltech/JPL 或深圳）是**不同城市、不同年份、不同抽样单元**的独立来源，只能作情景参数（如充电时长分布、功率/能量需求）使用；不得声称逐车联合实测，也不得把充电会话份额当 EV 渗透率或停车需求分母。

## 6 已知限制（供论文与 SI 引用）

1. 单泊位传感器：场站容量为派生值，容量在研究期内可能随传感器增删变化（以年观测最大值为准，需在方法中声明）。
2. 路侧收费泊位≠停车场/充电站：到达/停留分布可标定模拟车流，但不能直接外推为充电需求。
3. 事件对缺失即右删失；负时长、重复 ID、跨日事件需在建模前按 QA 规则过滤（规则见 `qa/QA_REPORT.md`）。
4. 归档 zip 来自旧门户（元数据 modified 2020-08-05），数据止于 2014/2020，无法反映当前城市结构。
5. 时区为本地墙钟假设，见 §3。
