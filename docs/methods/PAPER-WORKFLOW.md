# 稿件工作流

类型: 规范
状态: 生效
负责人: tho25
日期: 2026-10-29

管的是稿件怎么走阶段、版本怎么叫、论点怎么追溯、每天怎么操作。文献侧见
[literature/README.md](../../literature/README.md)。

## 正文只有一份

最新正文 = `main_paper/Electrification tipping point_manuscript 202603submit.docx`。这是投稿版，冻结。
`research/electrification/manuscript_extracted.txt` 是从它抽出来的文本，只读，不能当稿件改。
当前工作稿是 `paper/draft/Electrification_tipping_point_v2_draft_2026-10-29.docx`，已在 SECTIONS.md 登记；
它不替代投稿版，也不自动升级为定稿。以后若建 Markdown 工作稿，同样放 `paper/draft/` 并登记，
不允许两份同时称为最新。

## 六个阶段与完成条件

| 阶段 | 完成条件 |
|---|---|
| 构思 | 一句话写清问题、缺口、打算怎么做；能指出至少 3 篇相关文献 |
| 提纲 | 章节结构与每节论点齐备；每个论点标明证据来源（文献/数据/代码/推导） |
| 初稿 | 各节成文、图表编号可引用；未证明处标"待验证" |
| 修订 | 六项自查（符号、量纲、口径、引用编号、图表一致、术语统一）过一遍并留记录 |
| 核验 | 关键数值可复算、引用可追到具体页码或式号；未复现的写"未复现" |
| 定稿 | 期刊格式、字数与图表要求齐备；改动只做编辑性修改 |

阶段只能由实际工作结果推进：没有对应证据就不许标"核验"或"定稿"。

## 版本与修订记录

原始文件不改名、不覆盖。新版本命名 `paper/draft/YYYY-MM-DD-短名.md`，修订记录写进
`docs/reports/YYYY-MM-DD-修订记录.md`，一条写清改了什么、为什么、影响哪几节。
交接时在 `docs/PROGRESS.md` 更新"现在在哪"，在 `docs/TODO.md` 留下一步。

## 论点怎么追溯

每个关键论点、公式、图、表、实验结论都要能指到一处证据：文献编号（P/M）+ 位置，或数据文件，或脚本与推导记录。
SECTIONS.md 的"证据缺口"就是这件事没做到的地方；`scripts/paper_stats.py` 只保证字数对得上，
不判断论点真假。

## 四种状态词不要混用

候选创新（还没检验的想法）、待验证假设（能写出检验方法）、已证明结果（有证明或可复算证据）、
已完成实验（跑过并有记录）。现有项目里：候选创新有，前三类多数没有——不要把管理整理写成"已验证"。

## 日常五个动作

1. 导入一篇文献：PDF 按既有目录存放 → 在 `literature/reading-log.json` 登记状态与依据 → `python scripts/lit_index.py --write`。
2. 更新一章稿件：改 Word 工作稿 → `python scripts/paper_stats.py --manuscript <工作稿> --out <新报告>` 统计；
   `--write-sections` 只用于配置所指的投稿版 stats 块，不得把工作稿统计混进去 → 在 SECTIONS.md 改阶段/证据缺口/下一步。
3. 检查字数：`python scripts/paper_stats.py`；要报告加 `--out`。
4. 登记进度：改 `docs/PROGRESS.md` 的数字与阶段，待办写进 `docs/TODO.md`。
5. 交接：写清现在在哪（PROGRESS）、下一步做什么（TODO 未做段）、卡在哪（未解决段）、怎么验证（命令）后再离开。
