# -*- coding: utf-8 -*-
"""Unified social cost for the three T64 schemes.

One ledger, one denominator, one accounting window for S1/S2/S3.  Missing
parameters propagate as null (never zero), and transfer payments (parking fees,
charging tariffs, subsidies, penalties) are reported separately and never added
to the social cost.
"""
try:  # package import
    from .schemes import PARAM_SPECS, SCHEMA, CostParams
except ImportError:  # direct module import
    from schemes import PARAM_SPECS, SCHEMA, CostParams

SCHEMA_COST = "parking_lab_t64_cost/1"

ITEMS = (
    ("facility_fixed", "固定充电设施", "USD", ("a",), "a * n * days"),
    ("facility_mobile", "移动设备投资", "USD", ("a_mob",), "a_mob * m * days"),
    ("rejection_I", "燃油车停车被拒损失", "USD", ("b_I",), "b_I * R_I"),
    ("rejection_E0", "E0 停车被拒损失", "USD", ("b_E0",), "b_E0 * R_E0"),
    ("rejection_E1", "E1 充电被拒损失", "USD", ("b_E1",), "b_E1 * R_EP（不含充电后果）"),
    ("unmet_energy", "未满足电量损失", "USD", ("c_E",), "c_E * S_kwh"),
    ("resource_energy", "能源资源成本", "USD", ("c_res",),
     "c_res * (D_fixed_kwh + mobile_grid_kwh)"),
    ("mobile_active", "移动设备运行成本", "USD", ("c_mob_min",), "c_mob_min * mobile_active_min"),
    ("mobile_energy", "移动设备交付磨损", "USD", ("c_mob_kwh",), "c_mob_kwh * D_mobile_kwh"),
    ("moves", "召回换位不便", "USD", ("c_move",), "c_move * moves"),
)


def _value(features, name, default=0.0):
    v = features.get(name, default)
    return 0.0 if v is None else float(v)


def cost(features, params, *, currency="USD", price_year=2026):
    """Return the unified cost breakdown for one run's physical features."""
    if not isinstance(params, CostParams):
        raise TypeError("params 必须为 CostParams")
    params.validate()
    n = _value(features, "n")
    m = _value(features, "m")
    days = _value(features, "days")
    R_I = _value(features, "R_I")
    R_E0 = _value(features, "R_E0")
    R_EP = _value(features, "R_EP")
    S = _value(features, "S_kwh")
    D_fixed = _value(features, "D_fixed_kwh")
    D_mobile = _value(features, "D_mobile_kwh")
    grid = _value(features, "mobile_grid_kwh")
    active = _value(features, "mobile_active_min")
    moves = _value(features, "moves")

    quantities = {
        "facility_fixed": (n * days, None),
        "facility_mobile": (m * days, None),
        "rejection_I": (R_I, None),
        "rejection_E0": (R_E0, None),
        "rejection_E1": (R_EP, None),
        "unmet_energy": (S, None),
        "resource_energy": (D_fixed + grid, None),
        "mobile_active": (active, None),
        "mobile_energy": (D_mobile, None),
        "moves": (moves, None),
    }
    items = {}
    total = 0.0
    complete = True
    missing = []
    for name, label, unit, needs, formula in ITEMS:
        value = None
        qty = quantities[name][0]
        param_values = [getattr(params, key) for key in needs]
        absent = [key for key in needs if getattr(params, key) is None]
        if absent:
            complete = False
            missing.extend(k for k in absent if k not in missing)
        else:
            factor = 1.0
            for pv in param_values:
                factor *= float(pv)
            value = factor * float(qty)
            total += value
        items[name] = {
            "label": label, "unit": unit, "value": None if value is None else round(value, 6),
            "quantity": round(float(qty), 6), "params": list(needs), "formula": formula,
            "missing_parameters": absent,
            "provenance": {key: PARAM_SPECS[key] for key in needs},
        }
    if not complete:
        total = None
    per_day = None if total is None else (total / days if days > 0 else None)
    transfers = {
        "excluded": True,
        "note": "停车费/充电费/罚金/补贴属转移支付，不计入社会成本；本轮无可用的站点价格合同，故单列而不赋数值。",
        "items": {"parking_fee": None, "charging_fee": None, "subsidy": None, "penalty": None},
    }
    return {
        "schema": SCHEMA_COST, "math_schema": SCHEMA,
        "items": items, "total": None if total is None else round(total, 6),
        "total_per_day": None if per_day is None else round(per_day, 6),
        "complete": bool(complete), "missing_parameters": missing,
        "transfers": transfers, "currency": currency, "price_year": price_year,
        "unit": "USD", "period": "accounting_window",
        "params_label": params.label, "params": params.to_dict(),
    }