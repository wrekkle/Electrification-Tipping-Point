# 行为变更影响分析：experiments.write_output（第五轮安全修复）

- 日期：2026-10-31
- 变更文件：apps/parking_lab/workbench/experiments.py
- 变更前快照：before/experiments.py.before（sha256 9158D0E4F9FCA9451F50FD67F200F65C3B65D7AEB247CC1151AB742E06D575C9）
- 变更后：sha256 A7AFF1D47E87F8CA4B5C69BAA45469BF6B8E29D6189AD73E9AA055700688B4FB
- diff：before/experiments_write_output.diff
- 触发原因：F12–F15（见 REPORT.md）；纯维护性可靠性改动，不改变任何计算/统计口径

## 1. API 变更

| 符号 | 类型 | 说明 |
|---|---|---|
| inspect_output(directory) | 新增 | 只读状态判定：missing / not_a_directory / incomplete / complete / corrupt / foreign；返回 path/result/temp_files/other_files（corrupt 额外带 error） |
| fingerprint_output(directory) | 新增 | 仅 complete 可用；返回 path/result/bytes/sha256，供 manifest 与幂等检查 |
| write_output(directory, payload, *, force=False) | 签名扩展 | force 为仅关键字参数，默认 False 保持原语义 |
| RESULT_FILENAME / TEMP_PREFIX / TEMP_SUFFIX | 新增常量 | result.json、.result-、.tmp，供调用方识别与测试引用 |

位置参数、返回值（target.resolve()）、异常基类（FileExistsError 仍是“存在且不覆盖”的主信号）保持兼容。

## 2. 行为差异矩阵（对既有调用方）

| 场景 | 变更前 | 变更后默认 | 变更后 force=True |
|---|---|---|---|
| 新目录成功写 | 成功 | 成功（同） | 成功（同） |
| 完整结果目录 | FileExistsError（泛化消息） | FileExistsError，消息指明已有完整结果与 force | 原子替换 result.json |
| 空目录 / 仅 .result-*.tmp | FileExistsError（无法重试） | FileExistsError，列出残留 .tmp、说明可能中断、提示 force | 清理自己的 .tmp 后写入 |
| 残缺 result.json | FileExistsError（未指出损坏） | RuntimeError，明确“不能当作成功结果” | 原子替换 |
| 未知文件、无 result.json | FileExistsError | FileExistsError，列出未知文件 | 写 result.json，不删未知文件 |
| 路径是文件 | FileExistsError | FileExistsError（明确“不是目录”） | 同默认（不覆盖文件） |
| 序列化失败 | 清理临时文件与空目录后抛出 | 同（清理逻辑保留；force 场景保留旧 result.json） | 同 |

正常并发路径仍由 mkdir(parents=True, exist_ok=False) 原子占位保证互斥；仅当 mkdir 因竞争失败时新增“已被另一写入者创建”的明确消息。

## 3. 兼容性验证

- 旧用例：test_core.py（含“第二次写同一目录必须 FileExistsError 且内容不变”）、test_round4_atomic.py（成功无 .tmp、NaN 失败清理、既有目录不覆盖）全部通过。
- CLI：__main__.py 的 write_output(args.out, result) 未改，行为在成功路径完全一致；拒绝路径异常类型不变（FileExistsError），仅消息更具体；corrupt 场景由 FileExistsError 变为 RuntimeError（此前该场景实际不可达，因为任何已存在目录都先报 FileExistsError）。
- 全量回归：362 tests OK，exit 0（REPORT.md §1）。

## 4. 研究数值与证据影响

- 固定输入 compare（duration_hours=2、arrival_rate_hour=20、seed=5）修复前后结果 JSON 忽略 provenance 后完全相等（equal=true，differing_keys=[]，rows=4）。证据：before/fixed_input_compare.json、after/fixed_input_compare.json。
- provenance.source_sha256 中 experiments.py 的哈希会变化（源码内容变化导致），这是设计内行为；旧结果文件不受影响。
- VERSION 未提升：本次不改变模型/算法/统计口径，提升版本会让新产物的 provenance.model_version 与既有第四轮产物不一致，且对研究数值无信息增益。若后续把 force 暴露到 CLI 或改变默认拒绝策略，再单独提版本。
- 既有研究文件未改写：research/round4_20261031/** 仅只读审计（F16 未修）。

## 5. 并发与恢复语义（明确边界）

- 默认写：目录原子占位 → 同一路径两个写者只能有一个成功；失败方得到明确拒绝，不产生覆盖。
- 恢复（force）：只删除本写入器命名的 .result-*.tmp；未知文件永不删除；result.json 通过 os.replace 原子替换，失败时旧结果保留。
- force 并发：显式覆盖语义为 last-writer-wins；不会出现半截 JSON（原子替换），但不承诺哪个写者最终胜出。
- 恢复假设同一目录无并发写者（默认路径的互斥不受影响）。

## 6. 未验证 / 不做承诺

- 断电持久性：fsync 只覆盖文件内容；未做目录 fsync，不承诺断电后目录项与 rename 的持久性；本轮“中断”均为进程级硬退出。
- 网络文件系统/同步盘上的 os.replace 语义未测（仅本机 NTFS）。
- CLI 未暴露 force，拒绝时仍打印 traceback（F17，__main__.py 不在写范围）。

## 7. 回滚

1. 将 before/experiments.py.before 覆盖回 apps/parking_lab/workbench/experiments.py（或按 before/experiments_write_output.diff 反向应用）。
2. 删除 apps/parking_lab/workbench/tests/test_round5_safety.py（新增用例依赖新 API）。
3. 复跑 §1 回归命令确认回到 345 tests OK。
4. 回滚不影响任何既有结果文件（本轮未改写 research/ 既有产物）。

## 8. 建议 Lead 决策

1. 是否在 __main__.py 暴露 --force 并在拒绝时输出单行错误（需另开写范围）。
2. 是否把 inspect_output/fingerprint_output 纳入研究 runner 的 manifest（F16 的根治方案），需改 research/round4 或后续 runner（既有文件只读，建议在 round5 runner 中采用）。
