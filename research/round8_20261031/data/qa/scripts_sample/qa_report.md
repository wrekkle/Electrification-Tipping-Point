# 数据集 QA 报告

- 输入: C:\Projects\停车场充电桩优化方案\sample_events_20.csv
- 生成时间: 2026-10-31 19:21
- 总行数: 20
- 可解析行（两时间戳均可解析）: 19

## 逐项计数（分母见末节）

| 指标 | 值 | 分母 |
|---|---|---|
| 总行数 | 20 | — |
| 缺失必填字段合计 | 1 | total_rows × 10 列 |
| 重复 event_id | 1 | total_rows |
| 重复 (site_id, arrival_ts_utc) | 0 | total_rows |
| 负 duration | 1 | parseable_rows |
| dwell_min 与时间戳不一致 | 1 | rows_with_dwell_min |
| 跨日事件（day_local ≠ 到达日） | 1 | parseable_rows |
| 容量冲突样本 | 1 | parseable_rows |
| 空或 <=0 的 site_capacity | 1 | total_rows |
| 时间戳无法解析 | 1 | total_rows |

### 缺失必填字段（按列）

| 列 | 缺失数 |
|---|---|
| site_id | 0 |
| event_id | 0 |
| arrival_ts_utc | 0 |
| departure_ts_utc | 0 |
| dwell_min | 0 |
| site_capacity | 1 |
| day_local | 0 |
| arrival_local_hour | 0 |
| source_dataset | 0 |
| source_row | 0 |

### 每场站事件数

| site_id | 事件数 |
|---|---|
| A | 7 |
| B | 4 |
| C | 4 |
| D | 2 |
| E | 2 |

### 每日本地完整 24h 覆盖日（site@day → 是否覆盖 0..23 全部小时）

| site@day_local | 完整覆盖 |
|---|---|
| 2026-05-01@A | 否 |
| 2026-05-02@A | 否 |
| 2026-05-01@B | 否 |
| 2026-05-01@C | 否 |
| 2026-05-02@C | 否 |
| 2026-05-01@D | 否 |
| 2026-05-01@E | 否 |

### 停留时长分位数（分钟，分母 = rows_with_dwell_min = 19）

| p50 | p90 | p99 | max |
|---|---|---|---|
| 60.0 | 90.0 | 90.0 | 90.0 |

### arrival_local_hour 分布（24 桶，分母 = total_rows）

| hour | count |
|---|---|
| 0 | 0 |
| 1 | 0 |
| 2 | 0 |
| 3 | 0 |
| 4 | 0 |
| 5 | 0 |
| 6 | 2 |
| 7 | 1 |
| 8 | 2 |
| 9 | 3 |
| 10 | 2 |
| 11 | 1 |
| 12 | 1 |
| 13 | 1 |
| 14 | 2 |
| 15 | 1 |
| 16 | 0 |
| 17 | 0 |
| 18 | 1 |
| 19 | 0 |
| 20 | 1 |
| 21 | 0 |
| 22 | 0 |
| 23 | 1 |

## 分母说明

缺失/重复计数分母为 total_rows；负时长、dwell 不一致、跨日、时间戳不可解析、容量冲突分母为 parseable_rows（两时间戳均可解析的行）；分位数分母为 rows_with_dwell_min；hour 分布分母为 total_rows。

