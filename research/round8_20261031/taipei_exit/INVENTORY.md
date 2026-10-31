# 台北专属运行链路退出清单（round8）

类型: 退出记录
状态: 已执行（代码与运行链路），历史只读留存
负责人: lead（Team Lead）
日期: 2026-10-31
依据: 用户 2026-10-31 决定——从现行研究系统与论文主线完整移除台北专属模块；历史原始数据、旧稿、旧结果与审计证据只读保留，不作为新研究输入或新结果。

## 1 停掉的运行链路（实测证据）

| 项 | 证据 |
|---|---|
| 采集进程 | `python.exe` PID 28164，命令行 `research/collection/taipei_372_polling_20261030/poller.py --config ... --daemon`（2026-10-30 11:31 启动，371 轮） |
| 停止方式 | 用采集器自带 `poller.py --config config.json --stop`，写 `runtime/STOP` 哨兵（2026-10-31T10:37:58Z） |
| 停止后状态 | `runtime/state.json`：`"status": "stopped"`，最后成功槽 `2026-10-31T18:35+08:00`，心跳 `18:38:05+08:00`，consecutive_failures 0，gaps 2 条（10-30 11:35、15:10–15:15） |
| 进程核验 | `Get-CimInstance Win32_Process` 过滤 poller/parking：0 个残留 |
| 自动重启 | `Get-ScheduledTask` 全表按 Execute/Arguments 匹配 parking/taipei/372：0 条；项目无 supervisor/守护脚本；`start_polling.ps1` 仅为人工启动器 |
| 健康监测 | 由同一 daemon 循环内完成（`--health` 仅按需打印），无独立定时任务，随进程一并停止 |

未触碰项目外进程：同机其他 node/python 进程（WorkBuddy、Codex、投资大赛 watch 等）均未操作。

## 2 从现行程序移除的专属接口与依赖

| 对象 | 处理 |
|---|---|
| `apps/parking_lab/workbench/datasource.py`（唯一台北适配器，含 `TaipeiReplay`、`SEMANTICS`、`DEFAULT_COLLECTION`） | 移出执行链路 → `research/round8_20261031/taipei_exit/removed/datasource.py`，SHA-256 `08ebf8e4775a421058c5f6864fcc21ba1b1ada5149a42f19314acc0abd817e41`，登记于 `REMOVAL_MANIFEST.json` |
| `server.py` | 删除 `datasource` 导入、`datasource_summary`、`_replay_feed`、`_DS_LOCK/_DS_CACHE/DATASOURCE_TTL_SECONDS`、GET/POST `/api/datasource`、导出格式 `datasource_json`、`/api/health` 的 `datasource_available`、state/export 中的 `datasource` 块 |
| `continuous.py` | 删除 `datasource` 构造参数与属性、`start_replay("taipei")` 分支与 `datasource.step`；回放源只接受 `synthetic`（通用合成账本回放保留），错误信息明确 |
| `__main__.py` | 删除 `--collection`、`--now` 与 `data-span` 子命令；`traffic` 子命令保留但 `--params` 明示须为 round8 公开数据标定参数 |
| `web/index.html`、`web/app.js` | 删除“台北已保存批次（只读）”面板及其 10 个 DOM 字段、`replay-taipei` 按钮与监听、`renderDatasource`、`ds-refresh` 控件、导出选项“台北数据源 JSON” |
| 默认测试链 | 从 `test_runtime.py`（11）、`test_http.py`（3）、`test_security_round4.py`（11）移除依赖台北批次/接口的方法；补偿新增 `tests/test_round8_exit.py`（8 项退出不变量：模块不存在、无可执行残留引用、文案仅限历史标注、UI 无控件、无路由、回放只收 synthetic、无外连客户端导入、CLI 无 --collection） |
| 当前说明 | `apps/parking_lab/README.md` 改写“持续运行与真实数据”节与导出接口清单；项目根 `README.md` 数据行与本轮方向改写 |
| 旧车流生成器 | `traffic_gen.py` 首行标注 HISTORICAL：台北面板已退出执行链，其 `fitted_parameters.json` 只作历史证据，不是新运行默认输入 |

## 3 明确保留的通用能力（未动）

- 通用事件仿真与有限窗口连续运行（realtime/accelerated/paused/synthetic replay）；
- 配对重放与哈希一致性（`costs.traffic_hash`，两侧哈希不等即拒绝差值）；
- 五态语义（valid / not_applicable_zero_demand / censored_no_departure / missing / illegal）与双服务水平判定；
- 安全能力与回归（原子写、会话上限、只监听 127.0.0.1、无 shell/外连客户端导入等）。

## 4 历史材料（只读，退出执行链路）

- `research/collection/taipei_372_polling_20261030/`：原始批次、cohort、config、日志、STOP 哨兵与 state.json 全部保留原样，不再被程序读取；
- `docs/reports/` 中台北相关历史报告保留；
- 稿件侧：当前 rev4 工作稿内容（`paper/draft/paper_v3_round6_rev3_content.py`）**无** Taipei 引用；旧 v1 内容文件 `paper/draft/paper_v2_content.py` 仍含 Taipei 成本参数表（历史 v1 模型，rev4 已移出主结果、只在 SI S7 作历史说明），保留不改、不作新数据依据。

## 5 验收

```text
python -m unittest discover -s apps/parking_lab/workbench/tests -p "test_*.py"
→ Ran 414 tests  OK   (2026-10-31 复跑；371 为退出后首跑的旧计数，414 含新增 publicdata/energy_ledger 测试)
```

新增 `test_round8_exit.py` 8 项全部通过；退出后工作台仍可 `python -m apps.parking_lab.workbench serve` 启动（无台北面板/接口）。

## 6 未在本文件宣称的事

- 不宣称台北历史数据无价值：它只作为历史证据留存，不进入新研究输入或新结果；
- 不宣称其他城市/其他机器的采集任务已停止：本轮只处理本项目台北链路，未触碰项目外进程与任务。
