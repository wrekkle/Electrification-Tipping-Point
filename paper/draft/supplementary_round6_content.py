# -*- coding: utf-8 -*-
"""Content of the round-6 supplementary file (S1-S6). Text only; tables come from tables_si.json."""

TITLE = ("Supplementary Notes: Minimum integer charging provision in mixed-fleet parking: joint service "
         "constraints, an identifiability boundary, and conditional evidence on shared use and a "
         "charging-intention signal")

SUBTITLE = ("Round-6 working supplement, 2026-10-31. This file is separate from the manuscript; the main text "
            "refers to Supplementary Notes S1-S6. Numbers are recomputed from the stored machine records named "
            "in the audit note S6, and no result in this file is a field measurement.")

SECTIONS = [
{"title": "S1 Semantics of a rate and the five states",
 "blocks": [
  ("p", "A service rate in this project is a fraction whose denominator is a count of events of one kind in a "
        "fixed window. The records distinguish five states for every rate and every grid point: valid, when the "
        "denominator is positive and the record carries a computed value; not applicable, when the scenario has no "
        "event of the kind the rate refers to, so the denominator is zero; censored, when the window closes before "
        "the event that would decide the outcome, which happens for the energy shortfall rate when a charging "
        "session has not departed; missing, when the record should carry a value and does not; and illegal, when "
        "the stored value contradicts its denominator. The paper treats only valid values as evidence, and it "
        "states which convention it uses at each place where a zero denominator appears."),
  ("p", "Two conventions are reported side by side. The inclusive convention, which is the pre-registered one and "
        "the one the submitted model used, skips a rate whose denominator is zero because the scenario has no "
        "vehicle of that class and lets the remaining constraints decide. The strict convention requires every rate "
        "to be valid and at or below the tolerance, so a zero-demand scenario cannot be admissible on a rate that "
        "was never evaluated. The two conventions differ in 15 of the 975 joint units, and the difference is a "
        "change of convention rather than the effect of a repair."),
  ("caption", "Table S1 Admissible joint units under five rate conventions."),
  ("table", "S1"),
  ("note", "S1"),
  ("p", "The earlier convention that skipped every zero denominator is kept as a fourth reading because it was used "
        "in an earlier round; it leaves 310 units, the five-state strict reading leaves 51, and neither is a "
        "recomputation of the other. The energy shortfall rate stays auxiliary and censored: a group with a "
        "charging request and no departure inside the window is neither a success nor a failure, and it is "
        "counted rather than scored."),
 ]},
{"title": "S2 A restricted monotonicity proposition and its proof",
 "blocks": [
  ("p", 'The proposition below is the only general statement the paper makes about the direction in which the ICEV failure count moves with the number of equipped bays. It holds in a restricted no-fallback variant, not in the model that produces the traces of the main text, where the direction can be reversed. The enumeration reported in the main text is a consistent supporting check; the proof is here.'),
  ("p", 'Setting. A lot has N bays. Increasing the count from k to k+1 converts one bay from an ordinary into an equipped bay, so the number of ordinary bays falls from m = N-k to m-1. The argument below counts occupied ordinary bays and never refers to which bay is which.'),
  ("p", 'Assumptions.'),
  ("p", 'A1. N is fixed and 0 <= k < k+1 <= N; the two systems differ only in the number of ordinary bays, m and m-1, and in the corresponding number of equipped bays.'),
  ("p", 'A2. Strict no-fallback: an EV uses only an equipped bay and an ICEV only an ordinary bay; no vehicle changes class, and a charging EV never occupies an ordinary bay.'),
  ("p", 'A3. Loss system: no queueing, no relocation, no reservation and no preemption; an arrival that finds no compatible free bay leaves at once and is counted as failed.'),
  ("p", 'A4. Same exogenous arrival sequence in both systems: arrival times, classes and dwell times are identical, a departure occurs at arrival plus dwell, and charging energy or power does not affect ordinary-bay occupancy.'),
  ("p", 'A5. An arrival is admitted exactly when a compatible free bay exists; which free bay is chosen does not affect admission; the order of simultaneous events is the same in both systems. The proof does not use any smallest-index or first-fit rule.'),
  ("p", 'A6. The failure rate denominator is the number of ICEV arrivals, which does not depend on k; the statement is about one trajectory, not about a distribution over demands.'),
  ("p", 'Proposition 1. Under A1-A6, for the same arrival stream the set of failed ICEVs at k is contained in the set at k+1, so the ICEV failure count and the ICEV failure rate are non-decreasing in k.'),
  ("p", 'Proof. By A2 the EV never enters an ordinary bay, so each system reduces to a single-class loss system on its ordinary bays, and by A4 and A5 the two systems process the same ICEV arrivals with the same dwell times. Just before an event, let a be the number of ICEVs occupying ordinary bays in S_k, which has m ordinary bays, and b the same count in S_k+1, which has m-1. The proof keeps the single invariant 0 <= a-b <= 1; both systems start empty, so it holds initially.'),
  ("p", 'Departure. A4 and A5 give the same departing vehicles in both systems and the same order. A vehicle admitted in both systems decrements a and b, leaving the difference unchanged. A vehicle admitted only in S_k decrements a alone; because it is counted in a and not in b, the invariant gives a-b = 1 before the departure and 0 after it. A vehicle admitted only in S_k+1 does not exist, as the arrival case shows. Hence every departure preserves the invariant.'),
  ("p", 'Arrival. S_k admits the ICEV exactly when a < m, and S_k+1 exactly when b < m-1. If both admit or both refuse, the difference is unchanged. If S_k admits and S_k+1 refuses, then b = m-1, and a-b <= 1 gives a <= m; together with a < m this gives a <= m-1, so a = b = m-1 and the difference becomes 1 after a increments. If S_k refuses and S_k+1 admits, then a = m and b <= m-2, while a-b <= 1 gives b >= m-1, a contradiction; so this case cannot occur. Hence the invariant holds after every arrival, and no ICEV is ever admitted in S_k+1 and refused in S_k.'),
  ("p", 'Conclusion. If S_k+1 admits an ICEV then b <= m-2, so a <= b+1 <= m-1 < m and S_k admits it as well. Therefore every ICEV that parks in S_k+1 also parks in S_k, fail(k) is contained in fail(k+1), and by A6 the fixed denominator makes the count and the rate non-decreasing in k. QED'),
  ("p", 'Why the earlier argument fails. An earlier draft justified the statement by a mirror coupling that assumed the same ordinary bay b to be occupied at the same time in the systems with k and k+1 equipped bays. That assumption is false. Take n = 4 and k = 0 -> 1, with two ICEVs arriving one after the other and dwell 10 each: in the first system they park in bays 0 and 1, in the second system in bays 1 and 2, so after the first arrival bay 1 is free in one system and occupied in the other. A second attempt replaced the same-bay identity by a dominance of the sorted occupancy vectors, which is also not preserved: with m = 5, one system occupying {0,1,2} and the other {1,3} keeps the sorted dominance but reverses the identity of the smallest free bay. The correct argument needs no bay-level matching at all, only the count difference a-b above.'),
  ("p", 'What the enumeration supports. The strict implementation was run over 3,456 grid instances with no violation, and 12,000 randomly drawn small sequential streams also produced none, while the same check reproduces the same-bay counterexample above. The base model with an EV fallback is a different system and does show decreases, 16 of them in the stored set, so the proposition is not a property of the full model. The enumeration is consistent with the proposition but is not a substitute for the proof, and the paper claims no novelty for the argument.'),
 ]},
{"title": "S3 The three minimal traces, their controls and the counterexample set",
 "blocks": [
  ("p", "The three traces replay the mechanism model in the event simulator under three configurations: E1 with "
        "n = 6, seed 1, k = 0 -> 1; E2 with n = 8, seed 5, k = 5 -> 6; and E3 with n = 8, seed 3, k = 2 -> 3. In "
        "each of them the counted ICEV failures fall by one when the equipped count increases by one, while the "
        "EV failures rise in E1 and E3 and stay flat in E2. The traces are synthetic configurations of the "
        "mechanism model, replayed to explain an observed non-monotonicity; they are not field measurements."),
  ("pagebreak", ""),
  ("caption", "Table S3a Trace E1, event by event, at k = 0 and k = 1."),
  ("table", "S3a"),
  ("note", "S3a"),
  ("p", "The control variants recompute the same traces after one change at a time: removing the EV fallback to an "
        "ordinary bay, reversing the bay order, shortening dwell times by 20%, lengthening them by 20%, imposing an "
        "initial occupancy, and reversing the order of simultaneous events. The decrease survives only in the "
        "lengthened-dwell variant for E1 and in the simultaneous-order variant for all three; it disappears in "
        "every other combination, which is why the paper keeps the observation inside those conditions."),
  ("caption", "Table S3b Control variants applied to the three minimal traces."),
  ("table", "S3b"),
  ("note", "S3b"),
  ("p", "The stored counterexamples are 16 instances of the base model in which one extra equipped bay lowers ICEV "
        "failures while the grid sweep of 3,456 instances contains no violation under the strict no-fallback "
        "implementation and none under the reversed bay order. All 16 involve the EV fallback to an ordinary bay, "
        "which identifies the mechanism: with the fallback the extra equipped bay changes where an EV parks and "
        "releases an ordinary bay later in the sequence, and without it that channel is closed."),
 ]},
{"title": "S4 The information-condition comparison, unit by unit",
 "blocks": [
  ("p", "The comparison covers two lots (TPE0008, TPE0401), two seeds, two rules (the dedicated rule and one shared "
        "rule) and the complete integer grid up to the rule-specific maximum, 656 simulations in all, with no "
        "failed run. Within each lot and seed the exogenous demand is identical under the two conditions, which is "
        "checked by comparing the stored demand hashes."),
  ("p", "The I1 policy tested here is one implementation and not a solution concept. Under I1 the rule reads one "
        "additional field, the charging intention of the vehicle arriving now, and acts as follows: a charging "
        "arrival is offered an equipped bay first, a non-charging arrival an ordinary bay first, and an ICEV "
        "follows the rule it had under I0. Nothing else changes: no future arrivals, no departure times and no "
        "energy are read, and the analysis-only grant lists the permitted field explicitly."),
  ("p", "Three checks support the claim that the two conditions differ only through that field. An I0 policy is "
        "available under both conditions, so the best attainable value under I1 cannot be worse by construction. "
        "The I1 policy can be made to reproduce I0 exactly, and the reproduction is validated on the same runs. A "
        "real-rule context that tries to read the intention raises a permission error instead of silently "
        "obtaining it, and no run in the comparison reads a forbidden field."),
  ("p", "The heuristic reaches a smaller minimal count in all eight paired units, by 2 to 17 equipped bays with a "
        "median of 9.5. It is not uniformly better: at the count selected under I0 two of the eight cells remain "
        "admissible only without the signal, because the ICEV parking failure rate rises to 7.69% and 17.82% "
        "there, and over the fixed-k cells the four categories are 143 admissible under both conditions, 26 only "
        "under I0, 61 only under I1 and 98 neither."),
  ("caption", "Table S4 Paired comparison of the two information conditions, one row per unit."),
  ("table", "S4"),
  ("note", "S4"),
  ("p", "The selected-count reduction is an algorithmic result about two implemented policies. It is not an "
        "estimate of the value of information, which would require optima under both conditions, and it is not "
        "evidence that information saves equipment in general."),
 ]},
{"title": "S5 The feasible-configuration experiment and its edge cases",
 "blocks": [
  ("p", "The third experiment treats the admissible set as the object. Each group is a lot, seed, rule and scenario, "
        "and the grid runs over the complete integers from 0 to the rule maximum, 660 groups in all. Within the "
        "enumerated range 0-40 every non-empty set is a contiguous interval and no group produced a set with "
        "holes. The empty sets are the exception: 124 groups have no admissible count under the inclusive "
        "convention and 139 under the strict one, and the difference of 15 groups is the one that the zero-demand "
        "convention decides. A further 437 sets still contain the range edge, so they are truncated rather than "
        "infeasible, and the paper reports the smallest known admissible count for them."),
  ("p", "Over the 840 rule pairs, the two rules are both admissible in 677, only the first in 7, only the second in "
        "4 and neither in 152; admissibility is restored in 4 pairs and the minimal count is strictly smaller in "
        "2; service at a common k improves in 4 pairs and worsens in 6; and 5 pairs are admissible under both "
        "rules with disjoint sets. The rows of the main table separate the comparison types: only the rows that "
        "compare the dedicated rule with a shared rule speak to substitution, and in those rows the shared rule "
        "never restores admissibility and never lowers the minimal count."),
  ("p", "The two smaller counts come from two pairwise comparisons on one lot-seed group, scenario REF, lot "
        "TPE1376, seed 10. The forecast-gated shared rule is admissible from k = 2 onward, while the other two "
        "shared rules need k = 24; the dedicated rule is admissible from k = 2 as well, so this group shows no "
        "saving from sharing either. The cells are allocation-order effects between shared rules at the same "
        "information condition."),
  ("caption", "Table S5a Admissible counts for the four rules in scenario REF, lot TPE1376, seed 10."),
  ("table", "S5a"),
  ("note", "S5a"),
  ("caption", "Table S5b The two pairwise comparisons that produce the smaller counts."),
  ("table", "S5b"),
  ("note", "S5b"),
  ("p", "One lot illustrates why the boundary matters. For TPE0330 the curves exist only over a narrow range "
        "inside the grid, and an expansion of the search to 200 places the first admissible counts between 52 and "
        "84. Those values are reported as budget truncation and are not merged into the 660 groups; the grid "
        "results for that lot are written as the smallest known admissible counts."),
 ]},
{"title": "S6 Audit record",
 "blocks": [
  ("p", "The manuscript in this round is a new file; the previous working draft and the frozen submission file are "
        "read-only and their bytes are unchanged. The table below records the artifacts and the input hashes; the "
        "commands, interpreters and exit codes are listed in the run log of the round."),
  ("pagebreak", ""),
  ("caption", "Table S6 Artifacts and input hashes behind this round."),
  ("table", "S6"),
  ("note", "S6"),
  ("p", "Commands used for this round, all with exit code 0 unless noted: the builder for the manuscript "
        "(build_paper_v3_round6_rev2.py --force), the statistics script on the new manuscript, the table "
        "generators for the main text and for this supplement, the Word export of both files to PDF, and a "
        "page-level render check that extracts every page as an image and records blank pages, caption placement "
        "and table spans. Interpreters: the workspace Python for document work and the Word application for the "
        "export."),
  ("p", "Citation check: the manuscript cites 76 of its 76 listed references and lists no reference that is never "
        "cited, with no number outside the range. Pending production strings are zero. The residual limits of the "
        "round are listed in the main text and in the run log: no pixel-level comparison against a journal "
        "template, the author list of one reference still incomplete, and the appendix of one reference not "
        "obtained."),
 ]},
]
