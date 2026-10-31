"""生成 parameter_candidates_20261031.json 与 social_cost/manifest.json（数值全部来自 _computed.json / 日志 / 已落盘文件）。"""
import hashlib, json, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BASE = os.path.abspath(os.path.join(HERE, ".."))
LOG = os.path.join(BASE, "logs", "social_cost_requests.jsonl")
computed = json.load(open(os.path.join(HERE, "_computed.json"), encoding="utf-8"))
files = {f["local_path"]: f for f in computed["files"]}
oil, cpi, vot = computed["oil"], computed["cpi"], computed["vot"]

# ---- 日志 ----
rows = [json.loads(l) for l in open(LOG, encoding="utf-8") if l.strip()]
reqs = [r for r in rows if r.get("method") in ("GET", "POST")]
searches = [r for r in rows if r.get("method") == "SEARCH"]
t_min = min(r["t_utc"] for r in rows); t_max = max(r["t_utc"] for r in rows)
by_url = {}
for r in reqs:
    by_url[r["url"]] = r
total_bytes = sum(r.get("bytes") or 0 for r in reqs)
n_fail = sum(1 for r in reqs if r.get("error") or (r.get("status") or 0) >= 400)
saved_bytes = sum(f["bytes"] for f in computed["files"] if f["local_path"].startswith("research/official_data_20261031/"))

def rel(p):
    return p.replace("\\\\", "/")

def sha_of(p):
    return files.get(p, {}).get("sha256")

def src(sid, title, org, url, local_path, supports, limitations, *, official=True, sclass="official",
        region="台灣", period=None, unit_notes="", what_happened=None, revision=None, sample_filter=None,
        url_key=None):
    r = by_url.get(url_key or url, {})
    return {
        "source_id": sid, "title": title, "org": org, "url": url,
        "retrieved_at_utc": r.get("t_utc"), "http_status": r.get("status"),
        "local_path": local_path, "sha256": sha_of(local_path) if local_path else None,
        "bytes": files.get(local_path, {}).get("bytes"), "official": official,
        "source_class": sclass, "region": region, "period": period, "unit_notes": unit_notes,
        "sample_filter": sample_filter, "revision": revision,
        "what_it_supports": supports, "limitations": limitations, "what_happened": what_happened,
    }

U_HB = "https://www.iot.gov.tw/uploads/asset/data/6655325e085777b9e745ca2e/108%E5%B9%B4%E7%B6%93%E6%95%88%E8%A9%95%E4%BC%B0%E6%89%8B%E5%86%8A_110%E5%B9%B4%E8%A1%8C%E8%BB%8A%E6%88%90%E6%9C%AC%E5%8F%83%E6%95%B8%E6%9B%B4%E6%96%B0%E5%BE%8C%E6%95%B4%E7%90%86%E7%89%88%E6%9C%AC_.pdf"
U_CPI_M = "https://ws.dgbas.gov.tw/001/Upload/463/ebook/ebook_331734//pdf/full.pdf"
U_CPI_N = "https://ws.dgbas.gov.tw/Download.ashx?u=LzAwMS9VcGxvYWQvNDYzL3JlbGZpbGUvMTA5ODAvMjM2NzU5L25ld3MxMTUwOS5wZGY%3d&n=bmV3czExNTA5LnBkZg%3d%3d&icon=..pdf"
U_OIL = "https://www2.moeaea.gov.tw/oil111/Gasoline/RetailPrice/load"
U_OILPAGE = "https://www2.moeaea.gov.tw/oil111/Gasoline/RetailPrice"
U_TP_BRIEF = "https://www.taipower.com.tw/media/dhuhrppu/%E7%B0%A1%E8%A6%81%E9%9B%BB%E5%83%B9%E8%A1%A8.pdf?mediaDL=true"
U_TP_DETAIL = "https://www.taipower.com.tw/media/xtofy2yw/%E8%A9%B3%E7%B4%B0%E9%9B%BB%E5%83%B9%E8%A1%A8.pdf?mediaDL=true"
U_TP_LIST = "https://www.taipower.com.tw/2289/2290/46940/simpleList"
U_TP_EV = "https://www.taipower.com.tw/2289/2406/2420/2429/simpleList"
U_MOENV = "https://ghgregistry.moenv.gov.tw/upload/Tools/AI/113%E5%B9%B42%E6%9C%885%E6%97%A5%E5%85%AC%E5%91%8A%E6%BA%AB%E5%AE%A4%E6%B0%A3%E9%AB%94%E6%8E%92%E6%94%BE%E4%BF%82%E6%95%B8.pdf"
U_MOTC = "https://statis.motc.gov.tw/motc/Statistics/Display?Seq=810"
U_TPI = "https://data.taipei/api/dataset/59027123-0fd0-4599-bcc7-53e3f480e52a/resource/9fea1c0b-4ee1-45eb-9f92-f0a0eb1da2d7/download"
U_CARBON = "https://enews.moenv.gov.tw/moenv-news/zh-tw/News/2756"

