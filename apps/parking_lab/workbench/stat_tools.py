"""纯标准库统计工具：分位数、bootstrap 置信区间、Wilson 区间与两样本 KS 统计量。

供整数配桩实验做不确定性传播与验证使用；不依赖 numpy/pandas/scipy。
所有函数对非法输入抛 ValueError。
"""
import math
import random

_Z_BY_LEVEL = {
    0.90: 1.6448536269514722,
    0.95: 1.959963984540054,
    0.99: 2.5758293035489004,
}


def _require_finite_numbers(values):
    """校验 values 为非空序列且全部为有限实数，否则抛 ValueError。"""
    if values is None or len(values) == 0:
        raise ValueError("values must be a non-empty sequence")
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("all values must be real numbers")
        if not math.isfinite(v):
            raise ValueError("all values must be finite")


def percentile(values, q):
    """线性插值分位数：排序后 idx = q*(n-1)，在相邻两点间线性插值。

    values 非空且全为有限数；q ∈ [0, 1]；否则抛 ValueError。
    """
    _require_finite_numbers(values)
    if isinstance(q, bool) or not isinstance(q, (int, float)):
        raise ValueError("q must be a number")
    if not (0.0 <= q <= 1.0):
        raise ValueError("q must be within [0, 1]")
    ordered = sorted(values)
    n = len(ordered)
    idx = q * (n - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return float(ordered[lo])
    frac = idx - lo
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * frac)


def bootstrap_ci(values, statistic=None, n_boot=1000, alpha=0.05, seed=0):
    """有放回重抽样 bootstrap 置信区间（百分位法）。

    statistic 默认取均值；返回 {"point", "low", "high", "n_boot", "alpha"}，
    low/high 为 bootstrap 分布的 alpha/2 与 1-alpha/2 分位。
    使用 random.Random(seed)，同 seed 结果完全可复现。
    """
    _require_finite_numbers(values)
    if statistic is None:
        statistic = lambda xs: sum(xs) / len(xs)
    if not isinstance(n_boot, int) or isinstance(n_boot, bool) or n_boot < 1:
        raise ValueError("n_boot must be a positive integer")
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must be within (0, 1)")
    rng = random.Random(seed)
    n = len(values)
    point = float(statistic(list(values)))
    samples = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        samples.append(float(statistic(sample)))
    low = percentile(samples, alpha / 2.0)
    high = percentile(samples, 1.0 - alpha / 2.0)
    return {"point": point, "low": low, "high": high, "n_boot": n_boot, "alpha": alpha}


def paired_mean_diff_ci(a, b, n_boot=1000, alpha=0.05, seed=0):
    """配对差值均值及其 bootstrap 置信区间（逐对差 d_i = a[i]-b[i]）。

    a、b 长度必须相同且非空；返回 {"mean", "low", "high", "n", "n_boot"}。
    """
    if a is None or b is None or len(a) == 0 or len(b) == 0:
        raise ValueError("a and b must be non-empty")
    if len(a) != len(b):
        raise ValueError("a and b must have the same length")
    diffs = [x - y for x, y in zip(a, b)]
    ci = bootstrap_ci(diffs, n_boot=n_boot, alpha=alpha, seed=seed)
    return {"mean": ci["point"], "low": ci["low"], "high": ci["high"],
            "n": len(diffs), "n_boot": n_boot}


def wilson_interval(successes, trials, level=0.95):
    """二项比例 p̂=s/n 的 Wilson score 区间 (low, high)。

    level 仅支持 0.9/0.95/0.99（对应 z 见 _Z_BY_LEVEL），其余抛 ValueError；
    trials 为正整数，0 <= successes <= trials。
    """
    if isinstance(successes, bool) or not isinstance(successes, int):
        raise ValueError("successes must be an integer")
    if isinstance(trials, bool) or not isinstance(trials, int) or trials <= 0:
        raise ValueError("trials must be a positive integer")
    if successes < 0 or successes > trials:
        raise ValueError("must satisfy 0 <= successes <= trials")
    if level not in _Z_BY_LEVEL:
        raise ValueError("level must be one of 0.9, 0.95, 0.99")
    z = _Z_BY_LEVEL[level]
    p = successes / trials
    denom = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denom
    half = z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) / denom
    low = max(0.0, center - half)
    high = min(1.0, center + half)
    # 边界吸附：p̂=0 时下界精确为 0，p̂=1 时上界精确为 1，
    # 避免浮点误差产生 1e-16 量级的越界。
    if successes == 0:
        low = 0.0
    if successes == trials:
        high = 1.0
    return (low, high)


def ks_statistic(a, b):
    """两样本 Kolmogorov-Smirnov 统计量：经验分布函数的最大绝对差。

    a、b 均须非空；返回 float ∈ [0, 1]。
    """
    _require_finite_numbers(a)
    _require_finite_numbers(b)
    sa = sorted(a)
    sb = sorted(b)
    na, nb = len(sa), len(sb)
    i = j = 0
    best = 0.0
    while i < na or j < nb:
        if j >= nb or (i < na and sa[i] <= sb[j]):
            i += 1
        else:
            j += 1
        # 并列值：把两个样本中所有等于当前值的点一次性计入，
        # 保证相同样本（含重复值）的 ECDF 差恒为 0。
        val = sa[i - 1] if i > 0 else sb[j - 1]
        while i < na and sa[i] == val:
            i += 1
        while j < nb and sb[j] == val:
            j += 1
        diff = abs(i / na - j / nb)
        if diff > best:
            best = diff
    return float(best)
