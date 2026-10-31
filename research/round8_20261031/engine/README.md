# R8-B engine：公开数据接口、基线、离线界与 E1–E7 机器输出

负责人：engine-b（task-2）。本目录只新增文件，不改 apps/parking_lab/workbench 已有模块。

## 文件

| 文件 | 职责 |
|---|---|
| `synth.py` | 合成契约 fixture（**不是真实数据**，只用于跑通链路与自测） |
| `baselines.py` | B0 FCFS / B1 固定配额 / B2 文献改编；`BaselineSimulation` 子类只覆写 `choose_bay` |
| `offline_opt.py` | 小实例离线最小 k：0..K_max 完整枚举 + 分钟网格 max-flow + 可构造排程证书 |
| `minimality.py` | k 最小性五分类（confirmed_minimal / minimality_unconfirmed / physically_infeasible / budget_not_covered / missing_data） |
| `runner.py` | E1–E7 评价、k 曲线、配对重放、能量结算、manifest |
| `run_phase1.py` | 入口：自测 + 合成 fixture 冒烟 + 真实契约 E1–E7 + missing_data 空壳 |

配套新模块（apps/parking_lab/workbench/）：
`publicdata.py`（契约校验/场站-日切分/经验重采样/覆盖度）、`energy_ledger.py`（能量服务结算）。
单测：`apps/parking_lab/workbench/tests/test_publicdata.py`、`tests/test_energy_ledger.py`。

## 统一事件契约（v1）

```
{"schema_version": "public_parking_events/v1", "dataset_id": str,
 "sites": [{"site_id", "n_spaces", "charging_bays?", "connectors?",
            "connector_kw?", "feeder_kw?"}],
 "events": [{"event_id?", "site_id", "arrival_ts", "dwell_min" 或 "departure_ts",
             "is_ev", "needs_charge?", "energy_kwh?"}],
 "coverage": {"complete_days": {"<site_id>": ["YYYY-MM-DD", ...]}}}   # 可选
```

- 时间戳必须带时区偏移（`+08:00` / `Z`）；naive 时间戳按缺失处理（不猜时区）。
- 缺容量/缺充电字段只记 `missing_data`，不阻断读取：E1（到达/停留）仍可跑，
  E3/E6 会按 missing_data 分列，不伪造。
- CSV 交付：`publicdata.load_csv_contract(path, column_map={...}, sites=[...],`
  `tz_offset_minutes=..., default_is_ev=...)`。列名必须显式映射，不做猜测；
  本地 naive 时间按固定偏移补全（不做 DST 推断），该假设写入 provenance。

## 口径（与 PLAN §3 对齐）

- 统计单位 = 场站-日 / 独立流；重采样次数不是样本量；5 分钟快照不当独立样本。
- 留出：测试 = 留出场站全部日 + 其余场站的留出整日；与训练块不重叠。
- k 全枚举 0..K_max，不二分（无单调性证明）；离线结果标
  `information = offline_upper_bound_not_executable`。
- 离线最小性在声明模型 `offline_uniform_power_minute_grid` 内成立：
  每枪功率恒为 `min(connector_kw, feeder_kw/k)`、抢占式、1 分钟网格。
  因此 `confirmed_minimal` **不是物理下界**，E3 输出带 `evidence_model` 列。
- 能量结算分子分母逐条记录；被拒请求留在分母/缺口；不假设离场后免费补能；
  仍删失、零需求、初始车辆、缺失、非法分列。
- 选择（训练集定 k、B1 的 p_share、B2 参数）与测试分离；测试不达标如实记
  `feasible_3constraints = False`。

## 运行

    # 合成 fixture 冒烟 + 自测（输出在 experiments/_phase1_smoke_synthetic/）
    python research/round8_20261031/engine/run_phase1.py --mode synthetic --seed 20261031

    # 数据未到位：给 E1–E7 写 missing_data 空壳（不伪造数字）
    python research/round8_20261031/engine/run_phase1.py --mode auto

    # 数据到位：读 processed 契约，产出真实 E1–E7
    python research/round8_20261031/engine/run_phase1.py --mode data \
        --contract research/round8_20261031/data/processed/<contract>.json

每个族目录含 `manifest.json`（命令/种子/输入哈希/输出哈希/输出版本）；
根目录 `run_meta.json` 记录切分、预注册 k、E3 分类计数与 M1–M3 结果。

## 当前状态（2026-10-31）

- 阶段1 已完成并在合成 fixture 上跑通：engine 自测 41 项通过、新模块单测 42 项通过；
  E1–E7 机器输出均可生成（E7 合成 fixture 内无非单调反例 → missing_data，不伪造）。
- 阶段2 待 data/processed 统一契约文件；当前目录只有 interim `_window_events.csv`
  （Melbourne bay-level，无容量/无 EV 字段），尚不构成 v1 契约。
