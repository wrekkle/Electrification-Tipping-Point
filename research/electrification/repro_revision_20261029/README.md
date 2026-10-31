# PREI 复现后端（研究代码）

本目录是论文 `research/electrification/` 静态基线（P0）、事件层（P1）与统计/报告层（P2）的可运行实现，
只写本目录，不改原稿、历史文件与 `main_paper/`。原稿 MATLAB 代码与补充材料不可得，这是独立重写，不是原程序。
当前状态：一键运行、44 条单元测试通过、固定种子可复现；与原稿报告数值**未对齐**，偏差与归因见
`docs/reports/2026-10-29-后端复现报告.md`。

## 修订副本（2026-10-29）

本目录是 `research/electrification/repro/` 的修订副本，只实现 R1–R7 修复，原目录只读未改。
- 修复内容、时间单位契约、统计口径与剩余风险：[CHANGES.md](CHANGES.md)
- 复制来源与 SHA-256：[PROVENANCE.json](PROVENANCE.json)
- 修复前回归：`before_regressions.log`；修复后：`after_unittest.log`
- 重算基线：`outputs_revision/`（显式 `--out` 且 `--no-canonical`，未碰原 canonical 产物）

下方原文保留为**修订前状态**；其中"候选集不含 m=0""两个场地只差随机种子""CVaR 取尾均值"
等描述已过时，以 CHANGES.md 为准。

## 环境

- Python：`C:\Users\tho25\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`（3.12.14）
- 依赖：numpy 2.3.5、pandas 3.0.1；不依赖 PyYAML、scipy、pytest（自带 YAML 子集解析器与 unittest）
- 运行时需要把依赖目录加入 PYTHONPATH：

```powershell
$env:PYTHONPATH='C:\Users\tho25\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\Lib\site-packages'
```

## 一键运行

```powershell
Set-Location 'research/electrification/repro'
& 'C:\Users\tho25\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe' run_all.py --mode all --seed 42
```

- 输出目录：默认 `outputs/<config>/canonical-seed<seed>/`；每次运行先把旧的正式目录移入
  `outputs/_archive/<config>/`，只保留一个 canonical 产物。加 `--no-canonical` 可保留时间戳目录。
- 修订副本实测：**242 s**（默认 Python 3.12.3 / numpy 1.26.4；300 天 × 2 场地 × 10 个 r 网格点，g 不变号故无加密点）。原副本记录为 379 s。
- `--mode static` 只跑 P0；`--mode v2` 只跑事件层；`--seed` 换种子；`--config` 指定基线 yaml。
- `outputs/`、`__pycache__/`、`*.pyc` 已在 `.gitignore` 中；outputs 是可重算生成物，不进版本管理。

可复现性（2026-10-29 实测）：同命令跑两次，剔除 `timestamp/run_id/runtime_seconds/timings` 后
`params.json` 哈希 `6ca2dd649afee472`、`summary.json` 哈希 `db6a29389b378f01` 一致，23 个 CSV 逐字节一致，
两次耗时 379.06 s / 379.19 s。

## 测试

```powershell
& 'C:\Users\tho25\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe' -X utf8 -m unittest discover -s tests -v
```

2026-10-29 修订副本实测：`Ran 102 tests`，`OK`（含原 44 条、R1–R7 目标契约、T14/F 系列回归与模块边界 5 条）。拆分只搬移源码位置、不改逻辑，验证见 `CHANGES.md` §0。
后者在未修订副本上为 10 failures / 8 errors，见 `before_regressions.log`。新增覆盖：v2 统计层的 g 区间与三区标签、置信集包含最优、
CVaR 全安装评估标志、Fig. 8 稀缺度网格、canonical 归档、manifest 元数据、SAA 表与成本尺度可行域。

## 目录

