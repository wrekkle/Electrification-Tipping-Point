"""allocation 模块的手算算例、边界与 None 传播测试（纯标准库，不调用仿真）。

第二轮（R2-D5/D6/D7）新增：服务水平状态搜索、分批扩展、占位口径 dwell/legacy 对照、
Erlang-B 独立闭式求和校验（不照抄递推）与同 alpha 解析/整数对照。
"""
import ast
import inspect
import math
import unittest

from apps.parking_lab.workbench import allocation
from apps.parking_lab.workbench.allocation import (
    budgeted_service_search, compare_rounding, erlang_b, erlang_b_closed_form,
    evaluate_integer_costs, integer_recommendation, mean_connector_load,
    min_servers_for_blocking, regret, rounding_candidates, service_level_k,
)


class MeanConnectorLoadTests(unittest.TestCase):
    def test_hand_computed_dwell_case(self):
        # dwell（默认）：占位=全部 EV 停留时长；充电时长不缩短占位（充满不释放枪）
        result = mean_connector_load(120.0, 0.25, 0.5, 30.0, 60.0)
        self.assertAlmostEqual(result["lambda_ev_hour"], 30.0)
        self.assertAlmostEqual(result["lambda_charge_hour"], 15.0)
        self.assertAlmostEqual(result["mean_connector_minutes"], 60.0)
        self.assertAlmostEqual(result["offered_load_erlang"], 30.0)
        self.assertEqual(result["occupancy_model"], "dwell")
        self.assertIs(result["legacy"], False)

    def test_second_hand_computed_dwell_case(self):
        result = mean_connector_load(90.0, 0.2, 1.0 / 3.0, 40.0, 100.0)
        self.assertAlmostEqual(result["lambda_ev_hour"], 18.0)
        self.assertAlmostEqual(result["lambda_charge_hour"], 6.0)
        self.assertAlmostEqual(result["mean_connector_minutes"], 100.0)
        self.assertAlmostEqual(result["offered_load_erlang"], 30.0)

    def test_charge_model_is_legacy_control(self):
        legacy = mean_connector_load(120.0, 0.25, 0.5, 30.0, 60.0, occupancy_model="charge")
        self.assertAlmostEqual(legacy["mean_connector_minutes"], 45.0)
        self.assertAlmostEqual(legacy["offered_load_erlang"], 22.5)
        self.assertEqual(legacy["occupancy_model"], "charge")
        self.assertIs(legacy["legacy"], True)
        second = mean_connector_load(90.0, 0.2, 1.0 / 3.0, 40.0, 100.0, occupancy_model="charge")
        self.assertAlmostEqual(second["mean_connector_minutes"], 80.0)
        self.assertAlmostEqual(second["offered_load_erlang"], 24.0)

    def test_legacy_understates_place_load(self):
        # charge 口径相对 dwell 只会低估：q_need 处充电时长更短，充完也不释放枪
        for need in (0.0, 0.2, 0.5, 1.0):
            dwell = mean_connector_load(50.0, 1.0, need, 20.0, 80.0)
            charge = mean_connector_load(50.0, 1.0, need, 20.0, 80.0, occupancy_model="charge")
            with self.subTest(need=need):
                self.assertAlmostEqual(dwell["mean_connector_minutes"], 80.0)
                self.assertAlmostEqual(charge["mean_connector_minutes"],
                                       need * 20.0 + (1.0 - need) * 80.0)
                self.assertLessEqual(charge["offered_load_erlang"], dwell["offered_load_erlang"])

    def test_returns_exactly_six_documented_keys(self):
        result = mean_connector_load(10.0, 0.1, 0.2, 30.0, 90.0)
        self.assertEqual(set(result), {"lambda_ev_hour", "lambda_charge_hour",
                                       "mean_connector_minutes", "offered_load_erlang",
                                       "occupancy_model", "legacy"})

    def test_rejects_unknown_occupancy_model(self):
        for bad in ("Dwell", "parking", "", None, 1):
            with self.subTest(model=bad), self.assertRaises(ValueError):
                mean_connector_load(1.0, 0.5, 0.5, 10.0, 20.0, occupancy_model=bad)

    def test_zero_arrival_and_share_edges(self):
        zero = mean_connector_load(0.0, 0.5, 1.0, 30.0, 60.0)
        self.assertEqual(zero["offered_load_erlang"], 0.0)
        no_ev = mean_connector_load(50.0, 0.0, 0.0, 30.0, 60.0)
        self.assertEqual(no_ev["lambda_ev_hour"], 0.0)
        self.assertEqual(no_ev["offered_load_erlang"], 0.0)
        all_charge = mean_connector_load(60.0, 1.0, 1.0, 30.0, 999.0)
        self.assertAlmostEqual(all_charge["mean_connector_minutes"], 999.0)
        all_park = mean_connector_load(60.0, 1.0, 0.0, 999.0, 45.0)
        self.assertAlmostEqual(all_park["mean_connector_minutes"], 45.0)
        legacy_all_charge = mean_connector_load(60.0, 1.0, 1.0, 30.0, 999.0,
                                                occupancy_model="charge")
        self.assertAlmostEqual(legacy_all_charge["mean_connector_minutes"], 30.0)

    def test_rejects_non_finite_and_negative(self):
        valid = [120.0, 0.25, 0.5, 30.0, 60.0]
        for index in range(len(valid)):
            for bad in (-1.0, float("nan"), float("inf"), float("-inf")):
                args = list(valid)
                args[index] = bad
                with self.subTest(index=index, bad=bad), self.assertRaises(ValueError):
                    mean_connector_load(*args)

    def test_rejects_shares_outside_unit_interval(self):
        for index in (1, 2):
            for bad in (1.0001, -0.0001):
                args = [120.0, 0.25, 0.5, 30.0, 60.0]
                args[index] = bad
                with self.subTest(index=index, bad=bad), self.assertRaises(ValueError):
                    mean_connector_load(*args)


