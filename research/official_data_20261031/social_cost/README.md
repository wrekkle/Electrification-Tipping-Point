# social_cost：社會成本與基礎設施官方數據（cost-data, 2026-10-31）

類型: 研究原始資料與數據字典
狀態: 草案（階段一 C+D+E 交付）
負責人: cost-data
對應契約: research/official_data_20261031/contract/CONTRACT.md（schema v3、來源紀錄 §3、日誌 §4、回執 §10）
對應參數檔: research/cost_model_20261030/parameter_candidates_20261031.json（本目錄產出的**候選**參數，不改 parameters.json）
公式映射: research/official_data_20261031/social_cost/formula_variable_map.md

## 0 採集預算執行情況（可核對）

| 項目 | 預算 | 實際 | 證據 |
|---|---|---|---|
| HTTP 請求（GET/POST） | ≤60 | **33**（含 Lead 追加後 6 次） | logs/social_cost_requests.jsonl、manifest.json request_ledger |
| 網路檢索（web_search 查詢） | 計入同一請求預算 | **27** | 同上（method=SEARCH 行） |
| 落盤位元組 | ≤200 MB | **24.0 MB** | manifest._meta.request_summary.downloaded_bytes |
| 耗時 | ≤45 分鐘 | 2026-10-31T02:52:43Z→03:14:31Z（約 22 分鐘） | manifest._meta.request_summary |
| 失敗請求 | 留痕不重試湊數 | **9**（404/405/500/403 WAF/0-byte/付費牆） | manifest._meta.failures |

每次請求（含檢索、診斷）都寫一行 JSONL；失敗也保留，未對同一 URL 重複探測（唯一例外是油價 API：第一次日期格式錯誤回 res=00，改 yyyy/mm/dd 後同一端點第二次即成功，兩次都在日誌）。

## 1 檔案清單與數據字典

