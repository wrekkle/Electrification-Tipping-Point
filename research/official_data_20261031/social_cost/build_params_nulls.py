"""仍然缺来源、只能判 unidentified 的参数（cost-data, 2026-10-31）。由 build_params.py 调用。"""
def add_null_params(P, A, SHA, PARAMS):
    # ---------- 6. 仍然 null 的参数 ----------
    def nullp(pid, name, definition, unit, why, candidates, *, region="台灣/台北", adm=None, extra=None):
        d = P(pid, name, definition, value=None, unit=unit, status="unidentified", region=region,
              source_class="official", estimation_method=None, limitations=why,
              admitted_use=adm or ["social_cost"], candidate_sources=candidates)
        if extra:
            d.update(extra)
        return d

    A(nullp("fuel_consumption_L_per_km", "汽油小客車行駛油耗（L/km）", "繞行公里對應的額外油耗，用於 ice_vehicle_operating。",
            "L/km", ["未取得台灣官方行駛油耗測試值；不得用怠速 0.82 L/h 代替行駛油耗", "經濟部能源署車輛耗能測試為機型別，未取"],
            [{"title": "經濟部能源署 車輛耗能／能耗測試資料", "url": "https://www.moeaea.gov.tw/", "what_happened": "本輪未展開檢索"}]))

    A(nullp("ev_energy_consumption_kWh_per_km", "電動小客車電耗（kWh/km）", "繞行公里對應的額外電耗，用於 ev_detour_energy。",
            "kWh/km", ["未取得機型別官方能耗測試值", "缺此項使 ev_detour_energy 無法計算"],
            [{"title": "經濟部能源署 車輛耗能／能耗測試資料", "url": "https://www.moeaea.gov.tw/", "what_happened": "本輪未展開檢索"}]))

    A(nullp("parking_search_time_minutes", "停車搜尋時間（台北）", "油車無法停車時額外搜尋車位時間；Δt 的一段。",
            "min/次", ["台北路外停車場無官方搜尋時間統計",
                       "交通部「自用小客車使用狀況調查」有相關題項（統計查詢網 Seq=810 頁已落盘），但數值在查詢表單/圖表接口，本輪未取到",
                       "Shoup 8.1 分鐘為外地路邊停車，不得當台北值"],
            [{"title": "交通部統計查詢網「自用小客車在居家附近之尋找停車位時間及停車費」(Seq=810)", "url": "https://statis.motc.gov.tw/motc/Statistics/Display?Seq=810",
              "what_happened": "頁面可讀且已落盘，但表格/圖表資料需互動查詢；未取得數值"},
             {"title": "Shoup, D. (2007) Cruising for Parking, ACCESS 30（外地、路邊停車）", "url": "http://www.fbfl.us/DocumentCenter/View/16322/Cruising-for-Parking",
              "what_happened": "前輪已讀：平均 8.1 分鐘、巡遊車流 30%，屬外地路邊停車，不可當台北參數"}]))

    A(nullp("detour_distance_km", "繞行距離（每次失敗）", "無法停車/無法充電時額外行駛距離。",
            "km/次", ["無台北實測；任務禁止以最近停車場直線距離替代", "若日後用路網係數（如 1.3–1.5 倍），須登記係數來源與城市"],
            [{"title": "台北市交通局／停管處交通調查（未指定）", "url": "https://www.dot.gov.taipei/", "what_happened": "本輪未檢索到官方繞行距離統計"}]))

    A(nullp("substitute_parking_walk_time_minutes", "替代停車場步行時間", "改停替代場後增加的步行時間；Δt 的一段。",
            "min/次", ["無官方統計", "不得用直線距離/步行速度自行推估為官方值"],
            [{"title": "台北市停車場步行可達性研究（未指定）", "url": None, "what_happened": "本輪未檢索到官方統計"}]))

    A(nullp("substitute_charging_price_delta_TWD_per_kWh", "替代補能單價差", "替代充電站單價 − 目標站單價；乘缺電量得替代補能成本。",
            "TWD/kWh", ["兩端單價均未取得（充電費率頁未取得）", "即使取得費率，替代站選擇與缺電量也是行為假設"],
            [{"title": "台北市公共充電樁費率公告（未取得）", "url": "https://www-ws.gov.taipei/", "what_happened": "本輪抓到的 PDF 實為交通部資料標準，非費率；未取得費率頁"}]))

    A(nullp("parking_fee_rate_TWD_per_hour", "停車費率（台北市公有停車場）", "停車費；轉移支付，只用於分账，不進 social_total。",
            "TWD/小時", ["data.taipei 費率資源回應 0 bytes；pma.taipei.gov.tw 前輪連線失敗",
                         "屬轉移支付，缺失不阻塞社會成本，只影響 tariffs/transfers 區塊"],
            [{"title": "data.taipei「臺北市公有停車場收費費率」資料集", "url": "https://data.taipei/api/dataset/59027123-0fd0-4599-bcc7-53e3f480e52a/resource/9fea1c0b-4ee1-45eb-9f92-f0a0eb1da2d7/download",
              "what_happened": "HTTP 200 但回應 0 bytes（content-type: application/pdf），未取得檔案"},
             {"title": "臺北市停車管理工程處", "url": "https://pma.taipei.gov.tw/", "what_happened": "前輪 web_fetch 失敗"}],
            adm=["sensitivity_only"]))

    A(nullp("charging_fee_rate_TWD_per_kWh", "充電服務費率（台北市公共充電樁）", "充電費；轉移支付，只用於分账，不進 social_total。",
            "TWD/kWh", ["本輪未取得台北市公共充電樁費率官方頁（抓到的是資料標準文件）", "屬轉移支付，缺失不阻塞社會成本"],
            [{"title": "台北市公共充電樁費率公告（檔名為「充電站(樁)資料標準」的 PDF 已排除）", "url": "https://www-ws.gov.taipei/001/Upload/455/relfile/22477/8991302/105c068d-191d-4593-ad23-3e8e83ffe86c.pdf",
              "what_happened": "內容為交通部電動車充電站(樁)資料標準（XML 欄位），不是費率；已標 rejected"}],
            adm=["sensitivity_only"]))

    A(nullp("evse_capex_TWD_per_connector", "EVSE 單槍建置成本", "充電設備採購＋安裝＋配電擴容的一次性成本；與折舊二選一。",
            "TWD/槍", ["政府電子採購網決標價與官方補助要點本輪未取得可核對單價",
                       "不得用美金/LA 論文值按匯率搬用（P26）",
                       "缺此項使 operator_capital_depreciation 與 C(k) 的設施分攤成本不可算"],
            [{"title": "政府電子採購網 決標公告（充電樁採購/安裝）", "url": "https://web.pcc.gov.tw/", "what_happened": "本輪未取得（查詢需互動式檢索，時間預算內未完成）"},
             {"title": "經濟部能源署／交通部 公共充電樁補助要點", "url": "https://www.moeaea.gov.tw/", "what_happened": "本輪未取得可核對之每槍補助/成本數字"},
             {"title": "Tucker & Alizadeh (2020) P26 §IV-E（USD、LA）", "url": "https://arxiv.org/abs/1905.06468", "what_happened": "前輪已讀：pedestal 3,308 USD、每槍 3,343 USD、網管維護 75 USD/月；外地幣別，不得直接當台北值"}],
            extra={"carried_over_usd_reference": {"pedestal_evse_install_usd": 3308, "per_extra_cable_usd": 3343,
                                                 "networking_maintenance_usd_per_month": 75,
                                                 "source": "前輪 parameters.json / P26 p.10"}}))

    A(nullp("evse_maintenance_TWD_per_connector_year", "EVSE 維護成本（單槍·年）", "後端 maintenance_per_bay_day（位=帶枪設備位）之來源。",
            "TWD/槍·年", ["無台灣官方值", "P26 僅給網管維護 75 USD/月（外地）"],
            [{"title": "台電/縣市充電樁維護合約公告（未取得）", "url": None, "what_happened": "本輪未取得"}], adm=["social_cost"]))

    A(nullp("depreciation_annual_per_connector", "EVSE 年折舊分攤（單槍）", "年金法：A=P·i/(1-(1+i)^-n)；後端 depreciation_annual 或 capex/life 二選一。",
            "TWD/槍·年", ["缺 capex、折現率、設備壽命三項輸入", "不得套演示預設值"],
            [{"title": "本專案 parameter_candidates：evse_capex + 官方折現率 + 設備壽命", "url": None, "what_happened": "三項輸入均缺"}]))

    A(nullp("relocation_cost_TWD_per_event", "挪車代價（每次）", "移車人力/時間/風險成本；COST-MODEL-V2 §5 要求缺參即 null，禁止假設 0。",
            "TWD/次", ["無官方值", "缺此項時挪车相关成本项与完整成本差均为 null"],
            [{"title": "停車場營運人力成本（未取得）", "url": None, "what_happened": "本輪未取得"}]))

    A(nullp("residual_trip_loss_per_kWh", "缺電損失（每 kWh）", "離場仍缺電造成的行程損失；不得用售電價代替。",
            "TWD/kWh", ["無官方值/無可靠估計", "COST-MODEL-V2 §7 明示不得用售電價代替"],
            [{"title": "EV 用戶缺電損失調查（未取得）", "url": None, "what_happened": "本輪未取得"}]))

    A(nullp("activity_loss_per_failure", "活動機會損失（每次放棄）", "停車失敗導致活動/行程取消的一次性損失；EV/ICE 共用。",
            "TWD/次", ["無官方值", "只在『放棄活動』時觸發，不得對每次失敗都乘"],
            [{"title": "旅次目的/活動價值研究（未取得）", "url": None, "what_happened": "本輪未取得"}]))

    A(nullp("air_pollutant_damage_TWD_per_km", "空氣污染物單位損害（每車公里）", "emission_cost_per_km 中的 PM2.5/NOx 等分項；CO2 分項由碳費×排放量另行計算。",
            "TWD/km", ["未取得環境部空氣污染物係數/單位損害值", "缺此項時 emission_cost_per_km 只能含 CO2 分項（且 CO2 尚缺 kg/L）"],
            [{"title": "環境部 空氣污染物排放係數/空氣污染排放清冊（TEDS）", "url": "https://www.moenv.gov.tw/", "what_happened": "本輪未取得"},
             {"title": "運研所 108年手冊 空氣污染損害參數（表5-?，p.73-79）", "url": "https://www.iot.gov.tw/", "what_happened": "手冊有『空氣污染損害參數』章節，本輪未抽出數值；候選來源"}],
            extra={"candidate_note": "手冊 p.73 起有『損害參數=每人GDP×污染單位平均占比×平均匯率』章節，需另行抽出"}))

    A(nullp("gasoline_lower_heating_value_MJ_per_L", "車用汽油低位熱值（MJ/L）", "把 CO2 kg/TJ 換成 kg/L 所需的熱值。",
            "MJ/L", ["環境部 113年公告未附熱值", "不得用記憶值當官方值"],
            [{"title": "經濟部能源署 能源產品單位熱值表", "url": "https://www.moeaea.gov.tw/", "what_happened": "本輪未取得官方檔案"}]))

    A(P("overstay_penalty_reference_usd_per_hour", "充完滯留罰金參考（外地研究情景）",
        "Biswas et al. (2016) 的 penalty 結構；僅支撐機制，不得當台北罰金參數。",
        value={"optimal_penalty_utilization_usd_per_h": 2.37, "optimal_penalty_revenue_usd_per_h": 3.07,
               "charging_rate_usd_per_h": 2, "penalty_cap_examples_usd": [4, 8, 10, 20]},
        unit="USD/h", status="transferable", region="印度班加羅爾研究情境", period="2016",
        source_class="peer_reviewed", source_ids=["S-16-CARRIED-BISWAS"], locator="IJCAI-16 p.7、p.11（前輪已核全文）",
        estimation_method="論文最優罰金率（仿真）",
        limitations=["外地仿真值，不得按匯率當台北值", "罰金屬轉移支付，不進 social_total"],
        admitted_use=["sensitivity_only"], source_file_sha256=None,
        carried_over={"from": "research/cost_model_20261030/parameters.json#overstay_penalty_reference_USD_per_hour"}))



    return PARAMS
