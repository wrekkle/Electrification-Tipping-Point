# -*- coding: utf-8 -*-
"""T64 three-scheme contract: S1 dedicated, S2 timely opening, S3 mobile charging.

This module is the single Python source of truth for the *declared* parameter
objects of the three service schemes.  It contains no simulation logic; the
event engine lives in scheme_engine and the unified social cost in
social_cost.  Every constant here is either read from a registered project
artifact (facility cost anchor) or explicitly labelled as a scenario value.
"""
import json
import math
import numbers
import os

SCHEMA = "parking_lab_t64/1"
MATH_VERSION = "S1S2S3-2026-11-03/v1"
ENGINE_VERSION = "scheme_engine/1"

CLASSES = ("I", "E0", "E1")
SCHEMES = ("S1", "S2", "S3")
ADMISSION_RULES = ("strict", "fallback")
OPEN_RULES = ("never", "opportunity")
MODES = ("R0", "R1", "R2")
MODE_EVALUABLE_SCHEMES = {"R0": (), "R1": ("S1", "S2", "S3"), "R2": ("S1", "S2", "S3")}
MOBILE_DEVICE_KIND = "battery_buffered_mobile_charger"
MIN_PER_DAY = 1440.0
TIE_TOL = 1e-9

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
A_DAILY = os.path.join(_REPO, "data", "costs", "nyc_v2", "a_daily.json")


class SchemeError(ValueError):
    """Declared contract violation (bad scheme, bad parameter, bad domain)."""


def _num(x, name, *, positive=False, nonneg=False, integer=False):
    if isinstance(x, bool) or not isinstance(x, numbers.Real):
        raise SchemeError("%s 必须为数值，收到 %s" % (name, type(x).__name__))
    if not math.isfinite(float(x)):
        raise SchemeError("%s 必须有限" % name)
    if integer and float(x) != int(x):
        raise SchemeError("%s 必须为整数" % name)
    if positive and x <= 0:
        raise SchemeError("%s 必须 > 0" % name)
    if nonneg and x < 0:
        raise SchemeError("%s 必须 >= 0" % name)
    return int(x) if integer else float(x)


# --------------------------------------------------------------------- cost anchor
def cost_anchor():
    """Facility cost anchor read from the registered cost file (single source).

    The value is the L2 / 10-year / point / CRF row of
    data/costs/nyc_v2/a_daily.json.  If the file is missing the recorded value
    is used and flagged, never silently replaced by another number.
    """
    case = {"power": "L2", "lifetime_years": 10, "level": "point", "measure": "a_CRF_usd_per_day"}
    value = 3.112
    status = "recorded-fallback"
    if os.path.exists(A_DAILY):
        try:
            with open(A_DAILY, encoding="utf-8") as fh:
                doc = json.load(fh)
            for block in doc.get("cases", []):
                if block.get("power") == "L2" and block.get("lifetime_years") == 10:
                    for row in block.get("rows", []):
                        if row.get("level") == "point":
                            value = float(row["a_CRF_usd_per_day"])
                            status = "read"
        except (OSError, ValueError, KeyError):
            status = "recorded-fallback"
    return {"a_usd_per_bay_day": value, "case": case,
            "source": "data/costs/nyc_v2/a_daily.json",
            "status": status,
            "provenance": "L2/10y/point/CRF 摊销档；设备价/安装/联网/运维来源见 data/costs/nyc_v2/sources.md"}


# --------------------------------------------------------------------- frozen stream
def _canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(payload):
    import hashlib
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


