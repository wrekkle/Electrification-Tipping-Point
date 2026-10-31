# 第三轮基线（2026-10-31）

## 解释器

- 主运行/测试：`C:\anaconda\python.exe`（Python 3.12.3，numpy 1.26.4）
- 文档依赖：DSH 运行时 Python（python-docx）
- 采集器：按原 372 场周期运行，本轮只读其 data 目录

## 本轮开始时的源码指纹（SHA-256 前 16 位）

| 文件 | 哈希 |
|---|---|
| apps/parking_lab/workbench/costs.py | 80deefeff615f149 |
| apps/parking_lab/workbench/traffic_gen.py | 63f06d98c9bb3f5d |
| apps/parking_lab/workbench/allocation.py | 89d8a1862b0b5e4d |
| apps/parking_lab/workbench/rules.py | 012ced777e9a668a |
| apps/parking_lab/workbench/prediction.py | 559d1eedc135696b |
| apps/parking_lab/workbench/simulation.py | 146f1408595ea5ef |
| apps/parking_lab/workbench/config.py | a543e8456ec8500d |
| research/traffic_generation_20261031/fitted_parameters.json | 1dfc14a2a29e204d |
| research/round2_20261031/results/analysis_v2_all.json | 00ec8cdc46f9ec98 |
| research/round2_20261031/results/experiments_v2.json | 8d4516c602b51ca4 |

## 冻结对象（本轮只读）

main_paper/、paper/、research/collection/（含 372 场采集器）、第二轮证据与结果 JSON、
fitted_parameters.json、model_20261031.json、旧已交付 cost_curve_pi0_k40.json。

## 数据现状（2026-10-31 13:03 复核）

- 采集数据日期：2026-10-30、2026-10-31（仅两日；多日留出审计见 data_audit.json）
- 可用场站 9 个：train TPE0008/TPE0610/TPE0401/TPE0695/TPE0330；
  validation TPE1376/TPE0930/TPE1171/TPE1380
- 第三轮新结果一律写入 research/round3_20261031/

## 关键基线命令（第二轮终态，本轮回归用）

    python -m unittest discover -s apps/parking_lab/workbench/tests
    python research/round2_20261031/verify_round2.py
    python scripts/check_all.py


## 第三轮结束时源码/产物指纹（2026-10-31）

| 文件 | sha256[:16] |
|---|---|
| traffic_gen.py | 8c47f55f34c3fa0e |
| allocation.py | 5092379ed946487f |
| rules.py | 4654ef1257df62ca |
| simulation.py | 029a75820a941e92 |
| config.py | 4cf6f392b35590dd |
| service_metrics.py（新） | f954e30e8409d1ad |
| run_cost_curve.py | 47e4fedb240c1bec |
| analysis_round3.json | da0e14c2c5360479 |
| expansion_results.json | b2a7d17a8b740d4d |

冻结输入未变：fitted_parameters.json 1dfc14a2、旧 cost_curve_pi0_k40.json 3d77f693、model_20261031.json 75c4f034、第二轮 analysis_v2_all.json 00ec8cdc。