class ErlangBTests(unittest.TestCase):
    def test_known_values(self):
        self.assertAlmostEqual(erlang_b(1.0, 1), 0.5)
        self.assertAlmostEqual(erlang_b(2.0, 1), 2.0 / 3.0)
        self.assertAlmostEqual(erlang_b(1.0, 2), 0.2)
        self.assertAlmostEqual(erlang_b(2.0, 2), 0.4)
        self.assertEqual(erlang_b(0.0, 7), 0.0)
        self.assertEqual(erlang_b(0.0, 1), 0.0)

    def test_recursion_matches_closed_form(self):
        for load in (0.5, 1.0, 3.7, 12.0):
            previous = 1.0
            for servers in range(1, 9):
                expected = (load * previous) / (servers + load * previous)
                self.assertAlmostEqual(erlang_b(load, servers), expected)
                previous = expected

    def test_monotone_decreasing_in_servers(self):
        values = [erlang_b(3.5, servers) for servers in range(1, 12)]
        self.assertLessEqual(values[0], 1.0)
        for left, right in zip(values, values[1:]):
            self.assertLess(right, left)
        self.assertGreaterEqual(values[-1], 0.0)

    def test_invalid_inputs(self):
        for servers in (0, -1, 2.5, True, "3", None):
            with self.subTest(servers=servers), self.assertRaises(ValueError):
                erlang_b(1.0, servers)
        for load in (-1.0, float("nan"), float("inf"), "2"):
            with self.subTest(load=load), self.assertRaises(ValueError):
                erlang_b(load, 1)


class ErlangBClosedFormTests(unittest.TestCase):
    """R2-D7：用独立闭式求和校验 Erlang-B 递推，不照抄同一递推。"""

    def test_six_decimal_hand_values(self):
        # 手算：B(0.5,1)=1/3、B(1,1)=0.5、B(2,2)=0.4、B(5,3)=0.529661
        cases = ((0.5, 1, 0.333333), (1.0, 1, 0.500000),
                 (2.0, 2, 0.400000), (5.0, 3, 0.529661))
        for load, servers, expected in cases:
            with self.subTest(load=load, servers=servers):
                self.assertEqual(round(erlang_b(load, servers), 6), expected)
                self.assertEqual(round(erlang_b_closed_form(load, servers), 6), expected)

    def test_b_5_3_four_decimal_reference(self):
        self.assertEqual(round(erlang_b(5.0, 3), 4), 0.5297)

    def test_independent_factorial_sum_matches(self):
        # 直接按 B=(a^c/c!)/sum_{n=0..c}a^n/n! 求和（独立于递推与 lgamma 闭式）
        for load in (0.25, 1.0, 2.5, 7.0, 20.0):
            for servers in range(1, 16):
                terms = [load ** n / math.factorial(n) for n in range(servers + 1)]
                expected = terms[-1] / math.fsum(terms)
                with self.subTest(load=load, servers=servers):
                    self.assertAlmostEqual(erlang_b(load, servers), expected, places=13)
                    self.assertAlmostEqual(erlang_b_closed_form(load, servers), expected, places=13)

    def test_large_load_does_not_overflow(self):
        for load in (40.0, 120.0, 250.0):
            servers = int(load + 3 * math.sqrt(load)) + 1
            with self.subTest(load=load):
                closed = erlang_b_closed_form(load, servers)
                self.assertGreater(closed, 0.0)
                self.assertAlmostEqual(closed, erlang_b(load, servers), places=12)

    def test_zero_load(self):
        self.assertEqual(erlang_b_closed_form(0.0, 1), 0.0)
        self.assertEqual(erlang_b_closed_form(0.0, 9), 0.0)

    def test_invalid_inputs(self):
        for load in (-1.0, float("nan"), float("inf"), "2", True):
            with self.subTest(load=load), self.assertRaises(ValueError):
                erlang_b_closed_form(load, 1)
        for servers in (0, -1, 2.5, True, None):
            with self.subTest(servers=servers), self.assertRaises(ValueError):
                erlang_b_closed_form(1.0, servers)


