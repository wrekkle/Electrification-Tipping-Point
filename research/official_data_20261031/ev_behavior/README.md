# ev_behavior：充電概率官方/公共來源與證據（ev-data，2026-10-31）

本目錄是階段一 A+B 的官方/公共機構資料採集區：EV 保有、公共充電槍、充電會話、停車/充電行為調查、SOC 與里程代理、車槍比與設備利用率證據。**不采用统一默认充电率**；`selected_default` 在 `model_20261031.json` 中保持 null，q_need 不可識別的原因與識別邊界見該文件。

## 目錄

| 路徑 | 內容 |
|---|---|
| `raw/` | 下載原件（PDF/HTML/CSV/ZIP/JSON），14 個文件，59.6 MiB；URL、下載時間、HTTP 狀態、bytes、sha256 全部見 `manifest.json` |
| `derived/` | 本輪計算產物（`barnet_session_stats.json`：英國會話時長/滯留統計；`session_stats.json`：初版，樣本更少） |
| `source_review/` | PDF/HTML 提取文本與核對報告：`source_verification_20261031.md`、`m08_text.txt`、`m10_text.txt`、`m13_nature_text.txt`、`iot_report_hits.txt`、`afdc_registration_text.txt` |
| `tools/` | 採集與解析腳本（fetch.py 帶請求日誌/預算，parse_*.py，build_manifests.py） |
| `manifest.json` | 下載清單（含 failed_requests、request_budget、local_reference_files） |
| 請求日誌 | `research/official_data_20261031/logs/ev_behavior_requests.jsonl`（每個 HTTP 與 SEARCH 一行：seq/t_utc/method/url/purpose/status/bytes/sha256/saved_path/error） |

## 数据字典（raw/）

| 文件 | 類型/大小 | 來源類別 | 用途 |
|---|---|---|---|
| `IOT_public_charging_demand_table.pdf` | PDF 54,335,400 B（804 頁） | official（交通部運輸研究所） | 台灣 EV 保有、公共充電槍 7,146、車槍比、2,027 份 EV 使用者調查（充電頻率、公共份額 4/10、時長 72 min、SOC 29%、排隊≤10 min） |
| `AFDC_vehicle_registration_2024.html` | HTML 65,826 B | official（US DOE AFDC） | 美國 EV 登記 4,503,700（加州 1,533,900） |
| `AFDC_stations_states.html` | HTML 48,206 B | official（US DOE AFDC） | 公共充電站/槍數頁面結構；表格為 JS 動態，數字未數字化 |
| `epa_vehicles.csv.zip` | ZIP 2,212,193 B（vehicles.csv 50,407 行） | official（DOE/EPA fueleconomy.gov） | EV 車型續航代理（1,608 條，range 中位 282 mi，29–520） |
| `M10_TUE_fulltext.pdf` | PDF 4,655,408 B（30 頁） | peer_reviewed（TU/e 機構庫） | M10 Table 3 核對（6,187/2,062；1,486/469） |
| `M13_nature_article.html` | HTML 356,088 B | peer_reviewed（npj OA） | M13 定義、每日充電次數中位 0.81/1.14/1.67（q_day 型）、SOC 前後、數據可用性 |
| `barnet_cityev_2021Q2.csv` | CSV 601,635 B（44,225 行） | official（倫敦 Barnet 地方政府） | 充電交易會話：充電/連接/充電後仍連接時長代理；僅 856 行時間戳完整 |
| `crossref_M11.json` / `crossref_M12.json` | JSON 12,025 / 21,329 B | peer_reviewed 元數據 | 書目；無摘要（全文 403） |
| `ACN_research.html` | HTML 25,335 B | institutional_report（Caltech） | M15 充電會話數據集說明（無停車分母） |
| `uk_datagov_ckan_search.json` / `uk_datagov_ckan_device.json` | JSON 32,738 / 230 B | official（data.gov.uk） | 發現 Barnet 交易資料；DfT 全國統計未取得（gov.uk TLS 失敗） |
| `datataipei_parking_dataset.html` / `datataipei_parking_resources.json` | HTML 89,855 B / JSON 2 B | official（data.taipei） | 台北停車資料集出處；API 探測空回應（僅留痕） |

## 清洗記錄

1. 所有 HTTP 請求（含探測/失敗）先寫日誌再落盤；`fetch.py` 強制 ≤60 請求 / ≤200 MB，超限即停。
2. PDF 用 PyMuPDF 提取逐頁文本；HTML 去 script/style 後文本化；ZIP 解壓讀 CSV；不改動 raw 原始 bytes（sha256 由本地文件復算）。
3. 13 次失敗已如實記錄（data.gov.tw 405/500、data.taipei API 404、T&F/ScienceDirect 403、gov.uk/caltech/Zenodo SSL、等），未伪造或跳过原因。
4. 本輪未改 `evidence.json`、`rates.json`；新模型只寫 `model_20261031.json`。

## 來源類別

- official：運研所報告、US DOE AFDC/EPA、Barnet 地方政府、data.gov.uk、data.taipei（後兩者僅發現/出處）。
- peer_reviewed：M10 機構庫全文、M13 OA 全文、Crossref 元數據（M11/M12）。
- institutional_report：Caltech ACN-Data 文檔。
- failed/unavailable：M11、M12 全文；英國 DfT 全國 EVCI 統計；Zenodo M13 數據；日本 MLIT、EU JRC/EAFO 本輪未採（時間/預算）。
- 同一數據集標記：M11 疑似與 M08 同用 The EV Project 數據（UNVERIFIED，未計為獨立樣本）；M09/M10/M12/M13 為獨立樣本；M14/M15/M16 為新獨立來源。

## 缺口與修訂

- 缺口：逐槍額定功率、故障/停用狀態、停車場到訪車型、家充比例數值（僅圖表）、SOC/電池容量分佈（僅圖表/續航代理）、美國公共槍數、M11/M12 係數、M13 公開數據、日本/歐盟官方統計。
- 修訂：本目錄 append-only；重下載不得覆蓋舊檔，應新增文件名並在 manifest 記 revision。既有 M08 PDF 保持原樣（sha256 `afaf43d9…`）。
- UNVERIFIED：M11/M12 原文定義；M13 更正與數據內容；M14 出版年與家充比例數值；M16 其餘 43,369 行格式；英語系主機（gov.uk/caltech/zenodo）SSL 失敗原因。

## 預算

- 請求：27 / 60（其中 2 次 SEARCH 用於資料集定位，13 次失敗）；下載 bytes：62,456,270 / 200 MB；磁盤 raw：59.6 MiB。
