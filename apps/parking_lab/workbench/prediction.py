"""Discounted Gamma-Poisson and Beta-Bernoulli online baseline.

With forgetting, parameters are power-prior pseudo counts; intervals are model
predictive intervals, not guaranteed frequentist coverage under drift.

隐藏信息边界（阶段四）：Learner 只接收可观测事件，绝不接收 needs_charge/SOC/电池容量/
能量/真实离场时间/未来到达。两条观测通道对应两次可见事件：
- observe(is_ev)：车辆到达时只按车型计数（不进决策，决策读上一时刻已发布的 forecast）；
- observe_charging_start()：车辆第一次实际交付电量（开始充电）时才计数，
  用来估计"EV 到达后真正开始充电"的比例，仍遵循先发布后更新。
因此 π2 的"短期需充电到达"只由历史到达统计与已发生的充电开始推出，不能偷看隐藏意愿。
"""
import math


class ObservableOccupancy:
    """只吃"已发生离场"事件的占用估计（阶段四第二轮：connector_load / 窗口协调用）。

    可见事件：车辆到达时刻、车辆离场时刻、车型、是否曾占带枪位、是否曾真正开始充电
    （带枪位上首次交付电量）。不可见：本次是否想充电、能量、计划离场时间、未来到达。
    仍在场车辆是右删失样本，不能计入均值（不得用尚未发生的停留时间）。
    """

    def __init__(self):
        self.ev_departures = 0
        self.ice_departures = 0
        self.ice_minutes = 0.0
        self.ev_connector_minutes = 0.0
        self.charging_sessions = 0
        self.charging_session_minutes = 0.0

    def observe_departure(self, *, is_ev, duration_min, connector_minutes, charging_started):
        """一次已观察到的离场：时长从到达算到离场；connector_minutes 是占带枪位的分钟。"""
        duration = _finite("duration_min", duration_min, minimum=0.0)
        connector = _finite("connector_minutes", connector_minutes, minimum=0.0)
        if connector > duration + 1e-9:
            raise ValueError("connector_minutes 不能超过总停留时长")
        if type(is_ev) is not bool or type(charging_started) is not bool:
            raise ValueError("is_ev 与 charging_started 必须是布尔值")
        if is_ev:
            self.ev_departures += 1
            self.ev_connector_minutes += connector
            if charging_started:
                self.charging_sessions += 1
                self.charging_session_minutes += connector
        else:
            self.ice_departures += 1
            self.ice_minutes += duration

    def estimate(self):
        """返回只由已离场样本得到的估计；样本为 0 时返回 None（不填默认值）。"""
        return {
            "observed_departures": self.ice_departures + self.ev_departures,
            "observed_ev_departures": self.ev_departures,
            "observed_ice_departures": self.ice_departures,
            "mean_ice_occupancy_min": (self.ice_minutes / self.ice_departures
                                       if self.ice_departures else None),
            "mean_connector_minutes_per_ev": (self.ev_connector_minutes / self.ev_departures
                                              if self.ev_departures else None),
            "mean_charging_session_min": (self.charging_session_minutes / self.charging_sessions
                                          if self.charging_sessions else None),
            "basis": "只用已观察离场事件；在场/删失样本不计入（needs_charge 不可见）",
        }


def _finite(name, value, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} 必须是有限数值")
    if minimum is not None and value < minimum - 1e-12:
        raise ValueError(f"{name} 必须 ≥ {minimum}")
    return float(value)


class Learner:
    def __init__(self, c):
        self.level = c.interval_level
        self.half_life = c.learning_half_life_min
        self.window = c.forecast_window_min
        self.strength = c.prior_type_strength
        self.rate_a0 = c.prior_rate_hour / 60 * c.prior_strength_min
        self.rate_b0 = c.prior_strength_min
        self.ev0 = c.prior_ev_share
        self.need0 = c.prior_charge_probability
        self.events = self.exposure = self.ev_yes = self.ev_total = self.charge_starts = 0.0
        self.time = 0.0
        self.seen = 0

    def advance(self, now):
        dt = now - self.time
        if dt < -1e-9:
            raise ValueError("学习器时间不能倒退")
        if dt <= 0:
            return
        k = math.log(2) / self.half_life
        factor = math.exp(-k * dt)
        self.events *= factor
        # Exact exponentially weighted exposure, independent of HTTP step size.
        self.exposure = self.exposure * factor - math.expm1(-k * dt) / k
        for key in ("ev_yes", "ev_total", "charge_starts"):
            setattr(self, key, getattr(self, key) * factor)
        self.time = now

    def observe(self, is_ev):
        """到达观测：只记录车型。needs_charge 不可见，不在签名里。"""
        self.events += 1
        self.ev_total += 1
        self.ev_yes += int(is_ev)
        self.seen += 1

    def observe_charging_start(self):
        """充电开始观测：车辆第一次实际交付电量时调用（先发布后更新）。"""
        self.charge_starts += 1.0

    def forecast(self):
        a, b = self.rate_a0 + self.events, self.rate_b0 + self.exposure
        p_ev = (self.ev0 * self.strength + self.ev_yes) / (self.strength + self.ev_total)
        p_need = (self.need0 * self.strength + self.charge_starts) / (self.strength + self.ev_total)
        alpha = (1 - self.level) / 2
        quantile = lambda q: b * math.expm1(-math.log1p(-q) / a)
        mean_wait = b / (a - 1) if a > 1 else None
        expected = a / b * p_ev * p_need * self.window
        return {"issued_at_min": self.time, "p_ev": p_ev, "p_charge_given_ev": p_need,
                "arrival_rate_hour": a / b * 60, "interval_level": self.level,
                "wait_lower_min": quantile(alpha), "wait_upper_min": quantile(1 - alpha),
                "wait_median_min": quantile(.5), "wait_mean_min": mean_wait,
                "expected_charge_arrivals": expected, "window_min": self.window,
                "observed_arrivals": self.seen,
                "observed_charging_starts": self.charge_starts,
                "charging_start_basis": "已发生的充电开始（首次实际交付电量），非隐藏意愿",
                "cold_start": self.seen < 20,
                "posterior_shape": a, "posterior_rate_min": b,
                "model": "discounted Gamma-Poisson + Beta-Bernoulli"}
