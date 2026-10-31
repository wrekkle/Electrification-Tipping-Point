"""Build manifests for ev-data outputs: downloaded raw files + consumed local Taipei files. Read-only over sources."""
import hashlib, json, os

PROJ = r"C:\Projects\停车场充电桩优化方案"
BASE = os.path.join(PROJ, "research", "official_data_20261031")
EV = os.path.join(BASE, "ev_behavior")
LOG = os.path.join(BASE, "logs", "ev_behavior_requests.jsonl")
RAW = os.path.join(EV, "raw")
TR = os.path.join(BASE, "traffic_resources")

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

rows = [json.loads(l) for l in open(LOG, encoding="utf-8") if l.strip()]
ok_rows = [r for r in rows if r.get("saved_path")]
fail_rows = [r for r in rows if not r.get("saved_path")]
total_bytes = sum(int(r.get("bytes") or 0) for r in ok_rows)

META = {
 "M10_TUE_fulltext.pdf": dict(source_id="EVB-M10-FULLTEXT", title="A scenario-based stochastic programming approach for the public charging station location problem (institutional full text)", org="Eindhoven University of Technology institutional repository (Transportmetrica B article)", official=False, source_class="peer_reviewed", region="NL", period="2017 survey data; published 2022", unit_notes="PDF 30 pages; Table 3 on PDF p.12-13", sample_filter="none (verification copy)", what_it_supports=["M10 Table 3 training/validation counts (6187/2062, 1486/469)", "denominator definition of out-of-home charging decision cases"], limitations=["self-reported decisions", "100 users", "mixed charger access contexts"]),
 "M13_nature_article.html": dict(source_id="EVB-M13-OA", title="Large-scale empirical study of electric vehicle usage patterns and charging infrastructure needs (open-access article HTML)", org="npj Sustainable Mobility and Transport (Nature Portfolio)", official=False, source_class="peer_reviewed", region="CN (7 cities)", period="data period not fully extracted", unit_notes="HTML; parsed text source_review/m13_nature_text.txt", sample_filter="1.6M EVs, 73 fields", what_it_supports=["daily charging events medians 0.81/1.14/1.67 (q_day type)", "SOC before/after charging by power level", "data availability statement pointing to Zenodo"], limitations=["underlying data not downloaded (Zenodo SSL failure)", "correction not inspected"]),
 "IOT_public_charging_demand_table.pdf": dict(source_id="EVB-TW-IOT", title="電動車公共充電樁設施設置需求評估之研究 (report PDF)", org="交通部運輸研究所 (Institute of Transportation, MOTC, Taiwan)", official=True, source_class="official", region="TW", period="content updated to 2024-09-30; 2023 user survey", unit_notes="804 pages; EV stock/pile tables and 4.6 survey sections used", sample_filter="EV users only (n=2,027 valid)", what_it_supports=["EV stock 87,182 / 8,384,318 (1.04%), Taipei 21,399", "public charging guns 7,146 (2,253 DC/4,893 AC), Taipei 1,491", "car-to-gun ratios AC 17.7:1, DC 38.5:1", "self-reported charging frequency, public share 4/10, duration 72 min, SOC 29%, queue <=10 min"], limitations=["no parking-event denominator", "self-reported survey", "rated power per connector not tabulated", "home-charger share chart-only (not digitised)"]),
 "AFDC_vehicle_registration_2024.html": dict(source_id="EVB-US-AFDC-REG", title="Vehicle Registration Counts by State (AFDC)", org="U.S. Department of Energy, Alternative Fuels Data Center", official=True, source_class="official", region="US", period="2024", unit_notes="HTML table; states + United States total", sample_filter="none", what_it_supports=["US EV registrations total 4,503,700; California 1,533,900"], limitations=["state column mapping not fully validated (sum of parsed state rows double counts)", "stock not arrival share"]),
 "AFDC_stations_states.html": dict(source_id="EVB-US-AFDC-STATIONS", title="Alternative Fueling Station Counts by State (AFDC page)", org="U.S. Department of Energy, Alternative Fuels Data Center", official=True, source_class="official", region="US", period="current page 2026-10-31", unit_notes="HTML page; table appears JS-driven, public charging port counts not digitised", sample_filter="none", what_it_supports=["exists as official source for public station/port counts by state"], limitations=["numbers not extracted; not used numerically"]),
 "epa_vehicles.csv.zip": dict(source_id="EVB-US-EPA-VEH", title="Fuel Economy Data (vehicles.csv zip)", org="U.S. Department of Energy / EPA fueleconomy.gov", official=True, source_class="official", region="US", period="model years through latest file release", unit_notes="zip -> vehicles.csv, 50,407 rows, 1,608 EV rows with range", sample_filter="all model-year records", what_it_supports=["official EV range/consumption proxies (range median 282 mi, 29-520)"], limitations=["range is not battery capacity", "no charging power", "US models only"]),
 "ACN_research.html": dict(source_id="EVB-ACN-DOC", title="ACN-Data / ACN-Sim research page", org="Caltech Adaptive Charging Network", official=False, source_class="institutional_report", region="US-CA", period="2026-10-31 page", unit_notes="HTML research page", sample_filter="workplace charging sessions", what_it_supports=["dataset type and scope for M15 note", "charging-session denominator with no non-charging parking events"], limitations=["dataset not downloaded", "paper record SSL blocked"]),
 "uk_datagov_ckan_search.json": dict(source_id="EVB-UK-CKAN1", title="data.gov.uk CKAN dataset search: electric vehicle charging infrastructure", org="UK government open data portal", official=True, source_class="official", region="UK", period="2026-10-31", unit_notes="JSON query result, 5 datasets", sample_filter="none", what_it_supports=["discovery of local EV charging open data incl. Barnet transactions"], limitations=["gov.uk DfT statistics host blocked by TLS; national device statistics not obtained"]),
 "uk_datagov_ckan_device.json": dict(source_id="EVB-UK-CKAN2", title="data.gov.uk CKAN search: electric vehicle charging device statistics", org="UK government open data portal", official=True, source_class="official", region="UK", period="2026-10-31", unit_notes="JSON, empty result", sample_filter="none", what_it_supports=["documents the failed search for DfT charging device statistics"], limitations=["no DfT national charging device statistics obtained"]),
 "crossref_M11.json": dict(source_id="EVB-M11-CROSSREF", title="Crossref metadata record for M11 (10.1080/26941899.2025.2605778)", org="Crossref", official=False, source_class="peer_reviewed", region="US", period="2026-10-31 query", unit_notes="metadata only; no abstract", sample_filter="none", what_it_supports=["bibliographic record for M11"], limitations=["no definitions/denominators; M11 full text HTTP 403"]),
 "crossref_M12.json": dict(source_id="EVB-M12-CROSSREF", title="Crossref metadata record for M12 (10.1016/j.trd.2025.105094)", org="Crossref", official=False, source_class="peer_reviewed", region="JP", period="2026-10-31 query", unit_notes="metadata only; no abstract", sample_filter="none", what_it_supports=["bibliographic record for M12"], limitations=["no definitions/denominators; M12 full text HTTP 403"]),
 "barnet_cityev_2021Q2.csv": dict(source_id="EVB-UK-BARNET", title="Electric Vehicle Charging Transactions - CityEV 2021 Q2", org="London Borough of Barnet (local government open data)", official=True, source_class="official", region="UK-London-Barnet", period="2021 Q2", unit_notes="CSV 44,225 rows; plug/unplug/charge start/end + kWh per session", sample_filter="charging sessions only", what_it_supports=["device time utilisation and post-charge connection dwell (partial sample, 856 parseable rows)"], limitations=["only charging sessions; no parking denominator", "column misalignment suspected for most rows", "single operator/borough"]),
 "datataipei_parking_dataset.html": dict(source_id="EVB-TW-DATATPEI", title="臺北市停車場資訊 dataset page (data.taipei)", org="Taipei City Government open data platform", official=True, source_class="official", region="TW-TPE", period="2026-10-31 page", unit_notes="dataset metadata page; resource list is JS-driven", sample_filter="none", what_it_supports=["dataset lineage for the Taipei parking/charging collection used by traffic_resources"], limitations=["resource download endpoints not resolved via API this round; no new raw station data downloaded"]),
 "datataipei_parking_resources.json": dict(source_id="EVB-TW-DATATPEI-RES", title="data.taipei dataset resource API probe (2-byte response)", org="Taipei City Government open data platform", official=True, source_class="official", region="TW-TPE", period="2026-10-31", unit_notes="empty response saved for evidence", sample_filter="none", what_it_supports=["records the failed API probe"], limitations=["no content"]),
}
entries = []
for r in ok_rows:
    fn = os.path.basename(r["saved_path"])
    meta = META.get(fn, {})
    p = os.path.join(RAW, fn)
    entries.append(dict(
        source_id=meta.get("source_id", "EVB-UNKNOWN-" + fn), title=meta.get("title", fn),
        org=meta.get("org", ""), url=r["url"], retrieved_at_utc=r["t_utc"], http_status=r["status"],
        local_path="research/official_data_20261031/ev_behavior/raw/" + fn,
        sha256=sha(p), bytes=os.path.getsize(p), official=meta.get("official", False),
        source_class=meta.get("source_class", "unspecified"), region=meta.get("region", ""),
        period=meta.get("period", ""), unit_notes=meta.get("unit_notes", ""),
        sample_filter=meta.get("sample_filter", ""), revision="v1 2026-10-31",
        what_it_supports=meta.get("what_it_supports", []), limitations=meta.get("limitations", [])))
