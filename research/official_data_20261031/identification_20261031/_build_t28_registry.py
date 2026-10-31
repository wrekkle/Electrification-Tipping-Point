
import json, os, hashlib
from datetime import datetime, timezone
proj = r"C:\Projects\停车场充电桩优化方案"
ident = os.path.join(proj,"research","official_data_20261031","identification_20261031")
logp = os.path.join(ident,"t28_requests.jsonl")
rows = [json.loads(l) for l in open(logp, encoding="utf-8")]
now = datetime.now(timezone.utc).isoformat(timespec="seconds")
if not any(r.get("method")=="SEARCH" for r in rows):
    extra = [{"t_utc": now, "method":"SEARCH", "url":"web_search", "purpose":"T28 search #1: 台灣電動車新車市佔率/公共充電樁使用率/掛牌統計", "status":200, "bytes":0, "sha256":None, "saved_path":None, "error":None},
             {"t_utc": now, "method":"SEARCH", "url":"web_search", "purpose":"T28 search #2: 實際市售比/公共充電使用率/停車場EV到訪比例", "status":200, "bytes":0, "sha256":None, "saved_path":None, "error":None}]
    seq = max(r["seq"] for r in rows)
    for e in extra:
        seq += 1; e["seq"] = seq; rows.append(e)
    with open(logp,"w",encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r,ensure_ascii=False)+"\n")
evlog = os.path.join(proj,"research","official_data_20261031","logs","ev_behavior_requests.jsonl")
iot = None
for l in open(evlog, encoding="utf-8"):
    r=json.loads(l)
    if (r.get("saved_path") or "").endswith("IOT_public_charging_demand_table.pdf"): iot=r
evman = json.load(open(os.path.join(proj,"research","official_data_20261031","ev_behavior","manifest.json"), encoding="utf-8"))
iot_entry = next(e for e in evman["entries"] if e["local_path"].endswith("IOT_public_charging_demand_table.pdf"))
def get(fn):
    for r in rows:
        if (r.get("saved_path") or "") and os.path.basename(r["saved_path"] or "")==fn: return r
    return None
sources = []
def add(**kw): sources.append(kw)
ly = get("t28_ly_charging_infra_2026.pdf"); ndc = get("t28_ndc_charging_news.html")
au = get("t28_audit_charging_parking.pdf"); mo = get("t28_moenv_iea_gevo2025.html")
bad1 = get("t28_audit_ev_market_share.pdf"); bad3 = get("t28_iot_demand_report_2025.pdf")
add(evidence_id="TW-EV-STOCK-2026-02", quantity_class="ev_stock", value=130278, unit="electric passenger cars registered",
    period="2026-02", org="立法院（交通部書面資料）", url=ly["url"], retrieved_at_utc=ly["t_utc"], http_status=ly["status"],
    local_path=ly["saved_path"], sha256=ly["sha256"], bytes=ly["bytes"], locator="PDF 內文『截至115年2月底止…電動小客車登記數130,278輛』",
    denominator_notes="同期電動小客車登記數；不是新車銷售數，也不是場站到訪數", status="available", source_class="official",
    limitations=["報告彙整轉述，非統計原始表；未給縣市拆分"])
add(evidence_id="TW-EV-STOCK-2025-07", quantity_class="ev_stock", value=110768, unit="electric passenger cars registered",
    period="2025-07", org="行政院國家永續發展委員會（引交通部）", url=ndc["url"], retrieved_at_utc=ndc["t_utc"], http_status=ndc["status"],
    local_path=ndc["saved_path"], sha256=ndc["sha256"], bytes=ndc["bytes"], locator="新聞內文『截至114年7月底…電動小客車登記數110,768輛』",
    denominator_notes="同期電動小客車登記數", status="available", source_class="official", limitations=["新聞稿轉述；與2026-02口徑一致但期間不同"])
add(evidence_id="TW-EV-STOCK-2024-09", quantity_class="ev_stock", value=87182, unit="electric small vehicles (passenger 86,831)",
    period="2024-09", org="交通部運輸研究所（引公路局統計）", url=iot_entry["url"], retrieved_at_utc=iot_entry["retrieved_at_utc"], http_status=iot_entry["http_status"],
    local_path=iot_entry["local_path"], sha256=iot_entry["sha256"], bytes=iot_entry["bytes"], locator="報告表2.1-2（PDF p.34）",
    denominator_notes="全台小汽車掛牌 8,384,318 → EV 占 1.04%；存量份额，不是新車市售比或到訪比例", status="available", source_class="official",
    limitations=["自 small-vehicle 登記數計算；不能作 p_EV_arrival"])
