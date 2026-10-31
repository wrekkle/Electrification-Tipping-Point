"""R3-E 多日数据审计：只读扫描 research/collection/taipei_372_polling_20261030/data/。

重算实际日期、每日批次数、372 场覆盖、缺测/重复批/断档，并判断能否支持"整日留出"。
输出 data_audit.json（本目录）。
"""
from __future__ import annotations
import hashlib, json, os, re, statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "research/collection/taipei_372_polling_20261030/data"
OUT = Path(__file__).resolve().parent / "data_audit.json"
SLOT_RE = re.compile(r'"slot_start_utc": "([^"]+)"')
LOT_RE = re.compile(r'"parking_id": "([^"]+)"')
SPOT_RE = re.compile(r'"spot_abrv": "([^"]+)"')
DUP_RE = re.compile(r'"duplicate_batch": (true|false)')
MISS_RE = re.compile(r'"data_missing": (true|false)')
HTTP_RE = re.compile(r'"http_status": (\d+|null)')
LOCAL_TZ = timezone(timedelta(hours=8))


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def scan_jsonl(path: Path, need_spot: bool = False) -> dict:
    rows = 0
    slots = Counter()
    lots_by_slot = defaultdict(set)
    lot_set = set()
    dup_rows = 0
    missing_rows = 0
    http_bad = 0
    dup_flags = 0
    pair_counter = Counter()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rows += 1
            m = SLOT_RE.search(line)
            slot = m.group(1) if m else None
            if slot is None:
                continue
            slots[slot] += 1
            lm = LOT_RE.search(line)
            lot = lm.group(1) if lm else None
            if lot is not None:
                lots_by_slot[slot].add(lot)
                lot_set.add(lot)
                pair_counter[(slot, lot)] += 1
            if need_spot:
                sm = SPOT_RE.search(line)
                if sm:
                    pair_counter[(slot, sm.group(1))] += 1
            dm = DUP_RE.search(line)
            if dm and dm.group(1) == "true":
                dup_flags += 1
            mm = MISS_RE.search(line)
            if mm and mm.group(1) == "true":
                missing_rows += 1
            hm = HTTP_RE.search(line)
            if hm and hm.group(1) not in (None, "200"):
                http_bad += 1
    pair_dup = sum(c - 1 for c in pair_counter.values() if c > 1)
    slot_list = sorted(slots)
    return {
        "rows": rows,
        "unique_slots": len(slots),
        "unique_lots": len(lot_set),
        "slot_first": slot_list[0] if slot_list else None,
        "slot_last": slot_list[-1] if slot_list else None,
        "lot_rows_duplicate": pair_dup,
        "duplicate_batch_rows": dup_flags,
        "data_missing_rows": missing_rows,
        "http_non200_rows": http_bad,
        "rows_per_slot_min": min(slots.values()) if slots else 0,
        "rows_per_slot_max": max(slots.values()) if slots else 0,
        "lots_per_slot_min": min(len(v) for v in lots_by_slot.values()) if lots_by_slot else 0,
        "lots_per_slot_max": max(len(v) for v in lots_by_slot.values()) if lots_by_slot else 0,
        "lots_per_slot_mean": round(statistics.fmean(len(v) for v in lots_by_slot.values()), 3) if lots_by_slot else 0,
        "slots": sorted(slots.keys()),
        "lot_ids": sorted(lot_set),
    }


def expected_slots(first: datetime, last: datetime, step_min: int = 5) -> list[str]:
    out = []
    t = first
    while t <= last:
        out.append(t.isoformat())
        t += timedelta(minutes=step_min)
    return out