| 檔案 | 內容 | 官方性 | 用途 |
|---|---|---|---|
| raw/pdf/iot_108_handbook_110c_params.pdf | 交通部運輸研究所《108年 交通建設計畫經濟效益評估手冊（更新版）》，中華民國110年12月，108-129-1425，172 頁 | 官方 | 表5-6 每車時間價值（民國107年幣值：小客車都會 5.93、城際 7.58；前期手冊 3.61/5.23）、表5-1 工資率、空氣污染損害章節（未抽出） |
| raw/pdf/dgbas_price_monthly.pdf | 主計總處《物價統計月報》114年5月 653期（110年=100） | 官方 | 表1-8 消費者物價總指數銜接表年指數：2009=89.07、2018=97.76、2024=107.81；表1-2 月度指數 |
| raw/pdf/dgbas_cpi_news_11509.pdf | 主計總處《115年9月物價變動概況》新聞稿（2026-10-07 發布） | 官方 | 2025 年 CPI 年增率 1.66%、2026 年1-9月平均 +1.94%、2026年9月 +2.73% |
| raw/html/oil_price_range_2025_2026.json | 經濟部能源署油價資訊系統 POST /Gasoline/RetailPrice/load 回應 | 官方（API） | 2025-01-06～2026-09-28 共 91 筆週價；A=中油、B=台塑 |
| raw/html/moeaea_retailprice.html / .js | 能源署汽柴油參考零售價頁與前端腳本 | 官方 | API 參數格式 yyyy/mm/dd、CSV 欄位定義（95無鉛＝A95） |
| raw/pdf/taipower_brief_price_2026.pdf | 台電《簡要電價表》（33 頁，現行） | 官方 | 低壓電力電價、**電動車充換電設施電價**（本案充電樁適用費率） |
| raw/pdf/taipower_detail_price_2026.pdf | 台電《詳細電價表》（同批落盤） | 官方 | 尚未逐頁核（UNVERIFIED），同批保存 |
| raw/html/taipower_price_list.html / taipower_price_page.html / taipower_ev_zone.html | 台電電價表下載頁與電動車用電專區 | 官方 | 找到簡要/詳細電價表 PDF 連結；EV 專區未細讀 |
| raw/pdf/moenv_ghg_factors_2024.pdf | 環境部 113年2月5日公告「溫室氣體排放係數」（環部授氣字第1139101231號） | 官方 | 附表一：車用汽油移動燃燒 CO2 = 69,300 kg/TJ（基於低位熱值） |
| raw/html/moenv_ghg_registry.html | 環境部事業溫室氣體排放量資訊平台首頁 | 官方 | 找到上述公告 PDF 連結 |
| raw/html/motc_parking_search_time.html | 交通部統計查詢網「自用小客車在居家附近之尋找停車位時間及停車費」(Seq=810) | 官方 | 調查存在且頁面可讀；**數值未取得**（在互動查詢接口） |
| raw/html/datagovtw_dataset_6339.json | 政府資料開放平臺 dataset 6339「中油主產品牌價」元資料（Big5） | 官方 | 中油現價 WebService/JSON（無歷史序列） |
| raw/pdf/taipei_charging_fee_rates.pdf | **誤抓**：交通部《電動車充電站(樁)資料標準》 | 官方但**非費率** | 已標 rejected，不得當充電費率證據 |
| raw/pdf/iot_handbook_latest.pdf（548 B） | 404 頁 | 非證據 | 運研所舊資產連結已失效，失敗留痕 |
| raw/pdf/moenv_ghg_factors.pdf（2.4 KB） | HTTP 500 ASP.NET 錯誤頁 | 非證據 | cca.gov.tw 檔案接口失敗，改由 registry 入口取得正式公告 |
| raw/html/nstatdb_cpi.html / cpc_historyprice.html | 主計總處 CPI 查詢頁 / 中油歷史油價頁 | 頁面可讀但**無數據** | 需互動/POST，未取得數值（改用月報 PDF 與能源署 API） |
| raw/pdf/thb_public_charging_plan.pdf | 交通部公路局《公共充電樁設置及區域充電需求評估計畫（修正計畫）》37 頁 | 官方 | **每槍補助額度**：快充 200 萬元、慢充 8 萬元；CMS 每套 80 萬元（p.4/p.13/p.15） |
| raw/pdf/nlma_ghg_inventory_2023.pdf | 內政部國土管理署 溫室氣體盤查報告書（2023 年盤查）50 頁 | 官方 | p.23 以 **2.263132872 kg CO2/L** 轉列環境部汽油係數（固定源/移動源同值）；與 69,300 kg/TJ 互證 |
| raw/html/cbc_fx_statistics.html（實為 PDF） | 中央銀行 2019 年報「4. Foreign Exchange Market」6 頁 | 官方 | 2019 年新台幣對美元升貶方向；**未印年平均匯率水準**（FX 值仍 UNVERIFIED） |
| raw/html/acebidx_taitung_evse_award.html | （非官方鏡像）台東縣充電樁購置決標公告 | 非官方、**判 rejected** | 決標金額欄位付費牆（`* * * * *`），未取得金額 |
| raw/pdf/moeaea_vehicle_fuel_economy_guide（非 PDF） | 能源署「車輛油耗指南」統計檔案——**HTTP 403 WAF** | 非證據 | 未能取得 official 小客車 km/L；L/km 仍缺 |
| raw/pdf/moea_stat_handbook_fx.pdf（非 PDF） | 經濟部統計手冊（含 NTD/USD 月平均）——**HTTP 403 WAF** | 非證據 | 未能取得官方月平均匯率；FX 仍 UNVERIFIED |
| manifest.json | **20** 條來源紀錄（schema §3）+ 完整 33 筆請求台賬 + 失敗清單 + 未列入來源的下載檔 | — | 可獨立復核 |
| logs/social_cost_requests.jsonl | 49 行（27 請求 + 22 檢索） | — | 請求級證據 |

前輪已核、本輪未重抓但用於交叉核對：raw 外的 research/cost_model_20261030/downloads/ey_time_value_handbook_excerpt.pdf（SHA-256 e72743c15e12b53293781a8907055774c9fc04ffde9905644286915f841b2414）——3.61/5.23 與本輪 108 年手冊「前期手冊建議值」完全一致，可互證；怠速油耗 0.82 L/h 出處同檔。

## 2 換算與清洗記錄（全部可復算）

### 2.1 時間價值：2009 → 2026（CPI 鏈式，主值＋下限）

CPI 基期 110年=100，官方年指數（表1-8）：CPI_2009=89.07、CPI_2018=97.76、CPI_2024=107.81。
2025 年指數與 2026 年（1-9月平均）指數由官方年增率鏈式推算：
- CPI_2025 = 107.81 × (1+1.66%) = **109.5996**
- CPI_2026 = 109.5996 × (1+1.94%) = **111.7258**（2026 全年指數尚未發布，用 1-9 月平均代理）

兩條鏈：
1. **主值（最新手冊法）**：5.93（108 年手冊，2018 幣值）× 111.7258/97.76 = **6.7771 TWD/(車·分鐘)** = **406.63 TWD/(車·小時)**。
2. **下限（任務指定 2009 值法）**：3.61（2009 幣值）× 111.7258/89.07 = **4.5282 TWD/(車·分鐘)** = **271.69 TWD/(車·小時)**。
3. 城際對照：7.58 × 111.7258/97.76 = **8.6629 TWD/(車·分)**（僅上界參考，不屬市區停車情境）。

