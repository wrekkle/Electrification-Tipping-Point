# 第四轮充电概率正式接线记录（2026-10-31）

类型: 证据说明
状态: 生效
负责人: tho25（Lead 集成）
证据: research/round4_20261031/results/scenario_manifest.json、各 scenario_*.json、fixedk/、dwell/

## 1 结论

第三轮正式 manifest 的 64 条命令均未读取 M08/M10（data_trace C11/C13 的“未接线”仅指第三轮）。第四轮新入口把带来源元数据的充电概率情景接入正式曲线：

- 入口：research/integer_allocation_20261031/run_cost_curve.py --charge-catalog <catalog> --charge-scenario <id>；
- 目录：research/round4_20261031/charge_probability_sources.json，catalog sha256 331caf842ebfe60a27df4b9d3c32823190ae0770dc86c08d9646d0e57b477f1c；
- 每条结果行带 charge_scenario_id 与 charge_provenance（source_id、version、probability_object、分子/分母/事件定义、地区/时期/车型/地点、transfer、限制、catalog_sha256、record_sha256、identification_status）；
- 结果文档 meta 同时记录 catalog 路径与完整 provenance；p_EV 与 q_need 分别指定，legacy 固定乘积未用于本轮。

## 2 正式运行清单

scenario_manifest.json 15 条（5 情景 × 3 规则），全部 exit 0，全部命令含 --charge-catalog 与 --charge-scenario；每个结果 1025 行（5 场站 × 5 种子 × 41 k），failures=0。fixed-k（40 条）与 dwell（9 条）同样经 catalog 的 REF 情景运行。

| scenario_id | probability_object | p_EV | q_need | identification |
|---|---|---:|---:|---|
| REF | q_need | 0.10 | 0.36 | historical_reference_not_identified |
| M08-NEAR-BEV | q_use | 0.10 | 0.285685564938 | hypothetical_scenario_transfer_not_target_identified |
| M08-NEAR-COMBINED | q_use | 0.10 | 0.263477506506 | hypothetical_scenario_transfer_not_target_identified |
| M10-OUT-OF-HOME | q_use | 0.10 | 0.236998424051 | hypothetical_scenario_transfer_not_target_identified |
| M08-ALL-AWAY-REF | q_use | 0.10 | 0.071340856504 | hypothetical_scenario_transfer_not_target_identified |

## 3 必须保留的限制

1. 这些 q 值来自 M08/M10 的观察使用率（q_use），不是目标场景的潜在需求 q_need；转用是显式假设性迁移，只作情景/敏感性，不是识别值。
2. M08 的“附近 300 英尺”停车事件不等于进入带枪车位；M10 是荷兰 2017 年自报调查；两者分母、地区、车型、年份均不同。
3. p_EV=0.10 没有目标场景识别证据，五个情景统一固定它是为了隔离 q 的来源变化，不代表真实到访份额。
4. 不允许把这些数值简单平均，也不允许把 M14 的 0.4 地点份额当 q_use/q_need。
5. 所有结果保留 catalog/record哈希；catalog 内容改变会使 record/catalog 哈希变化，历史结果不覆盖。