| 路径 | 作用 |
|---|---|
| `run_all.py` | 命令行入口，串起静态层、敏感性、事件层、统计层与输出归档；各层实现在 `run_blocks.py` |
| `configs/baseline.yaml` | 37 个参数叶子，每个带 `value` 与 `source`（manuscript / assumption / sensitivity） |
| `configs/modes.yaml` | 四种运营模式参数（部分共享比例、移动充电覆盖率与单位成本比） |
| `configs/sensitivity.yaml` | 单因素 ±20%、极端值与命名场景（含成本尺度、寿命、投诉口径） |
| `configs/v2.yaml` | 事件层与 v2 统计层参数（三类需求、q、θ、设备、馈线、功率、能量、300 天、r 网格） |
| `src/prei/config.py` | YAML 子集解析、参数来源、校验、种子派生 |
| `src/prei/costs.py` | 式 (2)(5)(6) 成本、PSC、投诉概率期望、事件成本尺度 |
| `src/prei/demand.py` | Beta/Binomial 构成、Poisson/NHPP 到达、时长与能量 |
| `src/prei/rules.py` | π_S / π_F / π_θ 准入规则与兼容矩阵 |
| `src/prei/capacity.py` | 车位/设备/馈线/功率容量、服务账本与不变量 |
| `src/prei/simulator.py` | 事件层单日仿真（到达、准入、排队、充电、离开） |
| `src/prei/evaluate.py` | 门面：重新导出下列三模块，公共导入面不变 |
| `src/prei/evaluate_base.py` | 需求/情景、静态曲线与最优、模式对比、ETP、v2 设计 |
| `src/prei/evaluate_v2.py` | v2 单元矩阵、评价、最优、分解、CVaR、g(r) 结构 |
| `src/prei/evaluate_outputs.py` | Fig. 8 网格、可行域、SAA 行 |
| `src/prei/stats.py` | 门面：三区域、CVaR、式 (12) 分解 |
| `src/prei/stats_bootstrap.py` | block bootstrap、置信集、g(r) 区间 |
| `src/prei/io.py` | 时间戳、CSV/JSON 写入、内容哈希 |
| `tests/test_core.py` | 成本/需求/规则/容量/评价（核心组，拆分自 `test_prei.py`） |
| `tests/test_stats_sim.py` | 统计、仿真、配置组（同上） |
| `tests/test_v2_outputs.py` | v2 统计层与输出组（同上） |
| `tests/test_regressions_r.py` | R1–R7 目标契约回归（拆分自 `test_review_regressions.py`） |
| `tests/test_regressions_f01.py` | F01 区间与移动时机回归 |
| `tests/test_regressions_f09.py` | F09 区间覆盖与结构回归 |
| `tests/test_module_layout.py` | 模块边界与源码体积约束（5 条，本轮新增） |
| `tools/stat_experiment.py` | R2/R3/R5/R6 的小规模合成覆盖/误排实验 |
| `CHANGES.md` / `PROVENANCE.json` | 修订说明 / 复制来源与哈希 |
| `outputs/` | 运行产物（生成物，可重算；正式结果在 `outputs/baseline/canonical-seed42/`） |

## 输出文件与论文图表对应

| 文件 | 内容 | 对应图表 |
|---|---|---|
| `params.json` / `summary.json` | 参数快照、运行计数与关键结果 | 补充材料 |
| `rule_matrix.csv` | π_S/π_F/π_θ × 三类需求兼容矩阵（18 行） | **Table 9** |
| `static_curves.csv` / `static_optimum.csv` | 静态 PSC 曲线、最优 PPR、被动对照 | 图 2 数据 |
| `integer_check.csv` | 0.05 网格与整数枚举的差 | 方法附录 |
| `modes.csv` | 四种模式最优 PPR 与降幅 | 共享/移动充电比较图 |
| `etp.csv` / `etp_points.json` | 式 (8)(9) 全安装增量与净效益、静态 ETP | ETP 判定 |
| `sensitivity.csv` | 单因素 ±20% 与极端值 | 图 3/图 5 |
| `saa_error.csv` | 同种子重复 10 次的 argmin 命中率与 PSC 标准差 | 方法附录（SAA 误差） |
| `feasibility_costs.csv` | event_cost_scale × horizon 网格的可行域 | 方法/讨论（口径依赖） |
| `confidence_sets.csv` / `g_curve.csv` | 静态层置信集与 g(r) | Table 11 的静态对照 |
| `cvar.csv` | 静态层 CVaR_0.95（含全安装标志与零值原因） | Table 11 补充 |
| `fig8_regions.csv` | (r, 稀缺度) 三区地图数据 | **Fig. 8** |
| `v2_designs.csv` | 事件层规则 × 设备数 × 模式全设计评估 | Table 10/11 输入 |
| `v2_best.csv` | 各 r × q 的最优 v2 设计 | v2 结果 |
| `v2_service_accounting.csv` | 资源—服务台账：可达车位、并发、功率、能量、拒绝率 | **Table 10** |
| `v2_timeline_sample.csv` | 事件时间轴样本（t_a/t_c/t_d/t_r） | **Fig. 6** |
| `v2_confidence_sets.csv` | v2 候选集/置信集（block bootstrap + max-t/holm） | **Table 11** |
| `v2_g_curve.csv` | v2 的 g(r) 与置信区间 | **Fig. 7** |
| `v2_regions.csv` | v2 三区标签（full_dominant / partial_dominant / undetermined） | **Fig. 8 / Table 11** |
| `v2_cvar.csv` | v2 CVaR_0.95（tail_samples、aux、全安装标志） | **Table 11** |
| `v2_q_sensitivity.csv` | q=0.3/0.9（100 天）对最优规则/模式的影响 | v2 敏感性 |
| `decomposition.csv` | 式 (12) 路径 A/B 分解与路径依赖 | Fig. 7/8 支持 |
| `manifest.json` | 文件清单、sha256、命令、Python 版本、配置哈希、耗时分解 | 交付清单 |

