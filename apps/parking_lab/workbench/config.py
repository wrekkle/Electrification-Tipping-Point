"""Validated, unit-explicit configuration. No environment values seed the learner.

成本参数按 docs/methods/COST-MODEL-V2.md 收进嵌套 cost 块：无来源的数值一律 None
（不是 0、不是演示默认值），sources 记录来源槽位，metadata 记录币种/价格年份以便
混用时报错。v1 的扁平演示成本参数已删除，传入即报错。

单位口径（与 costs.py 计算一致，不得两套口径混用）：
- maintenance_per_bay_day 的"位"指带枪设备位（chargers，设备数），按数量逐日相乘，
  不是"全场维护总额/天"；改口径必须先改字段名与界面单位词。
- depreciation_life_years 必须 > 0（=0 会在 capex 分摊时除零，Config.parse 直接拒绝）。

共享策略分两组，都有校验、旧配置仍可解析（旧字段缺省走新默认规则 π0）：
- 正式规则 RULE_POLICIES：dedicated_by_type/full_open_ice_first/predictive_shared_ice_first，
  准入只看 is_ev 与当前资源、历史统计与预测（见 rules.py）。
- legacy LEGACY_POLICIES：strict/open/fixed/adaptive，仅历史复现与回归对比；
  strict 按隐藏意愿（needs_charge）分区，标签已改为 legacy，不得冒充 π0。
- π2 的阈值与窗口由 ice_share_free_bay_margin（车位）与 ice_share_forecast_window_min（分钟）给定。
"""
from dataclasses import asdict, dataclass, field, fields
import math

from .costs import COST_MODEL_VERSION, COST_PARAMETER_NAMES, PROVENANCE_KINDS
from .rules import PREDICTION_OBJECTS, RULE_NAMES

# 正式规则（阶段四，CONTRACT §7）：只接受可观测状态（is_ev/当前占用与资源/历史统计与预测），
# 绝不接受 needs_charge、能量、真实离场时间或未来到达。默认规则是 π0（电车专用）。
RULE_POLICIES = {
    "dedicated_by_type": "按车型专用（π0：EV 含本次不充电可用带枪位/充电位，油车只用普通位）",
    "full_open_ice_first": "普通位优先、普通位不足开放充电位（π1）",
    "predictive_shared_ice_first": "预测共享（π2：按可见 EV 到达/充电预测放行油车）",
    "protected_quota": "固定保护数量（C 基线：始终为 EV 保留 m 个带枪位，普通位不足时 ICE 可用其余带枪位）",
}
assert tuple(RULE_POLICIES) == RULE_NAMES, "规则注册表与 rules.RULE_NAMES 不一致"

# 历史策略（legacy，仅供历史复现/回归对比；strict 按隐藏意愿分区，不得改名冒充 π0）。
LEGACY_POLICIES = {
    "strict": "严格分区（legacy，按隐藏意愿分区，仅历史复现）",
    "open": "普通位优先开放（legacy，历史实现，未按车型准入）",
    "fixed": "固定保留（legacy）",
    "adaptive": "在线自适应保留（legacy）",
}
# POLICIES：历史四策略集合（legacy），保留给旧对比口径与注册表校验；
# experiments.compare 默认改用 RULE_POLICIES（policy_set="formal"），legacy 需显式选择并标注演示。
POLICIES = dict(LEGACY_POLICIES)
# ALL_POLICIES：配置校验与界面标签的完整集合（正式规则在前）。
ALL_POLICIES = {**RULE_POLICIES, **LEGACY_POLICIES}
DEFAULT_POLICY = "dedicated_by_type"
SCENARIOS = {"steady": "稳定到达", "peaks": "早晚高峰", "burst": "突发拥挤", "drift": "需求中途变化"}
COST_ACCOUNTING_PERIODS = {"per_day": "每个仿真日", "per_hour": "每个仿真小时"}
REJECTED_DISPOSITIONS = {"detour_exit": "绕行离开", "alternate_bay": "停到替代位", "give_up": "放弃出行"}
LEGACY_COST_KEYS = ("rejection_ice_cost", "rejection_ev_cost", "shortfall_cost_kwh",
                    "electricity_cost_kwh", "charger_cost_day")

