"""Exact discrete events with fixed connectors and continuously shared feeder power.

Charging bays [0,B); equipped bays [0,C). A connector remains at its bay;
charging completion releases power but not parking space. There is no queue and no
switching into a newly available equipped bay. The only relocation is the paired
counterfactual intervention release_after_complete: a completed EV may move to a
free ordinary bay (keeping its scheduled departure time, cost priced by
relocation_cost_per_move); without an ordinary bay it stays put and is not released.

准入由规则引擎决定（阶段四）：
- 正式规则 π0/π1/π2（config.RULE_POLICIES）走 rules.py，只读可观测状态
  （is_ev、当前占用与资源、历史统计与预测）；needs_charge/能量/真实离场时间/未来到达
  不进入任何准入决策。
- legacy 四策略（config.LEGACY_POLICIES）保留原实现供历史复现：strict 按隐藏意愿
  （needs_charge）分区，标签已改为 legacy，不得冒充 π0；正式对照必须用新规则。
- Learner 在正式与 legacy 运行中都只观测 get_visible 事件：到达车型与已发生的充电开始。
占位与滞留按三类单独计量（rules.type_occupancy_ledger）：无充电需求电车占带枪位、
充电完成仍占带枪位、油车占带枪位；逐车/逐事件可导出，只作结果计量，不反馈进决策。
"""
from __future__ import annotations

import math
from .config import ALL_POLICIES, LEGACY_POLICIES, RULE_POLICIES, Config
from .costs import (COST_MODEL_VERSION, DISPOSITIONS, UNKNOWN_DETOUR, CostLedger,
                    classify_charging_failure, cost_report, occupancy_minutes, traffic_hash)
from .demand import Arrival, generate, stream_hash
from .prediction import Learner, ObservableOccupancy
from .metrics import calculate, sampled
from .rules import (TYPE_OCCUPANCY_METRICS, ObservableState, candidates as rule_candidates,
                    reserved_charging_bays, type_occupancy_ledger)

EPS = 1e-8


