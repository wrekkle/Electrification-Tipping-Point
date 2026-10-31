
# -*- coding: utf-8 -*-
"""Round-7 rev4 builder, stage 2: wording changes and new evidence/historical notes.
Reads the stage-1 structural file and writes the final rev4.
"""
import os
from docx import Document

ROOT = r"C:\Projects\停车场充电桩优化方案"
SRC = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx")
STAGE1 = os.path.join(ROOT, "research", "manuscript_revision_20261031", "_rev4_stage1.docx")

doc = Document(STAGE1)
paras = list(doc.paragraphs)

def find(prefix, style=None):
    for p in paras:
        if p.text.strip().startswith(prefix) and (style is None or p.style.name == style):
            return p
    raise RuntimeError("not found: " + prefix)

def set_text(p, text):
    p.text = text

def remove(p):
    p._element.getparent().remove(p._element)

def add_para(segments, style=None, before=None, after=None):
    p = doc.add_paragraph(style=style)
    for text, sup in segments:
        r = p.add_run(text)
        if sup:
            r.font.superscript = True
    if before is not None:
        before._element.addprevious(p._element)
    elif after is not None:
        after._element.addnext(p._element)
    return p

# ---------- Abstract ----------
p = find("Public parking that serves both electric vehicles")
t = p.text
t = t.replace("in all eight tested units (median reduction 9.5 berths)",
              "in all eight tested lot-seed-rule units, which are four streams under two rules (median reduction 9.5 berths; the table defines the change as k(I1) - k(I0))")
t = t.replace("660 integer grids give only contiguous admissible sets",
              "660 lot-seed-rule-scenario groups give only contiguous admissible sets")
t = t.replace("and over 840 rule pairs no dedicated-versus-shared pair lowered the minimal count",
              "and over 840 rule pairs pooled across five scenarios no dedicated-versus-shared pair lowered the minimal count")
set_text(p, t)

# ---------- Results: Q1 proposition scope ----------
p = find("The controls separate the mechanism from the sample")
set_text(p, p.text.rstrip() + " The proposition is restricted to the no-fallback variant with assumptions A1-A6; it does not apply to the pi0 rule used in the main comparison, where an EV may fall back to an ordinary berth, and the paper does not export it to that model.")

# ---------- Results: Q2 ----------
p = find("Over 656 simulations covering two lots")
t = p.text
t = t.replace("in all eight paired units", "in all eight lot-seed-rule units (four streams, each under two rules)")
t = t.replace("two of the eight cells", "two rule-A cells on the two TPE0401 streams")
set_text(p, t)

p = find("Two properties of the comparison are not results")
set_text(p, "Three properties of the comparison are not results. Containment is one: a rule available under I0 is available under I1, so the best attainable value under I1 cannot be worse, and that is a property of how the two conditions are defined. The policies are the second: the I1 policy is one specific signal-aware heuristic that reads only the current arrival's charging intention, so the counts above compare two implemented policies and not two optima. The evidence design is the third: the eight units are four lot-seed streams under two rule labels, not eight independent replications, and no seed block is held out, so the comparison is exploratory rather than an independently evaluated effect. The reduction in the selected count is therefore what this heuristic extracts from the signal under the tested rules: an algorithmic comparison of two implemented policies, not an estimate of the value of information, which would require optima under both conditions, and not a statement that information saves equipment in general.")

p = find("Table 3 Smallest admissible integer count")
set_text(p, "Table 3 Smallest admissible integer count under the two information conditions. k is the smallest count at which the three service rates are at or below 5% over the complete grid; Change = k(I1) - k(I0), so a negative value means that I1 reaches the standard with fewer equipped berths. Rows are four lot-seed streams; A and B give the same minimum on each stream, so each row represents two of the eight lot-seed-rule units. Category is read at k(I0).")
p = find("Note. The two conditions replay identical exogenous demand within a lot-seed")
set_text(p, "Note. The two conditions replay identical exogenous demand within a lot-seed; the change is a difference between two implemented policies and not between two optima. No held-out seed block is used: this is an exploratory comparison on the same four streams, and the two rule labels are not independent replications.")

# Table 3 header: Change -> Change (I1 - I0)
for table in doc.tables:
    if table.rows and table.rows[0].cells[0].text.strip() == "Lot":
        table.rows[0].cells[4].text = "Change (I1 - I0)"
        break

# ---------- Results: Q3 ----------
p = find("Comparing the two rules on the same groups")
set_text(p, "Comparing the two rules on the same groups gives the conditional version of the substitution question. Over 840 rule pairs pooled across the five scenarios, the two rules are both admissible in 677, only the first in 7, only the second in 4 and neither in 152. Table 4 separates the comparison types, and we do not pool them. In the dedicated-versus-shared rows (470 pairs: A vs B, A vs C, A vs D), the shared rule never restores admissibility (0 pairs) and never lowers the minimal count (0 pairs); at a common k it improves service in 4 pairs and worsens it in 0; 5 pairs are admissible under both rules with disjoint sets. In the shared-versus-shared rows (370 pairs: B vs C, B vs D, C vs D), admissibility is restored in 4 pairs and the minimal count is smaller in 2; at a common k service improves in 0 and worsens in 6; no pair is disjoint. The two smaller counts are not two independent cases: both come from the same REF lot-seed group (TPE1376, seed 10) under B|D and C|D, where the forecast-gated shared rule needs two equipped bays while the other two shared rules need 24. Those cells are allocation-order effects between shared rules, not device savings from sharing. The information-condition comparison is reported in the previous subsection and is not entered into this table.")