COST_BOUNDS = {
    "vot_per_hour": (0, 1e6), "search_min": (0, 1440), "detour_min": (0, 1440), "walking_min": (0, 1440),
    "detour_km_per_failure": (0, 1000), "ev_kwh_per_km": (0, 10), "ev_energy_price_per_kwh": (0, 1000),
    "alternative_charging_delta_per_kwh": (0, 1000), "residual_trip_loss_per_kwh": (0, 10000),
    "emission_cost_per_km": (0, 1000), "fuel_l_per_km": (0, 10), "fuel_price_per_l": (0, 1000),
    "activity_loss_per_failure": (0, 1e6), "electricity_price_per_kwh": (0, 1000),
    "maintenance_per_kwh": (0, 1000), "maintenance_per_bay_day": (0, 1e5),
    "depreciation_annual": (0, 1e12), "depreciation_capex": (0, 1e12), "depreciation_life_years": (0, 100),
    "facility_fixed_cost_per_day": (0, 1e6),
    "relocation_cost_per_move": (0, 1e6), "relocation_km_per_move": (0, 1000),
    "parking_fee_per_hour": (0, 1e4), "charging_fee_per_kwh": (0, 1000),
    "fine_per_event": (0, 1e6), "subsidy_per_session": (0, 1e6),
}


def _optional_number(name, value, bounds):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"cost.{name} 必须是有限数值或 null")
    lo, hi = bounds
    if not lo <= value <= hi:
        raise ValueError(f"cost.{name} 必须是 {lo} 至 {hi} 的有限数值或 null")
    return float(value)


