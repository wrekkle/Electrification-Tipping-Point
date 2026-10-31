"""stat_tools 模块单元测试（纯标准库）。"""
import unittest

from apps.parking_lab.workbench.stat_tools import (
    bootstrap_ci,
    ks_statistic,
    paired_mean_diff_ci,
    percentile,
    wilson_interval,
)


class PercentileTests(unittest.TestCase):
    def test_median_of_four(self):
        self.assertEqual(percentile([1, 2, 3, 4], 0.5), 2.5)

    def test_endpoints(self):
        self.assertEqual(percentile([9, -1, 3], 0.0), -1.0)
        self.assertEqual(percentile([9, -1, 3], 1.0), 9.0)

    def test_single_value(self):
        self.assertEqual(percentile([7], 0.37), 7.0)

    def test_quartiles(self):
        self.assertEqual(percentile([1, 2, 3, 4, 5], 0.25), 2.0)
        self.assertEqual(percentile([1, 2, 3, 4, 5], 0.75), 4.0)

    def test_invalid_inputs(self):
        for bad in ([], None, [1, float("nan")], [1, float("inf")], ["x"]):
            with self.assertRaises(ValueError):
                percentile(bad, 0.5)
        for q in (-0.1, 1.1, "0.5", True):
            with self.assertRaises(ValueError):
                percentile([1, 2], q)


class BootstrapCiTests(unittest.TestCase):
    def test_reproducible_and_ordered(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        r1 = bootstrap_ci(data, n_boot=200, seed=42)
        r2 = bootstrap_ci(data, n_boot=200, seed=42)
        self.assertEqual(r1, r2)
        self.assertLessEqual(r1["low"], r1["point"])
        self.assertLessEqual(r1["point"], r1["high"])
        self.assertEqual(r1["n_boot"], 200)
        self.assertAlmostEqual(r1["alpha"], 0.05)

    def test_custom_statistic(self):
        data = [1.0, 2.0, 3.0]
        ci = bootstrap_ci(data, statistic=lambda xs: max(xs), n_boot=100, seed=1)
        self.assertEqual(ci["point"], 3.0)
        self.assertGreaterEqual(ci["high"], 3.0)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            bootstrap_ci([])
        with self.assertRaises(ValueError):
            bootstrap_ci([1, 2], n_boot=0)
        with self.assertRaises(ValueError):
            bootstrap_ci([1, 2], alpha=1.5)


class PairedMeanDiffCiTests(unittest.TestCase):
    def test_identical_arrays_give_zero(self):
        a = [1.0, 2.0, 3.0, 4.0]
        r = paired_mean_diff_ci(a, list(a))
        self.assertEqual(r["mean"], 0.0)
        self.assertEqual(r["low"], 0.0)
        self.assertEqual(r["high"], 0.0)
        self.assertEqual(r["n"], 4)

    def test_known_shift(self):
        r = paired_mean_diff_ci([2.0, 3.0], [1.0, 1.0])
        self.assertEqual(r["mean"], 1.5)
        self.assertGreaterEqual(r["high"], 1.5)
        self.assertLessEqual(r["low"], 1.5)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            paired_mean_diff_ci([], [])
        with self.assertRaises(ValueError):
            paired_mean_diff_ci([1.0], [1.0, 2.0])
        with self.assertRaises(ValueError):
            paired_mean_diff_ci(None, [1.0])


class WilsonIntervalTests(unittest.TestCase):
    def test_all_failures_lower_bound_zero(self):
        low, high = wilson_interval(0, 10)
        self.assertEqual(low, 0.0)
        self.assertGreater(high, 0.0)
        self.assertLessEqual(high, 1.0)

    def test_all_successes_upper_bound_one(self):
        low, high = wilson_interval(10, 10)
        self.assertEqual(high, 1.0)
        self.assertGreaterEqual(low, 0.0)
        self.assertLess(low, 1.0)

    def test_symmetric_half(self):
        low, high = wilson_interval(5, 10)
        self.assertAlmostEqual(low + high, 1.0, places=9)
        self.assertLess(low, 0.5)
        self.assertGreater(high, 0.5)

    def test_level_variants(self):
        # 置信水平越高区间越宽：比较宽度而非端点方向。
        lo90, hi90 = wilson_interval(5, 10, level=0.90)
        lo99, hi99 = wilson_interval(5, 10, level=0.99)
        self.assertGreater(hi99 - lo99, hi90 - lo90)

    def test_invalid_inputs(self):
        for args in ((-1, 10), (11, 10), (5, 0), (5, -3), (5.5, 10)):
            with self.assertRaises(ValueError):
                wilson_interval(*args)
        for level in (0.95, 0.97, 0.8, 1.0):
            if level == 0.95:
                continue
            with self.assertRaises(ValueError):
                wilson_interval(5, 10, level=level)


class KsStatisticTests(unittest.TestCase):
    def test_identical_samples_zero(self):
        self.assertEqual(ks_statistic([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 0.0)
        self.assertEqual(ks_statistic([3, 1, 2], [2, 3, 1]), 0.0)

    def test_disjoint_samples_one(self):
        self.assertEqual(ks_statistic([1.0, 2.0], [5.0, 6.0]), 1.0)
        self.assertEqual(ks_statistic([5.0, 6.0], [1.0, 2.0]), 1.0)

    def test_partial_overlap_between_zero_and_one(self):
        d = ks_statistic([1.0, 2.0, 3.0], [2.0, 3.0, 4.0])
        self.assertGreater(d, 0.0)
        self.assertLess(d, 1.0)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            ks_statistic([], [1.0])
        with self.assertRaises(ValueError):
            ks_statistic([1.0], [])


if __name__ == "__main__":
    unittest.main()