class FrozenStream:
    """A frozen exogenous vehicle stream (no n, m or theta inside)."""

    def __init__(self, stream_id, site_id, mode, scenario_id, N, station_kw,
                 W, T, H, vehicles, initial=None, source="synthetic",
                 provenance=None, world_hash=None):
        self.stream_id = str(stream_id)
        self.site_id = str(site_id)
        self.mode = str(mode)
        self.scenario_id = str(scenario_id)
        self.N = N
        self.station_kw = station_kw
        self.W = W
        self.T = T
        self.H = H
        self.vehicles = list(vehicles)
        self.initial = list(initial or [])
        self.source = str(source)
        self.provenance = dict(provenance or {})
        self.world_hash = world_hash

    # -- construction / hashing -------------------------------------------
    def hash_payload(self):
        return {
            "schema": SCHEMA,
            "stream_id": self.stream_id,
            "site_id": self.site_id,
            "mode": self.mode,
            "scenario_id": self.scenario_id,
            "N": self.N,
            "station_kw": self.station_kw,
            "W": self.W,
            "T": self.T,
            "vehicles": [
                [v["session_id"], v["vehicle_id"], v["arrival"], v["dwell"],
                 v["cls"], round(float(v["energy"]), 6),
                 None if v.get("accept_power") is None else round(float(v["accept_power"]), 6),
                 v.get("origin") or ""]
                for v in self.vehicles
            ],
            "initial": [[i["kind"], i["release"]] for i in self.initial],
        }

    def compute_hash(self):
        return canonical_hash(self.hash_payload())

    # -- validation --------------------------------------------------------
    def validate(self):
        self.N = _num(self.N, "N", nonneg=True, integer=True)
        self.station_kw = _num(self.station_kw, "station_kw", positive=True)
        self.W = _num(self.W, "W", nonneg=True, integer=True)
        self.T = _num(self.T, "T", positive=True, integer=True)
        self.H = _num(self.H, "H", nonneg=True, integer=True)
        if self.W >= self.T:
            raise SchemeError("W 必须 < T")
        if (self.T - self.W) % MIN_PER_DAY != 0:
            raise SchemeError("核算窗口必须是整日")
        if self.H < self.T:
            raise SchemeError("H 必须 >= T")
        if self.mode not in MODES:
            raise SchemeError("mode 必须为 R0/R1/R2")
        seen = set()
        for v in self.vehicles:
            sid = v.get("session_id")
            if not isinstance(sid, str) or not sid:
                raise SchemeError("session_id 必须为非空字符串")
            if sid in seen:
                raise SchemeError("重复 session_id %s" % sid)
            seen.add(sid)
            v["arrival"] = _num(v.get("arrival"), "arrival(%s)" % sid, nonneg=True, integer=True)
            v["dwell"] = _num(v.get("dwell"), "dwell(%s)" % sid, positive=True, integer=True)
            if v.get("cls") not in CLASSES:
                raise SchemeError("车辆类别必须为 I/E0/E1")
            if v["cls"] == "E1":
                v["energy"] = _num(v.get("energy"), "energy(%s)" % sid, positive=True)
            else:
                v["energy"] = _num(v.get("energy", 0.0), "energy(%s)" % sid, nonneg=True)
                if v["energy"] != 0:
                    raise SchemeError("非 E1 车辆 %s 的请求电量必须为 0" % sid)
            if v.get("accept_power") is not None:
                v["accept_power"] = _num(v["accept_power"], "accept_power(%s)" % sid, positive=True)
        for i in self.initial:
            if not isinstance(i, dict) or i.get("kind") not in ("charge", "ordinary"):
                raise SchemeError("initial 条目需要 kind=charge|ordinary")
            i["release"] = _num(i.get("release"), "initial.release", nonneg=True, integer=True)
        if sum(1 for i in self.initial if i["release"] > 0) > self.N:
            raise SchemeError("初始占用超过 N")
        self.world_hash = self.world_hash or self.compute_hash()
        return True

    @classmethod
    def from_dict(cls, doc):
        stream = cls(
            stream_id=doc["stream_id"], site_id=doc["site_id"], mode=doc["mode"],
            scenario_id=doc["scenario_id"], N=doc["N"], station_kw=doc["station_kw"],
            W=doc["W"], T=doc["T"], H=doc["H"],
            vehicles=doc.get("vehicles") or [], initial=doc.get("initial") or [],
            source=doc.get("source") or "synthetic",
            provenance=doc.get("provenance") or {},
            world_hash=doc.get("world_hash"))
        stream.validate()
        return stream

    def cohort(self):
        return [v for v in self.vehicles if self.W <= v["arrival"] < self.T]

    def to_dict(self, with_vehicles=True):
        doc = {
            "schema": SCHEMA, "stream_id": self.stream_id, "site_id": self.site_id,
            "mode": self.mode, "scenario_id": self.scenario_id, "N": self.N,
            "station_kw": self.station_kw, "W": self.W, "T": self.T, "H": self.H,
            "source": self.source, "provenance": self.provenance,
            "world_hash": self.world_hash,
        }
        if with_vehicles:
            doc["vehicles"] = self.vehicles
            doc["initial"] = self.initial
        return doc

    def summary(self):
        cohort = self.cohort()
        counts = {c: sum(1 for v in cohort if v["cls"] == c) for c in CLASSES}
        return {
            "stream_id": self.stream_id, "site_id": self.site_id, "mode": self.mode,
            "scenario_id": self.scenario_id, "N": self.N, "station_kw": self.station_kw,
            "W": self.W, "T": self.T, "H": self.H,
            "n_vehicles": len(self.vehicles), "n_cohort": len(cohort),
            "cohort_by_class": counts, "source": self.source,
            "world_hash": self.world_hash, "provenance": self.provenance,
            "days": (self.T - self.W) / MIN_PER_DAY,
            "accept_power": {
                "declared": sum(1 for v in self.vehicles if v.get("accept_power") is not None),
                "missing": sum(1 for v in self.vehicles if v.get("accept_power") is None),
                "values": sorted({float(v["accept_power"]) for v in self.vehicles
                                  if v.get("accept_power") is not None}),
                "source": ("observed_field" if any(v.get("accept_power") is not None
                                                   for v in self.vehicles)
                           else "missing: declared assumption required"),
            },
        }