@dataclass(frozen=True)
class CostConfig:
    """成本参数块。默认全部 null：缺参时成本项为 null、total 为 null、complete=false。"""

    currency: str = "TWD"
    price_year: int | None = None
    accounting_period: str = "per_day"
    rejected_disposition: str = "detour_exit"
    provenance: str = "unknown_not_calibrated"
    sources: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    vot_per_hour: float | None = None
    search_min: float | None = None
    detour_min: float | None = None
    walking_min: float | None = None
    detour_km_per_failure: float | None = None
    ev_kwh_per_km: float | None = None
    ev_energy_price_per_kwh: float | None = None
    alternative_charging_delta_per_kwh: float | None = None
    residual_trip_loss_per_kwh: float | None = None
    emission_cost_per_km: float | None = None
    fuel_l_per_km: float | None = None
    fuel_price_per_l: float | None = None
    activity_loss_per_failure: float | None = None
    electricity_price_per_kwh: float | None = None
    maintenance_per_kwh: float | None = None
    maintenance_per_bay_day: float | None = None
    depreciation_annual: float | None = None
    depreciation_capex: float | None = None
    depreciation_life_years: float | None = None
    facility_fixed_cost_per_day: float | None = None
    relocation_cost_per_move: float | None = None
    relocation_km_per_move: float | None = None
    parking_fee_per_hour: float | None = None
    charging_fee_per_kwh: float | None = None
    fine_per_event: float | None = None
    subsidy_per_session: float | None = None

    def params(self):
        data = {name: getattr(self, name) for name in COST_PARAMETER_NAMES}
        # facility_fixed_cost_per_day 未填写 = 本次核算不含站级固定成本（不是"未知"）；
        # 直接调用 costs.facility_cost 时仍可用显式 None 表示未知，两者不在这里混淆。
        if data.get("facility_fixed_cost_per_day") is None:
            data.pop("facility_fixed_cost_per_day", None)
        return data

    def to_dict(self):
        return asdict(self)

    @classmethod
    def parse(cls, raw=None):
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("cost 必须是JSON对象")
        names = {f.name for f in fields(cls)}
        unknown = set(raw) - names
        if unknown:
            raise ValueError("未知成本字段：" + ", ".join(sorted(unknown)))
        c = cls(**raw)
        if not isinstance(c.currency, str) or len(c.currency) != 3 or not c.currency.isalpha() or not c.currency.isupper():
            raise ValueError("cost.currency 必须是三位大写字母代码，如 TWD")
        if c.price_year is not None and (type(c.price_year) is not int or not 1990 <= c.price_year <= 2100):
            raise ValueError("cost.price_year 必须是 1990 至 2100 的整数或 null（未核实即 null）")
        if c.accounting_period not in COST_ACCOUNTING_PERIODS:
            raise ValueError("未知核算周期 cost.accounting_period")
        if c.rejected_disposition not in REJECTED_DISPOSITIONS:
            raise ValueError("未知被拒车辆去向 cost.rejected_disposition")
        if c.provenance not in PROVENANCE_KINDS:
            raise ValueError("未知成本参数来源状态 cost.provenance")
        for name, bounds in COST_BOUNDS.items():
            _optional_number(name, getattr(c, name), bounds)
        if c.depreciation_annual is not None and c.depreciation_capex is not None:
            raise ValueError("设备投入与折旧分摊只能取其一：cost.depreciation_annual 与 cost.depreciation_capex 不能同时给出")
        if c.depreciation_life_years is not None and c.depreciation_life_years <= 0:
            raise ValueError("cost.depreciation_life_years 必须大于 0（折旧年限为 0 会导致除零；未知即 null）")
        if not isinstance(c.sources, dict):
            raise ValueError("cost.sources 必须是对象")
        allowed = set(COST_PARAMETER_NAMES) | {"currency", "price_year", "accounting_period", "rejected_disposition"}
        for key, value in c.sources.items():
            if key not in allowed:
                raise ValueError(f"cost.sources 含未知参数：{key}")
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"cost.sources[{key}] 必须是非空字符串（来源或 unknown/pending calibration）")
        if not isinstance(c.metadata, dict):
            raise ValueError("cost.metadata 必须是对象")
        for key, entry in c.metadata.items():
            if key not in COST_PARAMETER_NAMES:
                raise ValueError(f"cost.metadata 含未知参数：{key}")
            if not isinstance(entry, dict):
                raise ValueError(f"cost.metadata[{key}] 必须是对象")
            unknown_meta = set(entry) - {"currency", "year", "note"}
            if unknown_meta:
                raise ValueError(f"cost.metadata[{key}] 含未知字段：" + ", ".join(sorted(unknown_meta)))
            if entry.get("currency") is not None and entry["currency"] != c.currency:
                raise ValueError(f"混用币种：cost.metadata[{key}].currency={entry['currency']} 与 cost.currency={c.currency} 不一致")
            if entry.get("year") is not None:
                if type(entry["year"]) is not int:
                    raise ValueError(f"cost.metadata[{key}].year 必须是整数年份")
                if c.price_year is None:
                    raise ValueError(f"cost.metadata[{key}] 声明了价格年份，但 cost.price_year 为 null")
                if entry["year"] != c.price_year:
                    raise ValueError(f"混用价格年份：cost.metadata[{key}].year={entry['year']} 与 cost.price_year={c.price_year} 不一致")
        return c


