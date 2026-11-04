# -*- coding: utf-8 -*-
"""NYC 半合成研究结果的只读数据访问层（同时支持 v1 / v2 / v3 契约）。

数据契约：
- v1: research/nyc_semisynthetic_20261103/v1/VIEWER_CONTRACT.md
- v2: research/nyc_semisynthetic_20261103/v2/VIEWER_CONTRACT_V2.md
- v3: research/nyc_semisynthetic_20261103/v3_t63/VIEWER_CONTRACT_V3.md

研究端把离线运行结果分别写到 v1/viewer/、v2/viewer/ 与 v3_t63/viewer/；后端只读加载，
不在请求里重算账本、成本或缺口，也不改写研究文件。数据集版本由 index.json 的
schema_version 区分（v2 前缀 "nyc_viewer_v2/"，v3 前缀 "nyc_viewer_v3/"），
不把新字段套到旧契约上。

目录可用环境变量覆盖（联调时指向 viewer_sample 或临时夹具）：
- v1: NYC_VIEWER_DIR
- v2: NYC_VIEWER_DIR_V2
- v3: NYC_VIEWER_DIR_V3
默认数据集由 NYC_VIEWER_DATASET 指定（v1 / v2 / v3，缺省 v1，保持 v1 行为不变）；
HTTP 请求可用 ?dataset=v1|v2|v3 显式选择。目录或 index.json 缺失时
/api/nyc/index 返回 status="empty" 与提示，不抛 500。

对外函数返回可直接 JSON 序列化的 dict 或 bytes；错误用异常表达，由 server.py 转成
JSON {"error": ...}：ViewerNotFound -> 404，ValueError -> 400。
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
from pathlib import Path

SCHEMA_V1 = "nyc_semisynthetic_viewer/v1"
SCHEMA_V2_PREFIX = "nyc_viewer_v2/"
SCHEMA_V3_PREFIX = "nyc_viewer_v3/"
SCHEMA_VERSION = SCHEMA_V1
DATASETS = ("v1", "v2", "v3")
DEFAULT_DATASET = "v1"
ENV_DIRS = {"v1": "NYC_VIEWER_DIR", "v2": "NYC_VIEWER_DIR_V2",
            "v3": "NYC_VIEWER_DIR_V3"}
ENV_DATASET = "NYC_VIEWER_DATASET"

REPO_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = REPO_ROOT / "research" / "nyc_semisynthetic_20261103"
DEFAULT_VIEWER_DIR = RESEARCH_ROOT / "v1" / "viewer"
DEFAULT_VIEWER_DIR_V2 = RESEARCH_ROOT / "v2" / "viewer"
DEFAULT_VIEWER_DIR_V3 = RESEARCH_ROOT / "v3_t63" / "viewer"

# run_id / world_id 只允许字母、数字、下划线、点、连字符；点号不得构成 .. 路径段。
ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,200}")
# 允许从 index 引用的结果/世界文件名：单层文件名，必须以 .json 结尾。
FILE_RE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,199}\.json")
# v2 曲线 CSV：export/<run_id>_curve.csv 或单层 <run_id>_curve.csv。
CURVE_CSV_RE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,199}\.csv")
EXPORT_FORMATS = ("json", "curve_csv", "outcomes_csv", "world_json")
EXPORT_FORMATS_V2 = ("json", "curve_csv", "world_json")
EXPORT_FORMATS_V3 = ("json", "curve_csv", "world_json")
# v3 的 index 用相对路径引用 runs/、world/、export/ 下的文件；只允许单层到四层安全路径。
REL_SEGMENT_RE = re.compile(r"[A-Za-z0-9_.-]{1,200}")
MAX_REL_DEPTH = 4
V3_MECHANISM_LABELS = {
    "M0": "M0 冻结 v2 模板（校正前对照）",
    "M1": "M1 到达时间条件属性（训练集收缩）",
    "M2": "M2 经验连续周/多日块",
}

DEFAULT_MODE_LABELS = {
    "R0": {"label": "R0 观测重放", "provenance": "observed",
           "note": "真实会话占用与交付重放；不计算真实请求缺口或拒绝率"},
    "R1": {"label": "R1 充电会话半合成", "provenance": "scenario",
           "note": "以真实充电会话为锚点补齐未知量；条件性情景，不是纽约真实完整需求"},
    "R2": {"label": "R2 三类车半合成", "provenance": "scenario",
           "note": "在 R1 上加燃油车与不充电电动车停车流；场景假设，不是实测"},
}
DEFAULT_MODE_LABELS_V2 = {
    "R0": "观测重放 R0",
    "R1": "充电会话半合成 R1",
    "R2": "三类车半合成 R2",
}

_CACHE_LOCK = threading.RLock()
_JSON_CACHE = {}


class ViewerNotFound(KeyError):
    """请求的查看器对象不存在；server 层统一转成 404 JSON。"""

    def __str__(self):
        return str(self.args[0]) if self.args else "对象不存在"


# --------------------------------------------------------------------- 数据集与目录
def dataset_name(value=None):
    """解析数据集名：显式参数 > 环境变量 NYC_VIEWER_DATASET > 默认 v1。"""
    raw = value if value is not None else os.environ.get(ENV_DATASET)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return DEFAULT_DATASET
    if not isinstance(raw, str):
        raise ValueError("数据集参数必须为字符串（v1、v2 或 v3）")
    key = raw.strip().lower()
    if key not in DATASETS:
        raise ValueError("数据集必须为 v1、v2 或 v3")
    return key


def data_dir(dataset=None):
    """当前数据集的结果目录；对应环境变量优先，否则仓库内契约默认目录。"""
    key = dataset_name(dataset)
    override = os.environ.get(ENV_DIRS[key])
    if override and override.strip():
        path = Path(override.strip()).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()
    if key == "v3":
        return DEFAULT_VIEWER_DIR_V3.resolve()
    return (DEFAULT_VIEWER_DIR_V2 if key == "v2" else DEFAULT_VIEWER_DIR).resolve()


def schema_kind(doc):
    """按 index.json 的 schema_version 识别契约版本；无法识别时按 v1 处理。"""
    if not isinstance(doc, dict):
        return None
    version = doc.get("schema_version")
    if isinstance(version, str) and version.startswith(SCHEMA_V3_PREFIX):
        return "v3"
    if isinstance(version, str) and version.startswith(SCHEMA_V2_PREFIX):
        return "v2"
    return "v1"


def _validate_id(value, kind):
    if not isinstance(value, str) or not ID_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError(kind + "标识不合法：只允许字母、数字、下划线、点和连字符，且不是 . 或 ..")
    return value


def _safe_file(base, name):
    """把文件名解析为 base 目录下的单层 JSON 文件；越界或非法名返回 None。"""
    if not isinstance(name, str) or not FILE_RE.fullmatch(name):
        return None
    candidate = (base / name).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    return candidate


def _safe_relative(base, name, suffixes=(".json", ".csv")):
    """把 index 里的相对路径（runs/xxx.json、export/xxx.csv）解析到 base 内；非法返回 None。"""
    if not isinstance(name, str):
        return None
    rel = name.strip().replace("\\", "/")
    if not rel or rel.startswith("/") or ":" in rel:
        return None
    parts = rel.split("/")
    if len(parts) > MAX_REL_DEPTH:
        return None
    for part in parts:
        if part in {"", ".", ".."} or not REL_SEGMENT_RE.fullmatch(part):
            return None
    if not any(rel.lower().endswith(suffix) for suffix in suffixes):
        return None
    try:
        candidate = (base / rel).resolve()
        candidate.relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return candidate


def _index_worlds(index_doc):
    """v3 index 的 worlds[] 转成 {world_id: entry}；缺失或格式错误返回 {}。"""
    if not isinstance(index_doc, dict):
        return {}
    worlds = index_doc.get("worlds")
    if not isinstance(worlds, list):
        return {}
    return {item.get("world_id"): item for item in worlds
            if isinstance(item, dict) and isinstance(item.get("world_id"), str)}


def _read_json(path):
    """带 mtime+size 缓存的只读 JSON 加载；缺失、不可解析或非对象返回 None。"""
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _CACHE_LOCK:
        cached = _JSON_CACHE.get(key)
        if cached is not None:
            return cached
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError):
        return None
    if not isinstance(doc, dict):
        return None
    with _CACHE_LOCK:
        _JSON_CACHE[key] = doc
        for stale in [item for item in _JSON_CACHE if item[0] == key[0] and item != key]:
            _JSON_CACHE.pop(stale, None)
    return doc


def _load_index(dataset=None):
    """返回 (index_doc|None, data_path, reason, schema_kind|None)；reason 只在 None 时非空。"""
    base = data_dir(dataset)
    if not base.is_dir():
        return None, base, "数据目录不存在", None
    index_path = base / "index.json"
    if not index_path.is_file():
        return None, base, "数据目录存在但缺少 index.json", None
    doc = _read_json(index_path)
    if doc is None:
        return None, base, "index.json 无法解析为 JSON 对象", None
    return doc, base, "", schema_kind(doc)


def _serve_kind(dataset):
    """数据集的实际契约版本：优先 index.json 的 schema_version，缺失时按请求数据集。"""
    doc, _base, _reason, kind = _load_index(dataset)
    if kind is not None:
        return kind
    return dataset


def _index_runs(index_doc):
    if not isinstance(index_doc, dict):
        return {}
    runs = index_doc.get("runs")
    if not isinstance(runs, list):
        return {}
    return {item.get("run_id"): item for item in runs
            if isinstance(item, dict) and isinstance(item.get("run_id"), str)}


def _empty_index_payload(dataset, base, reason):
    directory = str(base)
    payload = {
        "schema_kind": None,
        "dataset": dataset,
        "status": "empty",
        "generated_at": None,
        "warning": None,
        "data_dir": directory,
        "sites": [],
        "scenarios": [],
        "runs": [],
    }
    if dataset == "v3":
        payload.update({
            "schema_version": SCHEMA_V3_PREFIX + "1",
            "message": ("NYC v3 查看器数据尚未生成：" + reason + "。研究端运行 v3 导出后写入 " +
                        directory + "；也可设置环境变量 NYC_VIEWER_DIR_V3 指向数据目录。"),
            "mode_labels": {},
            "worlds": [],
            "panels": {},
            "counts": {},
            "registration": {},
            "limits": [],
            "sources": {},
            "downloads": {},
            "provenance": {},
        })
        return payload
    v2 = dataset == "v2"
    if v2:
        payload.update({
            "schema_version": SCHEMA_V2_PREFIX + "1",
            "message": ("尚未生成 NYC v2 半合成研究结果：" + reason + "。研究端写入 " + directory +
                        " 后刷新页面即可；也可设置环境变量 NYC_VIEWER_DIR_V2 指向数据目录。"),
            "mode_labels": dict(DEFAULT_MODE_LABELS_V2),
            "provenance": {},
            "fixed_eval": [],
            "robust": [],
            "sources": [],
            "limits": [],
        })
    else:
        payload.update({
            "schema_version": SCHEMA_VERSION,
            "message": ("尚未生成 NYC 半合成研究结果：" + reason + "。研究端写入 " + directory +
                        " 后刷新页面即可。"),
            "mode_labels": {key: dict(value) for key, value in DEFAULT_MODE_LABELS.items()},
            "provenance": {},
            "fixed_eval": None,
            "robust": None,
            "sources": None,
            "limits": None,
        })
    return payload


def index_payload(dataset=None):
    """GET /api/nyc/index。目录缺失时返回 status="empty" 与提示，不返回 500。"""
    key = dataset_name(dataset)
    doc, base, reason, kind = _load_index(key)
    if doc is None:
        return _empty_index_payload(key, base, reason)
    payload = dict(doc)
    payload["dataset"] = key
    payload["schema_kind"] = kind or key
    default_schema = (SCHEMA_V3_PREFIX + "1" if kind == "v3" else
                      (SCHEMA_V2_PREFIX + "1" if kind == "v2" else SCHEMA_VERSION))
    payload.setdefault("schema_version", default_schema)
    if kind == "v3":
        for name in ("runs", "worlds", "sites", "scenarios", "limits"):
            if not isinstance(payload.get(name), list):
                payload[name] = []
        for name in ("panels", "counts", "registration", "downloads"):
            if not isinstance(payload.get(name), dict):
                payload[name] = {}
        if not isinstance(payload.get("sources"), (dict, list)):
            payload["sources"] = {}
        if not isinstance(payload.get("mode_labels"), dict):
            payload["mode_labels"] = {}
        if not payload.get("status"):
            payload["status"] = "ready"
        payload["data_dir"] = str(base)
        return payload
    if not isinstance(payload.get("mode_labels"), dict) or not payload["mode_labels"]:
        labels = (DEFAULT_MODE_LABELS_V2 if kind == "v2" else DEFAULT_MODE_LABELS)
        payload["mode_labels"] = ({name: value for name, value in labels.items()}
                                  if kind == "v2" else
                                  {name: dict(value) for name, value in labels.items()})
    for name in ("sites", "scenarios", "runs"):
        if not isinstance(payload.get(name), list):
            payload[name] = []
    if kind == "v2":
        # v2 契约的顶层分析对象；缺失时给空列表，页面显示“未知/无记录”而不是猜数。
        for name in ("fixed_eval", "robust", "sources", "limits"):
            if not isinstance(payload.get(name), list):
                payload[name] = []
        if not isinstance(payload.get("counts"), dict):
            payload["counts"] = {}
        if not isinstance(payload.get("registration"), dict):
            payload["registration"] = {}
    else:
        if not isinstance(payload.get("provenance"), dict):
            payload["provenance"] = {}
    if not payload.get("status"):
        payload["status"] = "ready"
    payload["data_dir"] = str(base)
    return payload


def health_payload(dataset=None):
    """GET /api/nyc/health：只报告目录与数据状态，不依赖目录存在。"""
    key = dataset_name(dataset)
    doc, base, reason, kind = _load_index(key)
    runs = doc.get("runs") if isinstance(doc, dict) else None
    status = "empty"
    if isinstance(doc, dict):
        status = doc.get("status") or "ready"
    payload = {
        "ok": True,
        "service": "nyc-viewer",
        "dataset": key,
        "schema_version": (doc.get("schema_version") if isinstance(doc, dict)
                           else (SCHEMA_V3_PREFIX + "1" if key == "v3" else
                                 (SCHEMA_V2_PREFIX + "1" if key == "v2" else SCHEMA_VERSION))),
        "schema_kind": kind,
        "data_dir": str(base),
        "exists": base.is_dir(),
        "index_present": (base / "index.json").is_file(),
        "status": status,
        "generated_at": doc.get("generated_at") if isinstance(doc, dict) else None,
        "runs": len(runs) if isinstance(runs, list) else 0,
        "detail": reason or None,
    }
    if isinstance(doc, dict):
        for name in ("code_version", "counts", "registration"):
            if name in doc:
                payload[name] = doc[name]
        if kind == "v3" and isinstance(doc.get("worlds"), list):
            payload["worlds"] = len(doc["worlds"])
    return payload


def _require_data_dir(dataset=None):
    base = data_dir(dataset)
    if not base.is_dir():
        raise ViewerNotFound("尚无 NYC 半合成结果数据目录：" + str(base) + "。研究端生成结果后重试。")
    return base


# --------------------------------------------------------------------- 运行与世界
def run_payload(run_id, dataset=None):
    """GET /api/nyc/run/<run_id>：返回运行 JSON 原始对象（契约 §5）。"""
    rid = _validate_id(run_id, "运行")
    base = _require_data_dir(dataset)
    index_doc, _, _, kind = _load_index(dataset)
    indexed = _index_runs(index_doc).get(rid) or {}
    candidates = []
    if kind == "v3":
        for name in (indexed.get("run_json"), "runs/run_" + rid + ".json"):
            candidate = _safe_relative(base, name, (".json",))
            if candidate is not None and candidate.is_file() and candidate not in candidates:
                candidates.append(candidate)
        if not candidates:
            raise ViewerNotFound("v3 数据集中未找到运行 " + rid + " 的结果文件（runs/run_<run_id>.json）")
        for candidate in candidates:
            doc = _read_json(candidate)
            if doc is not None:
                return doc
        raise ViewerNotFound("运行 " + rid + " 的结果文件无法解析为 JSON 对象")
    for name in (indexed.get("result_file"), "run_" + rid + ".json"):
        candidate = _safe_file(base, name)
        if candidate is not None and candidate.is_file() and candidate not in candidates:
            candidates.append(candidate)
    if not candidates:
        raise ViewerNotFound("未找到运行 " + rid + " 的结果文件（run_<run_id>.json）")
    for candidate in candidates:
        doc = _read_json(candidate)
        if doc is not None:
            return doc
    raise ViewerNotFound("运行 " + rid + " 的结果文件无法解析为 JSON 对象")


def _indexed_world_candidates(base, index_doc, expected_stem):
    out = []
    for entry in _index_runs(index_doc).values():
        candidate = _safe_file(base, entry.get("world_file"))
        if candidate is not None and candidate.stem == expected_stem and candidate not in out:
            out.append(candidate)
    return out


def world_payload(world_id, dataset=None):
    """GET /api/nyc/world/<world_id>：返回冻结世界 JSON（v2 契约 §6）。"""
    wid = _validate_id(world_id, "世界")
    base = _require_data_dir(dataset)
    index_doc, _, _, kind = _load_index(dataset)
    if kind == "v3":
        entry = _index_worlds(index_doc).get(wid) or {}
        v3_candidates = []
        for name in (entry.get("world_json"), "world/world_" + wid + ".json"):
            candidate = _safe_relative(base, name, (".json",))
            if candidate is not None and candidate.is_file() and candidate not in v3_candidates:
                v3_candidates.append(candidate)
        if not v3_candidates:
            raise ViewerNotFound("v3 数据集中未找到世界 " + wid + " 的世界文件（world/world_<world_id>.json）")
        for candidate in v3_candidates:
            doc = _read_json(candidate)
            if doc is not None:
                return doc
        raise ViewerNotFound("世界 " + wid + " 的世界文件无法解析为 JSON 对象")
    candidates = []
    default = _safe_file(base, "world_" + wid + ".json")
    if default is not None:
        candidates.append(default)
    for candidate in _indexed_world_candidates(base, index_doc, "world_" + wid):
        if candidate not in candidates:
            candidates.append(candidate)
    existing = [candidate for candidate in candidates if candidate.is_file()]
    if not existing:
        raise ViewerNotFound("未找到世界 " + wid + " 的世界文件（world_<world_id>.json）")
    for candidate in existing:
        doc = _read_json(candidate)
        if doc is not None:
            return doc
    raise ViewerNotFound("世界 " + wid + " 的世界文件无法解析为 JSON 对象")


def _find_world_file(base, run_doc, run_id, index_doc):
    names = []
    export = run_doc.get("export") if isinstance(run_doc, dict) else None
    if isinstance(export, dict):
        names.append(export.get("world_file"))
    if isinstance(run_doc, dict):
        names.append(run_doc.get("world_file"))
    indexed = _index_runs(index_doc).get(run_id) or {}
    names.append(indexed.get("world_file"))
    for name in names:
        candidate = _safe_file(base, name)
        if candidate is not None and candidate.is_file():
            return candidate
    return None


def _v2_curve_file(base, run_doc, run_id):
    names = []
    if isinstance(run_doc, dict):
        names.append(run_doc.get("curve_file"))
    names.append("export/" + run_id + "_curve.csv")
    for name in names:
        if not isinstance(name, str) or not name.strip():
            continue
        rel = name.strip()
        if rel.startswith("export/"):
            rel = rel[len("export/"):]
        if not CURVE_CSV_RE.fullmatch(rel):
            continue
        candidate = (base / "export" / rel).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


# --------------------------------------------------------------------- 导出
def _scalar(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _csv_bytes(columns, rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore", restval="")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def _json_bytes(doc):
    return json.dumps(doc, ensure_ascii=False, allow_nan=False, indent=1).encode("utf-8")


def _curve_csv(run_id, mode, rows):
    preferred = ["run_id", "mode", "n", "capital", "service_loss", "J",
                 "rejected_total", "delivered_share"]
    feature_keys = []
    for row in rows:
        features = row.get("features") if isinstance(row, dict) else None
        if isinstance(features, dict):
            for key in features:
                if key not in feature_keys and key not in preferred:
                    feature_keys.append(key)
    columns = preferred + feature_keys
    flat = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = {"run_id": run_id, "mode": mode}
        for key, value in row.items():
            if key == "features":
                continue
            item[key] = _scalar(value)
        features = row.get("features") if isinstance(row.get("features"), dict) else {}
        for key, value in features.items():
            if key not in item:
                item[key] = _scalar(value)
        flat.append(item)
    return _csv_bytes(columns, flat)


def _outcomes_csv(run_id, mode, vehicles):
    preferred = ["run_id", "mode", "session_id", "synthetic_driver_id", "arrival_local",
                 "dwell_min", "cls", "requested_kwh", "accept_kw", "bay", "rejected",
                 "delivered_kwh", "shortfall_kwh", "origin", "assumption_id"]
    extra = []
    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            continue
        for key in vehicle:
            if key not in preferred and key not in extra:
                extra.append(key)
    columns = preferred + extra
    flat = []
    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            continue
        item = {"run_id": run_id, "mode": mode}
        for key, value in vehicle.items():
            item[key] = _scalar(value)
        flat.append(item)
    return _csv_bytes(columns, flat)


def _format_error(dataset, fmt):
    if dataset == "v3":
        raise ValueError("v3 数据集只提供 json、curve_csv、world_json；面板表格请用 /api/nyc/table/<name>?dataset=v3")
    if dataset == "v2" and fmt in EXPORT_FORMATS:
        raise ValueError("v2 数据集不提供 outcomes_csv；可用格式：json、curve_csv、world_json")
    allowed = EXPORT_FORMATS_V2 if dataset == "v2" else EXPORT_FORMATS
    raise ValueError("导出格式必须为 " + "、".join(allowed))


def _export_v2(run_id, fmt, base, run_doc, index_doc):
    kind = schema_kind(index_doc) or "v2"
    rid = run_id
    if fmt == "json":
        return _json_bytes(run_doc), "application/json; charset=utf-8", "nyc-" + rid + ".json"
    if fmt == "curve_csv":
        curve_file = _v2_curve_file(base, run_doc, rid)
        if curve_file is None:
            raise ViewerNotFound("运行 " + rid + " 没有曲线 CSV（export/<run_id>_curve.csv），没有 curve_csv 可导出")
        try:
            body = curve_file.read_bytes()
        except OSError:
            raise ViewerNotFound("运行 " + rid + " 的曲线 CSV 无法读取")
        if not body.strip():
            raise ViewerNotFound("运行 " + rid + " 的曲线 CSV 为空")
        return body, "text/csv; charset=utf-8", "nyc-" + rid + "-curve.csv"
    world_file = _find_world_file(base, run_doc, rid, index_doc)
    if world_file is None:
        raise ViewerNotFound("运行 " + rid + " 未关联世界文件（world_<world_id>.json），没有 world_json 可导出")
    doc = _read_json(world_file)
    if doc is None:
        raise ViewerNotFound("运行 " + rid + " 关联的世界文件无法解析为 JSON 对象")
    return _json_bytes(doc), "application/json; charset=utf-8", "nyc-" + rid + "-world.json"


def _v3_curve_file(base, run_doc, indexed, rid):
    exports = run_doc.get("exports") if isinstance(run_doc, dict) else None
    names = []
    if isinstance(exports, dict):
        names.append(exports.get("curve_csv"))
    names.extend([indexed.get("curve_csv"), "export/" + rid + "_curve.csv"])
    for name in names:
        candidate = _safe_relative(base, name, (".csv",))
        if candidate is not None and candidate.is_file():
            return candidate
    return None


def _v3_world_for_run(base, run_doc, indexed, index_doc):
    meta = run_doc.get("meta") if isinstance(run_doc.get("meta"), dict) else {}
    site = meta.get("site_id") or indexed.get("site_id")
    scenario = meta.get("scenario_id") or indexed.get("scenario_id")
    mechanism = meta.get("mechanism") or indexed.get("mechanism")
    for entry in _index_worlds(index_doc).values():
        if (entry.get("site_id") == site and entry.get("scenario_id") == scenario and
                entry.get("mechanism") == mechanism):
            candidate = _safe_relative(base, entry.get("world_json"), (".json",))
            if candidate is not None and candidate.is_file():
                return candidate
    return None


def _export_v3(run_id, fmt, base, run_doc, index_doc):
    """v3 导出：运行 JSON、曲线 CSV、匹配机制的世界 JSON，全部读取研究端真实文件。"""
    rid = run_id
    indexed = _index_runs(index_doc).get(rid) or {}
    if fmt == "json":
        return _json_bytes(run_doc), "application/json; charset=utf-8", "nyc-" + rid + ".json"
    if fmt == "curve_csv":
        curve_file = _v3_curve_file(base, run_doc, indexed, rid)
        if curve_file is None:
            raise ViewerNotFound("运行 " + rid + " 没有曲线 CSV（export/<run_id>_curve.csv），没有 curve_csv 可导出")
        try:
            body = curve_file.read_bytes()
        except OSError:
            raise ViewerNotFound("运行 " + rid + " 的曲线 CSV 无法读取")
        if not body.strip():
            raise ViewerNotFound("运行 " + rid + " 的曲线 CSV 为空")
        return body, "text/csv; charset=utf-8", "nyc-" + rid + "-curve.csv"
    world_file = _v3_world_for_run(base, run_doc, indexed, index_doc)
    if world_file is None:
        raise ViewerNotFound("运行 " + rid + " 未关联世界文件（world/world_<world_id>.json），没有 world_json 可导出")
    doc = _read_json(world_file)
    if doc is None:
        raise ViewerNotFound("运行 " + rid + " 关联的世界文件无法解析为 JSON 对象")
    return _json_bytes(doc), "application/json; charset=utf-8", "nyc-" + rid + "-world.json"


def _export_v1(run_id, fmt, base, run_doc, index_doc):
    rid = run_id
    mode = run_doc.get("mode")
    if fmt == "json":
        return _json_bytes(run_doc), "application/json; charset=utf-8", "nyc-" + rid + ".json"
    if fmt == "curve_csv":
        rows = run_doc.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ViewerNotFound("该运行没有配置—成本曲线（rows 为空），没有 curve_csv 可导出")
        return (_curve_csv(rid, mode, rows), "text/csv; charset=utf-8",
                "nyc-" + rid + "-curve.csv")
    if fmt == "outcomes_csv":
        selected = run_doc.get("selected")
        vehicles = selected.get("vehicles") if isinstance(selected, dict) else None
        if not isinstance(vehicles, list) or not vehicles:
            raise ViewerNotFound("该运行没有逐车结果（selected.vehicles 为空），没有 outcomes_csv 可导出")
        return (_outcomes_csv(rid, mode, vehicles), "text/csv; charset=utf-8",
                "nyc-" + rid + "-outcomes.csv")
    world_file = _find_world_file(base, run_doc, rid, index_doc)
    if world_file is None:
        raise ViewerNotFound("运行 " + rid + " 未关联世界文件（world_<world_id>.json），没有 world_json 可导出")
    doc = _read_json(world_file)
    if doc is None:
        raise ViewerNotFound("运行 " + rid + " 关联的世界文件无法解析为 JSON 对象")
    return _json_bytes(doc), "application/json; charset=utf-8", "nyc-" + rid + "-world.json"


def export_payload(run_id, fmt, dataset=None):
    """GET /api/nyc/export/<run_id>?format=...；返回 (body_bytes, content_type, filename)。

    v2 按契约提供 json / curve_csv / world_json；v1 保持原有 json / curve_csv /
    outcomes_csv / world_json 行为。实际契约版本由 index.json 的 schema_version 决定。
    """
    key = dataset_name(dataset)
    rid = _validate_id(run_id, "运行")
    kind = _serve_kind(key)
    if kind == "v3":
        allowed = EXPORT_FORMATS_V3
    elif kind == "v2":
        allowed = EXPORT_FORMATS_V2
    else:
        allowed = EXPORT_FORMATS
    if fmt not in allowed:
        _format_error(kind if kind in DATASETS else key, fmt)
    base = _require_data_dir(key)
    index_doc, _, _, _ = _load_index(key)
    run_doc = run_payload(rid, key)
    if kind == "v3":
        return _export_v3(rid, fmt, base, run_doc, index_doc)
    if kind == "v2":
        return _export_v2(rid, fmt, base, run_doc, index_doc)
    return _export_v1(rid, fmt, base, run_doc, index_doc)


# --------------------------------------------------------------------- v3 面板表格下载
def _v3_table_paths(index_doc, base):
    """收集 v3 index 引用到的 CSV（面板表格与 downloads.tables），解析到 base 内的真实文件。"""
    names = []
    panels = index_doc.get("panels") if isinstance(index_doc, dict) else None
    if isinstance(panels, dict):
        for panel in panels.values():
            if not isinstance(panel, dict):
                continue
            for field in ("table_a_csv", "table_b_csv", "noise_floor_csv", "drift_csv",
                          "csv", "selection_csv"):
                value = panel.get(field)
                if isinstance(value, str):
                    names.append(value)
    downloads = index_doc.get("downloads") if isinstance(index_doc, dict) else None
    tables = downloads.get("tables") if isinstance(downloads, dict) else None
    if isinstance(tables, list):
        names.extend(name for name in tables if isinstance(name, str))
    out = []
    for name in names:
        candidate = _safe_relative(base, name, (".csv",))
        if candidate is not None and candidate.is_file() and candidate not in out:
            out.append(candidate)
    return out


def table_payload(name, dataset=None):
    """GET /api/nyc/table/<name>：返回 v3 面板表格的真实 CSV 字节（只读、白名单限定）。"""
    key = dataset_name(dataset)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("表格名不能为空")
    rel = name.strip().replace("\\", "/")
    base_name = rel.split("/")[-1]
    if not CURVE_CSV_RE.fullmatch(base_name):
        raise ValueError("表格名只允许字母、数字、下划线、点和连字符，且必须以 .csv 结尾")
    base = _require_data_dir(key)
    doc, _, _reason, kind = _load_index(key)
    if kind != "v3":
        raise ValueError("表格下载接口只用于 v3 数据集")
    allowed = _v3_table_paths(doc, base)
    target = None
    for candidate in allowed:
        if candidate.name == base_name:
            target = candidate
            break
    if target is None:
        raise ViewerNotFound("v3 数据集中没有表格 " + base_name)
    try:
        body = target.read_bytes()
    except OSError:
        raise ViewerNotFound("表格 " + base_name + " 无法读取")
    if not body.strip():
        raise ViewerNotFound("表格 " + base_name + " 为空")
    return body, "text/csv; charset=utf-8", base_name


# --------------------------------------------------------------------- v2 分析对象
def _v2_section(dataset, doc, base, reason, kind, name):
    rows = doc.get(name) if isinstance(doc, dict) else None
    rows = rows if isinstance(rows, list) else []
    payload = {
        "dataset": dataset,
        "schema_kind": kind,
        "available": kind == "v2" and isinstance(doc, dict),
        "rows": rows,
        "count": len(rows),
        "data_dir": str(base),
        "generated_at": doc.get("generated_at") if isinstance(doc, dict) else None,
    }
    if kind != "v2":
        payload["message"] = "v1 契约没有 " + name + " 表；该表只存在于 v2 数据集。"
    elif not payload["available"]:
        payload["message"] = "尚无 v2 数据：" + (reason or "index.json 缺失")
    return payload


def _v3_decision(index_doc):
    panels = index_doc.get("panels") if isinstance(index_doc, dict) else None
    decision = panels.get("decision") if isinstance(panels, dict) else None
    return decision if isinstance(decision, dict) else {}


def fixed_eval_payload(dataset=None):
    """GET /api/nyc/fixed_eval：v2/v3 的固定配置评价表（冻结选择后在独立时间块×重复上评价）。"""
    key = dataset_name(dataset)
    doc, base, reason, kind = _load_index(key)
    kind = kind or key
    if kind == "v3":
        decision = _v3_decision(doc)
        rows = decision.get("fixed_eval")
        rows = rows if isinstance(rows, list) else []
        available = isinstance(doc, dict)
        return {
            "dataset": key,
            "schema_kind": kind,
            "available": available,
            "rows": rows,
            "count": len(rows),
            "data_dir": str(base),
            "generated_at": doc.get("generated_at") if isinstance(doc, dict) else None,
            "note": ("fixed_config_eval（v3）：把选择阶段得到的 n 冻结后，在独立时间块×独立重复上评价；"
                     "含跨机制行（eval_mechanism × n_source_mechanism）、登记充电位 registered_ev_bays "
                     "与 n=0 基线 J_mean_at_0；block_id 与 n_worlds 必须随行展示。"),
        } if available else {
            "dataset": key, "schema_kind": kind, "available": False, "rows": [],
            "count": 0, "data_dir": str(base), "generated_at": None,
            "message": "尚无 v3 数据：" + (reason or "index.json 缺失"),
        }
    payload = _v2_section(key, doc, base, reason, kind, "fixed_eval")
    if payload["available"]:
        payload["note"] = ("fixed_config_eval：把选择阶段得到的 n 冻结后，在独立时间块×独立重复上评价；"
                           "block_id 与 n_worlds 必须随行展示。")
    return payload


def robust_payload(dataset=None):
    """GET /api/nyc/robust：v2 的稳健配置表，robust_A 与 robust_B 分开返回、分开命名。"""
    key = dataset_name(dataset)
    doc, base, reason, kind = _load_index(key)
    kind = kind or key
    if kind == "v3":
        decision = _v3_decision(doc)
        raw_rows = decision.get("robust")
        raw_rows = raw_rows if isinstance(raw_rows, list) else []
        available = isinstance(doc, dict)
        payload = {
            "dataset": key, "schema_kind": kind, "available": available,
            "rows": [], "count": 0, "data_dir": str(base),
            "generated_at": doc.get("generated_at") if isinstance(doc, dict) else None,
        }
        if doc is None:
            payload["message"] = "尚无 v3 数据：" + (reason or "index.json 缺失")
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            if item.get("object") in ("A", "B"):
                item["object_raw"] = item["object"]
                item["object"] = "robust_" + item["object"]
            payload["rows"].append(item)
        payload["count"] = len(payload["rows"])
    else:
        payload = _v2_section(key, doc, base, reason, kind, "robust")
    rows = payload["rows"]
    rows_a, rows_b = [], []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("object")
        if name == "robust_A" or (name is None and "n_robust" in row):
            rows_a.append(row)
        elif name == "robust_B" or (name is None and "n_robust_stress" in row):
            rows_b.append(row)
    payload["A"] = rows_a
    payload["B"] = rows_b
    payload["counts"] = {"A": len(rows_a), "B": len(rows_b)}
    payload["objects"] = {
        "A": {"name": "robust_A", "definition": "先对 ω 求期望，再对 φ/θ 取最坏（设计对象）"},
        "B": {"name": "robust_B", "definition": "对单次实现取最坏，单独命名（压力测试对象，不是设计选择）"},
    }
    if payload["available"]:
        payload["note"] = "robust_A 与 robust_B 是不同对象，不得合并展示或互相替代。"
    return payload
