# 第四轮最终验收记录（Lead 亲自复跑）

类型: 验收证据
状态: 生效
负责人: tho25（Lead）
日期: 2026-10-31
证据目录: research/round4_20261031/

解释器：C:\anaconda\python.exe（Python 3.12.3）；DSH 内置 Python 3.12.14（含 python-docx，用于 check_all）。

## 1 命令与退出码

| 命令 | 退出码 | 结果 |
|---|---|---|
| python research/round4_20261031/data_trace.py | 0 | 20 项：19 pass / 1 unverified / 0 fail；catalog sha 331caf84… |
| python research/round4_20261031/run_scenarios.py --catalog … | 0 | 15/15 情景曲线；每文件 1025 行；failures=0 |
| python research/round4_20261031/eval_fixed_k.py --catalog … | 0 | 40/40 固定 k 运行 |
| python research/round4_20261031/run_dwell.py --catalog … | 0 | 9/9 停留情景曲线 |
| python research/round4_20261031/run_tradeoff_fixedk.py | 0 | 12 单元×34 配置=408 次固定 k 重跑 |
| python research/round4_20261031/analyze_round4.py | 0 | analysis_round4.json |
| python research/round4_20261031/verify_round4.py | 0 | 11/11 PASS，verify_round4_report.json |
| python -m unittest discover -s apps/parking_lab/workbench/tests | 0 | Ran 345 tests, OK |
| python research/round3_20261031/verify_round3.py | 0 | 15/15 PASS（旧证据仍通过） |
| DSH Python scripts/check_all.py | 0 | 文档/字数/文献三项通过；错误 0，警告 98 为既有软线/失效链接 |
| anaconda scripts/check_all.py | 1 | 缺 python-docx（既有环境差异，不改用其它解释器冒充） |

## 2 第四轮 11 项独立验收

1 来源目录与校验（6 情景、REF/M08/M10、q_use→q_need 假设迁移）；2 runner provenance（1025 行、catalog/record 哈希、p/q 值）；3 5 情景 Δk 独立重算（全 0、无正）；4 fixed-k 选择/评价种子不相交、40 运行、分析与重算一致；5 固定 k 共同 k 差值；6 dwell ±20%（9 对全 0）；7 固定 k C/D 权衡（408 次、无省枪）；8 数据审计结构与 19/1/0；9 原子写（成功无 .tmp、NaN 失败无 result/空目录、已有目录不覆盖）；10 真实 socket HTTP 防护（bind/Host/Origin/traversal/NaN/413/重复 CL）；11 冻结哈希与文档长度。

安全独立复核：sim-rules 实现 10 项修复（17 安全测试），ev-data 以非实现者身份只读复核 F11 原子写、全量测试、临时目录反例与非法 Host；Lead 的 verify_round4.py 另以独立代码复验。

## 3 关键数值

- 来源情景：REF/M08-BEV/M08-COMBINED/M10 可达 20/25，all-away 21/25；所有情景 Δk 中位 0、正 Δk=0；绝对 k 相对 REF：BEV 中位 0、COMBINED 0、M10 0（均值 −0.7）、all-away 中位 −3（均值 −4.85）。
- 固定 k 独立种子（48 单元）：A 可行 36，B 34，D 35；容量未服务 A 5.02%、B 6.49%、D 5.36%；EV 停车 A 0.19%、B 0.69%、D 0.19%；ICE A 0.99%、B 0.70%、D 0.90%。
- 固定 k 共同 k：π1 容量 +2.00 pp、EV +0.50 pp、ICE −0.29 pp；π2 +0.35 pp、0、−0.10 pp。
- 固定 k 权衡（12 训练单元，A k）：A 容量 0/EV 0/ICE 0.165%；C 全部 m 为 0/0/0.0825%（同 k 弱支配 A），D 最好与 A 同；无配置省枪。
- 停留 ±20%：9 对 Δk 全 0；绝对 k 中位 −1/0。
- 机制枚举：双方可行 1532 例 Δk>0=0；禁止 EV 回落时 641/1328 正；单调性反例 16/3456，未证定理。

## 4 产物哈希（SHA-256 前 16 位）

| 文件 | 哈希 |
|---|---|
| charge_sources.py | 541A1979A8E18F2D |
| traffic_gen.py | D29BAF51E74608E9 |
| experiments.py（原子写） | 9158D0E4F9FCA945 |
| server.py | 6C164E216B7FA2BF |
| datasource.py | 08EBF8E4775A4210 |
| test_security_round4.py | A2B354A06D8627AD |
| test_round4_atomic.py | C7A798A9E923D149 |
| run_cost_curve.py | 3B2241C2D91E7C76 |
| charge_probability_sources.json | 331CAF842EBFE60A |
| data_trace.py | D1B0B743569E9707 |
| data_trace.json | 6C2AF9B0B5D5E3E9 |
| WIRING.md | 7080CDC1C055D0A7 |
| scenario_manifest.json | B1A12A84CF05B3CD |
| analysis_round4.json | E39C936E5C5F72EF |
| tradeoff_fixedk.json | 577C9EF86483E5D9 |
| fixedk_manifest.json | 8A7089AFA92B0D2B |
| dwell_manifest.json | E7872A90488B9443 |
| round3_claims_audit.json | 849E17B4A943FF76 |
| shared_capacity_mechanism.json | 3B1F60C11AABD261 |
| verify_round4.py | 985EDB0B90615920 |
| 第四轮报告 | 11CA39A53F7A6BA1 |

冻结输入核对：fitted_parameters 1dfc14a2、旧曲线 3d77f693、model v1 75c4f034、第二轮 analysis 00ec8cdc 未变（verify_round4/verify_round3 均检查）。

## 5 剩余限制

1. p_EV/q_need 目标值不可识别；所有 q 情景是 q_use→q_need 假设迁移，不是目标场景识别值。
2. 只有两日数据（307 槽/25.75h），无完整 24h 日；不做整日留出、周末/季节声明。
3. 未服务损失 null，只有设施成本，无社会最优/福利排序。
4. cost_scenario 文档 per_connector_day 与公式差 0.0027%（UNVERIFIED）；结果用公式值。
5. REF 复跑 feeder 120（第三轮 336）；3 个 lot-seed 的 demand_hash 与第三轮不一致（UNVERIFIED），情景比较只在第四轮内部。
6. N1/M18 全文未取得（10 次合法尝试）；N1 模型细节只能摘要级。
7. 安全：F11 未 fsync 父目录；未做并发/中断故障注入；一次 test_http 瞬时 ERROR 未复现；ledger 内存无上限。
8. 能量约束只沿用第三轮有限网格；本轮未重跑功率/能量全网格。

## 6 复现顺序

先 data_trace，再 run_scenarios（可 --force 重跑），再 eval_fixed_k、run_dwell、run_tradeoff_fixedk、analyze_round4、verify_round4；最后 unittest 与 check_all（DSH Python）。所有结果在 research/round4_20261031/results/。
