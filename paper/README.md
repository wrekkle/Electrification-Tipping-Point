# 稿件说明

类型: 说明
状态: 生效
负责人: tho25
日期: 2026-10-29

| 文件 | 是什么 | 能不能改 |
|---|---|---|
| `main_paper/Electrification tipping point_manuscript 202603submit.docx` | 投稿版正文，唯一最新版 | 冻结；要改另存新版本 |
| `research/electrification/manuscript_extracted.txt` / `.json` | 从 docx 抽取的文本与段落，供检索 | 只读；重新抽取由脚本做 |
| `research/electrification/equations.xml` | 从 docx 抽出的公式 XML | 只读 |
| `SECTIONS.md` | 章节清单：目的、阶段、字数、证据缺口、下一步 | 人改文字，字数块由脚本写 |
| `draft/` | 已登记的 v2 Word 工作稿 `Electrification_tipping_point_v2_draft_2026-10-29.docx`、生成脚本与 `backup/` 投稿版备份 | 可继续改；须在 SECTIONS.md 登记，保留备份 |

字数只由 `scripts/paper_stats.py` 从 docx 解析；报告见 `docs/reports/`。Word 的缓存字数不用。
`stats` 块只对应投稿版；工作稿统计用 `--manuscript <工作稿> --out <报告>`，不得用 `--write-sections`。
阶段定义见 `docs/methods/PAPER-WORKFLOW.md`。