p = find("Table 4 Admissible sets of the two rules")
set_text(p, "Table 4 Admissible sets of the two rules over complete integer grids. Pairs are lot-seed groups pooled over five scenarios at tolerance 5%; the Pairs column is the sum within each rule pair, so rows are not independent samples. Rows A vs B, A vs C and A vs D compare the dedicated rule with a shared rule; rows B vs C, B vs D and C vs D compare two shared rules under the same information condition.")
p = find("Note. Only the A rows compare the dedicated rule with a shared rule")
set_text(p, "Note. Only the A rows compare the dedicated rule with a shared rule. The B/C/D rows compare two shared rules at the same information condition; their restored and smaller-k cells are allocation-order effects, not device savings from sharing. The two smaller counts in B vs D and C vs D come from the same lot-seed group (TPE1376, seed 10), where the forecast-gated shared rule needs two equipped bays while the other two shared rules need 24. Pairs are pooled over five scenarios and are not independent draws; no cross-type total is formed. A set counts as admissible only under the pre-registered convention, and truncation at the grid edge is reported separately from emptiness.")

p = find("The energy-based fourth constraint behaves differently")
set_text(p, "The energy-based fourth constraint behaves differently from the other three, and the difference lies in the records rather than in the model. Every rate is in one of five states: valid; not applicable because its denominator is zero; censored because the window closes before the event that would decide the outcome; missing; and illegal. Only valid values can satisfy a constraint. The inclusive convention records and skips a not-applicable rate; the strict convention requires every rate to be valid, so an N/A rate does not count as satisfied; censored energy is auxiliary; missing and illegal values are never silently dropped. A recount of the 60 curves under this five-state reading gives 780 of 975 units admissible under the three constraints when a zero-demand rate is skipped, and 765 when it is required to be valid; adding the energy shortfall rate at 5% leaves 66 of 975. The earlier all-skipped convention left 310, and the strict five-state convention leaves 51. Those differences are changes of convention, not a before-and-after repair; the paper keeps the pre-registered inclusive convention and reports the alternatives beside it. The energy rate stays a censored auxiliary: a group with a charging request but no departure inside the window is not a success and not a failure, and it is counted rather than scored.")

p = find("Nothing in this section identifies a best rule")
t = p.text
old = "The tipping-point statements of the earlier subsections were computed under the submitted model and accounting and are not re-estimated here; they neither confirm nor refute the comparisons above, and the two are not merged."
new = "The earlier tipping-point exercise was computed under the submitted v1 accounting and is not re-estimated here; it is reported in Supplementary Note S7 as a historical benchmark, neither confirming nor refuting the comparisons above, and no old ETP value enters the abstract, results or conclusions of this version."
if old not in t:
    raise RuntimeError("old ETP sentence not found")
set_text(p, t.replace(old, new))

# ---------- Methods: old-model narrative and five-state vocabulary ----------
p = find("EV ownership and charging need are distinct attributes")
set_text(p, "EV ownership and charging need are distinct attributes. Let r be the share of arriving vehicles that are EVs and q the share of EV arrivals that want to charge. A driver in a parking-only EV may take an ordinary berth and never plug in; a charging EV needs an equipped berth and a free device. Three demand classes follow, ICEV, parking-only EV and charging EV, and their compatibility with the two berth types follows from the rule definitions rather than from a separate table: an ICEV takes an ordinary berth only, a parking-only EV takes an ordinary berth under either rule and an equipped berth only when the shared rule admits it, and a charging EV takes an equipped berth and nothing else. The strict separation rule is a boundary case, not the model used for the main comparison: the main pi0 rule allows an EV to fall back to an ordinary berth, and the model here keeps that fallback unless a stated variant removes it.")

p = find("The comparison between pile ratios only means something")
set_text(p, "The comparison between pile ratios only means something when the admission rule is held fixed or changed on purpose, so we define the rule pi separately from m. Rule pi_S admits an ICEV or a parking-only EV to an ordinary berth only. Rule pi_F admits any vehicle to any compatible free berth. A protected-threshold rule pi_theta reserves theta*m charging berths for charging vehicles and opens the rest, following the threshold structure analysed for two-class loss systems 42 and for parking with priority users 43. The rules used in the comparisons are labelled A to D: A is the dedicated rule with EV fallback, B opens every compatible berth with ICEV first, C protects a quota, and D adds a forecast gate but still reads only I0 information. The comparison changes the rule while holding the stream and k fixed; it is not an optimization over rules.")