@dataclass(frozen=True)
class Config:
    n_spaces: int = 60
    charging_bays: int = 18
    chargers: int = 12
    charger_kw: float = 7.0
    feeder_kw: float = 60.0
    duration_hours: float = 12.0
    start_hour: float = 7.0
    seed: int = 42
    arrival_rate_hour: float = 35.0
    ev_share: float = 0.4
    charge_probability: float = 0.65
    ice_dwell_min: float = 90.0
    ev_dwell_min: float = 100.0
    dwell_cv: float = 0.45
    energy_mean_kwh: float = 14.0
    scenario: str = "peaks"
    policy: str = DEFAULT_POLICY
    peak_multiplier: float = 2.2
    burst_multiplier: float = 4.0
    drift_at_fraction: float = 0.5
    drift_rate_multiplier: float = 1.8
    drift_ev_share: float = 0.8
    interval_level: float = 0.9
    reserve_fixed: int = 4
    forecast_window_min: float = 30.0
    reserve_safety: float = 1.0
    learning_half_life_min: float = 120.0
    prior_rate_hour: float = 20.0
    prior_strength_min: float = 30.0
    prior_ev_share: float = 0.5
    prior_charge_probability: float = 0.5
    prior_type_strength: float = 4.0
    # π2 预测共享的可配置阈值与窗口（默认值见 rules.DEFAULT_*，只能用于正式规则 π2）。
    ice_share_forecast_window_min: float = 30.0
    ice_share_free_bay_margin: float = 1.0
    # 正式规则 π2 的预测对象与窗口协调开关（第三轮进入 config；研究子类不再另立一套）。
    prediction_object: str = "charge_arrivals"
    coordinate_window: bool = True
    # 规则 C（protected_quota）：始终留给 EV 的带枪位数，0≤m≤charging_bays，只有实验调参才改。
    protected_bays: int = 0
    cost: CostConfig = field(default_factory=CostConfig)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def parse(cls, raw=None):
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("配置必须是JSON对象")
        raw = dict(raw)
        legacy = sorted(set(raw) & set(LEGACY_COST_KEYS))
        if legacy:
            raise ValueError("v1 演示成本参数已移除（成本模型 " + COST_MODEL_VERSION + "）："
                             + ", ".join(legacy) + "；请改用 cost 块，无来源参数留 null")
        cost_raw = raw.pop("cost", None)
        unknown = set(raw) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError("未知配置字段：" + ", ".join(sorted(unknown)))
        c = cls(**raw, cost=CostConfig.parse(cost_raw))
        ints = {"n_spaces": (0, 2000), "charging_bays": (0, 2000), "chargers": (0, 2000),
                "seed": (0, 2**31 - 1), "reserve_fixed": (0, 2000)}
        bounds = {
            "charger_kw": (0, 1000), "feeder_kw": (0, 100000), "duration_hours": (0.05, 72),
            "start_hour": (0, 23.9999), "arrival_rate_hour": (0, 2000),
            "ev_share": (0, 1), "charge_probability": (0, 1),
            "ice_dwell_min": (0.1, 1440), "ev_dwell_min": (0.1, 1440), "dwell_cv": (0, 2),
            "energy_mean_kwh": (0, 300), "peak_multiplier": (1, 10), "burst_multiplier": (1, 20),
            "drift_at_fraction": (0, 1), "drift_rate_multiplier": (0, 10), "drift_ev_share": (0, 1),
            "interval_level": (0.5, 0.99), "forecast_window_min": (1, 240), "reserve_safety": (0, 4),
            "learning_half_life_min": (5, 1000000), "prior_rate_hour": (0.01, 2000),
            "prior_strength_min": (1, 1440), "prior_ev_share": (0.001, 0.999),
            "prior_charge_probability": (0.001, 0.999), "prior_type_strength": (0.1, 100),
            "ice_share_forecast_window_min": (1, 240), "ice_share_free_bay_margin": (0, 2000)}
        for key, (lo, hi) in ints.items():
            value = getattr(c, key)
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError(f"{key} 必须是 {lo} 至 {hi} 的整数")
        for key, (lo, hi) in bounds.items():
            value = getattr(c, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f"{key} 必须是 {lo} 至 {hi} 的有限数值")
        if not c.chargers <= c.charging_bays <= c.n_spaces:
            raise ValueError("必须满足：充电枪数 ≤ 充电车位 ≤ 总车位")
        if c.reserve_fixed > c.charging_bays:
            raise ValueError("固定保留数不能大于充电车位数")
        if type(c.prediction_object) is not str or c.prediction_object not in PREDICTION_OBJECTS:
            raise ValueError("未知预测对象 prediction_object：" + str(c.prediction_object))
        if type(c.coordinate_window) is not bool:
            raise ValueError("coordinate_window 必须是布尔值")
        if type(c.protected_bays) is not int or not 0 <= c.protected_bays <= c.charging_bays:
            raise ValueError("protected_bays 必须是 0 至 charging_bays 的整数")
        if c.prior_rate_hour * c.prior_strength_min / 60 < .01:
            raise ValueError("到达先验过于稀薄：先验到达率×先验暴露分钟/60需至少为0.01")
        if type(c.policy) is not str or c.policy not in ALL_POLICIES:
            raise ValueError("未知共享策略（正式规则见 RULE_POLICIES，legacy 见 LEGACY_POLICIES）")
        if type(c.scenario) is not str or c.scenario not in SCENARIOS:
            raise ValueError("未知到达情景")
        upper = c.arrival_rate_hour * max(1, c.peak_multiplier if c.scenario == "peaks" else 1,
                                        c.burst_multiplier if c.scenario == "burst" else 1,
                                        c.drift_rate_multiplier if c.scenario == "drift" else 1)
        if upper * c.duration_hours > 30000:
            raise ValueError("预计运行量过大：最大到达强度 × 时长需 ≤ 30000，请降低强度或时长")
        return c


