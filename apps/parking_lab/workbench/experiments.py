"""Paired policy comparisons and reproducible output envelopes."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import tempfile

from . import VERSION
from .config import Config, POLICIES
from .costs import COST_MODEL_VERSION
from .demand import generate, stream_hash
from .simulation import Simulation
from .metrics import calculate


def provenance():
    root = Path(__file__).resolve().parent
    hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".py", ".html", ".js", ".css"}}
    return {"model_version": VERSION, "source_sha256": hashes,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "data_source": "synthetic; not calibrated to observed parking data",
            "units": {"time": "minute", "power": "kW", "energy": "kWh",
                      "cost": "config.cost.currency (default TWD) per simulated window"},
            "cost_model_version": COST_MODEL_VERSION}


def export_run(sim):
    return {"provenance": provenance(), "config": sim.config.to_dict(),
            "seed": sim.config.seed, "demand_hash": sim.demand_hash, **sim.export()}


def compare(config, seeds=None):
    c = config if isinstance(config, Config) else Config.parse(config)
    seeds = seeds if seeds is not None else [c.seed, c.seed + 1, c.seed + 2]
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= 8 or any(type(s) is not int or not 0 <= s < 2**31 for s in seeds):
        raise ValueError("随机种子需为1至8个不重复的非负整数，最大2147483647")
    if len(set(seeds)) != len(seeds):
        raise ValueError("随机种子不能重复")
    max_factor = {"steady": 1, "peaks": c.peak_multiplier, "burst": c.burst_multiplier,
                  "drift": max(1, c.drift_rate_multiplier)}[c.scenario]
    if len(seeds) * 4 * c.arrival_rate_hour * max_factor * c.duration_hours > 120000:
        raise ValueError("对比总运行量过大，请减少随机种子、到达强度或仿真时长")
    runs = []
    for seed in seeds:
        seeded = replace(c, seed=seed)
        arrivals = generate(seeded)
        digest = stream_hash(arrivals)
        for policy in POLICIES:
            sim = Simulation(replace(seeded, policy=policy), arrivals)
            sim.run()
            runs.append({"seed": seed, "policy": policy, "demand_hash": digest, "metrics": calculate(sim)})
    keys = ["rejection_rate", "total_cost", "energy_delivered_kwh", "charge_completion_rate_all",
            "mean_occupancy_rate", "brier", "interval_coverage", "interval_width_min", "departed_shortfall_kwh"]
    rows = []
    for policy, label in POLICIES.items():
        selected = [r for r in runs if r["policy"] == policy]
        row = {"policy": policy, "name": label, "seeds": len(seeds)}
        for key in keys:
            values = [r["metrics"][key] for r in selected if r["metrics"][key] is not None]
            row[key] = statistics.mean(values) if values else None
            row[key + "_std"] = statistics.stdev(values) if len(values) > 1 else (0.0 if values else None)
        diffs, incomplete = [], 0
        for r in selected:
            base = next(x for x in runs if x["seed"] == r["seed"] and x["policy"] == "open")
            left, right = r["metrics"]["total_cost"], base["metrics"]["total_cost"]
            if left is None or right is None:
                # 缺参运行的总成本是 null（未知），不得当 0 参与相减
                incomplete += 1
                continue
            diffs.append(left - right)
        row["paired_cost_delta_vs_open"] = statistics.mean(diffs) if diffs else None
        row["paired_cost_pairs"] = len(diffs)
        row["paired_cost_incomplete_runs"] = incomplete
        row["cost_complete_runs"] = sum(r["metrics"]["cost_complete"] for r in selected)
        rows.append(row)
    first = runs[0]["metrics"]
    return {"provenance": provenance(), "config": c.to_dict(), "seeds": seeds, "rows": rows, "runs": runs,
            "cost_model_version": first["cost_model_version"],
            "cost_currency": first["cost_currency"], "cost_price_year": first["cost_price_year"],
            "comparison": "每个seed重放同一外生车辆流；std为种子间样本标准差，不是置信区间；非最优性证明",
            "cost_note": "缺参时 total_cost 为 null；均值只聚合 complete 运行，配对成本差只对两侧 complete 的 seed 计算"}


RESULT_FILENAME = "result.json"
TEMP_PREFIX = ".result-"
TEMP_SUFFIX = ".tmp"


def _temp_artifacts(target):
    """Our own temp files: named .result-<random>.tmp, written before os.replace."""
    return sorted(p for p in target.iterdir()
                  if p.is_file() and p.name.startswith(TEMP_PREFIX) and p.name.endswith(TEMP_SUFFIX))


def inspect_output(directory):
    """Classify an output directory without modifying it.

    States: "missing" (path absent), "not_a_directory", "incomplete" (empty directory or
    only our own temp files: a run that did not finish), "complete" (result.json exists
    and parses), "corrupt" (result.json exists but does not parse) and "foreign" (other
    files but no result.json). Only "complete" is evidence of a successful run.
    """
    target = Path(directory)
    if not target.exists():
        return {"state": "missing", "path": str(target), "result": None,
                "temp_files": [], "other_files": []}
    if not target.is_dir():
        return {"state": "not_a_directory", "path": str(target), "result": None,
                "temp_files": [], "other_files": []}
    temps = _temp_artifacts(target)
    result = target / RESULT_FILENAME
    other = sorted(p.name for p in target.iterdir() if p.name != RESULT_FILENAME and p not in temps)
    if result.exists():
        try:
            with open(result, encoding="utf-8") as handle:
                json.load(handle)
        except (OSError, ValueError) as exc:
            return {"state": "corrupt", "path": str(target), "result": str(result),
                    "temp_files": [p.name for p in temps], "other_files": other,
                    "error": f"{type(exc).__name__}: {exc}"}
        return {"state": "complete", "path": str(target), "result": str(result),
                "temp_files": [p.name for p in temps], "other_files": other}
    if not other:
        return {"state": "incomplete", "path": str(target), "result": None,
                "temp_files": [p.name for p in temps], "other_files": []}
    return {"state": "foreign", "path": str(target), "result": None,
            "temp_files": [p.name for p in temps], "other_files": other}


def fingerprint_output(directory):
    """sha256/size of a complete result.json, for manifests and idempotence checks."""
    state = inspect_output(directory)
    if state["state"] != "complete":
        raise RuntimeError(f"{state['path']} 没有完整结果（{state['state']}），不能当作成功证据")
    path = Path(state["result"])
    data = path.read_bytes()
    return {"path": state["path"], "result": str(path), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def write_output(directory, payload, *, force=False):
    """Write result.json atomically: temp file in the same directory, fsync, os.replace.

    A crash or a serialization error must not leave a half-written result.json. The
    directory itself is created with exist_ok=False, so two processes racing for the
    same path cannot both win: one creates it and writes, the other gets
    FileExistsError (explicit refusal, not a silent overwrite).

    An existing directory is refused by default. force=True is the explicit override:
    it replaces a complete/corrupt result.json atomically, and recovers an incomplete
    directory (leftover .result-*.tmp from a killed process, or an empty directory) by
    deleting only our own temp files first. Foreign files are never deleted; force only
    adds result.json next to them. Recovery assumes no concurrent writer on the same
    directory; the default path stays exclusive through the atomic directory creation.

    fsync covers the file contents only; directory-entry durability after power loss is
    not claimed or verified.
    """
    target = Path(directory)
    state = inspect_output(target)
    kind = state["state"]
    if kind == "missing":
        try:
            target.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise FileExistsError(f"输出目录已被另一写入者创建，拒绝并发写同一路径：{target}") from None
    elif kind == "not_a_directory":
        raise FileExistsError(f"输出路径已存在且不是目录：{target}")
    elif kind == "complete" and not force:
        raise FileExistsError(f"输出目录已有完整结果，拒绝覆盖：{state['result']}（如需覆盖请显式 force=True）")
    elif kind == "corrupt" and not force:
        raise RuntimeError(f"输出目录的 result.json 无法解析，不能当作成功结果：{state['result']}"
                           f"（{state.get('error')}；如需覆盖请显式 force=True）")
    elif kind == "incomplete" and not force:
        detail = "、".join(state["temp_files"]) or "空目录"
        raise FileExistsError(f"输出目录存在但未完成（{detail}），可能是上次写入中断；"
                              f"默认不当作结果也不覆盖，确认后可显式 force=True 重试：{target}")
    elif kind == "foreign" and not force:
        raise FileExistsError(f"输出目录已存在且包含未知文件（{'、'.join(state['other_files'][:5])}），"
                              f"拒绝写入：{target}")
    if force:
        # Only our own temp artifacts are removed; result.json is replaced atomically below.
        for stale in state["temp_files"]:
            try:
                (target / stale).unlink()
            except OSError:
                pass
    handle = tempfile.NamedTemporaryFile("w", dir=target, delete=False, encoding="utf-8",
                                         prefix=TEMP_PREFIX, suffix=TEMP_SUFFIX)
    try:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(handle.name, target / RESULT_FILENAME)
    except BaseException:
        try:
            handle.close()
        except Exception:
            pass
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        # A failed run must not leave an empty directory that blocks a retry with
        # exist_ok=False. Only remove it when it is empty (never delete foreign data
        # or a previous result kept by force).
        try:
            target.rmdir()
        except OSError:
            pass
        raise
    return target.resolve()
