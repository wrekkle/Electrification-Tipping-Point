# 文献索引与阅读登记

状态: 生效
负责人: tho25
日期: 2026-10-29

| 文件 | 是什么 | 谁写 |
|---|---|---|
| `index.json` | 机器可读索引，含编号、题名、DOI/来源、版本、PDF 路径、下载状态、阅读状态、笔记、校验发现 | 脚本（`lit_index.py --write`） |
| `INDEX.md` | 同一份索引的人读版，按 P 组 / M 组与方向分组 | 脚本 |
| `reading-log.json` | 人工登记的阅读状态与依据；未登记的按分组默认值 | 人 |
| `notes/` | 精读笔记，文件名以编号开头，如 `P09-准入定价.md` | 人 |

## 状态词

未开始 / 摘要级 / 全文略读 / 精读并记笔记 / 已验证 / 已引用。后三种须在 `notes/` 有笔记。
**下载不表示读过；改阅读状态要写依据。**

## 导入一篇文献

1. PDF 放进既有目录（P 组 `research/ev_parking_math_20261029/PDFs/`，M 组 `papers/electrification-math/`），
   文件名沿用 `<编号>_<短名>[_版本].pdf`。
2. 新下载另存记录，包含 SHA-256、页数、版本、入口；历史清单不覆盖。M组更新文件在配置的
   `literature.m_download_updates` 登记，由索引脚本按顺序合并。
3. 需要读全文就写 `notes/<编号>-<短名>.md`，模板见 `notes/README.md`。
4. 在 `reading-log.json` 的 `items` 里登记该编号的状态与依据路径。
5. 跑 `python scripts/lit_index.py --write` 重建索引，再跑 `python scripts/check_all.py` 确认无错误。

## 引用与版本

同一论文的不同版本要分清（预印本、作者稿、期刊排版版），版本写进索引的"版本"字段。
P08 是 1999 年报告版、P07 是扫描版、M03 是工作论文、M04 是 arXiv v2——引用前核对首页。