add(evidence_id="TW-EV-STOCK-2024-06", quantity_class="ev_stock", value=76525, unit="electric vehicles total",
    period="2024-06", org="審計部", url=au["url"], retrieved_at_utc=au["t_utc"], http_status=au["status"],
    local_path=au["saved_path"], sha256=au["sha256"], bytes=au["bytes"], locator="報告表2 前後文『截至113年6月底，電動車輛總數已達76,525輛』",
    denominator_notes="官方『電動車輛』總數（與小客車口徑需區分）", status="available", source_class="official",
    limitations=["含車種口徑與小客車不同；臺北市 113年6月底 19,339 輛（表2）"])
add(evidence_id="TW-PUBLIC-GUNS-2026-02", quantity_class="public_charging_supply", value=15328, unit="public charging guns (slow 11,426 / fast 3,902)",
    period="2026-02", org="立法院（交通部書面資料）", url=ly["url"], retrieved_at_utc=ly["t_utc"], http_status=ly["status"],
    local_path=ly["saved_path"], sha256=ly["sha256"], bytes=ly["bytes"], locator="PDF 內文『公共充電樁15,328槍…車樁比8.5:1；快充33.4:1』",
    denominator_notes="分母=同期電動小客車 130,278；車樁比是供給指標，不是到訪份額", status="available", source_class="official",
    limitations=["車樁比里程碑；未區分使用率；促成標示『快充/慢充』口徑"])
add(evidence_id="TW-PUBLIC-GUNS-2025-07", quantity_class="public_charging_supply", value=12334, unit="public charging guns",
    period="2025-07", org="行政院國家永續發展委員會（引交通部）", url=ndc["url"], retrieved_at_utc=ndc["t_utc"], http_status=ndc["status"],
    local_path=ndc["saved_path"], sha256=ndc["sha256"], bytes=ndc["bytes"], locator="新聞內文『截至114年7月底…12,334槍』",
    denominator_notes="分母=110,768 EV → 9.0:1；快充 33.9:1", status="available", source_class="official", limitations=["新聞稿轉述"])
add(evidence_id="TW-PUBLIC-GUNS-2024-06", quantity_class="public_charging_supply", value=9564, unit="public charging guns (slow 7,328 / fast 2,236)",
    period="2024-06", org="審計部", url=au["url"], retrieved_at_utc=au["t_utc"], http_status=au["status"],
    local_path=au["saved_path"], sha256=au["sha256"], bytes=au["bytes"], locator="報告『截至113年6月底止共計9,564槍』；表3 臺北市公有停車場充電樁 650 槍（113年6月底）",
    denominator_notes="分母=76,525 EV；表3 另給臺北市 650/19,339=3.4% 的槍/車比", status="available", source_class="official",
    limitations=["『公有停車場充電樁』與『全國公共充電樁』口徑不同（表3 僅公有停車場）"])
add(evidence_id="TW-POLICY-SALES-SHARE-TARGETS", quantity_class="policy_targets", value=None, unit="EV new-car sales share and penetration targets",
    period="2025-2040 targets", org="審計部（引國發會/交通部）", url=au["url"], retrieved_at_utc=au["t_utc"], http_status=au["status"],
    local_path=au["saved_path"], sha256=au["sha256"], bytes=au["bytes"], locator="報告表1：市售比 2025=10%、2030=30%、2035=60%、2040=100%；普及率 1.4/7.3/20.3/43.2%；新車數 38,000/114,000/228,000/380,000",
    denominator_notes="目標值，不是實際值；不得當實際市售比", status="available", source_class="official",
    limitations=["政策目標；實際值見 gap actual_new_car_sales_share"])
add(evidence_id="TW-POLICY-PARKING-CHARGING-MANDATE", quantity_class="policy_targets", value=None, unit="charging-capable parking space ratio mandate",
    period="2023-09-13 rules; due 2025-09-13", org="審計部 / 交通部 / 國發會", url=au["url"], retrieved_at_utc=au["t_utc"], http_status=au["status"],
    local_path=au["saved_path"], sha256=au["sha256"], bytes=au["bytes"],
    locator="報告：公有路外公共停車場 ≥2%、民營路外各場 ≥1%（辦法112-09-13發布，2年後施行）；NDC 新聞：公有 1.9%（含待送電2.4%）、民營 942 場應設/381 達 40%（114-08）",
    denominator_notes="供给側法定比例，不是 EV 到訪份額；不得當 p_EV_arrival", status="available", source_class="official",
    limitations=["比例是『充電專用停車位/總停車位』，與槍數/車流無關"])
add(evidence_id="TW-ACTUAL-NEW-CAR-SALES-SHARE", quantity_class="new_car_sales_share", value=None, unit="actual EV share of new car sales",
    period="2024-2025", org="審計部審核報告（下載失敗）", url=bad1["url"] if bad1 else None, retrieved_at_utc=bad1["t_utc"] if bad1 else None,
    http_status=bad1["status"] if bad1 else None, local_path=bad1["saved_path"] if bad1 else None,
    sha256=bad1["sha256"] if bad1 else None, bytes=bad1["bytes"] if bad1 else None,
    locator="搜索命中標題：『電動小客車市售比未達年度目標呈負成長』；PDF 下載端點回傳 HTML（212 bytes），重試 950 bytes，非 PDF",
    denominator_notes="UNVERIFIED：具體實際市售比數字未取得", status="UNVERIFIED", source_class="official",
    limitations=["不得用政策目標值冒充實際值", "下載端點需要工作階段/參數，未再試"])
