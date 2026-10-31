# -*- coding: utf-8 -*-
"""Round-4 independent acceptance.

Written by the Lead after implementation; it does not import the round-4 analysis helper
for its joint-k recomputation and it exercises the HTTP service over a real socket.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
R4 = ROOT / "research" / "round4_20261031"
RES = R4 / "results"
CATALOG = R4 / "charge_probability_sources.json"
ALPHA = 0.05
CHECKS = []


def check(name, fn):
    try:
        detail = fn()
        CHECKS.append({"name": name, "ok": True, "detail": detail})
        print("PASS", name, detail if isinstance(detail, (str, int, float)) else "")
    except Exception as exc:  # noqa: BLE001 - every failure must be listed
        CHECKS.append({"name": name, "ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})
        print("FAIL", name, type(exc).__name__, exc)


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def rates(row):
    sm = row.get("service_metrics") or {}
    r = sm.get("rates") or {}
    return {"capacity_only_unmet_rate": row.get("capacity_only_unmet_rate"),
            "ev_parking_failure_rate": r.get("ev_parking_failure_rate"),
            "ice_parking_failure_rate": r.get("ice_parking_failure_rate")}


def joint(by_k):
    for k in sorted(by_k):
        vals = rates(by_k[k])
        if all(v is None or v <= ALPHA + 1e-12 for v in vals.values()):
            return k
    return None


def group(rows):
    out = {}
    for row in rows:
        out.setdefault((row["lot_id"], int(row["seed"])), {})[int(row["k"])] = row
    return out


def curves_for(name, folder=None):
    doc = load((RES / folder / name) if folder else (RES / name))
    g = group(doc["rows"])
    return doc, g, {key: joint(by_k) for key, by_k in g.items()}


def check_catalog():
    from apps.parking_lab.workbench import charge_sources
    catalog_sha = __import__("hashlib").sha256(CATALOG.read_bytes()).hexdigest()
    ids = charge_sources.scenario_ids(CATALOG)
    assert "REF" in ids and "M08-NEAR-BEV" in ids and "M10-OUT-OF-HOME" in ids
    ref = charge_sources.resolve(CATALOG, "REF")
    assert abs(ref["p_ev"] - 0.10) < 1e-15 and abs(ref["q_need"] - 0.36) < 1e-15
    assert ref["provenance"]["identification_status"] == "historical_reference_not_identified"
    m08 = charge_sources.resolve(CATALOG, "M08-NEAR-BEV")
    assert m08["provenance"]["q_use_as_q_need"] is True
    assert m08["provenance"]["identification_status"] == "hypothetical_scenario_transfer_not_target_identified"
    assert abs(m08["q_need"] - 1421 / 4974) < 1e-12
    assert len(ref["provenance"]["record_sha256"]) == 64
    return {"scenarios": len(ids), "catalog_sha16": catalog_sha[:16]}


def check_runner_provenance():
    _, _, _ = curves_for("scenario_REF_A_s5.json")
    doc = load(RES / "scenario_REF_A_s5.json")
    from apps.parking_lab.workbench import charge_sources
    expected = charge_sources.resolve(CATALOG, "REF")["provenance"]
    assert len(doc["rows"]) == 1025
    assert doc["meta"]["charge_scenario"]["record_sha256"] == expected["record_sha256"]
    for row in doc["rows"][:50]:
        assert row["charge_scenario_id"] == "REF"
        assert abs(row["p_ev_used"] - 0.10) < 1e-15
        assert abs(row["q_need_used"] - 0.36) < 1e-15
        assert row["charge_provenance"]["catalog_sha256"] == expected["catalog_sha256"]
        assert row["charge_provenance"]["record_sha256"] == expected["record_sha256"]
    return {"rows": len(doc["rows"]), "record_sha16": expected["record_sha256"][:16]}


def check_scenario_deltas():
    scenarios = ["REF", "M08-NEAR-BEV", "M08-NEAR-COMBINED", "M10-OUT-OF-HOME", "M08-ALL-AWAY-REF"]
    analysis = load(RES / "analysis_round4.json")["scenario"]["scenarios"]
    summary = {}
    for sc in scenarios:
        _, _, ka = curves_for("scenario_%s_A_s5.json" % sc)
        out = {"A_achieved": sum(1 for v in ka.values() if v is not None)}
        for tag in ("B", "D"):
            _, _, kr = curves_for("scenario_%s_%s_s5.json" % (sc, tag))
            pairs = [ka[key] - kr[key] for key in ka if ka[key] is not None and kr.get(key) is not None]
            assert pairs, (sc, tag)
            assert min(pairs) >= 0, (sc, tag, min(pairs))
            assert all(d == 0 for d in pairs), (sc, tag, sorted(set(pairs)))
            out[tag] = {"pairs": len(pairs), "positive": sum(1 for d in pairs if d > 0),
                        "zero": sum(1 for d in pairs if d == 0), "negative": sum(1 for d in pairs if d < 0)}
            assert analysis[sc]["delta"][tag]["pairs"] == len(pairs)
            assert analysis[sc]["delta"][tag]["median"] == 0
        summary[sc] = out
    return summary


def check_fixedk_leakage_and_analysis():
    manifest = load(RES / "fixedk" / "fixedk_manifest.json")
    assert set(manifest["selection_seeds"]).isdisjoint(manifest["evaluation_seeds"])
    runs = manifest["runs"]
    assert runs
    for run in runs:
        assert run["exit"] == 0, run
        doc = load(run["out"])
        seeds = {int(row["seed"]) for row in doc["rows"]}
        assert seeds <= set(manifest["evaluation_seeds"]), (run["out"], seeds)
        assert all(int(row["k"]) == int(run["k"]) for row in doc["rows"])
    analysis = load(RES / "analysis_round4.json")["fixedk"]
    own = {}
    for rule in ("A", "B", "D"):
        rows = []
        for run in runs:
            if run["mode"] != "own" or run["rule"] != rule:
                continue
            rows.extend(load(run["out"])["rows"])
        own[rule] = {"cells": len(rows),
                     "feasible": sum(1 for r in rows if all(v is None or v <= ALPHA + 1e-12
                                                          for v in rates(r).values()))}
        assert own[rule]["cells"] == analysis["own"][rule]["cells"]
        assert own[rule]["feasible"] == analysis["own"][rule]["feasible"]
    assert analysis["own"]["B"]["feasible"] < analysis["own"]["A"]["feasible"]
    common = analysis["common"]
    assert common["B"]["same_k_cells"] == common["B"]["cells"]
    assert common["B"]["mean_diff"]["capacity_only_unmet_rate"] > 0
    assert common["D"]["mean_diff"]["capacity_only_unmet_rate"] > 0
    return {"own": own, "common_B_capacity_diff": common["B"]["mean_diff"]["capacity_only_unmet_rate"]}


def check_dwell():
    analysis = load(RES / "analysis_round4.json")["dwell"]
    out = {}
    for scale in ("0.8", "1.0", "1.2"):
        _, _, ka = curves_for("dwell_%s_A_s3.json" % scale, "dwell")
        out[scale] = {}
        for tag in ("B", "D"):
            doc = load(RES / "dwell" / ("dwell_%s_%s_s3.json" % (scale, tag)))
            assert abs(float(doc["meta"].get("dwell_scale") or 1.0) - float(scale)) < 1e-12
            _, _, kr = curves_for("dwell_%s_%s_s3.json" % (scale, tag), "dwell")
            pairs = [ka[k] - kr[k] for k in ka if ka[k] is not None and kr.get(k) is not None]
            assert pairs and all(d == 0 for d in pairs), (scale, tag, sorted(set(pairs)))
            out[scale][tag] = len(pairs)
    return out


def check_tradeoff():
    doc = load(RES / "tradeoff_fixedk.json")
    assert len(doc["cells"]) == 12
    assert len(doc["configs"]) == 34
    assert set(doc["dominates_A"]).issubset({i for i in doc["configs"] if i.startswith("C_")})
    assert doc["ev_first_selection"] in doc["configs"]
    assert doc["A"]["ice_parking_failure_rate"] > 0
    # No configuration may claim a smaller k: the file only contains fixed-k service runs.
    assert "k_saving" not in doc and "delta_k" not in doc
    return {"cells": len(doc["cells"]), "configs": len(doc["configs"]),
            "ev_first": doc["ev_first_selection"], "dominates_A": doc["dominates_A"]}


def check_data_audit():
    doc = load(R4 / "data_trace.json")
    checks = doc.get("checks") or []
    assert len(checks) == 20, len(checks)
    counts = {status: sum(1 for c in checks if c.get("status") == status)
              for status in ("pass", "unverified", "fail")}
    assert counts == {"pass": 19, "unverified": 1, "fail": 0}, counts
    assert any(c.get("id") == "C06" and c.get("status") == "pass" for c in checks)
    assert (R4 / "WIRING.md").exists()
    assert (R4 / "lit" / "round3_claims_audit.md").exists()
    assert (R4 / "mechanism" / "shared_capacity_mechanism.json").exists()
    return {"data_trace_size": (R4 / "data_trace.json").stat().st_size, "checks": counts}


def check_atomic_write():
    from apps.parking_lab.workbench.experiments import write_output
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "run1")
        write_output(target, {"a": 1})
        assert os.path.exists(os.path.join(target, "result.json"))
        assert not [n for n in os.listdir(target) if n.endswith(".tmp")]
        try:
            write_output(target, {"a": 2})
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing output directory was overwritten")
        bad = os.path.join(tmp, "run2")
        try:
            write_output(bad, {"x": float("nan")})
        except ValueError:
            pass
        else:
            raise AssertionError("NaN payload was accepted")
        assert not os.path.exists(os.path.join(bad, "result.json"))
        assert (not os.path.exists(bad)) or not os.listdir(bad)
    return "atomic+no-temp+no-overwrite"


def check_http_guard():
    from apps.parking_lab.workbench import server as server_mod
    server = server_mod.make_server(0)
    port = server.server_port
    assert server.server_address[0] == "127.0.0.1"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def request(method, path, body=None, headers=None):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            data = response.read()
            status = response.status
            conn.close()
            return status, data

        status, _ = request("GET", "/api/health")
        assert status == 200, status
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.putrequest("GET", "/api/health", skip_host=True)
        conn.putheader("Host", "evil.example")
        conn.endheaders()
        assert conn.getresponse().status == 403
        conn.close()
        status, _ = request("POST", "/api/validate", body=json.dumps({"config": {}}),
                            headers={"Origin": "http://evil.example", "Content-Type": "application/json"})
        assert status == 403, status
        status, _ = request("GET", "/../README.md")
        assert status == 404, status
        status, _ = request("POST", "/api/validate", body=b'{"config":{"seed":NaN}}',
                            headers={"Content-Type": "application/json"})
        assert status == 400, status
        big = b"{" + b" " * 131072 + b"}"
        status, _ = request("POST", "/api/validate", body=big, headers={"Content-Type": "application/json"})
        assert status == 413, status
        raw = socket.create_connection(("127.0.0.1", port), timeout=5)
        raw.sendall(("POST /api/validate HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
                     "Content-Length: 2\r\nContent-Length: 3\r\nConnection: close\r\n\r\n{}" % port).encode())
        line = raw.recv(200).decode("latin-1").split("\r\n", 1)[0]
        raw.close()
        assert " 400 " in line, line
    finally:
        server.shutdown()
        server.server_close()
    return "bind/Host/Origin/traversal/NaN/size/duplicate-CL"


def check_frozen_and_hashes():
    expected = {
        "research/traffic_generation_20261031/fitted_parameters.json": "1dfc14a2",
        "research/integer_allocation_20261031/outputs/cost_curve_pi0_k40.json": "3d77f693",
        "research/calibration/charging_probability_20261030/model_20261031.json": "75c4f034",
        "research/round2_20261031/results/analysis_v2_all.json": "00ec8cdc",
    }
    import hashlib
    out = {}
    for rel, prefix in expected.items():
        path = ROOT / rel
        if not path.exists():
            raise AssertionError("missing frozen file " + rel)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest.startswith(prefix), (rel, digest)
        out[rel] = digest[:16]
    return out


def check_docs():
    report = ROOT / "docs" / "reports" / "2026-10-31-第四轮数据接线与机制审查.md"
    assert report.exists(), report
    body = report.read_text(encoding="utf-8")
    for token in ("共享", "固定 k", "来源情景", "安全"):
        assert token in body, token
    limits = {"docs/PROGRESS.md": 3200, "docs/TODO.md": 8000, "docs/methods/COST-MODEL-V2.md": 3200}
    for rel, cap in limits.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert len(text) <= cap, (rel, len(text), cap)
    return {"report_chars": len(body)}


def main():
    check("catalog", check_catalog)
    check("runner_provenance", check_runner_provenance)
    check("scenario_deltas", check_scenario_deltas)
    check("fixedk_leakage", check_fixedk_leakage_and_analysis)
    check("dwell", check_dwell)
    check("tradeoff", check_tradeoff)
    check("data_audit", check_data_audit)
    check("atomic_write", check_atomic_write)
    check("http_guard", check_http_guard)
    check("frozen_hashes", check_frozen_and_hashes)
    check("docs", check_docs)
    payload = {"checks": CHECKS, "passed": sum(1 for c in CHECKS if c["ok"]), "total": len(CHECKS)}
    out = R4 / "verify_round4_report.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "total": payload["total"]}, ensure_ascii=False))
    return 0 if payload["passed"] == payload["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
