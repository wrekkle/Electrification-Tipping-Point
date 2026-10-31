# 第二轮最终验收记录（Lead 亲自复跑）

类型: 验收证据
状态: 生效
负责人: tho25（Lead）
日期: 2026-10-31

解释器：普通 `C:\\anaconda\\python.exe`（3.12.3，numpy 1.26.4）；DSH 自带 Python（3.12.14，含 python-docx）。
基线见 [BASELINE.md](BASELINE.md)；契约见 [CONTRACT.md](CONTRACT.md)。

## 1 Lead 亲自复跑的命令与退出码

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `python -m unittest discover -s apps/parking_lab/workbench/tests` | **0** | `Ran 281 tests in 7.077s / OK`（基线 216） |
| `python research/round2_20261031/verify_round2.py --curve research/round2_20261031/results/cost_curve_v2_pev030_seeds123.json --analysis research/round2_20261031/results/analysis_v2_all.json` | **0** | `{"passed": 12, "total": 12}`，明细 `verify_round2_report.json` |
| `python scripts/check_all.py`（普通 python） | **1** | 错误 0；仅"稿件字数与章节一致性"未过（缺 python-docx，基线既有，非本轮引入） |
| DSH Python `scripts/check_all.py` | **0** | 文档与链接 / 稿件字数 / 文献索引 三项全通过；错误 0 |
| `python scripts/lit_index.py --write` | **0** | M17 已并入索引；历史 STALE 警告保留（历史记录未改写） |

工作流自验（Lead 未逐条复跑，证据在各 REPORT/日志）：R2-A `verify_fix 43/43 + test_costs 63/63`；R2-B 修复前 0/8→后 8/8、`verify_v2 8/8`、test_traffic_gen 18/18；R2-C `repro_pre_fix 7 失败→post_fix 0`、test_allocation 69/69；R2-D `recompute_model_v2 EXIT=0（problems=[]）`；R2-E `run_rules_v2 exit 0（5226 runs/492.6s）`、test_type_rules 30/30。

## 2 12 项独立验收（修复器与验收器不同公式/来源）

1 成本窗口（k=0/1/2、半日换算、缺参）· 2 14kWh 需求/交付 7/缺口 7 · 3 平稳长度偏置暖启动（14.13 vs 14.61，n=150）· 4 模型 v2 可行域/不相容拒绝 · 5 搜索状态（不返回伪推荐）· 6 Erlang 闭式+同 α+dwell 占位 952min · 7 分母（零需求/删失/期初）· 8 三类占位守恒 · 9 隐藏信息不泄漏 · 10 外生需求不变性（k/功率/馈线）· 11 代理成本拆分与 null 传播 · 12 独立枚举 k*(L=100)+样本外误差（achieved-only）。

全部 PASS；不可判项：事件型 k5 低分母方差（U0=1–14，seed 间摆 2–6）未做 bootstrap；解析式只对照 π0；规则社会成本比较因缺参不可判；无多日数据。

## 3 产物哈希（SHA-256 前 16 位）

| 文件 | 哈希 |
| --- | --- |
| apps/parking_lab/workbench/costs.py | 80deefeff615f149 |
| apps/parking_lab/workbench/traffic_gen.py | 63f06d98c9bb3f5d |
| apps/parking_lab/workbench/allocation.py | 89d8a1862b0b5e4d |
| apps/parking_lab/workbench/rules.py | 012ced777e9a668a |
| apps/parking_lab/workbench/simulation.py | 146f1408595ea5ef |
| apps/parking_lab/workbench/config.py | a543e8456ec8500d |
| research/traffic_generation_20261031/fitted_parameters.json（冻结） | 1dfc14a2a29e204d |
| research/integer_allocation_20261031/outputs/cost_curve_pi0_k40.json（旧，未改） | 3d77f693a8d5514b |
| research/calibration/charging_probability_20261030/model_20261031.json（v1，未改） | 75c4f03498398cde |
| research/calibration/charging_probability_20261030/model_20261031_v2.json（新） | 628be14cee01e524 |
| research/round2_20261031/results/cost_curve_v2_pev030_seeds123.json（新曲线） | 081de1c074e212fb |
| research/round2_20261031/results/analysis_v2_all.json | 00ec8cdc46f9ec98 |
| research/round2_20261031/results/experiments_v2.json | 8d4516c602b51ca4 |
| docs/reports/2026-10-31-整数配桩规则与仿真验证.md（旧 1109553f3102fa5a，本轮按任务追加 §14 更正） | aa78fd624a5325d6 |

## 4 冻结边界核对

- `main_paper/`、`paper/`、`research/collection/`（372 场采集器）本轮未写入；采集器与名册未动。
- 旧交付 JSON（`cost_curve_pi0_k40.json`、`analysis_pi0.json`、`final_tables.json`、`model_20261031.json`、`fitted_parameters.json`、`parameter_candidates_20261031.json`）保留未改，哈希与基线一致或未变；新结果全部落在 `research/round2_20261031/` 与 `*_v2`。
- 主报告仅按任务追加 §14 更正并修正 §10 手算错误；旧稿件未改。
