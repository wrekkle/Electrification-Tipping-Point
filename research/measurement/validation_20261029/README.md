# 观测、指标与实验协议（validation_20261029）

类型: 规范
状态: 草案
负责人: tho25
日期: 2026-10-29

本目录是 Agent D 的协议与合成验证产物，对应 [TODO](../../../docs/TODO.md) 的 T10、T9 可行性检查。
只写本目录；原后端、新后端修订目录、采集目录与论文均为只读。登记（TODO/PROGRESS/SECTIONS/阅读登记/配置）由汇总 Agent 完成。

| 文件 | 内容 | 谁能直接用 |
|---|---|---|
| `SPEC_fields.md` | 字段编号 F01–F36、潜在状态 S0–S8、观测误差 E1–E8、站级不区分类 I1–I7、观测等级 L0–L3 | 采集负责人、后端 |
| `SPEC_metrics.md` | q_need/q_plug/q_energy、有限窗口恒等式、指标 M01–M14、决策规则 R1–R4 | 后端、实验设计 |
| `SPEC_experiments.md` | 合成真值、种子、E1–E7、留出与分离、B/C 资格、ETP 口径 | 实验执行者 |
| `code/sim_model.py` | 物理解释层：车位/枪/馈线状态仿真、指标、快照与删减 | 只读复用 |
| `code/run_validation_t14.py` | 当前唯一运行入口（T14/F08 修订，含回归） | 复现命令 |
| `code/run_validation.py` | 旧入口，已弃用：直接运行即退出 2，不写文件 | 仅历史对照 |
| `code/bounds.py` | 采样面积/期初/期末/到达数/q 的分项界与反例 | 后端、实验设计 |
| `code/metric_selftest.py` | 指标公式的固定算例自检 | 回归 |
| `results/` | 历史结果（第一轮，只读，不再被任何入口写入） | 报告引用 |
| `results_t14/` | T14 及后续实验输出（显式 `--out`，与历史结果分离） | 报告引用 |

## 运行

```text
python research/measurement/validation_20261029/code/metric_selftest.py
python research/measurement/validation_20261029/code/run_validation_t14.py \
  --out research/measurement/validation_20261029/results_t14/results_20261029_T14_bounds.json
```

生成物约定：唯一入口 `run_validation_t14.py` 写 `results_t14/`（默认 `results_20261029_T14_bounds.json`），显式 `--out` 可换路径；写入 `results/` 会被拒绝（退出 2）。`results/results_20261029.json` 与 `results/EVIDENCE.md` 是第一轮历史证据，只读、不再被覆盖。旧入口 `run_validation.py` 运行即退出 2。

## 边界

- 本目录里的任何数值都是合成情景结果，不是广州交集场站的实测值。
- 未运行的实验在报告中写“未做”；未证明的推断写“未证”。
- 方法新颖性由贡献查新（Agent C）负责，本协议不声称。