# --------------------------------------------------------------------- scheme spec
class OpenRule:
    """Timely-opening rule: only observable state, declared stays and past arrivals."""

    def __init__(self, open_rule="opportunity", forecast_window_min=60.0, kappa=1.0,
                 recall_lead_min=15.0, move_minutes=3.0, fallback_e1_per_hour=0.5,
                 fallback_unmet_kwh=12.0, forecast_bias=1.0, dwell_bias=1.0):
        self.open_rule = open_rule
        self.forecast_window_min = forecast_window_min
        self.kappa = kappa
        self.recall_lead_min = recall_lead_min
        self.move_minutes = move_minutes
        self.fallback_e1_per_hour = fallback_e1_per_hour
        self.fallback_unmet_kwh = fallback_unmet_kwh
        # declared sensitivity knobs: forecast under/over-estimation and
        # declared-stay error. Both only rescale estimates; never future info.
        self.forecast_bias = forecast_bias
        self.dwell_bias = dwell_bias

    def validate(self):
        if self.open_rule not in OPEN_RULES:
            raise SchemeError("open_rule 必须为 never|opportunity")
        self.forecast_window_min = _num(self.forecast_window_min, "forecast_window_min", positive=True)
        self.kappa = _num(self.kappa, "kappa", nonneg=True)
        self.recall_lead_min = _num(self.recall_lead_min, "recall_lead_min", nonneg=True)
        self.move_minutes = _num(self.move_minutes, "move_minutes", nonneg=True)
        self.fallback_e1_per_hour = _num(self.fallback_e1_per_hour, "fallback_e1_per_hour", nonneg=True)
        self.fallback_unmet_kwh = _num(self.fallback_unmet_kwh, "fallback_unmet_kwh", nonneg=True)
        self.forecast_bias = _num(self.forecast_bias, "forecast_bias", positive=True)
        self.dwell_bias = _num(self.dwell_bias, "dwell_bias", positive=True)
        return True

    def to_dict(self):
        return {"open_rule": self.open_rule,
                "forecast_window_min": self.forecast_window_min, "kappa": self.kappa,
                "recall_lead_min": self.recall_lead_min, "move_minutes": self.move_minutes,
                "fallback_e1_per_hour": self.fallback_e1_per_hour,
                "fallback_unmet_kwh": self.fallback_unmet_kwh,
                "forecast_bias": self.forecast_bias, "dwell_bias": self.dwell_bias}

    @classmethod
    def parse(cls, data):
        data = data or {}
        return cls(**{k: data[k] for k in (
            "open_rule", "forecast_window_min", "kappa", "recall_lead_min", "move_minutes",
            "fallback_e1_per_hour", "fallback_unmet_kwh",
            "forecast_bias", "dwell_bias") if k in data})


