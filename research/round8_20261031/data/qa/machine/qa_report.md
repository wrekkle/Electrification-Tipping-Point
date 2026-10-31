# 数据集 QA 报告

- 输入: C:\Projects\停车场充电桩优化方案\research\round8_20261031\data\processed\contract_events.csv
- 生成时间: 2026-10-31 19:39
- 总行数: 185550
- 可解析行（两时间戳均可解析）: 185550

## 逐项计数（分母见末节）

| 指标 | 值 | 分母 |
|---|---|---|
| 总行数 | 185550 | — |
| 缺失必填字段合计 | 0 | total_rows × 10 列 |
| 重复 event_id | 0 | total_rows |
| 重复 (site_id, arrival_ts_utc) | 6414 | total_rows |
| 负 duration | 0 | parseable_rows |
| dwell_min 与时间戳不一致 | 0 | rows_with_dwell_min |
| 跨日事件（day_local ≠ 到达日） | 0 | parseable_rows |
| 容量冲突样本 | 19 | parseable_rows |
| 空或 <=0 的 site_capacity | 0 | total_rows |
| 时间戳无法解析 | 0 | total_rows |

### 缺失必填字段（按列）

| 列 | 缺失数 |
|---|---|
| site_id | 0 |
| event_id | 0 |
| arrival_ts_utc | 0 |
| departure_ts_utc | 0 |
| dwell_min | 0 |
| site_capacity | 0 |
| day_local | 0 |
| arrival_local_hour | 0 |
| source_dataset | 0 |
| source_row | 0 |

### 每场站事件数

| site_id | 事件数 |
|---|---|
| Drummond | 13634 |
| Hyatt | 14295 |
| Jolimont | 25765 |
| Princes Theatre | 13115 |
| Queensberry | 34566 |
| Southbank | 24399 |
| Titles | 9923 |
| University | 20424 |
| Victoria Market | 24891 |
| West Melbourne | 4538 |

### 每日本地完整 24h 覆盖日（site@day → 是否覆盖 0..23 全部小时）

