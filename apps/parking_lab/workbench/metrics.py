"""Explicit denominators, censoring, window accounts and cost-model-v2 costs."""
from .costs import COST_MODEL_VERSION, cost_report


def calculate(sim):
    c, visits = sim.config, sim.visits
    n = len(visits)
    rejected = [v for v in visits if not v["admitted"]]
    parked = [v for v in visits if v["admitted"]]
    needs = [v for v in visits if v["needs_charge"]]
    requested = sum(v["energy_kwh"] for v in visits)
    delivered = sum(v["delivered_kwh"] for v in visits)
    refused_energy = sum(v["energy_kwh"] for v in rejected)
    departed_gap = sum(max(0, v["energy_kwh"] - v["delivered_kwh"]) for v in parked if v["departed"])
    pending = sum(max(0, v["energy_kwh"] - v["delivered_kwh"]) for v in sim.active.values())
    completed = sum(v["admitted"] and v["needs_charge"] and v["completed"] for v in visits)
    ev_rejected = sum(v["is_ev"] for v in rejected)
    ice_rejected = len(rejected) - ev_rejected
    cost = cost_report(sim)
    pred = sim.scores
    mean = lambda key: sum(r[key] for r in pred) / len(pred) if pred else None
    return {
        "arrivals": n, "admitted": len(parked), "rejected": len(rejected),
        "ev_arrivals": sum(v["is_ev"] for v in visits), "ice_arrivals": sum(not v["is_ev"] for v in visits),
        "rejected_ev": ev_rejected, "rejected_ice": ice_rejected,
        "rejection_rate": len(rejected) / n if n else None,
        "occupancy": len(sim.active), "capacity": c.n_spaces,
        "occupancy_rate": len(sim.active) / c.n_spaces if c.n_spaces else None,
        "mean_occupancy_rate": sim.occupied_minutes / (c.n_spaces * sim.time) if c.n_spaces and sim.time else None,
        "charging_now": len(sim.powers()), "charge_requests": len(needs),
        "charge_completed": completed,
        "charge_completion_rate_all": completed / len(needs) if needs else None,
        "departed_charge_requests": sum(v["needs_charge"] and v["departed"] for v in parked),
        "energy_requested_all_kwh": requested, "energy_delivered_kwh": delivered,
        "rejected_energy_kwh": refused_energy, "departed_shortfall_kwh": departed_gap,
        "pending_energy_kwh": pending, "window_undelivered_kwh": max(0, requested - delivered),
        "energy_balance_error_kwh": requested - delivered - refused_energy - departed_gap - pending,
        "peak_power_kw": sim.peak_power, "current_power_kw": sum(sim.powers().values()),
        "peak_occupancy": sim.peak_occupancy, "peak_charging": sim.peak_charging,
        # 成本模型 v2：分项 + attribution + transfers + 缺参清单 + complete。
        # total_cost 在缺参时为 None（未知），绝不填 0。
        "cost_model_version": COST_MODEL_VERSION,
        "cost": cost,
        "cost_items": cost["items"],
        "total_cost": cost["total"],
        "cost_complete": cost["complete"],
        "cost_missing_parameters": cost["missing_parameters"],
        "cost_attribution": cost["attribution"],
        "cost_transfers": cost["transfers"],
        "cost_transfers_missing_parameters": cost["transfers_missing_parameters"],
        "occupancy_minutes": cost["attribution"]["occupancy_minutes_by_reason"],
        "cost_unit": cost["unit"],
        "cost_currency": cost["currency"], "cost_price_year": cost["price_year"],
        "cost_accounting_period": cost["accounting_period"],
        "prediction_samples": len(pred), "brier": mean("brier"), "type_accuracy": mean("correct"),
        "interval_coverage": mean("covered"), "interval_width_min": mean("width_min"),
        "interval_score": mean("interval_score"), "interval_level": c.interval_level,
        "right_censored_next_arrival": sim.finished,
        "elapsed_min": sim.time, "synthetic": True,
    }


def sampled(rows, limit=500):
    if len(rows) <= limit:
        return rows[:]
    return [rows[round(i * (len(rows) - 1) / (limit - 1))] for i in range(limit)]