add(evidence_id="TW-PUBLIC-CHARGING-USAGE-SHARE", quantity_class="public_charging_usage_share", value=None, unit="public charging utilisation / usage share",
    period="2024-2026", org="未找到", url=None, retrieved_at_utc=None, http_status=None, local_path=None, sha256=None, bytes=None,
    locator="立法院/審計部/國發會文件均無公共充電樁使用率數字；M14 調查的 4/10 是自報充電事件的地點份額（q_location_share），不是官方使用率或到訪份額",
    denominator_notes="UNVERIFIED", status="UNVERIFIED", source_class=None, limitations=["缺口；不得用 M14 的 0.4 冒充使用率"])
add(evidence_id="TW-LOT-EV-ARRIVAL-SHARE", quantity_class="lot_ev_arrival_share", value=None, unit="EV share of arriving vehicles at a parking facility",
    period="2024-2026", org="未找到", url=None, retrieved_at_utc=None, http_status=None, local_path=None, sha256=None, bytes=None,
    locator="無場站級 EV 到訪統計；台北 372 場資料無車型/閘門記錄（見 traffic_resources/README.md 字段矩陣）",
    denominator_notes="UNVERIFIED；不得用保有量份額、法定充電位比例或槍位比替代", status="UNVERIFIED", source_class=None,
    limitations=["p_EV_arrival 仍不可識別；這是 T28 標題的核心缺口"])
registry = {
  "schema_version": 1, "date": "2026-10-31", "owner": "ev-data (R2-D/T28)",
  "purpose": "T28 p_EV 证据登记：保有量、新車市售比、公共充電供給/使用/到訪份額分開登记，不混用；存量资料只作假设性迁移参考。",
  "request_log": "research/official_data_20261031/identification_20261031/t28_requests.jsonl",
  "request_budget": {"get_requests": sum(1 for r in rows if r.get("method")=="GET"), "search_requests": sum(1 for r in rows if r.get("method")=="SEARCH"),
                     "failed_http": sum(1 for r in rows if r.get("method")=="GET" and r.get("status") not in (200,)),
                     "invalid_content_200": [os.path.basename(r["saved_path"]) for r in rows if r.get("saved_path") and os.path.basename(r["saved_path"]) in ("t28_audit_ev_market_share.pdf","t28_audit_ev_market_share_v2.bin","t28_iot_demand_report_2025.pdf")],
                     "downloaded_bytes": sum(int(r.get("bytes") or 0) for r in rows)},
  "sources": sources,
  "gaps": [
    {"gap_id":"GAP-ACTUAL-SALES-SHARE","question":"實際電動小客車新車市售比（年份序列）","status":"UNVERIFIED","evidence":"審計部報告標題稱未達目標/負成長，但 PDF 未取得；僅有政策目標值","next":"需人工從審計部網站下載 112/113 年度審核報告 PDF，或用公路局新領牌照統計自行計算"},
    {"gap_id":"GAP-PUBLIC-UTILIZATION","question":"公共充電樁使用率（設備時長利用率/充電次數）","status":"UNVERIFIED","evidence":"本次取得的官方文件無使用率數字","next":"能源署/交通部充電資訊平臺可能有；需帳號或另尋統計"},
    {"gap_id":"GAP-LOT-ARRIVAL-SHARE","question":"場站 EV 到訪份額 p_EV_arrival","status":"UNVERIFIED","evidence":"無場站級車型統計；台北資料無車型/閘門","next":"需停車場業者閘門/ANPR 資料或人工調查"},
    {"gap_id":"GAP-Z-MECHANISM","question":"z 的觀測覆蓋率 m/k","status":"UNVERIFIED","evidence":"mechanism_audit §5；無獨立到達/會話真值","next":"需一段人工計數的黃金標準時段"}
  ],
  "allowed_uses": ["stock/supply 作为情景背景", "政策目标作为政策语境", "存量份额作为假设性迁移参考（须标注）"],
  "forbidden_uses": ["用保有量份额当 p_EV_arrival", "用政策目标值当实际市售比", "用法定充电位比例当 EV 到访份额", "用 2024/2025/2026 不同口径的車樁比直接比较"],
  "retrieved_notes": "GET 8 次中 1 次 HTTP 500、3 次 200 但内容为 HTML/非 PDF（已保留原件并标 UNVERIFIED）；SEARCH 2 次作为定位记录。"
}
json.dump(registry, open(os.path.join(ident,"t28_p_ev_evidence.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"sources":len(sources),"gaps":len(registry["gaps"]),"requests":registry["request_budget"]}, ensure_ascii=False))