sources = [
 src("S-01-IOT-HANDBOOK-108", "108年 交通建設計畫經濟效益評估手冊（更新版）", "交通部運輸研究所",
     U_HB, "research/official_data_20261031/social_cost/raw/pdf/iot_108_handbook_110c_params.pdf",
     ["時間價值：表5-6 每車時間價值（本手冊建議值 民國107年幣值：小客車都會 5.93、城際 7.58；前期手冊 3.61/5.23 元/每車每分鐘）",
      "表5-1 每人每分鐘工資率（都會 3.57、城際 3.18，民國107年幣值）", "表5-5 每人時間價值（小客車都會 2.58）"],
     ["建議未來值以工資上漲率調整，不是 CPI", "幣值為民國107年（2018），須換算", "都會定義含台北市、新北市等 10 縣市，非台北市單獨值"],
     revision="中華民國110年12月（108-129-1425）", period="民國107年幣值"),
 src("S-02-DGBAS-CPI-MONTHLY", "物價統計月報 114年5月 653期", "行政院主計總處",
     U_CPI_M, "research/official_data_20261031/social_cost/raw/pdf/dgbas_price_monthly.pdf",
     ["表1-8 消費者物價總指數銜接表（110年=100）年指數：民國98年(2009)=89.07、民國107年(2018)=97.76、民國113年(2024)=107.81",
      "表1-2 消費者物價基本分類指數（月度，可核 114年1-5月）"],
     ["本刊為 114年5月（2025-05）期，不含 2025 年全年與 2026 年指數"], period="民國51年–114年5月"),
 src("S-03-DGBAS-CPI-NEWS", "115年9月物價變動概況（新聞稿）", "行政院主計總處",
     U_CPI_N, "research/official_data_20261031/social_cost/raw/pdf/dgbas_cpi_news_11509.pdf",
     ["114年 CPI 年增率 1.66%", "115年1-9月平均 CPI 較上年同期漲 1.94%；115年9月年增率 2.73%", "115年1-9月平均指數可由 2024 年官方年指數 × 年增率鏈式推算"],
     ["新聞稿不含 CPI 指數水準（附表未附於此 6 頁 PDF）", "年增率為四捨五入值，鏈式推算有小誤差"], period="115年9月"),
 src("S-04-ENERGY-OIL-API", "汽柴油參考零售價（指定期間查詢 API 回應）", "經濟部能源署 油價資訊管理與分析系統",
     U_OIL, "research/official_data_20261031/social_cost/raw/html/oil_price_range_2025_2026.json",
     ["台灣中油每周公告零售價：95無鉛 2025 全年 52 筆均值 29.1577、2026-01-01～09-30 共 39 筆均值 31.7385、近12月 30.9212 TWD/L",
      "同表亦含 92/98 無鉛與超級柴油；A 欄為台灣中油、B 欄為台塑石化"],
     ["周資料（非日資料），期間平均按公告次數算術平均，未加權", "2025-01-06 前資料不在回應中（查詢起日 2025/01/01，首筆 01/06）"],
     period="2025-01-06～2026-09-28", sample_filter="start=2025/01/01,end=2026/09/30"),
 src("S-05-ENERGY-OIL-PAGE", "汽柴油參考零售價頁面與前端腳本（API 參數與欄位定義）", "經濟部能源署 油價資訊管理與分析系統",
     U_OILPAGE, "research/official_data_20261031/social_cost/raw/html/moeaea_retailprice.js",
     ["查詢 API 為 POST /oil111/Gasoline/RetailPrice/load，參數 start/end 格式 yyyy/mm/dd",
      "CSV 欄位定義：Date/施行時間/92/95/98 無鉛與超級柴油（中油、台塑各一組）"],
     ["頁面本身不含價格（動態載入）"]),
 src("S-06-TAIPOWER-BRIEF", "簡要電價表", "台灣電力公司",
     U_TP_BRIEF, "research/official_data_20261031/social_cost/raw/pdf/taipower_brief_price_2026.pdf",
     ["低壓電力電價（非時間電價）：流動電費每度 4.08（夏月 6/1-9/30）/3.87（非夏月）元",
      "電動車充換電設施電價：基本電費按戶 262.50 元/戶月、經常契約 47.20（夏月）/34.60（非夏月）元/瓩月；流動電費尖峰 12.47（夏月 16-22 時）/12.14（非夏月 15-21 時）、離峰 3.05（夏月）/2.90（非夏月）元/度；週六日及離峰日離峰全日 3.05/2.90"],
     ["摘要版電價表，未列生效日期；表內提及 113年4月、113年10月調幅", "電價表未給充電樁典型時段結構，均價不可直接取"]),
 src("S-07-TAIPOWER-DETAIL", "詳細電價表", "台灣電力公司",
     U_TP_DETAIL, "research/official_data_20261031/social_cost/raw/pdf/taipower_detail_price_2026.pdf",
     ["與簡要電價表同一現行費率架構（尚未逐頁核對）"],
     ["UNVERIFIED: 未逐頁抽出核對，僅作同批落盘"]),
 src("S-08-MOENV-GHG-FACTORS", "溫室氣體排放係數（113年2月5日公告，環部授氣字第1139101231號）", "環境部",
     U_MOENV, "research/official_data_20261031/social_cost/raw/pdf/moenv_ghg_factors_2024.pdf",
     ["附表一 移動燃燒排放源：車用汽油 CO2 排放係數 69,300 kg/TJ（基於低位熱值）",
      "同表固定燃燒源亦列 車用汽油 69,300 kg CO2/TJ、CH4 3、N2O 0.6"],
     ["公告僅給 kg/TJ，未給低位熱值與 kg/L", "無空氣污染物（PM2.5/NOx）係數"]),
 src("S-09-MOTC-PARKING-SURVEY", "自用小客車在居家附近之尋找停車位時間及停車費（統計查詢網頁）", "交通部統計處",
     U_MOTC, "research/official_data_20261031/social_cost/raw/html/motc_parking_search_time.html",
     ["官方調查「自用小客車使用狀況調查」存在，且查詢頁可存取（Seq=810）"],
     ["數值在查詢表單/圖表接口，需 POST 或前端互動；本輪未取到台北數值", "不得用外地 Shoup 8.1 分鐘替代"]),
 src("S-10-TAIPOWER-LIST", "台電電價表下載清單頁", "台灣電力公司",
     U_TP_LIST, "research/official_data_20261031/social_cost/raw/html/taipower_price_list.html",
     ["簡要電價表（1039.8KB）與詳細電價表（1254.4KB）、最近兩年時間電價日曆表 PDF 連結"],
     []),
 src("S-11-TAIPOWER-EV", "電動車用電業務專區", "台灣電力公司",
     U_TP_EV, "research/official_data_20261031/social_cost/raw/html/taipower_ev_zone.html",
     ["台電電動車用電業務入口（含充換電設施電價說明頁索引）"],
     ["本輪未逐頁核對內容"]),
 src("S-12-DATAGOV-CPC", "政府資料開放平臺 dataset 6339「中油主產品牌價」元資料", "政府資料開放平臺",
     "https://data.gov.tw/api/v2/rest/dataset/6339", "research/official_data_20261031/social_cost/raw/html/datagovtw_dataset_6339.json",
     ["中油現行牌價 WebService/JSON 端點（僅現價，非歷史）"],
     ["不提供歷史序列；歷史改用能源署 API"], period="擷取時點"),
 src("S-13-CARRIED-EY-HANDBOOK", "前瞻基礎建設核定本（轉引運研所 100年9月手冊表5-6；含怠速油耗 0.82 L/h）", "行政院（交通部核定本）",
     "https://www.ey.gov.tw/File/1A7A9AD51FC4695F", "research/cost_model_20261030/downloads/ey_time_value_handbook_excerpt.pdf",
     ["民國98年幣值 都會一般化 小客車 3.61、城際 5.23 元/每車每分鐘（與 108 年手冊「前期手冊」列值一致，互相核對）",
      "停等怠速油耗 小客車 0.82 L/小時、機車 0.59 L/小時"],
     ["前輪任務已核；本輪未重抓，僅用於交叉核對與引入既有官方值"], sclass="official",
     period="民國98年幣值（3.61 項）"),
 src("S-14-CARRIED-CARBON", "環境部公告「碳費徵收費率」（113-10-23）", "環境部氣候變遷署",
     U_CARBON, None,
     ["一般費率 300 TWD/tCO2e；優惠費率 A 50、B 100"],
     ["前輪任務已核，本輪未重抓（無本地檔案 sha256）", "法定碳費≠運輸邊際社會碳成本，只能作敏感性"], official=True),
 src("S-15-REJECTED-TAIPEI-CHARGING-PDF", "（誤抓）交通部電動車充電站(樁)資料標準", "交通部",
     "https://www-ws.gov.taipei/001/Upload/455/relfile/22477/8991302/105c068d-191d-4593-ad23-3e8e83ffe86c.pdf",
     "research/official_data_20261031/social_cost/raw/pdf/taipei_charging_fee_rates.pdf",
     [], ["內容為資料標準（XML 欄位定義），不是充電費率；不得當費率證據"], what_happened="原以為是台北市充電費率 PDF，讀後排除"),
]

