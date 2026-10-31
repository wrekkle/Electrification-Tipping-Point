# traffic_resources：台北場站規模/充電位/槍/到訪結構可得性（ev-data，2026-10-31）

本目錄只**只讀消費**既有台北已保存數據，整理「模擬車流」可用的場站與充電資源欄位，並明確標出不可得字段。未重啟/修改台北 372 場採集器，未改動任何源數據；大文件全部流式讀取（`connector_status_long.jsonl` 單日 226 MB / 205 MB）。

## 來源（只讀）

| 來源 | 內容 |
|---|---|
| `research/collection/taipei_source_20261030/` | 官方 data.taipei 停車場靜態/即時快照：`all_parking_inventory.csv`（1,775 場）、`parking_charging_inventory.csv`（443 個帶充電站標籤場）、`summary.json`、`raw/static.xml`、`raw/dynamic.xml` |
| `research/collection/taipei_372_polling_20261030/data/static/cohort_static.json` | 372 場 cohort：`baseline_totalcar`、`baseline_connector_count` |
| `.../data/2026-10-30|2026-10-31/parking_slots.jsonl` | 5 分鐘淨佔用（54,684 / 49,476 行） |
| `.../data/2026-10-30|2026-10-31/connector_status_long.jsonl` | 逐槍狀態（267,994 / 248,837 行，1,888 槍） |
| `.../data/commits/2026-10-30|2026-10-31/` | 5 分鐘提交快照（147 + 133 個 JSON，含 parking_rows/connector_rows/meta） |
| 官方資料集出處 | `https://data.taipei/dataset/detail?id=d5c0656b-5250-4179-a491-c94daa56ef2c`（臺北市停車場資訊；動態 API 由既有採集器保存 request_url/request_sha256） |

本地檔案 bytes/sha256（小文件）見本目錄 `manifest.json`；大 jsonl 未哈希（活動採集器、流式讀取，僅記大小）。

## 字段可得性矩陣（支撐模擬車流？）

| 字段 | 可得 | 來源/定位 | 能否支撐模擬 | 限制 |
|---|---|---|---|---|
| 場站規模（總車位） | 是 | cohort_static `baseline_totalcar` / inventory `totalcar` | 是（容量約束、場站規模分佈） | 372 場合計 80,221 位，中位 145（10–1,998）；靜態與即時可能有差 |
| 充電位/樁/槍數 | 部分 | `baseline_connector_count`（1,888 槍，中位 3，1–46）；443 場有充電站標籤 | 是（槍數分佈、容量） | 「充電站宣告數（`charging_station_declared`）」≠槍數；1,775 場中有 443 場帶標籤，cohort 372 場全部有槍 |
| 額定功率 | **否** | `raw/static.xml` 無功率字段（「功率」0 次；「kW」412 次僅出現在費率/說明文本，非結構化） | 否 | 無逐槍 kW，無法算能量/功率約束，只能情景假設 |
| 故障/停用 | **否** | connector `status_raw` 只有 待機中/充電中 | 否 | 無故障/離線/維修碼；待機不等於可用於充電，也不等於空位 |
| 到訪結構（到達次數/車型） | **否** | 只有 5 分鐘淨佔用 `availablecar_valid` | 否 | 余位變化=淨佔用變化，不能恢復到達/離開次數；無車型、無閘門資料 |
| 佔用/充電狀態 | 是 | 5 分鐘余位 + 1,888 槍逐槍狀態 | 是（佔用率、充電中份額時序、站點異質性） | 5 分鐘批次（`source_update_time_is_batch_only=true`）；重複批次 `duplicate_batch` |
| 停留時長 | 部分 | 佔用/狀態轉移可近似聚合 | 部分（聚合 dwell/佔用時長） | 無逐車 ID，不能給逐車 dwell 分佈 |
| 充電完成後滯留 | **否** | 充電中→待機中只表示停止充電 | 否 | 不能證明車輛駛離；區分不了「充滿未走」與「未充電仍佔位」 |
| 排隊/拒絕 | **否** | 無排隊、無拒絕/失敗請求記錄 | 否 | 供需缺口只能用情景 |
| 充電會話起止 | 部分 | 逐槍狀態轉移可重建會話 | 部分（會話數/時長/利用率） | 需自行做狀態轉移重建；不能驗證用戶意願 |

## 實測規模與可復算數字（本輪流式統計）

- Cohort：372 場；總車位 80,221；中位 145（10–1,998）；槍 1,888（中位 3，1–46）；`baseline_connector_count` 與觀測到的 unique `spot_abrv` 完全一致（372 場差集 0）。
- 兩天 5 分鐘數據：2026-10-30 03:30–15:55 UTC（54,684 行，`duplicate_batch` 2,604）；2026-10-31 16:00(前日 UTC)–03:00（49,476 行，`duplicate_batch` 744）。合計約 23.4 小時/場。
- 逐槍狀態：2026-10-30 待機中 171,071 / 充電中 96,923；2026-10-31 待機中 179,779 / 充電中 69,058。槍時充電份額 = 36.17% / 27.75%（device_time_utilization，不是到訪充電概率）。
- commits：2026-10-30 147 個、2026-10-31 133 個 5 分鐘快照，字段 `slot_start_utc/parking_rows/connector_rows/meta/committed_at`。
- 靜態來源：1,775 場、1,230 場有動態、443 場有充電站標籤、2,117 條 connector 狀態（單次快照）；`summary.json` 與 `connector_status_long` 的口徑差異已在本 README 區分。

## 能/不能支撐模擬車流（結論）

- 能：場站容量與槍數分佈、按時段的淨佔用曲線（可近似到達強度先驗，但要標明是淨變化推斷）、充電中槍時份額、站點異質性、時段模式；可作為車流生成器的「約束與量級檢查」。
- 不能：逐車到達次數與車型比例、q_use/q_need、p_EV_arrival、功率/能量、故障、完成後滯留、排隊拒絕；也不能把「槍待機」當空位、把「余位變化」當到達次數。
- 建議：車流生成器用文獻/情景給到達率與 p_EV，台北數據只用於時段形狀、容量與充電佔用份額的合理性校驗（見 `model_20261031.json` 的 identification 與 traffic_fit admitted_use）。

## 清洗與修訂

- 只讀；未寫源數據；大文件流式；統計腳本見 `../ev_behavior/tools/taipei_stats.py`、`taipei_stats2.py`、`session_stats2.py`。
- 未對 5 分鐘批次做插值/去重（只統計 `duplicate_batch` 行數），模擬使用前需按 `slot_start_utc` 去重並處理批次更新時戳。
- 修訂：若後續拉長觀測窗口，另建新日期目錄，不覆蓋本輪統計；本 README 數字對應 2026-10-30/31 數據快照。
