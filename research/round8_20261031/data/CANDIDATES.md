# R8 数据候选矩阵（公开停车/充电数据）

类型: 研究数据候选清单
状态: 生效（2026-10-31 实测）
负责人: R8-A（数据工作流）
写入域: `research/round8_20261031/data/**`

判定规则见 `../PLAN.md` §2：主数据必须同时满足 P1 可实际下载 / P2 事件级到达+停留 / P3 多场站多完整日（≥4 个完整 24h 日、≥3 场站）/ P4 场站或车位标识+容量+带时区时间戳 / P5 许可清楚。
“实际下载状态”只写本轮真实执行过的动作；仅 HEAD 200 的标为“未下载（端点可用）”；未定位端点的标 UNVERIFIED。

## 0 总表

| # | 候选 | 来源/版本 | 许可 | 实际下载状态 | 字段 | 样本单位 | 场站/车位 | 事件数 | 日期跨度 | 完整24h日数 | 缺失/重复 | EV标签 | 充电数据 | 适用限制 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **City of Melbourne 停车位到达/离开 2014（主）** | data.melbourne.vic.gov.au，Opendatasoft 归档 S3 `mq3i-cbxd.zip`；元数据 modified 2020-08-05 | CC BY（Opendatasoft license 字段 "CC BY"） | **已全量下载**：zip 247,682,126 B，SHA-256 `B92333B2…2A34`；zip 内 CSV 2,840,248,423 B，21 列 | ParkingEventId, DeviceId, ArrivalTime, DepartureTime, DurationSeconds, StreetMarker, SignPlateId, Sign, Area, AreaName, StreetId, StreetName, BetweenStreet1/2 Id+Description, SideOfStreet, SideCode, SideName, BayID, InViolation | 一次停车占用事件（到达+离开成对） | 车位=BaidID（传感器），场站=StreetId×SideCode（街道侧段）；全量计数见 `qa/source_stats.json`（由 Lead 生成） | 官方描述 13.5M 行；本轮全量扫描由 Lead 的流式统计给出（UNVERIFIED：待 `qa/source_stats.json` 落地后回填） | 2014-01-01..2014-12-31（日历年内） | 全城口径待 Lead 统计；导出窗口内场站级完整日待回填 | 重复/负时长/跨日等由 Lead 统计回填；已知字段级问题见 §2 | 无 | 无 | 车牌无关；仅路侧单泊位传感器，容量按街道侧段派生；无 EV 标识、无 kWh |
| 2 | City of Melbourne 路侧传感器 2018 | 同上归档 S3 `5532-ig9r.zip`；portal 描述 504MB、30.2M 行 | CC BY | 未下载（HEAD 200，端点可用） | 与 2014 同族（2018/2019 版为“存在/离开”事件行） | 事件 | 同族 | 30.2M 行（portal 声明，UNVERIFIED 未下载核对） | 2018 日历年 | UNVERIFIED | UNVERIFIED | 无 | 无 | 文件更大（504MB zip），本轮不下载以免超出总量；可作为敏感性年份 |
| 3 | City of Melbourne 路侧传感器 2019 | 同上 `7pgd-bdf2.zip`；声明 717.1MB、42.7M 行 | CC BY | 未下载（HEAD 200） | 同族 | 事件 | 同族 | 42.7M 行（声明） | 2019 日历年 | UNVERIFIED | UNVERIFIED | 无 | 无 | 同上；下载量最大 |
| 4 | City of Melbourne 路侧传感器实时快照 | `on-street-parking-bay-sensors`（ODS 记录 6,324 行） | CC BY | 已下载 100 行样本（API records，23,925 B） | lastupdated, status_timestamp, zone_number, status_description, kerbsideid, location | 当前状态快照 | 6,324 车位 | 无历史事件（仅当前占用） | 仅当前 | 不适用 | — | 无 | 无 | 无到达/离开时间，不能做停留时长；仅作车位空间参照 |
| 5 | **Austin Parking Transactions（备选）** | data.austintexas.gov `5bb2-gtef` | Public Domain（Socrata license） | 已下载 2,000 行样本（311,107 B CSV）；`$select=count(*)`=**18,943,049** | id, source, duration_min, start_time, end_time, amount, meter_id, zone_id, zone_group, payment_method, location_name, updated_at | 一次缴费停车会话 | 咪表 meter_id／zone；容量需外部资产表 | 18,943,049 行（计数已验证） | 数据跨多年（样本含 2023–2024；具体起止 UNVERIFIED） | 未统计 | 未统计 | 无 | 无 | 停留=**购买时长**而非实测占用，会低估/高估真实停留；无时区偏移字段；无容量字段 |
| 6 | Seattle Paid Parking Transaction Data | data.seattle.gov `gg89-k5p6` | Public Domain | 已下载 500 行样本（87,712 B）；`count(*)`=**159,574** | transaction_id, meter_code, transactiondatetime, payment_mean, amount_paid, durationinminutes, blockface_name, sideofstreet, elementkey, parkingspacenumber, lat, lon | 一次缴费交易 | 咪表+blockface；无容量列 | 159,574 行 | 近两年滚动窗口（样本 2026-10；具体起止 UNVERIFIED） | 未统计 | 未统计 | 无 | 无 | 同为购买时长，非实测占用；无单车到达/离开对 |
| 7 | Seattle 2019 Paid Parking Occupancy | data.seattle.gov `qktt-2bsy` | Public Domain | 已下载 500 行样本（87,812 B）；`count(*)`=**286,106,444** | occupancydatetime, paidoccupancy, blockfacename, sideofstreet, sourceelementkey, parkingtimelimitcategory, parkingspacecount, paidparkingarea/subarea, rate, location | 路段 3 分钟级占用快照 | blockface 级；**有 parkingspacecount 容量** | 286M 快照行 | 2019 全年 | 可构造（快照密集） | 未统计 | 无 | 无 | 聚合占用，无单车到达/停留；仅能复核容量与占用率 |
| 8 | ACN-Data（官方，EV 充电会话） | ev.caltech.edu/dataset；API `/api/v1/sessions/...` | 官方需注册获取 token；仓库镜像无 LICENSE（UNVERIFIED） | 官方 API **401 Unauthorized**（未注册，不绕过）；GitHub 静态镜像 `tongxin-li/ACN-Data-Static` 已下载 2 个会话 csv.gz 样本（43,115 B / 22,128 B） | 官方会话字段含 connectionTime/disconnectTime/kWhDelivered/doneChargingTime/siteID/spaceID（镜像样本为逐会话时间序列：timestamp, Charging Current, Actual Pilot, Voltage, Charging State, Energy Delivered (kWh), Power (kW)） | 一次充电会话/逐会话时间序列 | 镜像 README：7 个车库（Caltech 5 个 + JPL 1 个 + Office1 1 个），85,877 个会话文件，2018–2020 | 85,877 会话文件 | 2018–2020 | 可构造 | 未统计 | 有（充电会话=EV） | **有 kWh/功率** | 需注册才可全量；镜像无许可声明；充电会话不能反推未充电 EV 的停车分母 |
| 9 | ST-EVCDP（深圳，EV 充电占用） | GitHub `IntelligentSystemsLab/ST-EVCDP`（MIT） | **MIT**（仓库 LICENSE 已下载核对） | **已真实下载** stations.csv (56,546 B, SHA-256 `FA9AA945…E804`)、occupancy.csv (5,574,243 B, `9502BE5F…F140`)、time.csv (147,925 B, `B6CE3811…6A8F9`) | stations: station_id, lat, lon, fast, slow, count；occupancy: 5 分钟×站点占用数宽表；time: 时间戳分解 | 站点×5 分钟聚合占用 | 1,706 个站点（stations.csv 行数）；README 声明 18,061 充电桩 | 8,640 个 5 分钟时段（30 天） | 2022-06-19..2022-07-18 | 30 天（5 分钟分辨率） | 未统计 | 有（充电桩占用） | 有占用/价格/电量聚合 | 聚合序列无会话级到达/离开，不可做停留时长拟合；中国深圳，非本论文城市情景 |
| 10 | UrbanEV（深圳，ST-EVCDP-v2） | GitHub `IntelligentSystemsLab/UrbanEV`（CC0-1.0） | CC0-1.0 | 未下载（仓库 85,603 KB；元数据已核对） | 站点/占用/时长/电量 5 分钟与 1 小时序列 | 站点×时间聚合 | 24,798 充电桩 | UNVERIFIED（未下载核对） | 6 个月 | 未下载 | 未统计 | 有 | 有 | 同上，聚合无会话 |
| 11 | Melbourne Off-street car parks with capacity and type (CLUE) | `off-street-car-parks-with-capacity-and-type`（ODS 151,199 行） | CC BY | 已下载 100 行样本（API records，35,385 B） | census_year, block_id, property_id, building_address, clue_small_area, parking_type, parking_spaces, lon/lat | 物业×普查年 | 151,199 物业年 | 无事件 | 2002–2024 | 不适用 | — | 无 | 无 | 只有容量（车位总数），无到达/停留；可做容量外部校验 |
| 12 | NYC Parking Meters Locations and Status | data.cityofnewyork.us `693u-uax6` | NYC Open Data 条款（Public Domain 类，UNVERIFIED 具体条款） | 已下载 500 行样本（132,486 B）；count=**15,598** | objectid, meter_number, status, meter_hours, facility, borough, on_street, from/to_street, lat/lon | 咪表点位 | 15,598 个咪表 | 无事件 | 仅当前点位 | 不适用 | — | 无 | 无 | 仅点位/状态，无交易或占用事件 |
| 13 | SFpark 传感器事件数据 | 检索 data.sfgov.org Socrata catalog `q=sfpark` → 0 结果；猜测的 sfmta.com 数据页 404 | UNVERIFIED | **未定位到公开可下载端点** | UNVERIFIED | — | — | — | — | — | — | — | — | UNVERIFIED：未找到官方 CSV/API 入口，本轮不采用 |