# 演示用合成成本参数：显式标注 illustrative_not_calibrated，不是现实台北参数。
ILLUSTRATIVE_COST = {
    "provenance": "illustrative_not_calibrated",
    "currency": "TWD", "price_year": None, "accounting_period": "per_day",
    "vot_per_hour": 600.0, "search_min": 6.0, "detour_min": 4.0, "walking_min": 3.0,
    "detour_km_per_failure": 2.0, "ev_kwh_per_km": 0.18, "ev_energy_price_per_kwh": 5.0,
    "alternative_charging_delta_per_kwh": 4.0, "residual_trip_loss_per_kwh": 8.0,
    "emission_cost_per_km": 1.5, "fuel_l_per_km": 0.08, "fuel_price_per_l": 30.0,
    "activity_loss_per_failure": 50.0, "electricity_price_per_kwh": 3.0,
    "maintenance_per_kwh": 0.5, "maintenance_per_bay_day": 20.0,
    "depreciation_annual": 365000.0, "parking_fee_per_hour": 40.0, "charging_fee_per_kwh": 8.0,
    "sources": {"vot_per_hour": "illustrative synthetic value; not calibrated to Taipei",
                "residual_trip_loss_per_kwh": "illustrative synthetic value; not calibrated to Taipei"},
}


def presets():
    base = Config().to_dict()
    variants = [
        ("steady", "稳定到达", {"scenario": "steady", "arrival_rate_hour": 30}),
        ("peaks", "早晚高峰", {"scenario": "peaks"}),
        ("burst", "突发拥挤", {"scenario": "burst", "n_spaces": 40, "charging_bays": 12, "chargers": 8}),
        ("drift", "需求中途变化", {"scenario": "drift", "ev_share": .2, "arrival_rate_hour": 25}),
        ("small", "小型停车场", {"scenario": "peaks", "n_spaces": 12, "charging_bays": 4, "chargers": 3,
                                  "reserve_fixed": 1, "arrival_rate_hour": 10, "feeder_kw": 14}),
        ("no_charge", "纯停车对照", {"scenario": "steady", "charging_bays": 0, "chargers": 0,
                                        "reserve_fixed": 0, "charge_probability": 0}),
        ("illustrative", "合成示例（非现实成本，仅演示算术）", {"cost": {**base["cost"], **ILLUSTRATIVE_COST}}),
    ]
    return [{"id": key, "name": label, "config": {**base, **updates}} for key, label, updates in variants]
