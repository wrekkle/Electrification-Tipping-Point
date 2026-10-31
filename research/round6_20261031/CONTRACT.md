# 第六轮接口契约（CONTRACT）

状态: 生效
日期: 2026-10-31
适用: A（仿真接口）、B（机制/可行域）、C（论文）、Lead（验收）

## 1 指标语义入口

模块：`apps/parking_lab/workbench/service_semantics.py`（新文件，A 实现）
导出至少：

```python
RATE_STATES = ("valid", "not_applicable_zero_demand", "censored_no_departure", "missing", "illegal")

def classify_rate(name, row) -> dict:
    # {"status": ..., "value": float|None, "numerator": ..., "denominator": ...,
    #  "reason": str, "source": str}
```

规则：
- 分母=0 且对应需求计数=0 → `not_applicable_zero_demand`；
- 离场能量率分母 `departed_requested_kwh=0` 且 `exogenous_charge_requests>0` → `censored_no_departure`；
- 分母>0 但 rate 缺失/None → `missing`；非有限、越界、类型错 → `illegal`；
- 只有 `valid` 且 ≤α 才可判“约束满足”；N/A 与 censored 不得判成功；missing/illegal 不得跳过判 achieved。
- 旧 `analyze_round3.joint_k` 不改写；新分析一律调用本入口。兼容性测试须证明：既有 59 条曲线上“N/A 视为通过”的结论与旧审计 780/975 一致（口径不漂移）。

## 2 信息条件接口

模块：`apps/parking_lab/workbench/info_regimes.py`（新文件，A 实现）
- `I0`：行为与现有正式规则完全一致（默认路径字节级/数值级不变）。
- `I1`：analysis_only=True；仅把当次到访 `needs_charge` 暴露给标记为 analysis-only 的策略；不得暴露未来到达、真实离场、能量等。
- 输出 JSON 顶层必须含 `information_regime`、`analysis_only`、`policy_kind`（"real_rule" | "analysis_heuristic"）与 `can_mimic_I0` 说明。
- 信息泄漏测试：现实规则上下文不含 needs_charge；I1 上下文仅多该字段；错误权限抛错。
- I1 若只实现少量启发式，报告只能写“算法比较/信息上界示例”，不得写“I0/I1 全局最优”。

## 3 固定轨迹与输出

- 场站/种子/参数：见 PLAN §4；k 完整枚举 0..40；每条结果带 lot、seed、rule、k、information_regime、analysis_only、command、interpreter、input hashes、workers。
- 可行集合定义：K={k∈[0,40]：三项约束（capacity_only_unmet_rate、ev_parking_failure_rate、ice_parking_failure_rate）均 ≤0.05}；集合形状字段：`is_interval`、`min_known_feasible`、`confirmed_minimal`（k_min>0 或完整枚举且 k_min−1 不可行才 true）、`truncated_at_kmax`、`empty_set`。
- 四类可行性：both / only_I0 / only_I1 / neither；另加 `undecidable`（censored/missing 主导时）。
- 规则语义：π0 允许 EV 回落普通位（当前实现）；strict_pi0（禁止回落）只作机制对照，明确标注变体。

## 4 写范围

- A：`apps/parking_lab/workbench/service_semantics.py`、`info_regimes.py`、必要的最小修改（`simulation.py`/`rules.py`/`config.py` 仅当无法在新增模块实现时，且须保持默认数值不变），tests `apps/parking_lab/workbench/tests/test_round6_*.py`，`research/round6_20261031/a_*/`。
- B：`research/round6_20261031/b_*/` 只读导入 workbench，不写 apps/。
- C：`paper/draft/` 新文件、`research/round6_20261031/c_*/`；不写 apps/、literature/index、旧 Word。
- Lead：`research/round6_20261031/PLAN.md/REPORT.md`、docs/TODO/PROGRESS/SECTIONS、最终验收。

## 5 禁止事项

不启动 RL；不扩城；不覆盖冻结原稿、旧 Word、旧原始数据、已有交付 JSON 与前五轮证据；不改采集器；不生成对外沟通稿；不编造未核页码/式号/定理；不把模拟反例写成真实停车场实测规律；不把有限枚举称普遍证明；不把条件配置称社会最优。