class Simulation:
    def __init__(self, config, arrivals=None, intervention=None):
        self.config = config if isinstance(config, Config) else Config.parse(config)
        # 占桩配对反事实的干预侧（B=及时释放）；None 表示基准 A=允许该段占位。
        self.intervention = dict(intervention or {})
        c = self.config
        self.horizon = c.duration_hours * 60
        self.arrivals = generate(c) if arrivals is None else tuple(arrivals)
        previous = -1.0
        ids = set()
        for a in self.arrivals:
            values = (a.time_min, a.dwell_min, a.energy_kwh)
            if (not all(math.isfinite(x) for x in values) or not 0 <= a.time_min < self.horizon
                    or a.time_min < previous or a.dwell_min <= 0 or a.energy_kwh < 0
                    or a.vehicle_id in ids or (a.needs_charge and not a.is_ev)
                    or (not a.needs_charge and a.energy_kwh != 0)):
                raise ValueError("车辆轨迹不合法：需有序、唯一ID及有限的非负时间/能量")
            ids.add(a.vehicle_id)
            previous = a.time_min
        if len(self.arrivals) > 40000:
            raise ValueError("实际车辆数超过40000硬上限")
        self.demand_hash = stream_hash(self.arrivals)
        self.traffic_hash = traffic_hash(self.arrivals)
        self.ledger = CostLedger(c.cost.params(), currency=c.cost.currency,
                                 price_year=c.cost.price_year,
                                 accounting_period=c.cost.accounting_period)
        # 正式规则走 rules.py；legacy 策略保留原实现（strict 按隐藏意愿分区，仅历史复现）。
        self.rule = c.policy if c.policy in RULE_POLICIES else None
        self.legacy_policy = c.policy if c.policy in LEGACY_POLICIES else None
        self.last_decision = None
        # 可见离场统计（只吃已发生离场；在场/删失不计）与同批次已放行油车数，供正式规则使用。
        self.observable = ObservableOccupancy()
        self._batch_time = None
        self._batch_pending = 0
        self.learner = Learner(c)
        self.issued = self.learner.forecast()
        self.time = 0.0
        self.index = 0
        self.active = {}
        self.visits, self.scores, self.events, self.history, self.power_segments = [], [], [], [], []
        self.occupied_minutes = 0.0
        self.rejected_count = 0
        self.rejected_ev_count = 0
        self.rejected_ice_count = 0
        self.peak_power = self.peak_charging = self.peak_occupancy = 0
        # 展示层累计量（不进入任何准入决策、指标分母或成本口径）：
        # delivered_total 与 metrics.energy_delivered_kwh 同源累计，供前端画累计电量曲线；
        # bay_frames 是车位状态热力图的历史帧，按字符编码并限量，避免每秒传整车位明细。
        self.delivered_total = 0.0
        self.completed_total = 0
        self.bay_frames = []
        self._frame_limit = max(24, min(240, int(120000 / max(1, c.n_spaces))))
        self._frame_interval = max(self.horizon / self._frame_limit, 0.25) if self.horizon > 0 else 0.25
        self._last_frame_time = None
        # 回放快照（展示层）：只在事件批次处理完、对应 history 行写入后记录一份真实状态；
        # 回放控件只在这些快照之间定位，不插值、不推进仿真、不伪造未来状态。
        # 与 bay_frames 一样按车位数量限量，超限时二分降采样（保留首尾覆盖范围）。
        self.replay_snapshots = []
        self._snapshot_limit = max(40, min(240, int(200000 / max(1, c.n_spaces))))
        # 车辆级明细（车位详情）只在可承受的车位数下随快照保存；否则回放显示“该历史时刻未记录”。
        self._roster_enabled = c.n_spaces <= 300
        self._last_snapshot_event_seq = -1
        self._history()
        self._capture_replay_snapshot()

    @property
    def finished(self):
        return self.time >= self.horizon - 1e-9

    def powers(self):
        c = self.config
        candidates = [bay for bay, v in self.active.items()
                      if bay < c.chargers and v["needs_charge"] and v["energy_kwh"] - v["delivered_kwh"] > EPS]
        if not candidates or c.charger_kw <= 0 or c.feeder_kw <= 0:
            return {}
        power = min(c.charger_kw, c.feeder_kw / len(candidates))
        return {bay: power for bay in candidates}

    def reserve(self, forecast=None):
        """保留/预留的充电位数（历史与展示字段，不进入正式规则决策）。

        正式规则的口径：π0 全部充电位保留给电车；π1 不保留（普通位优先后完全开放）；
        π2 按可见预测保留（窗口内预计充电到达 + 配置余量，向上取整，不超过充电位数）。
        legacy 四策略保持原口径，供历史复现。
        """
        c = self.config
        if self.rule is not None:
            f = forecast or self.learner.forecast()
            return reserved_charging_bays(
                self.rule, charging_bays=c.charging_bays,
                arrival_rate_per_hour=f["arrival_rate_hour"], p_ev=f["p_ev"],
                p_charge_given_ev=f["p_charge_given_ev"],
                window_min=c.ice_share_forecast_window_min,
                safety_margin=c.ice_share_free_bay_margin,
                protected_bays=c.protected_bays)
        if c.policy == "strict":
            return c.charging_bays
        if c.policy == "open":
            return 0
        if c.policy == "fixed":
            return min(c.reserve_fixed, c.chargers)
        mean = (forecast or self.learner.forecast())["expected_charge_arrivals"]
        return min(c.chargers, max(0, math.ceil(mean + c.reserve_safety * math.sqrt(mean))))

    def observable_state(self, a, forecast, free):
        """构造控制器可见状态：只有车型、占用/资源、历史统计与预测；不含隐藏意愿。"""
        c = self.config
        ice_charging = sum(1 for v in self.active.values()
                           if (not v["is_ev"]) and v.get("current_bay") is not None
                           and v["current_bay"] < c.charging_bays)
        seen = self.observable.estimate()
        return ObservableState(
            time_min=self.time, is_ev=a.is_ev, free_bays=tuple(free), n_spaces=c.n_spaces,
            charging_bays=c.charging_bays, chargers=c.chargers,
            arrival_rate_per_hour=forecast["arrival_rate_hour"], p_ev=forecast["p_ev"],
            p_charge_given_ev=forecast["p_charge_given_ev"],
            mean_ice_occupancy_min=seen["mean_ice_occupancy_min"],
            mean_connector_minutes_per_ev=seen["mean_connector_minutes_per_ev"],
            observed_departures=seen["observed_departures"],
            ice_charging_bays=ice_charging)

    def choose_bay(self, a, forecast):
        c = self.config
        free = [bay for bay in range(c.n_spaces) if bay not in self.active]
        if self.rule is not None:
            state = self.observable_state(a, forecast, free)
            ordered, reason, detail = rule_candidates(
                state, self.rule, window_min=c.ice_share_forecast_window_min,
                safety_margin=c.ice_share_free_bay_margin,
                prediction_object=c.prediction_object,
                coordinate_window=c.coordinate_window,
                pending_shared_bays=self._batch_pending,
                protected_bays=c.protected_bays)
            detail = dict(detail)
            if self.intervention.get("exclude_no_charging_demand") and not a.needs_charge:
                # 配对反事实 B 专用：无充电需求的车辆不占带枪位。该开关故意使用隐藏真值，
                # 只用于结果归因反事实，不是准入规则；正式规则不读它。
                ordered = [bay for bay in ordered if bay >= c.chargers]
                detail["counterfactual"] = "exclude_no_charging_demand"
            bay = ordered[0] if ordered else None
            self.last_decision = {"rule": self.rule, "reason": reason, "bay": bay,
                                  "detail": detail, "legacy": False}
            return bay
        bay = self._legacy_choose_bay(a, free, forecast)
        self.last_decision = {"rule": None, "reason": "legacy_" + c.policy, "bay": bay,
                              "detail": {"legacy": True}, "legacy": True}
        return bay

    def _legacy_choose_bay(self, a, free, forecast):
        """legacy 准入实现（原样保留，仅历史复现/回归）。

        strict 用 needs_charge（隐藏意愿）分区：需要充电的电车不能用普通位，
        不充电的电车只能用普通位——这正是阶段四要替换掉的泄漏，不得冒充 π0。
        """
        c = self.config
        equipped = [b for b in free if b < c.chargers]
        designated = [b for b in free if c.chargers <= b < c.charging_bays]
        ordinary = [b for b in free if b >= c.charging_bays]
        if a.needs_charge:
            candidates = equipped + designated + ([] if c.policy == "strict" else ordinary)
        elif c.policy == "strict":
            candidates = ordinary
        else:
            candidates = ordinary + designated
            if len(equipped) > self.reserve(forecast):
                candidates += equipped
        if self.intervention.get("exclude_no_charging_demand") and not a.needs_charge:
            # 反事实 B：无充电需求的车辆不占带枪车位（释放 connector），其余决策规则不变。
            candidates = [bay for bay in candidates if bay >= c.chargers]
        return candidates[0] if candidates else None

    def _log(self, kind, vehicle=None, **values):
        self.events.append({"time_min": self.time, "kind": kind, "vehicle_id": vehicle, **values})

    def _arrive(self, a):
        # 只用已发布的统计（暴露量、到达车型、已发生的充电开始）；当前车辆的隐藏意愿不可见。
        # 同一到达时刻视为一个决策批次：统计本批已放行到充电区的油车数（可见占用）。
        if self._batch_time is None or abs(a.time_min - self._batch_time) > 1e-9:
            self._batch_time = a.time_min
            self._batch_pending = 0
        forecast = self.learner.forecast()
        issued = self.issued
        wait = a.time_min - issued["issued_at_min"]
        lo, hi = issued["wait_lower_min"], issued["wait_upper_min"]
        p = issued["p_ev"]
        penalty = max(lo - wait, 0) + max(wait - hi, 0)
        self.scores.append({"vehicle_id": a.vehicle_id, "issued_at_min": issued["issued_at_min"],
                            "observed_at_min": a.time_min, "p_ev": p, "is_ev": a.is_ev,
                            "wait_min": wait, "lower_min": lo, "upper_min": hi,
                            "brier": (p - int(a.is_ev))**2, "correct": int((p >= .5) == a.is_ev),
                            "covered": int(lo <= wait <= hi), "width_min": hi - lo,
                            "interval_score": hi - lo + 2 / (1 - self.config.interval_level) * penalty})
        bay = self.choose_bay(a, forecast)
        visit = {**a.to_dict(), "admitted": bay is not None, "bay": bay, "current_bay": bay,
                 "departure_min": a.time_min + a.dwell_min,
                 "delivered_kwh": 0.0, "departed": False,
                 "completed": bool(bay is not None and a.needs_charge and a.energy_kwh <= EPS),
                 "completion_min": a.time_min if bay is not None and a.needs_charge and a.energy_kwh <= EPS else None,
                 "disposition": None, "cost_kind": None, "charging_failure_reason": None,
                 "released_min": None, "relocated_min": None,
                 "relocated_from_bay": None, "relocated_to_bay": None,
                 "relocation_status": None, "charge_start_min": None,
                 "admission": dict(self.last_decision or {})}
        self.visits.append(visit)
        if bay is not None and (not a.is_ev) and bay < self.config.charging_bays:
            self._batch_pending += 1
        if bay is not None:
            self.active[bay] = visit
        else:
            self.rejected_count += 1
            if a.is_ev:
                self.rejected_ev_count += 1
            else:
                self.rejected_ice_count += 1
            self._record_rejection_cost(a, visit)
        self._log("arrival" if bay is not None else "rejected", a.vehicle_id,
                  is_ev=a.is_ev, needs_charge=a.needs_charge, bay=bay)
        # 只在打分与本次分配决策之后观测车型；充电意愿只在真正开始充电时可见。
        self.learner.observe(a.is_ev)
        self.issued = self.learner.forecast()
        self.peak_occupancy = max(self.peak_occupancy, len(self.active))
        powers = self.powers()
        self.peak_charging = max(self.peak_charging, len(powers))
        self.peak_power = max(self.peak_power, sum(powers.values()))

    def _failure_intervals(self, start_min):
        """失败耗时区间：搜索→绕行→步行；任一参数未知则整段时间不可知（null，不是 0）。"""
        cost = self.config.cost
        durations = (cost.search_min, cost.detour_min, cost.walking_min)
        if any(value is None for value in durations):
            return None
        intervals, cursor = [], start_min
        for duration in durations:
            intervals.append((cursor, cursor + duration))
            cursor += duration
        return intervals

    def _failure_time_missing(self):
        cost = self.config.cost
        names = []
        if cost.search_min is None:
            names.append("search_min")
        if cost.detour_min is None:
            names.append("detour_min")
        if cost.walking_min is None:
            names.append("walking_min")
        return tuple(names)

    def _record_rejection_cost(self, arrival, visit):
        """被拒车辆必须落到明确去向之一，并按去向生成失败分项（不得凭空消失）。

        动力类型（is_ev）与本次是否需要充电（needs_charge）是两件事，分别决定：
        - 绕行能耗用哪套公式：电车 ev_detour_energy（电耗），油车 ice_vehicle_operating（燃油）；
        - 是否产生充电失败损失：只有"需要充电却没充上"才计替代补能/剩余行程损失。
        无充电需求的电车仍可有停车失败的时间/能耗/外部损失，但 ev_residual_trip_loss 必须为 0。
        """
        disposition = self.config.cost.rejected_disposition
        visit["disposition"] = disposition
        kind = "EV" if arrival.is_ev else "ICE"
        charging_failure = bool(arrival.is_ev and arrival.needs_charge)
        visit["cost_kind"] = kind
        visit["charging_failure_reason"] = (
            "rejected_no_capacity" if charging_failure else None)
        self.ledger.add_failure(
            arrival.vehicle_id, kind,
            intervals=self._failure_intervals(arrival.time_min),
            time_missing=self._failure_time_missing(),
            shortfall_kwh=arrival.energy_kwh if charging_failure else 0.0,
            activity_loss_applies=(disposition == "give_up"),
            reason="rejected_parking", disposition=disposition)

    def _record_departure_cost(self, visit):
        """已接纳电车离场时仍有充电缺口 ⇒ c_i^EV 分项；窗口末未离场不是失败。"""
        if not visit["admitted"] or not visit["needs_charge"] or not visit["departed"]:
            return
        gap = max(0.0, visit["energy_kwh"] - visit["delivered_kwh"])
        if gap <= EPS:
            return
        reason = classify_charging_failure(visit, self.config)
        visit["charging_failure_reason"] = reason
        # 离场仍缺电：后续额外时间（找替代桩/绕行/步行）与绕行距离在本仿真没有观测，
        # 不得因为"场内无排队"就隐含为零；保持未知并传播到 items/total/missing_parameters。
        self.ledger.add_failure(visit["vehicle_id"], "EV", intervals=None,
                                time_missing=("search_min", "detour_min", "walking_min"),
                                shortfall_kwh=gap, detour_km=UNKNOWN_DETOUR, reason=reason,
                                disposition="admitted_shortfall")

    def _release_completed(self, bay, visit):
        """挪车反事实：充满后把车辆挪到普通空位，车辆不得凭空消失。

        - 只有存在普通空位（bay >= charging_bays）才挪车；无普通位则不挪车、不释放，
          记 relocation_status="blocked_no_ordinary_bay"（该时点无法计算释放收益）。
        - 挪车后车辆继续占普通位，保留原定离场时间（departure_min 不变）。
        - 带枪位/枪口占用在挪车时刻结束（released_min），功率在充满时已自动释放。
        """
        c = self.config
        if visit["departure_min"] <= self.time + 1e-9:
            return  # 该时刻就要离场，挪车没有意义
        ordinary = [b for b in range(c.charging_bays, c.n_spaces) if b not in self.active]
        if not ordinary:
            if visit.get("relocation_status") is None:
                visit["relocation_status"] = "blocked_no_ordinary_bay"
                self._log("release_blocked", visit["vehicle_id"], bay=bay,
                          reason="no_ordinary_bay")
            return
        target = ordinary[0]
        del self.active[bay]
        self.active[target] = visit
        visit["current_bay"] = target
        visit["relocated_min"] = self.time
        visit["relocated_from_bay"] = bay
        visit["relocated_to_bay"] = target
        visit["released_min"] = self.time
        visit["relocation_status"] = "relocated_kept_until_departure"
        self.ledger.add_relocation(visit["vehicle_id"], from_bay=bay, to_bay=target,
                                   time_min=self.time)
        self._log("relocated", visit["vehicle_id"], bay=bay, to_bay=target,
                  reason="overstay_after_complete")

    def _history(self):
        c = self.config
        f = self.learner.forecast()
        row = {"time_min": self.time, "occupancy": len(self.active),
               "charging": len(self.powers()), "arrivals": len(self.visits),
               "rejected": self.rejected_count,
               "power_kw": sum(self.powers().values()), "p_ev": f["p_ev"],
               "rate_hour": f["arrival_rate_hour"], "reserve": self.reserve(f),
               "energy_kwh": round(self.delivered_total, 6), "charged": self.completed_total}
        if self.history and abs(self.history[-1]["time_min"] - self.time) < 1e-9:
            self.history[-1] = row
        else:
            self.history.append(row)
        self._capture_bay_frame()

    def advance(self, target_min):
        if isinstance(target_min, bool) or not isinstance(target_min, (int, float)) or not math.isfinite(target_min):
            raise ValueError("推进时间必须是有限数值")
        if target_min < self.time - 1e-9:
            raise ValueError("不能向过去推进，请重置实验")
        target = min(float(target_min), self.horizon)
        while self.time < target - 1e-10 or (self.index < len(self.arrivals) and self.arrivals[self.index].time_min <= self.time + 1e-10):
            powers = self.powers()
            next_arrival = self.arrivals[self.index].time_min if self.index < len(self.arrivals) else math.inf
            departure = min((v["departure_min"] for v in self.active.values()), default=math.inf)
            completion = min((self.time + (self.active[b]["energy_kwh"] - self.active[b]["delivered_kwh"]) / p * 60
                              for b, p in powers.items()), default=math.inf)
            nxt = min(next_arrival, departure, completion, target)
            dt = max(0.0, nxt - self.time)
            if dt:
                power = sum(powers.values())
                segment_start = self.time
                if power:
                    self.power_segments.append({"start_min": self.time, "end_min": nxt,
                                                "power_kw": power, "charging_count": len(powers)})
                started = []
                for b, p in powers.items():
                    v = self.active[b]
                    if v["charge_start_min"] is None and v["delivered_kwh"] <= EPS and p > 0:
                        v["charge_start_min"] = segment_start
                        started.append((b, v))
                    _before = v["delivered_kwh"]
                    v["delivered_kwh"] = min(v["energy_kwh"], _before + p * dt / 60)
                    self.delivered_total += v["delivered_kwh"] - _before
                self.occupied_minutes += len(self.active) * dt
                self.learner.advance(nxt)
                self.time = nxt
                # 充电开始是可见事件（首次实际交付电量）：学习器在其发生后才更新，
                # 且绝不读取 needs_charge；对外发布的预测仍是先发布后更新。
                for b, v in started:
                    self.learner.observe_charging_start()
                    self._log("charging_start", v["vehicle_id"], bay=b)
            # End charging before departure, departure before arrival at ties.
            for b, v in sorted(list(self.active.items())):
                if v["needs_charge"] and not v["completed"] and v["energy_kwh"] - v["delivered_kwh"] <= EPS:
                    v["completed"] = True
                    v["completion_min"] = self.time
                    self.completed_total += 1
                    self._log("charged", v["vehicle_id"], bay=b)
            if self.intervention.get("release_after_complete"):
                # 反事实 B：充满后挪到普通位以释放枪口（overstay_after_complete），其余规则不变。
                for b, v in sorted(list(self.active.items())):
                    if v["needs_charge"] and v["completed"] and v.get("released_min") is None:
                        self._release_completed(b, v)
            for b, v in sorted(list(self.active.items())):
                if v["departure_min"] <= self.time + 1e-9:
                    v["departed"] = True
                    self._log("departure", v["vehicle_id"], bay=b, delivered_kwh=v["delivered_kwh"])
                    self._record_departure_cost(v)
                    # 可见离场事件：控制器只在实际观察到离场后更新停留统计（右删失样本不计）。
                    connector_end = (v["released_min"] if v.get("released_min") is not None
                                     else v["departure_min"])
                    connector_min = (max(0.0, connector_end - v["time_min"])
                                     if v.get("bay") is not None
                                     and v["bay"] < self.config.chargers else 0.0)
                    self.observable.observe_departure(
                        is_ev=v["is_ev"],
                        duration_min=max(0.0, v["departure_min"] - v["time_min"]),
                        connector_minutes=connector_min,
                        charging_started=v.get("charge_start_min") is not None)
                    del self.active[b]
            while self.index < len(self.arrivals) and self.arrivals[self.index].time_min <= self.time + 1e-10:
                self._arrive(self.arrivals[self.index])
                self.index += 1
            self._history()
            self._capture_replay_snapshot()
            if self.time >= target - 1e-10:
                break
        if self.time < target:
            self.learner.advance(target)
            self.time = target
            self._history()
            self._capture_replay_snapshot()
        self.assert_invariants()
        return self.snapshot()

    def run(self):
        return self.advance(self.horizon)

    def assert_invariants(self):
        c = self.config
        if len(self.active) > c.n_spaces or self.peak_occupancy > c.n_spaces:
            raise AssertionError("parking capacity exceeded")
        if self.peak_charging > c.chargers or self.peak_power > c.feeder_kw + EPS:
            raise AssertionError("charging resource capacity exceeded")
        for v in self.visits:
            if not -EPS <= v["delivered_kwh"] <= v["energy_kwh"] + EPS:
                raise AssertionError("energy demand exceeded")
            if v["delivered_kwh"] > EPS and (not v["admitted"] or not v["needs_charge"] or v["bay"] >= c.chargers):
                raise AssertionError("energy delivered without connector")
        for visit in self.visits:
            if not visit["admitted"] and visit["disposition"] not in DISPOSITIONS:
                raise AssertionError("被拒车辆必须有明确去向（绕行离开/替代位/放弃出行）")
            if visit.get("released_min") is not None and not (visit["completed"] and visit["needs_charge"]):
                raise AssertionError("只有充满的车辆才能被干预释放")
            if visit.get("released_min") is not None and visit.get("relocated_min") is None:
                raise AssertionError("释放充电资源必须伴随挪到普通位（车辆不得凭空消失）")
            if visit.get("relocated_min") is not None:
                if (visit.get("relocated_to_bay") is None
                        or visit["relocated_to_bay"] < c.charging_bays):
                    raise AssertionError("挪车目标必须是普通车位")
                if visit["relocated_min"] < visit["time_min"] - EPS:
                    raise AssertionError("挪车时间早于到达时间")
                if visit["departed"] and visit["departure_min"] < visit["relocated_min"] - EPS:
                    raise AssertionError("挪车不得改变原定离场时间")
                if visit.get("relocation_status") != "relocated_kept_until_departure":
                    raise AssertionError("挪车后车辆必须保留到原定离场")
        if self.rule == "dedicated_by_type":
            for visit in self.visits:
                if visit["admitted"] and not visit["is_ev"] and visit["bay"] < c.charging_bays:
                    raise AssertionError("π0 下油车不得进入充电车位")
        for visit in self.visits:
            if visit["charge_start_min"] is not None and visit["delivered_kwh"] <= EPS:
                raise AssertionError("充电开始必须有实际交付电量")
            if visit["charge_start_min"] is not None and not (visit["is_ev"] and visit["bay"] < c.chargers):
                raise AssertionError("只有占用带枪位的电车才可能开始充电")
        if len({line["user_id"] for line in self.ledger.lines}) != len(self.ledger.lines):
            raise AssertionError("同一用户同一时段出现多条失败成本行")
        m = calculate(self)
        if abs(m["energy_balance_error_kwh"]) > 1e-6:
            raise AssertionError("energy accounting does not balance")

    def type_occupancy(self, cut_min=None):
        """三类占位分钟账本（无充电需求电车/充满仍占位/油车占带枪位），逐车与逐事件。

        只累计到 cut_min（缺省取当前仿真时刻）；用隐藏真值做结果计量，不反馈进准入决策。
        """
        cut = self.time if cut_min is None else cut_min
        return type_occupancy_ledger(self.visits, self.config, cut)

    def _bay_state_string(self):
        """每车位一个数字：0 空位 / 1 油车 / 2 电车停车未充 / 3 充电中 / 4 充满仍占位。

        只服务展示（点阵与热力图），不进入准入决策、指标或成本口径。
        """
        c = self.config
        powers = self.powers()
        states = ["0"] * c.n_spaces
        for b, v in self.active.items():
            if not 0 <= b < c.n_spaces:
                continue
            if b in powers:
                states[b] = "3"
            elif v["needs_charge"] and v["completed"]:
                states[b] = "4"
            elif v["is_ev"]:
                states[b] = "2"
            else:
                states[b] = "1"
        return "".join(states)

    def _capture_bay_frame(self):
        """追加车位状态热力图帧；超过帧数上限时二分降采样，保持覆盖整个已运行区间。"""
        if self.time is None:
            return
        if self.bay_frames and self._last_frame_time is not None \
                and self.time - self._last_frame_time < self._frame_interval - 1e-9:
            return
        if len(self.bay_frames) >= self._frame_limit:
            self.bay_frames = self.bay_frames[::2]
            self._frame_interval *= 2
        self.bay_frames.append({"t": round(self.time, 6), "s": self._bay_state_string()})
        self._last_frame_time = self.time

    def _capture_replay_snapshot(self):
        """记录一份可回放的真实状态快照（展示层，不参与模型决策）。

        调用时机：事件批次已处理完、对应 history 行已写入。快照包含：
        * t / event_seq：该时刻与截至该时刻已入账的事件数；
        * history_index / frame_t：用于精确截取趋势图与热力图；
        * bay_state：离散车位状态（与点阵逐位一致）；
        * metrics：该时刻的占用、充电、功率、累计电量、到达/拒绝等标量；
        * forecast / reserve：该时刻已发布的预测与保留位数（历史真实值）；
        * roster：车辆级明细（车位数较大时为 None，回放显示“该历史时刻未记录”）。

        同一时刻的多个事件在模型里是一个处理批次，因此只记一个快照（状态为该批次处理完后的
        真实状态）；没有新事件的纯时间推进不重复记录，避免回放位置与事件游标错位。
        """
        if self.time is None:
            return
        event_seq = len(self.events)
        # 事件批次（同一时刻多个事件）只记一个快照；没有新事件的纯推进不重复记录。
        # 例外：窗口结束时刻补记一份终态快照，保证回放能覆盖终点（此时 seq 不变但 t 前进，
        # 充电功率/累计电量确实变化，仍是该时刻的真实状态）。
        finished_now = self.time >= self.horizon - 1e-9
        last_t = self.replay_snapshots[-1]["t"] if self.replay_snapshots else None
        if event_seq == self._last_snapshot_event_seq and not (finished_now and last_t != self.time):
            return
        powers = self.powers()
        roster = None
        if self._roster_enabled:
            roster = []
            for bay, v in sorted(self.active.items()):
                roster.append({
                    "bay": bay, "power_kw": round(powers.get(bay, 0.0), 6),
                    "vehicle": {
                        "vehicle_id": v["vehicle_id"], "is_ev": bool(v["is_ev"]),
                        "needs_charge": bool(v["needs_charge"]),
                        "energy_kwh": v["energy_kwh"], "delivered_kwh": round(v["delivered_kwh"], 6),
                        "completed": bool(v["completed"]), "completion_min": v["completion_min"],
                        "departure_min": v["departure_min"], "time_min": v["time_min"],
                        "charge_start_min": v["charge_start_min"],
                    },
                })
        metrics = {
            "time_min": round(self.time, 6), "capacity": self.config.n_spaces,
            "occupancy": len(self.active), "charging_now": len(powers),
            "current_power_kw": round(sum(powers.values()), 6),
            "energy_delivered_kwh": round(self.delivered_total, 6),
            "charge_completed": self.completed_total,
            "arrivals": len(self.visits), "rejected": self.rejected_count,
            "rejected_ev": self.rejected_ev_count, "rejected_ice": self.rejected_ice_count,
            "rejection_rate": (self.rejected_count / len(self.visits)) if self.visits else None,
            "peak_power_kw": round(self.peak_power, 6), "peak_charging": self.peak_charging,
            "peak_occupancy": self.peak_occupancy,
        }
        snapshot = {
            # 保存未舍入的仿真时刻：history 行/事件时间同一源头，避免回放截断丢最后一行。
            "t": float(self.time), "event_seq": event_seq,
            "history_index": len(self.history) - 1,
            "frame_t": self.bay_frames[-1]["t"] if self.bay_frames else None,
            "bay_state": self._bay_state_string(),
            "metrics": metrics, "forecast": self.learner.forecast(),
            "reserve": self.reserve(), "roster": roster,
            "roster_available": roster is not None,
        }
        if len(self.replay_snapshots) >= self._snapshot_limit:
            # 二分降采样：位置变粗但每个位置仍是真实快照；首尾覆盖范围保持。
            self.replay_snapshots = self.replay_snapshots[::2]
        self.replay_snapshots.append(snapshot)
        self._last_snapshot_event_seq = event_seq

    def snapshot(self):
        c = self.config
        powers = self.powers()
        ledger = self.type_occupancy()
        metrics = {**calculate(self), **ledger["metrics"]}
        bays = []
        # Aggregate very large lots; keep complete metrics and CSV independent.
        shown = min(c.n_spaces, 300)
        for b in range(shown):
            v = self.active.get(b)
            bays.append({"bay": b, "charging_bay": b < c.charging_bays, "equipped": b < c.chargers,
                         "vehicle": dict(v) if v else None, "power_kw": powers.get(b, 0)})
        return {"config": c.to_dict(), "time_min": self.time, "horizon_min": self.horizon,
                "finished": self.finished, "forecast": self.learner.forecast(),
                "reserve": self.reserve(), "metrics": metrics, "bays": bays,
                "bays_shown": shown, "bays_total": c.n_spaces,
                "bay_state": self._bay_state_string(),
                "bay_frames": self.bay_frames,
                "occupied": [{"bay": b, "power_kw": powers.get(b, 0), "vehicle": dict(v)}
                             for b, v in sorted(self.active.items())],
                "events": self.events[-60:], "history": sampled(self.history),
                "demand_hash": self.demand_hash, "traffic_hash": self.traffic_hash,
                "rule_options": {"prediction_object": c.prediction_object,
                                 "coordinate_window": c.coordinate_window,
                                 "protected_bays": c.protected_bays},
                "observable_estimate": self.observable.estimate(),
                "cost_model_version": COST_MODEL_VERSION, "policy_name": ALL_POLICIES[c.policy],
                "policy_rule": self.rule, "policy_legacy": self.legacy_policy is not None,
                "type_occupancy": {"metrics": ledger["metrics"],
                                   "cutoff_min": ledger["cutoff_min"],
                                   "definitions": ledger["definitions"]},
                "intervention": dict(self.intervention),
                "assumptions": "合成车流；准入只看车型 is_ev、当前占用与资源、历史统计与预测；"
                               "needs_charge/能量/真实离场时间/未来到达对控制器不可见（充电意愿只在开始充电时显现）；"
                               "legacy 策略（含 strict）保留旧语义仅供历史复现，不是 π0；"
                               "固定枪位，无排队；只有占桩反事实干预才挪车（须有普通空位，保留原定离场）"}

    def export(self):
        ledger = self.type_occupancy()
        per_visit = {row["vehicle_id"]: row for row in ledger["by_visit"]}
        visits = [{**visit, **{name: per_visit[visit["vehicle_id"]][name]
                               for name in TYPE_OCCUPANCY_METRICS}}
                  for visit in self.visits]
        return {"state": self.snapshot(), "visits": visits, "prediction_scores": self.scores,
                "events": self.events, "power_segments": self.power_segments,
                "cost_model_version": COST_MODEL_VERSION, "traffic_hash": self.traffic_hash,
                "cost": cost_report(self), "occupancy_minutes": occupancy_minutes(self),
                "type_occupancy": ledger,
                "type_occupancy_metrics": ledger["metrics"],
                "pending_next_forecast": {**self.issued, "observed_next": False,
                                           "censored_after_min": self.time - self.issued["issued_at_min"]}}