class MinServersTests(unittest.TestCase):
    def test_hand_computed_case(self):
        self.assertEqual(min_servers_for_blocking(2.0, 0.5, 10), 2)
        self.assertEqual(min_servers_for_blocking(1.0, 0.5, 5), 1)

    def test_zero_load_returns_zero_servers(self):
        # R3-B：零需求不应推荐 1 台；负荷为 0 时任何 k_max/target 下都是 0 台
        for target in (0.1, 0.5, 0.9):
            for k_max in (1, 5, 60):
                with self.subTest(target=target, k_max=k_max):
                    self.assertEqual(min_servers_for_blocking(0.0, target, k_max), 0)

    def test_first_feasible_boundary(self):
        cases = ((2.0, 0.5, 20), (4.0, 0.01, 40), (12.5, 0.02, 60), (0.4, 0.9, 10))
        for load, target, k_max in cases:
            servers = min_servers_for_blocking(load, target, k_max)
            self.assertIsNotNone(servers)
            self.assertLessEqual(erlang_b(load, servers), target)
            for smaller in range(1, servers):
                self.assertGreater(erlang_b(load, smaller), target)

    def test_returns_none_beyond_k_max(self):
        self.assertIsNone(min_servers_for_blocking(10.0, 1e-9, 3))
        self.assertIsNone(min_servers_for_blocking(25.0, 0.001, 5))

    def test_invalid_inputs(self):
        for target in (0.0, 1.0, -0.1, 1.5, float("nan")):
            with self.subTest(target=target), self.assertRaises(ValueError):
                min_servers_for_blocking(2.0, target, 10)
        for k_max in (0, -2, 3.5):
            with self.subTest(k_max=k_max), self.assertRaises(ValueError):
                min_servers_for_blocking(2.0, 0.1, k_max)
        with self.assertRaises(ValueError):
            min_servers_for_blocking(-1.0, 0.1, 10)


