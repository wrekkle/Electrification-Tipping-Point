"""小实例离线最优最小 k（R8-B）：0..K_max 完整逐整数枚举 + 一分钟网格 max-flow 可行性。

性质（输出必须原样带上这些标记）：
- uses_future_information = True：用完整到达/离场/能量需求，**离线上界，不在线可执行**。
- 完整性：k = 0..K_max 逐整数检查，不二分、不跳点（没有单调性证明）。
- 声明模型（model = "offline_uniform_power_minute_grid"）：每枪功率恒为
  p = min(connector_kw, feeder_kw / k)（所有 k 条枪可能同时充电的最坏并发口径），
  充电可抢占，时间离散到 1 分钟，需求分钟数按 ceil 折算。
  该口径下每车每分钟获得的功率不超过同车流下真实共享馈线的功率（真实并发数 <= k 时
  单枪功率 >= p），故：本模型可行 => 该配置在现有仿真语义下能量上可行；
  本模型不可行 => 只能证明"在该保守口径不可行"，不是连续时间/非恒定功率模型下的
  物理不可行证明。因此 confirmed_minimal 是"本声明模型内的实测最小性"，
  E3 输出必须带 evidence_model 列，论文不得把它写成物理意义上的已证明下界。
- 禁止用"峰值 × 均值 × 安全系数"当上界（本模块不产生任何此类界）。
"""
from __future__ import annotations

import math

MAX_VEHICLES = 20
MAX_CONNECTORS = 8
EPS = 1e-9
MODEL = "offline_uniform_power_minute_grid"


class InstanceTooLarge(ValueError):
    """实例超出小实例范围（车辆 > 20）；不静默截断，交由调用方记 missing_data/不覆盖。"""


def peak_occupancy(vehicles):
    """同时在场的最大车辆数（含所有车辆，不做准入）。"""
    points = []
    for vehicle in vehicles:
        points.append((vehicle["arrival_min"], 1))
        points.append((vehicle["departure_min"], -1))
    points.sort(key=lambda item: (item[0], item[1]))
    current = peak = 0
    for _, delta in points:
        current += delta
        peak = max(peak, current)
    return peak


def charge_jobs(instance):
    """需要充电的车辆 -> 作业列表（释放/截止/所需分钟）；零需求车辆单列不占枪。"""
    jobs = []
    for index, vehicle in enumerate(instance["vehicles"]):
        if not vehicle.get("needs_charge"):
            continue
        energy = float(vehicle.get("energy_kwh") or 0.0)
        if energy <= EPS:
            continue
        jobs.append({"job": index, "vehicle_id": vehicle["vehicle_id"],
                     "release_min": float(vehicle["arrival_min"]),
                     "deadline_min": float(vehicle["departure_min"]),
                     "energy_kwh": energy})
    return jobs


def _power(instance, k):
    connector_kw = instance.get("connector_kw")
    feeder_kw = instance.get("feeder_kw")
    if connector_kw is None or connector_kw <= 0:
        raise ValueError("实例缺少 connector_kw：无法判定充电可行性（应是 missing_data）")
    if feeder_kw is None or feeder_kw <= 0:
        return float(connector_kw)
    return min(float(connector_kw), float(feeder_kw) / float(k))


class _Dinic:
    """最小若干行实现：单位容量/整数容量都可以，返回最大流与用流明细。"""

    def __init__(self, size):
        self.size = size
        self.head = [[] for _ in range(size)]
        self.to = []
        self.cap = []
        self.orig = []

    def add(self, u, v, capacity):
        self.head[u].append(len(self.to))
        self.to.append(v)
        self.cap.append(int(capacity))
        self.orig.append(int(capacity))
        self.head[v].append(len(self.to))
        self.to.append(u)
        self.cap.append(0)
        self.orig.append(0)

    def _bfs(self, source, sink):
        level = [-1] * self.size
        level[source] = 0
        queue = [source]
        for node in queue:
            for edge in self.head[node]:
                if self.cap[edge] > 0 and level[self.to[edge]] < 0:
                    level[self.to[edge]] = level[node] + 1
                    queue.append(self.to[edge])
        self.level = level
        return level[sink] >= 0

    def _dfs(self, node, sink, limit):
        if node == sink:
            return limit
        while self.iterator[node] < len(self.head[node]):
            edge = self.head[node][self.iterator[node]]
            target = self.to[edge]
            if self.cap[edge] > 0 and self.level[target] == self.level[node] + 1:
                pushed = self._dfs(target, sink, min(limit, self.cap[edge]))
                if pushed > 0:
                    self.cap[edge] -= pushed
                    self.cap[edge ^ 1] += pushed
                    return pushed
            self.iterator[node] += 1
        return 0

    def maxflow(self, source, sink):
        flow = 0
        while self._bfs(source, sink):
            self.iterator = [0] * self.size
            while True:
                pushed = self._dfs(source, sink, 10 ** 9)
                if pushed <= 0:
                    break
                flow += pushed
        return flow

    def flow_on(self, edge):
        return self.orig[edge] - self.cap[edge]


