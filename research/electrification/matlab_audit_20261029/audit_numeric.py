"""Independent numerical audit of the two supplied scripts (active h1=0 only).

This does not execute MATLAB or reproduce its random stream. The deterministic
script is translated both branch by branch and as positive-part formulas.
The stochastic script is evaluated with NumPy PCG64, and independently by
summing its NB/Beta probability law. Nothing is written without --out.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import numpy as np
import scipy
from scipy.special import betainc, expit
from scipy.stats import lognorm, nbinom, poisson

HERE = Path(__file__).resolve().parent
GRID = np.arange(21) / 20


def source(name):
    return (HERE / 'originals' / name).read_text('utf-8-sig')


def active(code):
    return '\n'.join(line.split('%', 1)[0] for line in code.splitlines())


def scalar(code, name):
    found = re.search(r'(?<!\w)' + re.escape(name)
                      + r'\s*=\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*[;,]', code)
    if not found:
        raise ValueError('No scalar assignment: ' + name)
    return float(found.group(1))


def parameters():
    codes = [active(source(n)) for n in ('final_tvr.m', 'final_tvr_v2_fluc_re.m')]
    result = []
    for code in codes:
        vals = re.search(r'\bt\s*=\s*\[([^]]+)\]', code).group(1)
        p = {'n': scalar(code, 'n'), 't': np.array([float(x) for x in re.split(r'[\s,]+', vals.strip())])}
        assert len(p['t']) == 24 and scalar(code, 'h1') == 0 and scalar(code, 'u1') == 1
        result.append(p)
    p, q = result
    for name in ('cgev', 'ctev', 'ccev', 'ccevp', 'cgicv', 'cticv', 'ccicv', 'ccicvp'):
        p[name] = scalar(codes[0], name)
    p['installation'] = sum(scalar(codes[0], n) for n in ('chargepile', 'converting', 'linefee'))
    p['years'] = 8
    p['ce'] = p['cgev'] + p['ctev'] + p['ccev'] * p['ccevp']
    p['ci'] = p['cgicv'] + p['cticv'] + p['ccicv'] * p['ccicvp']
    for name in ('cgev', 'cfev', 'ccev', 'cgicv', 'cficv', 'ccicv', 'mu_ct', 'sig_ct',
                 'alpha_cp', 'beta_cp', 'rho_nev_min', 'od_arr_min', 'nsim', 'power'):
        q[name] = scalar(codes[1], name)
    q['installation'] = q['power'] * 1000 * 1.2
    q['years'] = 5
    quantiles = (np.arange(int(q['nsim'])) + .5) / q['nsim']
    vot = lognorm.ppf(quantiles, s=q['sig_ct'], scale=math.exp(q['mu_ct']))
    q['vot_draws'] = vot
    q['ct_draws'] = vot * 6.81 / 60
    q['cp_draws'] = expit(-q['alpha_cp'] - q['beta_cp'] * np.log(vot))
    q['ce_draws'] = q['cgev'] + q['cfev'] + q['ct_draws'] + q['ccev'] * q['cp_draws']
    q['ci_draws'] = q['cgicv'] + q['cficv'] + q['ct_draws'] + q['ccicv'] * q['cp_draws']
    return p, q


def costs_from_demands(p, total, u_actual, ce, ci, complaint, fix_complaint=False):
    """Vectorized h1=0 allocation, retaining the paper's rule change at r=1."""
    total, u_actual = np.broadcast_arrays(np.asarray(total), np.asarray(u_actual))
    ev = np.maximum(total * (1 - u_actual) - p['n'] * GRID[:, None], 0.)
    ice = np.maximum(total * u_actual - p['n'] * (1 - GRID[:, None]), 0.)
    overflow = np.maximum(total[-1] - p['n'], 0.)
    ev[-1] = overflow * (1 - u_actual[-1])
    ice[-1] = overflow * u_actual[-1]
    installation = p['n'] * GRID[:, None] * p['installation'] / (365 * p['years'] * 24)
    cost = installation + ev * ce + ice * ci
    if not fix_complaint:
        cost[-1] -= ev[-1] * complaint
    return cost, ev, ice