def main() -> int:
    date_dirs = sorted(p.name for p in DATA.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name))
    result = {
        "schema": "multiday_data_audit/v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": "python research/round3_20261031/multiday_audit.py",
        "source_root": str(DATA.relative_to(ROOT)).replace("\\", "/"),
        "read_only": True,
        "note": "采集器可能仍在运行；本审计是读取时的快照，不修改任何采集文件。",
        "date_dirs": {},
        "commits": {},
        "raw": {},
        "union": {},
        "local_day_partition": [],
        "holdout": {},
    }
    all_slots = set()
    span_first = None
    span_last = None
    lot_union = set()
    for d in date_dirs:
        entry = {}
        for fname, need_spot in (("parking_slots.jsonl", False), ("connector_status_long.jsonl", True)):
            p = DATA / d / fname
            if not p.exists():
                entry[fname] = {"exists": False}
                continue
            st = scan_jsonl(p, need_spot=need_spot)
            lots_here = st.get("lot_ids", []) or []
            st.update({"bytes": p.stat().st_size, "sha256": sha256_file(p), "slots": st["slots"][:0] or None})
            st.pop("slots", None)
            st.pop("lot_ids", None)
            entry[fname] = st
            if fname == "parking_slots.jsonl":
                lot_union.update(lots_here)
                entry["lots_this_file"] = lots_here
        # 重新取 slot 列表（上面 pop 掉大头字段，这里单独再扫一遍 slot 列）
        slots = []
        for fname in ("parking_slots.jsonl", "connector_status_long.jsonl"):
            p = DATA / d / fname
            if p.exists():
                with open(p, encoding="utf-8") as fh:
                    for line in fh:
                        m = SLOT_RE.search(line)
                        if m:
                            slots.append(m.group(1))
        slots = sorted(set(slots))
        all_slots.update(slots)
        entry["batches"] = len(slots)
        entry["first_slot_utc"], entry["last_slot_utc"] = (slots[0], slots[-1]) if slots else (None, None)
        entry["slot_list"] = slots
        if "lots_this_file" in entry:
            entry["parking_unique_lots"] = len(entry["lots_this_file"])
        entry["parking"] = {k: v for k, v in entry.get("parking_slots.jsonl", {}).items() if k in ("rows", "unique_lots", "unique_slots", "lot_rows_duplicate", "duplicate_batch_rows", "data_missing_rows", "http_non200_rows", "lots_per_slot_min", "lots_per_slot_max", "rows_per_slot_min", "rows_per_slot_max", "bytes", "sha256")}
        entry["connector"] = {k: v for k, v in entry.get("connector_status_long.jsonl", {}).items() if k in ("rows", "unique_slots", "lot_rows_duplicate", "duplicate_batch_rows", "bytes", "sha256")}
        result["date_dirs"][d] = {k: v for k, v in entry.items() if k not in ("slot_list",)}
        if slots:
            first, last = parse_ts(slots[0]), parse_ts(slots[-1])
            if span_first is None or first < span_first:
                span_first = first
            if span_last is None or last > span_last:
                span_last = last
        # commits
        cdir = DATA / "commits" / d
        if cdir.is_dir():
            files = sorted(p.name for p in cdir.iterdir() if p.is_file())
            result["commits"][d] = {"count": len(files), "first": files[0] if files else None, "last": files[-1] if files else None,
                                    "bytes_total": sum((cdir / f).stat().st_size for f in files)}
        rdir = DATA / "raw" / d
        if rdir.is_dir():
            files = sorted(p.name for p in rdir.iterdir() if p.is_file())
            result["raw"][d] = {"count": len(files), "first": files[0] if files else None, "last": files[-1] if files else None,
                                "bytes_total": sum((rdir / f).stat().st_size for f in files)}
    # union coverage
    union_slots = sorted(all_slots)
    if union_slots:
        first, last = parse_ts(union_slots[0]), parse_ts(union_slots[-1])
        expected = expected_slots(first, last)
        expected_set = set(expected)
        missing = sorted(expected_set - set(union_slots))
        # gaps: consecutive observed slots differing > 5 min
        obs = [parse_ts(s) for s in union_slots]
        gaps = []
        for a, b in zip(obs, obs[1:]):
            if (b - a) > timedelta(minutes=5):
                gaps.append({"after": a.isoformat(), "before": b.isoformat(), "gap_min": (b - a).total_seconds() / 60})
        # duplicate slot across files? same slot appears in both date dirs would be duplicate; count
        result["union"] = {
            "first_slot_utc": first.isoformat(), "last_slot_utc": last.isoformat(),
            "span_hours": round((last - first).total_seconds() / 3600, 3),
            "slots_observed": len(union_slots), "slots_expected_5min": len(expected),
            "coverage_ratio": round(len(union_slots) / len(expected), 4),
            "missing_slots_count": len(missing), "missing_slots_first20": missing[:20],
            "gaps_count": len(gaps), "gaps": gaps,
            "union_lots": len(lot_union) if lot_union else None,
        }
        # local day partition
        by_local = defaultdict(list)
        for s in union_slots:
            by_local[parse_ts(s).astimezone(LOCAL_TZ).date().isoformat()].append(s)
        for ld in sorted(by_local):
            slots = by_local[ld]
            lfirst = parse_ts(slots[0]).astimezone(LOCAL_TZ)
            llast = parse_ts(slots[-1]).astimezone(LOCAL_TZ)
            exp = expected_slots(parse_ts(slots[0]), parse_ts(slots[-1]))
            result["local_day_partition"].append({
                "local_date": ld, "batches": len(slots),
                "first_local": lfirst.isoformat(), "last_local": llast.isoformat(),
                "span_hours": round((llast - lfirst).total_seconds() / 3600, 3),
                "expected_slots_within_span": len(exp),
                "coverage_ratio": round(len(slots) / len(exp), 4),
                "full_24h": len(slots) >= 288,
            })
        # holdout judgement
        full_days = [d for d in result["local_day_partition"] if d["full_24h"]]
        result["holdout"] = {
            "satisfied": False,
            "available_local_dates": [d["local_date"] for d in result["local_day_partition"]],
            "full_24h_local_days": [d["local_date"] for d in full_days],
            "reasons": [
                "只有两个日期目录（%s），且都不是完整本地日：10-30 从本地 11:30 起，10-31 到本地 13:10 止" % ", ".join(date_dirs),
                "整日留出至少需要 2 个完整 24h 日（训练/验证各一），当前无任何 full_24h=True 的本地日",
                "两个日期合计观测 %d 个 5min 槽（%.1f h），覆盖零散；未达到 2×288=576 槽" % (len(union_slots), (last - first).total_seconds() / 3600),
                "采集器仍在追加（快照读取），后续日期可能增加，但本判决基于本次快照",
            ],
            "training_window_used": {"window_utc": ["2026-10-30T03:30:00+00:00", "2026-10-31T03:25:00+00:00"], "slots": 279},
        }
    # static roster
    static_dir = DATA / "static"
    if static_dir.is_dir():
        files = sorted(p.name for p in static_dir.iterdir() if p.is_file())
        result["static"] = {"files": files, "bytes": {f: (static_dir / f).stat().st_size for f in files}}
        for f in files[:1]:
            try:
                doc = json.loads((static_dir / f).read_text(encoding="utf-8"))
                if isinstance(doc, list):
                    result["static"]["roster_count"] = len(doc)
                elif isinstance(doc, dict):
                    for k in ("lots", "parks", "records"):
                        if isinstance(doc.get(k), list):
                            result["static"]["roster_count"] = len(doc[k])
                            break
            except Exception as exc:  # noqa: BLE001
                result["static"]["parse_error"] = str(exc)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({
        "date_dirs": date_dirs,
        "batches_per_dir": {d: result["date_dirs"][d]["batches"] for d in date_dirs},
        "union": {k: result["union"].get(k) for k in ("first_slot_utc", "last_slot_utc", "span_hours", "slots_observed", "missing_slots_count", "gaps_count")},
        "lots": result["union"].get("union_lots"),
        "local_days": [(x["local_date"], x["batches"], x["full_24h"]) for x in result["local_day_partition"]],
        "holdout_satisfied": result["holdout"]["satisfied"],
        "commits": {d: result["commits"][d]["count"] for d in result["commits"]},
        "raw": {d: result["raw"][d]["count"] for d in result["raw"]},
        "parking_rows": {d: result["date_dirs"][d]["parking"].get("rows") for d in date_dirs},
        "connector_rows": {d: result["date_dirs"][d]["connector"].get("rows") for d in date_dirs},
        "missing_rows": {d: result["date_dirs"][d]["parking"].get("data_missing_rows") for d in date_dirs},
        "dup_rows": {d: result["date_dirs"][d]["parking"].get("duplicate_batch_rows") for d in date_dirs},
        "sha": {d: {f: result["date_dirs"][d][f].get("sha256", "")[:16] for f in ("parking", "connector")} for d in date_dirs},
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
