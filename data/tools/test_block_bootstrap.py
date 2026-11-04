"""Unit tests for the moving-block bootstrap engine (block_bootstrap.py)."""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from block_bootstrap import (
    _ar1_series,
    _iid_series,
    mbb_tail_bound,
    mbb_tail_bounds,
    vif_newey_west,
)


class TestBlockBootstrap(unittest.TestCase):
    def test_iid_vif_close_to_one(self):
        """(1) i.i.d. series: VIF should be close to 1 (< 1.3)."""
        vals = _iid_series(365, seed=42)
        vif = vif_newey_west(vals, max_lag=28)
        self.assertLess(vif, 1.3, f"i.i.d. vif too large: {vif}")

    def test_ar1_positive_correlation_vif_gt_1_5(self):
        """(2) AR(1) with positive correlation: VIF > 1.5."""
        vals = _ar1_series(365, rho=0.6, seed=42)
        vif = vif_newey_west(vals, max_lag=28)
        self.assertGreater(vif, 1.5, f"AR(1) vif too small: {vif}")

    def test_deterministic_with_fixed_seed(self):
        """(3) Same seed => identical results across two calls."""
        vals = _iid_series(365, seed=42)
        r1 = mbb_tail_bound(vals, n=0, L=14, B=2000, alpha=0.05, seed=7)
        r2 = mbb_tail_bound(vals, n=0, L=14, B=2000, alpha=0.05, seed=7)
        self.assertEqual(r1, r2)

    def test_iid_bound_matches_normal_approx(self):
        """(4) i.i.d., m=365: bound within 35% relative error of
        p_hat + 1.645*sqrt(p(1-p)/m)."""
        vals = _iid_series(365, seed=42)
        tb = mbb_tail_bound(vals, n=0, L=14, B=5000, alpha=0.05, seed=7)
        p = tb["p_hat"]
        expected = p + 1.645 * math.sqrt(p * (1.0 - p) / 365)
        rel_err = abs(tb["bound"] - expected) / max(expected, 1e-9)
        self.assertLess(rel_err, 0.35, f"rel err {rel_err:.4f} (bound={tb['bound']:.4f}, expected={expected:.4f})")

    def test_all_zero_boundary_is_kept(self):
        """(5) All-zero sample: bound is 0, while P(all zero | p=.02, m=50)=.98^50.

        This is a documented coverage failure, not a property to 'fix': it keeps
        the P4 report honest about n_corr at p_hat=0.
        """
        vals = [0] * 50
        tb = mbb_tail_bound(vals, n=0, L=7, B=2000, alpha=0.05, seed=1)
        self.assertEqual(tb["bound"], 0.0)
        self.assertAlmostEqual(0.98 ** 50, 0.3641696800871171, places=12)
        shared = mbb_tail_bounds(vals, [0, 1], L=7, B=2000, alpha=0.05, seed=1)
        self.assertEqual(shared[0]["bound"], 0.0)
        self.assertEqual(shared[1]["bound"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