def deterministic_formula(p, fix_complaint=False):
    cost = np.zeros((21, 21))
    ev = cost.copy()
    ice = cost.copy()
    for t in p['t']:
        c, e, i = costs_from_demands(p, t * np.ones((21, 21)), np.tile(GRID, (21, 1)),
                                    p['ce'], p['ci'], p['ccev'] * p['ccevp'], fix_complaint)
        cost += c
        ev += e
        ice += i
    return cost, ev, ice


def deterministic_branches(p):
    """Literal translation of active original branches, separate from oracle."""
    result = np.zeros((21, 21))
    for t in p['t']:
        for i, r in enumerate(GRID):
            for j, u in enumerate(GRID):
                ev, ice = t * (1-u), t * u
                gp, ep = p['n'] * (1-r), p['n'] * r
                if r < 1:
                    if ice > gp:
                        li = ice - gp
                        if li >= 0:  # n*r*h1*u1 == 0
                            le = ev - ep if ev > ep else 0
                        else:
                            raise AssertionError('Inactive sharing branch unexpectedly reached')
                    else:
                        li = 0
                        le = max(ev - ep, 0) if ev > ep else 0
                    c = li * p['ci'] + le * p['ce']
                else:
                    c = (max(t-p['n'], 0) * (p['ci']*u + (p['ce']-p['ccev']*p['ccevp'])*(1-u)))
                result[i, j] += c + p['n'] * r * p['installation'] / (365*p['years']*24)
    return result


def beta_params(u, rho, preserve_endpoints=False):
    if preserve_endpoints and u in (0., 1.):
        return None
    mu = np.clip(u, 1e-4, 1-1e-4)
    var = max(min(rho * mu * (1-mu), .95 * mu * (1-mu)), 1e-6)
    phi = max(mu * (1-mu) / var - 1, 2)
    return mu * phi, (1-mu) * phi


def simulation(p, seed=1, revised=False):
    rng = np.random.default_rng(seed)
    order = rng.permutation(int(p['nsim']))
    costs, evs, ices, den_evs, den_ices = [], [], [], [], []
    for s in range(int(p['nsim'])):
        idx = order[s]
        totals = np.array([rng.negative_binomial(mu/(p['od_arr_min']-1), 1/p['od_arr_min']) for mu in p['t']])
        cost = np.zeros((21, 21))
        ev = cost.copy()
        ice = cost.copy()
        den_ev = cost.copy()
        den_ice = cost.copy()
        for t in totals:
            u_actual = np.empty((21, 21))
            for j, u in enumerate(GRID):
                ab = beta_params(u, p['rho_nev_min'], revised)
                if ab is None:
                    u_actual[:, j] = u
                elif revised:
                    u_actual[:, j] = rng.beta(*ab)
                else:
                    u_actual[:, j] = rng.beta(*ab, size=21)
            c, e, i = costs_from_demands(p, t*np.ones((21, 21)), u_actual,
                                        p['ce_draws'][idx], p['ci_draws'][idx],
                                        p['ccev']*p['cp_draws'][idx], revised)
            cost += c
            ev += e
            ice += i
            den_ev += t*(1-u_actual)
            den_ice += t*u_actual
        costs.append(cost)
        evs.append(ev)
        ices.append(ice)
        den_evs.append(den_ev)
        den_ices.append(den_ice)
    return np.array(costs), np.array(evs), np.array(ices), np.array(den_evs), np.array(den_ices)


