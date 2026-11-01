"""Loopback-only JSON API and offline web UI, using the Python standard library.

The backend owns the continuous clock: the browser polls /api/advance and the engine moves
the simulation forward from its current time (never by resetting the seed or replaying an
array index).  Every posted event gets a monotonic seq guarded by a watermark, so a
pause/resume cycle cannot double count.  Replay is a separate explicit mode.
"""
from __future__ import annotations

import csv
import io
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import VERSION
from .config import ALL_POLICIES, Config, SCENARIOS, presets
from .continuous import COST_MODEL_SOURCE, COST_MODEL_VERSION, ContinuousEngine, ContinuousError
from .experiments import (FORMAL_POLICY_SET, POLICY_SETS, compare, export_run)
from .metrics import sampled
from .simulation import Simulation

EXPORT_SCHEMA_VERSION = 2
REPLAY_LABEL = "回放 replay"


class SessionLimitError(RuntimeError):
    """并发实验数量到达上限；与“请求体过大”的 OverflowError 分开，避免 413 误报。"""


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.sessions = {}

    def create(self, config, mode=None, speed=None):
        with self.lock:
            now = time.monotonic()
            for key in list(self.sessions):
                if now - self.sessions[key]["used"] > 3600:
                    del self.sessions[key]
            if len(self.sessions) >= 6:
                raise SessionLimitError("当前已有6个实验，请重置或关闭一个实验后再创建")
            sim = Simulation(config)
            engine = ContinuousEngine(sim)
            if mode is not None and mode != "realtime":
                engine.set_mode(mode, speed)
            elif speed is not None:
                engine.set_speed(speed)
            key = uuid.uuid4().hex
            self.sessions[key] = {"sim": sim, "engine": engine, "used": now, "created_utc": _now_iso()}
            return key, self.sessions[key]

    def get(self, key):
        if not isinstance(key, str) or key not in self.sessions:
            raise KeyError("实验不存在或已过期，请重新创建")
        self.sessions[key]["used"] = time.monotonic()
        return self.sessions[key]


def state_payload(entry):
    sim, engine = entry["sim"], entry["engine"]
    state = sim.snapshot()
    metrics = state.get("metrics") if isinstance(state, dict) else None
    payload = dict(state)
    payload["continuous"] = engine.status(metrics)
    payload["ledger_tail"] = engine.ledger_rows()[-60:]
    payload["cost_model_version"] = (metrics or {}).get("cost_model_version") or COST_MODEL_VERSION
    payload["cost_model_source"] = COST_MODEL_SOURCE
    payload["runtime"] = {"server_version": VERSION, "session_created_utc": entry["created_utc"],
                          "export_schema_version": EXPORT_SCHEMA_VERSION,
                          "replay_label": REPLAY_LABEL if engine.replay["active"] else None,
                          "clock_source": payload["continuous"]["clock_source"]}
    return payload