class ServiceLevelKTests(unittest.TestCase):
    """R2-D5/R3-B：未达标不得返回 max(by_k)；状态/边界/缺参/搜索边界按契约返回。"""

    STATUSES = {"achieved", "no_demand", "budget_exhausted", "infeasible_upper_bound", "missing_data"}
    BOUND_KINDS = {"achieved", "user_bound", "engineering_bound", "budget_exhausted",
                   "no_demand", "missing_data"}
    KEYS = {"status", "k", "alpha", "evaluated_max", "baseline", "note", "boundary", "bound_kind"}

    @staticmethod
    def curve(values):
        return {k: {"unmet_no_connector_events": value} for k, value in values.items()}

    def assert_status(self, result, status, *, k, evaluated_max, baseline, bound_kind,
                      boundary=None):
        self.assertEqual(set(result), self.KEYS)
        self.assertIn(result["status"], self.STATUSES)
        self.assertEqual(result["status"], status)
        self.assertIn(result["bound_kind"], self.BOUND_KINDS)
        self.assertEqual(result["bound_kind"], bound_kind)
        self.assertEqual(result["k"], k)
        self.assertEqual(result["evaluated_max"], evaluated_max)
        if baseline is None:
            self.assertIsNone(result["baseline"])
        else:
            self.assertAlmostEqual(result["baseline"], baseline)
        self.assertIsInstance(result["note"], str)
        self.assertTrue(result["note"])
        self.assertIsInstance(result["boundary"], bool)
        if boundary is not None:
            self.assertIs(result["boundary"], boundary)
        if k is not None:
            self.assertIsInstance(result["k"], int)

    def test_achieved_mid_curve(self):
        result = service_level_k(self.curve({0: 10.0, 1: 9.0, 2: 8.0, 3: 1.0, 4: 0.4}),
                                 0.05, search_max=6)
        self.assert_status(result, "achieved", k=4, evaluated_max=4, baseline=10.0,
                           bound_kind="achieved", boundary=False)
        self.assertAlmostEqual(result["alpha"], 0.05)

    def test_achieved_exactly_at_search_max_sets_boundary(self):
        result = service_level_k(self.curve({0: 10.0, 1: 9.0, 2: 8.0, 3: 1.0, 4: 0.4}),
                                 0.05, search_max=4)
        self.assert_status(result, "achieved", k=4, evaluated_max=4, baseline=10.0,
                           bound_kind="achieved", boundary=True)

    def test_default_bound_is_by_k_max_and_engineering(self):
        achieved = service_level_k(self.curve({0: 10.0, 1: 9.0, 2: 0.1}), 0.05)
        self.assert_status(achieved, "achieved", k=2, evaluated_max=2, baseline=10.0,
                           bound_kind="achieved", boundary=True)
        infeasible = service_level_k(self.curve({0: 10.0, 1: 9.0, 2: 8.0}), 0.05)
        self.assert_status(infeasible, "infeasible_upper_bound", k=None, evaluated_max=2,
                           baseline=10.0, bound_kind="engineering_bound", boundary=False)
        self.assertIsNone(infeasible["k"])  # 不得用 max(by_k)=2 冒充推荐

    def test_reaching_search_max_marks_user_bound(self):
        by_k = self.curve({0: 10.0, 1: 8.0, 2: 5.0})
        for search_max in (1, 2):
            with self.subTest(search_max=search_max):
                result = service_level_k(by_k, 0.05, search_max=search_max)
                self.assert_status(result, "infeasible_upper_bound", k=None,
                                   evaluated_max=search_max, baseline=10.0,
                                   bound_kind="user_bound", boundary=False)

    def test_search_max_beyond_data_is_budget_exhausted(self):
        result = service_level_k(self.curve({0: 10.0, 1: 8.0, 2: 5.0}), 0.05, search_max=5)
        self.assert_status(result, "budget_exhausted", k=None, evaluated_max=2,
                           baseline=10.0, bound_kind="budget_exhausted", boundary=False)
        self.assertIn("5", result["note"])

    def test_budget_max_limits_evaluation(self):
        by_k = self.curve({0: 10.0, **{k: 10.0 - 0.1 * k for k in range(1, 11)}})
        result = service_level_k(by_k, 0.05, search_max=10, budget_max=3)
        self.assert_status(result, "budget_exhausted", k=None, evaluated_max=3,
                           baseline=10.0, bound_kind="budget_exhausted", boundary=False)
        # 预算内达标正常返回；恰好落在预算上限也不算 boundary
        achieved = service_level_k(self.curve({0: 10.0, 1: 9.0, 2: 8.0, 3: 0.4}),
                                   0.05, search_max=10, budget_max=3)
        self.assert_status(achieved, "achieved", k=3, evaluated_max=3, baseline=10.0,
                           bound_kind="achieved", boundary=False)
        limited_out = service_level_k(self.curve({0: 10.0, 1: 9.0, 2: 8.0, 3: 0.4}),
                                      0.05, search_max=10, budget_max=2)
        self.assert_status(limited_out, "budget_exhausted", k=None, evaluated_max=2,
                           baseline=10.0, bound_kind="budget_exhausted", boundary=False)

    def test_threshold_boundary_uses_le(self):
        # alpha*U(0)=1.0 恰等于 U(1)，按 <= 判定达标（边界数值不算未达标）
        result = service_level_k(self.curve({0: 10.0, 1: 1.0}), 0.1)
        self.assert_status(result, "achieved", k=1, evaluated_max=1, baseline=10.0,
                           bound_kind="achieved", boundary=True)

    def test_no_demand_returns_k_zero(self):
        result = service_level_k(self.curve({0: 0.0, 1: 0.0, 2: 0.0}), 0.05)
        self.assert_status(result, "no_demand", k=0, evaluated_max=2, baseline=0.0,
                           bound_kind="no_demand", boundary=False)

    def test_missing_baseline_and_middle_row(self):
        missing_baseline = service_level_k(self.curve({1: 1.0, 2: 0.0}), 0.05)
        self.assert_status(missing_baseline, "missing_data", k=None, evaluated_max=2,
                           baseline=None, bound_kind="missing_data", boundary=False)
        gap = service_level_k(self.curve({0: 10.0, 1: 8.0, 3: 5.0}), 0.05)
        self.assert_status(gap, "missing_data", k=None, evaluated_max=3, baseline=10.0,
                           bound_kind="missing_data", boundary=False)
        self.assertIn("k=2", gap["note"])

    def test_none_row_and_missing_key_are_missing_data(self):
        for by_k in ({0: {"unmet_no_connector_events": 10.0}, 1: None},
                     {0: {"unmet_no_connector_events": 10.0}, 1: {"other": 1.0}}):
            with self.subTest(by_k=by_k):
                result = service_level_k(by_k, 0.05)
                self.assert_status(result, "missing_data", k=None, evaluated_max=1,
                                   baseline=10.0, bound_kind="missing_data", boundary=False)

    def test_custom_key_scalar_and_metric_alias(self):
        records = {0: {"unserved_events": 10.0}, 1: {"unserved_events": 0.4}}
        self.assertEqual(service_level_k(records, 0.05, key="unserved_events")["k"], 1)
        self.assertEqual(service_level_k({0: 10.0, 1: 0.4}, 0.05)["k"], 1)
        # 兼容第二轮 rules_v2 harness 的 metric= 别名
        self.assertEqual(service_level_k(records, 0.05, metric="unserved_events")["k"], 1)

    def test_legacy_k_hard_max_alias_keeps_old_behavior(self):
        by_k = self.curve({0: 10.0, 1: 9.0, 2: 8.0, 3: 1.0, 4: 0.4})
        achieved = service_level_k(by_k, 0.05, k_hard_max=4)
        self.assert_status(achieved, "achieved", k=4, evaluated_max=4, baseline=10.0,
                           bound_kind="achieved", boundary=True)
        exhausted = service_level_k(self.curve({0: 10.0, 1: 8.0, 2: 5.0}), 0.05,
                                    k_hard_max=5)
        self.assert_status(exhausted, "budget_exhausted", k=None, evaluated_max=2,
                           baseline=10.0, bound_kind="budget_exhausted", boundary=False)
        with self.assertRaises(ValueError):
            service_level_k(by_k, 0.05, search_max=4, k_hard_max=5)

    def test_invalid_inputs(self):
        self.assertAlmostEqual(service_level_k({0: 10.0, 1: 0.4}, 0.2)["alpha"], 0.2)
        for alpha in (0.0, -0.1, 1.5, float("nan"), True, "0.05"):
            with self.subTest(alpha=alpha), self.assertRaises(ValueError):
                service_level_k({0: 10.0, 1: 1.0}, alpha)
        for bad in ({1.5: 1.0}, {-1: 1.0}, {"1": 1.0}, {0: float("nan")},
                    {0: -1.0}, {0: "x"}, [1, 2], None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                service_level_k(bad, 0.05)
        with self.assertRaises(ValueError):
            service_level_k({0: 10.0}, 0.05, key="")
        for name in ("search_max", "budget_max", "k_hard_max"):
            for bad in (-1, 2.5, True):
                with self.subTest(name=name, bad=bad), self.assertRaises(ValueError):
                    service_level_k({0: 10.0}, 0.05, **{name: bad})


class BudgetedServiceSearchTests(unittest.TestCase):
    """R2-D5：budgeted_service_search 分批扩展，返回与 service_level_k 相同的状态结构。"""

    def test_expands_until_achieved(self):
        calls = []

        def evaluate(k):
            calls.append(k)
            return max(0.0, 10.0 - 0.5 * k)

        result = budgeted_service_search(evaluate, 0.05, 4, 20)
        self.assertEqual(set(result), ServiceLevelKTests.KEYS)
        self.assertEqual(result["status"], "achieved")
        self.assertEqual(result["k"], 19)
        self.assertIs(result["boundary"], False)
        self.assertEqual(result["evaluated_max"], 20)
        self.assertEqual(calls, list(range(21)))

    def test_expands_to_hard_upper_bound_then_infeasible(self):
        calls = []

        def evaluate(k):
            calls.append(k)
            return 10.0

        result = budgeted_service_search(evaluate, 0.05, 2, 8)
        self.assertEqual(result["status"], "infeasible_upper_bound")
        self.assertEqual(result["bound_kind"], "user_bound")
        self.assertIsNone(result["k"])
        self.assertEqual(result["evaluated_max"], 8)
        self.assertEqual(calls, list(range(9)))

    def test_batch_limits_double(self):
        calls = []

        def evaluate(k):
            calls.append(k)
            return 10.0

        budgeted_service_search(evaluate, 0.05, 3, 12)
        # 批次上限 3 -> 6 -> 12，每批评估到上限（含）
        self.assertEqual(calls, list(range(13)))

    def test_stops_within_initial_budget(self):
        calls = []

        def evaluate(k):
            calls.append(k)
            return max(0.0, 10.0 - 100.0 * k)

        result = budgeted_service_search(evaluate, 0.05, 4, 20)
        self.assertEqual(result["k"], 1)
        self.assertEqual(calls, [0, 1, 2, 3, 4])

    def test_no_demand(self):
        result = budgeted_service_search(lambda k: 0.0, 0.05, 2, 8)
        self.assertEqual(result["status"], "no_demand")
        self.assertEqual(result["k"], 0)

    def test_none_evaluation_is_missing_data(self):
        result = budgeted_service_search(lambda k: None if k == 2 else 10.0, 0.05, 3, 8)
        self.assertEqual(result["status"], "missing_data")
        self.assertIsNone(result["k"])

    def test_boundary_achievement_at_hard_upper_bound(self):
        result = budgeted_service_search(lambda k: max(0.0, 10.0 - 0.5 * k), 0.05, 4, 19)
        self.assertEqual(result["status"], "achieved")
        self.assertEqual(result["k"], 19)
        self.assertIs(result["boundary"], True)

    def test_record_evaluation_uses_default_key(self):
        result = budgeted_service_search(
            lambda k: {"unmet_no_connector_events": max(0.0, 10.0 - 0.5 * k)}, 0.05, 4, 20)
        self.assertEqual(result["k"], 19)

    def test_search_max_keyword_marks_user_bound(self):
        calls = []

        def evaluate(k):
            calls.append(k)
            return 10.0

        result = budgeted_service_search(evaluate, 0.05, 2, search_max=8)
        self.assertEqual(result["status"], "infeasible_upper_bound")
        self.assertEqual(result["bound_kind"], "user_bound")
        self.assertIsNone(result["k"])
        self.assertEqual(result["evaluated_max"], 8)
        self.assertEqual(calls, list(range(9)))

    def test_budget_max_exhausted_returns_status_not_fake_k(self):
        calls = []

        def evaluate(k):
            calls.append(k)
            return 10.0

        result = budgeted_service_search(evaluate, 0.05, 2, search_max=8, budget_max=5)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["bound_kind"], "budget_exhausted")
        self.assertIsNone(result["k"])
        self.assertEqual(result["evaluated_max"], 5)
        self.assertEqual(calls, list(range(6)))

    def test_budget_max_at_least_search_max_still_reaches_bound(self):
        calls = []

        def evaluate(k):
            calls.append(k)
            return 10.0

        result = budgeted_service_search(evaluate, 0.05, 2, search_max=8, budget_max=12)
        self.assertEqual(result["status"], "infeasible_upper_bound")
        self.assertEqual(result["evaluated_max"], 8)
        self.assertEqual(calls, list(range(9)))

    def test_initial_batch_above_budget_is_clamped(self):
        calls = []

        def evaluate(k):
            calls.append(k)
            return 10.0

        result = budgeted_service_search(evaluate, 0.05, 4, search_max=8, budget_max=2)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertIsNone(result["k"])
        self.assertEqual(result["evaluated_max"], 2)
        self.assertEqual(calls, [0, 1, 2])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            budgeted_service_search(None, 0.05, 2, 8)
        for initial, hard in ((0, 8), (2.5, 8), (9, 8), (1, 0), (True, 8)):
            with self.subTest(initial=initial, hard=hard), self.assertRaises(ValueError):
                budgeted_service_search(lambda k: 1.0, 0.05, initial, hard)
        with self.assertRaises(ValueError):
            budgeted_service_search(lambda k: 1.0, 0.05, 2)  # 缺搜索上限
        with self.assertRaises(ValueError):
            budgeted_service_search(lambda k: 1.0, 0.05, 2, 4, search_max=8)  # 上限冲突
        with self.assertRaises(ValueError):
            budgeted_service_search(lambda k: 1.0, 0.05, 9, search_max=8)  # 初始批超上限
        for bad in (-1, 2.5, True):
            with self.subTest(budget_max=bad), self.assertRaises(ValueError):
                budgeted_service_search(lambda k: 1.0, 0.05, 2, search_max=8, budget_max=bad)
        with self.assertRaises(ValueError):
            budgeted_service_search(lambda k: 1.0, 0.0, 2, 8)
        with self.assertRaises(ValueError):
            budgeted_service_search(lambda k: -1.0, 0.05, 2, 8)
        with self.assertRaises(ValueError):
            budgeted_service_search(lambda k: "x", 0.05, 2, 8)


