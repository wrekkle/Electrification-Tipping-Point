# 情景参数账本与声明/运行覆盖差异（R8-F 3/3）

类型: 研究分析
状态: 生效（2026-10-31）
证据: experiments/run_meta.json、experiments_main22/run_meta.json、contract provenance、experiments_declared22/（补跑中）

## 1 声明 vs 实际运行（已更正：不存在 4 枪上限或 0.10 份额覆盖）


engine-b 的硬件审计（experiments_declared22/hardware_audit.json）核对了 runner.py:62-67 的 SCENARIO_DEFAULTS：
该默认块**只在站点缺四字段时生效**（runner.py:115 site_capability）。契约 10 个场站四字段齐全，
resolved capability 的 derived_fields 为空，因此**默认块未生效**：7 kW 与 main22 运行的硬件就是契约声明的
20% 充电位、connectors=bays、feeder=connectors×kW；main22 只强行覆盖 connector_kw=22 与 feeder=k×22。
k 网格能达到声明的 charging_bays（最大 16）也证明没有被 4 枪上限截断。

因此此前"运行器用了 0.10 份额/4 枪上限"的判断是错的（我此前只读了 run_meta 的 parameters 默认块，没有核对
应用条件），已在正文 §4.3 与本节更正。run_meta 的 parameters 块应读作"记录在案的默认值"，不是实际生效值。

### 1.1 declared22 复核运行结果（合同硬件，22 kW）

| 量 | k=1（预注册压力点） | k=声明 charging_bays |
|---|---|---|
| 接入 | 52/137（37.96%） | 136/137（99.3%）；gate 0，no-connector 1 |
| 交付/需求 kWh | 365.7/1891.0（19.34%） | 984.2/1891.0（52.05%） |
| 短会话（dwell<required） | — | 80/137 |
| capacity_only_unmet 均值 | — | 58.35% |
| 三约束可行性 | 不可行 | 不可行（限制来自能量/停留） |

结论：低接入只出现在 k=1 的人为保守设计点；把 k 设到声明充电位数后接入≈99%，瓶颈是"停留时间内交付
声明能量"（52% 可交付），不是连接器数量。access-only 补充诊断仍只作补充口径。
