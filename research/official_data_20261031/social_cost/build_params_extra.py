"""Lead 复核追加的参数块（cost-data, 2026-10-31）。由 build_params.py 调用；本文件单独存在以避免单文件过长。"""
def add_extra(P, A, SHA, cpi, PARAMS):
    # ================= 7. Lead 复核追加（2026-10-31）：设施成本、CO2 kg/L、LHV =================
    NLMA = "research/official_data_20261031/social_cost/raw/pdf/nlma_ghg_inventory_2023.pdf"
    THB = "research/official_data_20261031/social_cost/raw/pdf/thb_public_charging_plan.pdf"
    CBC = "research/official_data_20261031/social_cost/raw/html/cbc_fx_statistics.html"
    P26 = "research/ev_parking_math_20261029/PDFs/P26_An_Online_Admission_Control_Mechanism_for_Electric_Vehicles_at_Public_Parking_Infrastructures.pdf"
    CPI2019 = 98.30
    FX2019 = 30.9
    FX2019_NOTE = "UNVERIFIED：2019 年新台幣對美元年平均匯率；央行 2019 年報外匯章節（已落盤）未印平均匯率水準，本輪 60 次請求額度用完前未取得可直接引用的官方年平均值。此值須以央行官方年平均值替換後才可去掉 is_scenario。"
    CAPEX_USD = (3308 + 3343) / 2
    CAPEX_TWD2019 = CAPEX_USD * FX2019
    CPI_FAC_2019_2026 = cpi["2026_ytd_derived"] / CPI2019
    CAPEX_TWD2026 = CAPEX_TWD2019 * CPI_FAC_2019_2026
    LIFE = 10
    ANNUAL_CAPEX = CAPEX_TWD2026 / LIFE
    MAINT_USD_PER_PED_YEAR = 75 * 12
    MAINT_USD_PER_CONN_YEAR = MAINT_USD_PER_PED_YEAR / 2
    MAINT_TWD2026 = MAINT_USD_PER_CONN_YEAR * FX2019 * CPI_FAC_2019_2026
    ANNUAL_TOTAL = ANNUAL_CAPEX + MAINT_TWD2026

    # CO2 kg/L：環境部公告 kg/TJ + 國土管理署盤查報告書轉列 kg/L（兩個官方數互證，並反推低位熱值）
    A(P("co2_emission_factor_gasoline_kg_per_L", "車用汽油 CO2 排放係數（每公升）",
        "環境部 113 年公告以 kg/TJ 給係數；國土管理署溫室氣體盤查報告書 p.23 以 2.263132872 kg CO2/L 轉列同一係數（固定源/移動源汽油同值）。",
        value=2.263132872, unit="kg CO2/L", status="available", region="台灣",
        period="環境部 113-02-05 公告；國土管理署報告書（2023 年盤查）轉列", 
        source_ids=["S-08-MOENV-GHG-FACTORS", "S-19-NLMA-GHG-INVENTORY"], source_class="official",
        locator="環境部公告 附表一 移動燃燒源（69,300 kg/TJ）；國土管理署報告書 p.23「移動源 汽油 2.263132872 kg CO2/L」",
        estimation_method="官方公告 kg/TJ × 汽油低位熱值；由官方轉列之 kg/L 反推 LHV=32.657 MJ/L 互證（69300×3.2657e-5=2.26313）",
        uncertainty={"low": 2.2630, "high": 2.2633, "type": "source_rounding"},
        limitations=["kg/L 為政府盤查報告書之轉列值（二次轉列），非環境部公告正文；與公告 kg/TJ 完全相容",
                     "僅 CO2，不含 CH4/N2O 與空氣污染物（PM2.5/NOx）", "對應汽油低位熱值 32.657 MJ/L，若車輛實際燃料不同需調整"],
        admitted_use=["social_cost"], source_file_sha256=SHA(NLMA),
        verification={"mienv_kg_per_TJ": 69300, "nlma_kg_per_L": 2.263132872,
                      "implied_LHV_MJ_per_L": round(2.263132872 / 69300 * 1e6, 4)}))

    A(P("gasoline_lower_heating_value_MJ_per_L", "車用汽油低位熱值（由兩個官方數反推）",
        "環境部公告 69,300 kg CO2/TJ 與國土管理署轉列 2.263132872 kg CO2/L 兩個官方值相除，得汽油低位熱值。",
        value=round(2.263132872 / 69300 * 1e6, 4), unit="MJ/L", status="available", region="台灣",
        period="2024 公告 + 2023 盤查報告", source_ids=["S-08-MOENV-GHG-FACTORS", "S-19-NLMA-GHG-INVENTORY"],
        source_class="derived", locator="2.263132872 kg/L ÷ 69,300 kg/TJ",
        estimation_method="由兩個官方係數反推（3.2657e-5 TJ/L = 32.657 MJ/L ≈ 7,800 kcal/L）",
        uncertainty={"low": None, "high": None, "type": "derived_from_official"},
        limitations=["反推值，不是官方直接公布之熱值；僅用於 kg/TJ↔kg/L 換算與合理性檢查", "≈7,800 kcal/L 與常見工程值一致，但不得反過來當作熱值官方來源"],
        admitted_use=["social_cost", "validation"], source_file_sha256=SHA(NLMA)))

    # 官方每槍補助額度（可作設施成本上限錨點）
    A(P("evse_subsidy_cap_TWD_per_connector_official", "公共充電樁每槍補助額度（交通部計畫）",
        "交通部「公共充電樁設置及區域充電需求評估計畫（修正計畫）」補助額度：快充每槍 200 萬元、慢充每槍 8 萬元、充電樁資訊管理系統每套 80 萬元。",
        value={"慢充AC_TWD_per_槍_額度上限": 80000, "快充DC_TWD_per_槍_額度上限": 2000000, "充電樁資訊管理系統_TWD_per_套": 800000},
        unit="TWD/槍（補助額度上限）", status="available", region="台灣",
        period="2023-2024 計畫（2022-09-26 核定，修正後）", price_year=2022,
        source_ids=["S-18-THB-CHARGING-PLAN"], locator="修正計畫 p.4/p.13/p.15「快充每槍200萬元或慢充8萬元…之額度基礎內」",
        estimation_method="官方補助額度直接轉錄",
        uncertainty={"low": None, "high": None, "type": None},
        limitations=["這是『補助額度上限』，不是實際決標成本；實際成本可能低於或高於額度（超額自籌）",
                     "額度對應的設備規格/是否含安裝與配電擴容，計畫文字未逐項列明", "補助本身屬轉移支付，不進 social_total；只作成本上限錨點"],
        admitted_use=["sensitivity_only"], source_file_sha256=SHA(THB)))

    # P26 可追溯換算：USD 2019 → TWD 2026
    A(P("evse_capex_usd2019_per_connector_transferable", "EVSE 單槍建置成本（P26，2019 前後 USD，LA）",
        "Tucker & Alizadeh (2020) P26：pedestal EVSE install 3,308 USD；每增加一槍 cable 3,343 USD。以 2 槍 pedestal 攤成單槍 = (3308+3343)/2。",
        value={"pedestal_evse_install_usd": 3308, "per_extra_cable_usd": 3343, "per_connector_2gun_usd": CAPEX_USD},
        unit="USD/槍（2019 前後，LA 場景）", status="transferable", region="美國洛杉磯",
        period="2019 前後（P26 引 AFDC/DOE 2015 EVSE cost report，本輪未讀原報告）",
        price_year=2019, vehicle_scope="充電設備", source_class="peer_reviewed",
        source_ids=["S-17-P26-PAPER"], locator="P26 p.10 §IV-E Infrastructure Recommendation",
        estimation_method="論文值直接取用；2 槍配置攤提",
        uncertainty={"low": None, "high": None, "type": None},
        limitations=["外地（LA）且非台灣採購價；不得直接當台北成本", "P26 轉引 AFDC/DOE 2015，原報告未讀", "未含配電擴容、土木、審查等項目"],
        admitted_use=["sensitivity_only"], source_file_sha256=SHA(P26),
        applies_to_taipei=False))

    A(P("evse_lifetime_years_scenario", "EVSE 設備壽命（情景，無官方值）",
        "折舊分攤所需設備壽命；無台灣官方值，取工程常用區間作情景。",
        value=LIFE, unit="年", status="unidentified", region="台灣", scenario_scope="情景假設：8–12 年，中值 10 年",
        source_class="scenario", source_ids=[], locator=None,
        estimation_method="情景假設（非估計值）", is_scenario=True,
        uncertainty={"low": 8, "high": 12, "type": "scenario_range"},
        limitations=["無官方來源；不得寫成已校準值", "若日後取得台電/縣市維護契約或設備規格書年限，應替換"],
        admitted_use=["sensitivity_only"], source_file_sha256=None))

    A(P("evse_capex_TWD_per_connector_2026_transferable", "EVSE 單槍建置成本換算至 2026 年新台幣（可追溯）",
        "P26 USD(2019) × 2019 年平均匯率 → TWD(2019) × CPI 2019→2026 → TWD(2026)；含安裝與 2 槍配置攤提。",
        value=round(CAPEX_TWD2026, 2), unit="TWD/槍（2026 年幣值）", status="transferable", region="台灣（來源為 LA）",
        period="2019 來源 → 2026 幣值", price_year=2026, vehicle_scope="充電設備",
        source_class="derived", source_ids=["S-17-P26-PAPER", "S-16-CBC-FX", "S-02-DGBAS-CPI-MONTHLY", "S-03-DGBAS-CPI-NEWS"],
        locator="3,325.5 USD × 30.9 TWD/USD × (111.7258/98.30)",
        estimation_method="可追溯換算：USD 2019 →（央行 2019 平均匯率）TWD 2019 →（主計總處 CPI 2019→2026）TWD 2026",
        uncertainty={"low": round(CAPEX_TWD2019 * 0.97, 0), "high": round(CAPEX_TWD2026 * 1.10, 0), "type": "fx_and_config_range"},
        limitations=["FX 30.9 為 UNVERIFIED（央行年報章節未印平均匯率），須以官方年平均替換", "2 槍 pedestal 攤提假設；1 槍配置會較高",
                     "未含配電擴容、土木與審查費", "與交通部慢充補助額度 8 萬元/槍相比偏高，兩者不宜直接互換（見 evse_subsidy_cap）"],
        is_scenario=True, admitted_use=["social_cost", "sensitivity_only"], source_file_sha256=SHA(P26),
        applies_to_taipei=False,
        derivation={"formula": "USD_2019 × FX_2019 × (CPI_2026 / CPI_2019)",
                    "usd_per_connector_2019": CAPEX_USD, "fx_2019_twd_per_usd": FX2019, "fx_status": FX2019_NOTE,
                    "cpi_2019": CPI2019, "cpi_2026": cpi["2026_ytd_derived"], "cpi_factor": round(CPI_FAC_2019_2026, 6),
                    "twd_2019": round(CAPEX_TWD2019, 2), "twd_2026": round(CAPEX_TWD2026, 2)}))

    A(P("evse_maintenance_TWD_per_connector_year_2026_transferable", "EVSE 維護成本換算（P26，每每年）",
        "P26 networking/maintenance 75 USD/月/pedestal → ×12 → /2 槍 → 匯率與 CPI 換算。",
        value=round(MAINT_TWD2026, 2), unit="TWD/槍·年（2026 年幣值）", status="transferable", region="台灣（來源為 LA）",
        period="2019 來源 → 2026 幣值", price_year=2026, source_class="derived",
        source_ids=["S-17-P26-PAPER", "S-16-CBC-FX", "S-02-DGBAS-CPI-MONTHLY", "S-03-DGBAS-CPI-NEWS"],
        locator="P26 p.10：networking/maintenance 75 USD/月（pedestal）",
        estimation_method="75 USD×12÷2 槍 ×30.9 ×(111.7258/98.30)",
        uncertainty={"low": round(MAINT_TWD2026 / 2, 0), "high": round(MAINT_TWD2026 * 2, 0), "type": "pedestal_gun_split_and_currency"},
        limitations=["FX 30.9 為 UNVERIFIED；且『每 pedestal 攤幾槍』為假設（本值按 2 槍）", "P26 的 maintenance 為 networking/maintenance 合計，未區分硬體維修"],
        is_scenario=True, admitted_use=["social_cost", "sensitivity_only"], source_file_sha256=SHA(P26),
        applies_to_taipei=False,
        derivation={"usd_per_pedestal_month": 75, "usd_per_pedestal_year": MAINT_USD_PER_PED_YEAR,
                    "usd_per_connector_year_assumed_2gun": MAINT_USD_PER_CONN_YEAR,
                    "twd_2019": round(MAINT_USD_PER_CONN_YEAR * FX2019, 2), "twd_2026": round(MAINT_TWD2026, 2)}))

    A(P("evse_annual_cost_TWD_per_connector_2026_transferable", "EVSE 單槍年化成本（設施分攤，2026 幣值）",
        "後端 operator_capital_depreciation 與 C(k) 設施分攤成本之候選輸入：年化 capex（直線法，壽命情景 10 年）+ 年維護。",
        value=round(ANNUAL_TOTAL, 2), unit="TWD/槍·年（2026 年幣值）", status="transferable", region="台灣（來源為 LA）",
        period="2019 來源 → 2026 幣值", price_year=2026, scenario_scope="2 槍 pedestal、壽命 10 年、FX 30.9 的條件化情景",
        source_class="derived", source_ids=["S-17-P26-PAPER", "S-16-CBC-FX", "S-18-THB-CHARGING-PLAN", "S-02-DGBAS-CPI-MONTHLY", "S-03-DGBAS-CPI-NEWS"],
        locator="capex(2026)/10 + maintenance(2026)",
        estimation_method="可追溯換算＋壽命情景；不含折現率（直線法，非年金法）",
        uncertainty={"low": round(CAPEX_TWD2026 / 12 + MAINT_TWD2026 / 2, 0), "high": round(CAPEX_TWD2026 / 8 + MAINT_TWD2026 * 2, 0), "type": "life_and_maintenance_scenario"},
        limitations=["is_scenario=true：FX 未核、壽命無官方值、維護按 2 槍攤提", "直線法未折現；若需年金法須再給社會折現率（官方值：手冊建議 4.4%? 未抽核）",
                     "不得宣稱這是台北已決標成本；來源為 LA 論文值", "官方錨點：交通部慢充補助額度 8 萬元/槍（2022 幣值）年化約 8,000 TWD/槍·年，與本值同量級但不同口徑"],
        is_scenario=True, admitted_use=["social_cost", "sensitivity_only"], source_file_sha256=SHA(P26),
        applies_to_taipei=False,
        derivation={"capex_annualized": round(ANNUAL_CAPEX, 2), "maintenance_annual": round(MAINT_TWD2026, 2),
                    "total": round(ANNUAL_TOTAL, 2), "life_years": LIFE,
                    "official_subsidy_benchmark_annualized": round(80000 / LIFE, 0)},
        blocks_or_enables="補上此項後 operator_capital_depreciation 與 C(k) 的設施分攤可分項計算（仍為 transferable/scenario，需在報告標明）"))

    # 6 项缺项定性（Lead 要求：是否存在该类量、为何未取得、可用哪类敏感性区间、阻塞哪项）
    QUAL = {
     "parking_search_time_minutes": {
       "exists_official_or_literature": "partial：交通部「自用小客車使用狀況調查」確有尋找停車位時間題項（統計查詢網 Seq=810 頁已落盤）；國外有 Shoup 類巡遊時間研究",
       "why_not_obtained": "官方值在互動查詢/圖表接口，本輪 GET 只取得表單頁；未取得台北數值",
       "sensitivity_range_class": "文獻外地均值類（如路邊巡遊平均 8 分鐘）與官方調查分縣市值類；僅可作上界/對照，不可當台北實測值",
       "blocks": "user_time（EV/ICE 失敗時間成本）、occupancy_impact 的 Δt 組成"},
     "detour_distance_km": {
       "exists_official_or_literature": "partial：無台北官方繞行距離統計；交通研究常用『路網/直線距離係數』類假設",
       "why_not_obtained": "官方交通調查未見該量；任務亦禁止以直線距離替代",
       "sensitivity_range_class": "路網係數類假設區間（如 1.3–1.5 倍直線距離，需來源）與 GPS 軌跡實測類；本輪無可用區間",
       "blocks": "ev_detour_energy、ev_external、ice_vehicle_operating、ice_external（四個繞行相關成本項）"},
     "substitute_parking_walk_time_minutes": {
       "exists_official_or_literature": "partial：無台北官方統計；步行可達性研究屬學術/規劃類",
       "why_not_obtained": "無官方調查值；需先界定替代場選擇行為",
       "sensitivity_range_class": "步行時間=距離/步速 類推算（需先有距離與步速來源）；純假設類區間僅供敏感性",
       "blocks": "user_time（ICE 搜尋+繞行+步行三段的步行段）"},
     "residual_trip_loss_per_kWh": {
       "exists_official_or_literature": "no：無官方或共識文獻值；COST-MODEL-V2 明示不得用售電價代替",
       "why_not_obtained": "需調查『缺電導致的行程/時間損失』，本輪無此調查",
       "sensitivity_range_class": "意願調查（WTP）類或行程重排成本類；本輪無可用來源，只能作情景假設區間並標 scenario",
       "blocks": "ev_residual_trip_loss（缺電損失）；連帶使 EV 充電失敗的完整成本不可算"},
     "activity_loss_per_failure": {
       "exists_official_or_literature": "no：無官方值；活動/行程取消的機會損失需旅次目的價值研究",
       "why_not_obtained": "需搭配旅次目的與活動價值資料，本輪未取得",
       "sensitivity_range_class": "旅次目的價值類（工資率×活動時長等推算）或問卷 WTP 類；只可作敏感性",
       "blocks": "ice_activity_loss、ev_activity_loss（放棄活動的一次性損失）"},
     "relocation_cost_TWD_per_event": {
       "exists_official_or_literature": "no：無官方值；需停車場營運人力/時間成本",
       "why_not_obtained": "無公開營運合約或人力成本資料；COST-MODEL-V2 禁止假設零成本",
       "sensitivity_range_class": "營運人力成本類（工資率×處理時間）或代客移車服務價類；本輪無來源，僅能情景",
       "blocks": "occupancy_impact 中需要挪車的干預分支（挪車相關成本差）；挪車不可行時該分支應回報『無法計算』"},
    }
    for _p in PARAMS:
        if _p["param_id"] in QUAL:
            _p["identifiability_note"] = QUAL[_p["param_id"]]

    # 去重（后面覆盖同名 param_id：Lead 复核新增版本优先）
    _dedup = {}
    for _p in PARAMS:
        _dedup[_p["param_id"]] = _p
    PARAMS = list(_dedup.values())



    return PARAMS