def _window_slots(release, deadline):
    start = int(math.ceil(release - EPS))
    stop = int(math.floor(deadline + EPS))
    return start, max(start, stop)


def check_feasible(instance, k):
    """检查配置 k（枪数）在声明模型下是否可行；返回带证据的 dict。"""
    if isinstance(k, bool) or not isinstance(k, int) or k < 0:
        raise ValueError("k 必须是非负整数")
    charging_bays = instance.get("charging_bays")
    n_spaces = instance.get("n_spaces")
    if n_spaces is None or charging_bays is None:
        return {"k": k, "status": "missing_data",
                "reason": "缺 n_spaces 或 charging_bays，无法判定车位/枪位约束",
                "evidence": {}, "model": MODEL}
    peak = peak_occupancy(instance["vehicles"])
    if peak > n_spaces:
        return {"k": k, "status": "infeasible", "reason": "parking_capacity_exceeded",
                "evidence": {"peak_occupancy": peak, "n_spaces": n_spaces},
                "capacity_claim": "capacity_or_service_conflict", "model": MODEL}
    jobs = charge_jobs(instance)
    if not jobs:
        return {"k": k, "status": "feasible", "reason": "no_charge_demand",
                "evidence": {"charge_jobs": 0, "peak_occupancy": peak, "n_spaces": n_spaces},
                "model": MODEL}
    if k > charging_bays:
        return {"k": k, "status": "infeasible", "reason": "chargers_exceed_charging_bays",
                "evidence": {"k": k, "charging_bays": charging_bays},
                "capacity_claim": "capacity_or_service_conflict", "model": MODEL}
    if k == 0:
        return {"k": 0, "status": "infeasible", "reason": "no_connector_with_charge_demand",
                "evidence": {"charge_jobs": len(jobs)},
                "capacity_claim": "capacity_or_service_conflict", "model": MODEL}
    power = _power(instance, k)
    if power <= 0:
        return {"k": k, "status": "infeasible", "reason": "no_deliverable_power",
                "evidence": {"power_kw": power}, "capacity_claim": "capacity_or_service_conflict",
                "model": MODEL}
    horizon = instance.get("horizon_min")
    demands = []
    for job in jobs:
        start, stop = _window_slots(job["release_min"], job["deadline_min"])
        need = int(math.ceil(job["energy_kwh"] / power * 60.0 - EPS))
        if need <= 0:
            continue
        demands.append({**job, "start_slot": start, "stop_slot": stop, "need_minutes": need,
                        "window_minutes": stop - start})
    if not demands:
        return {"k": k, "status": "feasible", "reason": "no_positive_demand",
                "evidence": {"power_kw": power}, "model": MODEL}
    for demand in demands:
        if demand["need_minutes"] > demand["window_minutes"]:
            return {"k": k, "status": "infeasible", "reason": "window_too_short",
                    "evidence": {"vehicle_id": demand["vehicle_id"],
                                 "need_minutes": demand["need_minutes"],
                                 "window_minutes": demand["window_minutes"],
                                 "power_kw": power},
                    "capacity_claim": "capacity_or_service_conflict", "model": MODEL}
    slot_count = max(demand["stop_slot"] for demand in demands)
    job_base = 1
    slot_base = job_base + len(demands)
    sink = slot_base + slot_count
    network = _Dinic(sink + 1)
    total = 0
    for offset, demand in enumerate(demands):
        node = job_base + offset
        network.add(0, node, demand["need_minutes"])
        total += demand["need_minutes"]
        for slot in range(demand["start_slot"], demand["stop_slot"]):
            network.add(node, slot_base + slot, 1)
    for slot in range(slot_count):
        network.add(slot_base + slot, sink, k)
    flow = network.maxflow(0, sink)
    if flow < total:
        return {"k": k, "status": "infeasible", "reason": "insufficient_connector_minutes",
                "evidence": {"demanded_minutes": total, "schedulable_minutes": flow,
                             "power_kw": power, "jobs": len(demands),
                             "slots": slot_count},
                "capacity_claim": "capacity_or_service_conflict", "model": MODEL}
    schedule = []
    for offset, demand in enumerate(demands):
        node = job_base + offset
        for edge in network.head[node]:
            target = network.to[edge]
            if target < slot_base:
                continue
            used = network.flow_on(edge)
            if used > 0:
                schedule.append({"job": demand["job"], "vehicle_id": demand["vehicle_id"],
                                 "slot": target - slot_base, "minutes": used})
    return {"k": k, "status": "feasible", "reason": "schedule_exists",
            "evidence": {"power_kw": power, "jobs": len(demands), "slots": slot_count,
                         "demanded_minutes": total, "schedule": schedule},
            "capacity_claim": None, "model": MODEL}