| site@day_local | 完整覆盖 |
|---|---|
| 2014-01-06@Drummond | 否 |
| 2014-01-07@Drummond | 否 |
| 2014-01-08@Drummond | 否 |
| 2014-01-09@Drummond | 否 |
| 2014-01-10@Drummond | 否 |
| 2014-01-11@Drummond | 否 |
| 2014-01-13@Drummond | 否 |
| 2014-01-14@Drummond | 否 |
| 2014-01-15@Drummond | 否 |
| 2014-01-16@Drummond | 否 |
| 2014-01-17@Drummond | 否 |
| 2014-01-18@Drummond | 否 |
| 2014-01-20@Drummond | 否 |
| 2014-01-21@Drummond | 否 |
| 2014-01-22@Drummond | 否 |
| 2014-01-23@Drummond | 否 |
| 2014-01-24@Drummond | 否 |
| 2014-01-25@Drummond | 否 |
| 2014-01-27@Drummond | 否 |
| 2014-01-28@Drummond | 否 |
| 2014-01-29@Drummond | 否 |
| 2014-01-30@Drummond | 否 |
| 2014-01-31@Drummond | 否 |
| 2014-02-01@Drummond | 否 |
| 2014-02-03@Drummond | 否 |
| 2014-02-04@Drummond | 否 |
| 2014-02-05@Drummond | 否 |
| 2014-02-06@Drummond | 否 |
| 2014-02-07@Drummond | 否 |
| 2014-02-08@Drummond | 否 |
| 2014-02-10@Drummond | 否 |
| 2014-02-11@Drummond | 否 |
| 2014-02-12@Drummond | 否 |
| 2014-02-13@Drummond | 否 |
| 2014-02-14@Drummond | 否 |
| 2014-02-15@Drummond | 否 |
| 2014-02-17@Drummond | 否 |
| 2014-02-18@Drummond | 否 |
| 2014-02-19@Drummond | 否 |
| 2014-02-20@Drummond | 否 |
| 2014-02-21@Drummond | 否 |
| 2014-02-22@Drummond | 否 |
| 2014-02-24@Drummond | 否 |
| 2014-02-25@Drummond | 否 |
| 2014-02-26@Drummond | 否 |
| 2014-02-27@Drummond | 否 |
| 2014-02-28@Drummond | 否 |
| 2014-03-01@Drummond | 否 |
| 2014-03-03@Drummond | 否 |
| 2014-03-04@Drummond | 否 |
| 2014-03-05@Drummond | 否 |
| 2014-03-06@Drummond | 否 |
| 2014-03-07@Drummond | 否 |
| 2014-03-08@Drummond | 否 |
| 2014-03-10@Drummond | 否 |
| 2014-03-11@Drummond | 否 |
| 2014-03-12@Drummond | 否 |
| 2014-03-13@Drummond | 否 |
| 2014-03-14@Drummond | 否 |
| 2014-03-15@Drummond | 否 |
| 2014-03-17@Drummond | 否 |
| 2014-03-18@Drummond | 否 |
| 2014-03-19@Drummond | 否 |
| 2014-03-20@Drummond | 否 |
| 2014-03-21@Drummond | 否 |
| 2014-03-22@Drummond | 否 |
| 2014-03-24@Drummond | 否 |
| 2014-03-25@Drummond | 否 |
| 2014-03-26@Drummond | 否 |
| 2014-03-27@Drummond | 否 |
| 2014-03-28@Drummond | 否 |
| 2014-03-29@Drummond | 否 |
| 2014-03-31@Drummond | 否 |
| 2014-01-06@Hyatt | 否 |
| 2014-01-07@Hyatt | 否 |
| 2014-01-08@Hyatt | 否 |
| 2014-01-09@Hyatt | 否 |
| 2014-01-10@Hyatt | 否 |
| 2014-01-11@Hyatt | 否 |
| 2014-01-12@Hyatt | 否 |
| 2014-01-13@Hyatt | 否 |
| 2014-01-14@Hyatt | 否 |
| 2014-01-15@Hyatt | 否 |
| 2014-01-16@Hyatt | 否 |
| 2014-01-17@Hyatt | 否 |
| 2014-01-18@Hyatt | 否 |
| 2014-01-19@Hyatt | 否 |
| 2014-01-20@Hyatt | 否 |
| 2014-01-21@Hyatt | 否 |
| 2014-01-22@Hyatt | 否 |
| 2014-01-23@Hyatt | 否 |
| 2014-01-24@Hyatt | 否 |
| 2014-01-25@Hyatt | 否 |
| 2014-01-26@Hyatt | 否 |
| 2014-01-27@Hyatt | 否 |
| 2014-01-28@Hyatt | 否 |
| 2014-01-29@Hyatt | 否 |
| 2014-01-30@Hyatt | 否 |
| 2014-01-31@Hyatt | 否 |
| 2014-02-01@Hyatt | 否 |
| 2014-02-02@Hyatt | 否 |
| 2014-02-03@Hyatt | 否 |
| 2014-02-04@Hyatt | 否 |
| 2014-02-05@Hyatt | 否 |
| 2014-02-06@Hyatt | 否 |
| 2014-02-07@Hyatt | 否 |
| 2014-02-08@Hyatt | 否 |
| 2014-02-09@Hyatt | 否 |
| 2014-02-10@Hyatt | 否 |
| 2014-02-11@Hyatt | 否 |
| 2014-02-12@Hyatt | 否 |
| 2014-02-13@Hyatt | 否 |
| 2014-02-14@Hyatt | 否 |
| 2014-02-15@Hyatt | 否 |
| 2014-02-16@Hyatt | 否 |
| 2014-02-17@Hyatt | 否 |
| 2014-02-18@Hyatt | 否 |
| 2014-02-19@Hyatt | 否 |
| 2014-02-20@Hyatt | 否 |
| 2014-02-21@Hyatt | 否 |
| 2014-02-22@Hyatt | 否 |
| 2014-02-23@Hyatt | 否 |
| 2014-02-24@Hyatt | 否 |
| 2014-02-25@Hyatt | 否 |
| 2014-02-26@Hyatt | 否 |
| 2014-02-27@Hyatt | 否 |
| 2014-02-28@Hyatt | 否 |
| 2014-03-01@Hyatt | 否 |
| 2014-03-02@Hyatt | 否 |
| 2014-03-03@Hyatt | 否 |
| 2014-03-04@Hyatt | 否 |
| 2014-03-05@Hyatt | 否 |
| 2014-03-06@Hyatt | 否 |
| 2014-03-07@Hyatt | 否 |
| 2014-03-08@Hyatt | 否 |
| 2014-03-09@Hyatt | 否 |
| 2014-03-10@Hyatt | 否 |
| 2014-03-11@Hyatt | 否 |
| 2014-03-12@Hyatt | 否 |
| 2014-03-13@Hyatt | 否 |
| 2014-03-14@Hyatt | 否 |
| 2014-03-15@Hyatt | 否 |
| 2014-03-16@Hyatt | 否 |
| 2014-03-17@Hyatt | 否 |
| 2014-03-18@Hyatt | 否 |
| 2014-03-19@Hyatt | 否 |
| 2014-03-20@Hyatt | 否 |
| 2014-03-21@Hyatt | 否 |
| 2014-03-22@Hyatt | 否 |
| 2014-03-23@Hyatt | 否 |
| 2014-03-24@Hyatt | 否 |
| 2014-03-25@Hyatt | 否 |
| 2014-03-26@Hyatt | 否 |
| 2014-03-27@Hyatt | 否 |
| 2014-03-28@Hyatt | 否 |
| 2014-03-29@Hyatt | 否 |
| 2014-03-30@Hyatt | 否 |
| 2014-03-31@Hyatt | 否 |
| 2014-01-06@Jolimont | 否 |
| 2014-01-07@Jolimont | 否 |
| 2014-01-08@Jolimont | 否 |
| 2014-01-09@Jolimont | 否 |
| 2014-01-10@Jolimont | 否 |
| 2014-01-11@Jolimont | 否 |
| 2014-01-12@Jolimont | 否 |
| 2014-01-13@Jolimont | 否 |
| 2014-01-14@Jolimont | 否 |
| 2014-01-15@Jolimont | 否 |
| 2014-01-16@Jolimont | 否 |
| 2014-01-17@Jolimont | 否 |
| 2014-01-18@Jolimont | 否 |
| 2014-01-19@Jolimont | 否 |
| 2014-01-20@Jolimont | 否 |
| 2014-01-21@Jolimont | 否 |
| 2014-01-22@Jolimont | 否 |
| 2014-01-23@Jolimont | 否 |
| 2014-01-24@Jolimont | 否 |
| 2014-01-25@Jolimont | 否 |
| 2014-01-26@Jolimont | 否 |
| 2014-01-27@Jolimont | 否 |
| 2014-01-28@Jolimont | 否 |
| 2014-01-29@Jolimont | 否 |
| 2014-01-30@Jolimont | 否 |
| 2014-01-31@Jolimont | 否 |
| 2014-02-01@Jolimont | 否 |
| 2014-02-02@Jolimont | 否 |
| 2014-02-03@Jolimont | 否 |
| 2014-02-04@Jolimont | 否 |
| 2014-02-05@Jolimont | 否 |
| 2014-02-06@Jolimont | 否 |
| 2014-02-07@Jolimont | 否 |
| 2014-02-08@Jolimont | 否 |
| 2014-02-09@Jolimont | 否 |
| 2014-02-10@Jolimont | 否 |
| 2014-02-11@Jolimont | 否 |
| 2014-02-12@Jolimont | 否 |
| 2014-02-13@Jolimont | 否 |
| 2014-02-14@Jolimont | 否 |
| 2014-02-15@Jolimont | 否 |
| 2014-02-16@Jolimont | 否 |
| 2014-02-17@Jolimont | 否 |
| 2014-02-18@Jolimont | 否 |
| 2014-02-19@Jolimont | 否 |
| 2014-02-20@Jolimont | 否 |
| 2014-02-21@Jolimont | 否 |
| 2014-02-22@Jolimont | 否 |
| 2014-02-23@Jolimont | 否 |
| 2014-02-24@Jolimont | 否 |
| 2014-02-25@Jolimont | 否 |
| 2014-02-26@Jolimont | 否 |
| 2014-02-27@Jolimont | 否 |
| 2014-02-28@Jolimont | 否 |
| 2014-03-01@Jolimont | 否 |
| 2014-03-02@Jolimont | 否 |
| 2014-03-03@Jolimont | 否 |
| 2014-03-04@Jolimont | 否 |
| 2014-03-05@Jolimont | 否 |
| 2014-03-06@Jolimont | 否 |
| 2014-03-07@Jolimont | 否 |
| 2014-03-08@Jolimont | 否 |
| 2014-03-09@Jolimont | 否 |
| 2014-03-10@Jolimont | 否 |
| 2014-03-11@Jolimont | 否 |
| 2014-03-12@Jolimont | 否 |
| 2014-03-13@Jolimont | 否 |
| 2014-03-14@Jolimont | 否 |
| 2014-03-15@Jolimont | 否 |
| 2014-03-16@Jolimont | 否 |
| 2014-03-17@Jolimont | 否 |
| 2014-03-18@Jolimont | 否 |
| 2014-03-19@Jolimont | 否 |
| 2014-03-20@Jolimont | 否 |
| 2014-03-21@Jolimont | 否 |
| 2014-03-22@Jolimont | 否 |
| 2014-03-23@Jolimont | 否 |
| 2014-03-24@Jolimont | 否 |
| 2014-03-25@Jolimont | 否 |
| 2014-03-26@Jolimont | 否 |
| 2014-03-27@Jolimont | 否 |
| 2014-03-28@Jolimont | 否 |
| 2014-03-29@Jolimont | 否 |
| 2014-03-30@Jolimont | 否 |
| 2014-03-31@Jolimont | 否 |
| 2014-01-06@Princes Theatre | 否 |
| 2014-01-07@Princes Theatre | 否 |
| 2014-01-08@Princes Theatre | 否 |
| 2014-01-09@Princes Theatre | 否 |
| 2014-01-10@Princes Theatre | 否 |
| 2014-01-11@Princes Theatre | 否 |
| 2014-01-12@Princes Theatre | 否 |
| 2014-01-13@Princes Theatre | 否 |
| 2014-01-14@Princes Theatre | 否 |
| 2014-01-15@Princes Theatre | 否 |
| 2014-01-16@Princes Theatre | 否 |
| 2014-01-17@Princes Theatre | 否 |
| 2014-01-18@Princes Theatre | 否 |
| 2014-01-19@Princes Theatre | 否 |
| 2014-01-20@Princes Theatre | 否 |
| 2014-01-21@Princes Theatre | 否 |
| 2014-01-22@Princes Theatre | 否 |
| 2014-01-23@Princes Theatre | 否 |
| 2014-01-24@Princes Theatre | 否 |
| 2014-01-25@Princes Theatre | 否 |
| 2014-01-26@Princes Theatre | 否 |
| 2014-01-27@Princes Theatre | 否 |
| 2014-01-28@Princes Theatre | 否 |
| 2014-01-29@Princes Theatre | 否 |
| 2014-01-30@Princes Theatre | 否 |
| 2014-01-31@Princes Theatre | 否 |
| 2014-02-01@Princes Theatre | 否 |
| 2014-02-02@Princes Theatre | 否 |
| 2014-02-03@Princes Theatre | 否 |
| 2014-02-04@Princes Theatre | 否 |
| 2014-02-05@Princes Theatre | 否 |
| 2014-02-06@Princes Theatre | 否 |
| 2014-02-07@Princes Theatre | 否 |
| 2014-02-08@Princes Theatre | 否 |
| 2014-02-09@Princes Theatre | 否 |
| 2014-02-10@Princes Theatre | 否 |
| 2014-02-11@Princes Theatre | 否 |
| 2014-02-12@Princes Theatre | 否 |
| 2014-02-13@Princes Theatre | 否 |
| 2014-02-14@Princes Theatre | 否 |
| 2014-02-15@Princes Theatre | 否 |
| 2014-02-16@Princes Theatre | 否 |
| 2014-02-17@Princes Theatre | 否 |
| 2014-02-18@Princes Theatre | 否 |
| 2014-02-19@Princes Theatre | 否 |
| 2014-02-20@Princes Theatre | 否 |
| 2014-02-21@Princes Theatre | 否 |
| 2014-02-22@Princes Theatre | 否 |
| 2014-02-23@Princes Theatre | 否 |
| 2014-02-24@Princes Theatre | 否 |
| 2014-02-25@Princes Theatre | 否 |
| 2014-02-26@Princes Theatre | 否 |
| 2014-02-27@Princes Theatre | 否 |
| 2014-02-28@Princes Theatre | 否 |
| 2014-03-01@Princes Theatre | 否 |
| 2014-03-02@Princes Theatre | 否 |
| 2014-03-03@Princes Theatre | 否 |
| 2014-03-04@Princes Theatre | 否 |
| 2014-03-05@Princes Theatre | 否 |
| 2014-03-06@Princes Theatre | 否 |
| 2014-03-07@Princes Theatre | 否 |
| 2014-03-08@Princes Theatre | 否 |
| 2014-03-09@Princes Theatre | 否 |
| 2014-03-10@Princes Theatre | 否 |
| 2014-03-11@Princes Theatre | 否 |
| 2014-03-12@Princes Theatre | 否 |
| 2014-03-13@Princes Theatre | 否 |
| 2014-03-14@Princes Theatre | 否 |
| 2014-03-15@Princes Theatre | 否 |
| 2014-03-16@Princes Theatre | 否 |
| 2014-03-17@Princes Theatre | 否 |
| 2014-03-18@Princes Theatre | 否 |
| 2014-03-19@Princes Theatre | 否 |
| 2014-03-20@Princes Theatre | 否 |
| 2014-03-21@Princes Theatre | 否 |
| 2014-03-22@Princes Theatre | 否 |
| 2014-03-23@Princes Theatre | 否 |
| 2014-03-24@Princes Theatre | 否 |
| 2014-03-25@Princes Theatre | 否 |
| 2014-03-26@Princes Theatre | 否 |
| 2014-03-27@Princes Theatre | 否 |
| 2014-03-28@Princes Theatre | 否 |
| 2014-03-29@Princes Theatre | 否 |
| 2014-03-30@Princes Theatre | 否 |
| 2014-03-31@Princes Theatre | 否 |
| 2014-01-06@Queensberry | 否 |
| 2014-01-07@Queensberry | 否 |
| 2014-01-08@Queensberry | 否 |
| 2014-01-09@Queensberry | 否 |
| 2014-01-10@Queensberry | 否 |
| 2014-01-11@Queensberry | 否 |
| 2014-01-12@Queensberry | 否 |
| 2014-01-13@Queensberry | 否 |
| 2014-01-14@Queensberry | 否 |
| 2014-01-15@Queensberry | 否 |
| 2014-01-16@Queensberry | 否 |
| 2014-01-17@Queensberry | 否 |
| 2014-01-18@Queensberry | 否 |
| 2014-01-19@Queensberry | 否 |
| 2014-01-20@Queensberry | 否 |
| 2014-01-21@Queensberry | 否 |
| 2014-01-22@Queensberry | 否 |
| 2014-01-23@Queensberry | 否 |
| 2014-01-24@Queensberry | 否 |
| 2014-01-25@Queensberry | 否 |
| 2014-01-26@Queensberry | 否 |
| 2014-01-27@Queensberry | 否 |
| 2014-01-28@Queensberry | 否 |
| 2014-01-29@Queensberry | 否 |
| 2014-01-30@Queensberry | 否 |
| 2014-01-31@Queensberry | 否 |
| 2014-02-01@Queensberry | 否 |
| 2014-02-02@Queensberry | 否 |
| 2014-02-03@Queensberry | 否 |
| 2014-02-04@Queensberry | 否 |
| 2014-02-05@Queensberry | 否 |
| 2014-02-06@Queensberry | 否 |
| 2014-02-07@Queensberry | 否 |
| 2014-02-08@Queensberry | 否 |
| 2014-02-09@Queensberry | 否 |
| 2014-02-10@Queensberry | 否 |
| 2014-02-11@Queensberry | 否 |
| 2014-02-12@Queensberry | 否 |
| 2014-02-13@Queensberry | 否 |
| 2014-02-14@Queensberry | 否 |
| 2014-02-15@Queensberry | 否 |
| 2014-02-16@Queensberry | 否 |
| 2014-02-17@Queensberry | 否 |
| 2014-02-18@Queensberry | 否 |
| 2014-02-19@Queensberry | 否 |
| 2014-02-20@Queensberry | 否 |
| 2014-02-21@Queensberry | 否 |
| 2014-02-22@Queensberry | 否 |
| 2014-02-23@Queensberry | 否 |
| 2014-02-24@Queensberry | 否 |
| 2014-02-25@Queensberry | 否 |
| 2014-02-26@Queensberry | 否 |
| 2014-02-27@Queensberry | 否 |
| 2014-02-28@Queensberry | 否 |
| 2014-03-01@Queensberry | 否 |
| 2014-03-02@Queensberry | 否 |
| 2014-03-03@Queensberry | 否 |
| 2014-03-04@Queensberry | 否 |
| 2014-03-05@Queensberry | 否 |
| 2014-03-06@Queensberry | 否 |
| 2014-03-07@Queensberry | 否 |
| 2014-03-08@Queensberry | 否 |
| 2014-03-09@Queensberry | 否 |
| 2014-03-10@Queensberry | 否 |
| 2014-03-11@Queensberry | 否 |
| 2014-03-12@Queensberry | 否 |
| 2014-03-13@Queensberry | 否 |
| 2014-03-14@Queensberry | 否 |
| 2014-03-15@Queensberry | 否 |
| 2014-03-16@Queensberry | 否 |
| 2014-03-17@Queensberry | 否 |
| 2014-03-18@Queensberry | 否 |
| 2014-03-19@Queensberry | 否 |
| 2014-03-20@Queensberry | 否 |
| 2014-03-21@Queensberry | 否 |
| 2014-03-22@Queensberry | 否 |
| 2014-03-23@Queensberry | 否 |
| 2014-03-24@Queensberry | 否 |
| 2014-03-25@Queensberry | 否 |
| 2014-03-26@Queensberry | 否 |
| 2014-03-27@Queensberry | 否 |
| 2014-03-28@Queensberry | 否 |
| 2014-03-29@Queensberry | 否 |
| 2014-03-30@Queensberry | 否 |
| 2014-03-31@Queensberry | 否 |
| 2014-01-06@Southbank | 否 |
| 2014-01-07@Southbank | 否 |
| 2014-01-08@Southbank | 否 |
| 2014-01-09@Southbank | 否 |
| 2014-01-10@Southbank | 否 |
| 2014-01-11@Southbank | 否 |
| 2014-01-12@Southbank | 否 |
| 2014-01-13@Southbank | 否 |
| 2014-01-14@Southbank | 否 |
| 2014-01-15@Southbank | 否 |
| 2014-01-16@Southbank | 否 |
| 2014-01-17@Southbank | 否 |
| 2014-01-18@Southbank | 否 |
| 2014-01-19@Southbank | 否 |
| 2014-01-20@Southbank | 否 |
| 2014-01-21@Southbank | 否 |
| 2014-01-22@Southbank | 否 |
| 2014-01-23@Southbank | 否 |
| 2014-01-24@Southbank | 否 |
| 2014-01-25@Southbank | 否 |
| 2014-01-26@Southbank | 否 |
| 2014-01-27@Southbank | 否 |
| 2014-01-28@Southbank | 否 |
| 2014-01-29@Southbank | 否 |
| 2014-01-30@Southbank | 否 |
| 2014-01-31@Southbank | 否 |
| 2014-02-01@Southbank | 否 |
| 2014-02-02@Southbank | 否 |
| 2014-02-03@Southbank | 否 |
| 2014-02-04@Southbank | 否 |
| 2014-02-05@Southbank | 否 |
| 2014-02-06@Southbank | 否 |
| 2014-02-07@Southbank | 否 |
| 2014-02-08@Southbank | 否 |
| 2014-02-09@Southbank | 否 |
| 2014-02-10@Southbank | 否 |
| 2014-02-11@Southbank | 否 |
| 2014-02-12@Southbank | 否 |
| 2014-02-13@Southbank | 否 |
| 2014-02-14@Southbank | 否 |
| 2014-02-15@Southbank | 否 |
| 2014-02-16@Southbank | 否 |
| 2014-02-17@Southbank | 否 |
| 2014-02-18@Southbank | 否 |
| 2014-02-19@Southbank | 否 |
| 2014-02-20@Southbank | 否 |
| 2014-02-21@Southbank | 否 |
| 2014-02-22@Southbank | 否 |
| 2014-02-23@Southbank | 否 |
| 2014-02-24@Southbank | 否 |
| 2014-02-25@Southbank | 否 |
| 2014-02-26@Southbank | 否 |
| 2014-02-27@Southbank | 否 |
| 2014-02-28@Southbank | 否 |
| 2014-03-01@Southbank | 否 |
| 2014-03-02@Southbank | 否 |
| 2014-03-03@Southbank | 否 |
| 2014-03-04@Southbank | 否 |
| 2014-03-05@Southbank | 否 |
| 2014-03-06@Southbank | 否 |
| 2014-03-07@Southbank | 否 |
| 2014-03-08@Southbank | 否 |
| 2014-03-09@Southbank | 否 |
| 2014-03-10@Southbank | 否 |
| 2014-03-11@Southbank | 否 |
| 2014-03-12@Southbank | 否 |
| 2014-03-13@Southbank | 否 |
| 2014-03-14@Southbank | 否 |
| 2014-03-15@Southbank | 否 |
| 2014-03-16@Southbank | 否 |
| 2014-03-17@Southbank | 否 |
| 2014-03-18@Southbank | 否 |
| 2014-03-19@Southbank | 否 |
| 2014-03-20@Southbank | 否 |
| 2014-03-21@Southbank | 否 |
| 2014-03-22@Southbank | 否 |
| 2014-03-23@Southbank | 否 |
| 2014-03-24@Southbank | 否 |
| 2014-03-25@Southbank | 否 |
| 2014-03-26@Southbank | 否 |
| 2014-03-27@Southbank | 否 |
| 2014-03-28@Southbank | 否 |
| 2014-03-29@Southbank | 否 |
| 2014-03-30@Southbank | 否 |
| 2014-03-31@Southbank | 否 |
| 2014-01-06@Titles | 否 |
| 2014-01-07@Titles | 否 |
| 2014-01-08@Titles | 否 |
| 2014-01-09@Titles | 否 |
| 2014-01-10@Titles | 否 |
| 2014-01-11@Titles | 否 |
| 2014-01-12@Titles | 否 |
| 2014-01-13@Titles | 否 |
| 2014-01-14@Titles | 否 |
| 2014-01-15@Titles | 否 |
| 2014-01-16@Titles | 否 |
| 2014-01-17@Titles | 否 |
| 2014-01-18@Titles | 否 |
| 2014-01-19@Titles | 否 |
| 2014-01-20@Titles | 否 |
| 2014-01-21@Titles | 否 |
| 2014-01-22@Titles | 否 |
| 2014-01-23@Titles | 否 |
| 2014-01-24@Titles | 否 |
| 2014-01-25@Titles | 否 |
| 2014-01-26@Titles | 否 |
| 2014-01-27@Titles | 否 |
| 2014-01-28@Titles | 否 |
| 2014-01-29@Titles | 否 |
| 2014-01-30@Titles | 否 |
| 2014-01-31@Titles | 否 |
| 2014-02-01@Titles | 否 |
| 2014-02-02@Titles | 否 |
| 2014-02-03@Titles | 否 |
| 2014-02-04@Titles | 否 |
| 2014-02-05@Titles | 否 |
| 2014-02-06@Titles | 否 |
| 2014-02-07@Titles | 否 |
| 2014-02-08@Titles | 否 |
| 2014-02-09@Titles | 否 |
| 2014-02-10@Titles | 否 |
| 2014-02-11@Titles | 否 |
| 2014-02-12@Titles | 否 |
| 2014-02-13@Titles | 否 |
| 2014-02-14@Titles | 否 |
| 2014-02-15@Titles | 否 |
| 2014-02-16@Titles | 否 |
| 2014-02-17@Titles | 否 |
| 2014-02-18@Titles | 否 |
| 2014-02-19@Titles | 否 |
| 2014-02-20@Titles | 否 |
| 2014-02-21@Titles | 否 |
| 2014-02-22@Titles | 否 |
| 2014-02-23@Titles | 否 |
| 2014-02-24@Titles | 否 |
| 2014-02-25@Titles | 否 |
| 2014-02-26@Titles | 否 |
| 2014-02-27@Titles | 否 |
| 2014-02-28@Titles | 否 |
| 2014-03-01@Titles | 否 |
| 2014-03-02@Titles | 否 |
| 2014-03-03@Titles | 否 |
| 2014-03-04@Titles | 否 |
| 2014-03-05@Titles | 否 |
| 2014-03-06@Titles | 否 |
| 2014-03-07@Titles | 否 |
| 2014-03-08@Titles | 否 |
| 2014-03-09@Titles | 否 |
| 2014-03-10@Titles | 否 |
| 2014-03-11@Titles | 否 |
| 2014-03-12@Titles | 否 |
| 2014-03-13@Titles | 否 |
| 2014-03-14@Titles | 否 |
| 2014-03-15@Titles | 否 |
| 2014-03-16@Titles | 否 |
| 2014-03-17@Titles | 否 |
| 2014-03-18@Titles | 否 |
| 2014-03-19@Titles | 否 |
| 2014-03-20@Titles | 否 |
| 2014-03-21@Titles | 否 |
| 2014-03-22@Titles | 否 |
| 2014-03-23@Titles | 否 |
| 2014-03-24@Titles | 否 |
| 2014-03-25@Titles | 否 |
| 2014-03-26@Titles | 否 |
| 2014-03-27@Titles | 否 |
| 2014-03-28@Titles | 否 |
| 2014-03-29@Titles | 否 |
| 2014-03-30@Titles | 否 |
| 2014-03-31@Titles | 否 |
| 2014-01-06@University | 否 |
| 2014-01-07@University | 否 |
| 2014-01-08@University | 否 |
| 2014-01-09@University | 否 |
| 2014-01-10@University | 否 |
| 2014-01-11@University | 否 |
| 2014-01-13@University | 否 |
| 2014-01-14@University | 否 |
| 2014-01-15@University | 否 |
| 2014-01-16@University | 否 |
| 2014-01-17@University | 否 |
| 2014-01-18@University | 否 |
| 2014-01-20@University | 否 |
| 2014-01-21@University | 否 |
| 2014-01-22@University | 否 |
| 2014-01-23@University | 否 |
| 2014-01-24@University | 否 |
| 2014-01-25@University | 否 |
| 2014-01-27@University | 否 |
| 2014-01-28@University | 否 |
| 2014-01-29@University | 否 |
| 2014-01-30@University | 否 |
| 2014-01-31@University | 否 |
| 2014-02-01@University | 否 |
| 2014-02-03@University | 否 |
| 2014-02-04@University | 否 |
| 2014-02-05@University | 否 |
| 2014-02-06@University | 否 |
| 2014-02-07@University | 否 |
| 2014-02-08@University | 否 |
| 2014-02-10@University | 否 |
| 2014-02-11@University | 否 |
| 2014-02-12@University | 否 |
| 2014-02-13@University | 否 |
| 2014-02-14@University | 否 |
| 2014-02-15@University | 否 |
| 2014-02-17@University | 否 |
| 2014-02-18@University | 否 |
| 2014-02-19@University | 否 |
| 2014-02-20@University | 否 |
| 2014-02-21@University | 否 |
| 2014-02-22@University | 否 |
| 2014-02-24@University | 否 |
| 2014-02-25@University | 否 |
| 2014-02-26@University | 否 |
| 2014-02-27@University | 否 |
| 2014-02-28@University | 否 |
| 2014-03-01@University | 否 |
| 2014-03-03@University | 否 |
| 2014-03-04@University | 否 |
| 2014-03-05@University | 否 |
| 2014-03-06@University | 否 |
| 2014-03-07@University | 否 |
| 2014-03-08@University | 否 |
| 2014-03-10@University | 否 |
| 2014-03-11@University | 否 |
| 2014-03-12@University | 否 |
| 2014-03-13@University | 否 |
| 2014-03-14@University | 否 |
| 2014-03-15@University | 否 |
| 2014-03-17@University | 否 |
| 2014-03-18@University | 否 |
| 2014-03-19@University | 否 |
| 2014-03-20@University | 否 |
| 2014-03-21@University | 否 |
| 2014-03-22@University | 否 |
| 2014-03-24@University | 否 |
| 2014-03-25@University | 否 |
| 2014-03-26@University | 否 |
| 2014-03-27@University | 否 |
| 2014-03-28@University | 否 |
| 2014-03-29@University | 否 |
| 2014-03-31@University | 否 |
| 2014-01-06@Victoria Market | 否 |
| 2014-01-07@Victoria Market | 否 |
| 2014-01-08@Victoria Market | 否 |
| 2014-01-09@Victoria Market | 否 |
| 2014-01-10@Victoria Market | 否 |
| 2014-01-11@Victoria Market | 否 |
| 2014-01-12@Victoria Market | 否 |
| 2014-01-13@Victoria Market | 否 |
| 2014-01-14@Victoria Market | 否 |
| 2014-01-15@Victoria Market | 否 |
| 2014-01-16@Victoria Market | 否 |
| 2014-01-17@Victoria Market | 否 |
| 2014-01-18@Victoria Market | 否 |
| 2014-01-19@Victoria Market | 否 |
| 2014-01-20@Victoria Market | 否 |
| 2014-01-21@Victoria Market | 否 |
| 2014-01-22@Victoria Market | 否 |
| 2014-01-23@Victoria Market | 否 |
| 2014-01-24@Victoria Market | 否 |
| 2014-01-25@Victoria Market | 否 |
| 2014-01-26@Victoria Market | 否 |
| 2014-01-27@Victoria Market | 否 |
| 2014-01-28@Victoria Market | 否 |
| 2014-01-29@Victoria Market | 否 |
| 2014-01-30@Victoria Market | 否 |
| 2014-01-31@Victoria Market | 否 |
| 2014-02-01@Victoria Market | 否 |
| 2014-02-02@Victoria Market | 否 |
| 2014-02-03@Victoria Market | 否 |
| 2014-02-04@Victoria Market | 否 |
| 2014-02-05@Victoria Market | 否 |
| 2014-02-06@Victoria Market | 否 |
| 2014-02-07@Victoria Market | 否 |
| 2014-02-08@Victoria Market | 否 |
| 2014-02-09@Victoria Market | 否 |
| 2014-02-10@Victoria Market | 否 |
| 2014-02-11@Victoria Market | 否 |
| 2014-02-12@Victoria Market | 否 |
| 2014-02-13@Victoria Market | 否 |
| 2014-02-14@Victoria Market | 否 |
| 2014-02-15@Victoria Market | 否 |
| 2014-02-16@Victoria Market | 否 |
| 2014-02-17@Victoria Market | 否 |
| 2014-02-18@Victoria Market | 否 |
| 2014-02-19@Victoria Market | 否 |
| 2014-02-20@Victoria Market | 否 |
| 2014-02-21@Victoria Market | 否 |
| 2014-02-22@Victoria Market | 否 |
| 2014-02-23@Victoria Market | 否 |
| 2014-02-24@Victoria Market | 否 |
| 2014-02-25@Victoria Market | 否 |
| 2014-02-26@Victoria Market | 否 |
| 2014-02-27@Victoria Market | 否 |
| 2014-02-28@Victoria Market | 否 |
| 2014-03-01@Victoria Market | 否 |
| 2014-03-02@Victoria Market | 否 |
| 2014-03-03@Victoria Market | 否 |
| 2014-03-04@Victoria Market | 否 |
| 2014-03-05@Victoria Market | 否 |
| 2014-03-06@Victoria Market | 否 |
| 2014-03-07@Victoria Market | 否 |
| 2014-03-08@Victoria Market | 否 |
| 2014-03-09@Victoria Market | 否 |
| 2014-03-10@Victoria Market | 否 |
| 2014-03-11@Victoria Market | 否 |
| 2014-03-12@Victoria Market | 否 |
| 2014-03-13@Victoria Market | 否 |
| 2014-03-14@Victoria Market | 否 |
| 2014-03-15@Victoria Market | 否 |
| 2014-03-16@Victoria Market | 否 |
| 2014-03-17@Victoria Market | 否 |
| 2014-03-18@Victoria Market | 否 |
| 2014-03-19@Victoria Market | 否 |
| 2014-03-20@Victoria Market | 否 |
| 2014-03-21@Victoria Market | 否 |
| 2014-03-22@Victoria Market | 否 |
| 2014-03-23@Victoria Market | 否 |
| 2014-03-24@Victoria Market | 否 |
| 2014-03-25@Victoria Market | 否 |
| 2014-03-26@Victoria Market | 否 |
| 2014-03-27@Victoria Market | 否 |
| 2014-03-28@Victoria Market | 否 |
| 2014-03-29@Victoria Market | 否 |
| 2014-03-30@Victoria Market | 否 |
| 2014-03-31@Victoria Market | 否 |
| 2014-01-06@West Melbourne | 否 |
| 2014-01-07@West Melbourne | 否 |
| 2014-01-08@West Melbourne | 否 |
| 2014-01-09@West Melbourne | 否 |
| 2014-01-10@West Melbourne | 否 |
| 2014-01-11@West Melbourne | 否 |
| 2014-01-12@West Melbourne | 否 |
| 2014-01-13@West Melbourne | 否 |
| 2014-01-14@West Melbourne | 否 |
| 2014-01-15@West Melbourne | 否 |
| 2014-01-16@West Melbourne | 否 |
| 2014-01-17@West Melbourne | 否 |
| 2014-01-18@West Melbourne | 否 |
| 2014-01-19@West Melbourne | 否 |
| 2014-01-20@West Melbourne | 否 |
| 2014-01-21@West Melbourne | 否 |
| 2014-01-22@West Melbourne | 否 |
| 2014-01-23@West Melbourne | 否 |
| 2014-01-24@West Melbourne | 否 |
| 2014-01-25@West Melbourne | 否 |
| 2014-01-26@West Melbourne | 否 |
| 2014-01-27@West Melbourne | 否 |
| 2014-01-28@West Melbourne | 否 |
| 2014-01-29@West Melbourne | 否 |
| 2014-01-30@West Melbourne | 否 |
| 2014-01-31@West Melbourne | 否 |
| 2014-02-01@West Melbourne | 否 |
| 2014-02-02@West Melbourne | 否 |
| 2014-02-03@West Melbourne | 否 |
| 2014-02-04@West Melbourne | 否 |
| 2014-02-05@West Melbourne | 否 |
| 2014-02-06@West Melbourne | 否 |
| 2014-02-07@West Melbourne | 否 |
| 2014-02-08@West Melbourne | 否 |
| 2014-02-10@West Melbourne | 否 |
| 2014-02-11@West Melbourne | 否 |
| 2014-02-12@West Melbourne | 否 |
| 2014-02-13@West Melbourne | 否 |
| 2014-02-14@West Melbourne | 否 |
| 2014-02-15@West Melbourne | 否 |
| 2014-02-16@West Melbourne | 否 |
| 2014-02-17@West Melbourne | 否 |
| 2014-02-18@West Melbourne | 否 |
| 2014-02-19@West Melbourne | 否 |
| 2014-02-20@West Melbourne | 否 |
| 2014-02-21@West Melbourne | 否 |
| 2014-02-22@West Melbourne | 否 |
| 2014-02-23@West Melbourne | 否 |
| 2014-02-24@West Melbourne | 否 |
| 2014-02-25@West Melbourne | 否 |
| 2014-02-26@West Melbourne | 否 |
| 2014-02-27@West Melbourne | 否 |
| 2014-02-28@West Melbourne | 否 |
| 2014-03-01@West Melbourne | 否 |
| 2014-03-02@West Melbourne | 否 |
| 2014-03-03@West Melbourne | 否 |
| 2014-03-04@West Melbourne | 否 |
| 2014-03-05@West Melbourne | 否 |
| 2014-03-06@West Melbourne | 否 |
| 2014-03-07@West Melbourne | 否 |
| 2014-03-08@West Melbourne | 否 |
| 2014-03-09@West Melbourne | 否 |
| 2014-03-10@West Melbourne | 否 |
| 2014-03-11@West Melbourne | 否 |
| 2014-03-12@West Melbourne | 否 |
| 2014-03-13@West Melbourne | 否 |
| 2014-03-14@West Melbourne | 否 |
| 2014-03-15@West Melbourne | 否 |
| 2014-03-16@West Melbourne | 否 |
| 2014-03-17@West Melbourne | 否 |
| 2014-03-18@West Melbourne | 否 |
| 2014-03-19@West Melbourne | 否 |
| 2014-03-20@West Melbourne | 否 |
| 2014-03-21@West Melbourne | 否 |
| 2014-03-22@West Melbourne | 否 |
| 2014-03-23@West Melbourne | 否 |
| 2014-03-24@West Melbourne | 否 |
| 2014-03-25@West Melbourne | 否 |
| 2014-03-26@West Melbourne | 否 |
| 2014-03-27@West Melbourne | 否 |
| 2014-03-28@West Melbourne | 否 |
| 2014-03-29@West Melbourne | 否 |
| 2014-03-30@West Melbourne | 否 |
| 2014-03-31@West Melbourne | 否 |

### 停留时长分位数（分钟，分母 = rows_with_dwell_min = 185550）

| p50 | p90 | p99 | max |
|---|---|---|---|
| 22.983 | 118.167 | 351.21783000000124 | 1437.783 |

### arrival_local_hour 分布（24 桶，分母 = total_rows）

| hour | count |
|---|---|
| 0 | 242 |
| 1 | 79 |
| 2 | 51 |
| 3 | 62 |
| 4 | 120 |
| 5 | 135 |
| 6 | 293 |
| 7 | 11315 |
| 8 | 11876 |
| 9 | 17420 |
| 10 | 18398 |
| 11 | 18693 |
| 12 | 19272 |
| 13 | 16988 |
| 14 | 15504 |
| 15 | 13851 |
| 16 | 12749 |
| 17 | 13991 |
| 18 | 9177 |
| 19 | 3534 |
| 20 | 1135 |
| 21 | 264 |
| 22 | 234 |
| 23 | 167 |

## 分母说明

缺失/重复计数分母为 total_rows；负时长、dwell 不一致、跨日、时间戳不可解析、容量冲突分母为 parseable_rows（两时间戳均可解析的行）；分位数分母为 rows_with_dwell_min；hour 分布分母为 total_rows。