## 口径与已知限制

- `event_cost_scale=36` 是**假设**：原文每事件损失约 5.36 元，与 60000 元/桩、5 年寿命字面不相容
  （最优 PPR=0）。原文另有"占用充电位成本约 200 元"的说法，5.365×36≈193 元/事件据此取值；
  `feasibility_costs.csv` 扫描 scale∈{1,8,18,36,54}×H∈{1,5,10}：scale=1 全部非内点，scale≥8 才回到 (0,1)，
  且 H 在两侧同比例缩放、不改变最优比例。
- 静态层 500 个场景；v2 统计层每格 300 天，r∈[0.2,1.0] 步长 0.1，并在 g 首次变号区间按 0.02 加密（本次 8 个点）。
- **v2 统计层的候选集限定 fixed 模式**（π_S/π_F/π_θ）以便和静态层 ETP 同口径比较；移动充电（overhead）在
  `v2_best.csv` 里单独报告，不进入 g(r) 与置信集。若把 overhead 也纳入候选，g(r) 在 0.2–1.0 全为正（全安装从不占优）。
- v2 的 q 只对统计层固定为 0.6；q=0.3/0.9 用 100 天单独扫描（`v2_q_sensitivity.csv`），不能与 300 天统计混用。
- Beta 构成方差 0.09 只在 `0<r<1` 且 `0.09<r(1-r)` 内可行；r=0.9 钳制、r=1.0 退化为确定性；
  Binomial 构成作为逐车独立 EV 的诊断口径同时报告。
- 静态层移动充电按"设备数=容量"处理，覆盖率与功率上限只在 v2 层计入。
- 投诉成本默认 `embedded`（式 (3)(4) 已含）；`complaint_accounting=separate` 已作为灵敏度场景。
- VaR 取经验分布尾段最小值、CVaR 取尾均值；静态 cvar 与 v2 cvar 都以"日运营损失"为基准（不含桩资本），
  `full_install_evaluated` 为 True；全安装损失恒为 0 的行在 `full_install_zero_reason` 里写明原因。
- g(r) 三区域：`g_hi<0` 全安装占优、`g_lo>0` 部分占优、否则未定；置信集用 block bootstrap（块长 1 天）+ max-t/holm。
- g 区间自 T14 起默认配对同时 max-t（K 个对比同界、按 max 传播，见 `CHANGES.md` §11.3）；百分位自举仅作诊断，
  不声称名义覆盖。主导窗口、持续负后缀与规则是否同时改变见 `v2_g_structure.csv`。
- 区间为逐 r 点式，三区标签/占优窗口/ETP 沿用点式口径，**不构成跨 r 联合保证**；
  `block_len>1` 或相关场景只作诊断（输出列 `g_nominal_coverage`/`region_confidence` 已在机器标记中体现）。
  失败请求的移动不再留执行区间（`t_move_status=cancelled`），见 `CHANGES.md` §13。
- 原文 MATLAB 代码与补充材料不可得，无法逐行核对；图 2/图 5 的对照值是图形读数。

## 复现结论（2026-10-29，canonical-seed42）

- 静态层：PSC 损失增幅 0%–37.8%（原文 42%–91%）；plc/beta 的 ETP 点估计 0.2，plc/binomial 1.0
  （原文 0.7）；plc/beta 净效益 58.9–162.2 元（EV）/129.3–232.6 元（ICEV），binomial 为负；原文 4.1/6.3 元。
- v2 统计层：44 个 (场地, 构成, r) 格；区域标签 27 partial_dominant / 4 full_dominant / 13 undetermined；
  g(r) 在 r≈0.5–0.6 首次下穿 0、在 r≈0.76–0.9 出现 full_dominant 窗口，但 r=1.0 又回到 partial_dominant，
  因此"首次持续为负"的 ETP 在 v2 层不存在（`v2_etp_points` 全为 null）。置信集大小 1–3。
- 这些数值**不是**原稿结论的复现证据；差异归因见报告第 5/6 节。