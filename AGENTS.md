# 项目规则

类型: 规范
状态: 生效
负责人: tho25
日期: 2026-10-29

本项目研究停车场充电设施配置、车位共享与随机需求优化，以论文发表为目标。
这是全仓库唯一的 agent 规则文件；其他项目说明与本文件冲突时，以本文件为准，用户明确指令优先。
这里只放长期执行规则；当前事实、进度和任务分别查对应入口，不在这里复制。

## 先定位任务

首次接手依次读 [README.md](README.md) → [docs/PROGRESS.md](docs/PROGRESS.md) →
[docs/TODO.md](docs/TODO.md)。同一对话已读且未变的文件不重复通读。

| 本次任务 | 再读 |
|---|---|
| 写稿、改章节、统计稿件 | [paper/SECTIONS.md](paper/SECTIONS.md)、[稿件流程](docs/methods/PAPER-WORKFLOW.md) |
| 检索、下载、阅读或引用文献 | [literature/README.md](literature/README.md)；写笔记再读 [笔记模板](literature/notes/README.md) |
| 写管理说明或报告 | [文档写法](docs/methods/DOC-STYLE.md)；目录归属查 [docs/README.md](docs/README.md) |
| 改检查脚本或统计口径 | [repo-discipline.json](repo-discipline.json) 与相关脚本 |

只处理当前请求；任务清单用于定位和登记，不表示自动执行其中全部任务。
发现其他问题，登记到 docs/TODO.md 并继续不受影响的工作。

提示词与一般进度答复留在对话，不按 Agent 新建文档。同阶段结果集中追加既有报告；过时提示词和交付记录归入 `docs/reports/archive/`，保留证据并修正链接。细则见文档写法。

## 文件边界与事实来源

| 对象 | 执行规则 |
|---|---|
| `main_paper/` | 冻结的投稿版原件，不改名、不覆盖、不删除。统计对象由配置的 `paper.manuscript` 指定。 |
| `paper/draft/` | Word 或 Markdown 工作稿；当前工作文件、阶段及版本关系以 SECTIONS.md 登记为准，不凭文件名判断。修改按当前任务授权进行，保留原件与备份。 |
| `paper/SECTIONS.md` | 维护章节、阶段与证据缺口；`stats` 字数块只由脚本写，当前对应冻结投稿版。工作稿统计须另存报告。 |
| `research/`、`plan/`、`metadata/` | 既有历史文件只读；允许按任务新增研究、复现或校验文件，不重写旧记录。补全文献可向既有 PDF 目录新增文件。 |
| `papers/` | 文献原文与下载证据；保留历史清单，新增下载另记更新记录，并按文献说明登记到配置。 |
| `literature/` | 阅读状态认 `reading-log.json`，精读证据认 `notes/`；`index.json`、`INDEX.md` 由脚本生成，不手改。 |
| `docs/` | PROGRESS.md 是进度入口，TODO.md 是唯一任务登记处；其他文档可引用任务编号、描述证据缺口，不另建任务清单。脚本生成报告不手改。 |
| `scripts/`、`repo-discipline.json` | 按任务维护检查实现与口径；默认检查只读，写入必须有显式输出参数。 |

提取文本、研究报告与字数报告均不是正文。历史记录与现状不符时，保留历史，
用当前索引、实测结果及带日期的新报告说明差异。工作稿不自动升级为投稿定稿。

## 研究证据

- 下载、阅读、验证分别登记。阅读状态只能按实际阅读范围和证据推进；标为“精读并记笔记”“已验证”“已引用”前，须有对应编号的 `literature/notes/` 笔记。
- 关键论点、公式和引用写明文献编号、版本及页码/式号；只有摘要时，不推断全文的定理条件或实验结果。
- 候选创新、假设、证明和实验结果分清。没有证明或运行证据就写“未证/未复现/未做”，不得把管理整理当成研究验证。
- 实验记录数据来源、参数、随机种子、运行命令与输出位置；原稿方法与自行扩展的方法分别说明。
- 数量、下载状态与字数由脚本复算；快照注明日期、统计对象和命令，现状优先引用索引与报告，不手抄另一份计数。
- 任务及完成标准只在 docs/TODO.md 维护；只有研究阶段或交接事实改变时，才同步 PROGRESS.md、SECTIONS.md 的相关内容。

## 检查与交付

有文件改动后运行：

```text
python scripts/check_all.py
```

缺少 `python-docx` 时，先用工作区已有且带依赖的 Python 运行；不可用就报告该检查未完成。
区分本次新增问题与原有问题；修复本次造成的问题，其他问题登记到 docs/TODO.md。
检查退出失败或依赖缺失都不能称为“全部通过”；结构检查通过也不代表论文结论成立。

按改动选择写入命令，先核对对象与输出范围：

| 场景 | 命令与范围 |
|---|---|
| 更新文献数据后 | `python scripts/lit_index.py --write`，只重建文献索引 |
| 同步配置所指稿件的字数块 | `python scripts/paper_stats.py --write-sections` |
| 统计工作稿 | `python scripts/paper_stats.py --manuscript <工作稿路径> --out <新报告路径>`；不加 `--write-sections` 或 `--check-sections`，避免与投稿版统计混用 |
| 确需落盘检查报告 | `python scripts/check_all.py --write-reports`，只写生成报告 |

交付写清改了什么、验证命令和结果、剩余限制，并链接实际产物。未执行的检查如实说明。