class MobileFleet:
    """Battery-buffered mobile charger fleet (scenario-locked device type)."""

    FIELDS = ("count", "capacity_kwh", "output_kw", "travel_min", "connect_min", "release_min",
              "recharge_kw", "discharge_efficiency", "min_service_min", "min_deliver_kwh",
              "soc_reserve_kwh", "recharge_threshold", "initial_soc_kwh",
              "assumed_accept_power_kw")

    def __init__(self, count=0, capacity_kwh=40.0, output_kw=7.2, travel_min=10.0,
                 connect_min=5.0, release_min=2.0, recharge_kw=7.2,
                 discharge_efficiency=0.95, min_service_min=10.0, min_deliver_kwh=2.0,
                 soc_reserve_kwh=4.0, recharge_threshold=0.4, initial_soc_kwh=None,
                 assumed_accept_power_kw=None):
        self.count = count
        self.capacity_kwh = capacity_kwh
        self.output_kw = output_kw
        self.travel_min = travel_min
        self.connect_min = connect_min
        self.release_min = release_min
        self.recharge_kw = recharge_kw
        self.discharge_efficiency = discharge_efficiency
        self.min_service_min = min_service_min
        self.min_deliver_kwh = min_deliver_kwh
        self.soc_reserve_kwh = soc_reserve_kwh
        self.recharge_threshold = recharge_threshold
        self.initial_soc_kwh = initial_soc_kwh
        # declared assumption used only when the frozen stream has no accept_power
        self.assumed_accept_power_kw = assumed_accept_power_kw

    def validate(self):
        self.count = _num(self.count, "m", nonneg=True, integer=True)
        self.capacity_kwh = _num(self.capacity_kwh, "capacity_kwh", positive=True)
        self.output_kw = _num(self.output_kw, "output_kw", positive=True)
        self.travel_min = _num(self.travel_min, "travel_min", nonneg=True)
        self.connect_min = _num(self.connect_min, "connect_min", nonneg=True)
        self.release_min = _num(self.release_min, "release_min", nonneg=True)
        self.recharge_kw = _num(self.recharge_kw, "recharge_kw", positive=True)
        self.discharge_efficiency = _num(self.discharge_efficiency, "discharge_efficiency",
                                         positive=True)
        if self.discharge_efficiency > 1:
            raise SchemeError("discharge_efficiency 必须 <= 1")
        self.min_service_min = _num(self.min_service_min, "min_service_min", nonneg=True)
        self.min_deliver_kwh = _num(self.min_deliver_kwh, "min_deliver_kwh", nonneg=True)
        self.soc_reserve_kwh = _num(self.soc_reserve_kwh, "soc_reserve_kwh", nonneg=True)
        if self.soc_reserve_kwh >= self.capacity_kwh:
            raise SchemeError("soc_reserve_kwh 必须 < capacity_kwh")
        self.recharge_threshold = _num(self.recharge_threshold, "recharge_threshold", nonneg=True)
        if self.recharge_threshold >= 1:
            raise SchemeError("recharge_threshold 必须 < 1")
        if self.initial_soc_kwh is None:
            self.initial_soc_kwh = self.capacity_kwh
        self.initial_soc_kwh = _num(self.initial_soc_kwh, "initial_soc_kwh", positive=True)
        if self.initial_soc_kwh > self.capacity_kwh:
            raise SchemeError("initial_soc_kwh 必须 <= capacity_kwh")
        if self.assumed_accept_power_kw is not None:
            self.assumed_accept_power_kw = _num(self.assumed_accept_power_kw,
                                                "assumed_accept_power_kw", positive=True)
        return True

    def to_dict(self):
        out = {k: getattr(self, k) for k in self.FIELDS}
        out["device_kind"] = MOBILE_DEVICE_KIND
        return out

    @classmethod
    def parse(cls, data):
        data = data or {}
        return cls(**{k: data[k] for k in cls.FIELDS if k in data})


