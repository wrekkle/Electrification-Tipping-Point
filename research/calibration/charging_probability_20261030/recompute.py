"""Recompute cited event ratios; no inferred demand, fitting, or implicit writes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def calculate(evidence):
    rows = []
    for source in evidence["sources"]:
        for item in source.get("event_counts", []):
            numerator, denominator = item["charging_events"], item["parking_events"]
            if type(numerator) is not int or type(denominator) is not int:
                raise ValueError("Event counts must be integers")
            if not 0 <= numerator <= denominator or denominator <= 0:
                raise ValueError("Invalid event counts")
            rows.append({
                "source_id": source["id"], "context": item["context"],
                "charging_events": numerator, "parking_events": denominator,
                "probability": numerator / denominator,
                "percent": numerator / denominator * 100,
                "transcription_status": source["transcription_status"],
                "estimand": "observed charging use per parking event in source context",
                "global_default_approved": False,
                "latent_intent_identified": False,
            })
    return {"rows": rows, "selected_default": None,
            "note": "Ratios are source-context observations, not a pooled estimate. "
                    "Repeated drivers/sites prevent an iid-binomial confidence claim."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path,
                        default=Path(__file__).with_name("evidence.json"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    raw = args.evidence.read_bytes()
    result = calculate(json.loads(raw.decode("utf-8")))
    result["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(encoded)
    print(encoded)


if __name__ == "__main__":
    main()
