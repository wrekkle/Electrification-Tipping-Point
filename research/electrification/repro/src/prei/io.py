# -*- coding: utf-8 -*-
"""Deterministic CSV/JSON output, parameter snapshots and run hashes."""
from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
import os


def timestamp():
    return _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def run_id(seed, stamp=None):
    stamp = stamp or _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return "%s-seed%s" % (stamp, seed)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def _json_default(obj):
    import numpy as np
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError("not JSON serialisable: %r" % (type(obj),))


def write_json(path, payload):
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True,
                  default=_json_default)
        fh.write("\n")


def write_csv(path, rows, columns=None):
    ensure_dir(os.path.dirname(path) or ".")
    rows = list(rows)
    if columns is None:
        columns = list(rows[0].keys()) if rows else []
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _cell(row.get(k)) for k in columns})
    return path


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return "%.10g" % value
    if isinstance(value, (list, tuple)):
        return ";".join(str(x) for x in value)
    return value


def canonical_json(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=_json_default)


def content_hash(payload):
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def params_snapshot(config, resolved, seed, run_id_value):
    return {
        "schema_version": 1,
        "run_id": run_id_value,
        "timestamp": timestamp(),
        "seed": seed,
        "config_path": config.path,
        "sources": config.source_map(),
        "params": config.params,
        "resolved": resolved,
    }


def summary_payload(seed, run_id_value, runtime_s, counts, results, notes):
    return {
        "run_id": run_id_value,
        "seed": seed,
        "timestamp": timestamp(),
        "runtime_seconds": round(runtime_s, 3),
        "counts": counts,
        "results": results,
        "notes": notes,
    }