sources += [
 src("S-16-CBC-FX", "中央銀行 2019 年報：II. Financial Developments – 4. Foreign Exchange Market", "中央銀行",
     "https://www.cbc.gov.tw/dl-149432-669bf5f5a92c434cb24881ba49fb8e02.html",
     "research/official_data_20261031/social_cost/raw/html/cbc_fx_statistics.html",
     ["2019 年新台幣對美元、日圓、歐元、人民幣之升貶方向與幅度（日平均基礎）"],
     ["UNVERIFIED: 章節僅敘述方向，未印 2019 年平均匯率水準；不能直接給 FX 值", "本地檔案副檔名為 .html，內容實為 PDF（HTTP Content-Type: application/pdf）"],
     region="台灣", period="2019 年"),
 src("S-17-P26-PAPER", "Tucker & Alizadeh (2020) An Online Admission Control Mechanism for EVs at Public Parking Infrastructures, IEEE TSG 11(1)", "IEEE / arXiv",
     "https://arxiv.org/abs/1905.06468",
     "research/ev_parking_math_20261029/PDFs/P26_An_Online_Admission_Control_Mechanism_for_Electric_Vehicles_at_Public_Parking_Infrastructures.pdf",
     ["p.10 §IV-E：pedestal EVSE install 3,308 USD；per extra cable 3,343 USD；networking/maintenance 75 USD/月"],
     ["美國洛杉磯 2019 前後、非台灣採購價", "轉引 AFDC/DOE 2015 EVSE cost report，原報告未讀", "前輪已核，本輪未重抓（本地檔案 sha256 已記）"],
     official=False, sclass="peer_reviewed", region="美國洛杉磯", period="2019 前後"),
 src("S-18-THB-CHARGING-PLAN", "公共充電樁設置及區域充電需求評估計畫（修正計畫）", "交通部公路局",
     "https://ws.thb.gov.tw/Download.ashx?u=LzAwMS9VcGxvYWQvNDM2L3JlbGZpbGUvMTIyNzEvMzQyOS8yNGRkNGI1YS04MzIwLTQ5OWEtODk4YS03ZmI2MzQ2YWVhNzUucGRm&n=5YWs5YWx5YWF6Zu75qiB6Kit572u5Y%2bK5Y2A5Z%2bf5YWF6Zu76ZyA5rGC6KmV5Lyw6KiI55WrX%2besrDHmrKHkv67mraPoqIjnlasucGRm&icon=.pdf",
     "research/official_data_20261031/social_cost/raw/pdf/thb_public_charging_plan.pdf",
     ["補助額度：快充每槍 200 萬元、慢充每槍 8 萬元、充電樁資訊管理系統每套 80 萬元（計畫 p.4/p.13/p.15）",
      "計畫總經費 9.8 億元、核定中央補助 672,310,200 元；2023-2024 年目標慢充 6,000 槍、快充 500 槍"],
     ["為『補助額度上限』，非實際決標成本", "是否含安裝/配電擴容未逐項列明"],
     region="台灣", period="2023-01-01～2024-12-31 計畫（2022-09-26 核定）"),
 src("S-19-NLMA-GHG-INVENTORY", "內政部國土管理署 溫室氣體盤查報告書（2023 年）", "內政部國土管理署",
     "https://www.nlma.gov.tw/uploads/files/077692af23bbfa3af2d22aa36a01d30f.pdf",
     "research/official_data_20261031/social_cost/raw/pdf/nlma_ghg_inventory_2023.pdf",
     ["p.23：固定源/移動源 汽油 CO2 係數 2.263132872 kg CO2/L（與環境部公告 69,300 kg/TJ 相容）",
      "同表列 CH4/N2O 係數（kg/L）"],
     ["政府報告書之二次轉列，非環境部公告正文", "報告書未標明所引環境部係數表版本"],
     region="台灣", period="2023 年盤查"),
 src("S-20-REJECTED-ACEBIDX", "（非官方鏡像）台東縣政府電動汽車充電樁購置設備案 決標公告", "acebidx.com（非官方）",
     "https://acebidx.com/zh-TW/docs/award/id/1c5c5a02-0425-4958-a3cd-a8362bc65481",
     "research/official_data_20261031/social_cost/raw/html/acebidx_taitung_evse_award.html",
     [], ["決標金額/底價欄位需付費解鎖（頁面顯示 * * * * *），未取得金額", "非官方鏡像，不得作為成本證據；官方原始為政府電子採購網決標公告"],
     official=False, sclass="institutional_report", what_happened="嘗試以鏡像取得充電樁決標單價，但金額欄位付費牆，判 rejected"),
]

