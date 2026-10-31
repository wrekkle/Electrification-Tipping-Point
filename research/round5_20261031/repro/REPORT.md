# P0 复现一致性：第三/四轮 demand_hash 不一致的定位与结论

状态: 生效（第五轮）
日期: 2026-10-31
范围: 1025 个重叠 (lot, seed, k) 中 3 个车流的 demand_hash 不同（TPE0330 s2、TPE0401 s2、TPE0695 s3）。
冻结: 第三/四轮结果文件未改动；本目录只新增证据与复跑输出。

## 1 结论（先给判断）

**分类：第 2 类——版本升级改变抽样，不是同版本不确定，也不是配置不同，更不是仅哈希定义变化。**

- 两轮同 (lot, seed) 的 p_EV=0.10、q_need=0.36、horizon=1440、start_hour=11.5、规则与 seed 完全相同（行内 `p_ev_used`/`q_need_used` 一致，见 §3）。feeder 120 vs 336 不同，但 feeder 不参与需求生成。
- 第三轮结果写于 **13:26:25**，`traffic_gen.py` 改于 **14:07:52**，第四轮 REF 结果写于 **14:14:15**；两份结果 meta 的 `source_sha256` 显示 `traffic_gen.py`（8c47f55f…→d29baf51…）与 `run_cost_curve.py`（47e4fedb…→3b2241c2…）在两轮之间确实变化。
- 当前代码（traffic_gen-2.1.0）确定性：同命令重复、独立进程、workers=1 与 workers=8 各 25 条流全部同哈希；且 **25/25 复现第四轮 REF 哈希**，只复现第三轮 22/25，恰为上述 3 条。
- 对当前原始车辆记录做多种排序/重编号置换（按时间、按 EV、按 dwell、倒序、重编号）均不能得到第三轮哈希，说明不是“记录相同、仅顺序/哈希定义变化”；记录值本身有差异。
- 差异量级：3 条流的 `arrivals`、`ev_arrivals`、`initial_occupancy_n`、`demand_energy_kwh_total` 两轮完全相同，仅 `demand_hash`、`traffic_hash` 与 `mean_occupancy_rate` 不同，后者 abs 差 7.34e-7~2.91e-6（相对 1.07e-6~8.75e-6），即车辆集合在实验分辨率下等价、浮点/顺序层面不同。
- **第一条实际差异（车辆级字段）无法给出：旧版 traffic_gen 源码与旧原始车辆记录都未被保留（无 git 提交、无快照；round2 的 v1.1.0 快照哈希也不等于第三轮值），旧记录不可重建。** 该项保持 UNVERIFIED，不用“重算一次哈希通过”掩盖。

## 2 传播路径

`traffic_gen.generate_for_lot`（版本 8c47…，第三轮）→ `arrivals`（vehicle_id/time/dwell/is_ev/needs_charge/energy）
→ runner `demand_hash=sha256(json([[id,time,is_ev,needs_charge,dwell,energy]…]))` 与 `Simulation.traffic_hash`
→ 第三轮 `main_A_pi0_ref_s10.json` 的 3 条流；代码更新为 d29b…（14:07）后，
同 (lot,seed) 的同一 3 条流采样结果改变 → 第四轮 REF 写入新哈希。其余 22 条流对新旧版本不敏感（同哈希）。
故 14:07 的版本变更不是全局重采样，只影响这些 (lot,seed) 的抽样细节；具体触发的代码行未保留，标 UNVERIFIED。

## 3 证据与复算

| 证据 | 文件 |
|---|---|
| 两轮结果 meta 的 source_sha256、p/q/feeder/horizon 字段 | `main_A_pi0_ref_s10.json` meta、`scenario_REF_A_s5.json` meta |
| 两轮逐流对照（22 同 / 3 异；异者字段清单） | `repro_hash_diff.json`（本目录，脚本生成） |
| 当前代码 25 流复跑：workers=1 ×2、workers=8 ×1 | `repro_r3params_s5_k0.json`、`…_rep2.json`、`…_w8.json` |
| 同流跨进程重复生成（4 次） | `probe_rng.py` 输出（见 §5 命令） |
| 排序/重编号置换不能复现旧哈希 | `probe_order.py`、`probe_ids.py` |
| 自动核对 | `python research/round5_20261031/repro/verify_repro.py` → EXIT 0 |

## 4 处理与新基线

- 第三轮 3 条流视为**旧版本证据**，不删除、不与第四轮结果做配对比较。
- 跨轮比较统一使用当前版本 + 固定显式参数（p_EV=0.10、q_need=0.36、horizon=1440、start_hour=11.5、feeder 显式给出、workers 不影响哈希）；新证据以 `ref_feeder336.json` / 第四轮 REF 为准。
- 若写作需要第三轮 90 流基线，重跑 `main_A` 命令（当前代码）另存为新基线，注明与旧文件差 3 条流、原因版本变更。

## 5 复算命令

    python research/round5_20261031/repro/probe_rng.py TPE0330 2      # 重复 4 次同哈希
    python research/round5_20261031/repro/verify_repro.py             # 自动核对，EXIT 0
    # 25 流重跑（workers 1/8）命令见 verify_repro.py 文件头注释与 shell 记录

解释器：C:\anaconda\python.exe（3.12.3）+ PyMuPDF 1.28.2；MATLAB 未参与此项。