def replay_snapshot_payload(entry, index):
    """回放视图的唯一数据源：一份后端真实状态快照。

    回放不再把“实时 state”按时间裁剪来拼视图；点阵、KPI、趋势图、热力图、事件列表
    都从这一个快照派生，快照时间和状态同源。车辆级明细只在快照保存了 roster 时可用，
    否则明确标记为未记录。cost/运行诊断属于当前运行状态，放在 replay_diagnostics 中
    单独标注，不冒充历史时刻。
    """
    sim, engine = entry["sim"], entry["engine"]
    snapshots = getattr(sim, "replay_snapshots", [])
    if not snapshots:
        raise ValueError("当前运行没有可用的回放快照，请先让仿真产生事件")
    try:
        wanted = int(index)
    except (TypeError, ValueError):
        raise ValueError("回放位置必须是整数快照序号")
    idx = max(0, min(wanted, len(snapshots) - 1))
    snap = snapshots[idx]
    t = snap["t"]
    history_index = snap.get("history_index", -1)
    history = sim.history[:history_index + 1] if history_index >= 0 else []
    frames = [frame for frame in sim.bay_frames if frame["t"] <= t + 1e-9]
    events = [dict(item) for item in engine.ledger if item.get("seq", 0) <= snap["event_seq"]][-60:]
    scores = [row for row in sim.scores if row.get("observed_at_min", 0) <= t + 1e-9]

    def mean(key):
        values = [row[key] for row in scores if row.get(key) is not None]
        return sum(values) / len(values) if values else None

    prediction = {"samples": len(scores), "brier": mean("brier"),
                  "type_accuracy": mean("correct"), "interval_coverage": mean("covered"),
                  "interval_width_min": mean("width_min"),
                  "interval_level": sim.config.interval_level}
    metrics = dict(snap["metrics"])
    metrics.update({"prediction_samples": prediction["samples"],
                    "brier": prediction["brier"], "type_accuracy": prediction["type_accuracy"],
                    "interval_coverage": prediction["interval_coverage"],
                    "interval_width_min": prediction["interval_width_min"],
                    "interval_level": prediction["interval_level"],
                    # 时间平均占用率需要运行期累计，未随快照保存：历史值不可恢复，显式置空。
                    "mean_occupancy_rate": None})
    continuous = engine.status(sim.snapshot().get("metrics") or {})
    positions = [{"t": item["t"], "event_seq": item["event_seq"]} for item in snapshots]
    replay_block = {"active": True, "label": REPLAY_LABEL, "source": "synthetic_ledger",
                    "basis": "state_snapshot", "index": idx, "cursor": idx,
                    "total": len(snapshots), "t": t, "event_seq": snap["event_seq"],
                    "history_t": history[-1]["time_min"] if history else None,
                    "frame_t": frames[-1]["t"] if frames else None,
                    "positions": positions,
                    "note": "回放位置=后端记录的真实状态快照；同一时刻的多个事件合为一个快照；"
                            "不插值，也不产生到达/离场/充电完成事件。"}
    return {"config": sim.config.to_dict(), "time_min": t, "horizon_min": sim.horizon,
            "finished": t >= sim.horizon - 1e-9, "metrics": metrics,
            "bay_state": snap["bay_state"], "history": sampled(history),
            "bay_frames": frames, "occupied": snap.get("roster"),
            "occupied_available": bool(snap.get("roster_available")),
            "events": events, "events_total": snap["event_seq"], "ledger_tail": events,
            "forecast": snap["forecast"], "reserve": snap["reserve"],
            "prediction_summary": prediction,
            "policy_name": ALL_POLICIES[sim.config.policy], "policy_rule": sim.rule,
            "policy_legacy": sim.legacy_policy is not None,
            "cost_model_version": COST_MODEL_VERSION, "cost_model_source": COST_MODEL_SOURCE,
            "replay": replay_block, "continuous": continuous,
            "replay_diagnostics": {"diagnostics_time_min": sim.time,
                                   "note": "运行明细/账本/成本是当前运行状态（非回放时刻），回放视图只使用本快照数据。"},
            "runtime": {"server_version": VERSION, "session_created_utc": entry["created_utc"],
                        "export_schema_version": EXPORT_SCHEMA_VERSION,
                        "replay_label": REPLAY_LABEL, "clock_source": continuous["clock_source"]}}


def export_payload(entry):
    """Export must match the UI: same state block, ledger and cost version."""
    payload = export_run(entry["sim"])
    state = state_payload(entry)
    payload["state"] = state
    payload["runtime"] = {"server_version": VERSION, "export_schema_version": EXPORT_SCHEMA_VERSION,
                          "exported_utc": _now_iso(), "continuous": state["continuous"],
                          "ledger": entry["engine"].ledger_rows(),
                          "cost_model_version": state["cost_model_version"],
                          "cost_model_source": state["cost_model_source"],
                          "replay_label": state["runtime"]["replay_label"]}
    return payload