def verify_schedule(instance, k, schedule):
    """构造性核验：把 max-flow 解翻译回分钟表，逐条检查容量/窗口/能量。

    可行配置必须能通过本函数（这就是"存在一个离线排程"的证书）。
    """
    power = _power(instance, k) if k > 0 else 0.0
    jobs = {job["job"]: job for job in charge_jobs(instance)}
    per_slot = {}
    per_job = {}
    problems = []
    for entry in schedule:
        slot = entry["slot"]
        per_slot[slot] = per_slot.get(slot, 0) + 1
        per_job[entry["job"]] = per_job.get(entry["job"], 0) + 1
        job = jobs.get(entry["job"])
        if job is None:
            problems.append("未知作业 %r" % (entry["job"],))
            continue
        start, stop = _window_slots(job["release_min"], job["deadline_min"])
        if not start <= slot < stop:
            problems.append("作业 %r 的分钟越过停留窗口" % job["vehicle_id"])
    for slot, count in per_slot.items():
        if count > k:
            problems.append("分钟 %d 并发 %d 超过 k=%d" % (slot, count, k))
    delivered = {}
    for job_index, minutes in per_job.items():
        job = jobs[job_index]
        delivered[job_index] = minutes * power / 60.0
        if delivered[job_index] + 1e-6 < job["energy_kwh"]:
            problems.append("作业 %r 交付 %.6f kWh < 需求 %.6f"
                            % (job["vehicle_id"], delivered[job_index], job["energy_kwh"]))
    missing = [index for index in jobs if index not in per_job and jobs[index]["energy_kwh"] > EPS]
    if missing:
        problems.append("有 %d 个充电作业未被排程" % len(missing))
    return {"ok": not problems, "problems": problems,
            "delivered_kwh": {jobs[i]["vehicle_id"]: delivered.get(i, 0.0) for i in jobs},
            "max_concurrent": max(per_slot.values(), default=0), "k": k}


def brute_force_feasible(instance, k, *, node_limit=2_000_000):
    """穷举验证（仅用于自测交叉验证，实例必须很小）：按分钟把作业分配到枪。

    与 check_feasible 同一离散模型；若两者结论不一致说明实现有 bug。
    """
    power = _power(instance, k) if k > 0 else 0.0
    jobs = charge_jobs(instance)
    if not jobs:
        return True
    if k <= 0:
        return False
    demands = []
    for job in jobs:
        start, stop = _window_slots(job["release_min"], job["deadline_min"])
        need = int(math.ceil(job["energy_kwh"] / power * 60.0 - EPS))
        if need > stop - start:
            return False
        demands.append({"start": start, "stop": stop, "need": need})
    demands.sort(key=lambda d: (d["stop"] - d["start"], -d["need"]))
    counters = {"nodes": 0}

    def place(index, used):
        counters["nodes"] += 1
        if counters["nodes"] > node_limit:
            raise RuntimeError("穷举节点超限：实例不够小")
        if index == len(demands):
            return True
        demand = demands[index]
        slots = list(range(demand["start"], demand["stop"]))
        need = demand["need"]
        from itertools import combinations
        for choice in combinations(slots, need):
            if any(used.get(slot, 0) + 1 > k for slot in choice):
                continue
            for slot in choice:
                used[slot] = used.get(slot, 0) + 1
            if place(index + 1, used):
                return True
            for slot in choice:
                used[slot] -= 1
                if used[slot] == 0:
                    del used[slot]
        return False

    return place(0, {})