class ErlangAnalyticSameAlphaTests(unittest.TestCase):
    """R2-D6/D7：解析 k 与整数服务水平搜索必须在同一 alpha 下对照，且结果一致。"""

    def test_service_level_k_equals_erlang_rule_at_same_alpha(self):
        for load in (0.4, 2.0, 8.7, 24.0):
            for alpha in (0.02, 0.05, 0.10, 0.20):
                by_k = {0: {"unmet_no_connector_events": 1.0}}
                by_k.update({k: {"unmet_no_connector_events": erlang_b(load, k)}
                             for k in range(1, 61)})
                expected = min_servers_for_blocking(load, alpha, 60)
                result = service_level_k(by_k, alpha, k_hard_max=60)
                with self.subTest(load=load, alpha=alpha):
                    if expected is None:
                        self.assertEqual(result["status"], "infeasible_upper_bound")
                        self.assertIsNone(result["k"])
                    else:
                        self.assertEqual(result["status"], "achieved")
                        self.assertEqual(result["k"], expected)

    def test_analytic_rule_uses_dwell_load_not_charge_load(self):
        # 同一输入下 dwell 负荷更大会给出更大的 k；charge 口径仅作 legacy 对照
        dwell = mean_connector_load(10.0, 1.0, 0.2, 30.0, 90.0)
        charge = mean_connector_load(10.0, 1.0, 0.2, 30.0, 90.0, occupancy_model="charge")
        k_dwell = min_servers_for_blocking(dwell["offered_load_erlang"], 0.05, 60)
        k_charge = min_servers_for_blocking(charge["offered_load_erlang"], 0.05, 60)
        self.assertEqual(dwell["offered_load_erlang"], 15.0)
        self.assertAlmostEqual(charge["offered_load_erlang"], 13.0)
        self.assertGreater(k_dwell, k_charge)


