"""Backend-driven continuous run: wall-clock clock, monotonic ledger, explicit replay.

The backend owns the clock.  A tick advances the simulation by
elapsed_wall_seconds * effective_speed / 60 simulated minutes.  Modes:

* realtime    - ALWAYS 1x: one simulated minute per 60 wall seconds (1:1 with the clock).
               The stored speed is only remembered for accelerated mode and ignored here.
* accelerated - speed N: N times faster than realtime (validated 0.1 .. 86400)
* paused      - the clock does not advance; a tick only refreshes the reference time
* replay      - no clock advance; only replay_step() reveals recorded data

Every mode/speed transition (pause, set_speed, set_mode) first settles the outstanding
interval: the wall time since the last tick/settle is advanced with the *old* mode and
speed before the switch.  Otherwise the last poll-to-operation interval would vanish.
Resuming after a pause never back-fills the paused span and the monotonic seq/watermark
guard still refuses any re-accounting.

The run is a FINITE window: advancement is clamped to sim.horizon, so the run stops by
itself when the simulated window is used up (finished=True).  It is not an endless run.

The run never resets the seed and never replays the same trajectory through an array
index: each tick asks the simulation to advance from its current time to a later time.

Every simulation event is posted to the ledger exactly once.  Each posted event gets a
monotonic seq and the engine keeps a watermark (how many sim.events are already
posted).  Pause/resume cannot double count because the watermark never rewinds; a rewind
of the simulation event list is refused with an error instead of being re-accounted.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone

MODES = ("realtime", "accelerated", "paused", "replay")
MODE_LABELS = {"realtime": "实时 realtime", "accelerated": "加速 accelerated",
               "paused": "已暂停 paused", "replay": "回放 replay"}
LEDGER_SCHEMA_VERSION = 1
MIN_SPEED, MAX_SPEED = 0.1, 86400.0
DEFAULT_SPEED = 60.0

try:  # cost-backend owns costs.py; the version string is fixed by the v2 spec.
    from .costs import COST_MODEL_VERSION  # type: ignore
    COST_MODEL_SOURCE = "costs.py"
except Exception:  # pragma: no cover - depends on the sibling task landing first
    COST_MODEL_VERSION = "v2-2026-10-30"  # docs/methods/COST-MODEL-V2.md section 9
    COST_MODEL_SOURCE = "docs/methods/COST-MODEL-V2.md#9 (costs.py 未接入)"


class ContinuousError(ValueError):
    """非法的时钟模式/推进请求。"""


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _validate_speed(speed):
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed):
        raise ContinuousError("倍速必须是有限数值")
    if not MIN_SPEED <= speed <= MAX_SPEED:
        raise ContinuousError(f"倍速必须在 {MIN_SPEED} 至 {MAX_SPEED} 之间")
    return float(speed)


def _cost_block(metrics):
    """Cost ledger view.  null stays null: no 0 substitution, no demo defaults."""
    version = COST_MODEL_VERSION
    if not isinstance(metrics, dict):
        return {"available": False, "reason": "未提供 metrics", "cost_model_version": version,
                "total": None, "complete": False, "missing_parameters": ["cost"]}
    if "cost" in metrics:
        block = metrics.get("cost") or {}
        return {"available": True,
                "cost_model_version": metrics.get("cost_model_version") or block.get("version") or version,
                "total": metrics.get("total_cost", block.get("total")),
                "complete": metrics.get("cost_complete", block.get("complete")),
                "missing_parameters": metrics.get("cost_missing_parameters", block.get("missing_parameters")) or [],
                "attribution": metrics.get("cost_attribution", block.get("attribution")),
                "transfers": metrics.get("cost_transfers", block.get("transfers")),
                # 挪车成本已计入 total，精选字段必须带上它；projected 是“预计最终值”，与实时口径分列。
                # null 保持 null：不替代成 0，也不因缺键而被吞掉。
                "projected": block.get("projected"),
                "relocation_cost": block.get("relocation_cost"),
                "relocation_count": block.get("relocation_count"),
                "relocation_blocked": block.get("relocation_blocked"),
                "currency": block.get("currency"), "price_year": block.get("price_year"),
                "accounting_period": block.get("accounting_period"), "unit": block.get("unit")}
    return {"available": False, "reason": "metrics.calculate() 尚未提供 v2 cost 块（cost-backend 落地前）",
            "cost_model_version": version, "total": metrics.get("total_cost"), "complete": False,
            "missing_parameters": ["cost"], "legacy_cost_components": metrics.get("cost_components")}


class ContinuousEngine:
    def __init__(self, sim, clock=time.monotonic, speed=DEFAULT_SPEED):
        self.sim = sim
        self.clock = clock
        self.clock_is_injected = clock is not time.monotonic
        self.speed = _validate_speed(speed)
        self.mode = "realtime"
        self.paused = False
        self._resume_mode = "realtime"
        self.event_seq = 0
        self.ledger = []
        self.watermark = 0
        self.last_accounted_min = 0.0
        self.last_tick_monotonic = self.clock()
        self.last_tick_utc = _now_iso()
        self.real_elapsed_s = 0.0
        self.ticks = 0
        self.mode_history = [{"mode": "realtime", "at_utc": self.last_tick_utc, "speed": self.speed}]
        self.replay = {"active": False, "label": "回放 replay", "source": None, "cursor": 0, "total": 0, "events": []}

    # ------------------------------------------------------------------ modes
    def _record(self, mode, note=""):
        self.mode_history.append({"mode": mode, "at_utc": _now_iso(), "speed": self.speed, "note": note})

    def mode_label(self):
        return MODE_LABELS[self.mode]

    def effective_speed(self):
        """当前生效倍速：realtime 恒为 1x（忽略所选倍速），accelerated 用所选倍速。"""
        return 1.0 if self.mode == "realtime" else self.speed

    def settle(self):
        """先结算上一运行区间：把上次 tick/结算到当前时刻的墙上时间推进完。

        暂停、改倍速、切换模式前必须调用，否则最后一次轮询到操作时刻的时间会丢失。
        暂停/回放状态不推进，只刷新参考时刻。返回本次新入账的事件数。
        """
        now = self.clock()
        if self.paused or self.replay["active"]:
            self.last_tick_monotonic = now
            return 0
        elapsed = now - self.last_tick_monotonic
        self.last_tick_monotonic = now
        return self._advance(elapsed)

    def _advance(self, elapsed):
        """按当前生效倍速推进 elapsed 墙上秒，并把新事件入账；有限窗口在 horizon 处停止。"""
        if elapsed <= 0 or self.sim.finished:
            return 0
        speed = self.effective_speed()
        target = min(self.sim.time + elapsed * speed / 60.0, self.sim.horizon)
        if target <= self.sim.time + 1e-9:
            return 0
        self.sim.advance(target)
        posted = self.post_pending()
        self.real_elapsed_s += elapsed
        self.ticks += 1
        self.last_tick_utc = _now_iso()
        return posted

    def set_mode(self, mode, speed=None):
        if mode not in MODES:
            raise ContinuousError("模式必须为 realtime、accelerated、paused 或 replay")
        if mode == "replay":
            if not self.replay["active"]:
                raise ContinuousError("回放模式需要先调用 replay/start 指定回放源")
            self.settle()  # 进入回放前先结算上一运行区间
            self.paused = False
            self.mode = "replay"
            self._record("replay")
            return self.status()
        if self.replay["active"]:
            raise ContinuousError("回放进行中：请先退出回放再切换实时/加速")
        validated = None if speed is None else _validate_speed(speed)
        if mode == "paused":
            self.settle()  # 用旧模式/旧倍速结算到暂停时刻
            if validated is not None:
                self.speed = validated
            return self.pause(settle=False)
        self.settle()  # 用旧模式/旧倍速结算到切换时刻
        if validated is not None:
            self.speed = validated
        self.paused = False
        self._resume_mode = mode
        self.mode = mode
        self._record(mode)
        return self.status()

    def set_speed(self, speed):
        validated = _validate_speed(speed)
        self.settle()  # 用旧倍速结算到改速时刻
        self.speed = validated
        return self.status()

    def pause(self, settle=True):
        if self.paused:
            return self.status()
        if self.replay["active"]:
            raise ContinuousError("回放模式不参与暂停/恢复；请先退出回放")
        if settle:
            self.settle()  # 结算最后一次轮询到暂停时刻，不丢最后一个区间
        self._resume_mode = self.mode if self.mode in ("realtime", "accelerated") else "realtime"
        self.paused = True
        self.mode = "paused"
        self.last_tick_monotonic = self.clock()
        self._record("paused")
        return self.status()

    def resume(self):
        if not self.paused:
            raise ContinuousError("当前未暂停，无法恢复")
        if self.replay["active"]:
            raise ContinuousError("回放模式不参与暂停/恢复；请先退出回放")
        self.paused = False
        self.mode = self._resume_mode
        self.last_tick_monotonic = self.clock()  # 恢复时刻重新起算，暂停期间不补推进
        self._record(self.mode, "resumed")
        return self.status()

    # ------------------------------------------------------------------ clock
    def tick(self, elapsed_seconds=None):
        now = self.clock()
        if self.paused or self.replay["active"]:
            self.last_tick_monotonic = now
            return self.status()
        if elapsed_seconds is None:
            elapsed = now - self.last_tick_monotonic
        else:
            if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, (int, float)) \
                    or not math.isfinite(elapsed_seconds) or not 0 <= elapsed_seconds <= 86400:
                raise ContinuousError("elapsed_seconds 必须为0至86400的有限数值")
            elapsed = float(elapsed_seconds)
        self.last_tick_monotonic = now
        self._advance(elapsed)
        return self.status()

    def mark_manual_step(self):
        """手动单步后重新起算墙上时钟，避免随后一次 tick 重复计算这段时间。"""
        self.last_tick_monotonic = self.clock()
        return self.post_pending()

    # ----------------------------------------------------------------- ledger
    def post_pending(self):
        events = self.sim.events
        if len(events) < self.watermark:
            raise ContinuousError("事件账本回退：拒绝重复入账（已入账水位高于当前事件数）")
        new = events[self.watermark:]
        if not new:
            return 0
        last = self.last_accounted_min
        stamp = _now_iso()
        for event in new:
            when = event.get("time_min")
            if when is None or when < last - 1e-9:
                raise ContinuousError("事件时间倒退：拒绝重复入账")
            self.event_seq += 1
            self.ledger.append({**event, "seq": self.event_seq, "accounted_at_utc": stamp,
                                "source": "simulation", "cost_items": None,
                                "cost_model_version": COST_MODEL_VERSION})
            last = when
        self.watermark = len(events)
        self.last_accounted_min = last
        return len(new)

    def ledger_summary(self, metrics=None):
        kinds = {}
        for entry in self.ledger:
            kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
        return {"schema_version": LEDGER_SCHEMA_VERSION,
                "entries": len(self.ledger), "first_seq": 1 if self.ledger else None,
                "last_seq": self.event_seq, "watermark": self.watermark,
                "events_seen": len(self.sim.events), "per_kind": kinds,
                "last_accounted_min": round(self.last_accounted_min, 6),
                "double_accounting_guard": "单调 seq + 已入账水位；回退即报错",
                "cost": _cost_block(metrics), "cost_model_version": COST_MODEL_VERSION,
                "cost_model_source": COST_MODEL_SOURCE}

    def ledger_rows(self):
        return list(self.ledger)

    # ----------------------------------------------------------------- replay
    def start_replay(self, source="synthetic", events=None):
        if source == "synthetic":
            source_events = [dict(item) for item in (self.ledger if events is None else events)]
            self.replay = {"active": True, "label": "回放 replay", "source": "synthetic_ledger",
                           "cursor": 0, "total": len(source_events), "events": source_events}
        else:
            raise ContinuousError("回放源必须为 synthetic（通用合成账本回放）")
        self.paused = False
        self.mode = "replay"
        self.last_tick_monotonic = self.clock()
        self._record("replay", source)
        return self.status()

    def exit_replay(self):
        if not self.replay["active"]:
            raise ContinuousError("当前不在回放模式")
        self.replay = {"active": False, "label": "回放 replay", "source": None, "cursor": 0, "total": 0, "events": []}
        self.mode = self._resume_mode
        self.last_tick_monotonic = self.clock()
        self._record(self.mode, "exit replay")
        return self.status()

    def replay_step(self, count=1):
        if not self.replay["active"]:
            raise ContinuousError("当前不在回放模式")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 500:
            raise ContinuousError("回放步数必须为1至500的整数")
        start = self.replay["cursor"]
        items = self.replay["events"][start:start + count]
        self.replay["cursor"] = start + len(items)
        return {"label": "回放 replay", "source": "synthetic_ledger", "cursor": self.replay["cursor"],
                "total": self.replay["total"], "events": items}

    # ----------------------------------------------------------------- status
    def status(self, metrics=None):
        replay = {key: value for key, value in self.replay.items() if key != "events"}
        replay["events_total"] = len(self.replay["events"])
        return {"mode": self.mode, "mode_label": MODE_LABELS[self.mode], "paused": self.paused,
                "speed": self.speed, "effective_speed": self.effective_speed(),
                "speed_note": "realtime 恒为 1x（忽略所选倍速）：1 仿真分钟 / 60 实时秒；accelerated = 所选倍速 N × realtime",
                "window": {"finite": True, "horizon_min": self.sim.horizon,
                           "stops_when": "仿真时间到达 horizon_min（duration_hours × 60）后 tick 不再推进，finished=true",
                           "note": "有限窗口运行：到期自动停止，不是无限持续运行。"},
                "time_min": round(self.sim.time, 6), "horizon_min": self.sim.horizon,
                "finished": bool(self.sim.finished), "ticks": self.ticks,
                "real_elapsed_s": round(self.real_elapsed_s, 3), "last_tick_utc": self.last_tick_utc,
                "events_total": len(self.sim.events), "ledger": self.ledger_summary(metrics),
                "replay": replay, "modes": list(MODES),
                "clock_source": "injected" if self.clock_is_injected else "monotonic",
                "mode_history": self.mode_history[-8:]}