def instance_from_block(block, *, connector_kw=None, feeder_kw=None,
                        max_vehicles=MAX_VEHICLES):
    """场站-日块 -> 小实例；车辆数超限抛 InstanceTooLarge（不截断）。"""
    site = block["site"]
    if site.get("n_spaces") is None or site.get("charging_bays") is None:
        raise ValueError("场站缺 n_spaces/charging_bays：E3 实例不可构造（missing_data）")
    if len(block["events"]) > max_vehicles:
        raise InstanceTooLarge("车辆数 %d 超过小实例上限 %d：%s:%s"
                               % (len(block["events"]), max_vehicles,
                                  block["site_id"], block["day_key"]))
    origin = block["first_arrival_min"]
    vehicles = []
    for event in block["events"]:
        need = bool(event["needs_charge"]) and event["energy_kwh"] is not None \
            and float(event["energy_kwh"]) > EPS
        if need and event["energy_kwh"] is None:
            raise ValueError("需要充电但缺 energy_kwh：实例不可构造（missing_data）")
        arrival = event["arrival_min"] - origin
        vehicles.append({"vehicle_id": event["event_id"],
                         "arrival_min": arrival,
                         "dwell_min": float(event["dwell_min"]),
                         "departure_min": arrival + float(event["dwell_min"]),
                         "is_ev": bool(event["is_ev"]),
                         "needs_charge": need,
                         "energy_kwh": float(event["energy_kwh"] or 0.0)})
    horizon = max(vehicle["departure_min"] for vehicle in vehicles)
    kw = connector_kw if connector_kw is not None else site.get("connector_kw")
    feeder = feeder_kw if feeder_kw is not None else site.get("feeder_kw")
    return {"instance_id": "%s:%s" % (block["site_id"], block["day_key"]),
            "site_id": block["site_id"], "day_key": block["day_key"],
            "n_spaces": site["n_spaces"], "charging_bays": site["charging_bays"],
            "connectors": site.get("connectors"),
            "connector_kw": kw, "feeder_kw": feeder,
            "horizon_min": horizon, "vehicles": vehicles,
            "information": "offline_upper_bound_not_executable",
            "uses_future_information": True, "model": MODEL}


def min_connectors(instance, *, k_max=None):
    """完整枚举 k=0..K_max 求最小可行枪数（离线、声明模型、非在线可执行）。"""
    charging_bays = instance.get("charging_bays")
    connectors = instance.get("connectors")
    physical_bound = None
    if charging_bays is not None and connectors is not None:
        physical_bound = min(int(charging_bays), int(connectors))
    cap = MAX_CONNECTORS if k_max is None else int(k_max)
    if isinstance(k_max, int) and not isinstance(k_max, bool) and k_max < 0:
        raise ValueError("k_max 必须是非负整数")
    if physical_bound is not None:
        cap = min(cap, physical_bound)
    per_k = {}
    k_min = None
    for k in range(0, cap + 1):
        record = check_feasible(instance, k)
        per_k[k] = record
        if record["status"] == "feasible":
            k_min = k
            break
    if k_min is not None:
        stop_reason = "found_feasible"
    elif physical_bound is not None and cap >= physical_bound:
        stop_reason = "exhausted_physical_bound"
    else:
        stop_reason = "budget_cap"
    return {"instance_id": instance.get("instance_id"),
            "site_id": instance.get("site_id"), "day_key": instance.get("day_key"),
            "k_min": k_min, "k_max_searched": cap, "physical_bound": physical_bound,
            "stop_reason": stop_reason, "per_k": per_k,
            "model": MODEL,
            "information": "offline_upper_bound_not_executable",
            "uses_future_information": True,
            "direction": ("conservative_uniform_power_model：min(charger_kw, feeder_kw/k) 恒定；"
                          "可行=>该仿真语义下能量可行；不可行仅在本口径成立"),
            "n_vehicles": len(instance["vehicles"]),
            "n_charge_jobs": len(charge_jobs(instance)),
            "peak_occupancy": peak_occupancy(instance["vehicles"]),
            "n_spaces": instance.get("n_spaces"),
            "charging_bays": instance.get("charging_bays"),
            "connectors": instance.get("connectors")}