**為什麼必須兩條並列**：手冊明示未來值應以「工資上漲率」調整，不是 CPI。2009→2018 手冊自身把 3.61 修訂為 5.93（×1.643，約 +5.7%/年），而同期 CPI 只 ×1.098（+1.0%/年）。單用 CPI 會明顯低估（因修訂同時含方法/乘載率變動），故 4.53 是下限、6.78 是可辯護主值，不得宣稱唯一真值。**沒有把國外時間價值按匯率搬用。**

### 2.2 油價：台灣中油官方週牌價期間平均

- 資料：能源署油價資訊管理與分析系統 API（中油每週公告零售價），查詢 2025/01/01–2026/09/30，回傳 91 筆（首筆 2025/01/06、末筆 2026/09/28）。
- 方法：期間內每週公告價**算術平均，未加權、未插補**（週資料，不是日資料）。
- 結果（TWD/L，95無鉛/A95）：2025 全年（52 筆）**29.1577**；2026-01-01～09-30（39 筆）**31.7385**；近12月（52 筆）**30.9212**。92無鉛 2026 均值 30.2385；超級柴油 29.0513。
- 用途：ice_vehicle_operating = 繞行km × L/km × 油價；L/km 仍缺。

### 2.3 電價：台電現行費率表（本案充電樁適用）

台電《簡要電價表》p.8「低壓電力－時間電價－3.電動車充換電設施電價」：
- 流動電費每度：尖峰 12.47（夏月 16–22 時）／12.14（非夏月 15–21 時）；離峰 **3.05（夏月）／2.90（非夏月）**；週六日及離峰日離峰全日 3.05/2.90。
- 基本電費：按戶 262.50 元/戶·月；經常契約 47.20（夏月）／34.60（非夏月）元/瓩·月。
- 對照：低壓電力非時間電價流動電費 4.08（夏月）／3.87（非夏月）元/度。
- **清洗判斷**：費率表可直接入模，但後端 electricity_price_per_kwh 是**單值**，需充電時刻分布與契約容量，兩者未知 ⇒ 該欄位保持 null，另给「非夏月離峰 2.90」為 is_scenario 情景值。UNVERIFIED：電價表 PDF 未印生效日期（表內援引 113年4月、113年10月調幅），生效日未核。

### 2.4 排放：環境部汽油 CO2

- 官方值：移動燃燒源 車用汽油 CO2 = **69,300 kg CO2/TJ**（基於低位熱值）。可直接用於「已知燃料熱值/用量」的排放計算。
- 換算 kg/L 需汽油低位熱值，**公告未提供**；因此 co2_emission_factor_gasoline_kg_per_L 保持 null。若假設 LHV=32.657 MJ/L（≈7,800 kcal/L，常見工程值，本輪無官方文件）則 = 3.2657e-5 TJ/L × 69,300 = **2.2631 kg/L**，此值標 UNVERIFIED 情景值，不得入模。缺的是熱值、不是係數。
- 空氣污染物（PM2.5/NOx）係數與單位損害本輪未取得 → null；候選：環境部排放係數/清冊、運研所手冊空氣污染損害章節（p.73 起，未抽出）。

### 2.5 碳費（沿用的既有官方值，僅敏感性）

一般費率 300 TWD/tCO2e、優惠 A 50、B 100（前輪已核，本輪未重抓）。**法定碳費≠邊際社會碳成本**：只用於 CO2 外部成本敏感性，且缺 kg/L 前無法算進 per-km 成本。

### 2.6 未取得／判不可識別的項（不填值）

台北停車搜尋時間、繞行距離、替代步行時間、替代補能價差、行駛油耗 L/km、EV 電耗 kWh/km、缺電損失、活動機會損失、挪車代價、EVSE 單槍建置/維護/折舊、停車費率、充電服務費率、汽油低位熱值、空氣污染物單位損害。每項的候選來源與「發生了什麼」寫在 parameter_candidates_20261031.json 的 candidate_sources。

特別說明兩處失敗：
- 台北停車費率：data.taipei 資源連結 HTTP 200 但回 0 bytes；pma.taipei.gov.tw 前輪連線失敗 ⇒ 留 null（屬轉移支付，不阻塞社會成本）。
- 充電服務費率：抓到的 PDF 實為交通部「電動車充電站(樁)資料標準」，已在 manifest 標 rejected，不當費率證據。
- EVSE 成本：政府電子採購網決標查詢與補助要點在時間預算內未取得可核對單價 ⇒ null；P26 的 USD/LA 值只作候選，禁止按匯率搬用。

## 3 分類：可進完整社會成本 / 僅敏感性 / 不可識別