# remove old cluster-analysis paragraph and rewrite the layer paragraph
old_p72 = find("The parameters for the typical scenario are obtained through cluster analysis")
remove(old_p72)
p = find("The numbers in this paper come from three layers that are kept apart")
set_text(p, "The numbers in this paper come from three layers that are kept apart. The first is a frozen open parking panel: a roster of 372 lots polled every five minutes over two collection dates, 307 five-minute slots spanning 25.75 h, with no complete 24-hour local day. From it we take the hourly pattern of occupancy, the arrival intensity implied by it and a dwell-time distribution; we do not take energy, refusals or vehicle identities, because the panel does not carry them. Official aggregate statistics supply the electricity price and a value of time at a stated price year. The third layer is assumed: the EV share r, the charging-want share q and the scenario parameters are not identified from these records, and each is labelled wherever it enters a result. The planning dataset and cost parameters of the earlier v1 model are historical and are described in Supplementary Note S7; they are not used to compute the results below.")

p = find("Two categories are excluded from the count rather than scored")
set_text(p, "Rates can be in one of five states. A rate is valid when its denominator is positive and the record carries a computed value; not applicable when the scenario contains no event of the kind the rate refers to, so the denominator is zero; censored when the window closes before the event that would decide the outcome, as happens for the energy shortfall rate when a charging session has not departed; missing when the record should carry a value and does not; and illegal when the stored value contradicts its denominator. Only valid values can satisfy a constraint. The inclusive convention records and skips a not-applicable rate; the strict convention requires every rate to be valid, so an N/A rate does not count as satisfied. The energy shortfall rate is held censored and auxiliary throughout; missing and illegal values are never silently dropped. Where the grid is truncated we write that the grid does not settle the question; we do not write that a configuration is infeasible.")

# ---------- Discussion: remove old related-method paragraphs, add opening ----------
old_disc = [
    "One assumption carries more weight than the others",
    "The objective is expected social cost",
    "If a prediction module is added",
    "A static ratio is a planning object",
]
for prefix in old_disc:
    remove(find(prefix))

opening = add_para([("The three results answer one planning question: with a fixed stock of berths and a fixed exogenous stream, how do the rule that assigns vehicles to compatible berths and the information available to that rule change the smallest integer provision and the shape of the admissible set? The answer is conditional in three ways. First, the admission rule changes who bears a failure, so an extra equipped bay is not a monotone instrument for the class that does not charge; in a loss system with fallback, one added bay can lower ICEV failures while raising EV failures, and only the restricted no-fallback variant gives the nested failure sets. Second, a specific signal-aware heuristic lowers the selected count but moves failures between classes and makes some cells inadmissible at the count selected without the signal; that is an algorithmic comparison, not the value of information. Third, within 0-40 the admissible sets are intervals but are often empty or truncated, so a single count misrepresents what the data can support. We do not rank the rules, and we do not convert the service standard into a social optimum.", False)])
reading = find("Reading the conditional results")
reading._element.addprevious(opening._element)

# historical note before Limitations
lim = find("Limitations and reproducibility")
hist_h = add_para([("Relation to the earlier v1 model", False)], style="Heading 2", before=lim)
hist = add_para([
    ("Before the service-standard formulation, the submitted manuscript minimized a social cost over the pile ratio and read an electrification tipping point from that cost comparison", False),
    ("37-40,54,70,71", True),
    (". That exercise used a different objective, cost parameters that are not identified for the site, and an earlier accounting; it is reported for traceability in Supplementary Note S7 and is not re-estimated here. It neither confirms nor refutes the service-standard comparisons above, and no old ETP number enters the abstract, results or conclusions of this version.", False),
], before=lim)

rel_h = add_para([("Related methods not used here", False)], style="Heading 2", before=lim)
rel = add_para([
    ("Several extensions are outside this paper and are not implemented: decision-dependent demand ", False),
    ("55", True),
    (", robust satisficing ", False), ("56", True),
    (", Wasserstein or moment ambiguity ", False), ("57,58", True),
    (", predict-then-optimise ", False), ("53,59", True),
    (", and rolling or online allocation ", False), ("60-69", True),
    (". They indicate what would be needed to turn the conditional comparisons into a policy with guarantees; none is used as evidence here.", False),
], before=lim)

# evidence status inside Limitations, before the literature paragraph
lit = find("The literature enters with its own evidence levels")
ev = add_para([("Evidence status differs by claim. The fixed-k dedicated-versus-shared comparison is the only one with a held-out design: k was selected on seeds 1-4 and evaluated on seeds 5-10, over 40 runs and 48 lot-rule cells, and that evaluation reported capacity-unmet rates of 5.02% for A, 6.49% for B and 5.36% for D, with the class-specific rates recorded in the round-4 acceptance file. The I0/I1 comparison has no held-out block and is exploratory; the mechanism traces are deterministic replays; the feasible-set counts are complete within 0-40 but describe the stored trajectories. No claim here is a population estimate or a field trial.", False)], before=lit)

doc.save(SRC)
print("SAVED", SRC)
print("PARAS", len(doc.paragraphs), "TABLES", len(doc.tables))
