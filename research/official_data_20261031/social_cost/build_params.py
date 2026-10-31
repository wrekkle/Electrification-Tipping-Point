"""生成 parameter_candidates_20261031.json（CONTRACT §2 schema v3）。数值来自 _computed.json，不手抄。"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(ROOT, "research", "cost_model_20261030", "parameter_candidates_20261031.json")
c = json.load(open(os.path.join(HERE, "_computed.json"), encoding="utf-8"))
req = json.load(open(os.path.join(HERE, "_reqsum.json"), encoding="utf-8"))
files = {f["local_path"]: f for f in c["files"]}
oil, cpi, vot = c["oil"], c["cpi"], c["vot"]
SHA = lambda p: (files.get(p) or {}).get("sha256")


def P(param_id, name_zh, definition, *, value, unit, status, region="台灣", period=None, price_year=None,
      vehicle_scope="小客車", scenario_scope=None, source_ids=None, source_class="official", locator=None,
      estimation_method=None, uncertainty=None, limitations=None, is_scenario=False, admitted_use=None,
      source_file_sha256=None, candidate_sources=None, **extra):
    d = {
        "param_id": param_id, "name_zh": name_zh, "definition": definition,
        "probability_object": None, "numerator": None, "denominator": None, "denominator_definition": None,
        "unit": unit, "region": region, "period": period, "vehicle_scope": vehicle_scope,
        "scenario_scope": scenario_scope, "price_year": price_year, "value": value,
        "source_ids": source_ids or [], "source_class": source_class, "locator": locator,
        "estimation_method": estimation_method,
        "uncertainty": uncertainty or {"low": None, "high": None, "type": None},
        "limitations": limitations or [], "is_scenario": is_scenario,
        "admitted_use": admitted_use or [], "status": status,
        "source_file_sha256": source_file_sha256,
    }
    if candidate_sources:
        d["candidate_sources"] = candidate_sources
    d.update(extra)
    return d

PARAMS = []
A = PARAMS.append
HB = "research/official_data_20261031/social_cost/raw/pdf/iot_108_handbook_110c_params.pdf"
CPIM = "research/official_data_20261031/social_cost/raw/pdf/dgbas_price_monthly.pdf"
CPIN = "research/official_data_20261031/social_cost/raw/pdf/dgbas_cpi_news_11509.pdf"
OIL = "research/official_data_20261031/social_cost/raw/html/oil_price_range_2025_2026.json"
TPB = "research/official_data_20261031/social_cost/raw/pdf/taipower_brief_price_2026.pdf"
MOE = "research/official_data_20261031/social_cost/raw/pdf/moenv_ghg_factors_2024.pdf"
EY = "research/cost_model_20261030/downloads/ey_time_value_handbook_excerpt.pdf"

# ---------- 0. CPI 辅助 ----------
A(P("cpi_index_base2021", "消費者物價總指數（110年=100，年指數）",
    "主計總處 CPI 總指數年指數；用於把不同幣值年的官方金額換算到目標年。",
    value={"2009": cpi["2009"], "2018": cpi["2018"], "2024": cpi["2024"],
           "2025_derived": cpi["2025_derived"], "2026_ytd_derived": cpi["2026_ytd_derived"]},
    unit="index（110年=100）", status="available", period="民國51年–114年5月（2025、2026 為推算）",
    source_ids=["S-02-DGBAS-CPI-MONTHLY", "S-03-DGBAS-CPI-NEWS"], locator="表1-8 消費者物價總指數銜接表（年指數欄）；2025/2026 由年增率鏈式推算",
    estimation_method="2009/2018/2024 為官方年指數；2025=2024×(1+1.66%)，2026(1-9月平均)=2025×(1+1.94%)，年增率取自 115年9月新聞稿",
    uncertainty={"low": cpi["2026_ytd_derived"] - 0.4, "high": cpi["2026_ytd_derived"] + 0.4, "type": "rounding_chain"},
    limitations=["2025/2026 為年增率鏈式推算，非官方指數水準；年增率四捨五入有小誤差", "2026 年全年指數尚未發布，1-9 月平均為代理"],
    admitted_use=["validation"], source_file_sha256=SHA(CPIM)))

# ---------- 1. 時間價值 ----------
A(P("vot_passenger_car_city_2009_TWD_per_vehicle_minute", "時間價值（小客車·都會一般化，2009 年幣值）",
    "運研所手冊前期版表5-6 每車時間價值都會一般化小客車值；本輪用 108 年手冊「前期手冊建議值」列交叉核對一致。",
    value=3.61, unit="TWD/(車·分鐘)", status="available", period="民國98年幣值",
    price_year=2009, source_ids=["S-13-CARRIED-EY-HANDBOOK", "S-01-IOT-HANDBOOK-108"],
    locator="108年手冊 表5-6「前期手冊建議值／都會一般化時間價值／小客車」；原引 100年9月手冊 表5-6",
    estimation_method="直接取官方建議值", admitted_use=["sensitivity_only", "validation"],
    source_file_sha256=SHA(EY), limitations=["2009 年幣值；未調整不得直接用於 2026 算例，只作換算輸入與交叉核對"]))

A(P("vot_passenger_car_city_2018_TWD_per_vehicle_minute", "時間價值（小客車·都會一般化，2018 年幣值）",
    "運研所 108 年手冊（110年12月更新版）表5-6 本手冊建議值：都會一般化時間價值／小客車。",
    value=5.93, unit="TWD/(車·分鐘)", status="available", period="民國107年幣值",
    price_year=2018, source_ids=["S-01-IOT-HANDBOOK-108"], locator="108年手冊 表5-6（PDF p.55／內頁 p.43）本手冊建議值",
    estimation_method="直接取官方建議值（工資率×工資調整比例×乘載率）",
    admitted_use=["sensitivity_only", "validation"], source_file_sha256=SHA(HB),
    limitations=["手冊建議未來值以工資上漲率調整，不是 CPI", "都會定義含台北市等 10 縣市，非台北市單獨值"]))

A(P("vot_passenger_car_city_2026_TWD_per_vehicle_minute", "時間價值（小客車·都會一般化，換算至 2026 年幣值，主值）",
    "以 108 年手冊 2018 年幣值 5.93 為主值，乘 CPI 2018→2026 鏈式因子。",
    value=vot["chain_2018_to_2026_min"], unit="TWD/(車·分鐘)", status="available",
    period="2018 幣值→2026 年 1-9 月價格水準", price_year=2026,
    source_ids=["S-01-IOT-HANDBOOK-108", "S-02-DGBAS-CPI-MONTHLY", "S-03-DGBAS-CPI-NEWS"],
    locator="5.93 × CPI_2026(111.7258)/CPI_2018(97.76)",
    estimation_method="CPI 鏈式換算（非手冊建議的工資上漲率）",
    uncertainty={"low": vot["chain_2009_to_2026_min"], "high": vot["chain_2018_to_2026_min"], "type": "conversion_method_range"},
    limitations=["手冊明示未來值應以工資上漲率調整；CPI 僅為保守下限（2009→2018 手冊自身由 3.61 修訂至 5.93，+64%，同期 CPI 僅 +9.8%）",
                 "若改用薪資成長率，結果會高於本值；本值為可辯護的下界，不宜宣稱唯一真值",
                 "2026 價格水準為 1-9 月平均代理"],
    admitted_use=["social_cost", "sensitivity_only"], source_file_sha256=SHA(HB),
    conversion={"formula": "3.61 or 5.93 × CPI_2026 / CPI_base", "cpi_2009": cpi["2009"], "cpi_2018": cpi["2018"],
                "cpi_2026": cpi["2026_ytd_derived"], "chain_2009": vot["chain_2009_to_2026_min"],
                "chain_2018": vot["chain_2018_to_2026_min"], "ratio_handbook_2009_2018": vot["handbook_revision_ratio_2009_2018"],
                "ratio_cpi_2009_2018": vot["cpi_ratio_2009_2018"]}))

A(P("vot_passenger_car_city_2026_lower_cpi_chain_TWD_per_vehicle_minute", "時間價值（小客車·都會一般化，2009 值 CPI 鏈，下限）",
    "以 2009 年幣值 3.61 乘 CPI 2009→2026 鏈式因子，作為下限／敏感性。",
    value=vot["chain_2009_to_2026_min"], unit="TWD/(車·分鐘)", status="available", price_year=2026,
    source_ids=["S-13-CARRIED-EY-HANDBOOK", "S-01-IOT-HANDBOOK-108", "S-02-DGBAS-CPI-MONTHLY", "S-03-DGBAS-CPI-NEWS"],
    locator="3.61 × 111.7258/89.07", estimation_method="CPI 鏈式換算",
    uncertainty={"low": None, "high": vot["chain_2018_to_2026_min"], "type": "lower_bound"},
    limitations=["忽略 2009→2018 手冊方法/乘載率修訂，屬明顯低估", "僅作下限與敏感性"],
    admitted_use=["sensitivity_only"], source_file_sha256=SHA(EY)))

A(P("vot_passenger_car_intercity_2026_TWD_per_vehicle_minute", "時間價值（小客車·城際一般化，換算至 2026）",
    "108 年手冊表5-6 城際一般化小客車 7.58（2018 幣值）× CPI 因子；僅供與都會值對照。",
    value=vot["intercity_2018_to_2026_min"], unit="TWD/(車·分鐘)", status="transferable", price_year=2026,
    scenario_scope="城際旅次，非都會停車情境",
    source_ids=["S-01-IOT-HANDBOOK-108", "S-02-DGBAS-CPI-MONTHLY", "S-03-DGBAS-CPI-NEWS"],
    locator="7.58 × 111.7258/97.76", estimation_method="CPI 鏈式換算",
    limitations=["台北市區停車失敗不屬城際旅次；不得直接入模，僅作區間上界參考"],
    admitted_use=["sensitivity_only"], source_file_sha256=SHA(HB)))

A(P("vot_per_hour_2026", "時間價值後端欄位 vot_per_hour（TWD/小時）",
    "costs.py 的 vot_per_hour 以小時計；由每分鐘值 × 60。",
    value=round(vot["chain_2018_to_2026_min"] * 60, 2), unit="TWD/(車·小時)", status="available", price_year=2026,
    source_ids=["S-01-IOT-HANDBOOK-108", "S-02-DGBAS-CPI-MONTHLY", "S-03-DGBAS-CPI-NEWS"],
    locator="6.7771 × 60", estimation_method="單位換算",
    uncertainty={"low": round(vot["chain_2009_to_2026_min"] * 60, 2), "high": round(vot["chain_2018_to_2026_min"] * 60, 2), "type": "conversion_method_range"},
    limitations=["同 vot_passenger_car_city_2026 的限制"], admitted_use=["social_cost", "sensitivity_only"],
    source_file_sha256=SHA(HB)))

# ---------- 2. 油价 ----------
def oilp(pid, name, key, n, start, end, status="available"):
    v = oil[key]
    return P(pid, name, "台灣中油每周公告零售價之期間算術平均（A92/A95/A98/超級柴油）。",
             value=v["A95"], unit="TWD/L", status=status, period="%s～%s" % (start, end),
             price_year=int(end[:4]), source_ids=["S-04-ENERGY-OIL-API", "S-05-ENERGY-OIL-PAGE"],
             locator="能源署油價資訊管理與分析系統 POST /Gasoline/RetailPrice/load（start/end）",
             estimation_method="期間內每周公告價算術平均（未加權、未插補）",
             uncertainty={"low": None, "high": None, "type": "period_selection"},
             limitations=["95無鉛為小客車常用油品；若模型指定 92/98 需換值", "周資料平均，非日加權"],
             admitted_use=["social_cost", "sensitivity_only"], source_file_sha256=SHA(OIL),
             period_values={"n_obs": n, "A92": v["A92"], "A95": v["A95"], "A98": v["A98"], "diesel": v["diesel"]})

A(oilp("fuel_price_95_unleaded_2026_ytd_TWD_per_liter", "95 無鉛汽油零售價（2026 年初至 9 月底平均）", "2026_ytd", oil["2026_ytd"]["n"], "2026-01-01", "2026-09-30"))
A(oilp("fuel_price_95_unleaded_2025_TWD_per_liter", "95 無鉛汽油零售價（2025 全年平均）", "2025_full", oil["2025_full"]["n"], "2025-01-01", "2025-12-31", status="available"))
A(oilp("fuel_price_95_unleaded_trailing12m_TWD_per_liter", "95 無鉛汽油零售價（近 12 個月平均）", "trailing12m", oil["trailing12m"]["n"], "2025-10-01", "2026-09-30"))
A(oilp("fuel_price_92_unleaded_2026_ytd_TWD_per_liter", "92 無鉛汽油零售價（2026 年初至 9 月底平均）", "2026_ytd", oil["2026_ytd"]["n"], "2026-01-01", "2026-09-30"))
A(oilp("fuel_price_diesel_2026_ytd_TWD_per_liter", "超級柴油零售價（2026 年初至 9 月底平均）", "2026_ytd", oil["2026_ytd"]["n"], "2026-01-01", "2026-09-30"))

# ---------- 3. 电价 ----------
A(P("electricity_tariff_ev_charging_2026", "台電電動車充換電設施電價（現行費率）",
    "台電簡要電價表「低壓電力－時間電價－3.電動車充換電設施電價」全文；本案充電樁適用之費率結構。",
    value={"流動電費_TWD_per_kWh": {"夏月尖峰": 12.47, "夏月離峰": 3.05, "非夏月尖峰": 12.14, "非夏月離峰": 2.90,
                              "週六日及離峰日離峰": {"夏月": 3.05, "非夏月": 2.90}},
           "基本電費": {"按戶計收_TWD_per_戶_月": 262.50, "經常契約_TWD_per瓩_月": {"夏月": 47.20, "非夏月": 34.60}}},
    unit="TWD/kWh（另含 TWD/戶·月、TWD/瓩·月）", status="available", period="現行（表內援引 113年4月、113年10月電價調幅）",
    price_year=2026, scenario_scope="電動車充換電設施（低壓）", source_ids=["S-06-TAIPOWER-BRIEF", "S-10-TAIPOWER-LIST", "S-11-TAIPOWER-EV"],
    locator="簡要電價表 PDF p.8「3.電動車充換電設施電價」",
    estimation_method="官方費率表直接轉錄",
    uncertainty={"low": None, "high": None, "type": None},
    limitations=["表內未印生效日期，UNVERIFIED: 現行費率公告日", "夏月=6/1-9/30；尖峰時段夏月 16-22 時、非夏月 15-21 時",
                 "單一均價需充電時刻分布，本表不提供"],
    admitted_use=["social_cost", "energy_power_dwell"], source_file_sha256=SHA(TPB)))

A(P("electricity_tariff_lowvoltage_flat_2026", "台電低壓電力電價（非時間電價，現行）",
    "若充電樁以一般低壓電力計價（非電動車專用時間電價）之流動電費。",
    value={"夏月_TWD_per_kWh": 4.08, "非夏月_TWD_per_kWh": 3.87}, unit="TWD/kWh", status="available",
    period="現行", price_year=2026, scenario_scope="低壓電力供電（非時間電價）",
    source_ids=["S-06-TAIPOWER-BRIEF", "S-10-TAIPOWER-LIST"], locator="簡要電價表 PDF p.7「四、低壓電力電價（一）非時間電價」",
    estimation_method="官方費率表直接轉錄",
    limitations=["另有基本電費與需量契約，未列入", "夏月=6/1-9/30"],
    admitted_use=["social_cost", "sensitivity_only"], source_file_sha256=SHA(TPB)))

A(P("electricity_price_TWD_per_kWh", "營運電價單值（後端 electricity_price_per_kwh）",
    "costs.py 的 operator_energy 與 EV 繞行充電成本需要單一 TWD/kWh。",
    value=None, unit="TWD/kWh", status="unidentified",
    period="現行費率", price_year=2026, source_ids=["S-06-TAIPOWER-BRIEF"],
    locator="費率表已取得（見 electricity_tariff_ev_charging_2026），但單值不可識別",
    estimation_method=None,
    limitations=["費率依充電發生時段（夏月/非夏月、尖峰/離峰）與契約容量而異；缺少充電時刻分布與契約容量假設 ⇒ 不得填單值",
                 "不得用售電價代替缺電損失（COST-MODEL-V2 §7）"],
    admitted_use=["social_cost"], source_file_sha256=SHA(TPB),
    candidate_sources=[{"title": "台電電動車充換電設施電價（已取得）", "url": "https://www.taipower.com.tw/2289/2290/46940/simpleList",
                        "what_happened": "費率已取得但單值需充電時段結構；此項缺的是行為/負載假設，不是官方價格"}])) 

A(P("electricity_price_scenario_offpeak_nonsummer_TWD_per_kWh", "營運電價情境值（非夏月離峰）",
    "假設全部充電發生在非夏月離峰時段時的電價，供條件化情景；is_scenario=true。",
    value=2.90, unit="TWD/kWh", status="available", is_scenario=True,
    period="非夏月離峰時段", price_year=2026, scenario_scope="假設：全部充電落在非夏月離峰（00:00-15:00、21:00-24:00）",
    source_ids=["S-06-TAIPOWER-BRIEF", "S-10-TAIPOWER-LIST"], locator="簡要電價表 p.8「非夏月離峰時間 每度 2.90」",
    estimation_method="官方費率 + 明確時段假設",
    limitations=["僅適用於上述時段假設；與實際充電時間不符即失效", "不含基本電費與需量契約分攤"],
    admitted_use=["social_cost", "sensitivity_only"], source_file_sha256=SHA(TPB)))

# ---------- 4. 排放 / 碳費 ----------
A(P("co2_emission_factor_gasoline_mobile_kg_per_TJ", "車用汽油 CO2 排放係數（移動燃燒源）",
    "環境部 113年2月5日公告「溫室氣體排放係數」附表一 移動燃燒排放源 車用汽油 CO2。",
    value=69300, unit="kg CO2/TJ", status="available", region="台灣",
    period="113年2月5日公告生效", price_year=None, vehicle_scope="汽油小客車",
    source_ids=["S-08-MOENV-GHG-FACTORS"], locator="附表一 移動燃燒排放源排放係數（PDF p.7／內頁 p.5）",
    estimation_method="官方係數直接取用（基於低位熱值）",
    uncertainty={"low": None, "high": None, "type": None},
    limitations=["係數以低位熱值為基礎；換算 kg/L 需汽油低位熱值，該熱值不在本公告內", "未含 CH4/N2O 之外的污染物（PM2.5/NOx）", "與 2006 IPCC 預設值同源"],
    admitted_use=["social_cost"], source_file_sha256=SHA(MOE)))

A(P("co2_emission_factor_gasoline_kg_per_L", "車用汽油 CO2 排放係數（每公升）",
    "由 kg/TJ 係數乘汽油低位熱值換算；後端 emission_cost_per_km / 油耗×排放計算需要 kg/L。",
    value=None, unit="kg CO2/L", status="unidentified", region="台灣", period="113年2月5日公告",
    source_ids=["S-08-MOENV-GHG-FACTORS"], locator="需 kg/TJ × 低位熱值；低位熱值未取得官方文件",
    estimation_method=None,
    limitations=["環境部公告未給低位熱值與 kg/L；不得用記憶中的 7,800 kcal/L 當官方值"],
    admitted_use=["social_cost"], source_file_sha256=SHA(MOE),
    derivation={"formula": "69300 kg/TJ × LHV(TJ/L)", "lhv_missing": True,
                "scenario_if_lhv_32657_MJ_per_L": {"LHV": "32.657 MJ/L（≈7,800 kcal/L，常見工程值，本輪無官方文件）",
                                                   "value_kg_per_L": round(0.000032657 * 69300, 4),
                                                   "status": "UNVERIFIED 情景值，不得入模"},
                "note": "若日後取得官方汽油低位熱值，直接套上式即可；此項缺的是熱值，不是排放係數"},
    candidate_sources=[{"title": "經濟部能源署 能源產品單位熱值（能源統計/能源平衡表）", "url": "https://www.moeaea.gov.tw/",
                        "what_happened": "本輪未取得可核對的官方汽油低位熱值檔；候選來源待查"}])) 

A(P("carbon_fee_general_TWD_per_tCO2e", "碳費一般費率",
    "環境部公告碳費徵收費率一般費率；本專案僅作 CO2 外部成本敏感性，不代表邊際社會碳成本。",
    value=300, unit="TWD/tCO2e", status="available", region="台灣", period="114年1月1日起",
    source_ids=["S-14-CARRIED-CARBON"], source_class="official",
    locator="前輪已核：環境部新聞「環境部公告『碳費徵收費率』」（113-10-23）",
    estimation_method="官方費率（前輪 verified_official，本輪未重抓）",
    limitations=["法定碳費是對排放源徵收的費率，不是運輸排放邊際社會成本；用於車輛 CO2 屬建模類比",
                 "未涵蓋 PM2.5/NOx 等局部污染物健康成本", "只能作敏感性，不得寫成官方社會成本"],
    admitted_use=["sensitivity_only"], source_file_sha256=None,
    carried_over={"from": "research/cost_model_20261030/parameters.json#carbon_fee_general_TWD_per_tCO2e",
                  "note": "本輪未重抓；候選值 50/100 為優惠費率 A/B"})) 

# ---------- 5. 既有官方值（前轮核，复用） ----------
A(P("fuel_idle_consumption_car_L_per_hour", "小客車停等（怠速）油耗",
    "運研所培訓講義轉引之停等油耗；僅適用怠速/停等段，不含行駛。",
    value=0.82, unit="L/小時", status="available", region="台灣", period="民國97年資料",
    source_ids=["S-13-CARRIED-EY-HANDBOOK"], locator="臺鐵集集支線核定本 §C 耗油率（轉引 運研所 97 年培訓講義）；前輪已核",
    estimation_method="官方轉引值",
    limitations=["只覆蓋停等；繞行行駛油耗 L/km 仍缺（見 fuel_consumption_L_per_km）", "前輪未重抓但已目視核對"],
    admitted_use=["social_cost", "sensitivity_only"], source_file_sha256=SHA(EY)))

from build_params_nulls import add_null_params

PARAMS = add_null_params(P, A, SHA, PARAMS)

from build_params_extra import add_extra

PARAMS = add_extra(P, A, SHA, cpi, PARAMS)

# ---------- 汇总 ----------
nulls = [p["param_id"] for p in PARAMS if p["value"] is None]
classification = {
 "can_enter_complete_social_cost": [p["param_id"] for p in PARAMS if p["status"] == "available" and p["value"] is not None and p["admitted_use"] and "social_cost" in p["admitted_use"] and not p["is_scenario"]],
 "sensitivity_only": [p["param_id"] for p in PARAMS if "sensitivity_only" in p["admitted_use"] or p["is_scenario"]],
 "unidentified": nulls,
 "transferable_not_local": [p["param_id"] for p in PARAMS if p["status"] == "transferable"],
}
doc = {
 "_meta": {
  "file": "research/cost_model_20261030/parameter_candidates_20261031.json",
  "schema": "CONTRACT §2 schema v3",
  "owner": "cost-data", "generated": "2026-10-31",
  "cost_model_version_ref": "v2-2026-10-30",
  "contract": "research/official_data_20261031/contract/CONTRACT.md",
  "rules": [
    "本文件不改动 parameters.json；它是候选参数，供 Lead 的 parameter_registry 合并。",
    "无来源一律 null；禁止填 0、禁止套演示默认值。",
    "法定碳費≠邊際社會碳成本；停车费/充电费/罚金/补贴≠社会资源成本；国外值不得按汇率当本地值。",
    "价格年份/地域/时期不一致必须写换算依据；本文件所有换算见 conversion 字段。",
  ],
  "request_summary": {"total_requests": req["n_requests"], "web_search_queries": req["n_searches"],
                      "failed_requests": req["n_failed"], "downloaded_bytes": req["total_bytes"],
                      "budget": "≤60 请求 / ≤200MB / ≤45 分钟", "first_utc": req["first"], "last_utc": req["last"]},
  "sources_file": "research/official_data_20261031/social_cost/manifest.json",
 },
 "parameters": {p["param_id"]: p for p in PARAMS},
 "missing_parameters": nulls,
 "classification": classification,
 "computable_items_after_this_file": {
   "user_time": "仍需 Δt（搜索/绕行/步行）与 vot；vot 已可用（2026 主值 6.7771 TWD/(車·分)），Δt 全缺 ⇒ 项 null",
   "operator_energy": "费率表已取得；单值需充电时段结构 ⇒ 默认 null，或声明 scenario 后按 2.90 元/度 算条件化值",
   "ice_vehicle_operating": "油价已可用（95無鉛 31.7385 TWD/L）；缺 L/km 行驶油耗 ⇒ 项 null",
   "ice_external / ev_external": "CO2 系数 kg/TJ 已有；缺 kg/L（需官方低位热值）与污染物分项 ⇒ 项 null",
   "operator_capital_depreciation": "缺 EVSE capex/寿命/折现率 ⇒ null",
   "operator_maintenance": "缺维护成本 ⇒ null",
   "complete_social_cost": "不可算（total=null, complete=false），只能输出条件化情景与 missing_parameters",
 },
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(doc, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("params:", len(PARAMS), "nulls:", len(nulls))
print("can_enter:", classification["can_enter_complete_social_cost"])
print("unidentified:", nulls)
print("wrote", OUT, os.path.getsize(OUT), "bytes")
