# R8 数据字段级质检报告（主：Melbourne 2014 路侧停车事件）

类型: 数据质检报告
状态: 进行中（依赖 Lead 的全文件流式统计 `data/qa/source_stats.json`）
负责人: R8-A（诊断与报告）；全量计数由 Lead 的构建生成
数据: `data/raw/melbourne_parking_bay_arrivals_departures_2014_mq3i-cbxd.zip`（SHA-256 `B92333B2…2A34`）

## 1 检查对象与口径

- 原始：zip 247,682,126 B → 内嵌 CSV 2,840,248,423 B（21 列，`ParkingEventId` 为主键候选）。
- 行语义：一行 = 一次占用事件（`ArrivalTime` 到达、`DepartureTime` 离开、`DurationSeconds` 停留）。
- 主键：ParkingEventId；场站单元：`StreetId` × `SideCode`（街道侧段）；车位：`BayID`。
- 计数来源纪律：**本节所有计数取自 Lead 生成的 `data/qa/source_stats.json`（全文件流式一遍）**；该文件未出现或字段缺失时，本报告对应单元格标 UNVERIFIED，不补造。

## 2 R8-A 已完成的独立诊断（有工具输出）

| 检查 | 方法 | 结果 |
|---|---|---|
| 日期字段格式 | 400 万行样本，分别按 mm/dd 与 dd/mm 解析 | 按 mm/dd 解析失败 **2,437,464 / 4,000,000** 行；按 dd/mm 全部可解析 → 确认 **日/月/年** |
| 时间后缀 | 逐行提取尾部 offset | 全部为 `+0000`（恒定，非真实时区偏移） |
| 时区判定 | 标注小时直方图（400 万行样本成功解析部分） | 高峰 07:00–18:00（9–13 点最高，约 12.6–13.9 万/小时），低谷 01:00–05:00（约 2.5–4.5 千/小时）；与咪表收费时段 07:30–19:30 一致 → 本地墙钟时间 |
| 跨年溢出 | 样本内年份字段 | 4,000,000 行中 2015 年 822 行（新年前后边界，需在全量统计中单列） |
| 文件可读性 | zip 条目读取 + csv 解析 | 可流式读取，无需解压落盘 |

## 3 全量字段级检查（已回填 Lead 的 source_stats.json，2026-10-31 19:02Z）

来源：`data/qa/source_stats.json`（Lead 全文件流式统计）。该文件没有给出的指标一律保持 UNVERIFIED，不用门户宣传数替代。

| 检查项 | 规则 | 实测 |
|---|---|---|
| 总行数 | = 有效+剔除 | **13,503,655** 行（与门户声明 13.5M 行一致） |
| 到达时间可解析率 | 应接近 100% | 解析失败 **0** 行 |
| ParkingEventId 唯一性 | 主键应唯一 | **不唯一**：distinct_event_ids=**168,905**（同一 ID 在 13.5M 行中重复；推断为按设备/日历循环的计数器）→ 见 §6 |
| 车位/场站 | BayID、街道侧段 | 不同 **BayID=5,228**；不同 **block face=335** |
| 本地日期跨度 | 2014 日历年 | day_min=**2014-01-01**，day_max=**2015-01-01**；不同本地日 **366**（含跨年边界 1 天） |
| 完整 24h 日（全城口径） | 24 个小时档均有到达 | **364** 天 |
| 负时长 | 剔除并计数 | **7,670** 行 |
| 零时长 | 剔除并计数 | **0** 行 |
| InViolation（超时） | true 计数/比例 | **1,505,691** 行 = **11.15%** |
| 缺失字段 | 空 DepartureTime=右删失 | UNVERIFIED（source_stats.json 未给） |
| 重复事件 / 重复 (BayID, ArrivalTime) | 完全重复 | UNVERIFIED（源统计未给；ID 不唯一 ≠ 行重复） |
| 时间戳与 DurationSeconds 一致性 | 差值>5s | UNVERIFIED |
| 跨日事件 | 到达与离开跨本地日 | UNVERIFIED |
| 同一车位容量冲突（重叠停留） | 单泊位重叠检测 | UNVERIFIED |
| 缺失日 | 2014 年内无事件日 | UNVERIFIED（区间内 366 天，2014 年缺日未给） |
| 传感器停机/重置 | 同 BayID 长时间空洞/映射变化 | UNVERIFIED |
| 左右删失 | 右删失=DepartureTime 缺失 | UNVERIFIED |
| DST 两日事件数 | 2014-04-06 / 2014-10-05 | UNVERIFIED |
| 场站级完整日 | site-day 有事件 BayID/容量≥0.8 | UNVERIFIED |

