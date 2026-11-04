"""Moving-block bootstrap (MBB) statistical engine.

Pure functions, standard library only (math/random/statistics).
Does not read any repository data files.

Implements:
- vif_newey_west(x, max_lag): Newey-West/Bartlett weighted variance inflation
  factor for the sample mean of a time series.
- mbb_tail_bounds(vals, ns, L, B, alpha, seed): one-sided upper bounds on the
  exceedance rate p_hat via moving-block bootstrap, with ONE shared set of
  resampling indices across all thresholds n (mbb_tail_bound is the single-n
  wrapper).
- mbb_rate_ci(vals, n, L, B, alpha, seed): two-sided MBB confidence interval
  for the exceedance rate.
- binom_p_effective(x, m, p, vif): one-sided binomial tail probability with
  effective sample size n_eff = max(1, round(m / vif)).
"""

import math
import random
import statistics


def _mean(xs):
    return sum(xs) / len(xs)


def vif_newey_west(x, max_lag=28):
    """Variance inflation factor for the mean using Newey-West weighting.

    Returns max(1.0, gamma0_hat^-1 * var_NW), where var_NW is the Bartlett
    kernel estimate of the long-run variance of the demeaned series.
    """
    m = len(x)
    if m < 2:
        return 1.0
    mu = _mean(x)
    d = [v - mu for v in x]
    # autocovariances
    acov = []
    for lag in range(max_lag + 1):
        s = 0.0
        for i in range(m - lag):
            s += d[i] * d[i + lag]
        acov.append(s / m)
    kmax = min(max_lag, m - 1)
    nw = acov[0]
    for lag in range(1, kmax + 1):
        w = 1.0 - lag / (kmax + 1)  # Bartlett kernel
        nw += 2.0 * w * acov[lag]
    vif = nw / acov[0] if acov[0] > 0 else 1.0
    return max(1.0, vif)


def _mbb_resample(vals, L, rng):
    """One moving-block bootstrap resample (circular blocks)."""
    m = len(vals)
    out = []
    while len(out) < m:
        start = rng.randrange(m)
        for j in range(L):
            out.append(vals[(start + j) % m])
    return out[:m]


def _p_hat_of(sample, n):
    m = len(sample)
    return sum(1 for v in sample if v > n) / m


def _mbb_indices(m, L, B, rng):
    """B moving-block index vectors, drawn once and reused across thresholds."""
    out = []
    for _ in range(B):
        ix = []
        while len(ix) < m:
            start = rng.randrange(m)
            ix.extend((start + j) % m for j in range(L))
        out.append(ix[:m])
    return out


def _quantile(sorted_vals, p):
    n = len(sorted_vals)
    idx = p * (n - 1)
    lo_i = int(math.floor(idx))
    hi_i = min(lo_i + 1, n - 1)
    frac = idx - lo_i
    return sorted_vals[lo_i] * (1.0 - frac) + sorted_vals[hi_i] * frac


def mbb_tail_bounds(vals, ns, L, B, alpha, seed):
    """Upper tail bounds for several thresholds with ONE set of resamples.

    Sharing the bootstrap indices across n keeps the bounds comparable across
    thresholds (the old per-n seed + n scheme drew a different resample set for
    every n).  It does not repair the finite-sample coverage failure at the
    all-zero boundary: if every v is <= n for every resample, q = 0 and the
    bound is p_hat = 0; a true tail below the boundary is not covered.
    """
    m = len(vals)
    rng = random.Random(seed)
    IX = _mbb_indices(m, L, B, rng)
    out = {}
    for n in ns:
        p_hat = _p_hat_of(vals, n)
        boot = sorted(sum(1 for i in ix if vals[i] > n) / m - p_hat for ix in IX)
        q = _quantile(boot, 1.0 - alpha)
        bound = min(1.0, max(0.0, p_hat + q))
        out[n] = {"p_hat": p_hat, "q": q, "bound": bound, "L": L, "B": B, "m": m}
    return out


def mbb_tail_bound(vals, n, L, B, alpha, seed):
    """Single-threshold wrapper; see mbb_tail_bounds for the shared-index form."""
    return mbb_tail_bounds(vals, [n], L, B, alpha, seed)[n]