def expected_cost(p, fix_complaint=False, preserve_endpoints=False, arrival_law='nb'):
    """NB sum of analytic Beta stop-loss moments; each tail <=1e-12.

    VOT is averaged over the script's exact 50 stratified quantiles. This is
    the expectation over demand, not a native MATLAB Monte Carlo result.
    """
    ev = np.zeros((21, 21))
    ice = ev.copy()
    tail_mass = 0.
    for mu, count in zip(*np.unique(p['t'], return_counts=True)):
        shape = mu/(p['od_arr_min']-1)
        prob = 1/p['od_arr_min']
        distribution = nbinom(shape, prob) if arrival_law == 'nb' else poisson(mu)
        lo = int(distribution.ppf(1e-12))
        hi = int(distribution.ppf(1-1e-12))
        t = np.arange(lo, hi+1, dtype=float)
        pmf = distribution.pmf(t)
        tail_mass += count*(distribution.cdf(lo-1)+distribution.sf(hi))
        for j, u in enumerate(GRID):
            ab = beta_params(u, p['rho_nev_min'], preserve_endpoints)
            mu_u = u if ab is None else ab[0]/sum(ab)
            if ab is None:
                ev[:-1, j] += count*np.sum(np.maximum(t[None, :]*(1-u)-p['n']*GRID[:-1, None], 0)*pmf,axis=1)
                ice[:-1, j] += count*np.sum(np.maximum(t[None, :]*u-p['n']*(1-GRID[:-1, None]), 0)*pmf,axis=1)
            else:
                ai, bi = ab
                for dest, mean, a, b, capacity in (
                        (ev, 1-mu_u, bi, ai, p['n']*GRID[:-1]),
                        (ice, mu_u, ai, bi, p['n']*(1-GRID[:-1]))):
                    k = capacity[:, None]
                    cutoff = np.clip(k/t[None, :], 0, 1)
                    loss = t[None, :]*mean*(1-betainc(a+1, b, cutoff))-k*(1-betainc(a, b, cutoff))
                    dest[:-1, j] += count*np.sum(loss*pmf,axis=1)
            overflow = np.sum(np.maximum(t-p['n'], 0)*pmf)
            ev[-1, j] += count*overflow*(1-mu_u)
            ice[-1, j] += count*overflow*mu_u
    cost = ev*np.mean(p['ce_draws']) + ice*np.mean(p['ci_draws'])
    if not fix_complaint:
        cost[-1] -= ev[-1]*p['ccev']*np.mean(p['cp_draws'])
    cost += p['n']*GRID[:, None]*p['installation']/(365*p['years'])
    return cost, tail_mass


def column_rows(cost, label):
    best = cost.argmin(axis=0)
    diag, anti = np.diag(cost), cost[np.arange(20, -1, -1), np.arange(21)]
    result = []
    for j, u in enumerate(GRID):
        opt = cost[best[j], j]
        result.append({'model': label, 'u_ice': u, 'ev_share': 1-u, 'best_r': GRID[best[j]],
                       'best_daily_cost': opt, 'full_daily_cost': cost[-1, j],
                       'passive_wrong_r_eq_u_cost': diag[j], 'passive_correct_r_eq_1_minus_u_cost': anti[j],
                       'wrong_passive_increase_pct': (diag[j]/opt-1)*100,
                       'correct_passive_increase_pct': (anti[j]/opt-1)*100})
    return result


