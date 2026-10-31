# 第五轮安全可靠性报告（task-2）

- 日期：2026-10-31
- 执行者：safety（子代理）
- 工作目录：C:/Projects/停车场充电桩优化方案
- 写范围：research/round5_20261031/safety/**、apps/parking_lab/workbench/tests/**；经许可修改 apps/parking_lab/workbench/experiments.py（原文件快照与 diff 见 before/）
- 未触碰：research/ 既有文件、research/collection（采集器运行中）、Word 稿件、旧结果目录；未安装依赖、未杀用户进程

## 0. 结论摘要

| 项目 | 结果 |
|---|---|
| 第四轮安全回归复跑（修复前） | 345/345 通过，exit 0 |
| 修复后全量回归 | 362/362 通过（345 + 新增 17），exit 0 |
| 同名输出并发 | 修复前后均互斥：3/3 次双进程竞争均为「1 成功 + 1 拒绝」，只有获胜者的 result.json，无残留临时文件 |
| 写入中断 | 硬中断后不产生 result.json（无“成功”证据），残留 .result-*.tmp 可识别；修复前重试被泛化 FileExistsError 永久阻塞，修复后状态可判定、默认明确拒绝、force 可恢复 |
| 重试恢复 | 完整结果默认不覆盖（字节级不变），仅 force 覆盖；残缺半成品不会被当成功 |
| 结果与 manifest 一致性 | 命令/参数/哈希/输出路径/exit code 全部对应（harness 自建 manifest + fingerprint_output）；round4 旧 manifest 缺哈希与 cwd（F16，只读审计） |
| test_http 偶发失败 | 顺序 30/30 通过 + 6 并发 × 5 轮 30/30 通过，失败率 0/60；无法复现，给出已排除项与未覆盖条件 |
| 固定输入研究数值 | 前后完全一致（忽略 provenance）：4 行 × 4 策略，seed=5，compare 输出 equal=true |
| 仓库检查 | scripts/check_all.py exit 0（0 错误，8 条既有历史统计警告，与本次改动无关） |

发现缺陷 5 条（F12–F16）与 1 条范围外 CLI 表现问题（F17）；修复 F12–F15，F16 因研究既有文件只读不改，F17 因 __main__.py 不在写范围未改。

## 1. 环境与命令

解释器（仓库内带依赖的 Python）：

~~~
C:/Users/tho25/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe
~~~

第四轮回归命令（修复前后同一条）：

~~~
python -m unittest discover -s apps/parking_lab/workbench/tests -p "test_*.py" -t .
~~~

| 步骤 | 命令 | exit code | 结果 |
|---|---|---|---|
| 修复前回归 | 上条命令 | 0 | Ran 345 tests in 8.360s，OK |
| 新增用例 | python -m unittest apps.parking_lab.workbench.tests.test_round5_safety -v | 0 | Ran 17 tests in 0.078s，OK |
| 修复后回归 | 上条 discover 命令 | 0 | Ran 362 tests in 9.407s，OK |
| 并发探针（修复前/后） | python research/round5_20261031/safety/scripts/probe_concurrency.py | 1 / 0 | 修复前探针脚本自身判定口径有误（见 §4.1），行为证据有效；修复后全部检查通过 |
| 中断重试探针（前/后） | python research/round5_20261031/safety/scripts/probe_crash_retry.py | 0 / 0 | 记录型探针，前/后证据见 logs/ |
| manifest 探针（前/后） | python research/round5_20261031/safety/scripts/probe_manifest.py | 1 / 0 | 修复前唯一失败项是 fingerprint_output 不存在；修复后全部通过 |
| 固定输入一致性 | python research/round5_20261031/safety/scripts/compare_fixed_input.py before/fixed_input_compare.json after/fixed_input_compare.json | 0 | equal=true，differing_keys=[]，seeds=[5]，rows=4 |
| 仓库检查 | python scripts/check_all.py | 0 | 文档与链接/字数/文献索引均通过，0 错误、8 警告（既有） |
| tmp 清理 | python research/round5_20261031/safety/scripts/cleanup_tmp.py | 0 | 删除前逐条断言绝对路径在 safety/tmp 下，remaining=[] |

说明：probe_concurrency.py 修复前退出 1 是探针自身把成功子进程的 SystemExit 误判为失败（子进程 try 块包住 sys.exit），日志中的进程退出码与产物证据不受影响；修复后该口径已修正，行为结论由修复后探针与新增用例共同支撑。

## 2. 缺陷清单

| ID | 严重度 | 现象（修复前反例） | 根因 | 修复 |
|---|---|---|---|---|
| F12 | 高 | 进程在写临时文件后被杀（os._exit(7)），目录残留 .result-*.tmp、无 result.json；再次写同一路径永远 FileExistsError，只能手工删目录 | write_output 对“已存在目录”一律 mkdir(exist_ok=False)，无法区分“完整结果”与“上次中断残留” | inspect_output 状态判定；默认对 incomplete 明确拒绝并给出残留文件名与 force 提示；force 只删自己的 .result-*.tmp 后重写 |
| F13 | 中 | 调用方/脚本只能 os.listdir 猜测目录状态；残缺 .tmp 与成功结果无法程序化区分，也没有指纹 | 无状态识别与指纹 API | 新增 inspect_output（missing/incomplete/complete/corrupt/foreign/not_a_directory）与 fingerprint_output（sha256/bytes，仅 complete 可用） |
| F14 | 中 | 已有完整结果时无法显式重跑，只能手工删目录；需求要求“除非显式 force” | write_output 无 force 通道 | 新增 write_output(..., force=False)；force 原子替换 result.json，失败时保留旧结果 |
| F15 | 中 | 残缺/损坏的 result.json（外部拷贝或旧版本残留）只报泛化 FileExistsError，不指出损坏，也不能明确阻止被后续流程误用 | 不解析 result.json，只看目录存在 | 状态判定为 corrupt 并抛 RuntimeError，明确指出“不能当作成功结果”；force 才可覆盖 |
| F16 | 低（研究证据） | research/round4_20261031/results/scenario_manifest.json 记录 command/out/exit，但无结果 sha256、无 cwd；skipped_existing=true 的条目只证明文件存在 | 既有研究 runner 的 manifest 设计（只读文件，不改） | 本轮不改研究既有文件；safety harness 自建 manifest 增加 cwd/sha256/bytes 并用 fingerprint_output 核对，供后续 runner 采用 |
| F17 | 低（范围外） | CLI 遇到已存在输出目录时未捕获 FileExistsError，打印 traceback、exit 1；拒绝语义正确但证据不友好 | apps/parking_lab/workbench/__main__.py 未捕获（不在本轮写范围） | 未改；库层错误类型与消息已明确，报告列为剩余风险 |

## 3. 修复内容（apps/parking_lab/workbench/experiments.py）

- 原文件快照：before/experiments.py.before，sha256 = 9158D0E4F9FCA9451F50FD67F200F65C3B65D7AEB247CC1151AB742E06D575C9
- 修复后 sha256 = A7AFF1D47E87F8CA4B5C69BAA45469BF6B8E29D6189AD73E9AA055700688B4FB
- unified diff：before/experiments_write_output.diff（140 行）
- 变更：新增 RESULT_FILENAME / TEMP_PREFIX / TEMP_SUFFIX 常量、_temp_artifacts、inspect_output、fingerprint_output；write_output 增加仅关键字参数 force=False，并在“目录已被另一写入者创建”时给出明确并发拒绝消息
- 行为矩阵：

| 目录状态 | 默认 | force=True |
|---|---|---|
| missing | 原子创建目录并写 | 同默认 |
| complete | FileExistsError，不覆盖 | 原子替换 result.json，清理自己的残留 .tmp |
| corrupt | RuntimeError（不能当成功） | 原子替换 |
| incomplete（空目录/仅 .tmp） | FileExistsError，列出残留文件并提示 force | 清理自己的 .tmp 后写入 |
| foreign（未知文件） | FileExistsError，列出未知文件 | 写 result.json，绝不删除未知文件 |
| not_a_directory | FileExistsError | 同默认 |

兼容性：force 默认 False，位置参数不变；既有调用方（__main__.py、test_core.py、test_round4_atomic.py）行为不变，旧用例全部通过。详细影响分析见 IMPACT.md。

## 4. 六项实测

### 4.1 同名输出并发

- 方法：两个独立进程通过 go 文件同步后同时写同一目录；3 轮独立试验；随后顺序重复写同一路径。
- 修复前（logs/probe_concurrency_before.json）：3/3 轮均为 1 个 exit 0 + 1 个 exit 2（FileExistsError），目录仅 result.json，无 .tmp；获胜者 payload 完整；顺序重复被拒绝且 sha256 不变（a85772715aab...）。
- 修复后（logs/probe_concurrency_after.json）：同上，1 成功 + 1 拒绝，marker 与获胜进程一致，files=["result.json"]；顺序重复仍拒绝、字节不变。
- 结论：正常路径已互斥（mkdir exist_ok=False 原子占位），无需修复；修复后拒绝消息对“竞争创建”场景更明确。force 并发属于显式覆盖，语义为 last-writer-wins，见剩余风险。

### 4.2 写入中断

- 方法：子进程把 json.dump 替换为“写入半截 JSON 后 os._exit(7)”，模拟硬中断；另测可控序列化失败（NaN）。
- 修复前（logs/probe_crash_retry_before.json）：exit 7；目录仅 .result-l7cx6t2i.tmp；无 result.json（不产生成功证据）；重试 exit 2 泛化 FileExistsError；force 不存在（TypeError）。
- 修复后（logs/probe_crash_retry_after.json）：硬中断后 inspect_output 判定 incomplete（残留 .result-bv4a9ah7.tmp）；默认重试 exit 2，消息为“输出目录存在但未完成（.result-bv4a9ah7.tmp），可能是上次写入中断……可显式 force=True 重试”；force 重试 exit 0，状态 complete，marker=retry，目录仅 result.json。
- 可控失败：NaN 序列化抛 ValueError，目录被清理（dir_exists=false，无 .tmp）；force 失败时旧 result.json 字节不变、无残留 .tmp（新增用例覆盖）。
- 结论：中断不会留下“成功”证据；.tmp 以 .result- 前缀 + .tmp 后缀可识别，且不被状态判定/指纹当作结果。

### 4.3 重试恢复

- 完整结果：默认 FileExistsError，result.json 字节不变（新增用例 test_complete_result_is_not_overwritten）；force 原子替换（test_force_replaces_complete_result）。
- 残缺半成品：仅 .tmp/空目录 → incomplete，默认拒绝，force 恢复；残缺 result.json → corrupt，默认 RuntimeError（不能当成功），force 覆盖。
- 证据：probe_crash_retry_after.json 的 retry_default/retry_force/corrupt_result/empty_dir 步骤；新增用例 17 条全部通过。

### 4.4 结果与 manifest 一致性

- 方法：在 safety/tmp/manifest 下用固定输入（duration_hours=2、arrival_rate_hour=20、seed=5）跑 workbench CLI compare；harness 记录 command（完整 argv）、cwd、exit code、输出绝对路径、result.json sha256/bytes，并逐项核对。
- 修复后（logs/probe_manifest_after.json）全部通过：exit=0；stdout 输出路径 == manifest out；result.config 与输入一致；seeds=[5]；provenance.model_version 与包版本一致；provenance.source_sha256 逐文件重算一致；fingerprint_output 的 sha256/bytes 与 manifest 一致；两次独立运行 runs/rows 完全相同（固定输入确定性）；对同一路径重跑被拒绝（exit 1）且 sha256 不变。
- 修复前（logs/probe_manifest_before.json）：除 fingerprint_output 不存在外其余检查已通过，说明原有原子写入/目录占位已保证路径与内容一致；缺的是可引用的完整性指纹 API。
- round4 只读审计：scenario_manifest.json 15 条，缺失输出 0、非零 exit 0；但 has_hash_field=false、has_command_cwd=false（F16）。skipped_existing=true 的条目只证明文件存在，不能证明内容与命令对应。

### 4.5 临时文件与残缺目录识别

inspect_output 状态表（新增用例 test_round5_safety.py 覆盖）：

| 目录内容 | state | 是否成功证据 | fingerprint_output |
|---|---|---|---|
| 路径不存在 | missing | 否 | RuntimeError |
| 空目录 / 仅 .result-*.tmp | incomplete | 否 | RuntimeError |
| result.json 可解析 | complete | 是 | 返回 sha256/bytes |
| result.json 不可解析 | corrupt | 否 | RuntimeError |
| 未知文件、无 result.json | foreign | 否 | RuntimeError |
| 路径是文件 | not_a_directory | 否 | RuntimeError |

### 4.6 test_http 偶发失败

- 顺序复跑 30 次（logs/test_http_30x.log）：每次 Ran 15 tests，30/30 exit 0，FAILED/FAIL:/ERROR: 行数 0（450 次测试执行 0 失败），总耗时约 55s。
- 并发隔离：6 个进程同时跑、共 5 轮 = 30 次运行（logs/test_http_concurrent.log）：FAILS=0。
- 机制检查：test_http 使用 make_server(0)（临时端口，无固定端口冲突），每个测试类一个 server，请求超时 20s；时间敏感断言在 test_continuous_advance_pause_resume_ledger（60x 加速、暂停/恢复墙钟差 <5 分钟），理论上受负载影响，但 6 并发负载下未复现。
- 结论：本轮 60 次运行未复现偶发失败；可排除固定端口冲突（port=0），未复现的原因无法归因到单一机制；0/60 不等于不存在偶发，慢机/CI/杀毒扫描等条件未覆盖（见剩余风险）。

## 5. 固定输入研究数值一致性

- 修复前结果：before/fixed_input_compare.json（sha256 8BCD634D76A9E7131428D59912136C19F79A26AB132D09DD75F71E1557DA847E）
- 修复后结果：after/fixed_input_compare.json
- 比较命令与结果：compare_fixed_input.py → equal=true，differing_keys=[]，seeds=[5]，rows=4（忽略 provenance.created_utc 与 source_sha256；后者因 experiments.py 内容变化必然变化，属设计内）。
- 结论：纯维护性改动未改变固定输入的研究数值。

## 6. 新增测试（apps/parking_lab/workbench/tests/test_round5_safety.py）

17 条：状态判定 6 条（missing/complete+fingerprint/incomplete+不可指纹/corrupt/foreign/not_a_directory）；写入语义 11 条（完整结果不覆盖、force 替换、残留 .tmp 明确拒绝、force 恢复、空目录、残缺 result.json、外来文件不被删除、序列化失败清理、force 失败保留旧结果、路径是文件、双线程竞争恰好一个获胜）。

## 7. 剩余风险与未验证项

1. 断电持久性未验证：只 fsync 文件内容，未做目录 fsync，也不承诺断电后目录项/rename 的持久性；本轮所有“中断”均为进程级硬退出，不是断电。
2. 恢复语义假设同一目录无并发写者；force 并发写为显式覆盖的 last-writer-wins（原子替换保证不出现半截 JSON，但不保证谁赢）。
3. CLI 无 --force，且拒绝时打印 traceback、exit 1（F17，__main__.py 不在写范围）。
4. F16 未修：round4 既有 manifest 无 sha256/cwd，skipped_existing 记录不能证明内容；研究既有文件只读，本轮只在 harness 中补齐。
5. traffic_gen.save_traffic 仍为非原子写（traffic 子命令），不在本轮写范围，未修复。
6. test_http 0/60 失败不代表不存在偶发；未在慢机/CI/高负载/杀毒扫描下验证。
7. 网络文件系统/同步盘（os.replace 跨卷或同步客户端语义）未测；本轮只在本机 NTFS 验证。
8. check_all.py 的 8 条警告均为既有文献统计历史记录（STALE_TOTAL/STALE_PENDING 等），与本次改动无关。

## 8. 产物与复现

| 产物 | 路径 |
|---|---|
| 本报告 | research/round5_20261031/safety/REPORT.md |
| 影响分析 | research/round5_20261031/safety/IMPACT.md |
| 修复前源码快照 + sha256 + diff | before/experiments.py.before、before/experiments.py.sha256、before/experiments_write_output.diff |
| 修复前后固定输入结果 | before/fixed_input_compare.json、after/fixed_input_compare.json |
| 探针日志（修复前/后） | logs/probe_concurrency_before.json / _after.json、logs/probe_crash_retry_before.json / _after.json、logs/probe_manifest_before.json / _after.json |
| test_http 日志 | logs/test_http_30x.log、logs/test_http_concurrent.log |
| 清理日志 | logs/cleanup.log（删除前断言绝对路径在 safety/tmp 下，remaining=[]） |
| 探针脚本 | scripts/probe_concurrency.py、scripts/probe_crash_retry.py、scripts/probe_manifest.py、scripts/compare_fixed_input.py、scripts/cleanup_tmp.py |
| 新增用例 | apps/parking_lab/workbench/tests/test_round5_safety.py |

复现顺序（均在仓库根目录，使用 §1 解释器）：

~~~
python research/round5_20261031/safety/scripts/probe_concurrency.py
python research/round5_20261031/safety/scripts/probe_crash_retry.py
python research/round5_20261031/safety/scripts/probe_manifest.py
python research/round5_20261031/safety/scripts/compare_fixed_input.py research/round5_20261031/safety/before/fixed_input_compare.json research/round5_20261031/safety/after/fixed_input_compare.json
python -m unittest discover -s apps/parking_lab/workbench/tests -p "test_*.py" -t .
python scripts/check_all.py
python research/round5_20261031/safety/scripts/cleanup_tmp.py
~~~

探针只写 research/round5_20261031/safety/tmp/**，清理前逐条断言绝对路径；本轮结束时 tmp 已清空，证据保留在 logs/。