manifest = dict(schema_version=1, date="2026-10-31", owner="ev-data",
  purpose="Official/public source downloads for charging-probability evidence; hashes recomputed from local files.",
  request_budget=dict(requests_logged=len(rows), requests_limit=60, downloaded_bytes=total_bytes, bytes_limit=200*1024*1024),
  failed_requests=[{k: r.get(k) for k in ("seq","t_utc","method","url","purpose","status","error")} for r in fail_rows],
  entries=entries,
  local_reference_files=[dict(path="papers/electrification-math/M08_INL-parking-event-charging-rate_2015.pdf", sha256=sha(os.path.join(PROJ,"papers","electrification-math","M08_INL-parking-event-charging-rate_2015.pdf")), role="M08 verification (existing local copy, not downloaded this round)", note="evidence.json/rates.json reuse unchanged")],
  log_file="research/official_data_20261031/logs/ev_behavior_requests.jsonl")
json.dump(manifest, open(os.path.join(EV, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# traffic resources manifest (read-only local files)
TR_FILES = [
 ("research/collection/taipei_372_polling_20261030/data/static/cohort_static.json", "cohort definition: 372 sites, baseline_totalcar, baseline_connector_count", True),
 ("research/collection/taipei_372_polling_20261030/data/2026-10-30/parking_slots.jsonl", "5-min net occupancy 2026-10-30 (54,684 rows)", False),
 ("research/collection/taipei_372_polling_20261030/data/2026-10-30/connector_status_long.jsonl", "connector status 2026-10-30 (267,994 rows)", False),
 ("research/collection/taipei_372_polling_20261030/data/2026-10-31/parking_slots.jsonl", "5-min net occupancy 2026-10-31 partial (49,476 rows)", False),
 ("research/collection/taipei_372_polling_20261030/data/2026-10-31/connector_status_long.jsonl", "connector status 2026-10-31 partial (248,837 rows)", False),
 ("research/collection/taipei_source_20261030/parking_charging_inventory.csv", "443 lots with charging tag (static+dynamic snapshot)", True),
 ("research/collection/taipei_source_20261030/all_parking_inventory.csv", "1,775 static lots inventory", True),
 ("research/collection/taipei_source_20261030/summary.json", "collection summary: 1,775 static / 1,230 dynamic / 443 charging / 2,117 connector rows", True),
 ("research/collection/taipei_source_20261030/raw/static.xml", "official static parking API payload (4,123,840 bytes)", True),
 ("research/collection/taipei_source_20261030/raw/dynamic.xml", "official dynamic occupancy API payload (686,810 bytes)", True),
 ("research/official_data_20261031/traffic_resources/summary_stats.json", "derived: cohort/polling counts and status counts", True),
 ("research/official_data_20261031/traffic_resources/summary_stats_extra.json", "derived: connector hashes/EPA/Barnet/AFDC stats", True),
 ("research/official_data_20261031/traffic_resources/summary_stats_extra2.json", "derived: robust Barnet stats and Taipei slot/commit coverage", True),
 ("research/official_data_20261031/ev_behavior/derived/barnet_session_stats.json", "derived session stats (856 valid rows)", True),
]
tentries = []
for rel, role, do_hash in TR_FILES:
    p = os.path.join(PROJ, rel)
    if not os.path.exists(p):
        continue
    tentries.append(dict(path=rel, bytes=os.path.getsize(p), sha256=(sha(p) if do_hash and os.path.getsize(p) <= 20*1024*1024 else None),
                         role=role, read_mode="read-only streaming" if not do_hash else "read-only",
                         sha256_note=None if (do_hash and os.path.getsize(p) <= 20*1024*1024) else "not hashed: active collector large file read in streaming mode; size recorded"))
trmanifest = dict(schema_version=1, date="2026-10-31", owner="ev-data",
  purpose="Local Taipei data consumed read-only for station/traffic field inventory; no source data modified.",
  upstream_official_dataset="https://data.taipei/dataset/detail?id=d5c0656b-5250-4179-a491-c94daa56ef2c",
  files=tentries,
  derived_outputs=["research/official_data_20261031/traffic_resources/README.md", "research/official_data_20261031/traffic_resources/summary_stats.json"])
json.dump(trmanifest, open(os.path.join(TR, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"log_requests": len(rows), "ok": len(ok_rows), "failed": len(fail_rows), "downloaded_bytes": total_bytes,
                  "raw_entries": len(entries), "traffic_entries": len(tentries)}, ensure_ascii=False))