def etp(cost):
    best = cost.argmin(axis=0)[::-1]
    for i in range(21):
        if np.all(best[i:] == 20):
            return float(GRID[i])
    return None


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--replicates', type=int, default=20)
    ap.add_argument('--plot', action='store_true')
    args = ap.parse_args()
    p, q = parameters()
    print('Parsed source parameters; evaluating deterministic and stochastic translations.', flush=True)
    raw1, lev1, lic1 = deterministic_formula(p)
    fixed1, _, _ = deterministic_formula(p, True)
    branch1 = deterministic_branches(p)
    mc, ev_mc, ice_mc, den_ev, den_ice = simulation(q, args.seed)
    revised, _, _, _, _ = simulation(q, args.seed, True)
    print('Evaluating the NB/Beta probability law independently of Monte Carlo.', flush=True)
    expect, tail = expected_cost(q)
    print('Original-law expectation complete; evaluating corrections and Poisson sensitivity.', flush=True)
    expect_complaint, _ = expected_cost(q, fix_complaint=True)
    expect_fixed, _ = expected_cost(q, True, True)
    expect_poisson, _ = expected_cost(q, arrival_law='poisson')
    tests = []

    def check(name, passed, evidence):
        tests.append({'name': name, 'passed': bool(passed), 'evidence': clean(evidence)})

    check('v1_all_441_raw_costs_branch_translation_vs_formula', np.allclose(branch1, raw1, rtol=0, atol=1e-9),
          {'max_abs_error': np.max(abs(branch1-raw1))})
    check('v1_v2_normalized_loading_identical', np.allclose(p['t']/p['n'], q['t']/q['n']),
          {'v1_t_sum': sum(p['t']), 'v2_t_sum': sum(q['t'])})
    check('passive_r_equals_EV_share_uses_antidiagonal', np.allclose(GRID[::-1], 1-GRID),
          {'u_0_2_original_r': .2, 'u_0_2_correct_r': .8})
    check('v1_daily_rate_counterexample', lev1[0, 0]/p['t'][-1] > 1,
          {'original_lrev': lev1[0, 0]/p['t'][-1], 'daily_lrev': lev1[0, 0]/sum(p['t'])})
    check('v1_zero_demand_denominator_present', p['t'][-1]*GRID[0] == 0,
          'Original endpoint ratios divide by zero; undefined rates should be NaN.')
    check('both_full_branches_omit_EV_complaint', np.all(fixed1[-1] >= raw1[-1]) and fixed1[-1, 0] > raw1[-1, 0],
          {'v1_full_cost_missing_at_EV_1': fixed1[-1, 0]-raw1[-1, 0],
           'v2_expected_full_cost_missing_at_EV_1': expect_complaint[-1, 0]-expect[-1, 0]})
    check('NB_variance_to_mean_ratio_equals_42', q['od_arr_min'] == 42,
          {'variance_over_mean': q['od_arr_min'], 'Poisson_variance_over_mean': 1})
    check('beta_09_is_relative_variance_not_absolute_variance', np.isclose(.09*.2*.8, .0144),
          {'actual_variance_at_EV_0_2': .09*.2*.8, 'rho': .09})
    check('original_beta_endpoint_shift', beta_params(0, .09)[0]/sum(beta_params(0, .09)) > 0,
          {'nominal_u_0_actual_mean': beta_params(0, .09)[0]/sum(beta_params(0, .09)),
           'revised_endpoint_is_degenerate': beta_params(0, .09, True) is None})
    check('original_c7_mc_is_never_updated', source('final_tvr_v2_fluc_re.m').count('c7_mc(:,:,s) = c7') == 1
          and 'c7(i,j)=' not in active(source('final_tvr_v2_fluc_re.m')),
          'c7 is initialized to zero and stored before the post-MC comparison, so c7_std is identically zero.')
    check('positive_costs_would_be_zeroed_in_plot', np.any(raw1 > raw1[-1]),
          {'cells_masked_by_original_v1': np.sum(raw1 > raw1[-1]), 'minimum_unmasked_raw_cost': raw1.min()})
    rates = np.divide(ev_mc, den_ev, out=np.full_like(ev_mc, np.nan), where=den_ev>0)
    rates_i = np.divide(ice_mc, den_ice, out=np.full_like(ice_mc, np.nan), where=den_ice>0)
    check('daily_flow_conservation_and_rates', np.nanmin(rates) >= -1e-12 and np.nanmax(rates) <= 1+1e-12
          and np.nanmax(rates_i) <= 1+1e-12, {'EV_rate_min': np.nanmin(rates), 'EV_rate_max': np.nanmax(rates)})
    check('quadrature_NB_omitted_probability_mass', tail < 5e-11, {'sum_24_hour_tail_probability': tail})
    check('positive_part_baseline_counterexample', max(80-60, 0) == 20 and max(20-40, 0) == 0,
          'N=100,T=100,u=.2,r=.6: EV leaving=20,ICE leaving=0; r=1 shared gives 0.')
    check('complaint_fix_preserves_r_below_1', np.array_equal(raw1[:-1], fixed1[:-1])
          and np.allclose(expect[:-1], expect_complaint[:-1]), 'Only r=1 cost changes in this one-factor probe.')
    check('endpoint_fix_preserves_interior_expectations', np.allclose(expect_complaint[:, 1:-1], expect_fixed[:, 1:-1]),
          'Endpoint correction changes u=0/1 only.')
    # Inactive at h1=0, but both files contain this branch used for sharing.
    share_n, share_r, share_h, share_t, share_u = 100, .5, .4, 105, .6
    share_ice = share_t*share_u
    share_ev = share_t*(1-share_u)
    overflow_ice = share_ice-share_n*(1-share_r)
    shared_left = share_n*share_r*share_h-overflow_ice
    original_rejected = max(share_ev-share_n*share_r-shared_left, 0)
    corrected_rejected = max(share_ev-share_n*share_r*(1-share_h)-shared_left, 0)
    check('partial_sharing_branch_capacity_violation_counterexample',
          original_rejected == 0 and corrected_rejected == 5,
          {'n': share_n, 'r': share_r, 'h1': share_h, 'T': share_t, 'u_ice': share_u,
           'original_total_rejected': original_rejected, 'corrected_total_rejected': corrected_rejected,
           'minimum_total_rejected_from_capacity': share_t-share_n})
    repeats = []
    etps = []
    print('Evaluating independent 50-scenario replicates.', flush=True)
    for seed in range(1, args.replicates+1):
        c = simulation(q, seed)[0].mean(axis=0)
        repeats.append(c.argmin(axis=0))
        etps.append(etp(c))
    repeats = np.array(repeats)
    target = expect.argmin(axis=0)
    rows = []
    for label, cost in [('v1_as_written', raw1), ('v1_complaint_fixed', fixed1),
                        ('v2_numpy_50_as_written', mc.mean(axis=0)),
                        ('v2_numpy_50_review_fixes', revised.mean(axis=0)),
                        ('v2_distribution_expectation_as_written', expect),
                        ('v2_distribution_expectation_complaint_fixed', expect_complaint),
                        ('v2_distribution_expectation_review_fixes', expect_fixed),
                        ('v2_distribution_expectation_poisson_sensitivity', expect_poisson)]:
        rows.extend(column_rows(cost, label))
    mc_delta = mc-mc[:, -1:, :]
    summary = {
        'date': '2026-10-29', 'scope': 'h1=0,u1=1 active configurations only',
        'execution': 'Independent Python translation; MATLAB/Octave not called; random streams differ.',
        'python': sys.executable, 'python_version': sys.version, 'numpy': np.__version__, 'scipy': scipy.__version__,
        'random_generator': 'numpy.random.default_rng PCG64', 'seed': args.seed,
        'command': sys.argv, 'parameters': [p, q],
        'tests_passed': sum(x['passed'] for x in tests), 'tests_total': len(tests), 'tests': tests,
        'etp_grid_point_estimates': {
            'v1_as_written': etp(raw1), 'v1_complaint_fixed': etp(fixed1),
            'v2_numpy_50': etp(mc.mean(axis=0)), 'v2_expectation_as_written': etp(expect),
            'v2_expectation_review_fixes': etp(expect_fixed), 'v2_expectation_poisson_sensitivity': etp(expect_poisson)},
        'v2_50_scenario_repeats': {'count': args.replicates, 'seeds': list(range(1, args.replicates+1)),
                                  'etp_points': etps, 'best_r_match_probability_by_u': (repeats == target).mean(axis=0)},
        'nonzero_paired_gap_std_cells': int(np.sum(mc_delta.std(axis=0, ddof=1) > 1e-9)),
        'NB_tail_probability_sum': tail,
        'sources_sha256': {x.name: hashlib.sha256(x.read_bytes()).hexdigest() for x in (HERE/'originals').glob('*.m')},
    }
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out/'audit_results.json').write_text(json.dumps(clean(summary), ensure_ascii=False, indent=2, allow_nan=False)+'\n', 'utf-8')
        with (args.out/'cost_comparison.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        np.savez_compressed(args.out/'cost_surfaces.npz', v1_raw=raw1, v1_complaint_fixed=fixed1,
                            v2_mc=mc, v2_mc_review_fixes=revised, v2_expectation=expect,
                            v2_expected_review_fixes=expect_fixed, v2_expected_poisson_sensitivity=expect_poisson)
        if args.plot:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), layout='constrained')
            for j in (0, 4, 8, 12, 16, 20):
                axes[0].plot(GRID, raw1[:, j], label=f'EV={1-GRID[j]:.1f}')
                axes[1].plot(GRID, expect[:, j]/q['n'], label=f'EV={1-GRID[j]:.1f}')
            axes[0].set(title='Deterministic script / original costs', ylabel='Daily cost / RMB')
            axes[1].set(title='Stochastic model / distribution expectation', ylabel='Daily cost per parking space / RMB')
            for ax in axes:
                ax.set_xlabel('Pile-to-parking ratio r')
                ax.grid(alpha=.25)
                ax.legend(fontsize=8)
            fig.savefig(args.out/'raw_cost_curves.png', dpi=170)
            plt.close(fig)
    concise = {k: summary[k] for k in ('execution', 'tests_passed', 'tests_total', 'etp_grid_point_estimates',
                                       'v2_50_scenario_repeats', 'NB_tail_probability_sum')}
    print(json.dumps(clean(concise), ensure_ascii=False, indent=2))
    return 0 if all(t['passed'] for t in tests) else 1


if __name__ == '__main__':
    raise SystemExit(main())