class IntegerRecommendationTests(unittest.TestCase):
    """R3-B：逐种子整数 k 汇总为可安装推荐；None 只给下界，非整数中位数不得冒充安装值。"""

    KEYS = {"per_seed", "median", "q90", "recommended_k", "status", "note"}

    def test_integral_median_is_installable(self):
        result = integer_recommendation([14, 10, 12], 40)
        self.assertEqual(set(result), self.KEYS)
        self.assertEqual(result["per_seed"], [14, 10, 12])
        self.assertEqual(result["median"], 12)
        self.assertEqual(result["q90"], 14)
        self.assertEqual(result["recommended_k"], 12)
        self.assertIsInstance(result["recommended_k"], int)
        self.assertEqual(result["status"], "ok")
        self.assertIsInstance(result["note"], str)

    def test_non_integral_median_marked_not_installable(self):
        result = integer_recommendation([8, 9], 40)
        self.assertEqual(result["median"], 8.5)
        self.assertEqual(result["status"], "statistical_summary_not_installable")
        self.assertEqual(result["note"], "statistical_summary_not_installable")
        self.assertEqual(result["recommended_k"], 9)  # 向上取整，避免少配
        self.assertIsInstance(result["recommended_k"], int)

    def test_any_none_seed_forces_lower_bound(self):
        result = integer_recommendation([10, None, 12], 40)
        self.assertIsNone(result["recommended_k"])
        self.assertEqual(result["status"], "lower_bound")
        self.assertIn("cap+X 下界", result["note"])
        self.assertIn("下界", result["note"])
        self.assertIn("41", result["note"])  # cap+1
        self.assertIn("cap=40", result["note"])

    def test_all_none_has_no_median(self):
        result = integer_recommendation([None, None], 40)
        self.assertIsNone(result["recommended_k"])
        self.assertIsNone(result["median"])
        self.assertIsNone(result["q90"])
        self.assertEqual(result["status"], "lower_bound")

    def test_empty_input_is_missing_data(self):
        result = integer_recommendation([], 40)
        self.assertIsNone(result["recommended_k"])
        self.assertIsNone(result["median"])
        self.assertEqual(result["status"], "missing_data")

    def test_single_seed(self):
        result = integer_recommendation([15], 40)
        self.assertEqual((result["median"], result["q90"], result["recommended_k"]), (15, 15, 15))
        self.assertEqual(result["status"], "ok")

    def test_q90_nearest_rank(self):
        result = integer_recommendation([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 40)
        self.assertEqual(result["median"], 5.5)
        self.assertEqual(result["q90"], 9)  # ceil(0.9*10)=9 -> 升序第 9 个
        self.assertEqual(result["status"], "statistical_summary_not_installable")
        self.assertEqual(result["recommended_k"], 6)
        self.assertIsInstance(result["recommended_k"], int)

    def test_tuple_input_and_cap_zero_note(self):
        result = integer_recommendation((10, 12), 0)
        self.assertEqual(result["per_seed"], [10, 12])
        self.assertEqual(result["recommended_k"], 11)
        bound = integer_recommendation([None, 3], 0)
        self.assertIn("1", bound["note"])  # cap+1 = 1

    def test_invalid_inputs(self):
        for cap in (-1, 2.5, True, None, "40"):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                integer_recommendation([1], cap)
        for per_seed in (None, "1,2", {1: 2}, 1):
            with self.subTest(per_seed=per_seed), self.assertRaises(ValueError):
                integer_recommendation(per_seed, 40)
        for bad in (1.5, True, "3", -1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                integer_recommendation([1, bad], 40)


class IntegerCostTests(unittest.TestCase):
    def test_tie_best_and_non_decreasing_deltas(self):
        report = evaluate_integer_costs({1: 10.0, 2: 8.0, 3: 8.0, 4: 12.0})
        self.assertEqual(report["best_k"], [2, 3])
        self.assertEqual(report["best_cost"], 8.0)
        self.assertEqual(report["deltas"], {1: -2.0, 2: 0.0, 3: 4.0})
        self.assertIs(report["marginal_non_decreasing"], True)
        self.assertEqual(report["feasible_k"], [1, 2, 3, 4])

    def test_marginal_not_non_decreasing(self):
        report = evaluate_integer_costs({1: 0.0, 2: 10.0, 3: 15.0})
        self.assertEqual(report["deltas"], {1: 10.0, 2: 5.0})
        self.assertIs(report["marginal_non_decreasing"], False)

    def test_single_delta_has_undefined_marginal(self):
        report = evaluate_integer_costs({2: 4.0, 3: 3.0})
        self.assertEqual(report["deltas"], {2: -1.0})
        self.assertIsNone(report["marginal_non_decreasing"])

    def test_none_breaks_delta_pairs(self):
        report = evaluate_integer_costs({1: None, 2: 5.0, 3: 4.0, 4: None})
        self.assertEqual(report["feasible_k"], [2, 3])
        self.assertEqual(report["best_k"], [3])
        self.assertEqual(report["best_cost"], 4.0)
        self.assertEqual(report["deltas"], {2: -1.0})
        self.assertIsNone(report["marginal_non_decreasing"])

    def test_gap_in_keys_still_makes_deltas(self):
        report = evaluate_integer_costs({1: 5.0, 2: 4.0, 4: 1.0})
        self.assertEqual(report["deltas"], {1: -1.0})
        self.assertEqual(report["feasible_k"], [1, 2, 4])
        self.assertEqual(report["best_k"], [4])

    def test_empty_and_all_none(self):
        empty = {"best_k": [], "best_cost": None, "deltas": {},
                 "marginal_non_decreasing": None, "feasible_k": []}
        self.assertEqual(evaluate_integer_costs({}), empty)
        self.assertEqual(evaluate_integer_costs({1: None, 2: None}), empty)

    def test_negative_and_zero_costs_allowed(self):
        report = evaluate_integer_costs({0: -5.0, 1: 0.0})
        self.assertEqual(report["best_k"], [0])
        self.assertEqual(report["best_cost"], -5.0)
        self.assertEqual(report["deltas"], {0: 5.0})
        self.assertIsNone(report["marginal_non_decreasing"])

    def test_invalid_inputs(self):
        for costs in ({1.5: 1.0}, {"1": 1.0}, {-1: 1.0}, {1: float("nan")},
                      {1: float("inf")}, {1: "x"}, [1, 2], None):
            with self.subTest(costs=costs), self.assertRaises(ValueError):
                evaluate_integer_costs(costs)


class RoundingTests(unittest.TestCase):
    def test_hand_values(self):
        self.assertEqual(rounding_candidates(1.5), [1, 2])
        self.assertEqual(rounding_candidates(2.5), [2, 3])
        self.assertEqual(rounding_candidates(2.0), [2])
        self.assertEqual(rounding_candidates(1.2), [1, 2])
        self.assertEqual(rounding_candidates(2.4), [2, 3])
        self.assertEqual(rounding_candidates(0.5), [0, 1])
        self.assertEqual(rounding_candidates(0.0), [0])

    def test_floor_round_ceil_dedup(self):
        for value in (0.4, 1.0, 1.49, 1.5, 1.51, 7.0, 12.999):
            candidates = rounding_candidates(value)
            self.assertEqual(candidates, sorted(set(candidates)))
            for expected in (math.floor(value), math.floor(value + 0.5), math.ceil(value)):
                self.assertIn(expected, candidates)

    def test_invalid_inputs(self):
        for value in (-0.5, -1.0, float("nan"), float("inf"), "1.5", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rounding_candidates(value)


class CompareRoundingTests(unittest.TestCase):
    def test_zero_gap_when_candidates_contain_global_best(self):
        report = compare_rounding({1: 10.0, 2: 8.0, 3: 9.0}, 2.4)
        self.assertEqual(report["k_cont"], 2.4)
        self.assertEqual(report["candidates"], {2: 8.0, 3: 9.0})
        self.assertEqual(report["best_among_candidates"], [2])
        self.assertEqual(report["global_best"], [2])
        self.assertEqual(report["selection_gap"], 0.0)

    def test_positive_selection_gap(self):
        report = compare_rounding({1: 10.0, 2: 8.0, 4: 5.0}, 1.2)
        self.assertEqual(report["candidates"], {1: 10.0, 2: 8.0})
        self.assertEqual(report["best_among_candidates"], [2])
        self.assertEqual(report["global_best"], [4])
        self.assertEqual(report["selection_gap"], 3.0)

    def test_none_and_missing_candidates(self):
        report = compare_rounding({2: None, 3: 7.0}, 1.5)
        self.assertEqual(report["candidates"], {1: None, 2: None})
        self.assertEqual(report["best_among_candidates"], [])
        self.assertIsNone(report["selection_gap"])
        self.assertEqual(report["global_best"], [3])

    def test_candidate_ties(self):
        report = compare_rounding({1: 4.0, 2: 4.0}, 1.5)
        self.assertEqual(report["best_among_candidates"], [1, 2])
        self.assertEqual(report["selection_gap"], 0.0)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            compare_rounding({1: 1.0}, -0.5)
        with self.assertRaises(ValueError):
            compare_rounding({1: float("nan")}, 1.0)
        with self.assertRaises(ValueError):
            compare_rounding({}, float("inf"))


class RegretTests(unittest.TestCase):
    def test_hand_values(self):
        costs = {1: 10.0, 2: 8.0, 3: 8.0}
        report = regret(costs, 1)
        self.assertEqual(report["recommended_k"], 1)
        self.assertEqual(report["cost"], 10.0)
        self.assertEqual(report["best_cost"], 8.0)
        self.assertEqual(report["regret"], 2.0)
        self.assertEqual(report["regret_ratio"], 0.25)
        optimal = regret(costs, 2)
        self.assertEqual(optimal["regret"], 0.0)
        self.assertEqual(optimal["regret_ratio"], 0.0)

    def test_none_propagation(self):
        report = regret({1: 10.0, 2: None}, 2)
        self.assertIsNone(report["cost"])
        self.assertIsNone(report["regret"])
        self.assertIsNone(report["regret_ratio"])
        self.assertEqual(report["best_cost"], 10.0)
        missing = regret({1: 10.0}, 5)
        self.assertIsNone(missing["cost"])
        self.assertIsNone(missing["regret"])
        self.assertEqual(regret({}, 1)["best_cost"], None)

    def test_ratio_undefined_for_non_positive_best(self):
        negative = regret({1: -5.0, 2: -3.0}, 2)
        self.assertEqual(negative["regret"], 2.0)
        self.assertIsNone(negative["regret_ratio"])
        zero = regret({1: 0.0, 2: 3.0}, 2)
        self.assertEqual(zero["regret"], 3.0)
        self.assertIsNone(zero["regret_ratio"])

    def test_invalid_inputs(self):
        for recommended in (1.5, -1, True, None):
            with self.subTest(recommended=recommended), self.assertRaises(ValueError):
                regret({1: 1.0}, recommended)
        with self.assertRaises(ValueError):
            regret({1: float("nan")}, 1)


class PurityTests(unittest.TestCase):
    def test_imports_only_standard_library(self):
        source = inspect.getsource(allocation)
        modules = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or "").split(".")[0])
        self.assertEqual(modules, {"__future__", "math"})

    def test_public_functions_documented(self):
        names = ("mean_connector_load", "erlang_b", "erlang_b_closed_form",
                 "min_servers_for_blocking", "service_level_k", "budgeted_service_search",
                 "integer_recommendation", "evaluate_integer_costs", "rounding_candidates",
                 "compare_rounding", "regret")
        for name in names:
            function = getattr(allocation, name)
            self.assertTrue(callable(function))
            self.assertTrue(function.__doc__ and function.__doc__.strip(), name)


if __name__ == "__main__":
    unittest.main()