class SchemeSpec:
    """S1/S2/S3 = fixed facilities + declared admission rule + declared mechanisms."""

    def __init__(self, scheme="S1", rule="fallback", open_rule=None, mobile=None):
        self.scheme = scheme
        self.rule = rule
        self.open = open_rule if isinstance(open_rule, OpenRule) else OpenRule.parse(open_rule)
        self.mobile = mobile if isinstance(mobile, MobileFleet) else MobileFleet.parse(mobile)

    def validate(self):
        if self.scheme not in SCHEMES:
            raise SchemeError("scheme 必须为 S1/S2/S3")
        if self.rule not in ADMISSION_RULES:
            raise SchemeError("rule 必须为 strict|fallback")
        self.open.validate()
        self.mobile.validate()
        if self.scheme == "S1":
            if self.open.open_rule != "never":
                raise SchemeError("S1 不允许开放规则（open_rule 必须为 never）")
            if self.mobile.count != 0:
                raise SchemeError("S1 不允许移动设备（m 必须为 0）")
        if self.scheme == "S2" and self.mobile.count != 0:
            raise SchemeError("S2 不允许移动设备（m 必须为 0）")
        return True

    def to_dict(self):
        return {"scheme": self.scheme, "rule": self.rule,
                "open_rule": self.open.to_dict(), "mobile": self.mobile.to_dict()}

    @classmethod
    def parse(cls, data):
        data = data or {}
        return cls(scheme=data.get("scheme", "S1"), rule=data.get("rule", "fallback"),
                   open_rule=data.get("open_rule"), mobile=data.get("mobile"))

    # -- constructors ------------------------------------------------------
    @classmethod
    def s1(cls, rule="fallback"):
        return cls("S1", rule, OpenRule(open_rule="never"), MobileFleet(count=0))

    @classmethod
    def s2(cls, rule="fallback", **open_kw):
        open_kw.setdefault("open_rule", "opportunity")
        return cls("S2", rule, OpenRule(**open_kw), MobileFleet(count=0))

    @classmethod
    def s3(cls, rule="fallback", m=1, open_kw=None, mobile_kw=None):
        open_kw = dict(open_kw or {})
        open_kw.setdefault("open_rule", "opportunity")
        mobile_kw = dict(mobile_kw or {})
        mobile_kw["count"] = m
        return cls("S3", rule, OpenRule(**open_kw), MobileFleet(**mobile_kw))


# --------------------------------------------------------------------- cost params
PARAM_SPECS = {
    "a": {"unit": "USD/桩·日", "status": "derived",
          "source": "data/costs/nyc_v2/a_daily.json（L2/10y/point/CRF）"},
    "a_mob": {"unit": "USD/台·日", "status": "scenario",
              "source": "T64 声明：60,000 USD/台、5 年寿命、1.6% 折现率、3,000 USD/年运维摊销"},
    "b_I": {"unit": "USD/次", "status": "scenario",
            "source": "theta_center: beta_I=1 × a"},
    "b_E0": {"unit": "USD/次", "status": "scenario",
             "source": "theta_center: beta_E0=1 × a"},
    "b_E1": {"unit": "USD/次", "status": "scenario",
             "source": "theta_center: beta_E1=1 × a（只代表被拒本身，不含充电后果）"},
    "c_E": {"unit": "USD/kWh", "status": "scenario",
            "source": "theta_center: gamma_E=0.10 × a"},
    "c_res": {"unit": "USD/kWh", "status": "scenario",
              "source": "theta_center: delta_res=0.05 × a（资源价格代理，不是用户电价）"},
    "c_mob_min": {"unit": "USD/设备·分钟", "status": "scenario",
                  "source": "T64 声明：0.05 USD/设备·分钟（运行人工+磨损）"},
    "c_mob_kwh": {"unit": "USD/kWh", "status": "scenario",
                  "source": "T64 声明：0.02 USD/kWh（移动设备交付磨损）"},
    "c_move": {"unit": "USD/次", "status": "scenario",
               "source": "T64 声明：5 USD/次（召回换位用户不便）"},
}


def crf(rate, years):
    if rate <= 0:
        return 1.0 / years
    f = (1.0 + rate) ** years
    return rate * f / (f - 1.0)


def mobile_anchor(capital_usd=60000.0, lifetime_years=5, rate=0.016, om_usd_per_year=3000.0):
    daily = capital_usd * crf(rate, lifetime_years) / 365.0 + om_usd_per_year / 365.0
    return {"a_mob_usd_per_device_day": round(daily, 3),
            "capital_usd": capital_usd, "lifetime_years": lifetime_years,
            "rate": rate, "om_usd_per_year": om_usd_per_year,
            "source": PARAM_SPECS["a_mob"]["source"], "status": "scenario"}