def mbb_rate_ci(vals, n, L, B, alpha, seed):
    """Two-sided MBB confidence interval for the exceedance rate.

    lo/hi are the alpha/2 and 1-alpha/2 quantiles of the bootstrap
    distribution of p_hat.
    """
    m = len(vals)
    rng = random.Random(seed)
    p_hat = _p_hat_of(vals, n)
    boot = [_p_hat_of(_mbb_resample(vals, L, rng), n) for _ in range(B)]
    boot.sort()

    def quantile(p):
        idx = p * (B - 1)
        lo_i = int(math.floor(idx))
        hi_i = min(lo_i + 1, B - 1)
        frac = idx - lo_i
        return boot[lo_i] * (1.0 - frac) + boot[hi_i] * frac

    lo = quantile(alpha / 2.0)
    hi = quantile(1.0 - alpha / 2.0)
    return {"rate": p_hat, "lo": lo, "hi": hi}


def binom_p_effective(x, m, p, vif):
    """One-sided binomial tail P(X >= x | Bin(n_eff, p)), n_eff = max(1, round(m/vif))."""
    n_eff = max(1, round(m / vif))
    x = int(x)
    total = 0.0
    log_pf = math.log(p)
    log_qf = math.log(1.0 - p)
    for k in range(x, n_eff + 1):
        log_c = math.lgamma(n_eff + 1) - math.lgamma(k + 1) - math.lgamma(n_eff - k + 1)
        total += math.exp(log_c + k * log_pf + (n_eff - k) * log_qf)
    return min(1.0, total)


def _iid_series(m, seed, thresh_frac=0.5):
    """Generate an i.i.d. Bernoulli-like series: values 0/1 with p=thresh_frac."""
    rng = random.Random(seed)
    return [rng.random() < thresh_frac for _ in range(m)]


def _ar1_series(m, rho, seed):
    """AR(1) series x_t = rho*x_{t-1} + eps_t, eps ~ N(0,1); return list."""
    rng = random.Random(seed)
    vals = []
    x = 0.0
    for _ in range(m):
        x = rho * x + rng.gauss(0.0, 1.0)
        vals.append(x)
    return vals


if __name__ == "__main__":
    print("=== self-check: i.i.d. series ===")
    iid = _iid_series(365, seed=42)
    vif_iid = vif_newey_west(iid, max_lag=28)
    print(f"i.i.d. m=365: vif={vif_iid:.4f}")
    tb = mbb_tail_bound(iid, n=0, L=14, B=2000, alpha=0.05, seed=7)
    print(f"i.i.d. tail bound: p_hat={tb['p_hat']:.4f} q={tb['q']:.4f} bound={tb['bound']:.4f}")
    ci = mbb_rate_ci(iid, n=0, L=14, B=2000, alpha=0.05, seed=7)
    print(f"i.i.d. rate CI: rate={ci['rate']:.4f} lo={ci['lo']:.4f} hi={ci['hi']:.4f}")
    pb = binom_p_effective(200, 365, 0.5, vif_iid)
    print(f"binom_p_effective(x=200,m=365,p=0.5,vif={vif_iid:.4f})={pb:.6f}")

    print()
    print("=== self-check: AR(1) positive correlation ===")
    ar = _ar1_series(365, rho=0.6, seed=42)
    vif_ar = vif_newey_west(ar, max_lag=28)
    print(f"AR(1) rho=0.6 m=365: vif={vif_ar:.4f}")
    med = statistics.median(ar)
    tb_ar = mbb_tail_bound(ar, n=med, L=14, B=2000, alpha=0.05, seed=7)
    print(f"AR(1) tail bound at median: p_hat={tb_ar['p_hat']:.4f} q={tb_ar['q']:.4f} bound={tb_ar['bound']:.4f}")
    pb_ar = binom_p_effective(int(tb_ar["p_hat"] * tb_ar["m"]), tb_ar["m"], tb_ar["p_hat"], vif_ar)
    print(f"binom_p_effective(x={int(tb_ar['p_hat']*tb_ar['m'])},m=365,p={tb_ar['p_hat']:.4f},vif={vif_ar:.4f})={pb_ar:.6f}")
