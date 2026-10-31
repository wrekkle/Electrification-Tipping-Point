# 停车场充电桩优化论文项目

状态: 生效
负责人: tho25
日期: 2026-10-30

以论文发表为目标，研究停车场充电设施配置、车位共享、随机需求与算法优化。主稿是已投稿的
Word 稿件；另有已登记的 v2 扩写工作稿和独立 Python 后端。冻结投稿版保持原样，
当前按用户2026-10-31决定改为公开停车数据驱动：台北专属采集与回放链路已退出运行程序（历史批次只读留档，见 [退出清单](research/round8_20261031/taipei_exit/INVENTORY.md)），研究证据集中在 `research/round8_20261031/`，研究结论尚未定稿。

## 现在在哪（2026-10-30 实测）

| 项 | 状态 |
|---|---|
| 主稿 | `main_paper/Electrification tipping point_manuscript 202603submit.docx`，141 段，分范围合计英文 5776 词，40 条非空参考文献，8 图 8 表；较旧统计变化来自空段/题注口径修正，Word未改 |
| 文献 | P/M 组文献的数量、版本、PDF 与阅读状态均以 [literature/INDEX.md](literature/INDEX.md) 为准 |
| 阅读 | 实际范围与证据见阅读登记及 `literature/notes/`，下载、阅读、验证分别记录 |
| 研究 | 原 R1–R6 修复已复验；新发现的实现/实验与区间覆盖问题见 T14，原稿数值未对齐 |
| 数据 | 公开停车数据选型/下载/质检证据在 `research/round8_20261031/data/`（主源确定后登记 DATASET_CHOICE.md 与 PROVENANCE.json）；台北历史批次已退出执行链路，只读留档 |
| 稿件阶段 | 投稿版（文件名标注 2026-03），本仓库不据此声称已录用 |

## 我要看什么

- 接手/开始干活：[AGENTS.md](AGENTS.md) → [docs/PROGRESS.md](docs/PROGRESS.md) → [docs/TODO.md](docs/TODO.md)
- 稿件与章节：[paper/SECTIONS.md](paper/SECTIONS.md)、[paper/README.md](paper/README.md)
- 当前总体规划：[交集全量观测与配置决策](docs/reports/2026-10-29-项目未来规划.md)
- 当前研究计划：[round8 计划与设计矩阵](research/round8_20261031/PLAN.md)（历史主线：[充电率证据与后端实施方案](docs/reports/2026-10-30-充电率证据与后端实施方案.md)）
- 仿真与在线学习：[实验台使用说明](apps/parking_lab/README.md)，运行 `python -m apps.parking_lab.workbench serve`
- 文献：统一索引 [literature/INDEX.md](literature/INDEX.md)（含 PDF 路径、下载状态、阅读状态、笔记）
- 研究路线：[research_framework.md](research/ev_parking_math_20261029/research_framework.md)、
  [算法解析与数学结合建议](research/electrification/算法解析与数学结合建议_2026-10-29.md)
- 目录说明与写法：[docs/README.md](docs/README.md)、[docs/methods/DOC-STYLE.md](docs/methods/DOC-STYLE.md)

## 常用命令

    python scripts/check_all.py                      # 全部只读检查
    python scripts/check_all.py --write-reports      # 另存三份报告到 docs/reports/
    python scripts/lit_index.py                      # 看文献索引摘要（不写）
    python scripts/lit_index.py --write              # 重写 literature/index.json 与 INDEX.md
    python scripts/paper_stats.py                    # 稿件字数（不使用 Word 缓存值）
    python scripts/paper_stats.py --check-sections    # 核对章节清单字数是否过期

配置只有一个：[repo-discipline.json](repo-discipline.json)（档位表、统计口径、路径归属）。

## 目录

| 目录 | 内容 |
|---|---|
| `main_paper/` | 原始 Word 稿（唯一正文来源） |
| `research/ev_parking_math_20261029/` | P 组 35 项文献清单、研究框架、29 篇 PDF、下载脚本与检索记录（历史） |
| `research/electrification/` | 算法解析、稿件提取文本与图像、处理脚本（历史） |
| `papers/electrification-math/` | M 组文献、历史清单与新增下载记录 |
| `literature/` | 统一文献索引、阅读登记、精读笔记 |
| `paper/` | 章节清单与稿件说明 |
| `plan/` | 原对话的工作笔记与进度（历史） |
| `docs/` | 待办、进度、方法规范、生成报告 |
| `scripts/` | 只读检查脚本 |
| `metadata/` | 迁移清单与 SHA-256 校验（历史） |

历史记录（`plan/`、`research/`、`metadata/`、`待手动下载论文链接_2026-10-29.md`）保留原样，
是当时的快照；与现状不符时以 [literature/INDEX.md](literature/INDEX.md) 和
[docs/PROGRESS.md](docs/PROGRESS.md) 为准，差异登记在 [docs/TODO.md](docs/TODO.md)。

## 公开展示（GitHub）

本仓库同步到 <https://github.com/wrekkle/Electrification-Tipping-Point>，用于展示研究代码、文档与稿件。
按体积与版权原因不入库：`research/collection/`（已退出采集链路的原始抓取）、`tmp/`、`papers/`（文献 PDF 原件）、
各轮原始数据与结果表（单文件 ≥100KB 的 `.json`/`.csv` 结果、`.pdf`/`.zip`/`.gz`/`.jsonl`/`.mat` 等格式）、
Octave 运行时产物与 `_scratch/` 临时脚本，以及稿件的历史重复版本（只保留 `main_paper/` 投稿版与最新工作稿）。
上述内容的说明、参数与统计口径仍在对应 `docs/`、`research/*/PLAN.md` 与 [literature/INDEX.md](literature/INDEX.md) 中。