manifest = {
 "_meta": {
  "file": "research/official_data_20261031/social_cost/manifest.json",
  "owner": "cost-data", "generated_utc": t_max,
  "contract": "research/official_data_20261031/contract/CONTRACT.md §3",
  "request_summary": {"total_requests": len(reqs), "web_search_queries": len(searches), "total_log_rows": len(rows),
                      "budget_requests": 60, "downloaded_bytes": total_bytes, "saved_bytes": saved_bytes,
                      "budget_bytes": 200 * 1024 * 1024, "budget_minutes": 45,
                      "first_t_utc": t_min, "last_t_utc": t_max, "failed_requests": n_fail},
  "note": "每个 GET/POST 均记入 logs/social_cost_requests.jsonl；失败请求也保留。sha256 见下；非证据文件（404/500/0-byte 或误抓文档）在 sources 中标注 what_happened 或排除。",
 },
 "sources": sources,
}
os.makedirs(os.path.join(HERE), exist_ok=True)
json.dump(manifest, open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("manifest sources:", len(sources), "requests:", len(reqs), "search:", len(searches), "bytes:", total_bytes, "saved:", saved_bytes)
print("span:", t_min, "->", t_max)
json.dump({"n_requests": len(reqs), "n_searches": len(searches), "n_failed": n_fail,
           "total_bytes": total_bytes, "saved_bytes": saved_bytes,
           "first": t_min, "last": t_max}, open(os.path.join(HERE, "_reqsum.json"), "w", encoding="utf-8"))


# ---- 完整请求台账与非证据文件 ----
ledger = []
for r in reqs:
    ledger.append({"seq": r["seq"], "t_utc": r["t_utc"], "method": r["method"], "url": r["url"],
                   "purpose": r.get("purpose"), "status": r.get("status"), "bytes": r.get("bytes"),
                   "sha256": r.get("sha256"), "saved_path": r.get("saved_path"), "error": r.get("error")})
manifest["request_ledger"] = ledger
manifest["search_queries"] = [{"seq": r["seq"], "t_utc": r["t_utc"], "query": r.get("query")} for r in searches]
covered = {s["local_path"] for s in sources if s.get("local_path")}
manifest["downloaded_files_not_in_sources"] = [
    f for f in computed["files"]
    if f["local_path"] not in covered
    and f["local_path"].startswith("research/official_data_20261031/")
]
manifest["_meta"]["budget_ok"] = {
    "requests": len(reqs) <= 60, "bytes": total_bytes <= 200 * 1024 * 1024, "minutes_target": 45}
manifest["_meta"]["failures"] = [
    {"url": r["url"], "status": r.get("status"), "error": r.get("error"), "purpose": r.get("purpose")}
    for r in reqs if r.get("error") or (r.get("status") or 0) >= 400
]
json.dump(manifest, open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ledger:", len(ledger), "non_source_files:", len(manifest["downloaded_files_not_in_sources"]), "failures:", len(manifest["_meta"]["failures"]))