- **可進完整社會成本（官方值且已接到後端欄位）**：vot（2026 幣值 6.7771 TWD/車·分＝406.63 TWD/h）、95無鉛油價（2026 初至 9 月底 31.7385 TWD/L）、台電 EV 充換電設施電價（分時費率表）、低壓電力非時間電價、汽油 CO2 係數（69,300 kg/TJ **及 2.263132872 kg/L**）、汽油低位熱值（反推 32.657 MJ/L）、怠速油耗 0.82 L/h。
- **設施成本（Lead 追加）**：C(k) 的設施分攤成本可用 `evse_annual_cost_TWD_per_connector_2026_transferable` = **27,483.40 TWD/槍·年** 分項計算（transferable/scenario，非台北實測），並有官方額度錨點（慢充 8 萬元/槍、快充 200 萬元/槍）。
- **僅敏感性／情景**：碳費 300 元/公噸（法定費率非社會碳成本）、「非夏月離峰 2.90 元/度」電價情景、城際時間價值 8.66、2009 年幣值原值（只作換算輸入/核對）、Biswas/P26 外地美金值。
- **不可識別**：上節 18 項（含 electricity_price 單值、CO2 kg/L、全部行程時間/距離/能耗/成本項）。

## 4 為什麼完整社會成本仍不可算（缺參如何傳播）

後端（apps/parking_lab/workbench/costs.py）對 null 參數傳播：任一乘數為 None ⇒ 該成本項 None ⇒ total None、complete=false，並輸出 missing_parameters（COST-MODEL-V2 §7）。本輪補齊後，11 個 COST_ITEMS 仍無一項能獨立算出完整數值：

| 成本項 | 目前缺什麼（本輪後） |
|---|---|
| user_time | Δt 搜索/繞行/步行（全缺；vot 已有） |
| ev_detour_energy | 繞行距離、EV 電耗、替代補能價差 |
| ev_external / ice_external | 排放 kg/L（缺低位熱值）或 per-km 係數；污染物分項 |
| ev_residual_trip_loss | 缺電損失單價 |
| ice_vehicle_operating | 行駛油耗 L/km（油價與怠速油耗已有） |
| ice_activity_loss / ev_activity_loss | 活動機會損失 |
| operator_capital_depreciation | 已可用 transferable 年化值（27,483 TWD/槍·年，scenario）分項計算；但非台北實測、未折現，且折現率與官方單位成本仍缺 |
| operator_energy | 電價單值（需充電時段結構；費率表已有） |
| operator_maintenance | 維護成本 |

因此 C(k;π0) 的「設施分攤」現可以 transferable/scenario 值分項計算，「用戶額外社會成本」與「運行資源」仍有多項 null；完整 total 仍不可算，只能給**條件化情景成本**，並明確標註（CONTRACT §8、§11）。不得把模擬條件最優當真實效果或完整社會成本最優樁數；k* 若給出，必須標明設施成本為 LA 論文換算、非台北採購價。

## 5 限制與 UNVERIFIED

- UNVERIFIED：台電簡要電價表的生效日期（PDF 未印，僅援引 113年4月/10月調幅）。
- UNVERIFIED：詳細電價表（raw/pdf/taipower_detail_price_2026.pdf）尚未逐頁核對，僅同批落盤。
- UNVERIFIED：手冊空氣污染損害參數（p.73 起）未抽出數值。
- UNVERIFIED：台北市公有停車場費率（資源 0 bytes）與充電服務費率（未取得）。
- UNVERIFIED：2025/2026 CPI 為年增率鏈式推算，非官方指數水準；2026 用 1-9 月平均代理。
- UNVERIFIED：**2019 年新台幣對美元年平均匯率 30.9**（央行年報章節未印水準；經濟部統計手冊 403）；所有 EVSE TWD 換算依賴此值，須以官方年平均替換。
- UNVERIFIED：EVSE 壽命 10 年（8–12）為情景；維護按 2 槍攤提為假設；直線法未折現。
- 未取得：能源署「車輛油耗指南」與「車輛耗能」官方 km/L（403 WAF）；手冊動態能耗/碳排係數附表未含於取得之 PDF ⇒ `fuel_consumption_L_per_km`、`ev_energy_consumption_kWh_per_km` 仍 null。
- 轉移支付（停車費/充電費/罰金/補貼）與占桩歸因（attribution）都不進 social_total；本目錄不主張任何「最優樁數」。
- 本目錄未改 parameters.json、workbench、docs/TODO.md/PROGRESS.md、literature 索引，未觸碰台北採集器。

## 6 復算指令

    python research/official_data_20261031/social_cost/compute_derived.py   # sha256、油價均值、CPI 鏈、vot 換算 → _computed.json
    python research/official_data_20261031/social_cost/build_manifest.py    # → manifest.json
    python research/official_data_20261031/social_cost/build_params.py      # → ../../cost_model_20261030/parameter_candidates_20261031.json

抓取腳本：fetch.py（GET 落盤+日誌）、fetch_post.py（POST 表單）、inspect_raw.py / probe_pdf.py / extract_pages.py（只輸出到 stdout、不寫入原始檔）。
