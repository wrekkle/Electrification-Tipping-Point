# 第二轮修复基线快照（2026-10-31）

类型: 研究记录
状态: 生效
负责人: tho25（Lead）
日期: 2026-10-31

本文件冻结第二轮开工前的解释器、版本、关键输入哈希与基线命令结果。后续所有新结果必须与这里的哈希对照，旧 JSON 不覆盖。

## 1 解释器与环境

| 项 | 值 |
| --- | --- |
| 主解释器 | C:\anaconda\python.exe（Python 3.12.3, conda-forge） |
| 数值库 | numpy 1.26.4 |
| 带 python-docx 的解释器 | C:\Users\tho25\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe（Python 3.12.14） |
| 本地 Qwen | http://127.0.0.1:8081（/health ok；单并发） |
| 采集器 | 固定 372 场台北采集器保持运行，本轮只读、不重启、不改名册 |

## 2 基线命令与结果（修复前）

    python -m unittest discover -s apps/parking_lab/workbench/tests     -> Ran 216 tests, OK, EXIT=0
    python scripts/check_all.py                                         -> EXIT=1（错误 0；仅"稿件字数与章节一致性"因缺 python-docx）
    "C:\Users\tho25\.dsh\...\python.exe" scripts/check_all.py        -> EXIT=0（三项全通过）

## 3 关键输入/源码哈希（修复前，SHA-256 前 16 位）

| 文件 | 字节 | sha256[:16] |
| --- | ---: | --- |
| apps/parking_lab/workbench/costs.py | 38,766 | 9a727717eb62316c |
| apps/parking_lab/workbench/traffic_gen.py | 17,611 | 52dabaad74a6d89b |
| apps/parking_lab/workbench/rules.py | 16,308 | 501f21a2c9e9493b |
| apps/parking_lab/workbench/prediction.py | 3,730 | 2f2c1fc4298d41e8 |
| apps/parking_lab/workbench/allocation.py | 9,534 | 8f17ecb287a302de |
| apps/parking_lab/workbench/simulation.py | 28,262 | 146f1408595ea5ef |
| apps/parking_lab/workbench/config.py | 17,330 | ce673e1e33852abd |
| research/traffic_generation_20261031/fitted_parameters.json | 187,613 | 1dfc14a2a29e204d |
| research/integer_allocation_20261031/outputs/cost_curve_pi0_k40.json | 5,639,559 | 3d77f693a8d5514b |
| research/integer_allocation_20261031/cost_scenario.json | 2,993 | 6ac1e3dbf0a0658c |
| research/cost_model_20261030/parameter_candidates_20261031.json | 73,891 | 5076501832ed3528 |
| research/calibration/charging_probability_20261030/model_20261031.json | 36,102 | 75c4f03498398cde |
| docs/reports/2026-10-31-整数配桩规则与仿真验证.md | 20,652 | 1109553f3102fa5a |

## 4 已确认缺陷（本轮修复对象）

| 编号 | 缺陷 | 影响 |
| --- | --- | --- |
| R2-D1 | costs.py 资本折旧不乘设备数（k=0 仍计 31.998 TWD/日） | 成本口径错误，设施成本依赖 runner 私算 |
| R2-D2 | occupancy_minutes 旧字段把油车占枪混入"非充电电车占枪" | 三类占位口径失真 |
| R2-D3 | traffic_gen 用 min(需求, 可交付) 提前削减 energy_kwh | 需求被削，缺口被掩盖 |
| R2-D4 | 暖启动用普通停留分布再 U(0,D) 取剩余 | 期初在场占用分布有偏 |
| R2-D5 | service_level_k 未达标时返回 max(by_k) | 把预算截断伪装成推荐 k |
| R2-D6 | mean_connector_load 对有需求 EV 用充电时长，与"充满不释放枪"冲突 | 解析近似系统性低估 |
| R2-D7 | 报告与模块的 Erlang-B 手算不一致（B(1,1) 应为 0.5） | 文档错误 |
| R2-D8 | 识别边界表述过强（0.0364 被称"可识别乘积"） | 结论边界失真 |

## 5 冻结/只读清单

- main_paper/、paper/、research/collection/、research/integer_allocation_20261031/outputs/*.json（旧）、
  research/traffic_generation_20261031/fitted_parameters.json（旧本体，新拟合另存）、
  research/calibration/.../model_20261031.json、research/cost_model_20261030/parameter_candidates_20261031.json。
- 旧报告不删除；新结论写入 docs/reports/2026-10-31-第二轮修复与复算.md，并在主报告追加"更正与影响"段。