算术派生（除数为源统计直接字段）：平均每车位全年事件数 2583；平均每 block face 事件数 40309；超时率 11.15%。


## 6 关键警告：ParkingEventId 不是唯一事件键

`source_stats.json` 显示 13,503,655 行仅有 168,905 个不同 ParkingEventId，因此：

1. 契约 `event_id` 若直接取 ParkingEventId，**不是唯一事件标识**，下游 join/去重会误合并；
2. 建议事件唯一键使用 `source_row`（CSV 数据行号）或 (DeviceId, ParkingEventId, ArrivalTime) 组合；
3. “重复事件”检测不能按 ParkingEventId 判定，必须按 (BayID, ArrivalTime, DepartureTime) 判定。

## 4 已知问题与处理规则（确定项）

1. **时区**：后缀 `+0000` 不可信；按 Australia/Melbourne 本地墙钟→UTC 处理（依据见 §2）。2014 DST 规则：AEDT UTC+11 至 2014-04-06 03:00；AEST UTC+10 至 2014-10-05 02:00；之后 AEDT UTC+11。导出窗口（2014-01-06..03-30）全程 AEDT，无 DST 跳变。
2. **成对事件**：DepartureTime 缺失即右删失，不得当作 0 停留或删除后不记录。
3. **容量派生**：单泊位传感器，容量=StreetId×SideCode 下不同 BayID 数；同一场站全年容量可能变化，须在方法中声明取值口径（年观测最大/窗口观测）。
4. **单泊位冲突**：同一 BayID 的停留区间重叠视为容量/传感冲突（1 车位不应同时两车），须计数并从建模样本中按规则剔除或标记。
5. **门户 rows=0**：ODS 新 API 无记录，实际数据仅在归档 S3 zip；一切计数以实际下载文件统计为准。

## 5 下游使用注意

- 统计单元=场站-日（site-day），**不得把 5 分钟快照或单条事件当独立样本**（PLAN §3.7）。
- 事件加权失败率与场站平均/最坏日口径需先声明；本数据只提供到达/停留，不提供拒绝服务记录，服务水平需由重放模拟产生。
- 无 EV 标签、无 kWh：能量侧须另行声明跨来源组合（见 `DATASET_CHOICE.md` §5）。
- 本报告只引用 Lead 的 `source_stats.json`；未回填项保持 UNVERIFIED，不引用门户宣传数当实测。


## 回填（Lead，2026-10-31）

- 最终契约 data/processed/public_parking_events.json，schema public_parking_events/v1，SHA-256 38b1422bb95d4122565d4de70a5ef4faf35e41600019068c9c077a295ee6bdf6；10 个场站（AreaName 口径）、185,550 条事件、789 个完整场站-日。
- 契约层 complete_days 已可核（coverage.complete_days），此前标 UNVERIFIED 的场站级完整日由该字段回填。
- 事件键：源 ParkingEventId 不唯一（13.5M 行 / 168,905 值）；契约 event_id 用窗口行号唯一化，source_event_id 仅追溯。
- 独立质检脚本 scripts/dataset_qa.py 对 data/processed/contract_events.csv 复算，结果见 data/qa/machine/。

## 独立质检结果（契约层，scripts/dataset_qa.py，2026-10-31 19:39）

对象 data/processed/contract_events.csv（185,550 行，契约直出导出，仅供质检）。

| 检查 | 结果 |
|---|---|
| 必需字段缺失 | 0/0/0/0/0/0/0/0/0/0（全 0） |
| 重复 event_id | 0 |
| 负时长 / 停留与到达-离开不一致 / 跨日 | 0 / 0 / 0 |
| 无法解析时间戳 / 容量为空或非正 | 0 / 0 |
| 同场站同到达时刻的多条记录 | 6,414（3.46%）——同一街区面多车位在同一分钟到达属正常，非重复事件 |
| 同场站同时刻占用>申报容量 | 19 个样本（0.010%），见下方口径说明 |
| 24 小时全覆盖日 | 全部 false——路侧地磁不是 24h 传感器；本项目 complete_days 定义是"当日到达覆盖 >=6 个两小时桶"（>=12h），两者定义不同，非数据缺陷 |

口径说明：契约 n_spaces = 窗口内观测到的不同 BayID 数；地磁在换车/换 Bay 时可能瞬时重叠，故少量同时刻占用超申报容量属边界效应，已在论文数据节与限制节注明。
