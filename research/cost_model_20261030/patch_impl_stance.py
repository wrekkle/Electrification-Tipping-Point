# -*- coding: utf-8 -*-
"""Rewrite the cost-framework paragraphs to the frozen implementation stance (T22 item 9).

Idempotent: every target line is found by a unique prefix of the existing node text.
"""
import json
import py_compile

PATH = "paper/draft/paper_v2_content.py"

A = ("Occupancy of a charging bay without a charging vehicle has more than one cause, and the causes are "
     "not interchangeable. We distinguish five: no charging demand, where an EV takes the bay and does not "
     "plug in; overstay after completion, the case studied by Biswas et al. {BISWAS16}; a deferral by the "
     "dispatch rule, where a vehicle is admitted and held without supply; insufficient power, where the device "
     "cannot deliver the requested energy at the rated level; and equipment failure. A release returns four "
     "resources, and they are recorded one by one instead of being collapsed into a single occupancy flag: "
     "power that can be reallocated, power_released, in kW; a connector that becomes free, connector_released; "
     "the charging bay itself, charged_bay_released; and, when the vehicle is moved, the ordinary bay it then "
     "occupies, ordinary_bay_released. Releasing a charged vehicle is conditional. The vehicle is moved only "
     "when an ordinary bay is free at that moment, it keeps its original departure time, it continues to "
     "occupy that ordinary bay, and it is not recorded as a departure and does not create a failure cost row; "
     "what the move returns is charging-side capacity. When no ordinary bay is free, nothing is moved and "
     "nothing is released, and the run reports the intervention as not implemented under the code "
     "no_ordinary_bay with null totals rather than reporting a zero difference. A move also carries a cost of "
     "its own, and that cost is not identified from a local source: with no value for the cost per move, the "
     "relocation item and the resulting difference are null and the parameter is listed as missing. A "
     "difference computed with a missing or zero move cost describes an idealised intervention, not a policy "
     "this lot could operate, and it is not reported as a feasible benefit.")

B = ("Both runs replay the same exogenous arrivals, vehicle mix, charging requests and dwell times and differ "
     "only in the decision taken for the stretch under study. A common random seed is not evidence that the "
     "two runs saw the same demand, so the implementation hashes the exogenous event stream generated up to "
     "the intervention and refuses to report a difference when the hashes disagree. The quantity is an "
     "attribution: it states how much of the gap between two designs is due to that occupancy, and it is "
     "reported beside the total rather than added to it. If the waiting, the detour and the unmet demand of "
     "later vehicles already sit inside the total, a separate occupancy penalty would count the same loss a "
     "second time. The difference is null whenever a move is involved and its cost is unknown, and the number "
     "is also silent about the ranking of the five causes: each cause needs its own paired run, and "
     "comparisons across causes are not read off one intervention.")

D = ("When a vehicle does leave the lot with energy undelivered, the extra time and the detour needed to "
     "complete the charge elsewhere are unknown rather than zero: the driver's onward route and the queue at "
     "the substitute charger are not observed. Those items are therefore null, the total is reported as not "
     "computable, and the parameters are listed as missing. An empty queue inside this lot at the moment of "
     "departure is not evidence that the substitute charge took no extra time, and it does not license a zero "
     "for either term.")

C = ("Occupancy and charges accrue on the simulation clock, not on the planned stay. A vehicle still in the "
     "lot is counted up to the current simulation instant only, not for the remainder of the window and not "
     "for its planned dwell time; a value projected to the planned departure is stored as a forecast in a "
     "separate projected block, keeps the same item names, and is never summed into the realised total or into "
     "the attribution. Realtime operation advances one simulation step per clock tick, that is at 1x, "
     "whatever speed multiplier the configuration carries; the accelerated mode is the one that applies the "
     "chosen multiplier. Pausing, changing the multiplier or switching mode settles the interval that has "
     "already run before the change takes effect, and resuming does not back-fill the paused interval. The "
     "current runner is a finite-window run: it stops at the end of the window and makes no claim to generate "
     "an unbounded stream.")

E = ("Two further entries follow the same vocabulary. A charging EV that fails to find any admissible berth "
     "and abandons its activity carries ev_activity_loss, computed with the same parameter as "
     "ice_activity_loss; a charging failure keeps ev_residual_trip_loss, and no vehicle carries both, so the "
     "abandoned-activity loss is not charged twice. The maintenance entry is quoted per gun-equipped device "
     "day: maintenance_per_bay_day counts the devices that have a connector, that is the chargers, and is "
     "multiplied by the number of devices rather than by the number of physical bays they can reach. The cost "
     "block of the ledger and of the export also carries the projected block and the relocation record, "
     "relocation_cost, relocation_count and relocation_blocked, so that a counterfactual which could not move "
     "a vehicle is visible in the record instead of being inferred from a zero.")

REPLACE = [
    ('("p", "Occupancy of a charging bay without a charging vehicle', A),
    ('("p", "Both runs replay the same exogenous arrivals', B),
]
INSERT_BEFORE = [
    ('("p", "Parking failure is the case in which an ICEV', [D]),
    ('("p", "Table 12 lists the parameters of equations', [C, E]),
]


def node(text):
    return '  ("p", ' + json.dumps(text, ensure_ascii=False) + '),'


lines = open(PATH, encoding="utf-8").read().splitlines()
changed = 0
done = set()
for prefix, text in REPLACE:
    hits = [i for i, l in enumerate(lines) if prefix in l]
    if len(hits) != 1:
        raise SystemExit("replace prefix not unique: %r hits=%d" % (prefix, len(hits)))
    lines[hits[0]] = node(text)
    done.add(prefix)
    changed += 1
for prefix, texts in INSERT_BEFORE:
    hits = [i for i, l in enumerate(lines) if prefix in l]
    if len(hits) != 1:
        raise SystemExit("insert prefix not unique: %r hits=%d" % (prefix, len(hits)))
    lines[hits[0]:hits[0]] = [node(t) for t in texts]
    changed += len(texts)
open(PATH, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
py_compile.compile(PATH, doraise=True)
print("patched nodes:", changed)