class CostParams:
    """Unified social-cost vector.  None means *missing*, never zero."""

    FIELDS = ("a", "a_mob", "b_I", "b_E0", "b_E1", "c_E", "c_res",
              "c_mob_min", "c_mob_kwh", "c_move")

    def __init__(self, a=None, a_mob=None, b_I=None, b_E0=None, b_E1=None, c_E=None,
                 c_res=None, c_mob_min=None, c_mob_kwh=None, c_move=None, label="theta_center"):
        self.a = a
        self.a_mob = a_mob
        self.b_I = b_I
        self.b_E0 = b_E0
        self.b_E1 = b_E1
        self.c_E = c_E
        self.c_res = c_res
        self.c_mob_min = c_mob_min
        self.c_mob_kwh = c_mob_kwh
        self.c_move = c_move
        self.label = label

    @classmethod
    def theta_center(cls, anchor_a=None):
        anchor_a = cost_anchor()["a_usd_per_bay_day"] if anchor_a is None else anchor_a
        return cls(a=anchor_a, a_mob=mobile_anchor()["a_mob_usd_per_device_day"],
                   b_I=anchor_a, b_E0=anchor_a, b_E1=anchor_a,
                   c_E=0.10 * anchor_a, c_res=0.05 * anchor_a,
                   c_mob_min=0.05, c_mob_kwh=0.02, c_move=5.0, label="theta_center")

    @classmethod
    def parse(cls, data, base=None):
        data = data or {}
        base = base or cls.theta_center()
        kwargs = {}
        for name in cls.FIELDS:
            kwargs[name] = data.get(name, getattr(base, name))
        return cls(label=data.get("label", base.label), **kwargs)

    def validate(self):
        for name in self.FIELDS:
            value = getattr(self, name)
            if value is None:
                continue
            setattr(self, name, _num(value, name, nonneg=True))
        return True

    def missing(self):
        return [name for name in self.FIELDS if getattr(self, name) is None]

    def to_dict(self):
        return {"params": {name: getattr(self, name) for name in self.FIELDS},
                "label": self.label, "missing": self.missing(),
                "provenance": {name: PARAM_SPECS[name] for name in self.FIELDS}}


# --------------------------------------------------------------------- feasible domain
def default_m_max(N, cap=6):
    return int(max(0, min(cap, N)))


class FeasibleDomain:
    """Declared configuration grid; the search enumerates it and says so."""

    def __init__(self, N, n_grid=None, m_grid=None, m_max=None):
        self.N = _num(N, "N", nonneg=True, integer=True)
        self.m_max = default_m_max(self.N) if m_max is None else _num(m_max, "m_max", nonneg=True, integer=True)
        self.n_grid = sorted(set(n_grid)) if n_grid is not None else list(range(0, self.N + 1))
        self.m_grid = sorted(set(m_grid)) if m_grid is not None else list(range(0, self.m_max + 1))

    def validate(self, scheme="S3"):
        for n in self.n_grid:
            _num(n, "n", nonneg=True, integer=True)
            if n > self.N:
                raise SchemeError("n=%d 超出声明可行域 0..%d" % (n, self.N))
        for m in self.m_grid:
            _num(m, "m", nonneg=True, integer=True)
            if m > self.m_max:
                raise SchemeError("m=%d 超出声明可行域 0..%d" % (m, self.m_max))
        if not self.n_grid:
            raise SchemeError("n_grid 不能为空")
        if scheme in ("S1", "S2"):
            if any(m != 0 for m in self.m_grid):
                raise SchemeError("%s 的 m 只能为 0" % scheme)
        if not self.m_grid:
            raise SchemeError("m_grid 不能为空")
        return True

    def configs(self, scheme="S3"):
        self.validate(scheme)
        if scheme in ("S1", "S2"):
            return [{"n": n, "m": 0} for n in self.n_grid]
        return [{"n": n, "m": m} for n in self.n_grid for m in self.m_grid]

    def to_dict(self):
        return {"N": self.N, "n_grid": self.n_grid, "m_grid": self.m_grid,
                "m_max": self.m_max, "declared": True,
                "note": "声明网格内枚举；网格外不搜索，结论仅限声明可行域"}


def validate_config(stream, scheme, config):
    """Single-configuration feasibility (independent of the search grid)."""
    scheme = str(scheme)
    if scheme not in SCHEMES:
        raise SchemeError("scheme 必须为 S1/S2/S3")
    n = _num((config or {}).get("n"), "n", nonneg=True, integer=True)
    m = _num((config or {}).get("m", 0), "m", nonneg=True, integer=True)
    if n > stream.N:
        raise SchemeError("n=%d 超出 0..N=%d" % (n, stream.N))
    if scheme in ("S1", "S2") and m != 0:
        raise SchemeError("%s 的 m 必须为 0" % scheme)
    if m > default_m_max(stream.N):
        raise SchemeError("m=%d 超出 0..%d" % (m, default_m_max(stream.N)))
    return {"n": n, "m": m}