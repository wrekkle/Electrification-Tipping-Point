# Method summary

状态: 生效

The full derivation is in the manuscript; this page fixes the symbols, units and the equations
that the public code implements, so the results can be read without the paper.

## Units and notation

- `s` site, `n_s` spaces, `b_s` declared charging bays, `k` operated connectors,
  `k in {0..b_s}`.
- stream: one complete site-day block; `N` charge requests in it.
- request `i`: dwell `T_i` in **minutes**, requested energy `E_i` in **kWh**; connector
  power `P` in **kW**. Energy deliverable in a visit: `P * T_i / 60`.
- target fraction `f` in `(0,1]`: an evaluation target for the metric. It does not change the
  vehicle's stopping rule.

## Equations

1. delivered energy upper bound per session: `d_i(f) = min(f*E_i, P*T_i)`
2. ideal energy service rate: `R_ideal(f) = sum_i d_i(f) / sum_i E_i`
3. ideal session failure rate: `Phi_ideal(f) = (1/N) * sum_i 1{f*E_i > P*T_i}`
4. never-connected rate: `Gamma_conn = (g + n) / C`, `g` gate refusals, `n` no-connector
5. departed-shortfall session rate: `Gamma_ses = u / C`
6. energy shortfall ratio: `Gamma_eng = 1 - D / sum_i E_i`
7. feasible set: `F_s(f) = { k in {0..b_s} : A_s(k) <= alpha, E_s(k) <= alpha, I_s(k) <= alpha }`
8. minimal configuration: `k_s*(f) = min F_s(f)`; empty set is reported as infeasible
9. paired difference: `Delta = (1/N) * sum_i (r_b,i - r_A,i)`
10. dwell-coupled demand weight: `w_i = 1 / (1 + exp(-beta*(T_i - med(T))/sd(T)))`
11. fixed-size weighted sampling without replacement: `Pr(S) = prod_{i in S} w_i /
    sum_{|S'|=C} prod_{j in S'} w_j`

Important distinctions kept in the code and the paper:

- `d_i(f)` and `R_ideal` are analytic upper bounds with perfect scheduling; they are **not**
  an executable policy and carry no optimality claim.
- `w_i`, the sampling distribution (11) and a real charging probability are three different
  objects. `w_i` is a scenario-design weight; it is not an inclusion probability and not an
  odds ratio estimated from data.
- Rates state numerator, denominator and whether they are pooled ratios or means of per-stream
  ratios. `in_violation` is a source compliance flag and is retained, with an exclusion
  sensitivity reported.
