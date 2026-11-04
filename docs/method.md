# Method summary

状态: 生效

The full derivation is in the manuscript; this page fixes the symbols, units and the equations
that the public code implements, so the results can be read without the paper.

## Units and notation

| symbol | meaning | unit / domain |
|---|---|---|
| `s` | site index | — |
| `N` | charge requests in one complete site-day stream | count |
| `n_s`, `b_s` | spaces, declared charging bays at site `s` | count |
| `k` | operated/installed connectors, `k in {0..b_s}` | count |
| `T_i` | dwell time of request `i` | minutes |
| `E_i` | requested energy of request `i` | kWh |
| `P` | connector power | kW |
| `f` | evaluation target fraction in `(0,1]`; does not change the vehicle's stopping rule | — |
| `C` | charge requests in the evaluated sample (the common denominator of the session rates) | count |
| `alpha` | service-tolerance level in `F_s` | proportion |
| `beta` | slope of the dwell weight | — |
| `g`, `n` | gate refusals and no-connector outcomes | count |
| `v`, `C_ICE` | refused ICEV arrivals, ICEV arrivals in the same sample | count |
| `u` | sessions that connected but departed with an energy shortfall | count |
| `D` | delivered energy over the same evaluated requests | kWh |
| `A_s(k)` | EV access/parking-failure rate at site `s` with `k` connectors | proportion |
| `E_s(k)` | energy-shortfall rate at site `s` with `k` connectors | proportion |
| `I_s(k)` | ICEV parking-failure rate at site `s` with `k` connectors | proportion |
| `r_{p,i}` | 0/1 failure indicator for request `i` under policy `p` | 0 or 1 |
| `med(T)`, `sd(T)` | median and sample standard deviation of the stream's dwell times | minutes |

- stream: one complete site-day block; `N` charge requests in it.
- `C`, `u`, `D`, `A_s`, `E_s`, `I_s` are **pooled** quantities: numerators and
  denominators are summed over the evaluated streams, then divided once. They are not means
  of per-stream ratios. `A_s = (g+n)/C`, `E_s = 1 - D/sum_i E_i`, and
  `I_s = v/C_ICE`, where `v` is refused ICEV arrivals and `C_ICE` is ICEV arrivals in the
  same sample; the public code only consumes the resulting values in `F_s`.

## Equations

1. delivered energy upper bound per session: `d_i(f) = min(f*E_i, P*T_i/60)` (T_i in minutes, P in kW, so P*T_i/60 is kWh)
2. ideal energy service rate: `R_ideal(f) = sum_i d_i(f) / sum_i E_i`
3. ideal session failure rate: `Phi_ideal(f) = (1/N) * sum_i 1{f*E_i > P*T_i/60}`
4. never-connected rate: `Gamma_conn = (g + n) / C`
5. departed-shortfall session rate: `Gamma_ses = u / C`
6. energy shortfall ratio: `Gamma_eng = 1 - D / sum_i E_i`
7. feasible set: `F_s(f) = { k in {0..b_s} : A_s(k) <= alpha, E_s(k) <= alpha, I_s(k) <= alpha }`
8. minimal configuration: `k_s*(f) = min F_s(f)`; empty set is reported as infeasible
9. paired difference: `Delta = (1/N) * sum_i (r_b,i - r_A,i)`. `r_{p,i}` is the 0/1
   failure indicator for the **same** request `i` under policy `p`; the two policies are
   paired by request and stream, the direction is `b - A` (positive = b fails more often),
   and `Delta` is a dimensionless proportion, not a count.
10. dwell-coupled demand weight: `w_i = 1 / (1 + exp(-beta*(T_i - med(T))/sd(T)))`
11. fixed-size weighted sampling without replacement: `Pr(S) = prod_{i in S} w_i /
    sum_{|S'|=C} prod_{j in S'} w_j`

Important distinctions kept in the code and the paper:

- Hand check for (1): 10 minutes at 7 kW delivers `7*10/60 = 7/6 kWh`; a 14 kWh
  request cannot be completed in those 10 minutes, and its delivered upper bound is 7/6 kWh.
  `analysis/example.py` implements the same expression as `min(e, P*t)` with `t = dwell/60`,
  so the 10 min / 7 kW / 14 kWh case gives the same 7/6 and failure indicator 1.
- `d_i(f)` and `R_ideal` are analytic upper bounds with perfect scheduling; they are **not**
  an executable policy and carry no optimality claim.
- `w_i`, the sampling distribution (11) and a real charging probability are three different
  objects. `w_i` is a scenario-design weight; it is not an inclusion probability and not an
  odds ratio estimated from data.
- Rates state numerator, denominator and whether they are pooled ratios or means of per-stream
  ratios. `in_violation` is a source compliance flag and is retained, with an exclusion
  sensitivity reported.
