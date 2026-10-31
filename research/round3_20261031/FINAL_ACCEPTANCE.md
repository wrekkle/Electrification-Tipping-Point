# 第三轮最终验收记录（Lead 亲自复跑）

类型: 验收证据
状态: 生效
负责人: tho25（Lead）
日期: 2026-10-31

解释器：C:\anaconda\python.exe（Python 3.12.3，numpy 1.26.4）；DSH 自带 Python（含 python-docx）。
基线：[BASELINE.md](BASELINE.md)；预登记：[PREREGISTRATION.json](PREREGISTRATION.json)。

## 1 命令与退出码

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| python -m unittest discover -s apps/parking_lab/workbench/tests | 0 | Ran 317 tests, OK |
| python research/round3_20261031/audit_round2.py | 0 | audit_round2.json + CONSISTENCY.md |
| python research/round3_20261031/multiday_audit.py | 0 | data_audit.json（2 日期/307 槽/无完整 24h 日） |
| python research/round3_20261031/run_experiments.py --phase pilot | 0 | 1845 行；final 代码与 pilot 重跑哈希一致 |
| python research/round3_20261031/run_experiments.py --phase tune | 0 | C 7 组 + D 27 组，34 个文件 |
| python research/round3_20261031/analyze_round3.py --select | 0 | C m=0；D charge_arrivals/10/0 |
| python research/round3_20261031/run_experiments.py --phase main --seeds-n 10 | 0 | 4 规则×9 场×10 seed×41 k |
| python research/round3_20261031/analyze_round3.py --plan-expansion | 0 | 67 个待扩展单元（k>40） |
| python research/round3_20261031/expand_search.py | 0 | 45 个达成（k 41–84），22 个到 N/200 仍未达成 |
| python research/round3_20261031/analyze_round3.py --seeds-n 10 | 0 | analysis_round3.json |
| python research/round3_20261031/analyze_round3.py --validation --seeds-n 10 | 0 | analysis_round3_validation.json |
| python research/round3_20261031/analyze_round3.py --scenarios | 0 | analysis_round3_scenarios.json |
| python research/round3_20261031/run_experiments.py --phase pq/power/legacy | 0/0/1 | legacy 单独手跑通过；driver 的 legacy 参数组合失败（见 §4） |
| python research/round3_20261031/verify_round3.py | 0 | 15/15 PASS，verify_round3_report.json |
| python research/round3_20261031/verify_generator_independent.py | 0 | 14/14 PASS（黑盒） |
| python scripts/check_all.py（DSH 内置 3.12.14） | 0 | 错误 0；文档/字数/文献三项通过；94 警告为既有软线/历史 STALE |
| python scripts/check_all.py（anaconda 3.12.3） | 1 | 缺 python-docx（基线既有）；不改用其它 Python 冒充通过 |
| python scripts/lit_index.py --write | 0 | 50 条（P37/M13），错误 0，历史 STALE 警告保留 |

## 2 15 项独立验收（实现与验收公式不同源）

1 independent 生成器（p=0.05 q=0.70 分布/元数据）· 2 legacy 标记 · 3 strict 拒绝 q>1/NaN/缺参 · 4 service_metrics 手算六项+零分母 · 5 config 往返 · 6 规则 C 端点（m=0≡π1、m=k≡π0）· 7 隐藏信息（决策文本无 needs_charge/能量/停留）· 8 独立重算联合 k 与 analysis JSON 一致 · 9 搜索边界状态/整数推荐/no_demand=0 · 10 成本窗口算术 · 11 第二轮审计（8/9、range 22、TPE1171、/365）· 12 多日审计（2 日期/307 槽/不足）· 13 冻结哈希 · 14 文档长度 · 15 rules_v2 更正。

## 3 产物哈希（SHA-256 前 16 位）

| 文件 | 哈希 |
| --- | --- |
| costs.py | 80deefeff615f149 |
| traffic_gen.py | 8c47f55f34c3fa0e |
| allocation.py | 5092379ed946487f |
| rules.py | 4654ef1257df62ca |
| prediction.py | 559d1eedc135696b |
| simulation.py | 029a75820a941e92 |
| config.py | 4cf6f392b35590dd |
| service_metrics.py | f954e30e8409d1ad |
| run_cost_curve.py | 47e4fedb240c1bec |
| analyze_round3.py | da2f64de9c27241c |
| expand_search.py | 3126887ba749b02b |
| verify_round3.py | cc131ac2065070db |
| run_experiments.py | bad27cdd6919a93d |
| analysis_round3.json | da0e14c2c5360479 |
| analysis_round3_validation.json | 8de6d7347021541c |
| analysis_round3_scenarios.json | b3e30f9ee7197e48 |
| expansion_results.json | b2a7d17a8b740d4d |
| audit_round2.json | 31449e2b724a02c0 |
| data_audit.json | 376064ca570ce6ff |
| 第三轮报告 | 51fd280a0a14b46a |

## 4 与预登记的偏差（如实记录）

1. TPE0330 的 k>40 未用整条曲线，改为定向最小 k 搜索（expand_search.py），避免 851 列曲线；结果与主曲线同源同参数。
2. 增加 low/high 需求情景的规则对照（rules_pq，3 seed），属探索性分析，非预登记主比较。
3. C 调参出现所有 m 同分（sum_k=142），按平局规则取 m=0；D 落角点（10 min/0 余量）。
4. driver 的 legacy 阶段因参数组合退出 1；单独命令 legacy_product（p_EV=0.10）成功，正式结果不使用该文件。
5. n=10 由 pilot 统计量按预登记规则得出；pilot 在最终生成器上重跑，流哈希一致。

## 5 冻结边界核对

- main_paper/、paper/、research/collection/（372 场采集器）未写入；采集器继续运行。
- fitted_parameters.json 1dfc14a2、旧 cost_curve_pi0_k40.json 3d77f693、model_20261031.json 75c4f034、第二轮 analysis_v2_all.json 00ec8cdc 均未变（verify_round3 检查 13 通过）。
- 旧报告只追加带日期更正指针；第二轮证据未改写。