def make_server(port=8765):
    store = Store()
    comparison_gate = threading.BoundedSemaphore(1)
    assets = Path(__file__).resolve().parent / "web"

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, fmt, *args):
            pass

        def send(self, status, body, content_type="application/json; charset=utf-8", filename=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def body(self):
            # 严格只接受一个十进制 Content-Length：重复头是可请求走私的解析歧义，
            # 非十进制（如 "+2"）不是合法 HTTP；空请求体是客户端错误（400），超限才是 413。
            lengths = self.headers.get_all("Content-Length") or []
            if len(lengths) != 1:
                raise ValueError("请求必须带且只能带一个 Content-Length")
            raw = lengths[0].strip()
            if not raw.isdigit():
                raise ValueError("Content-Length 必须为非负十进制整数")
            length = int(raw)
            if length == 0:
                raise ValueError("请求体不能为空（必须为JSON对象）")
            if length > 131072:
                raise OverflowError("请求体必须为1至131072字节")
            def bad_constant(value):
                raise ValueError("JSON不允许NaN或Infinity")
            data = json.loads(self.rfile.read(length).decode("utf-8"), parse_constant=bad_constant)
            if not isinstance(data, dict):
                raise ValueError("请求必须为JSON对象")
            return data

        def guard(self):
            actual_port = self.server.server_address[1]
            allowed_hosts = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}
            if self.headers.get("Host", "") not in allowed_hosts:
                raise PermissionError("仅支持本地地址访问")
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + host for host in allowed_hosts}:
                raise PermissionError("不接受其他网页发起的请求")

        # ------------------------------------------------------------------ GET
        def do_GET(self):
            try:
                self.guard()
                parsed = urlsplit(self.path)
                path = unquote(parsed.path)
                query = parse_qs(parsed.query)
                if path == "/api/health":
                    return self.send(200, {"ok": True, "version": VERSION, "synthetic": True,
                                           "continuous": True, "replay": True})
                if path == "/api/presets":
                    return self.send(200, {"presets": presets(), "defaults": Config().to_dict(),
                                           "policies": ALL_POLICIES, "scenarios": SCENARIOS,
                                           "policy_sets": {key: {
                                               "label": value["label"], "kind": value["kind"],
                                               "baseline": value["baseline"],
                                               "applicable_model": value["applicable_model"],
                                               "info_contract": value["info_contract"],
                                               "legacy_notice": value["legacy_notice"],
                                               "policies": value["policies"]}
                                               for key, value in POLICY_SETS.items()},
                                           "default_policy_set": FORMAL_POLICY_SET,
                                           "cost_model_version": COST_MODEL_VERSION})
                if path in {"/api/state", "/api/export"}:
                    with store.lock:
                        entry = store.get(query.get("id", [None])[0])
                        if path == "/api/state":
                            return self.send(200, state_payload(entry))
                        kind = query.get("format", ["json"])[0]
                        if kind == "json":
                            return self.send(200, export_payload(entry), filename="parking-run.json")
                        if kind == "cost_csv":
                            metrics = entry["sim"].snapshot().get("metrics") or {}
                            block = metrics.get("cost") or {}
                            version = metrics.get("cost_model_version") or COST_MODEL_VERSION
                            currency = block.get("currency") or ""
                            price_year = "" if block.get("price_year") is None else block.get("price_year")
                            period = block.get("accounting_period") or ""
                            missing = metrics.get("cost_missing_parameters") or block.get("missing_parameters") or []
                            unit = block.get("unit") or ""
                            rows = []
                            for name, value in (block.get("items") or metrics.get("cost_items") or {}).items():
                                rows.append({"item": name, "value": "" if value is None else value, "unit": unit,
                                             "cost_model_version": version, "currency": currency, "price_year": price_year,
                                             "accounting_period": period, "complete": "false" if value is None else "true",
                                             "missing_parameters": "|".join(missing)})
                            for group in ("attribution", "transfers"):
                                for name, value in (block.get(group) or {}).items():
                                    if isinstance(value, dict):
                                        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                                    rows.append({"item": group + "." + name, "value": "" if value is None else value,
                                                 "unit": unit, "cost_model_version": version, "currency": currency,
                                                 "price_year": price_year, "accounting_period": period,
                                                 "complete": "false" if value is None else "true",
                                                 "missing_parameters": "|".join(missing)})
                            columns = ["item", "value", "unit", "cost_model_version", "currency", "price_year",
                                       "accounting_period", "complete", "missing_parameters"]
                            output = io.StringIO(newline="")
                            writer = csv.DictWriter(output, fieldnames=columns)
                            writer.writeheader()
                            writer.writerows(rows)
                            return self.send(200, output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8",
                                             "parking-cost.csv")
                        if kind == "ledger_csv":
                            rows = entry["engine"].ledger_rows()
                            columns = ["seq", "time_min", "kind", "vehicle_id", "is_ev", "needs_charge", "bay",
                                       "delivered_kwh", "accounted_at_utc", "cost_model_version", "source"]
                            output = io.StringIO(newline="")
                            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
                            writer.writeheader()
                            writer.writerows(rows)
                            return self.send(200, output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8",
                                             "parking-ledger.csv")
                        selectors = {"csv": entry["sim"].visits, "predictions_csv": entry["sim"].scores,
                                     "events_csv": entry["sim"].events}
                        if kind not in selectors:
                            raise ValueError("导出格式必须为json、csv、predictions_csv、events_csv、ledger_csv或cost_csv")
                        rows = selectors[kind]
                        output = io.StringIO(newline="")
                        base_columns = {"csv": ["vehicle_id", "time_min", "is_ev", "needs_charge", "dwell_min", "energy_kwh", "admitted", "bay", "departure_min", "delivered_kwh", "departed", "completed", "completion_min"],
                                        "predictions_csv": ["vehicle_id", "issued_at_min", "observed_at_min", "p_ev", "is_ev", "wait_min", "lower_min", "upper_min", "brier", "correct", "covered", "width_min", "interval_score"],
                                        "events_csv": ["time_min", "kind", "vehicle_id", "is_ev", "needs_charge", "bay", "delivered_kwh"]}
                        columns = list(dict.fromkeys(base_columns[kind] + [key for row in rows for key in row]))
                        if columns:
                            writer = csv.DictWriter(output, fieldnames=columns)
                            writer.writeheader()
                            writer.writerows(rows)
                        return self.send(200, output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "parking-" + kind + ".csv")
                mapping = {"/": ("index.html", "text/html; charset=utf-8"),
                           "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                           "/style.css": ("style.css", "text/css; charset=utf-8"),
                           "/lib/charts.js": ("lib/charts.js", "text/javascript; charset=utf-8"),
                           "/lib/dotgrid.js": ("lib/dotgrid.js", "text/javascript; charset=utf-8")}
                if path not in mapping:
                    return self.send(404, {"error": "页面不存在"})
                filename, mime = mapping[path]
                return self.send(200, (assets / filename).read_bytes(), mime)
            except Exception as exc:
                self.error(exc)

        # ----------------------------------------------------------------- POST
        def do_POST(self):
            try:
                self.guard()
                data = self.body()
                path = urlsplit(self.path).path
                if path == "/api/validate":
                    return self.send(200, {"ok": True, "config": Config.parse(data.get("config", {})).to_dict()})
                if path == "/api/compare":
                    if not comparison_gate.acquire(blocking=False):
                        raise BlockingIOError("已有策略对比正在计算，请稍后再试")
                    try:
                        result = compare(Config.parse(data.get("config", {})), data.get("seeds"),
                                         policy_set=data.get("policy_set") or FORMAL_POLICY_SET)
                    finally:
                        comparison_gate.release()
                    return self.send(200, result)
                with store.lock:
                    if path == "/api/create":
                        mode = data.get("mode")
                        key, entry = store.create(Config.parse(data.get("config", {})), mode=mode,
                                                  speed=data.get("speed"))
                        return self.send(200, {"id": key, **state_payload(entry)})
                    if path == "/api/close":
                        key = data.get("id")
                        store.get(key)
                        del store.sessions[key]
                        return self.send(200, {"ok": True})
                    if path in {"/api/step", "/api/run", "/api/reset"}:
                        key = data.get("id")
                        entry = store.get(key)
                        sim, engine = entry["sim"], entry["engine"]
                        if path == "/api/reset":
                            config = Config.parse(data["config"]) if "config" in data else sim.config
                            speed = engine.speed
                            sim = Simulation(config)
                            engine = ContinuousEngine(sim, speed=speed)
                            entry["sim"], entry["engine"] = sim, engine
                            state = state_payload(entry)
                        elif path == "/api/run":
                            sim.run()
                            engine.mark_manual_step()
                            state = state_payload(entry)
                        else:
                            dt = data.get("minutes", 5)
                            if isinstance(dt, bool) or not isinstance(dt, (int, float)) or not 0 < dt <= 4320:
                                raise ValueError("步长必须为0至4320分钟的有限正数")
                            sim.advance(sim.time + dt)
                            engine.mark_manual_step()
                            state = state_payload(entry)
                        return self.send(200, {"id": key, **state})
                    if path == "/api/advance":
                        key = data.get("id")
                        entry = store.get(key)
                        engine = entry["engine"]
                        elapsed = data.get("elapsed_seconds")
                        status = engine.tick(elapsed)
                        # state_payload() 用带 metrics 的 engine.status()，内容更全（v2 cost 块含
                        # projected/relocation_*）；tick() 的 status 未带 metrics 会造成兜底口径覆盖，
                        # 故让 state_payload 的 continuous 生效，两者同源同口径。
                        return self.send(200, {"id": key, "continuous": status, **state_payload(entry)})
                    if path in {"/api/mode", "/api/speed"}:
                        key = data.get("id")
                        entry = store.get(key)
                        engine = entry["engine"]
                        if path == "/api/speed":
                            engine.set_speed(data.get("speed"))
                        else:
                            engine.set_mode(data.get("mode"), data.get("speed"))
                        return self.send(200, {"id": key, **state_payload(entry)})
                    if path == "/api/pause":
                        key = data.get("id")
                        entry = store.get(key)
                        entry["engine"].pause()
                        return self.send(200, {"id": key, **state_payload(entry)})
                    if path == "/api/resume":
                        key = data.get("id")
                        entry = store.get(key)
                        entry["engine"].resume()
                        return self.send(200, {"id": key, **state_payload(entry)})
                    if path in {"/api/replay/jump", "/api/replay/snapshot"}:
                        key = data.get("id")
                        entry = store.get(key)
                        engine = entry["engine"]
                        if path == "/api/replay/jump":
                            result = engine.replay_jump(data.get("index", 0))
                            return self.send(200, {"id": key, "replay_jump": result, **state_payload(entry)})
                        payload = replay_snapshot_payload(entry, data.get("index", 0))
                        return self.send(200, {"id": key, **payload})
                    if path in {"/api/replay/start", "/api/replay/step", "/api/replay/exit"}:
                        key = data.get("id")
                        entry = store.get(key)
                        engine = entry["engine"]
                        if path == "/api/replay/start":
                            engine.start_replay(data.get("source", "synthetic"))
                            return self.send(200, {"id": key, **state_payload(entry)})
                        if path == "/api/replay/exit":
                            engine.exit_replay()
                            return self.send(200, {"id": key, **state_payload(entry)})
                        step = engine.replay_step(data.get("count", 1))
                        return self.send(200, {"id": key, "replay_step": step, **state_payload(entry)})
                self.send(404, {"error": "接口不存在"})
            except Exception as exc:
                self.error(exc)

        def error(self, exc):
            if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
                return
            if isinstance(exc, KeyError):
                status = 404
            elif isinstance(exc, OverflowError):
                status = 413
            elif isinstance(exc, PermissionError):
                status = 403
            elif isinstance(exc, BlockingIOError):
                status = 503
            elif isinstance(exc, SessionLimitError):
                status = 429
            elif isinstance(exc, (ValueError, TypeError, UnicodeError)):
                status = 400
            else:
                status = 500
                import traceback
                traceback.print_exc()
            self.close_connection = True
            self.send(status, {"error": str(exc) if status != 500 else "服务内部错误，请查看运行日志"})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.store = store
    return server


def serve(port=8765):
    server = make_server(port)
    print(f"停车场仿真与在线学习实验台 http://127.0.0.1:{server.server_port}/", flush=True)
    print("合成仿真 + 台北已保存批次（只读）；成本参数缺失时显示未知／待校准。按Ctrl+C停止。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
