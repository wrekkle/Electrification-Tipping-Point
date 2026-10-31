# qwen_handchecks — 独立数学手算模块（round2, 2026-10-31）

纯标准库、不 import apps/ 下任何模块，用于对被检对象的关键数值做独立复算。

## 文件

- handcheck_math.py — 五个可复用纯函数
- test_handcheck_math.py — unittest 断言（13 条）

## 函数与关键数值

| 函数 | 公式 | 参考值 |
|---|---|---|
| erlang_b_closed_form(load, servers) | C=(a^c/c!)/Σ_{n=0..c} a^n/n!，闭式求和、无递推 | (0.5,1)=1/3；(1,1)=0.5；(2,2)=0.4；(5,3)=0.5297（6 位内） |
| stationary_residual_mean(dwell_values, probs) | E[D²]/(2E[D])，长度偏置平稳剩余寿命 | {1:0.5, 9:0.5} → 4.1 |
| charge_gap(demand_kwh, power_kw, dwell_min) | delivered=min(需求, 功率×时长/60)，返回 (delivered, gap) | (14,7,60) → (7, 7) |
| facility_cost_per_window(k, capex, life_years, maintenance_per_bay_day, window_min) | k×(capex/(life×365)+maint)×window_min/1440：资本按天摊销再按窗口比例折算，维护同为每日值×窗口比例 | (2, 116792.62, 10, 43.29969863, 720) → 75.2977（2 位内） |
| service_status(baseline_unmet, curve, hard_limit=40) | 五态判定，返回 (status, k) | 见下 |

service_status 规则（curve 为 {k: unmet}）：
1. baseline_unmet == 0 → ("no_demand", 0)
2. curve 缺 k=0 → ("missing_data", None)
3. 存在 unmet ≤ 0 的最小 k → ("achieved", k)
4. 无达标且已检查到硬上限（默认 40）→ ("infeasible_upper_bound", None)
5. 未达上限但预算用尽 → ("budget_exhausted", None)

## 测试

命令（项目根目录执行）：

```text
python -m unittest discover -s research/round2_20261031/qwen_handchecks -p "test_*.py"
```

结果：**Ran 13 tests ... OK**，退出码 0。

## 实现要点

- Erlang B 严格闭式：逐项 a^n/n! 直接计算，不用递推；servers≥1 校验。
- stationary_residual_mean 接受 dict {dwell: prob} 或两个并行序列（probs 可选）。
- facility_cost_per_window 的资本项是 capex/(life_years×365) 每日摊销 × window_min/1440，
  与每日维护同口径相加后乘 k——这是唯一能复现参考值 75.2977 的口径
  （年摊销口径会得到 23401.82，不符）。
- service_status 先判 no_demand，再判 missing_data，然后取最小达标 k；
  infeasible 与 budget_exhausted 的分界是 max(curve.keys()) 是否 ≥ hard_limit。