## 1 主/备选择

- **主：候选 1（Melbourne 2014 到达/离开事件）**——唯一同时实测满足 P1（已全量下载+哈希）、P2（成对到达/离开）、P3（全城多街道侧段+全年 365 天）、P4（BayID/StreetId/SideCode + 可派生容量 + 本地时间可转 UTC）、P5（CC BY）的候选。
- **备：候选 5（Austin Parking Transactions）**——P1（可 API 分页下载，实测样本+计数）、P4 部分（meter/zone + 时间，但无容量列）、P5（Public Domain）；P2 弱（停留=购买时长）、P3 满足（多 zone、多年）。仅用于灵敏度/复核，不进主结果。
- 备选之二：候选 8（ACN-Data）仅作**充电/能量侧情景**来源，不作停车分母。

## 2 主数据集已知问题与处理

1. **时间格式**：`ArrivalTime/DepartureTime` 为 `dd/mm/yyyy hh:mm:ss AM` + 固定 `+0000` 后缀。本轮用 400 万行样本验证：按 `mm/dd` 解析时有 2,437,464 行失败（首段>12），按 `dd/mm` 全部可解析 → 确认日/月顺序为 **日/月/年**。
2. **时区标注不可信**：后缀恒为 `+0000`，但数据是墨尔本本地墙钟时间（证据见 `DATASET_CHOICE.md` §3 的日内分布），处理为 Australia/Melbourne 本地时间再转 UTC。
3. **成对事件**：一行=一次占用（到达+离开），若 DepartureTime 缺失则为右删失，需在质检中分离。
4. **单泊位容量**：每个传感器只有 1 个泊位，场站容量需按“街道侧段内不同 BayID 数”派生（见 processed 的 site_capacity 定义）。
5. **门户元数据 rows=0**：该 ODS 数据集记录未迁移进新 API，实际数据仅在归档 S3 zip 中，故所有规模必须以实际下载文件统计为准（见 PROVENANCE.json）。

## 3 未采用/未验证说明

- 候选 2/3/10/13 未全量下载：本轮下载总量控制（主 zip 247.7MB），且主数据已满足 P1–P5；UNVERIFIED 部分不回填为“确定”。
- 候选 4/7/11/12 无事件级到达+停留，不满足 P2，仅作参照。
- 任何“事件数/完整日数”未实测者一律标 UNVERIFIED，不引用门户宣传数当实测。
